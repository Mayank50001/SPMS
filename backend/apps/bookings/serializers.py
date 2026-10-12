"""Booking read/write shapes (increment 4.4).

Read and write shapes are separate, as in ``apps.accounts`` and
``apps.parking``: one response shape, one request shape, and the client never
sets a server-computed value. The price, status and hold are produced by
``services.create_booking`` (PROJECT.md §45/§46), never accepted from the body.
"""


from rest_framework import serializers

from apps.accounts.models import Vehicle
from apps.parking.models import ParkingSlot

from .models import Booking
from .services import (
    CANCELLABLE_STATUSES,
    CHECKINABLE_STATUSES,
    CHECKOUTABLE_STATUSES,
    EXTENDABLE_STATUSES,
    effective_status as compute_effective_status
)

class BookingSerializer(serializers.ModelSerializer):
    """Read representation of a booking (D39).

    ``slot_number`` and ``lot_code`` are derived for display so a client can
    render "BLR-001 / A-01" without a second request. The price/plate fields are
    the stored snapshots, not live values.

    ``effective_status`` (increment 4.5, D50) reports a lapsed ``PENDING_PAYMENT``
    hold as ``EXPIRED`` without changing the stored ``status`` -- expiry is lazy
    (D6) and reads do not write (D43). Clients should render ``effective_status``;
    the raw ``status`` and ``hold_expires_at`` remain for transparency.
    """

    slot_number = serializers.CharField(source="slot.number", read_only=True)
    lot_code = serializers.CharField(source="slot.lot.code", read_only=True)
    lot_name = serializers.CharField(source="slot.lot.name", read_only=True)
    effective_status = serializers.SerializerMethodField()

    def get_effective_status(self, obj):
        return compute_effective_status(obj)

    class Meta:
        model = Booking
        fields = [
            "id",
            "reference",
            "status",
            "effective_status",
            "slot",
            "slot_number",
            "lot_code",
            "lot_name",
            "slot_type",
            "user",
            "vehicle",
            "vehicle_plate",
            "start_time",
            "end_time",
            "billed_hours",
            "hourly_rate",
            "base_amount",
            "refund_due_amount",
            "hold_expires_at",
            "cancelled_at",
            "actual_entry_at",
            "actual_exit_at",
            "overstay_hours",
            "overstay_amount",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

class BookingCreateSerializer(serializers.Serializer):
    """Write shape for ``POST /api/bookings/`` (4.4).

    A plain ``Serializer``, not a ``ModelSerializer``: the status, hold and
    price are computed by the service. This validates shape and vehicle
    ownership only; the window's business rules (past window, conflict,
    duration, out-of-service) are enforced in the service under the slot lock.
    """

    slot = serializers.PrimaryKeyRelatedField(
        queryset=ParkingSlot.objects.all(),
        error_messages={"does_not_exist": "No parking slot with this id exists."},
    )
    # Required: a consumer booking's authoritative plate comes from a registered
    # vehicle (D39/V6). Walk-in free-text plates arrive with their own flow.
    vehicle = serializers.PrimaryKeyRelatedField(
        queryset=Vehicle.objects.all(),
        error_messages={"does_not_exist": "No vehicle with this id exists."},
    )
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()

    def validate_vehicle(self, vehicle):
        # Invariant 2: a consumer may only book with a vehicle they own. The
        # object is resolved from a global queryset above, so ownership must be
        # checked here rather than by scoping the queryset.
        request = self.context["request"]
        if vehicle.owner_id != request.user.id:
            raise serializers.ValidationError(
                "You can only create a booking with one of your own vehicles."
            )
        return vehicle

    def validate(self, attrs):
        # Cheap shape check so ``end <= start`` is a clean 400 at the door. The
        # service re-validates under the lock via ``validate_window`` (D41).
        if attrs["end_time"] <= attrs["start_time"]:
            raise serializers.ValidationError(
                {"end_time": "end_time must be after start_time."}
            )
        return attrs

class ExtensionQuoteQuerySerializer(serializers.Serializer):
    """Validates the ``?end_time=`` of the extension quote read (D54).

    DRF parses offset-aware ISO-8601 and normalises to UTC (D5), so the service
    always compares aware values; a malformed value is a field-shaped ``400``.
    """

    end_time = serializers.DateTimeField()

class ExtensionQuoteSerializer(serializers.Serializer):
    """Read shape for the extension quote (D54): the cost before Phase 5 charges."""

    added_hours = serializers.IntegerField()
    extension_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    new_billed_hours = serializers.IntegerField()
    new_base_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    hourly_rate = serializers.DecimalField(max_digits=8, decimal_places=2)
    new_end_time = serializers.DateTimeField()

class BookingHistoryQuerySerializer(serializers.Serializer):
    """Validates the history filters of ``GET /api/bookings/`` (increment 4.9).

    Every filter is optional; omitting all of them returns the caller's whole
    history (newest first). ``status`` accepts one or more comma-separated stored
    states; an unknown token is a field-shaped 400. ``scope`` is a stored-time
    window, independent of state, so a client can combine the two (e.g. upcoming
    confirmed bookings). ``lot`` and ``ordering`` are self-explanatory.
    """

    status = serializers.CharField(required=False)
    scope = serializers.ChoiceField(
        choices=["upcoming", "ongoing", "past"], required=False
    )
    lot = serializers.IntegerField(required=False, min_value=1)
    ordering = serializers.ChoiceField(
        choices=[
            "start_time",
            "-start_time",
            "end_time",
            "-end_time",
            "created_at",
            "-created_at",
        ],
        required=False,
    )

    def validate_status(self, value):
        tokens = [token.strip() for token in value.split(",") if token.strip()]
        if not tokens:
            raise serializers.ValidationError("Provide at least one status.")
        unknown = sorted(
            {token for token in tokens if token not in Booking.Status.values}
        )
        if unknown:
            raise serializers.ValidationError(
                f"Unknown status: {', '.join(unknown)}."
            )
        return tokens

class BookingDetailSerializer(BookingSerializer):
    """Rich read shape for ``GET /api/bookings/{id}/`` (increment 4.9).

    Everything the history list returns, plus the lot/slot location details a
    "Booking Details" page needs and the ``can_cancel`` / ``can_extend`` action
    hints. The hints mirror the write endpoints' state checks exactly (the write
    endpoint stays authoritative). Payment details arrive with Phase 5, so none
    are referenced here.
    """

    lot = serializers.IntegerField(source="slot.lot_id", read_only=True)
    lot_address_line = serializers.CharField(
        source="slot.lot.address_line", read_only=True
    )
    lot_city = serializers.CharField(source="slot.lot.city.name", read_only=True)
    lot_state = serializers.CharField(source="slot.lot.state", read_only=True)
    lot_postal_code = serializers.CharField(
        source="slot.lot.postal_code", read_only=True
    )
    slot_floor = serializers.CharField(source="slot.floor", read_only=True)
    can_cancel = serializers.SerializerMethodField()
    can_extend = serializers.SerializerMethodField()

    def get_can_cancel(self, obj):
        # Mirrors ``services.cancel_booking``: a live hold or a paid booking.
        return obj.status in CANCELLABLE_STATUSES

    def get_can_extend(self, obj):
        # Mirrors ``services.EXTENDABLE_STATUSES``.
        return obj.status in EXTENDABLE_STATUSES

    class Meta(BookingSerializer.Meta):
        fields = BookingSerializer.Meta.fields + [
            "lot",
            "lot_address_line",
            "lot_city",
            "lot_state",
            "lot_postal_code",
            "slot_floor",
            "can_cancel",
            "can_extend",
        ]


class BookingOperatorSerializer(BookingSerializer):
    """Operator read shape for the booking listing (increment 6.1, D67).

    Everything a consumer sees, plus who booked (the payer's email and name) and
    the lot id, so a Manager/Administrator can reconcile a booking against a lot.
    Selected by role in the view, so these operator-only fields never reach a
    consumer response. Read-only in 6.1: operator *actions* on a booking arrive
    with increments 6.2-6.4.
    """

    lot = serializers.IntegerField(source="slot.lot_id", read_only=True)
    consumer_email = serializers.SerializerMethodField()
    consumer_name = serializers.SerializerMethodField()
    can_check_in = serializers.SerializerMethodField()
    can_check_out = serializers.SerializerMethodField()

    def get_consumer_email(self, obj):
        return obj.user.email if obj.user else None

    def get_consumer_name(self, obj):
        return obj.user.full_name if obj.user else None

    def get_can_check_in(self, obj):
        return obj.status in CHECKINABLE_STATUSES

    def get_can_check_out(self, obj):
        return obj.status in CHECKOUTABLE_STATUSES

    class Meta(BookingSerializer.Meta):
        fields = BookingSerializer.Meta.fields + [
            "lot",
            "consumer_email",
            "consumer_name",
            "can_check_in",
            "can_check_out",
        ]
