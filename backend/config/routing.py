"""WebSocket routes (D72).

Aggregates the app-level WebSocket patterns. The occupancy board is the only
WebSocket in the project today.
"""

from apps.parking.routing import websocket_urlpatterns as parking_websockets

websocket_urlpatterns = [
    *parking_websockets,
]