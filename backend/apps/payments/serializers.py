"""Payment request/response shapes (increment 5.3, D59).

As elsewhere, the write shape is minimal and the client never sends a
server-computed value (PROJECT.md §45/§46): the amount and currency are read
from the booking server-side.
"""

from rest_framework import serializers

from .models import Payment, Refund

from .services import payment_receipt_number


class PaymentCreateSerializer(serializers.Serializer):
    """Write shape for ``POST /api/payments/`` (5.3, D59).

    A plain ``Serializer``: the target booking plus, for an extension, the new
    end time. Ownership and pricing are checked by the service, not here, so a
    foreign booking is a 404 rather than a per-field error (Invariant 2) and the
    amount is never accepted from the client (§46).
    """

    booking = serializers.IntegerField(min_value=1)
    purpose = serializers.ChoiceField(
        choices=Payment.Purpose.choices,
        required=False,
        default=Payment.Purpose.BOOKING,
    )
    end_time = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        # D62: only an EXTENSION carries a target end time, and it must carry
        # one. A clean 400 here; the Payment constraint enforces it again in the
        # database.
        purpose = attrs.get("purpose", Payment.Purpose.BOOKING)
        end_time = attrs.get("end_time")
        if purpose == Payment.Purpose.EXTENSION and end_time is None:
            raise serializers.ValidationError(
                {"end_time": "An extension payment requires the new end time."}
            )
        if purpose == Payment.Purpose.BOOKING and end_time is not None:
            raise serializers.ValidationError(
                {"end_time": "Only an extension payment may set an end time."}
            )
        return attrs


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
            "extension_end_time",
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

class ReceiptSerializer(serializers.Serializer):
    """Read shape for a payment receipt (5.8, D64).

    A derived projection, not a stored model: every field is read from the settled
    ``Payment`` and its booking snapshot. ``receipt_number`` reuses the same helper
    the gateway call uses, so a provider reference and a customer-facing receipt
    agree.
    """

    receipt_number = serializers.SerializerMethodField()
    payment = serializers.IntegerField(source="id", read_only=True)
    status = serializers.CharField(read_only=True)
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    currency = serializers.CharField(read_only=True)
    method = serializers.CharField(read_only=True)
    purpose = serializers.CharField(read_only=True)
    paid_at = serializers.DateTimeField(read_only=True)
    transaction_id = serializers.CharField(
        source="provider_payment_id", read_only=True
    )

    booking = serializers.IntegerField(source="booking_id", read_only=True)
    booking_reference = serializers.CharField(
        source="booking.reference", read_only=True
    )
    slot_number = serializers.CharField(
        source="booking.slot.number", read_only=True
    )
    lot_code = serializers.CharField(source="booking.slot.lot.code", read_only=True)
    lot_name = serializers.CharField(source="booking.slot.lot.name", read_only=True)
    start_time = serializers.DateTimeField(
        source="booking.start_time", read_only=True
    )
    end_time = serializers.DateTimeField(source="booking.end_time", read_only=True)
    billed_hours = serializers.IntegerField(
        source="booking.billed_hours", read_only=True
    )

    def get_receipt_number(self, obj):
        return payment_receipt_number(obj)

class PaymentHistoryQuerySerializer(serializers.Serializer):
    """Validates the filters of ``GET /api/payments/`` (5.9, D65).

    Every filter is optional; omitting all of them returns every payment the
    caller may see (newest first). ``status`` accepts one or more comma-separated
    stored states; an unknown token is a field-shaped 400. Mirrors the booking
    history filters (4.9) so the two reads feel the same.
    """

    status = serializers.CharField(required=False)
    method = serializers.ChoiceField(
        choices=Payment.Method.choices, required=False
    )
    purpose = serializers.ChoiceField(
        choices=Payment.Purpose.choices, required=False
    )
    booking = serializers.IntegerField(required=False, min_value=1)
    lot = serializers.IntegerField(required=False, min_value=1)
    created_from = serializers.DateTimeField(required=False)
    created_to = serializers.DateTimeField(required=False)
    ordering = serializers.ChoiceField(
        choices=[
            "created_at",
            "-created_at",
            "paid_at",
            "-paid_at",
            "amount",
            "-amount",
        ],
        required=False,
    )

    def validate_status(self, value):
        tokens = [token.strip() for token in value.split(",") if token.strip()]
        if not tokens:
            raise serializers.ValidationError("Provide at least one status.")
        unknown = sorted(
            {token for token in tokens if token not in Payment.Status.values}
        )
        if unknown:
            raise serializers.ValidationError(
                f"Unknown status: {', '.join(unknown)}."
            )
        return tokens

    def validate(self, attrs):
        start, end = attrs.get("created_from"), attrs.get("created_to")
        if start and end and end < start:
            raise serializers.ValidationError(
                {"created_to": "created_to must be on or after created_from."}
            )
        return attrs


class PaymentHistorySerializer(serializers.ModelSerializer):
    """Slim read shape for a consumer's own payment history (5.9, D65).

    Consumer-facing: it names the booking and lot, never the payer (that is the
    caller). ``receipt_available`` is derived from the status, so the frontend
    knows whether to offer ``GET /api/payments/{id}/receipt/`` (5.8) without a
    second request. ``refunded_amount`` is annotated by the list view.
    """

    booking_reference = serializers.CharField(
        source="booking.reference", read_only=True
    )
    slot_number = serializers.CharField(
        source="booking.slot.number", read_only=True
    )
    lot_code = serializers.CharField(source="booking.slot.lot.code", read_only=True)
    lot_name = serializers.CharField(source="booking.slot.lot.name", read_only=True)
    receipt_available = serializers.SerializerMethodField()
    refunded_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )

    def get_receipt_available(self, obj):
        return obj.status == Payment.Status.SUCCEEDED

    class Meta:
        model = Payment
        fields = [
            "id",
            "booking",
            "booking_reference",
            "slot_number",
            "lot_code",
            "lot_name",
            "purpose",
            "method",
            "status",
            "amount",
            "currency",
            "refunded_amount",
            "receipt_available",
            "paid_at",
            "created_at",
        ]
        read_only_fields = fields


class TransactionSerializer(PaymentHistorySerializer):
    """Operator read shape for the transaction listing (5.9, D65).

    Everything a consumer sees, plus who paid (the consumer and the plate) and
    the lot id, so a Manager/Administrator can reconcile a transaction. Selected
    by role in the view; operator-only fields never reach a consumer response.
    """

    lot = serializers.IntegerField(source="booking.slot.lot_id", read_only=True)
    consumer = serializers.SerializerMethodField()
    consumer_email = serializers.SerializerMethodField()
    vehicle_plate = serializers.CharField(
        source="booking.vehicle_plate", read_only=True
    )

    def get_consumer(self, obj):
        return obj.booking.user_id

    def get_consumer_email(self, obj):
        user = obj.booking.user
        return user.email if user else None

    class Meta(PaymentHistorySerializer.Meta):
        fields = PaymentHistorySerializer.Meta.fields + [
            "lot",
            "consumer",
            "consumer_email",
            "vehicle_plate",
            "extension_end_time",
        ]