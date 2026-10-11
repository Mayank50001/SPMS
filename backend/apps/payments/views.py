"""Payment API views (increment 5.3, D59).

The first Phase 5 write path. Creation is delegated to
``services.create_payment_attempt`` so the state checks and the gateway call
live in one place; the view maps stable refusal codes to HTTP statuses only
(Q10, PROJECT.md §33), exactly like the booking views (4.4).
"""

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import IsConsumer, IsAdminOrManager
from apps.bookings.services import BookingRuleError

from .models import Payment

from .serializers import (
    PaymentConfirmSerializer,
    PaymentCreateSerializer,
    PaymentHistoryQuerySerializer,
    PaymentHistorySerializer,
    PaymentSerializer,
    RefundSerializer,
    ReceiptSerializer,
    TransactionSerializer,
)
from .services import (
    InvalidWebhookSignatureError,
    PaymentCapturedNotAppliedError,
    PaymentError,
    PaymentGatewayUnavailableError,
    annotate_refunded_amount,
    confirm_payment_attempt,
    create_payment_attempt,
    filter_payments,
    get_payment_receipt,
    handle_payment_webhook,
    refund_payment,
)

#: Stable refusal code -> HTTP status (Q10). Shape errors are 400, state
#: conflicts 409, an unaddressable target 404, a dead provider 503.
REFUSAL_STATUS = {
    "BOOKING_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "BOOKING_NOT_PAYABLE": status.HTTP_409_CONFLICT,
    "BOOKING_ALREADY_PAID": status.HTTP_409_CONFLICT,
    "PAYMENT_GATEWAY_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
    "PAYMENT_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "PAYMENT_NOT_CONFIRMABLE": status.HTTP_409_CONFLICT,
    "PAYMENT_VERIFICATION_FAILED": status.HTTP_409_CONFLICT,
    "PAYMENT_CAPTURED_NOT_APPLIED": status.HTTP_409_CONFLICT,
    "INVALID_WEBHOOK_SIGNATURE": status.HTTP_400_BAD_REQUEST,
    "PAYMENT_NOT_REFUNDABLE": status.HTTP_409_CONFLICT,
    "PAYMENT_REFUND_FAILED": status.HTTP_502_BAD_GATEWAY,
    "BOOKING_NOT_EXTENDABLE": status.HTTP_409_CONFLICT,
    "INVALID_EXTENSION": status.HTTP_400_BAD_REQUEST,
    "MAX_DURATION_EXCEEDED": status.HTTP_400_BAD_REQUEST,
    "EXTENSION_ALREADY_PAID": status.HTTP_409_CONFLICT,
    "PAYMENT_NOT_REFUNDABLE": status.HTTP_409_CONFLICT,
    "PAYMENT_REFUND_FAILED": status.HTTP_502_BAD_GATEWAY,
    "RECEIPT_NOT_AVAILABLE": status.HTTP_409_CONFLICT,
}

def _visible_payments(request):
    """Payments a caller may list (5.9, D65; Invariant 2/3).

    Consumer -> their own payments. Manager -> payments on the lots assigned to
    them (``booking.slot.lot.manager``). Administrator -> all. Scoping is done
    here, in the queryset, so a caller who owns none gets an empty list -- never
    a 403. (The permissions module documents why "is this mine?" cannot be a
    permission class.)
    """
    queryset = Payment.objects.select_related(
        "booking__user", "booking__slot__lot"
    )
    user = request.user
    if user.role == User.Role.ADMIN:
        return queryset
    if user.role == User.Role.MANAGER:
        return queryset.filter(booking__slot__lot__manager=user)
    return queryset.filter(booking__user=user)

