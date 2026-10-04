"""Parking API views (D37).

The catalogue is public to *read* (``AllowAny`` on safe methods) so a visitor can
browse lots before signing in -- a deliberate, documented opt-out of the
deny-by-default posture (D18) for read-only, non-PII data. Every write requires
an Administrator.

Only ``is_active=True`` lots are visible to anonymous visitors and Consumers. A
Manager's catalogue is scoped to their assigned lots, including deactivated ones
(D37, D38; increment 3.4).
"""

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import SAFE_METHODS, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import IsAdmin, IsAdminOrManager

from .models import City, ParkingLot, ParkingSlot, Tariff, BusinessRule

from .serializers import (
    CitySerializer,
    ParkingLotSerializer,
    ParkingLotWriteSerializer,
    ParkingSlotSerializer,
    ParkingSlotWriteSerializer,
    TariffSerializer, TariffWriteSerializer,
    BusinessRuleSerializer, BusinessRuleUpdateSerializer
)

from .services import (
    MaxRateBelowTariffError, MaxRateExceededError, save_slot, set_tariff, set_business_rules, MaxDurationBelowSlotError, SlotDurationAboveMaximumError
)

def _is_admin(request):
    """True when the caller is an authenticated Administrator."""
    user = request.user
    return user.is_authenticated and user.role == User.Role.ADMIN

def _visible_lot_catalogue(request):
    """Lots a caller sees in the catalogue *listing* (D37, 3.4 decision 1a).

    Admin -> every lot. Manager -> only the lots assigned to them, active or
    deactivated (D38). Everyone else (anonymous, Consumer) -> active lots only,
    so the public catalogue is unchanged.
    """
    queryset = ParkingLot.objects.select_related("city", "manager")
    user = request.user

    if _is_admin(request):
        return queryset
    if user.is_authenticated and user.role == User.Role.MANAGER:
        return queryset.filter(manager=user)
    return queryset.filter(is_active=True)

def _addressable_lot(request):
    """Lots a caller may fetch by id (D37, 3.4 decision 2).

    A single lot follows the same public rule as the nested slot/tariff views:
    a Manager may address an *active* lot (it is public anyway) **or** one
    assigned to them even when deactivated (D38), so nobody is ever shown less
    than an anonymous visitor can already see.
    """
    queryset = ParkingLot.objects.select_related("city", "manager")
    user = request.user

    if _is_admin(request):
        return queryset
    if user.is_authenticated and user.role == User.Role.MANAGER:
        return queryset.filter(Q(is_active=True) | Q(manager=user))
    return queryset.filter(is_active=True)

class LotScopedMixin:
    """Shared lot lookup for the nested slot views (D37, Invariant 3).

    The URL always names a lot, so "may this caller address that lot?" is
    answered once here:

    * Admin -- any lot.
    * Safe methods -- the public active catalogue; a Manager additionally sees
      their own lots even when inactive (D38), so a manager can inspect a
      deactivated assigned lot.
    * Writes -- only the lot's assigned Manager. An unassigned manager gets an
      empty queryset, i.e. a **404**, never a leak (D37/D28).

    Object-level enforcement is *scoping the queryset*, exactly as the
    permissions module documents: a role class cannot answer "is this manager
    the lot's manager?".
    """

    def _visible_lot_queryset(self):
        queryset = ParkingLot.objects.all()
        user = self.request.user

        if user.is_authenticated and user.role == User.Role.ADMIN:
            return queryset

        if self.request.method in SAFE_METHODS:
            if user.is_authenticated and user.role == User.Role.MANAGER:
                return queryset.filter(Q(is_active =True) | Q(manager=user))
            return queryset.filter(is_active=True)

        return queryset.filter(manager=user)

    def get_lot(self):
        if not hasattr(self, "_lot"):
            self._lot = get_object_or_404(
                self._visible_lot_queryset(), pk=self.kwargs["lot_pk"]
            )
        return self._lot

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["lot"] = self.get_lot()
        return context

class CityListCreateView(generics.ListCreateAPIView):
    """List cities (public) or add a city (Administrator only)."""

    queryset = City.objects.all()
    serializer_class = CitySerializer

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [AllowAny()]
        return [IsAdmin()]

class ParkingLotListCreateView(generics.ListCreateAPIView):
    """List/search lots (public) or create one (Administrator only)."""

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [AllowAny()]
        return [IsAdmin()]

    def get_queryset(self):
        queryset = _visible_lot_catalogue(self.request)

        city_code = self.request.query_params.get("city")
        if city_code:
            queryset = queryset.filter(city__code__iexact=city_code)

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(address_line__icontains=search)
            )
        return queryset

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ParkingLotWriteSerializer
        return ParkingLotSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lot = serializer.save()
        return Response(ParkingLotSerializer(lot).data, status=status.HTTP_201_CREATED)

class ParkingLotDetailView(generics.RetrieveUpdateAPIView):
    """Read one lot (public) or edit it (Administrator only). No ``DELETE``/``PUT``.

    ``PUT`` is disabled for the same reason as D25/D27: a partial payload must
    not be able to blank fields. ``DELETE`` is disabled because lifecycle is a
    flag (D38).
    """

    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [AllowAny()]
        return [IsAdmin()]

    def get_queryset(self):
        return _addressable_lot(self.request)

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return ParkingLotWriteSerializer
        return ParkingLotSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        lot = serializer.save()
        return Response(ParkingLotSerializer(lot).data)

