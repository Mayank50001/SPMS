"""Reports aggregations (Phase 8, D73).

Read-only: every figure is computed from tables Phases 3-6 already built. This
phase adds **no model, no migration and no write path** (§42). The module holds
the seam every report reuses -- the role-scoped lot set, the ``?from=&to=``
period and the ``?lot=`` narrowing -- and the per-metric aggregations 8.2-8.5
build on it.

Day-bucketing follows ``settings.BUSINESS_TIMEZONE`` (D5): instants are stored
UTC but a bare calendar date means midnight in the business timezone.
"""

from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Count, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.accounts.models import User
from apps.bookings.models import Booking
from apps.bookings.services import InvalidWindowError
from apps.parking.models import ParkingLot, ParkingSlot
from apps.payments.models import Payment, Refund

#: Window used when ``?from=&to=`` are both omitted (D73).
DEFAULT_PERIOD_DAYS = 30

class ReportError(Exception):
    """Base class for report refusals (mirrors ``BookingRuleError``)."""

    code = "REPORT_ERROR"


class LotNotFoundError(ReportError):
    """The named ``?lot=`` does not exist or is outside the caller's scope."""

    code = "LOT_NOT_FOUND"


def visible_lots(user):
    """Lots a caller may report on (D73; the D65/D67 role-scope pattern).

    Admin -> every lot; Manager -> only the lots assigned to them. Scoping is
    done in the queryset, so a caller who owns none sees empty figures -- never
    a 403 (Invariant 2/3).
    """
    queryset = ParkingLot.objects.all()
    if user.role == User.Role.ADMIN:
        return queryset
    return queryset.filter(manager=user)

def resolve_scope(*, user, lot_raw):
    """Resolve the role scope plus an optional ``?lot=``, as ``(ids, lot)``.

    ``?lot=`` narrows **within** scope: a Manager naming a lot they are not
    assigned to (or an unknown id) gets ``LOT_NOT_FOUND`` -- a 404, never a 403
    (Invariant 3). Returns the selected lot ids and the chosen lot (or ``None``).
    """
    lots = visible_lots(user)

    if lot_raw in (None, ""):
        return list(lots.values_list("id", flat=True)), None

    try:
        lot_id = int(lot_raw)
    except (TypeError, ValueError):
        raise LotNotFoundError("No parking lot with this id exists.")

    selected = lots.filter(pk=lot_id).first()
    if selected is None:
        raise LotNotFoundError("No parking lot with this id exists.")
    return [selected.id], selected

def scope_block(*, lot_ids, selected):
    """The echoed ``scope`` object every report returns (D73/D74)."""
    return {"lot": selected.id if selected is not None else None, "lots": list(lot_ids)}

def _parse_bound(raw, tz):
    """Parse one ISO-8601 date or datetime into an aware instant (D5).

    A datetime with an offset is kept; a naive datetime and a bare date are read
    as business-local. Anything else is an ``INVALID_WINDOW`` refusal.
    """
    if not raw:
        return None

    parsed = parse_datetime(raw)
    if isinstance(parsed, datetime):
        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed, tz)
        return parsed

    day = parse_date(raw)
    if day is not None:
        return datetime.combine(day, time.min, tzinfo=tz)

    raise InvalidWindowError(f"Unrecognised date or datetime: {raw!r}.")

def parse_period(*, from_raw, to_raw, now=None):
    """Resolve ``?from=&to=`` into the half-open window ``[from, to)`` (D73).

    Both ends accept an ISO date or datetime. With both omitted the window is the
    trailing :data:`DEFAULT_PERIOD_DAYS` days ending now; a single end fills the
    other (``to`` defaults to now, ``from`` to 30 days before ``to``). A window
    that does not move forward raises the shared ``INVALID_WINDOW`` (D41/D73).
    """
    tz = ZoneInfo(settings.BUSINESS_TIMEZONE)
    now = now or timezone.now()

    from_dt = _parse_bound(from_raw, tz)
    to_dt = _parse_bound(to_raw, tz)

    if to_dt is None:
        to_dt = now
    if from_dt is None:
        from_dt = to_dt - timedelta(days=DEFAULT_PERIOD_DAYS)

    if from_dt >= to_dt:
        raise InvalidWindowError("'from' must be before 'to'.")

    return from_dt, to_dt

def period_block(*, from_dt, to_dt):
    """The echoed ``period`` object every report returns (D73)."""
    return {
        "from": from_dt.isoformat(),
        "to": to_dt.isoformat(),
        "timezone": settings.BUSINESS_TIMEZONE,
    }

