"""Bookings domain models.

Phase 4 (PROJECT.md §36). This first increment defines the ``Booking`` record
and its state machine only -- pricing helpers, availability, creation, holds,
cancellation and extension arrive in later increments (see
``docs/phase-4-booking/PROGRESS.md``). Comments mark the decision IDs the code
embeds (PROJECT.md §9).
"""

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from apps.parking.models import ParkingSlot

from .references import generate_reference

class Booking(models.Model):
    """A reservation of one :class:`~apps.parking.models.ParkingSlot` for a time
    window (PROJECT.md §15, §17).

    The booking is the **reservation** concept; the slot's stored ``status``
    stays physical/operational only (D33). "Reserved" and "held" are *derived*
    from bookings at query time, never stored (D2 revised by D33).

    Price is **snapshotted** at creation (D39): the agreed ``hourly_rate``,
    ``slot_type`` and rounded ``billed_hours`` are copied onto the row, so a
    later tariff or slot-type edit cannot retroactively change what an existing
    booking costs.
    """

    class Status(models.TextChoices):
        """The booking lifecycle states (D40, PROJECT.md §17)."""

        PENDING_PAYMENT = "PENDING_PAYMENT", "Pending payment"
        CONFIRMED = "CONFIRMED", "Confirmed"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"
        EXPIRED = "EXPIRED", "Expired"
        TERMINATED = "TERMINATED", "Terminated"

    #: States that occupy the slot's window and therefore block another booking
    #: for an overlapping window (D40). Availability must *additionally* exclude
    #: a ``PENDING_PAYMENT`` whose hold has lapsed -- expiry is lazy (D6/D41),
    #: so it cannot be expressed in this stored tuple alone.
    BLOCKING_STATUSES = (
        Status.PENDING_PAYMENT,
        Status.CONFIRMED,
        Status.IN_PROGRESS,
    )

    # ---- identity ----------------------------------------------------------

    # D52: the public, unguessable code a receipt or QR code carries, so a
    # walk-in (no account) or a gate scanner can look a booking up. Random and
    # unique; generated on save via ``default`` and never edited by a client.
    reference = models.CharField(
        max_length=12,
        unique=True,
        editable=False,
        default=generate_reference,
        help_text="Public, unguessable code for receipts and QR/gate lookup (D52).",
    )

    # ---- who ---------------------------------------------------------------

    # D8: nullable so a manager can create a walk-in for someone with no
    # account. SET_NULL so deleting an account never erases booking history.
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings",
        help_text="The consumer who booked; null for a walk-in.",
    )

    # D36: the acting account. A walk-in has user=null but created_by=manager;
    # a consumer booking has created_by == user.
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_bookings",
        help_text="Who created the booking: the consumer or a manager.",
    )

    # ---- what / where ------------------------------------------------------
    # D39/V6: nullable + SET_NULL because a vehicle may be edited or removed;
    # the authoritative plate is snapshotted below instead.
    vehicle = models.ForeignKey(
        "accounts.Vehicle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings",
    )

    # D39/V6: the canonical plate at booking time. Authoritative for history,
    # reports and gate checks; also carries a walk-in's free-text plate (V7).
    # It is a snapshot: the FK above is only a convenience link.
    vehicle_plate = models.CharField(max_length=20)

    # D39: PROTECT -- a booking must never be orphaned or silently deleted if a
    # slot is removed outside the API (D38 forbids slot deletion via the API).
    slot = models.ForeignKey(
        ParkingSlot, 
        on_delete=models.PROTECT,
        related_name="bookings",
    )

    # D39: snapshot of ``slot.slot_type``. Pricing and the overstay multiplier
    # depend on it, and the slot's type may later be edited.
    slot_type = models.CharField(
        max_length=20,
        choices = ParkingSlot.SlotType.choices,
    )

    # ---- when --------------------------------------------------------------

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    # D39: billing is whole hours, part-hours rounded up (PROJECT.md §19). The
    # rounded count is stored alongside the price snapshot so the amount cannot
    # drift. Storing the count (rather than only end-start) makes the billing
    # decision auditable.
    billed_hours = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
    )

    # ---- money (snapshot) --------------------------------------------------

    # D39: the agreed hourly rate, Decimal/INR (D34). Never read live from the
    # tariff, which may change after the booking is made.
    hourly_rate = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))]
    )

    base_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    # ---- lifecycle bookkeeping ---------------------------------------------
    status = models.CharField(
        max_length=20,
        choices = Status.choices,
        default = Status.PENDING_PAYMENT,
    )

    # D6/D41: the hold deadline while PENDING_PAYMENT. Expiry is lazy -- there
    # is no scheduler; a query treats a lapsed PENDING_PAYMENT as expired.
    hold_expires_at = models.DateTimeField(null=True, blank=True)

    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_bookings",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # History reads newest-first; the id tiebreak makes paging stable.
        ordering = ["-start_time", "-id"]
        verbose_name = "booking"
        verbose_name_plural = "bookings"
        indexes = [
            # Availability / overlap query: window lookups per slot.
            models.Index(
                fields=["slot", "start_time", "end_time"],
                name="booking_slot_window_idx",
            ),
            # "My bookings" filtered by status.
            models.Index(
                fields=["user", "status"],
                name="booking_user_status_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_time__gt=F("start_time")),
                name="booking_end_after_start",
            ),
            models.CheckConstraint(
                condition=Q(billed_hours__gte=1),
                name="booking_billed_hours_min_one",
            ),
            models.CheckConstraint(
                condition=~Q(vehicle_plate=""),
                name="booking_vehicle_plate_not_blank",
            ),
            models.CheckConstraint(
                condition=Q(base_amount__gt=0),
                name="booking_base_amount_positive",
            )
        ]

    def __str__(self):
        return f"{self.slot_id} {self.start_time:%Y-%m-%d %H:%M} [{self.status}]"

    def save(self, *args, **kwargs):
        # D39/V6: the plate snapshot is authoritative and single-form. When a
        # registered vehicle is attached the FK wins (a consumer cannot spoof a
        # plate via the request body); otherwise the free-text walk-in plate is
        # canonicalised (strip + upper), the same rule as email (D13), the
        # vehicle plate (D28) and the slot number (D31).
        if self.vehicle_id is not None:
            self.vehicle_plate = self.vehicle.registration_number
        elif self.vehicle_plate:
            self.vehicle_plate = self.vehicle_plate.strip().upper()
        super().save(*args, **kwargs)

        