class ParkingSlotListCreateView(LotScopedMixin, generics.ListCreateAPIView):
    """List slots of a lot (public) or add one (Admin / the lot's Manager).

    ``GET  /api/parking-lots/{lot_pk}/slots/``
    ``POST /api/parking-lots/{lot_pk}/slots/``

    Reads are public like the lot catalogue (D37); the listing returns each
    slot's stored ``status`` only -- the time-window availability query is
    Phase 4.
    """

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [AllowAny()]
        return [IsAdminOrManager()]

    def get_queryset(self):
        return ParkingSlot.objects.filter(lot=self.get_lot()).select_related("lot")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ParkingSlotWriteSerializer
        return ParkingSlotSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            slot = save_slot(serializer=serializer, lot=self.get_lot())
        except SlotDurationAboveMaximumError as exc:
            return Response(
                {"error": "MAX_DURATION_ABOVE_CAP", "max_booking_hours": [str(exc)]},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            ParkingSlotSerializer(slot).data, status=status.HTTP_201_CREATED
        )


class ParkingSlotDetailView(LotScopedMixin, generics.RetrieveUpdateAPIView):
    """Read one slot (public) or edit it (Admin / the lot's Manager).

    ``GET   /api/parking-lots/{lot_pk}/slots/{pk}/``
    ``PATCH /api/parking-lots/{lot_pk}/slots/{pk}/``

    ``PUT`` is disabled so a partial payload cannot blank fields; ``DELETE`` is
    disabled because lifecycle is a flag (D38) -- withdrawing a slot is
    ``status=OUT_OF_SERVICE``.
    """

    http_method_names = ["get", "patch", "head", "options"]
    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [AllowAny()]
        return [IsAdminOrManager()]

    def get_queryset(self):
        return ParkingSlot.objects.filter(lot=self.get_lot()).select_related("lot")

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return ParkingSlotWriteSerializer
        return ParkingSlotSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        try:
            slot = save_slot(serializer=serializer)
        except SlotDurationAboveMaximumError as exc:
            return Response(
                {"error": "MAX_DURATION_ABOVE_CAP", "max_booking_hours": [str(exc)]},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(ParkingSlotSerializer(slot).data)

class TariffListCreateView(LotScopedMixin, generics.ListCreateAPIView):
    """List a lot's tariffs (public) or add one (Admin / the lot's Manager).

    ``GET  /api/parking-lots/{lot_pk}/tariffs/``
    ``POST /api/parking-lots/{lot_pk}/tariffs/``

    Reads are public like the lot catalogue (D37/Q5): a consumer needs prices to
    choose a lot. Writes go through ``services.set_tariff`` so Invariant 4 is
    enforced on every path (D35).
    """

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [AllowAny()]
        return [IsAdminOrManager()]

    def get_queryset(self):
        return Tariff.objects.filter(lot=self.get_lot()).select_related("lot")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return TariffWriteSerializer
        return TariffSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            tariff = set_tariff(
                lot=self.get_lot(),
                slot_type = serializer.validated_data["slot_type"],
                hourly_rate=serializer.validated_data["hourly_rate"],
            )
        except MaxRateExceededError as exc:
            return Response(
                {"error" : "RATE_ABOVE_MAXIMUM", "hourly_rate": [str(exc)]},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(TariffSerializer(tariff).data, status=status.HTTP_201_CREATED)

class TariffDetailView(LotScopedMixin, generics.RetrieveUpdateAPIView):
    """Read one tariff (public) or edit it (Admin / the lot's Manager).

    ``PUT`` is disabled so a partial payload cannot blank the rate; ``DELETE``
    is disabled because a price is changed, not removed (mirrors the lifecycle
    rule, D38).
    """

    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [AllowAny()]
        return [IsAdminOrManager()]

    def get_queryset(self):
        return Tariff.objects.filter(lot=self.get_lot()).select_related("lot")

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return TariffWriteSerializer
        return TariffSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        try:
            tariff = set_tariff(
                lot=self.get_lot(),
                slot_type=serializer.validated_data.get(
                    "slot_type", instance.slot_type
                ),
                hourly_rate=serializer.validated_data.get(
                    "hourly_rate", instance.hourly_rate
                ),
                instance=instance,
            )
        except MaxRateExceededError as exc:
            return Response(
                {"error" : "RATE_ABOVE_MAXIMUM", "hourly_rate": [str(exc)]},
                status=status.HTTP_409_CONFLICT
            )
        return Response(TariffSerializer(tariff).data)

class BusinessRuleView(APIView):
    """Read or update the platform's single business-rule row (D35).

    ``GET   /api/business-rules/`` -- public (a Manager needs the cap to price
                                       within it; the value is non-PII).
    ``PATCH /api/business-rules/`` -- Administrator only. Lowering the cap below
                                       an existing tariff is a ``409`` with a
                                       stable ``error`` code (Q2), not a bare
                                       validation error.
    """

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [AllowAny()]
        return [IsAdmin()]

    def get(self, request):
        return Response(BusinessRuleSerializer(BusinessRule.load()).data)

    def patch(self, request):
        serializer = BusinessRuleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            rule = set_business_rules(
                max_hourly_rate=serializer.validated_data.get("max_hourly_rate"),
                max_booking_hours=serializer.validated_data.get("max_booking_hours"),
            )
        except MaxRateBelowTariffError as exc:
            return Response(
                {"error": "MAX_RATE_BELOW_TARIFF", "message": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        except MaxDurationBelowSlotError as exc:
            return Response(
                {"error": "MAX_DURATION_BELOW_SLOT", "message": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(BusinessRuleSerializer(rule).data)