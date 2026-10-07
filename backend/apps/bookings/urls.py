from django.urls import path

from .views import BookingCancelView, BookingListCreateView

urlpatterns = [
	path("bookings/", BookingListCreateView.as_view(), name="booking-list"),
	path("bookings/<int:pk>/cancel/", BookingCancelView.as_view(), name="booking-cancel"),
]