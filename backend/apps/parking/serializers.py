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

from .models import City, ParkingLot

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
        