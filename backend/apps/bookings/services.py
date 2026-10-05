"""Booking rules: pricing, the conflict predicate and lazy hold expiry.

Phase 4 (increment 4.2). One module (D44) holds the rules later increments
consume, so availability (4.3) and creation (4.4) share a single definition of
"does this window conflict?" and "what does this window cost?" (D43).

Reads stay side-effect free: availability filters lapsed holds out with
``blocking_window_q`` and never persists expiry. Only the creation path calls
``expire_stale_holds``, inside its slot-locked transaction (4.4).
"""

import math
from decimal import Decimal
from typing import NamedTuple

from django.db.models import Q, Exists, OuterRef
from django.utils import timezone

from apps.parking.models import Tariff, ParkingSlot

from .models import Booking

class BookingRuleError(Exception):
	"""Base class for booking refusals.

    ``code`` is stable so the API layer can return ``{"error": CODE, ...}``
    without parsing prose (D44, PROJECT.md §33).
    """

	code = "BOOKING_RULE_VIOLATION"

class InvalidWindowError(BookingRuleError):
    """The window is not a valid reservation interval (``end <= start``)."""

    code = "INVALID_WINDOW"

class MinDurationNotMetError(BookingRuleError):
    """The window is shorter than the slot's minimum bookable duration."""

    code = "MIN_DURATION_NOT_MET"

class MaxDurationExceededError(BookingRuleError):
    """The window is longer than the slot's maximum bookable duration."""

    code = "MAX_DURATION_EXCEEDED"

class NoTariffError(BookingRuleError):
    """The slot's ``(lot, slot_type)`` has no tariff, so it cannot be priced."""

    code = "NO_TARIFF"

class BookingQuote(NamedTuple):
    """The priced result of a window, ready to snapshot onto a ``Booking``."""

    billed_hours: int
    hourly_rate: Decimal
    base_amount: Decimal
    slot_type: str


def hours_between(start, end):
	"""Whole hours between two datetimes, part-hours rounded up (§19).

    Pure arithmetic, deliberately separate from the window and duration rules so
    the billing unit can change without touching them (D42). Requires
    ``end > start``; ``validate_window`` enforces that first.
    """
	return math.ceil((end - start).total_seconds() / 3600)

def validate_window(start, end):
    """Reject a window that is empty or backwards (D41, D44)."""
    if end <= start:
        raise InvalidWindowError("end_time must be after start_time.")

def validate_duration(slot, billed_hours):
    """Enforce the slot's per-slot duration policy (D45).

    Both ends reject: below the minimum and above the maximum are refusals,
    not a billing floor.
    """
    if billed_hours < slot.min_booking_hours:
        raise MinDurationNotMetError(
            f"This slot must be booked for at least {slot.min_booking_hours} hour(s)."
        )
    if billed_hours > slot.max_booking_hours:
        raise MaxDurationExceededError(
            f"This slot may be booked for at most {slot.max_booking_hours} hour(s)."
        )

def quote_booking(*, slot, start_time, end_time):
    """Price a window for a slot (D42, D44).

    Validates the window shape and the slot's duration policy, reads the one
    tariff that applies to the slot, and returns a :class:`BookingQuote`. The
    ``base_amount`` is computed here and later snapshotted onto the booking, so
    a later tariff edit cannot change it (D39, revised for 4.2).

    Eligibility -- the lot being active, the slot being in service and the
    window being free -- is **not** checked here; that is 4.3/4.4 (D44).
    """
    validate_window(start_time, end_time)
    billed_hours = hours_between(start_time, end_time)
    validate_duration(slot, billed_hours)

    tariff = Tariff.objects.filter(
        lot_id=slot.lot_id, slot_type=slot.slot_type
    ).first()
    if tariff is None:
        raise NoTariffError(
            "No tariff is configured for this slot type in this lot."
        )

    rate = tariff.hourly_rate
    return BookingQuote(
        billed_hours=billed_hours,
        hourly_rate=rate,
        base_amount=rate * billed_hours,
        slot_type=slot.slot_type,
    )

def blocking_window_q(start, end, now):
    """A positive ``Q`` matching bookings that block ``[start, end)`` (D41).

    A booking blocks when it is CONFIRMED or IN_PROGRESS, or it is
    PENDING_PAYMENT with a hold that has not lapsed. Written as a positive
    expression (never ``~Q``) so a NULL ``hold_expires_at`` cannot fall through
    SQL three-valued logic and stop a pending booking from blocking (D43).
    """
    active = Q(
        status__in=(Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS)
    )
    live_pending = Q(status=Booking.Status.PENDING_PAYMENT) & (
        Q(hold_expires_at__gt=now) | Q(hold_expires_at__isnull=True)
    )
    overlaps = Q(start_time__lt=end, end_time__gt=start)
    return (active | live_pending) & overlaps

def is_hold_live(booking, now):
    """True while ``booking``'s PENDING_PAYMENT hold still blocks (D6/D41).

    A non-pending booking has no hold; a pending booking with no deadline is
    live, and one whose deadline has passed is not.
    """
    if booking.status != Booking.Status.PENDING_PAYMENT:
        return False
    if booking.hold_expires_at is None:
        return True
    return booking.hold_expires_at > now

def expire_stale_holds(*, slot=None, now=None):
    """Mark lapsed PENDING_PAYMENT holds EXPIRED; return how many changed (D6).

    Called only by the creation path, inside the slot-locked transaction, where
    the status must be authoritative (D43). ``updated_at`` is set explicitly
    because a queryset ``update()`` does not trigger ``auto_now``.
    """
    now = now or timezone.now()
    stale = Booking.objects.filter(
        status=Booking.Status.PENDING_PAYMENT,
        hold_expires_at__lte=now,
    )
    if slot is not None:
        stale = stale.filter(slot=slot)
    return stale.update(status=Booking.Status.EXPIRED, updated_at=now)

def available_slots(*, lot, start_time, end_time, now=None):
    """Slots in ``lot`` that can be booked for ``[start_time, end_time)`` (D46).

    Read-only: a pending hold's liveness is decided by ``blocking_window_q`` (a
    lapsed hold simply stops blocking), never by persisting expiry, so a GET has
    no side effects (D43, Invariant 6).

    A slot is returned when it is not ``OUT_OF_SERVICE`` (Invariant 5), the
    window fits its per-slot duration policy (D45), and no blocking booking
    overlaps it (D41). ``OCCUPIED`` is deliberately not excluded -- it is
    physical, time-unbounded state owned by Phase 6 (PROJECT.md §28).

    The overlap test is a correlated ``EXISTS``, so the whole lot is answered in
    one query (using ``booking_slot_window_idx``) rather than one query per slot.
    """

    validate_window(start_time, end_time)
    now = now or timezone.now()
    billed_hours = hours_between(start_time, end_time)

    blocking = Booking.objects.filter(slot=OuterRef("pk")).filter(
        blocking_window_q(start_time, end_time, now)
    )

    return  (
        ParkingSlot.objects.filter(
            lot=lot,
            min_booking_hours__lte=billed_hours,
            max_booking_hours__gte=billed_hours,
        )
        .exclude(status=ParkingSlot.Status.OUT_OF_SERVICE)
        .annotate(is_booked=Exists(blocking))
        .filter(is_booked=False)
        .select_related("lot")
    )