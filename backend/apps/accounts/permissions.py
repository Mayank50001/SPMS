"""Role-based DRF permission classes.

These gate an endpoint by ``request.user.role`` (PROJECT.md §16, §25). They
answer "may this ROLE call this endpoint", and nothing else. Object-level
ownership -- "is this booking mine", "is this manager assigned to this lot" -- is
a different question and belongs in the view's queryset (PROJECT.md §20).

Two things to know before using them:

1. Setting ``permission_classes`` on a view REPLACES the project-wide default
   rather than adding to it (D18 sets ``DEFAULT_PERMISSION_CLASSES`` to
   ``[IsAuthenticated]``). These classes therefore check authentication
   themselves; a view that uses them must not assume ``IsAuthenticated`` is
   still in force.

2. Role is read from ``request.user``, which simplejwt re-loads from the database
   on every request (D15). A role change or a suspension therefore takes effect
   on the next request, with no token refresh and no revocation list.
"""

from rest_framework.permissions import BasePermission

from .models import User


class HasRole(BasePermission):
    """Allow the request only when the user's role is in ``allowed_roles``.

    Subclasses exist so that call sites read as ``permission_classes =
    [IsManager]`` and appear by name in tracebacks and debug toolbars, rather
    than being constructed inline.
    """

    #: Tuple of ``User.Role`` values this permission accepts. Empty means "deny
    #: everyone", which is the correct default for an abstract base.
    allowed_roles: tuple = ()

    #: Surfaced by DRF as the ``detail`` of the 403 response. Deliberately
    #: states which role is required -- that is not a leak, and it saves the
    #: frontend from guessing why a request failed.
    message = "You do not have permission to perform this action."

    def has_permission(self, request, view):
        # AnonymousUser is a different model from User and has no ``role``
        # attribute, so this guard is what stops an anonymous request becoming
        # an AttributeError (500) instead of a rejection.
        #
        # Returning False is all that is needed: DRF converts it to 401 or 403
        # depending on whether authentication itself succeeded, so the status
        # code is never hand-coded here.
        if not request.user.is_authenticated:
            return False

        return request.user.role in self.allowed_roles

    # NOTE: ``has_object_permission`` is intentionally NOT overridden. DRF's
    # default returns True, and repeating the role check here would look like
    # object-level protection while providing none -- the role check has already
    # run, and it still does not know who owns the object. Views must scope their
    # querysets instead.


class IsConsumer(HasRole):
    """Allow only ``User.Role.CONSUMER`` accounts."""

    allowed_roles = (User.Role.CONSUMER,)
    message = "This endpoint is available to consumers only."


class IsManager(HasRole):
    """Allow only ``User.Role.MANAGER`` accounts.

    This checks the role, and only the role. "Is this manager assigned to lot
    10?" cannot be answered until ``ManagerLotAssignment`` exists in Phase 3, so
    PROJECT.md §20 Invariant 3 is not yet enforceable by any permission class.
    """

    allowed_roles = (User.Role.MANAGER,)
    message = "This endpoint is available to parking managers only."


class IsAdmin(HasRole):
    """Allow only ``User.Role.ADMIN`` accounts.

    ``is_superuser`` is deliberately not accepted as an alternative authority.
    ``UserManager.create_superuser`` forces ``role=ADMIN``, so a superuser
    already passes on the role alone; accepting ``is_superuser`` separately would
    create a second authorization source alongside the role column, which D15
    rejected. The Django admin site's ``is_staff`` gate governs ``/admin/`` and
    is a separate system for a separate surface.
    """

    allowed_roles = (User.Role.ADMIN,)
    message = "This endpoint is available to administrators only."
