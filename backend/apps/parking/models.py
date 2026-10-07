"""Parking domain models.

Phase 3 (PROJECT.md §36). This first increment defines the lot catalogue only:
``City`` and ``ParkingLot``. Parking slots, tariffs and business rules arrive in
later increments (see ``docs/phase-3-parking/PROGRESS.md``). Comments mark the
decision IDs (PROJECT.md §9) that the code embeds.
"""

from django.core.validators import MinValueValidator
from django.db import models
from decimal import Decimal


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

class ParkingSlot(models.Model):
    """A numbered, typed bay inside a :class:`ParkingLot` (D31, D32, D33).

    The slot stores only **physical/operational** state. ``RESERVED`` and
    ``HELD`` are *derived from bookings* in Phase 4/5 and must never appear
    here (D33, revising D2): storing them would collapse physical occupancy,
    booking reservation and temporary hold -- the three concepts PROJECT.md
    §18 forbids merging.

    ``status`` therefore holds ``AVAILABLE`` / ``OCCUPIED`` /
    ``OUT_OF_SERVICE`` only. ``OCCUPIED`` is written by Phase 6 occupancy
    actions; this phase's API exposes ``AVAILABLE`` / ``OUT_OF_SERVICE`` so a
    slot can be withdrawn without deleting it (D38).
    """

    class SlotType(models.TextChoices):
        """Fixed domain types (D32). Not a table; adding one is a migration."""

        REGULAR = "REGULAR", "Regular"
        COMPACT = "COMPACT", "Compact"
        LARGE = "LARGE", "Large"
        TWO_WHEELER = "TWO_WHEELER", "Two-wheeler"
        EV = "EV", "Electric vehicle"

    class Status(models.TextChoices):
        """Stored physical/operational state only (D33)."""

        AVAILABLE = "AVAILABLE", "Available"
        OCCUPIED = "OCCUPIED", "Occupied"
        OUT_OF_SERVICE = "OUT_OF_SERVICE", "Out of service"

    #: CASCADE (3.2 decision 1): a slot has no meaning without its lot. D38
    #: already forbids lot deletion through the API, so this only governs direct
    #: DB/admin deletion. Mirrors Vehicle -> owner (V4).
    lot = models.ForeignKey(
        ParkingLot,
        on_delete=models.CASCADE,
        related_name="slots",
    )

    #: Manager-supplied identifier within the lot (D31), e.g. ``A-01``. Stored
    #: canonically (strip + upper, like the city code D29-S1) so ``a-01`` and
    #: ``A-01`` cannot become two different bays.
    number = models.CharField(max_length=20)

    #: Optional floor label (3.2 decision 2). Char so ``G``, ``1``, ``B1`` read
    #: naturally.
    floor = models.CharField(max_length=10, blank=True)

    slot_type = models.CharField(
        max_length=20,
        choices=SlotType.choices,
        default=SlotType.REGULAR,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AVAILABLE,
    )

    # D45: the manager-set bookable duration policy for THIS bay, in whole
    # hours. Per-slot (not per lot or type) so a premium bay near a lift or an
    # EV charger can enforce a short maximum while a long-stay bay allows a
    # full day. Defaults let every existing slot keep working with no backfill.
    DEFAULT_MIN_BOOKING_HOURS = 1
    DEFAULT_MAX_BOOKING_HOURS = 24

    min_booking_hours = models.PositiveIntegerField(
        default=DEFAULT_MIN_BOOKING_HOURS,
        validators=[MinValueValidator(1)],
        help_text="Shortest bookable duration for this bay, in whole hours.",
    )
    max_booking_hours = models.PositiveIntegerField(
        default=DEFAULT_MAX_BOOKING_HOURS,
        validators=[MinValueValidator(1)],
        help_text="Longest bookable duration for this bay, in whole hours.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "parking slot"
        verbose_name_plural = "parking slots"
        constraints = [
            # D31: the DB constraint is the real guard; the serializer pre-checks
            # so a duplicate is a clean 400 rather than a 500.
            models.UniqueConstraint(
                fields=["lot", "number"],
                name="unique_slot_number_per_lot",
            ),
            # D45: a slot may not have a minimum above its maximum.
            models.CheckConstraint(
                condition=models.Q(
                    min_booking_hours__lte=models.F("max_booking_hours")
                ),
                name="slot_min_booking_hours_lte_max",
            ),
        ]

    def __str__(self):
        return f"{self.lot.code} - {self.number}"

    def save(self, *args, **kwargs):
        # Single stored representation for the slot identifier (3.2 decision 6),
        # the same rule as email (D13), the plate (D28) and the city code
        # (D29-S1). ``.update()`` bypasses this; nothing does that today.
        if self.number:
            self.number = self.number.strip().upper()
        super().save(*args, **kwargs)

class Tariff(models.Model):
    """The hourly price of one slot type in one lot (D34).

    Pricing is keyed on ``(lot, slot_type)``: the same bay size may cost
    different amounts in different lots, and one lot may price its regular and
    EV bays differently. The hour is the billing unit -- PROJECT.md §19 defines
    overstay as a multiple of the "applicable hourly rate", so a ``daily_rate``
    is deliberately not stored (D34).
    """

    lot = models.ForeignKey(
        ParkingLot,
        on_delete=models.CASCADE,
        related_name="tariffs",
    )

    slot_type = models.CharField(
        max_length = 20,
        choices=ParkingSlot.SlotType.choices,
    )

    # Money is ``Decimal``, never ``float`` (D34): binary floats cannot
    # represent 0.10 exactly, so sums drift. ``max_digits=8`` allows up to
    # 999,999.99 INR per hour, far above any real rate.
    hourly_rate = models.DecimalField(
        max_digits=  8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))]
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "tariff"
        verbose_name_plural = "tariffs"
        constraints = [
            models.UniqueConstraint(
                fields = ["lot", "slot_type"],
                name = "unique_tariff_per_lot_slot_type"
            ),
            models.CheckConstraint(
                condition=models.Q(hourly_rate__gt =0),
                name="tariff_hourly_rate_positive",
            ),
        ]

    def __str__(self):
        return f"{self.lot.code} - {self.slot_type}: {self.hourly_rate}"

