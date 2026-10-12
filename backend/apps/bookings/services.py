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
from datetime import timedelta, datetime

from django.db import transaction
from django.db.models import Q, Exists, OuterRef
from django.utils import timezone

from apps.parking.models import Tariff, ParkingSlot, BusinessRule
from apps.parking.services import set_slot_occupancy

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

class BookingNotCancellableError(BookingRuleError):
    """The booking is past the point where a consumer may cancel it (D53).

    A consumer may cancel only a ``PENDING_PAYMENT`` or ``CONFIRMED`` booking
    (PROJECT.md §17). A booking that has started, been completed, expired or
    terminated is not cancellable here -- manager/admin removal is the separate
    ``TERMINATED`` transition, owned by a later phase.
    """

    code = "BOOKING_NOT_CANCELLABLE"

class BookingNotExtendableError(BookingRuleError):
    """The booking is not in a state a consumer may extend (D54).

    Only the two "paid, not finished" states -- ``CONFIRMED`` and
    ``IN_PROGRESS`` -- can be extended. A ``PENDING_PAYMENT`` must be paid (or
    cancelled and rebooked) first; ``COMPLETED``/``CANCELLED``/``EXPIRED``/
    ``TERMINATED`` are past the point of extension.
    """

    code = "BOOKING_NOT_EXTENDABLE"

class BookingNotCheckinableError(BookingRuleError):
    """The booking is not a CONFIRMED one, so it cannot be checked in (D69)."""

    code = "BOOKING_NOT_CHECKINABLE"

class BookingNotCheckoutableError(BookingRuleError):
    """The booking is not IN_PROGRESS, so it cannot be checked out (D69)."""

    code = "BOOKING_NOT_CHECKOUTABLE"

    

class InvalidExtensionError(BookingRuleError):
    """The requested end time does not lengthen the booking (D54)."""

    code = "INVALID_EXTENSION"

class ExtensionQuote(NamedTuple):
    """The priced result of extending a booking to a later end time (D54)."""

    added_hours: int
    extension_amount: Decimal
    new_billed_hours: int
    new_base_amount: Decimal
    hourly_rate: Decimal
    new_end_time: datetime

#: The states a consumer may extend: the paid, not-yet-finished pair (D54).
EXTENDABLE_STATUSES = (Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS)

#: The states a consumer may cancel: a live hold or a paid booking (D53). Shared
#: with the history read's ``can_cancel`` hint so the two cannot drift (4.9).
CANCELLABLE_STATUSES = (Booking.Status.PENDING_PAYMENT, Booking.Status.CONFIRMED)

#: The states a manager may check in: a paid, not-yet-entered booking (D69).
CHECKINABLE_STATUSES = (Booking.Status.CONFIRMED,)

