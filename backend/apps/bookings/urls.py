from django.urls import path

from .views import BookingListCreateView

urlpatterns = [
	path("bookings/", BookingListCreateView.as_view(), name="booking-list"),
]