def booking_statistics(*, user, from_raw=None, to_raw=None, lot_raw=None, now=None):
    """Booking statistics for a period and scope (8.2, D74).

    ``total`` is the **cohort of bookings created** in ``[from, to)``; the
    ``by_status`` breakdown is that same cohort's *current* status. There is no
    stored status history (only one status per booking), so "status at the end of
    the window" cannot be reconstructed; the report says so rather than guessing.
    ``active_now`` is a deliberate *now* snapshot (``IN_PROGRESS`` in scope),
    independent of the period. All seven states are always present, ``0`` when
    empty, so a client never guards for a missing key.
    """
    now = now or timezone.now()
    from_dt, to_dt = parse_period(from_raw=from_raw, to_raw=to_raw, now=now)
    lot_ids, selected = resolve_scope(user=user, lot_raw=lot_raw)

    scoped = Booking.objects.filter(slot__lot_id__in=lot_ids)
    cohort = scoped.filter(created_at__gte=from_dt, created_at__lt=to_dt)

    by_status = {status: 0 for status in Booking.Status.values}
    counts = cohort.values("status").annotate(n=Count("id"))
    for row in counts:
        by_status[row["status"]] = row["n"]

    return {
        "period": period_block(from_dt=from_dt, to_dt=to_dt),
        "scope": scope_block(lot_ids=lot_ids, selected=selected),
        "total": cohort.count(),
        "by_status": by_status,
        "active_now": scoped.filter(status=Booking.Status.IN_PROGRESS).count(),
        "completed": by_status[Booking.Status.COMPLETED],
        "cancelled": by_status[Booking.Status.CANCELLED],
    }

#: Booking states that represent time actually held on a bay (8.4, D76). A
#: PENDING_PAYMENT hold is excluded -- it is not a confirmed reservation -- and
#: CANCELLED/EXPIRED/TERMINATED never occupied the bay.
BOOKED_STATUSES = (
    Booking.Status.CONFIRMED,
    Booking.Status.IN_PROGRESS,
    Booking.Status.COMPLETED,
)


def _money(value):
    """Serialise a Decimal amount as a 2-place string (D34/§46)."""
    return str((value or Decimal("0.00")).quantize(Decimal("0.01")))


def _timedelta_hours(delta):
    """Hours in a ``timedelta`` as a Decimal, without float artefacts."""
    return (
        Decimal(delta.days) * 24
        + Decimal(delta.seconds) / Decimal(3600)
        + Decimal(delta.microseconds) / Decimal(3600000000)
    )


def _ratio(numerator, denominator, *, places="0.0001"):
    """``numerator / denominator`` to ``places``, or ``0`` on a zero divisor."""
    if not denominator:
        return str(Decimal(0).quantize(Decimal(places)))
    value = (Decimal(numerator) / Decimal(denominator)).quantize(
        Decimal(places), rounding=ROUND_HALF_UP
    )
    return str(value)


