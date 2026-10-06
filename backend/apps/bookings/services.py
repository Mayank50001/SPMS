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
from datetime import timedelta

from django.db import transaction
from django.db.models import Q, Exists, OuterRef
from django.utils import timezone

from apps.parking.models import Tariff, ParkingSlot, BusinessRule

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

class SlotNotFoundError(BookingRuleError):
    """No slot with the requested id exists."""

    code = "SLOT_NOT_FOUND"


class LotNotBookableError(BookingRuleError):
    """The slot's lot is inactive and cannot be booked (D38)."""

    code = "LOT_NOT_BOOKABLE"


class SlotUnavailableError(BookingRuleError):
    """The slot is out of service (Invariant 5)."""

    code = "SLOT_UNAVAILABLE"


class WindowInPastError(BookingRuleError):
    """The requested window is already over (§35, booking in the past)."""

    code = "WINDOW_IN_PAST"


class BookingConflictError(BookingRuleError):
    """Another live booking blocks this window (Invariant 1, D41)."""

    code = "BOOKING_CONFLICT"

class BookingNotFoundError(BookingRuleError):
    """No booking with the requested id exists."""

    code = "BOOKING_NOT_FOUND"

class BookingNotConfirmableError(BookingRuleError):
    """The booking is not a live pending one, so it cannot be confirmed (D51).

    A lapsed hold reaches this too: confirmation sweeps stale holds first, so an
    over-due ``PENDING_PAYMENT`` has already become ``EXPIRED`` -- the same
    answer as a cancelled or terminated booking: this one cannot be confirmed.
    """

    code = "BOOKING_NOT_CONFIRMABLE"

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

def effective_status(booking, now=None):
    """The status a reader should see, reporting a lapsed hold as EXPIRED (4.5).

    Expiry is lazy (D6): the stored ``status`` stays ``PENDING_PAYMENT`` and this
    function computes the *effective* state at read time, so a client never
    renders a dead hold as live. Reads never persist it (D43) -- ``expire_stale_holds``
    remains the only writer, called inside creation's slot lock. A pending
    booking with no deadline is live and never expires, matching
    :func:`is_hold_live`; every non-pending status is returned unchanged.
    """
    now = now or timezone.now()
    if booking.status == Booking.Status.PENDING_PAYMENT and not is_hold_live(booking, now):
        return Booking.Status.EXPIRED
    return booking.status

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

@transaction.atomic
def create_booking(*, slot_id, start_time, end_time, user, vehicle):
    """Create a PENDING_PAYMENT booking atomically, or refuse (D3/D41).

    The ordering is the whole point: the slot row is locked FIRST and the
    conflict re-check runs while that lock is held. A check-then-act sequence --
    even inside ``transaction.atomic`` -- would let two concurrent creates both
    observe "no conflict" under READ COMMITTED and both insert, breaking
    Invariant 1. See D41, PROJECT.md §21.

    ``available_slots`` (4.3) is deliberately NOT used for correctness here: it
    is an unlocked read and would be stale by insert time. It remains a UI hint.
    """

    now = timezone.now()
    validate_window(start_time, end_time)
    if end_time <= now:
        raise WindowInPastError("The booking window must end in the future.")

    # Lock ONLY the slot row. select_related("lot") is a read convenience for
    # the active-lot check; ``of=("self",)`` keeps FOR UPDATE off the joined lot
    # row so bookings in the same lot but different slots do not queue.

    slot = (
        ParkingSlot.objects.select_for_update(of=("self",)).select_related("lot").filter(pk=slot_id).first()
    )

    if slot is None:
        raise SlotNotFoundError("No parking slot with this id exists.")
    if not slot.lot.is_active:
        raise LotNotBookableError("This parking lot is not accepting bookings.")
    if slot.status == ParkingSlot.Status.OUT_OF_SERVICE:
        raise SlotUnavailableError("This slot is out of service.")

    # Price + duration policy (4.2). May raise INVALID_WINDOW,
    # MIN_DURATION_NOT_MET, MAX_DURATION_EXCEEDED or NO_TARIFF.
    quote = quote_booking(slot=slot, start_time=start_time, end_time=end_time)

    # D43: the create path is the only writer of lazy expiry. Called inside the
    # lock, so the conflict check below sees authoritative state.
    expire_stale_holds(slot=slot, now=now)

    conflict = Booking.objects.filter(slot=slot).filter(blocking_window_q(start_time, end_time, now)).exists()
    if conflict:
        raise BookingConflictError(
            "This slot is no longer available for the selected window."
        )

    hold_minutes = BusinessRule.load().hold_minutes

    return Booking.objects.create(
        user=user,
        created_by=user,
        vehicle=vehicle,
        # ``vehicle_plate`` is blank here on purpose: Booking.save() copies the
        # registered plate from the vehicle FK (D39/V6), so the snapshot cannot
        # be spoofed from the request. Walk-ins (later) pass free text instead.
        vehicle_plate="",
        slot=slot,
        slot_type=quote.slot_type,
        start_time=start_time,
        end_time=end_time,
        billed_hours=quote.billed_hours,
        hourly_rate=quote.hourly_rate,
        base_amount=quote.base_amount,
        status=Booking.Status.PENDING_PAYMENT,
        hold_expires_at=now + timedelta(minutes=hold_minutes),
    )

