from django.urls import path

from .views import (
    BookingCancelView,
    BookingExtensionQuoteView,
    BookingListCreateView,
)

urlpatterns = [
	path("bookings/", BookingListCreateView.as_view(), name="booking-list"),
	path("bookings/<int:pk>/cancel/", BookingCancelView.as_view(), name="booking-cancel"),
	path(
		"bookings/<int:pk>/extension-quote/",
		BookingExtensionQuoteView.as_view(),
		name="booking-extension-quote",
	),
]