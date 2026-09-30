from django.contrib import admin

from .models import City, ParkingLot


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


@admin.register(ParkingLot)
class ParkingLotAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "city", "number", "is_active", "manager")
    list_filter = ("is_active", "city")
    search_fields = ("code", "name", "address_line")