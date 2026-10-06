"""Booking API views (increment 4.4).

The first write path of the booking domain. Creation is delegated to
``services.create_booking`` so the slot lock, lazy expiry and conflict re-check
run atomically; the view only maps the service's stable refusal codes to HTTP
statuses (Q10, PROJECT.md §33).
"""

from rest_framework import generics, status
from rest_framework.response import Response

from apps.accounts.permissions import IsConsumer

from .models import Booking
from .serializers import BookingCreateSerializer, BookingSerializer
from .services import BookingRuleError, create_booking

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
}

class BookingListCreateView(generics.ListCreateAPIView):
    """List the caller's bookings, or create one (Invariant 2, PROJECT.md §16).

    ``GET /api/bookings/``  -> the caller's own bookings only
    ``POST /api/bookings/`` -> create a PENDING_PAYMENT booking

    Ownership is enforced by scoping the queryset to ``request.user`` (the
    permissions module documents that a role class cannot answer "is this
    booking mine?"). An anonymous caller gets 401; a Consumer can never read
    another Consumer's bookings.
    """

    permission_classes = [IsConsumer]

    def get_queryset(self):
        return (
            Booking.objects.filter(user=self.request.user)
            .select_related("slot__lot", "vehicle")
        )

    def get_serializer_class(self):
        if self.request.method == "POST":
            return BookingCreateSerializer
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


