"""Parking API views (D37).

The catalogue is public to *read* (``AllowAny`` on safe methods) so a visitor can
browse lots before signing in -- a deliberate, documented opt-out of the
deny-by-default posture (D18) for read-only, non-PII data. Every write requires
an Administrator.

Only ``is_active=True`` lots are visible to non-Administrators. Manager-scoped
lot views land with the manager increment; today a Manager browses active lots
like a consumer.
"""

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import SAFE_METHODS, AllowAny
from rest_framework.response import Response

from apps.accounts.models import User
from apps.accounts.permissions import IsAdmin, IsAdminOrManager

from .models import City, ParkingLot, ParkingSlot
from .serializers import (
    CitySerializer,
    ParkingLotSerializer,
    ParkingLotWriteSerializer,
    ParkingSlotSerializer,
    ParkingSlotWriteSerializer
)

def _is_admin(request):
    """True when the caller is an authenticated Administrator."""
    user = request.user
    return user.is_authenticated and user.role == User.Role.ADMIN

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
        queryset = ParkingLot.objects.select_related("city", "manager")
        if not _is_admin(self.request):
            queryset = queryset.filter(is_active=True)

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
        queryset = ParkingLot.objects.select_related("city", "manager")
        if not _is_admin(self.request):
            queryset = queryset.filter(is_active=True)
        return queryset

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
        slot = serializer.save(lot=self.get_lot())
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
        slot = serializer.save()
        return Response(ParkingSlotSerializer(slot).data)