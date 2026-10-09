"""Payments domain models.

Phase 5 (PROJECT.md §36). This first increment defines the ``Payment`` record
and its state machine only -- the gateway abstraction and the create / confirm /
refund / receipt surfaces arrive in later increments (see
``docs/phase-5-payment/PROGRESS.md``). Comments mark the decision IDs (PROJECT.md
§9) the code embeds.

The concrete gateway is **Razorpay in test mode** behind the provider-agnostic
``PaymentGateway`` interface of PROJECT.md §26 (D56, revised). No real money
moves and no card data is ever stored: the payment UI is Razorpay-hosted.
"""

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

class Payment(models.Model):
    """One charge **attempt** against a :class:`~apps.bookings.models.Booking`
    (PROJECT.md §15, D57).

    ``Payment`` is a separate aggregate from ``Booking``: it tracks **money**,
    while the booking tracks the **reservation**. A successful payment does not
    write ``Booking.status`` itself -- it calls ``services.confirm_booking``
    (D51), which owns that transition.

    There may be several payments per booking -- a failed attempt, a retry, an
    extension charge -- but at most one ``SUCCEEDED`` initial charge. Storing
    each attempt as its own row is what makes retries and extensions possible
    without overwriting history (D57).
    """

    class Purpose(models.TextChoices):
        """What the charge is for (D57)."""

        BOOKING = "BOOKING", "Initial booking"
        EXTENSION = "EXTENSION", "Booking extension"

    class Method(models.TextChoices):
        """How the money is taken (D57)."""

        ONLINE = "ONLINE", "Online (Razorpay)"
        CASH = "CASH", "Cash (manager-recorded)"

    class Status(models.TextChoices):
        """The payment lifecycle states (D57). Deliberately small."""

        PENDING = "PENDING", "Pending"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"
        REFUNDED = "REFUNDED", "Refunded"

    # ---- what --------------------------------------------------------------

    # D57: PROTECT -- payment history must never be orphaned or silently lost
    # if a booking is removed outside the API (mirrors Booking.slot, D39).
    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.PROTECT,
        related_name="payments",
    )

    purpose = models.CharField(
        max_length=20,
        choices=Purpose.choices,
        default=Purpose.BOOKING,
    )

    method = models.CharField(
        max_length=20,
        choices=Method.choices,
        default=Method.ONLINE,
    )

    # ---- money (INR snapshot) ----------------------------------------------

    # D57/§46: the server decides the amount (Booking.base_amount for the
    # initial charge, the D54 quote for an extension); the client never sends
    # it. Decimal/INR, like every other price (D34).
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    # The project is INR-only (§4). Recorded explicitly so a payment row is
    # self-describing; server-set, never accepted from the client (D57).
    currency = models.CharField(max_length=3, default="INR", editable=False)

    # ---- lifecycle bookkeeping ---------------------------------------------

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    # ---- provider handles (Razorpay, D56 revised) --------------------------

    # The Razorpay Order for this attempt (``order_...``) and the payment that
    # settles it (``pay_...``). Both are provider-generated and immutable;
    # storing them unique is how a retried webhook/callback is matched to
    # exactly one attempt (D57). Cash payments carry neither (NULL).
    provider_order_id = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )
    provider_payment_id = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )

    failure_reason = models.CharField(max_length=255, blank=True)

    # Set when the gateway confirms success; used by receipts and transaction
    # history in later increments (D57).
    paid_at = models.DateTimeField(null=True, blank=True)


    # True once a captured charge has been applied to its booking (confirm_booking
    # for an initial charge, extend_booking for an extension). A SUCCEEDED payment
    # with this still False is "captured but not applied": the money is real but
    # the booking could not be moved (lapsed hold / slot taken). The refund it
    # owes is a later Refund ledger event (D61); the automated reconciler that
    # acts on this flag is deferred post-project (D60).
    booking_applied = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "payment"
        verbose_name_plural = "payments"
        indexes = [
            models.Index(
                fields=["booking", "status"],
                name="payment_booking_status_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="payment_amount_positive",
            ),
            # A CASH payment never carries provider handles (D57). The reverse
            # is not enforced: a PENDING online attempt has no ids yet.
            models.CheckConstraint(
                condition=~models.Q(method="CASH")
                | models.Q(
                    provider_order_id__isnull=True,
                    provider_payment_id__isnull=True,
                ),
                name="payment_cash_has_no_provider_ids",
            ),
        ]


    def save(self, *args, **kwargs):
        # A blank provider handle must be NULL, not "", so the unique
        # constraints do not mistake two cash payments for duplicates (D57).
        if not self.provider_order_id:
            self.provider_order_id = None
        if not self.provider_payment_id:
            self.provider_payment_id = None
        super().save(*args, **kwargs)

class Refund(models.Model):
    """A refund **ledger event** against a captured :class:`Payment` (5.5, D61).

    A captured payment is immutable: its ``status`` never moves to a "refunded"
    state. Each refund is its own row instead, so "how much of this payment was
    refunded?" is the sum of its reserving rows and history is never rewritten.

    The *rule* that decides a refund -- the §19 cancellation cutoff -- lives in
    Phase 4 (:func:`apps.bookings.services.refund_due_for`, D53) and is stored
    on the booking. This model only records the money movement.
    """

    class Status(models.TextChoices):
        """The refund lifecycle states (5.5). Small, mirroring ``Payment``."""

        PENDING = "PENDING", "Pending"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"

    # D61: PROTECT -- a refund is part of the financial ledger and must never be
    # orphaned or silently lost if a payment is removed outside the API
    # (mirrors Payment.booking, D57).
    payment = models.ForeignKey(
        "payments.Payment",
        on_delete=models.PROTECT,
        related_name="refunds",
    )

    # D34/D61: Decimal/INR. Any positive amount, so a future partial-refund
    # policy needs no migration -- though 5.5's business rule only ever refunds
    # the full owed amount (§19 is all-or-nothing).
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    # The provider's ``rfnd_...`` handle once acknowledged; NULL while
    # PENDING/FAILED, and unique so a retried acknowledgement is matched once
    # (mirrors Payment.provider_payment_id, D57).
    provider_refund_id = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )

    reason = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "refund"
        verbose_name_plural = "refunds"
        indexes = [
            models.Index(
                fields=["payment", "status"],
                name="refund_payment_status_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="refund_amount_positive",
            ),
        ]

    def save(self, *args, **kwargs):
        # A blank provider handle must be NULL, not "", so the unique constraint
        # does not mistake two not-yet-acknowledged refunds for duplicates.
        if not self.provider_refund_id:
            self.provider_refund_id = None
        super().save(*args, **kwargs)