class PaymentListCreateView(generics.ListCreateAPIView):
    """List visible payments (5.9, D65), or start a payment (5.3, D59).

    ``GET /api/payments/``  -> the payments the caller may see
    ``POST /api/payments/`` -> start a PENDING attempt for an own booking

    Both roles share the path (PROJECT.md §22; D59 reserved the GET). The
    queryset is scoped by role (consumer -> own, manager -> assigned lots,
    admin -> all), so "may I see this row" is answered in one place and a caller
    who owns none gets an empty list, never a 403 (Invariant 2/3). The response
    shape is chosen the same way: a slim consumer item, an operator row
    otherwise. POST stays consumer-only and unchanged.
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsConsumer()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return PaymentCreateSerializer
        user = self.request.user
        if user.role in (User.Role.ADMIN, User.Role.MANAGER):
            return TransactionSerializer
        return PaymentHistorySerializer

    def get_queryset(self):
        queryset = _visible_payments(self.request)
        if self.request.method != "GET":
            return queryset

        query = PaymentHistoryQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        queryset = annotate_refunded_amount(queryset)
        return filter_payments(
            queryset,
            statuses=query.validated_data.get("status"),
            method=query.validated_data.get("method"),
            purpose=query.validated_data.get("purpose"),
            booking_id=query.validated_data.get("booking"),
            lot_id=query.validated_data.get("lot"),
            created_from=query.validated_data.get("created_from"),
            created_to=query.validated_data.get("created_to"),
            ordering=query.validated_data.get("ordering"),
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            payment, client_payload = create_payment_attempt(
                booking_id=serializer.validated_data["booking"],
                user=request.user,
                purpose=serializer.validated_data["purpose"],
                end_time=serializer.validated_data.get("end_time")
            )
        except (BookingRuleError, PaymentError) as exc:
            return Response(
                {"error": exc.code, "message": str(exc)},
                status=REFUSAL_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST),
            )

        data = PaymentSerializer(payment).data
        data["client_payload"] = client_payload
        return Response(data, status=status.HTTP_201_CREATED)

class PaymentConfirmView(generics.GenericAPIView):
    """Verify a returned Checkout callback and confirm the booking (5.4, D60).

    ``POST /api/payments/{id}/confirm/`` with the gateway's callback wrapped in
    ``{"payload": {...}}`` -> 200 with the payment now SUCCEEDED and its booking
    CONFIRMED. Consumer-only and owner-scoped, so a foreign or unknown id is a
    404 (Invariant 2). The backend verifies the signature itself; the client is
    never believed (§24/§25).
    """

    permission_classes = [IsConsumer]
    serializer_class = PaymentConfirmSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            payment = confirm_payment_attempt(
                payment_id=kwargs["pk"],
                user=request.user,
                payload=serializer.validated_data.get("payload") or {},
            )
        except (BookingRuleError, PaymentError) as exc:
            return Response(
                {"error": exc.code, "message": str(exc)},
                status=REFUSAL_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST),
            )

        return Response(PaymentSerializer(payment).data)

class PaymentWebhookView(APIView):
    """Provider-to-server payment webhook (5.4, D60).

    ``POST /api/payments/webhook/``. Public by design: Razorpay cannot send a
    JWT, so the **signature over the raw body** is the authentication, and it is
    checked before the body is parsed. Authentication and permission are cleared
    so the project-wide ``IsAuthenticated`` default (D18) cannot reject it.

    Status contract: an unverifiable webhook is 400 (refused); a verified event
    that is unknown, duplicated or "captured but not applied" is 200, so the
    provider stops retrying rather than hammering us forever.
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        try:
            handle_payment_webhook(body=request.body, headers=request.headers)
        except InvalidWebhookSignatureError as exc:
            return Response(
                {"error": exc.code, "message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except PaymentGatewayUnavailableError as exc:
            return Response(
                {"error": exc.code, "message": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except PaymentCapturedNotAppliedError:
            # Money recorded; the booking could not be applied. Acknowledge so
            # the provider does not retry; the refund is 5.5's concern.
            return Response({"status": "captured"})
        return Response({"status": "ok"})

class PaymentRefundView(generics.GenericAPIView):
    """Refund what is owed on a payment (5.5, D61).

    ``POST /api/payments/{id}/refund/`` -> 201 with the new ``Refund`` ledger
    row. Manager/Admin only: it is the operational refund/retry tool (a
    consumer's refund is triggered automatically when they cancel, 4.7). The
    amount is server-derived -- ``refundable_amount`` -- so a client can never
    choose it (§46); the §19 cutoff that decides it lives in Phase 4 (D53).

    Idempotent: repeating the call after a settled refund returns that same row
    instead of moving money again. A gateway failure is recorded as a FAILED
    refund and surfaced as ``PAYMENT_REFUND_FAILED`` (502); retry to make a new
    attempt.
    """

    permission_classes = [IsAdminOrManager]
    serializer_class = RefundSerializer

    def post(self, request, *args, **kwargs):
        try:
            refund = refund_payment(payment_id=kwargs["pk"])
        except (BookingRuleError, PaymentError) as exc:
            return Response(
                {"error": exc.code, "message": str(exc)},
                status=REFUSAL_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST),
            )
        return Response(
            RefundSerializer(refund).data, status=status.HTTP_201_CREATED
        )

class PaymentReceiptView(generics.GenericAPIView):
    """Read a receipt for a settled charge (5.8, D64).

    ``GET /api/payments/{id}/receipt/`` -> the JSON receipt for one SUCCEEDED
    payment, derived from the payment and its booking snapshot. Consumer-only and
    owner-scoped, so a foreign or unknown id is a 404 (Invariant 2). A charge that
    is not settled has no receipt (409 ``RECEIPT_NOT_AVAILABLE``).
    """

    permission_classes = [IsConsumer]
    serializer_class = ReceiptSerializer

    def get(self, request, *args, **kwargs):
        try:
            payment = get_payment_receipt(
                payment_id=kwargs["pk"], user=request.user
            )
        except PaymentError as exc:
            return Response(
                {"error": exc.code, "message": str(exc)},
                status=REFUSAL_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST),
            )
        return Response(ReceiptSerializer(payment).data)


