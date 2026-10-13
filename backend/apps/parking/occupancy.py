"""Occupancy-board broadcast plumbing (6.5, D72).

One Channels group per lot. Occupancy actions -- a manual mark in the parking
app, a check-in/check-out in bookings -- call :func:`notify_board_changed`; the
message is sent **on commit**, so a rolled-back write never announces a phantom
change. The payload is deliberately tiny: the consumer re-reads the board rather
than trusting the message.
"""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

def board_group_name(lot_id):
    """The Channels group name for one lot's occupancy board (D72)."""
    return f"occupancy.{lot_id}"

def notify_board_changed(lot_id):
    """Announce that ``lot``'s occupancy board may have changed (D72).

    Deferred to commit: writers call this inside their atomic block, and a
    rollback must not push a stale board. With no channel layer configured this
    is a no-op, so unit tests that patch it out stay simple.
    """
    layer = get_channel_layer()
    if layer is None:
        return

    def _send():
        async_to_sync(layer.group_send)(
            board_group_name(lot_id), {"type": "board.changed"}
        )

    transaction.on_commit(_send)