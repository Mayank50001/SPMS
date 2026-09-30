from django.urls import path

from .views import (
    CityListCreateView,
    ParkingLotDetailView,
    ParkingLotListCreateView,
)

urlpatterns = [
    path("cities/", CityListCreateView.as_view(), name="city-list"),
    path("parking-lots/", ParkingLotListCreateView.as_view(), name="parking-lot-list"),
    path(
        "parking-lots/<int:pk>/",
        ParkingLotDetailView.as_view(),
        name="parking-lot-detail",
    ),
]