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

class BookingSerializer(serializers.ModelSerializer):
    """Read representation of a booking (D39).

    ``slot_number`` and ``lot_code`` are derived for display so a client can
    render "BLR-001 / A-01" without a second request. The price/plate fields are
    the stored snapshots, not live values.
    """

    slot_number = serializers.CharField(source="slot.number", read_only=True)
    lot_code = serializers.CharField(source="slot.lot.code", read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id",
            "status",
            "slot",
            "slot_number",
            "lot_code",
            "slot_type",
            "user",
            "vehicle",
            "vehicle_plate",
            "start_time",
            "end_time",
            "billed_hours",
            "hourly_rate",
            "base_amount",
            "hold_expires_at",
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