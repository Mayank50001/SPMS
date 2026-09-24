from django.apps import AppConfig


class ParkingConfig(AppConfig):
    """Parking lots, slots, slot types, pricing and manager assignments.

    Owns: parking lots, parking slots, slot types, pricing configuration,
    manager-to-lot assignments.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.parking"
    label = "parking"
    verbose_name = "Parking"
