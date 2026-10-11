from django.urls import path

from .views import (
    PaymentConfirmView,
    PaymentListCreateView,
    PaymentReceiptView,
    PaymentRefundView,
    PaymentWebhookView,
)

urlpatterns = [
    path("payments/", PaymentListCreateView.as_view(), name="payment-create"),
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
    path(
        "payments/<int:pk>/receipt/",
        PaymentReceiptView.as_view(),
        name="payment-receipt",
    ),
]