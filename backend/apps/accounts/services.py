"""Accounts-domain business logic that is more than input validation.

PROJECT.md §9 lists authorization decisions and concurrency-sensitive rules among
the "core backend logic" that must be explicit. The last-Administrator guard
(D24) is exactly that, so it lives here rather than inside a serializer or view.
"""

from django.db import transaction
from django.db.models import Q

from .models import User


class LastAdministratorError(Exception):
    """A change was refused because it would leave no active Administrator."""


@transaction.atomic
def update_user_access(*, target_id, role=None, is_active=None):
    """Change one account's ``role`` and/or ``is_active``, protecting D24.

    Returns the updated ``User``. Raises ``User.DoesNotExist`` if the target is
    gone, and ``LastAdministratorError`` if the change would leave the platform
    with zero active Administrators.

    Concurrency
    -----------
    "Is another active Administrator left?" is a check-then-act, so two
    Administrators demoting each other at the same instant could each see a count
    of two and both proceed -- leaving zero, with no in-app recovery (D24).

    Every row the decision depends on is therefore locked in ONE statement, in
    primary-key order:

    * all currently active Administrators (the rows the count is taken over), and
    * the target row (the row being changed).

    A single ordered locking query gives every caller the same lock order, which
    avoids the deadlock that "lock the target, then the set" would produce when
    two transactions name different targets. A competing change blocks until the
    first commits, then re-reads committed rows and sees the first change's
    effect, so the guard holds.
    """
    rows = list(
        User.objects.select_for_update()
        .filter(Q(role=User.Role.ADMIN, is_active=True) | Q(pk=target_id))
        .order_by("pk")
    )

    target = next((row for row in rows if row.pk == target_id), None)
    if target is None:
        raise User.DoesNotExist(f"User {target_id} does not exist.")

    active_admins = [
        row for row in rows if row.role == User.Role.ADMIN and row.is_active
    ]

    new_role = target.role if role is None else role
    new_is_active = target.is_active if is_active is None else is_active

    stop_being_active_admin = (
        target.role == User.Role.ADMIN
        and target.is_active
        and not (new_role == User.Role.ADMIN and new_is_active)
    )

    if stop_being_active_admin and len(active_admins) <= 1:
        raise LastAdministratorError(
            "This change would leave the platform without an active Administrator."
        )

    target.role = new_role
    target.is_active = new_is_active
    target.save()
    return target
