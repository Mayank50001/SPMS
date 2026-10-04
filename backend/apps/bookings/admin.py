from django.contrib import admin

from .models import Booking

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    """Read-mostly admin view for inspecting bookings during development."""
    list_display = (
        "id", "slot", 'vehicle', 'status', 'start_time', 'end_time', 'base_amount', 'user',
    )
    list_filter = ("status", "slot_type")
    search_fields = ("vehicle_plate", "user__email")
    date_hierarchy = "start_time"
    # raw_id_fields keeps these FKs as id inputs instead of huge <select>s.
    raw_id_fields = ("user", "created_by", "vehicle", "slot", "cancelled_by")