@transaction.atomic
def confirm_booking(*, booking_id, now=None):
    """Move a live ``PENDING_PAYMENT`` booking to ``CONFIRMED`` (4.6, D51).

    This is the **confirmation seam**: Phase 5's payment gateway calls it when a
    payment succeeds. Phase 4 does not process a payment -- it only performs the
    state transition -- and it only confirms a booking whose hold is still live,
    so a late callback cannot resurrect a slot that has since been freed.

    The ordering mirrors :func:`create_booking` and is the point of the function:

    * the **slot** row is locked first (not the booking row), so confirmation is
      serialized with creation and with other confirmations for the same slot;
    * the lazy expiry sweep runs inside the lock (D43), so the decision uses
      authoritative state: a lapsed hold is treated as ``EXPIRED`` and refused.
      The attempt is atomic, so a refusal rolls the sweep back and leaves the
      row untouched -- harmless, because a lapsed hold no longer blocks (D41)
      and reads already report it as ``EXPIRED`` (D50);
    * the window is re-checked for *other* blocking bookings before committing,
      so Invariant 1 holds even in the narrow race after a hold lapses.

    A repeat confirmation of an already-``CONFIRMED`` booking returns it
    unchanged (payment gateways retry callbacks). Any other state is refused
    with ``BOOKING_NOT_CONFIRMABLE``.
    """

    now = now or timezone.now()

    # A booking's slot never changes, so this unlocked read only finds the row to
    # lock; the authoritative status is re-read after the lock is held.
    slot_id = (
        Booking.objects.filter(pk=booking_id)
        .values_list("slot_id", flat=True)
        .first()
    )
    if slot_id is None:
        raise BookingNotFoundError("No booking with this id exists.")

    # D39 makes ``Booking.slot`` PROTECT, so the locked slot always exists.
    slot = (
        ParkingSlot.objects.select_for_update(of=("self",))
        .filter(pk=slot_id)
        .first()
    )

    # D43: the same single sweep creation uses. It runs inside the lock, so the
    # state re-read below is authoritative.
    expire_stale_holds(slot=slot, now=now)
    booking = Booking.objects.get(pk=booking_id)

    if booking.status == Booking.Status.CONFIRMED:
        return booking
    if booking.status != Booking.Status.PENDING_PAYMENT:
        raise BookingNotConfirmableError(
            f"A {booking.status} booking cannot be confirmed."
        )

    conflict = (
        Booking.objects.filter(slot=slot)
        .exclude(pk=booking.pk)
        .filter(blocking_window_q(booking.start_time, booking.end_time, now))
        .exists()
    )
    if conflict:
        raise BookingConflictError(
            "This booking's slot has since been taken by another booking."
        )

    # The hold exists only to protect a pending booking; confirmation retires it.
    booking.status = Booking.Status.CONFIRMED
    booking.hold_expires_at = None
    booking.updated_at = now
    booking.save(update_fields=["status", "hold_expires_at", "updated_at"])
    return booking
