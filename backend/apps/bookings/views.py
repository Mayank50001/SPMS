"""Booking API views (increment 4.4).

The first write path of the booking domain. Creation is delegated to
``services.create_booking`` so the slot lock, lazy expiry and conflict re-check
run atomically; the view only maps the service's stable refusal codes to HTTP
statuses (Q10, PROJECT.md §33).
"""

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import User
from apps.accounts.permissions import IsConsumer, IsManager

from .models import Booking
from .serializers import (
    BookingCreateSerializer,
    BookingDetailSerializer,
    BookingHistoryQuerySerializer,
    BookingOperatorSerializer,
    BookingSerializer,
    ExtensionQuoteQuerySerializer,
    ExtensionQuoteSerializer,
)
from .services import (
    BookingRuleError,
    cancel_booking,
    check_in_booking,
    check_out_booking,
    create_booking,
    filter_bookings,
    quote_extension,
)

from apps.payments.services import refund_booking

#: Stable refusal code -> HTTP status (Q10). Shape/client errors are 400,
#: state/config conflicts are 409, an unaddressable target is 404.
REFUSAL_STATUS = {
    "INVALID_WINDOW": status.HTTP_400_BAD_REQUEST,
    "WINDOW_IN_PAST": status.HTTP_400_BAD_REQUEST,
    "MIN_DURATION_NOT_MET": status.HTTP_400_BAD_REQUEST,
    "MAX_DURATION_EXCEEDED": status.HTTP_400_BAD_REQUEST,
    "SLOT_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "LOT_NOT_BOOKABLE": status.HTTP_404_NOT_FOUND,
    "SLOT_UNAVAILABLE": status.HTTP_409_CONFLICT,
    "BOOKING_CONFLICT": status.HTTP_409_CONFLICT,
    "NO_TARIFF": status.HTTP_409_CONFLICT,
    "BOOKING_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "BOOKING_NOT_CANCELLABLE": status.HTTP_409_CONFLICT,
    "BOOKING_NOT_EXTENDABLE": status.HTTP_409_CONFLICT,
    "INVALID_EXTENSION": status.HTTP_400_BAD_REQUEST,
    "BOOKING_NOT_CHECKINABLE": status.HTTP_409_CONFLICT,
    "BOOKING_NOT_CHECKOUTABLE": status.HTTP_409_CONFLICT,
}

def _visible_bookings(request):
    """Bookings a caller may list (6.1, D67; Invariant 2/3).

    Consumer -> their own bookings. Manager -> bookings on the lots assigned to
    them (``slot.lot.manager``). Administrator -> all. Scoping is done here, in
    the queryset, so a caller who owns none gets an empty list -- never a 403.
    (The permissions module documents why "is this mine?" cannot be a permission
    class.)
    """
    queryset = Booking.objects.select_related("slot__lot__city", "vehicle")
    user = request.user
    if user.role == User.Role.ADMIN:
        return queryset
    if user.role == User.Role.MANAGER:
        return queryset.filter(slot__lot__manager=user)
    return queryset.filter(user=user)

