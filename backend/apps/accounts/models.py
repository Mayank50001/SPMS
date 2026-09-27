"""Accounts domain models.

Defines the custom ``User`` model and its manager. Role-based authorization is
implemented as DRF permission classes in ``apps/accounts/permissions.py`` rather
than here; this module holds only state and persistence. ``TODO(HUMAN)`` and
``TODO(DECISION)`` markers flag decisions that are still open (PROJECT.md §8,
§40).
"""

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
import re



class UserManager(BaseUserManager):
    """Manager for the email-based custom ``User`` model.

    ``create_user`` / ``create_superuser`` are standard Django boilerplate that
    the ``AbstractBaseUser`` contract expects; they contain no SPMS business
    rules.
    """

    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        """Create and save a user with the given email and password."""
        if not email:
            raise ValueError("Users must have an email address.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Create and save an Administrator with full Django-admin access.

        Forces ``is_staff``, ``is_superuser`` and ``role=ADMIN`` so a superuser
        can never be created by accident with a lesser role.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ADMIN)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        if extra_fields.get("role") != User.Role.ADMIN:
            raise ValueError("Superuser must have role=User.Role.ADMIN.")

        return self.create_user(email, password, **extra_fields)

    def get_by_natural_key(self, username):
        """Find a user by login identifier, canonicalising it first.

        ``email`` is the login identifier and is stored lower-cased by
        ``User.save()`` (D13), so the *incoming* identifier must be canonicalised
        the same way before an exact match -- otherwise a user who types
        "John@Gmail.com" would not reach the row stored as "john@gmail.com".

        This method is the single lookup used by Django's authentication
        backend, so putting the rule here makes every path case-insensitive at
        once: the API login, the Django admin and ``manage.py shell``. Because
        both sides are already lower-case, the comparison stays exact and can
        use the unique index (no ``iexact``/``UPPER()`` scan).
        """
        normalized = (username or "").strip().lower()
        return self.get(**{self.model.USERNAME_FIELD: normalized})


class User(AbstractBaseUser, PermissionsMixin):
    """SPMS account identity.

    Authentication is by ``email`` (the ``USERNAME_FIELD``). The single
    ``role`` field distinguishes the three actors from PROJECT.md §16. Account
    suspension is modelled by ``is_active=False``.

    ``PermissionsMixin`` supplies ``is_superuser`` plus the ``groups`` and
    ``user_permissions`` relations used by the Django admin; ``is_staff`` is
    declared explicitly because ``AbstractBaseUser`` does not provide it.
    """

    class Role(models.TextChoices):
        CONSUMER = "CONSUMER", "Consumer"
        MANAGER = "MANAGER", "Parking Manager"
        ADMIN = "ADMIN", "Administrator"

    email = models.EmailField(unique=True)

     # Optional contact number (D23). Deliberately NOT unique: a globally unique,
    # unverified number lets anyone claim a stranger's number and permanently
    # block the real owner. Stored as digits only (see normalize_phone); may be
    # blank/None, and two accounts may share a number.
    phone = models.CharField(max_length=15, null=True, blank=True)
    

    full_name = models.CharField(max_length=150)

    # Role assignment policy:
    #
    # - Self-registration always produces CONSUMER (the default below). `role`
    #   is not a serializer field, so a client can never propose one (§24, §45).
    # - Manager and Administrator accounts are created only by an existing
    #   Administrator (D20), so privilege escalation reduces to one check.
    # - Role checks live in `apps/accounts/permissions.py` as DRF permission
    #   classes (IsConsumer / IsManager / IsAdmin), never in client-supplied data.
    #
    # D24: `role` is mutable by an Administrator (endpoint pending); the last
    # active Administrator can be neither demoted nor suspended. Role changes
    # take effect on the next request because D15 re-reads the user, so no token
    # invalidation is needed.

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CONSUMER,
    )

    # Suspension is ``is_active=False`` (D11). Resolved by D15: JWTAuthentication
    # re-reads the user on every request, so suspension blocks all authenticated
    # requests on the very next call, and TokenObtainPairSerializer refuses to
    # issue tokens to an inactive account at all. No revocation list is needed.
    # Still open: an audit trail for who suspended whom (PROJECT.md §16).
    is_active = models.BooleanField(default=True)

    is_staff = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self):
        return self.email

    @staticmethod
    def normalize_phone(value):
        """Return ``value`` reduced to digits, or ``None`` if it is empty.

        D23: ``phone`` is optional contact information stored digits-only, so
        "+91 98765-43210" and "919876543210" cannot become two different values.
        Only common separators are removed; anything else non-digit is left in
        place so the caller can reject it rather than silently discarding input.
        An empty result becomes ``None`` so "absent" has exactly one form.
        """
        if value is None:
            return None
        digits = re.sub(r"[\s()+\-.]", "", value)
        return digits or None

    def save(self, *args, **kwargs):
        # ``email`` is the login identifier, so exactly one stored
        # representation exists (D13). The assignment matters: ``strip()`` and
        # ``lower()`` return *new* strings, and discarding the result was the B3
        # bug. Queryset ``.update()`` bypasses ``save()``; nothing does that
        # today (a DB-level ``Lower("email")`` unique constraint is a Phase 10
        # hardening item).
        if self.email:
            self.email = self.email.strip().lower()

        self.phone = self.normalize_phone(self.phone)
        super().save(*args, **kwargs)
