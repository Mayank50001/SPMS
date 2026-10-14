from django.urls import path

from .views import (
    BookingReportView,
    OccupancyReportView,
    PlatformReportView,
    RevenueReportView,
)

urlpatterns = [
    path("reports/bookings/", BookingReportView.as_view(), name="report-bookings"),
    path("reports/revenue/", RevenueReportView.as_view(), name="report-revenue"),
    path("reports/occupancy/", OccupancyReportView.as_view(), name="report-occupancy"),
    path("reports/platform/", PlatformReportView.as_view(), name="report-platform"),
]