"""Parking-domain business logic that is more than input validation.

PROJECT.md §9 lists pricing and rules that must hold under concurrency among the
"core backend logic". Invariant 4 (D35) is exactly that, so it lives here rather
than in a serializer: a serializer guards only the API door, while every write
path -- API, admin, shell, a future command -- should pass through the same
check (the ``accounts.services.update_user_access`` precedent).

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

from .models import BusinessRule, Tariff

class MaxRateExceededError(Exception):
    """A tariff's ``hourly_rate`` is above the Administrator's maximum."""


class MaxRateBelowTariffError(Exception):
    """Lowering the maximum would leave an existing tariff above it."""

def _locked_business_rule():
    BusinessRule.load()
    return BusinessRule.objects.select_for_update().get(pk=1)

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
def set_max_hourly_rate(*, max_hourly_rate):
    """Update the cap, refusing to break Invariant 4 at rest (D35).

    Raises ``MaxRateBelowTariffError`` if any existing tariff is above the new
    maximum.
    """

    rule = _locked_business_rule()

    if Tariff.objects.filter(hourly_rate__gt=max_hourly_rate).exists():
        raise MaxRateBelowTariffError(
            "The maximum cannot be lowered below an existing tariff."
        )

    rule.max_hourly_rate = max_hourly_rate
    rule.save()
    return rule
