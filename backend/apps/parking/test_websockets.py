"""WebSocket tests for the live occupancy board (6.5, D72).

Separate from ``tests.py``: these run under ``TransactionTestCase`` (the consumer
touches the database from async context, so test data must be committed rather
than held in a wrapping transaction) and override the channel layer to the
in-memory backend so the suite never needs Redis.
"""

from asgiref.sync import async_to_sync
from channels.layers import channel_layers, get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import re_path
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import User
from apps.accounts.ws_auth import _user_for_token
from apps.parking.consumers import OccupancyConsumer
from apps.parking.models import City, ParkingLot, ParkingSlot
from apps.parking.occupancy import board_group_name

IN_MEMORY_LAYER = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


def _occupancy_router():
    return URLRouter(
        [
            re_path(
                r"^ws/parking-lots/(?P<lot_pk>\d+)/occupancy/$",
                OccupancyConsumer.as_asgi(),
            ),
        ]
    )


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYER)
class OccupancySocketTests(TransactionTestCase):
    def setUp(self):
        # The layer is cached process-wide; drop it so the override wins.
        channel_layers.backends = {}

        city = City.objects.create(code="BLR", name="Bengaluru")
        self.manager = User.objects.create_user(
            email="mgr@example.com", password="Tr0ub4dor&3",
            full_name="Mgr", role=User.Role.MANAGER,
        )
        self.other_manager = User.objects.create_user(
            email="mgr2@example.com", password="Tr0ub4dor&3",
            full_name="Mgr2", role=User.Role.MANAGER,
        )
        self.consumer = User.objects.create_user(
            email="user@example.com", password="Tr0ub4dor&3",
            full_name="User", role=User.Role.CONSUMER,
        )
        self.lot = ParkingLot.objects.create(
            city=city, number=1, name="MG Road", address_line="1 MG Road",
            manager=self.manager,
        )
        ParkingSlot.objects.create(lot=self.lot, number="A-01")
        ParkingSlot.objects.create(lot=self.lot, number="A-02")

    def tearDown(self):
        channel_layers.backends = {}

    def _communicator(self, user, lot=None):
        communicator = WebsocketCommunicator(
            _occupancy_router(),
            f"/ws/parking-lots/{(lot or self.lot).id}/occupancy/",
        )
        communicator.scope["user"] = user
        return communicator

    def test_manager_receives_the_initial_snapshot(self):
        async def scenario():
            communicator = self._communicator(self.manager)
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            message = await communicator.receive_json_from()
            self.assertEqual(message["type"], "occupancy")
            self.assertEqual(message["board"]["lot"]["id"], self.lot.id)
            self.assertEqual(message["board"]["summary"]["total"], 2)
            await communicator.disconnect()

        async_to_sync(scenario)()

    def test_unauthenticated_connection_is_closed(self):
        async def scenario():
            communicator = self._communicator(AnonymousUser())
            connected, code = await communicator.connect()
            self.assertFalse(connected)
            self.assertEqual(code, 4401)

        async_to_sync(scenario)()

    def test_manager_of_another_lot_is_closed(self):
        async def scenario():
            communicator = self._communicator(self.other_manager)
            connected, code = await communicator.connect()
            self.assertFalse(connected)
            self.assertEqual(code, 4403)

        async_to_sync(scenario)()

    def test_a_consumer_role_is_closed(self):
        async def scenario():
            communicator = self._communicator(self.consumer)
            connected, code = await communicator.connect()
            self.assertFalse(connected)
            self.assertEqual(code, 4403)

        async_to_sync(scenario)()

    def test_a_board_change_pushes_a_fresh_snapshot(self):
        async def scenario():
            communicator = self._communicator(self.manager)
            await communicator.connect()
            await communicator.receive_json_from()  # initial snapshot
            await get_channel_layer().group_send(
                board_group_name(self.lot.id), {"type": "board.changed"}
            )
            message = await communicator.receive_json_from()
            self.assertEqual(message["type"], "occupancy")
            self.assertEqual(message["board"]["summary"]["total"], 2)
            await communicator.disconnect()

        async_to_sync(scenario)()


class JwtMiddlewareTests(TransactionTestCase):
    """D72/D15: the WebSocket handshake token resolves to a user server-side.

    ``TransactionTestCase``, not ``TestCase``: ``channels``'
    ``database_sync_to_async`` runs ``close_old_connections()`` around every call,
    and inside a ``TestCase``'s wrapping atomic block (autocommit off) that closes
    the very connection the query then needs -- "connection already closed". A
    committed, non-atomic test database avoids it, exactly as the socket tests
    above.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="mgr@example.com", password="Tr0ub4dor&3",
            full_name="Mgr", role=User.Role.MANAGER,
        )

    def test_a_valid_token_resolves_to_the_user(self):
        token = str(AccessToken.for_user(self.user))
        self.assertEqual(async_to_sync(_user_for_token)(token), self.user)

    def test_a_garbage_token_resolves_to_none(self):
        self.assertIsNone(async_to_sync(_user_for_token)("not-a-token"))

    def test_a_missing_token_resolves_to_none(self):
        self.assertIsNone(async_to_sync(_user_for_token)(None))