"""Parking serializers (Phase 3).

Read and write shapes are separate, following the established pattern in
``apps/accounts`` (``VehicleSerializer`` / ``VehicleWriteSerializer``): a
resource has one response shape and one request shape, and a client never sets a
derived value (``code`` is built by the model, D29).

Import-time constraint (B5): ``User = get_user_model()`` resolves the concrete
model as this module is imported, so this module must only be imported once
Django's app registry is ready -- by ``views.py``/``urls.py`` after startup,
never from ``models.py`` or ``apps.py``.
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import City, ParkingLot, ParkingSlot, BusinessRule, Tariff

User = get_user_model()

class CitySerializer(serializers.ModelSerializer):
    """Read/write shape for a city (D29-S1).

    ``code`` is canonicalised to upper case by the model's ``save()``; the
    serializer validates the shape and pre-checks uniqueness case-insensitively
    so a clash is a clean ``400`` rather than a ``500``.
    """

    code = serializers.RegexField(
        r"^[A-Za-z]{2,4}$",
        error_messages={"invalid": "Enter a 2-4 letter city code (e.g. BLR)."},
    )

    class Meta:
        model = City
        fields = ["id","code", "name", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_code(self, value):
        code = value.upper()
        queryset = City.objects.filter(code=code)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("A city with this code already exists.")
        return code

class ParkingLotSerializer(serializers.ModelSerializer):
    """Read representation of a lot: the derived code plus its city object."""

    city = CitySerializer(read_only=True)
    class Meta:
        model = ParkingLot
        fields = [
            "id",
            "code",
            "name",
            "address_line",
            "city",
            "number",
            "state",
            "postal_code",
            "is_active",
            "manager",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

class ParkingLotWriteSerializer(serializers.ModelSerializer):
    """Create/update a lot from a city code and a number (D29, D29-S2).

    The client sends ``city_code`` and ``number``; the backend resolves the city
    and the model derives ``code`` (``BLR-007``). ``city_code`` is not a model
    field -- it is declared here and resolved in ``validate()``.

    ``manager`` is restricted to accounts with ``role=MANAGER`` by the field's
    queryset, so assigning a Consumer or Administrator is a ``400`` (D36).
    """

    city_code = serializers.CharField(
        max_length=4,
        required=False,
        error_messages={"required": "This field is required."},
    )

    manager = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=User.Role.MANAGER),
        required=False,
        allow_null=True,
        error_messages={"does_not_exist": "No parking manager with this id exists."},
    )

    class Meta:
        model = ParkingLot
        fields = [
            "id",
            "code",
            "city_code",
            "number",
            "name",
            "address_line",
            "state",
            "postal_code",
            "is_active",
            "manager",
        ]
        read_only_fields = ["id", "code"]

    def validate(self, attrs):
        city_code = attrs.pop("city_code", None)
        if city_code is not None:
            try:
                attrs["city"] = City.objects.get(code__iexact=city_code)
            except City.DoesNotExist:
                raise serializers.ValidationError({"city_code" : "Unknown city code."})
        elif self.instance is None:
            raise serializers.ValidationError({"city_code" : "This field is required."})

        city = attrs.get("city") or (self.instance.city if self.instance else None)
        number = attrs.get("number", self.instance.number if self.instance else None)

        # Pre-check the (city, number) pair so a duplicate is a clean 400. The
        # DB UniqueConstraint remains the real guard against a concurrent insert.
        if city is not None and number is not None:
            duplicates = ParkingLot.objects.filter(city=city, number=number)
            if self.instance is not None:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise serializers.ValidationError(
                    {"number": "This number is already used for the selected city."}
                )

        return attrs

class ParkingSlotSerializer(serializers.ModelSerializer):
    """Read representation of a slot (D31, D32, D33).

    ``lot`` is the owning lot's id; ``lot_code`` is derived for display so a
    client does not have to join to render "BLR-001 / A-01".
    """

    lot_code = serializers.CharField(source="lot.code", read_only=True)

    class Meta:
        model = ParkingSlot
        fields = [
            "id",
            "lot",
            "lot_code",
            "number",
            "floor",
            "slot_type",
            "status",
            "min_booking_hours",
            "max_booking_hours",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

class ParkingSlotWriteSerializer(serializers.ModelSerializer):
    """Create/update a slot from the body, with the lot taken from the URL.

    ``lot`` is deliberately not a field: it comes from the nested route and is
    passed to ``save(lot=...)`` by the view, so a client cannot create a slot in
    a lot it never addressed (Invariant 3).

    ``status`` is restricted to the two states a Phase 3 caller may set (3.2
    decision 7, D38). ``OCCUPIED`` is written by Phase 6 occupancy actions, not
    here, so sending it is a clean 400 (PROJECT.md §28 boundary).
    """

    SUPERVISED_STATUSES = [
        (ParkingSlot.Status.AVAILABLE.value, ParkingSlot.Status.AVAILABLE.label),
        (
            ParkingSlot.Status.OUT_OF_SERVICE.value, ParkingSlot.Status.OUT_OF_SERVICE.label
        ),
    ]

    status = serializers.ChoiceField(choices=SUPERVISED_STATUSES, required=False)
    min_booking_hours = serializers.IntegerField(required=False, min_value=1)
    max_booking_hours = serializers.IntegerField(required=False, min_value=1)


    class Meta:
        model = ParkingSlot
        fields = ["id", "number", "floor", "slot_type", "status", "min_booking_hours", "max_booking_hours",]
        read_only_fields = ["id"]

    def validate_number(self, value):
        # Canonicalise here as well as in the model so the duplicate pre-check
        # below compares the same form the DB will store (3.2 decision 6).
        value = value.strip().upper()
        if not value:
            raise serializers.ValidationError("Slot number cannot be blank.")
        return value

    def validate(self, attrs):
        lot = self.context.get("lot")
        number = attrs.get("number")
        if number is None and self.instance is not None:
            number = self.instance.number

        # Pre-check (lot, number) so a duplicate is a clean 400; the DB
        # UniqueConstraint stays the guard against a concurrent insert.
        if lot is not None and number:
            duplicates = ParkingSlot.objects.filter(lot=lot, number=number)
            if self.instance is not None:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise serializers.ValidationError(
                    {"number": "This slot number is already used in this lot."}
                )

        # D34 (3.3): a slot of a type with no tariff in this lot could never be
        # booked, so it is rejected here. The check runs only when the type is
        # actually being set -- on create, or when PATCH explicitly changes
        # ``slot_type`` -- so an existing slot can still have its number, floor
        # or status edited.
        if lot is not None and (self.instance is None or "slot_type" in attrs):
            slot_type = attrs.get("slot_type") or (
                self.instance.slot_type if self.instance is not None else ParkingSlot.SlotType.REGULAR
            )
            if not Tariff.objects.filter(lot=lot, slot_type=slot_type).exists():
                raise serializers.ValidationError(
                    {
                        "slot_type" : (
                            "No tariff is configured for this slot type in this lot."
                        )
                    }
                )

        # D45: min <= max. A clean 400 here; the DB CheckConstraint is the
        # backstop. The ceiling against the Administrator's cap is enforced in
        # ``services.save_slot`` (409), not here.
        min_hours = attrs.get("min_booking_hours", self.instance.min_booking_hours 
            if self.instance is not None 
            else ParkingSlot.DEFAULT_MIN_BOOKING_HOURS)
        max_hours = attrs.get("max_booking_hours", self.instance.max_booking_hours if self.instance is not None else ParkingSlot.DEFAULT_MAX_BOOKING_HOURS)
        if min_hours > max_hours:
            raise serializers.ValidationError(
                {"max_booking_hours": "The maximum must not be below the minimum."}
            )
        return attrs

class TariffSerializer(serializers.ModelSerializer):
    """Read representation of a tariff (D34)."""

    lot_code = serializers.CharField(source="lot.code", read_only=True)
    slot_type_label = serializers.CharField(
        source="get_slot_type_display", read_only=True
    )

    class Meta:
        model = Tariff
        fields = [
            "id",
            "lot",
            "lot_code",
            "slot_type",
            "slot_type_label",
            "hourly_rate",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

class TariffWriteSerializer(serializers.ModelSerializer):
    """Create/update a tariff; the lot comes from the nested URL (Invariant 3).

    ``lot`` is deliberately not a field: it is taken from the route and passed
    to the service by the view, so a client cannot price a lot it never
    addressed. The Invariant 4 cap check is *not* here -- it lives in
    ``services.set_tariff`` so no caller can bypass it (D35).
    """
    class Meta:
        model = Tariff
        fields = ["id", "slot_type", "hourly_rate"]
        read_only_fields = ["id"]

    def validate_hourly_rate(self , value):
        # Q4: strictly positive. The model validator says the same; repeating it
        # here yields a field-shaped 400 instead of a 500 from the DB check.
        if value <= 0:
            raise serializers.ValidationError("Hourly rate must be greater than zero.")
        return value

    def validate(self, attrs):
        lot = self.context.get("lot")
        slot_type = attrs.get(
            "slot_type", self.instance.slot_type if self.instance is not None else None,
        )

        if lot is not None and slot_type:
            duplicates = Tariff.objects.filter(lot=lot, slot_type=slot_type)
            if self.instance is not None:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise serializers.ValidationError(
                    {
                        "slot_type": (
                            "A tariff for this slot type already exists in this lot."
                        )
                    }
                )
        return attrs

class BusinessRuleSerializer(serializers.ModelSerializer):
    """Read representation of the business-rule singleton (D35)."""

    class Meta:
        model = BusinessRule
        fields = ["id", "max_hourly_rate","max_booking_hours", "hold_minutes", "updated_at"]
        read_only_fields = fields

class BusinessRuleUpdateSerializer(serializers.ModelSerializer):
    """Write shape for the singleton: either ceiling may be edited.

    The "cannot lower below an existing row" guards are not here; they live in
    ``services.set_business_rules`` (D35, D45).
    """

    max_booking_hours = serializers.IntegerField(required=False, min_value=1)
    hold_minutes = serializers.IntegerField(required=False, min_value=1)
    class Meta:
        model = BusinessRule
        fields = ["max_hourly_rate", "max_booking_hours", "hold_minutes"]

    def validate_max_hourly_rate(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "The maximum hourly rate must be greater than zero."
            )
        return value

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide at least one field to update.")
        return attrs


class AvailabilityQuerySerializer(serializers.Serializer):
    """Validates the ``?start=&end=`` window of the availability read (D46).

    Both instants are required. DRF parses offset-aware ISO-8601 and normalises
    to the current timezone (UTC, D5), so the service and the database always
    compare aware UTC values; a malformed value is a field-shaped ``400``.
    """

    start = serializers.DateTimeField()
    end = serializers.DateTimeField()

