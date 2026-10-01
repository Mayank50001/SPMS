from django.urls import path

from .views import (
    CityListCreateView,
    ParkingLotDetailView,
    ParkingLotListCreateView,
    ParkingSlotDetailView,
    ParkingSlotListCreateView,
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
]