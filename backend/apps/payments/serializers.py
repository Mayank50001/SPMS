"""Payment request/response shapes (increment 5.3, D59).

As elsewhere, the write shape is minimal and the client never sends a
server-computed value (PROJECT.md §45/§46): the amount and currency are read
from the booking server-side.
"""

from rest_framework import serializers

from .models import Payment, Refund


class PaymentCreateSerializer(serializers.Serializer):
    """Write shape for ``POST /api/payments/`` (5.3, D59).

    A plain ``Serializer``: only the target booking is accepted. Ownership is
    checked by the service, not here, so a foreign booking is a 404 rather than
    a per-field error (Invariant 2).
    """

    booking = serializers.IntegerField(min_value=1)


class PaymentSerializer(serializers.ModelSerializer):
    """Read representation of a payment (5.3, D57)."""

    class Meta:
        model = Payment
        fields = [
            "id",
            "booking",
            "purpose",
            "method",
            "status",
            "amount",
            "currency",
            "provider_order_id",
            "provider_payment_id",
            "failure_reason",
            "paid_at",
            "booking_applied",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

class PaymentConfirmSerializer(serializers.Serializer):
    """Write shape for ``POST /api/payments/{id}/confirm/`` (5.4, D60).

    The client returns whatever the gateway's Checkout handed the browser,
    wrapped under ``payload``. It is passed straight to the adapter's
    ``verify_payment``, so the field names stay the provider's, not ours -- and
    the client can never supply an amount, currency or order id we act on (the
    stored order id is what gets signed, D56/§46).
    """

    payload = serializers.DictField(required=False, default=dict)


class RefundSerializer(serializers.ModelSerializer):
    """Read representation of a refund ledger event (5.5, D61)."""

    class Meta:
        model = Refund
        fields = [
            "id",
            "payment",
            "amount",
            "status",
            "provider_refund_id",
            "reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields