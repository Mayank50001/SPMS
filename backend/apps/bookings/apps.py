from django.apps import AppConfig


class BookingsConfig(AppConfig):
    """Bookings and the booking lifecycle.

    Owns: bookings, booking lifecycle, slot reservation, cancellation,
    extension, temporary holds. Availability is DERIVED from overlapping
    bookings (see docs/DECISIONS.md).
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.bookings"
    label = "bookings"
    verbose_name = "Bookings"
