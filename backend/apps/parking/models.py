"""Parking domain models.

Phase 3 (PROJECT.md §36). This first increment defines the lot catalogue only:
``City`` and ``ParkingLot``. Parking slots, tariffs and business rules arrive in
later increments (see ``docs/phase-3-parking/PROGRESS.md``). Comments mark the
decision IDs (PROJECT.md §9) that the code embeds.
"""

from django.core.validators import MinValueValidator
from django.db import models

class City(models.Model):
    """A parking city and its short code (D29-S1).

    The full set of Indian city codes is impractically large, so a small set of
    well-known cities is seeded by a data migration (``0002_seed_cities``) and an
    Administrator may add more through the API. The code is the first half of a
    lot's canonical identifier (``BLR-007``), so it is treated as immutable once
    created: the API exposes list/create only (D37) -- changing a code would
    invalidate every lot code derived from it.
    """

    # ``blr`` and ``BLR`` are the same city, so the value is canonicalised in
    # ``save()`` -- the same single-representation rule as email (D13) and the
    # vehicle plate (D28).
    code = models.CharField(max_length=4, unique=True)
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "city"
        verbose_name_plural = "cities"

    def __str__(self):
        return f"{self.name} ({self.code})"

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

class ParkingLot(models.Model):
    """A physical parking lot (PROJECT.md §16).

    Identity (D29)
    --------------
    The real primary key is the surrogate ``id``. ``code`` is a unique business
    identifier built from the city code and a per-city number (``BLR-007``),
    supplied by an Administrator as two parts and joined in ``save()`` -- the
    same canonical-value pattern as the vehicle plate (D28). Keeping the PK a
    surrogate avoids making every child foreign key a human-meaningful string
    and avoids a race-prone "next number" counter (D29-S2: the number is typed).
    """

    city = models.ForeignKey(
        City,
        on_delete=models.PROTECT,
        related_name="lots",
        help_text="THe city this lot belongs to",
    )

    #: Per-city sequence number chosen by the Administrator (D29-S2).
    number = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    #: Canonical ``CITY-NNN`` value, derived in ``save()`` and never accepted
    #: from the client. ``editable=False`` keeps it out of forms/admin input;
    #: the API exposes it read-only.
    code = models.CharField(max_length=20, unique=True, editable=False)

    name = models.CharField(max_length=150)
    address_line = models.CharField(max_length=255)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=10, blank=True)

    # D38: lifecycle is a flag, not a delete. Inactive lots are hidden from
    # consumers and cannot be booked.
    is_active = models.BooleanField(default=True)

    # D36: exactly one manager per lot, nullable until an Administrator assigns
    # one. SET_NULL so removing an account does not delete the lot.
    # ``limit_choices_to`` is advisory (admin/forms); the role itself is
    # enforced at the service/API layer later.
    manager = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_lots",
        limit_choices_to={"role": "MANAGER"},
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "parking lot"
        verbose_name_plural = "parking lots"
        constraints = [
            models.UniqueConstraint(
                fields=["city", "number"],
                name="unique_lot_number_per_city",
            ),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def save(self, *args, **kwargs):
        # The canonical code is the single stored representation (D29), derived
        # from the city and number on every save so it can never drift from its
        # parts. ``self.city`` may trigger one query on a write, which is fine.
        if self.city_id is not None and self.number is not None:
            self.code = f"{self.city.code}-{self.number:03d}"
        super().save(*args, **kwargs)