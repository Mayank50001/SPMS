"""WebSocket routes for the parking domain (6.5, D72)."""

from django.urls import re_path

from apps.parking.consumers import OccupancyConsumer

websocket_urlpatterns = [
    re_path(
        r"^ws/parking-lots/(?P<lot_pk>\d+)/occupancy/$",
        OccupancyConsumer.as_asgi(),
    ),
]