#: The states a manager may check out (D69).
CHECKOUTABLE_STATUSES = (Booking.Status.IN_PROGRESS,)

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
    overlaps it (D41). An ``OCCUPIED`` bay is excluded **only for a window that
    has already begun** (D68): the car is there *now*, but a future window does
    not overlap it, so a momentarily-full lot can still take a later booking.
    ``create_booking`` applies the same rule, so this read and the write agree.

    The overlap test is a correlated ``EXISTS``, so the whole lot is answered in
    one query (using ``booking_slot_window_idx``) rather than one query per slot.
    """

    validate_window(start_time, end_time)
    now = now or timezone.now()
    billed_hours = hours_between(start_time, end_time)

    blocking = Booking.objects.filter(slot=OuterRef("pk")).filter(
        blocking_window_q(start_time, end_time, now)
    )

    queryset = (
        ParkingSlot.objects.filter(
            lot=lot,
            min_booking_hours__lte=billed_hours,
            max_booking_hours__gte=billed_hours,
        )
        .exclude(status=ParkingSlot.Status.OUT_OF_SERVICE)
    )
    # D68: occupied is a *now*-fact, so it hides the bay only for a window that
    # has already started. OUT_OF_SERVICE (above) leaves the pool entirely.
    if start_time <= now:
        queryset = queryset.exclude(status=ParkingSlot.Status.OCCUPIED)

    return (
        queryset.annotate(is_booked=Exists(blocking))
        .filter(is_booked=False)
        .select_related("lot")
    )

#: The time scopes the history read accepts (4.9). Pure time windows, independent
#: of ``status``: a client combines ``scope`` with ``status`` for a tab such as
#: "upcoming confirmed".
HISTORY_SCOPES = ("upcoming", "ongoing", "past")

def filter_bookings(queryset, *, statuses=None, scope=None, lot_id=None, ordering=None, now=None):
    """Refine a booking queryset for the history read (4.9).

    Pure and read-only (a GET has no side effects, D43/Invariant 6). It filters
    on the **stored** ``status``: a lapsed ``PENDING_PAYMENT`` is still stored as
    ``PENDING_PAYMENT``, so it matches a ``status=PENDING_PAYMENT`` filter while
    its ``effective_status`` in the response reads ``EXPIRED`` (lazy expiry is a
    read-time presentation concern, D50).

    ``scope`` is a stored-time window independent of state: ``upcoming`` starts
    after ``now``, ``ongoing`` straddles it, ``past`` has ended. ``statuses`` and
    ``scope`` combine as an AND. It is an unlocked read, like ``available_slots``:
    it says nothing about concurrency.
    """

    if statuses:
        queryset = queryset.filter(status__in=statuses)

    if scope:
        now = now or timezone.now()
        if scope == "upcoming":
            queryset = queryset.filter(start_time__gt=now)
        elif scope == "ongoing":
            queryset = queryset.filter(start_time__lte=now, end_time__gt=now)
        elif scope == "past":
            queryset = queryset.filter(end_time__lte=now)

    if lot_id is not None:
        queryset = queryset.filter(slot__lot_id=lot_id)

    if ordering:
        # ``-id`` keeps paging stable regardless of the chosen sort key.
        queryset = queryset.order_by(ordering, "-id")

    return queryset

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
    if slot.status == ParkingSlot.Status.OCCUPIED and start_time <= now:
        raise SlotUnavailableError("This slot is currently occupied.")
    
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

def _manager_scoped_slot_id(booking_id, user):
    """The slot id of a booking on a lot assigned to ``user``, or None (D69).

    Combines ownership and Invariant 3 into one lookup: a booking in a lot this
    manager is not assigned to is simply not found -- a 404, never a 403. The
    unlocked read only locates the row to lock, exactly as confirmation does.
    """
    return (
        Booking.objects.filter(pk=booking_id, slot__lot__manager=user)
        .values_list("slot_id", flat=True)
        .first()
    )

@transaction.atomic
def check_in_booking(*, booking_id, user, now=None):
    """Simulate a vehicle entering: ``CONFIRMED -> IN_PROGRESS`` (6.3, D69).

    Manager-only, scoped to the booking's assigned lot. The **slot** row is
    locked first, mirroring create/confirm/cancel (D49/D51/D53), so entry cannot
    race a cancel, confirm or extension. Entry stamps ``actual_entry_at`` and
    marks the slot ``OCCUPIED`` (never overriding ``OUT_OF_SERVICE``, D68).

    Idempotent: checking in an already-``IN_PROGRESS`` booking returns it
    unchanged. Any other state is refused with ``BOOKING_NOT_CHECKINABLE``.
    """
    now = now or timezone.now()

    slot_id = _manager_scoped_slot_id(booking_id, user)
    if slot_id is None:
        raise BookingNotFoundError("No booking with this id exists.")

    slot = (
        ParkingSlot.objects.select_for_update(of=("self",))
        .filter(pk=slot_id)
        .first()
    )
    booking = Booking.objects.get(pk=booking_id)

    if booking.status == Booking.Status.IN_PROGRESS:
        return booking
    if booking.status != Booking.Status.CONFIRMED:
        raise BookingNotCheckinableError(
            f"A {booking.status} booking cannot be checked in."
        )

    booking.status = Booking.Status.IN_PROGRESS
    booking.actual_entry_at = now
    booking.updated_at = now
    booking.save(update_fields=["status", "actual_entry_at", "updated_at"])

    set_slot_occupancy(slot, ParkingSlot.Status.OCCUPIED)
    return booking

@transaction.atomic
def check_out_booking(*, booking_id, user, now=None):
    """Simulate a vehicle leaving: ``IN_PROGRESS -> COMPLETED`` (6.3, D69).

    Manager-only and assigned-lot scoped, taking the same shared slot lock as
    entry/confirm/cancel. Exit stamps ``actual_exit_at`` (what 6.4 measures
    overstay against) and returns the slot to ``AVAILABLE`` (never overriding
    ``OUT_OF_SERVICE``, D68).

    Idempotent: an already-``COMPLETED`` booking returns unchanged. Any other
    state is refused with ``BOOKING_NOT_CHECKOUTABLE``.
    """
    now = now or timezone.now()

    slot_id = _manager_scoped_slot_id(booking_id, user)
    if slot_id is None:
        raise BookingNotFoundError("No booking with this id exists.")

    slot = (
        ParkingSlot.objects.select_for_update(of=("self",))
        .filter(pk=slot_id)
        .first()
    )
    booking = Booking.objects.get(pk=booking_id)

    if booking.status == Booking.Status.COMPLETED:
        return booking
    if booking.status != Booking.Status.IN_PROGRESS:
        raise BookingNotCheckoutableError(
            f"A {booking.status} booking cannot be checked out."
        )

    booking.status = Booking.Status.COMPLETED
    booking.actual_exit_at = now
    booking.updated_at = now
    booking.save(update_fields=["status", "actual_exit_at", "updated_at"])

    set_slot_occupancy(slot, ParkingSlot.Status.AVAILABLE)
    return booking

def refund_due_for(booking, *, now, cutoff_minutes):
    """The amount refundable if ``booking`` is cancelled at ``now`` (§19, D53).

    Only a ``CONFIRMED`` booking has been paid, so only it can owe a refund. A
    cancellation at or before ``start_time - cutoff_minutes`` earns the full
    ``base_amount``; later than that, nothing. The result is computed here and
    snapshotted onto the booking by :func:`cancel_booking`, so a later change to
    the cutoff cannot rewrite an already-cancelled booking.
    """
    if booking.status != Booking.Status.CONFIRMED:
        return Decimal("0.00")
    if now <= booking.start_time - timedelta(minutes=cutoff_minutes):
        return booking.base_amount
    return Decimal("0.00")

@transaction.atomic
def cancel_booking(*, booking_id, user, now=None):
    """Cancel the caller's own booking and record any refund due (4.7, D53).

    A consumer may cancel a ``PENDING_PAYMENT`` (early release of the §18 hold)
    or a ``CONFIRMED`` booking; both free the slot immediately. The refund is
    decided by the §19 cutoff and **stored**, but no money moves -- Phase 5's
    gateway reads ``refund_due_amount`` (the Phase 4/5 boundary).

    Concurrency: the **slot** row is locked first, mirroring
    :func:`create_booking` and :func:`confirm_booking` (D49/D51). Cancellation
    needs no window check, but it must serialize with confirmation, which locks
    the slot and then writes the booking. Locking only the booking row would let
    a payment-success and a cancel both commit, losing one of the two writes.
    Same first lock, same order, no race.

    Ownership is part of the lookup: another consumer's booking is simply not
    found (Invariant 2). Cancelling an already-``CANCELLED`` booking returns it
    unchanged -- idempotent, like confirmation -- so a retry is safe.
    """
    now = now or timezone.now()

    # Scope the lookup to the caller so a foreign id is BOOKING_NOT_FOUND, not a
    # leak. The unlocked read only finds the slot to lock, as in confirmation.
    slot_id = (
        Booking.objects.filter(pk=booking_id, user=user)
        .values_list("slot_id", flat=True)
        .first()
    )
    if slot_id is None:
        raise BookingNotFoundError("No booking with this id exists.")

    # D49/D51: the same first lock creation and confirmation take. D39 makes
    # ``Booking.slot`` PROTECT, so the locked slot always exists.
    ParkingSlot.objects.select_for_update(of=("self",)).filter(pk=slot_id).first()

    booking = Booking.objects.get(pk=booking_id)

    if booking.status == Booking.Status.CANCELLED:
        return booking

    if booking.status not in CANCELLABLE_STATUSES:
        raise BookingNotCancellableError(
            f"A {booking.status} booking cannot be cancelled."
        )

    cutoff_minutes = BusinessRule.load().cancellation_cutoff_minutes
    booking.refund_due_amount = refund_due_for(
        booking, now=now, cutoff_minutes=cutoff_minutes
    )
    booking.status = Booking.Status.CANCELLED
    booking.cancelled_at = now
    booking.cancelled_by = user
    booking.updated_at = now
    booking.save(
        update_fields=[
            "status",
            "cancelled_at",
            "cancelled_by",
            "refund_due_amount",
            "updated_at",
        ]
    )
    return booking

def quote_extension(*, booking, new_end_time, now=None):
    """Price lengthening ``booking`` to ``new_end_time`` (D54, §19).

    Read-only, so a client can be shown the cost before Phase 5 charges; it is
    therefore an *unlocked hint* for conflicts, like ``available_slots``.
    ``extend_booking`` re-runs this under the slot lock before writing.

    The window must strictly lengthen (``new_end_time > booking.end_time``) and
    end in the future. Billing recomputes the **whole** window, not the rounded
    slice: ``new_billed = hours_between(start, new_end)`` and the charge is the
    difference, so ``billed_hours`` always equals "whole hours of
    ``[start, end)``" (D42). The slot's per-bay duration policy is re-applied
    through the shared ``validate_duration``, so the new total still satisfies
    **both** its minimum and maximum (D45/D54).
    """
    now = now or timezone.now()

    if new_end_time <= booking.end_time:
        raise InvalidExtensionError(
            "The new end time must be after the booking's current end time."
        )
    if new_end_time <= now:
        raise InvalidExtensionError("The new end time must be in the future.")

    new_billed_hours = hours_between(booking.start_time, new_end_time)
    # D45: the same per-bay min/max rule creation uses. Lengthening only grows
    # ``billed_hours``, so the minimum can never be broken -- but the maximum
    # very much can, and one shared rule enforces both ends.
    validate_duration(booking.slot, new_billed_hours)

    added_hours = new_billed_hours - booking.billed_hours
    extension_amount = booking.hourly_rate * added_hours
    return ExtensionQuote(
        added_hours=added_hours,
        extension_amount=extension_amount,
        new_billed_hours=new_billed_hours,
        new_base_amount=booking.base_amount + extension_amount,
        hourly_rate=booking.hourly_rate,
        new_end_time=new_end_time,
    )

@transaction.atomic
def extend_booking(*, booking_id, user, new_end_time, now=None):
    """Apply a (paid) extension to the caller's own booking (4.8, D54).

    This is the **extension seam**: Phase 5's gateway calls it once it has
    charged the amount ``quote_extension`` returned. Phase 4 charges nothing and
    records nothing extra -- it only moves ``end_time``/``billed_hours``/
    ``base_amount`` forward -- so ``base_amount`` never includes unpaid money.
    That is what keeps 4.7's "refund the full ``base_amount``" rule correct for
    an extended booking.

    Ordering mirrors the other write paths (D49/D51/D53): lock the **slot** row
    first, re-read the booking, check its state, re-price and re-check the added
    window ``[old_end, new_end)`` for conflicts, then write. A gateway retry
    that sends the same ``new_end_time`` is a no-op success.
    """
    now = now or timezone.now()

    # Scope to the caller so a foreign id is BOOKING_NOT_FOUND (Invariant 2).
    slot_id = (
        Booking.objects.filter(pk=booking_id, user=user)
        .values_list("slot_id", flat=True)
        .first()
    )
    if slot_id is None:
        raise BookingNotFoundError("No booking with this id exists.")

    # D49/D51/D53: the same first lock every booking write takes.
    slot = (
        ParkingSlot.objects.select_for_update(of=("self",))
        .filter(pk=slot_id)
        .first()
    )

    booking = Booking.objects.get(pk=booking_id)

    if booking.status not in EXTENDABLE_STATUSES:
        raise BookingNotExtendableError(
            f"A {booking.status} booking cannot be extended."
        )

    # Gateway retry: the extension is already in place.
    if new_end_time == booking.end_time:
        return booking

    # Re-price and re-apply the duration policy under the lock. May raise
    # INVALID_EXTENSION or MAX_DURATION_EXCEEDED.
    quote = quote_extension(booking=booking, new_end_time=new_end_time, now=now)

    # D41/D43: the *added* window must be free. The booking itself cannot match
    # (its end is the left edge of a half-open interval), but exclude it anyway.
    conflict = (
        Booking.objects.filter(slot=slot)
        .exclude(pk=booking.pk)
        .filter(blocking_window_q(booking.end_time, new_end_time, now))
        .exists()
    )
    if conflict:
        raise BookingConflictError("The time after this booking is already taken.")

    booking.end_time = new_end_time
    booking.billed_hours = quote.new_billed_hours
    booking.base_amount = quote.new_base_amount
    booking.updated_at = now
    booking.save(
        update_fields=["end_time", "billed_hours", "base_amount", "updated_at"]
    )
    return booking