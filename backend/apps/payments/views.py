"""Payment API views (increment 5.3, D59).

The first Phase 5 write path. Creation is delegated to
``services.create_payment_attempt`` so the state checks and the gateway call
live in one place; the view maps stable refusal codes to HTTP statuses only
(Q10, PROJECT.md §33), exactly like the booking views (4.4).
"""

from rest_framework import generics, status
from rest_framework.response import Response

from apps.accounts.permissions import IsConsumer
from apps.bookings.services import BookingRuleError

from .serializers import PaymentCreateSerializer, PaymentSerializer
from .services import PaymentError, create_payment_attempt

#: Stable refusal code -> HTTP status (Q10). Shape errors are 400, state
#: conflicts 409, an unaddressable target 404, a dead provider 503.
REFUSAL_STATUS = {
    "BOOKING_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "BOOKING_NOT_PAYABLE": status.HTTP_409_CONFLICT,
    "BOOKING_ALREADY_PAID": status.HTTP_409_CONFLICT,
    "PAYMENT_GATEWAY_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
}

class PaymentCreateView(generics.GenericAPIView):
    """Start an online payment for the caller's own booking (5.3, D59).

    ``POST /api/payments/`` with ``{"booking": <id>}`` -> 201 with the PENDING
    payment plus the ``client_payload`` the client uses to open Razorpay
    Checkout. Consumer-only and scoped to the caller, so a foreign or unknown
    booking is a 404 (Invariant 2). It does **not** confirm anything: verifying
    the callback and moving the booking to CONFIRMED is 5.4.
    """

    permission_classes = [IsConsumer]
    serializer_class = PaymentCreateSerializer
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            payment, client_payload = create_payment_attempt(
                booking_id=serializer.validated_data["booking"],
                user=request.user,
            )
        except (BookingRuleError, PaymentError) as exc:
            return Response(
                {"error": exc.code, "message": str(exc)},
                status=REFUSAL_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST),
            )

        data = PaymentSerializer(payment).data
        data["client_payload"] = client_payload
        return Response(data, status=status.HTTP_201_CREATED)