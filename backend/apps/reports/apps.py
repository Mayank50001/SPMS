from django.apps import AppConfig


class ReportsConfig(AppConfig):
    """Occupancy, revenue and booking reports / dashboard metrics.

    Owns: occupancy reports, revenue reports, booking statistics and
    administrator dashboard metrics. Day-bucketing uses BUSINESS_TIMEZONE.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reports"
    label = "reports"
    verbose_name = "Reports"
