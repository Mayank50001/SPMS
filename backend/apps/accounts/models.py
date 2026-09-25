"""Accounts domain models.

This module currently defines the project's custom ``User`` model and its
manager only. Vehicles, role/authorization helpers and account-status business
rules are deliberately *not* implemented here (PROJECT.md §8, §9).

Schema/scaffolding is in scope for this task; business logic is owned by the
human developer. Search for ``TODO(HUMAN)`` below for the decisions that are
still open.
"""

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models


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

    # Postgres permits multiple NULLs under a UNIQUE constraint, so any number
    # of users may have no phone number while a *provided* phone stays unique.
    # TODO(HUMAN): Decide phone normalisation/verification (PROJECT.md §35 lists
    # "duplicate phone"). E.g. store E.164, or validate format before saving.
    phone = models.CharField(max_length=15, unique=True, null=True, blank=True)

    full_name = models.CharField(max_length=150)

    # TODO(HUMAN): Decide how `role` is enforced server-side (PROJECT.md §25).
    #
    # Questions to answer:
    # - Who is allowed to set/change a user's role? (Privilege-escalation risk:
    #   a Consumer must never promote themselves, and a Manager must not create
    #   Administrators.)
    # - Is `role` mutable after creation, or frozen at account creation?
    # - Should role checks live in a DRF permission class, a model/service
    #   method, or both?
    #
    # The default below is least-privilege (self-registration => CONSUMER).
    # NEVER rely on a client-supplied role (§24, §45): the backend is
    # authoritative.
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CONSUMER,
    )

    # TODO(HUMAN): Define what suspension (is_active=False) must do in practice.
    #
    # Questions to answer:
    # - Must an in-flight JWT stop working immediately once suspended? If so,
    #   how is that enforced (per-request DB check vs. token blacklist)?
    # - Does suspension block login only, or all authenticated requests?
    # - Is there an audit trail for who suspended whom and when? (PROJECT.md
    #   §16: Administrator "suspend users".)
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
