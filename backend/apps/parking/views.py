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
from rest_framework import generics, status
from rest_framework.permissions import SAFE_METHODS, AllowAny
from rest_framework.response import Response

from apps.accounts.models import User
from apps.accounts.permissions import IsAdmin

from .models import City, ParkingLot
from .serializers import (
    CitySerializer,
    ParkingLotSerializer,
    ParkingLotWriteSerializer,
)

def _is_admin(request):
    """True when the caller is an authenticated Administrator."""
    user = request.user
    return user.is_authenticated and user.role == User.Role.ADMIN

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