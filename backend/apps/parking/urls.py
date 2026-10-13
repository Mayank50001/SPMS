from django.urls import path

from .views import (
    CityListCreateView,
    ParkingLotDetailView,
    ParkingLotListCreateView,
    ParkingSlotDetailView,
    ParkingSlotListCreateView,
    ParkingLotAvailabilityView,
    ParkingLotOccupancyView,
    TariffListCreateView,
    TariffDetailView,
    SlotOccupancyView,
    BusinessRuleView,
)

urlpatterns = [
    path("cities/", CityListCreateView.as_view(), name="city-list"),
    path("parking-lots/", ParkingLotListCreateView.as_view(), name="parking-lot-list"),
    path(
        "parking-lots/<int:pk>/",
        ParkingLotDetailView.as_view(),
        name="parking-lot-detail",
    ),
    path("parking-lots/<int:lot_pk>/slots/", ParkingSlotListCreateView.as_view(), name="parking-slot-list"),
    path("parking-lots/<int:lot_pk>/slots/<int:pk>/", ParkingSlotDetailView.as_view(), name="parking-slot-detail"),
    path("parking-lots/<int:lot_pk>/availability/", ParkingLotAvailabilityView.as_view(), name="parking-lot-availability"),
    path("parking-lots/<int:lot_pk>/tariffs/", TariffListCreateView.as_view(), name="tariff-list",),
    path("parking-lots/<int:lot_pk>/tariffs/<int:pk>/", TariffDetailView.as_view(),name="tariff-detail"),
    path("business-rules/", BusinessRuleView.as_view(), name="business-rule",),
    path(
        "parking-lots/<int:lot_pk>/slots/<int:pk>/occupancy/",
        SlotOccupancyView.as_view(),
        name="parking-slot-occupancy",
    ),
    path(
        "parking-lots/<int:lot_pk>/occupancy/",
        ParkingLotOccupancyView.as_view(),
        name="parking-lot-occupancy",
    ),
]