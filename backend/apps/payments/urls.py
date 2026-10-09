from django.urls import path

from .views import (
    PaymentConfirmView,
    PaymentCreateView,
    PaymentRefundView,
    PaymentWebhookView,
)

urlpatterns = [
    path("payments/", PaymentCreateView.as_view(), name="payment-create"),
    path(
        "payments/webhook/",
        PaymentWebhookView.as_view(),
        name="payment-webhook",
    ),
    path(
        "payments/<int:pk>/confirm/",
        PaymentConfirmView.as_view(),
        name="payment-confirm",
    ),
    path(
        "payments/<int:pk>/refund/",
        PaymentRefundView.as_view(),
        name="payment-refund",
    ),
]