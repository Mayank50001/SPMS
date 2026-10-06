"""Add the public booking reference (increment 4.6, D52).

Three operations in one file:

1. add ``reference`` as a nullable, non-unique column (safe for existing rows);
2. backfill every existing booking with a random, unique code;
3. tighten it to the final non-null, unique, editable=False field.

A single ``AddField`` with ``unique=True`` would apply the same default to every
existing row and fail the unique index, so the backfill is explicit.
"""

import secrets

import apps.bookings.references
from django.db import migrations, models

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_LENGTH = 10


def _generate():
    return "".join(secrets.choice(_ALPHABET) for _ in range(_LENGTH))


def fill_references(apps, schema_editor):
    """Give every pre-existing booking a unique reference (D52)."""
    Booking = apps.get_model("bookings", "Booking")
    used = set(
        Booking.objects.exclude(reference__isnull=True).values_list(
            "reference", flat=True
        )
    )
    for booking in Booking.objects.filter(reference__isnull=True):
        candidate = _generate()
        while candidate in used:
            candidate = _generate()
        used.add(candidate)
        booking.reference = candidate
        booking.save(update_fields=["reference"])


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0002_booking_base_amount_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="reference",
            field=models.CharField(
                max_length=12,
                null=True,
                blank=True,
                editable=False,
            ),
        ),
        migrations.RunPython(fill_references, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="booking",
            name="reference",
            field=models.CharField(
                default=apps.bookings.references.generate_reference,
                editable=False,
                help_text=(
                    "Public, unguessable code for receipts and QR/gate lookup "
                    "(D52)."
                ),
                max_length=12,
                unique=True,
            ),
        ),
    ]
