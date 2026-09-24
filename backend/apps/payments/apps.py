from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    """Payment records, mock gateway, refunds and receipts.

    Owns: payment records, mock payment gateway, refunds, receipts,
    transaction status. No real financial processing is performed.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.payments"
    label = "payments"
    verbose_name = "Payments"
