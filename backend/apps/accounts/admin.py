"""Django admin registration for the accounts domain.

Minimal, standard registration so Administrators can manage users through the
Django admin. No SPMS business rules live here.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, Vehicle


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin for the email-based custom user model."""

    ordering = ("email",)
    list_display = ("email", "full_name", "role", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("email", "full_name", "phone")
    readonly_fields = ("created_at", "updated_at", "last_login")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("full_name", "phone")}),
        (
            "Roles & permissions",
            {
                "fields": (
                    "role",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "full_name",
                    "role",
                    "password1",
                    "password2",
                    "is_active",
                    "is_staff",
                ),
            },
        ),
    )

    filter_horizontal = ("groups", "user_permissions")


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    """Admin for consumer vehicles.

    Read-only on ``registration_number`` because it is derived from segments by
    the API (V2); editing it here would bypass the format/uniqueness checks.
    """

    list_display = ("registration_number", "owner", "make", "model", "color")
    list_filter = ("make", "color")
    search_fields = ("registration_number", "owner__email")
    readonly_fields = ("registration_number", "created_at", "updated_at")
