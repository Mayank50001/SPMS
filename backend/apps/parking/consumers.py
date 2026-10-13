"""WebSocket consumers (D72).

6.5a ships a tiny ping consumer only to prove the ASGI + Redis channel layer is
wired; the real occupancy consumer replaces the route in 6.5b.
"""

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.accounts.models import User
from apps.bookings.services import build_occupancy_board
from apps.parking.models import ParkingLot
from apps.parking.occupancy import board_group_name

#: Policy close codes (application range 4000-4999).
WS_UNAUTHENTICATED = 4401
WS_FORBIDDEN = 4403

class OccupancyConsumer(AsyncJsonWebsocketConsumer):
    """Pushes one lot's occupancy board over a WebSocket (6.5, D72).

    The connection is authorised **server-side on connect** -- role and lot
    scoping (Invariant 3), never trusted from the client. It joins the lot's
    group and immediately receives the same snapshot
    ``GET /api/parking-lots/{lot}/occupancy/`` returns. Any board change in the
    lot (a manual mark, a check-in, a check-out) broadcasts to the group and
    every consumer re-reads and pushes. The socket is read-only.
    """

    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close(code=WS_UNAUTHENTICATED)
            return

        self.lot_id = self.scope["url_route"]["kwargs"]["lot_pk"]
        self.group_name = board_group_name(self.lot_id)

        snapshot = await self._snapshot(user)
        if snapshot is None:
            # Unknown lot, or a manager not assigned to it: no leak.
            await self.close(code=WS_FORBIDDEN)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({"type": "occupancy", "board": snapshot})

    async def disconnect(self, code):
        if getattr(self, "group_name", None):
            await self.channel_layer.group_discard(
                self.group_name, self.channel_name
            )

    async def receive_json(self, content, **kwargs):
        # Read-only board: a client has nothing to send.
        return

    async def board_changed(self, event):
        snapshot = await self._snapshot(self.scope["user"])
        if snapshot is not None:
            await self.send_json({"type": "occupancy", "board": snapshot})

    @database_sync_to_async
    def _snapshot(self, user):
        queryset = ParkingLot.objects.filter(pk=self.lot_id)
        if user.role == User.Role.MANAGER:
            queryset = queryset.filter(manager=user)
        elif user.role != User.Role.ADMIN:
            return None
        lot = queryset.first()
        return None if lot is None else build_occupancy_board(lot)