def revenue_aggregation(*, user, from_raw=None, to_raw=None, lot_raw=None, now=None):
    """Revenue over a period and scope, from the payment/refund ledgers (D75).

    The ``Payment`` ledger is the source of truth -- never ``Booking.base_amount``
    -- because only a captured charge records money that actually moved. ``gross``
    sums ``SUCCEEDED`` payments captured in the window (``paid_at``); ``refunded``
    sums ``SUCCEEDED`` refunds against those same payments; ``net`` is the
    difference. ``payment_failures`` counts ``FAILED`` attempts (windowed on
    ``created_at``, since a failed attempt never reaches ``paid_at``). Overstay is
    reported **separately and never added to revenue**: it was recorded, not
    collected (D70).
    """
    now = now or timezone.now()
    from_dt, to_dt = parse_period(from_raw=from_raw, to_raw=to_raw, now=now)
    lot_ids, selected = resolve_scope(user=user, lot_raw=lot_raw)

    scoped = Payment.objects.filter(booking__slot__lot_id__in=lot_ids)
    captured = scoped.filter(
        status=Payment.Status.SUCCEEDED,
        paid_at__gte=from_dt,
        paid_at__lt=to_dt,
    )

    gross = captured.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    by_purpose = {purpose: Decimal("0.00") for purpose in Payment.Purpose.values}
    for row in captured.values("purpose").annotate(total=Sum("amount")):
        by_purpose[row["purpose"]] = row["total"]

    refunded = (
        Refund.objects.filter(status=Refund.Status.SUCCEEDED, payment__in=captured)
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    overstay = (
        Booking.objects.filter(
            slot__lot_id__in=lot_ids,
            actual_exit_at__gte=from_dt,
            actual_exit_at__lt=to_dt,
        ).aggregate(total=Sum("overstay_amount"))["total"]
        or Decimal("0.00")
    )

    return {
        "period": period_block(from_dt=from_dt, to_dt=to_dt),
        "scope": scope_block(lot_ids=lot_ids, selected=selected),
        "currency": "INR",
        "gross": _money(gross),
        "refunded": _money(refunded),
        "net": _money(gross - refunded),
        "by_purpose": {purpose: _money(amount) for purpose, amount in by_purpose.items()},
        "payment_failures": scoped.filter(
            status=Payment.Status.FAILED,
            created_at__gte=from_dt,
            created_at__lt=to_dt,
        ).count(),
        "overstay_recorded": _money(overstay),
    }


def occupancy_aggregation(*, user, from_raw=None, to_raw=None, lot_raw=None, now=None):
    """Occupancy over a period and scope (8.4, D76).

    Two figures, never blended. ``current`` is the **live** slot-state summary:
    the slot's stored ``status`` is authoritative, so it is a point-in-time truth
    (D2/D33). ``window`` is a **booked-rate proxy** -- booked slot-hours of
    bookings overlapping ``[from, to)`` (clipped to the window) over the hours a
    bay was bookable. Slot state has no stored history, so a measured past
    occupancy cannot be reconstructed; this reports *booked* time and is named so.
    A withdrawn bay (``OUT_OF_SERVICE``) leaves the denominator: it is not
    capacity.
    """
    now = now or timezone.now()
    from_dt, to_dt = parse_period(from_raw=from_raw, to_raw=to_raw, now=now)
    lot_ids, selected = resolve_scope(user=user, lot_raw=lot_raw)

    slots = ParkingSlot.objects.filter(lot_id__in=lot_ids)
    counts = {status: 0 for status in ParkingSlot.Status.values}
    for row in slots.values("status").annotate(n=Count("id")):
        counts[row["status"]] = row["n"]

    total = sum(counts.values())
    out_of_service = counts[ParkingSlot.Status.OUT_OF_SERVICE]
    occupied = counts[ParkingSlot.Status.OCCUPIED]

    overlapping = Booking.objects.filter(
        slot__lot_id__in=lot_ids,
        status__in=BOOKED_STATUSES,
        start_time__lt=to_dt,
        end_time__gt=from_dt,
    ).values_list("start_time", "end_time")

    booked_hours = Decimal("0")
    bookings = 0
    for start, end in overlapping:
        bookings += 1
        booked_hours += _timedelta_hours(min(end, to_dt) - max(start, from_dt))
    booked_hours = booked_hours.quantize(Decimal("0.01"))

    bookable_slots = slots.exclude(status=ParkingSlot.Status.OUT_OF_SERVICE).count()
    bookable_hours = (
        Decimal(bookable_slots) * _timedelta_hours(to_dt - from_dt)
    ).quantize(Decimal("0.01"))

    return {
        "scope": scope_block(lot_ids=lot_ids, selected=selected),
        "period": period_block(from_dt=from_dt, to_dt=to_dt),
        "current": {
            "total": total,
            "available": counts[ParkingSlot.Status.AVAILABLE],
            "occupied": occupied,
            "out_of_service": out_of_service,
            "rate": _ratio(occupied, total - out_of_service),
        },
        "window": {
            "bookings": bookings,
            "booked_hours": str(booked_hours),
            "bookable_hours": str(bookable_hours),
            "booked_rate": _ratio(booked_hours, bookable_hours),
        },
    }

def platform_report(*, user, from_raw=None, to_raw=None, now=None):
    """The Administrator's platform-wide summary (8.5, D77).

    Administrator-only and platform-wide by definition, so there is no ``?lot=``.
    It composes the 8.2-8.4 figures -- booking, revenue and occupancy -- rather
    than recomputing them, so the Administrator sees exactly the numbers a Manager
    would for the same period, plus the platform counts §29 names: users, lots,
    slots, the live occupancy rate and payment failures. The period filter applies
    to everything dated (bookings, revenue); ``occupancy_rate`` is a live snapshot,
    so it is deliberately not windowed (D76).
    """
    now = now or timezone.now()

    bookings = booking_statistics(user=user, from_raw=from_raw, to_raw=to_raw, now=now)
    revenue = revenue_aggregation(user=user, from_raw=from_raw, to_raw=to_raw, now=now)
    occupancy = occupancy_aggregation(
        user=user, from_raw=from_raw, to_raw=to_raw, now=now
    )

    by_role = {role: 0 for role in User.Role.values}
    for row in User.objects.values("role").annotate(n=Count("id")):
        by_role[row["role"]] = row["n"]

    slot_counts = {status: 0 for status in ParkingSlot.Status.values}
    for row in ParkingSlot.objects.values("status").annotate(n=Count("id")):
        slot_counts[row["status"]] = row["n"]

    return {
        "period": bookings["period"],
        "users": {
            "total": User.objects.count(),
            "active": User.objects.filter(is_active=True).count(),
            "by_role": by_role,
        },
        "lots": {
            "total": ParkingLot.objects.count(),
            "active": ParkingLot.objects.filter(is_active=True).count(),
        },
        "slots": {
            "total": sum(slot_counts.values()),
            "by_status": slot_counts,
        },
        "bookings": {
            "total": bookings["total"],
            "active_now": bookings["active_now"],
            "completed": bookings["completed"],
            "cancelled": bookings["cancelled"],
        },
        "revenue": {
            "gross": revenue["gross"],
            "refunded": revenue["refunded"],
            "net": revenue["net"],
        },
        "occupancy_rate": occupancy["current"]["rate"],
        "payment_failures": revenue["payment_failures"],
        "cancellations": bookings["cancelled"],
    }