class BookingListCreateView(generics.ListCreateAPIView):
    """List the caller's bookings, or create one (Invariant 2, PROJECT.md §16).

    ``GET /api/bookings/``  -> the caller's own bookings only
    ``POST /api/bookings/`` -> create a PENDING_PAYMENT booking

    Ownership is enforced by scoping the queryset to ``request.user`` (the
    permissions module documents that a role class cannot answer "is this
    booking mine?"). An anonymous caller gets 401; a Consumer can never read
    another Consumer's bookings.
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsConsumer()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = _visible_bookings(self.request)
        if self.request.method == "GET":
            history = BookingHistoryQuerySerializer(data=self.request.query_params)
            history.is_valid(raise_exception=True)
            return filter_bookings(
                queryset, statuses=history.validated_data.get("status"),
                scope=history.validated_data.get("scope"),
                lot_id=history.validated_data.get("lot"),
                ordering=history.validated_data.get("ordering"),
            )
        return queryset
            

    def get_serializer_class(self):
        if self.request.method == "POST":
            return BookingCreateSerializer
        user = self.request.user
        if user.role in (User.Role.ADMIN, User.Role.MANAGER):
            return BookingOperatorSerializer
        return BookingSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            booking = create_booking(
                slot_id=data["slot"].id,
                start_time=data["start_time"],
                end_time=data["end_time"],
                user=request.user,
                vehicle=data["vehicle"],
            )
        except BookingRuleError as exc:
            return Response(
                {"error": exc.code, "message": str(exc)},
                status=REFUSAL_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST),
            )

        return Response(
            BookingSerializer(booking).data, status=status.HTTP_201_CREATED
        )

class BookingCancelView(generics.GenericAPIView):
    """Cancel the caller's own booking (increment 4.7, D53).

    ``POST /api/bookings/{id}/cancel/`` -> the booking as ``CANCELLED``, with
    any refund the §19 cutoff entitles the consumer to stored on it. No money
    moves here; Phase 5's gateway reads ``refund_due_amount``.

    Only a Consumer may call it, and the service scopes the lookup to the
    caller, so another consumer's booking is a 404 (Invariant 2). The service
    owns the state check and maps to ``BOOKING_NOT_CANCELLABLE`` (409) for a
    booking that is already in progress/complete/expired/terminated.
    """

    permission_classes = [IsConsumer]
    serializer_class = BookingSerializer

    def post(self, request, *args, **kwargs):
        try:
            booking = cancel_booking(booking_id=kwargs["pk"], user=request.user)
        except BookingRuleError as exc:
            return Response(
                {"error": exc.code, "message": str(exc)},
                status=REFUSAL_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST),
            )

        # D53/D61 (5.5): cancellation stored the §19 entitlement; Phase 5 now
        # moves the money. Best-effort -- a failed refund is recorded on the
        # payment and retriable via POST /api/payments/{id}/refund/, so a dead
        # gateway never un-cancels a booking.
        if booking.refund_due_amount > 0:
            refund_booking(booking)

        return Response(BookingSerializer(booking).data)

class BookingExtensionQuoteView(generics.GenericAPIView):
    """Price extending the caller's booking, without changing it (4.8, D54).

    ``GET /api/bookings/{id}/extension-quote/?end_time=...`` -> the added hours
    and amount Phase 5 will charge. Read-only, so it is safe to call while the
    consumer decides; the write itself is ``services.extend_booking``, which
    Phase 5's gateway calls after the payment succeeds.
    """

    permission_classes = [IsConsumer]
    serializer_class = ExtensionQuoteSerializer

    def get(self, request, *args, **kwargs):
        booking = (
            Booking.objects.filter(user=request.user)
            .select_related("slot")
            .filter(pk=kwargs["pk"])
            .first()
        )
        if booking is None:
            return Response(
                {
                    "error": "BOOKING_NOT_FOUND",
                    "message": "No booking with this id exists.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        window = ExtensionQuoteQuerySerializer(data=request.query_params)
        window.is_valid(raise_exception=True)

        try:
            quote = quote_extension(
                booking=booking, new_end_time=window.validated_data["end_time"]
            )
        except BookingRuleError as exc:
            return Response(
                {"error": exc.code, "message": str(exc)},
                status=REFUSAL_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST),
            )
        return Response(ExtensionQuoteSerializer(quote).data)

class BookingDetailView(generics.GenericAPIView):
    """Read one of the caller's own bookings (increment 4.9).

    ``GET /api/bookings/{id}/`` -> the rich :class:`BookingDetailSerializer`
    shape. Consumer-only and scoped to the caller, so a foreign or unknown id is
    a 404 carrying the booking lifecycle's stable ``BOOKING_NOT_FOUND`` code --
    never a 403 (Invariant 2) -- matching cancel/confirm/extend. Read-only: it
    writes nothing and derives everything from the stored row.
    """

    permission_classes = [IsConsumer]
    serializer_class = BookingDetailSerializer

    def get(self, request, *args, **kwargs):
        booking = (
            Booking.objects.filter(user=request.user)
            .select_related("slot__lot__city", "vehicle")
            .filter(pk=kwargs["pk"])
            .first()
        )
        if booking is None:
            return Response(
                {
                    "error": "BOOKING_NOT_FOUND",
                    "message": "No booking with this id exists.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(BookingDetailSerializer(booking).data)

class BookingCheckInView(generics.GenericAPIView):
    """Simulate a vehicle entering an assigned lot (6.3, D69).

    ``POST /api/bookings/{id}/check-in/`` -> the booking as ``IN_PROGRESS`` with
    ``actual_entry_at`` stamped and the slot marked ``OCCUPIED``.

    Manager-only and scoped to the booking's assigned lot: a foreign booking, or
    one in a lot this manager is not assigned to, is a ``404``
    (``BOOKING_NOT_FOUND``), never a ``403`` (Invariant 2/3). Only a
    ``CONFIRMED`` booking may enter; a repeat is idempotent.
    """

    permission_classes = [IsManager]
    serializer_class = BookingOperatorSerializer

    def post(self, request, *args, **kwargs):
        try:
            booking = check_in_booking(booking_id=kwargs["pk"], user=request.user)
        except BookingRuleError as exc:
            return Response(
                {"error": exc.code, "message": str(exc)},
                status=REFUSAL_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST),
            )
        return Response(BookingOperatorSerializer(booking).data)

class BookingCheckOutView(generics.GenericAPIView):
    """Simulate a vehicle leaving an assigned lot (6.3, D69).

    ``POST /api/bookings/{id}/check-out/`` -> the booking as ``COMPLETED`` with
    ``actual_exit_at`` stamped and the slot returned to ``AVAILABLE``.

    Same Manager-only, assigned-lot scope and 404-not-403 rule as check-in. Only
    an ``IN_PROGRESS`` booking may leave; a repeat is idempotent.
    """

    permission_classes = [IsManager]
    serializer_class = BookingOperatorSerializer

    def post(self, request, *args, **kwargs):
        try:
            booking = check_out_booking(booking_id=kwargs["pk"], user=request.user)
        except BookingRuleError as exc:
            return Response(
                {"error": exc.code, "message": str(exc)},
                status=REFUSAL_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST),
            )
        return Response(BookingOperatorSerializer(booking).data)