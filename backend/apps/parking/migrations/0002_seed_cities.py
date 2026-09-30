"""Seed a small starter set of cities (D29-S1).

The full Indian city-code list is infeasibly large, so the platform ships with
well-known cities and Administrators add the rest through the API. A data
migration (rather than a fixture) means it runs automatically on ``migrate`` in
every environment, including tests.
"""

from django.db import migrations

# (code, name)
SEED_CITIES = [
    ("DEL", "Delhi"),
    ("BOM", "Mumbai"),
    ("BLR", "Bengaluru"),
    ("MAA", "Chennai"),
    ("HYD", "Hyderabad"),
    ("CCU", "Kolkata"),
    ("PNQ", "Pune"),
    ("AMD", "Ahmedabad"),
    ("JAI", "Jaipur"),
    ("COK", "Kochi"),
    ("GOI", "Goa"),
    ("LKO", "Lucknow"),
    ("IXC", "Chandigarh"),
    ("BBI", "Bhubaneswar"),
    ("IXR", "Ranchi"),
]

def seed_cities(apps, schema_editor):
    City = apps.get_model("parking", "City")
    City.objects.bulk_create(
        [City(code=code, name=name) for code, name in SEED_CITIES],
        ignore_conflicts=True,
    )

def unseed_cities(apps, schema_editor):
    City = apps.get_model("parking", "City")
    City.objects.filter(code__in=[code for code, _ in SEED_CITIES]).delete()

class Migration(migrations.Migration):
    dependencies = [
        ("parking", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_cities, unseed_cities),
    ]