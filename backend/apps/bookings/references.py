"""Public booking reference codes (Phase 4, increment 4.6, D52).

A ``reference`` is the unguessable bearer key a receipt or QR code carries, so a
walk-in with no account -- or a gate scanner -- can look a booking up without
logging in. It is deliberately **random**: it encodes no lot, date or sequence,
so the population cannot be enumerated even though the codes are short enough to
print and read. The alphabet omits characters that are easy to confuse when read
aloud or OCR'd (``I``, ``O``, ``0``, ``1``).

The value is generated on save via the model field's ``default`` (see
:class:`apps.bookings.models.Booking`); the database's unique index is the
backstop against the astronomically unlikely collision.
"""

import secrets

#: Length of a generated code. 10 characters over a 32-character alphabet is
#: ~2**50 possibilities -- far beyond guessing, still short enough for a ticket.
REFERENCE_LENGTH = 10

#: Crockford-ish alphabet: A-Z minus I/O, plus 2-9 (no ambiguous 0/1).
REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_reference():
    """Return a fresh, random public reference code (D52)."""
    return "".join(
        secrets.choice(REFERENCE_ALPHABET) for _ in range(REFERENCE_LENGTH)
    )