class BusinessRule(models.Model):
    """The single row of platform-wide rules (D35).

    Only the field Phase 3 needs is modelled: ``max_hourly_rate``, the
    Administrator-defined ceiling for Invariant 4. PROJECT.md §41 forbids
    speculative fields, so the other §19 rules (hold minutes, cancellation
    cutoff, overstay multiplier) arrive with their own phases.

    Singleton strategy (Q1): the row is pinned to ``pk=1`` in ``save()`` and read
    through ``load()``, which creates it on first use. There is never ambiguity
    about which row is "the" rule, and no seed migration is needed.
    """

    max_hourly_rate = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("100.00"),
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    # D45: the Administrator's ceiling on any slot's bookable maximum -- the
    # duration analogue of ``max_hourly_rate`` (Invariant 4). A manager may set
    # a slot's maximum up to this value, never above it.
    max_booking_hours = models.PositiveIntegerField(
        default=72,
        validators=[MinValueValidator(1)],
    )

    # D6/§19: how long a PENDING_PAYMENT booking holds its slot before a lazy
    # query treats it as expired. Introduced in 4.4 because a pending booking
    # that never expires (hold_expires_at=NULL) would block its slot forever.
    hold_minutes = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(1)],
        help_text="Minutes a PENDING_PAYMENT booking holds its slot (PROJECT.md §19).",
    )

    # D53/§19: how long before a booking's start a cancellation still earns a
    # full refund. Introduced in 4.7. Phase 4 owns the refund *rule*; Phase 5's
    # payment gateway performs the money movement (see the Phase 5 boundary).
    cancellation_cutoff_minutes = models.PositiveIntegerField(
        default=30,
        validators=[MinValueValidator(1)],
        help_text="Minutes before start time within which cancellation is non-refundable (PROJECT.md §19).",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "business rule"
        verbose_name_plural = "business rules"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(max_hourly_rate__gt=0),
                name="business_rule_max_hourly_rate_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(max_booking_hours__gt=0),
                name="business_rule_max_booking_hours_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(hold_minutes__gt=0),
                name="business_rule_hold_minutes_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(cancellation_cutoff_minutes__gt=0),
                name="business_rule_cancellation_cutoff_positive",
            )
        ]

    def __str__(self):
        return f"Business rules (max hourly rate: {self.max_hourly_rate})"

    def save(self, *args, **kwargs):
        # Q1: fixed-PK singleton. Every save writes row 1, so a second row can
        # never be created through the model or the Django admin.
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Return the singleton, creating it with defaults on first use."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj