from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """In-app notification records.

    Owns: notification records, booking notifications, payment notifications,
    system alerts. External providers (SMS/email/push) are optional.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"
    label = "notifications"
    verbose_name = "Notifications"
