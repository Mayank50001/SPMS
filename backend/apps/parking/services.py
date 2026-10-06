"""Parking-domain business logic that is more than input validation.

PROJECT.md §9 lists pricing and rules that must hold under concurrency among the
"core backend logic". Invariant 4 (D35) is exactly that, so it lives here rather
than in a serializer: a serializer guards only the API door, while every write
path -- API, admin, shell, a future command -- should pass through the same
check (the ``accounts.services.update_user_access`` precedent).

The per-slot duration policy (D45) is enforced the same way: a slot's
``max_booking_hours`` may not exceed the Administrator's ``max_booking_hours``,
and lowering that ceiling below an existing slot is refused -- the duration twin
of Invariant 4.

Concurrency (D35)
-----------------
A tariff write and a cap change can race: a manager could set ₹60 while the
Administrator lowers the cap to ₹50, and two separate checks could each see the
old value. Both operations therefore lock the same ``BusinessRule`` row first
with ``select_for_update``, inside one ``transaction.atomic``. Whoever commits
second re-reads the committed value and sees the first change's effect, so
Invariant 4 holds at rest.
"""

from django.db import transaction

from .models import BusinessRule, Tariff, ParkingSlot

class MaxRateExceededError(Exception):
    """A tariff's ``hourly_rate`` is above the Administrator's maximum."""


class MaxRateBelowTariffError(Exception):
    """Lowering the maximum would leave an existing tariff above it."""

class SlotDurationAboveMaximumError(Exception):
    """A slot's ``max_booking_hours`` is above the Administrator's maximum."""


class MaxDurationBelowSlotError(Exception):
    """Lowering the maximum would leave an existing slot above it."""


def _locked_business_rule():
    BusinessRule.load()
    return BusinessRule.objects.select_for_update().get(pk=1)

def _effective_max_booking_hours(serializer):
    """The ``max_booking_hours`` a slot write would end up storing.

    A PATCH may omit the field, in which case the instance's current value
    stands; a create that omits it falls back to the model default.
    """
    if "max_booking_hours" in serializer.validated_data:
        return serializer.validated_data["max_booking_hours"]
    if serializer.instance is not None:
        return serializer.instance.max_booking_hours
    return ParkingSlot._meta.get_field("max_booking_hours").get_default()

@transaction.atomic
def save_slot(*, serializer, **save_kwargs):
    """Save a validated slot, enforcing the duration ceiling (D45).

    The check lives here, not in the serializer, so no caller can bypass it --
    the same reasoning as Invariant 4 (D35). It runs while the ``BusinessRule``
    row is locked, so a slot raise and a cap change cannot race.
    """
    rule = _locked_business_rule()
    effective_max = _effective_max_booking_hours(serializer)
    if effective_max > rule.max_booking_hours:
        raise SlotDurationAboveMaximumError(
            f"max_booking_hours must not exceed the maximum of {rule.max_booking_hours}."
        )
    return serializer.save(**save_kwargs)

@transaction.atomic
def set_tariff(*, lot, slot_type, hourly_rate, instance=None):
    """Create or update a tariff, enforcing Invariant 4 (D34, D35).

    ``instance`` is the row being edited, or ``None`` to create one. The lot is
    always the one named by the URL, never client data.
    """
    rule = _locked_business_rule()
    if hourly_rate > rule.max_hourly_rate:
        raise MaxRateExceededError(
            f"hourly_rate must not exceed the maximum of {rule.max_hourly_rate}."
        )

    if instance is None:
        instance = Tariff(lot=lot, slot_type=slot_type, hourly_rate=hourly_rate)
    else:
        instance.slot_type = slot_type
        instance.hourly_rate = hourly_rate
    instance.save()
    return instance

@transaction.atomic
def set_business_rules(*, max_hourly_rate=None, max_booking_hours=None, hold_minutes=None):
    """Update the singleton's ceilings, refusing to break an invariant at rest.

    Any argument may be omitted to leave that value unchanged. All checks run
    under one lock of the ``BusinessRule`` row (D35, D45). ``hold_minutes`` is
    the §19 hold length used by booking creation (4.4); it has no "below an
    existing row" invariant -- it is a forward-looking duration only.
    """

    rule = _locked_business_rule()
    if max_hourly_rate is not None:
        if Tariff.objects.filter(hourly_rate__gt=max_hourly_rate).exists():
            raise MaxRateBelowTariffError(
                "The maximum cannot be lowered below an existing tariff."
            )
        rule.max_hourly_rate = max_hourly_rate

    if max_booking_hours is not None:
        if ParkingSlot.objects.filter(max_booking_hours__gt=max_booking_hours).exists():
            raise MaxDurationBelowSlotError(
                "The maximum cannot be lowered below an existing slot's maximum."
            )
        rule.max_booking_hours = max_booking_hours

    if hold_minutes is not None:
        rule.hold_minutes = hold_minutes
        
    rule.save()
    return rule

def set_max_hourly_rate(*, max_hourly_rate):
    """Change only the rate ceiling (D35). Kept for callers and tests."""
    return set_business_rules(max_hourly_rate=max_hourly_rate)


