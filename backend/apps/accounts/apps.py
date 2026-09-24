from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Users, roles, authentication and vehicles.

    Owns: users, roles, authentication, vehicles, account status.
    Business logic for this domain is implemented by the human developer.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Accounts"
