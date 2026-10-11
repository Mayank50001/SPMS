"""Payment creation (increment 5.3, D59).

The service layer between the HTTP surface and the gateway. It owns **every**
database write, so the adapters in :mod:`apps.payments.gateway` stay
primitive-only (D58), and it reuses the Phase 4 seams rather than re-deriving
booking rules.

5.3 creates a ``PENDING`` attempt only. Confirming a payment -- verifying the
callback and calling ``bookings.services.confirm_booking`` (D51) -- is 5.4.
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.services import (
    EXTENDABLE_STATUSES,
    BookingNotExtendableError,
    BookingNotFoundError,
    BookingRuleError,
    confirm_booking,
    extend_booking,
    is_hold_live,
    quote_extension,
)

from .gateway import PaymentGatewayError, get_payment_gateway
from .models import Payment, Refund

class PaymentError(Exception):
    """Base class for payment refusals; ``code`` is stable (PROJECT.md §33)."""

    code = "PAYMENT_ERROR"

class BookingNotPayableError(PaymentError):
    """The booking is not a live PENDING_PAYMENT, so it cannot be paid (D59)."""

    code = "BOOKING_NOT_PAYABLE"

class BookingAlreadyPaidError(PaymentError):
    """This booking already has a successful initial charge (D59)."""

    code = "BOOKING_ALREADY_PAID"

class ExtensionAlreadyPaidError(PaymentError):
    """An already-successful extension to this same end time exists (D62)."""

    code = "EXTENSION_ALREADY_PAID"

class PaymentGatewayUnavailableError(PaymentError):
    """The gateway could not be configured or reached (not a card decline)."""

    code = "PAYMENT_GATEWAY_UNAVAILABLE"

class PaymentNotFoundError(PaymentError):
    """No payment with that id belongs to the caller (Invariant 2)."""

    code = "PAYMENT_NOT_FOUND"

class PaymentNotConfirmableError(PaymentError):
    """This attempt is not a live PENDING online booking charge (5.4)."""

    code = "PAYMENT_NOT_CONFIRMABLE"

class PaymentVerificationFailedError(PaymentError):
    """The gateway could not verify the callback (bad signature / declined)."""

    code = "PAYMENT_VERIFICATION_FAILED"

class PaymentCapturedNotAppliedError(PaymentError):
    """Money was captured but the booking could no longer be confirmed (D60)."""

    code = "PAYMENT_CAPTURED_NOT_APPLIED"

class InvalidWebhookSignatureError(PaymentError):
    """A webhook whose signature could not be verified; refuse it."""

    code = "INVALID_WEBHOOK_SIGNATURE"

class PaymentNotRefundableError(PaymentError):
    """This payment is not (yet) entitled to a refund (5.5, D61)."""

    code = "PAYMENT_NOT_REFUNDABLE"

class PaymentRefundFailedError(PaymentError):
    """The gateway refused or failed the refund; the attempt is logged (5.5)."""

    code = "PAYMENT_REFUND_FAILED"

class ReceiptNotAvailableError(PaymentError):
    """The payment has no receipt because it is not a settled charge (5.8, D64)."""

    code = "RECEIPT_NOT_AVAILABLE"

def create_payment_attempt(
    *,
    booking_id,
    user,
    purpose=Payment.Purpose.BOOKING,
    end_time=None,
):
    """Start an ONLINE charge for ``user``'s own booking (5.3 D59, 5.6 D62).

    ``purpose=BOOKING`` charges ``Booking.base_amount`` for a live hold.
    ``purpose=EXTENSION`` prices ``end_time`` with the D54 ``quote_extension``
    and charges only the added hours, storing the target ``extension_end_time``
    for confirmation to read back.

    Returns ``(payment, client_payload)``.

    Ordering: check the booking, resolve the adapter (a config error is refused
    *before* any row is written), store the ``PENDING`` attempt, then open the
    provider order. A provider failure marks the row ``FAILED`` -- the audit
    trail D57 asks for -- and raises a stable error.
    """

    # Ownership is part of the lookup, so a foreign or unknown id is a 404, not
    # a 403 (Invariant 2), matching cancel/extend.
    booking = Booking.objects.filter(pk=booking_id, user=user).first()
    if booking is None:
        raise BookingNotFoundError("No booking with this id exists.")

    now = timezone.now()

    if purpose == Payment.Purpose.EXTENSION:
        # D62: eligibility first.
        if booking.status not in EXTENDABLE_STATUSES:
            raise BookingNotExtendableError(
                f"A {booking.status} booking cannot be extended."
            )

        # The extension twin of BOOKING_ALREADY_PAID: an extension to this exact
        # end time that already succeeded is not charged again. Checked BEFORE
        # the quote, because once the extension is applied the booking's end
        # time IS this value, so the quote would reject it as INVALID_EXTENSION
        # and mask the honest "already paid" answer.
        if Payment.objects.filter(
            booking=booking,
            purpose=Payment.Purpose.EXTENSION,
            status=Payment.Status.SUCCEEDED,
            extension_end_time=end_time,
        ).exists():
            raise ExtensionAlreadyPaidError(
                "This extension has already been paid."
            )

        # D54 quote -- the same unlocked hint the 4.8 read uses; extend_booking
        # re-checks the window under the slot lock when the charge is applied.
        quote = quote_extension(booking=booking, new_end_time=end_time, now=now)
        amount = quote.extension_amount
        extension_end_time = quote.new_end_time

    else:
        # Payable = a live hold (D6/D50). Everything else -- confirmed, expired,
        # cancelled, lapsed hold -- is refused.
        if booking.status != Booking.Status.PENDING_PAYMENT or not is_hold_live(
            booking, now
        ):
            raise BookingNotPayableError("This booking is not awaiting payment.")

        if Payment.objects.filter(
            booking=booking,
            purpose=Payment.Purpose.BOOKING,
            status=Payment.Status.SUCCEEDED,
        ).exists():
            raise BookingAlreadyPaidError("This booking has already been paid.")

        amount = booking.base_amount
        extension_end_time = None

    # Resolve the adapter first: a missing SDK or missing keys raises here,
    # before a row exists (D58/D59).
    try:
        gateway = get_payment_gateway()
    except PaymentGatewayError as exc:
        raise PaymentGatewayUnavailableError(str(exc)) from exc

    # D57/§46: the amount is the server-snapshotted base_amount; the client
    # never supplies it.
    payment = Payment.objects.create(
        booking=booking,
        purpose=purpose,
        method=Payment.Method.ONLINE,
        amount=amount,
        status=Payment.Status.PENDING,
        extension_end_time=extension_end_time
    )

    # A unique per-attempt receipt: the public booking reference (D52) plus the
    # row id. D64 reads the customer-facing receipt through this same helper, so a
    # provider reference and a receipt can never disagree.
    receipt = payment_receipt_number(payment)
    try:
        initiation = gateway.create_payment(
            amount=payment.amount,
            currency=payment.currency,
            receipt=receipt,
        )
    except PaymentGatewayError as exc:
        # The attempt is recorded so a failure is auditable (D57), then the
        # error is surfaced as a stable refusal. (The Razorpay adapter should
        # translate SDK/transport errors into PaymentGatewayError when the
        # sandbox path is exercised.)
        payment.status = Payment.Status.FAILED
        payment.failure_reason = "gateway_unavailable"
        payment.save(update_fields=["status", "failure_reason", "updated_at"])
        raise PaymentGatewayUnavailableError(str(exc)) from exc

    payment.provider_order_id = initiation.gateway_order_id
    payment.save(update_fields=["provider_order_id", "updated_at"])
    return payment, initiation.client_payload

def apply_payment_outcome(
    *, payment, success, gateway_payment_id=None, failure_reason=""
):
    """Record a gateway outcome, then apply it to the booking (5.4, D60).

    This is the single point where a Payment becomes SUCCEEDED/FAILED and the
    D51 ``confirm_booking`` seam is called, so the return-verify path and the
    webhook path cannot drift.

    It is deliberately **not** one transaction. The money state is written and
    committed *before* the booking seam runs, so if the gateway captured the
    money but the booking can no longer be confirmed (lapsed hold, slot taken),
    the payment stays SUCCEEDED -- the money is real -- and only the
    ``booking_applied`` flag records that it could not be applied. The owed
    refund is a later Refund ledger event (D61); the automated reconciler that
    acts on ``booking_applied=False`` is deferred post-project (D60).
    """
    now = timezone.now()

    if not success:
        payment.status = Payment.Status.FAILED
        payment.failure_reason = failure_reason or "verification_failed"
        payment.save(update_fields=["status", "failure_reason", "updated_at"])
        return payment

    # Money is captured: record and COMMIT it first, so a later booking refusal
    # cannot roll the captured state back. Never re-stamp paid_at on a retry.
    payment.status = Payment.Status.SUCCEEDED
    if gateway_payment_id:
        payment.provider_payment_id = gateway_payment_id
    if payment.paid_at is None:
        payment.paid_at = now
    payment.booking_applied = False
    payment.failure_reason = ""
    payment.save(
        update_fields=[
            "status",
            "provider_payment_id",
            "paid_at",
            "booking_applied",
            "failure_reason",
            "updated_at",
        ]
    )

    # D62: an EXTENSION charge applies the stored target end time; a BOOKING
    # charge confirms the pending booking. Both trusted channels (return verify
    # and webhook) reach this one core, so they cannot drift (D60).
    try:
        if payment.purpose == Payment.Purpose.EXTENSION:
            extend_booking(
                booking_id=payment.booking_id,
                user=payment.booking.user,
                new_end_time=payment.extension_end_time,
                now=now,
            )
        else:
            confirm_booking(booking_id=payment.booking_id, now=now)
    except BookingRuleError as exc:
        # Captured but not applied. Keep SUCCEEDED; flag it for the (deferred)
        # reconciler and the 5.5 refund path, and surface a stable refusal.
        prefix = (
            "booking_not_applied"
            if payment.purpose == Payment.Purpose.EXTENSION
            else "booking_not_confirmable"
        )
        payment.failure_reason = f"{prefix}:{exc.code}"
        payment.save(update_fields=["failure_reason", "updated_at"])
        raise PaymentCapturedNotAppliedError(
            "The payment succeeded but the booking could no longer be updated."
        ) from exc

    payment.booking_applied = True
    payment.save(update_fields=["booking_applied", "updated_at"])
    return payment

def confirm_payment_attempt(*, payment_id, user, payload):
    """Verify a returned Checkout callback and apply it (5.4, D60).

    Consumer-only and owner-scoped: a foreign or unknown id is a 404, not a 403
    (Invariant 2). Only a live PENDING **online booking** charge can be
    confirmed here; an extension charge (5.6) and a cash payment (5.7) are
    refused with ``PAYMENT_NOT_CONFIRMABLE``.

    Idempotent: re-posting a SUCCEEDED attempt re-applies the booking seam (a
    harmless no-op once the booking is CONFIRMED) and returns the payment.
    """
    payment = (
        Payment.objects.select_related("booking")
        .filter(pk=payment_id, booking__user=user)
        .first()
    )
    if payment is None:
        raise PaymentNotFoundError("No payment with this id exists.")

    if (
        payment.method != Payment.Method.ONLINE
    ):
        raise PaymentNotConfirmableError(
            "Only an online charge can be confirmed here."
        )

    if payment.status == Payment.Status.SUCCEEDED:
        return apply_payment_outcome(
            payment=payment,
            success=True,
            gateway_payment_id=payment.provider_payment_id,
        )

    if payment.status != Payment.Status.PENDING:
        raise PaymentNotConfirmableError("This payment attempt is already resolved.")

    # Resolve the adapter before verifying: a config error is a 503 and leaves
    # the attempt PENDING (a retry can still succeed).
    try:
        gateway = get_payment_gateway()
    except PaymentGatewayError as exc:
        raise PaymentGatewayUnavailableError(str(exc)) from exc

    # Never sign with a client-supplied order id: use the one we stored (D56).
    verification = gateway.verify_payment(
        gateway_order_id=payment.provider_order_id, payload=payload
    )
    if not verification.success:
        apply_payment_outcome(
            payment=payment,
            success=False,
            failure_reason=verification.failure_reason or "verification_failed",
        )
        raise PaymentVerificationFailedError("The payment could not be verified.")

    return apply_payment_outcome(
        payment=payment,
        success=True,
        gateway_payment_id=verification.gateway_payment_id,
    )

def handle_payment_webhook(*, body, headers):
    """Verify and apply a provider webhook (5.4, D60).

    Public: there is no user, so the gateway signature is the *only*
    authentication. Unknown orders are acknowledged (returns ``None``) so the
    provider stops retrying, and a duplicate event is a no-op because a resolved
    Payment is terminal. Raises ``InvalidWebhookSignatureError`` when the
    signature cannot be verified.
    """
    try:
        gateway = get_payment_gateway()
    except PaymentGatewayError as exc:
        raise PaymentGatewayUnavailableError(str(exc)) from exc

    event = gateway.parse_webhook(body=body, headers=headers)
    if event is None:
        raise InvalidWebhookSignatureError("The webhook signature is invalid.")

    if not event.gateway_order_id and not event.gateway_payment_id:
        return None  # nothing to correlate; acknowledge

    payment = None
    if event.gateway_order_id:
        payment = Payment.objects.filter(
            provider_order_id=event.gateway_order_id
        ).first()
    if payment is None and event.gateway_payment_id:
        payment = Payment.objects.filter(
            provider_payment_id=event.gateway_payment_id
        ).first()
    if payment is None or payment.method != Payment.Method.ONLINE:
        return None  # unknown/irrelevant; acknowledge

    if payment.status != Payment.Status.PENDING:
        return payment  # already resolved: dedupe

    return apply_payment_outcome(
        payment=payment,
        success=event.success,
        gateway_payment_id=event.gateway_payment_id,
        failure_reason="" if event.success else "payment_failed",
    )

#: Refund states that reserve money: a PENDING attempt is in flight and a
#: SUCCEEDED one is settled. Both count against a payment's refundable balance,
#: so a double-submit cannot refund twice (5.5, D61).
_REFUND_RESERVING_STATUSES = (Refund.Status.PENDING, Refund.Status.SUCCEEDED)


def refunded_total(payment):
    """How much of ``payment`` is already refunded or being refunded (5.5)."""

    total = payment.refunds.filter(
        status__in=_REFUND_RESERVING_STATUSES
    ).aggregate(total=Sum("amount"))["total"]
    return total or Decimal("0.00")


def refundable_amount(payment):
    """The amount still refundable on ``payment`` right now (5.5, D61).

    A refund is owed in exactly two situations:

    * the charge was **captured but never applied** to a booking (D60): the
      consumer paid for a slot they did not get, so the whole capture is owed;
    * the booking was **cancelled with a refund entitlement** (D53): the §19 rule
      is all-or-nothing, so each applied charge is fully refundable.

    Everything else is owed nothing. The result is net of refunds already
    reserved or settled, so it is safe to call repeatedly.
    """
    if (
        payment.status != Payment.Status.SUCCEEDED
        or payment.method != Payment.Method.ONLINE
        or not payment.provider_payment_id
    ):
        return Decimal("0.00")

    if not payment.booking_applied:
        ceiling = payment.amount
    else:
        booking = payment.booking
        if (
            booking.status != Booking.Status.CANCELLED
            or booking.refund_due_amount <= 0
        ):
            return Decimal("0.00")
        ceiling = min(payment.amount, booking.refund_due_amount)

    remaining = ceiling - refunded_total(payment)
    return remaining if remaining > 0 else Decimal("0.00")


@transaction.atomic
def _reserve_refund(*, payment_id, reason):
    """Lock the payment and insert a PENDING refund for what is owed (5.5).

    The row lock plus counting PENDING refunds is what makes concurrent refund
    requests safe: the second one sees the first one's PENDING row and reserves
    nothing. Returns ``None`` when nothing is refundable.
    """
    payment = (
        Payment.objects.select_for_update()
        .select_related("booking")
        .get(pk=payment_id)
    )
    amount = refundable_amount(payment)
    if amount <= 0:
        return None
    return Refund.objects.create(
        payment=payment,
        amount=amount,
        status=Refund.Status.PENDING,
        reason=reason,
    )


def refund_payment(*, payment_id, reason=""):
    """Refund what is owed on one payment, recording a ``Refund`` ledger event.

    Returns the :class:`Refund`. Idempotent per payment: once a refund is
    settled, asking again returns the existing row rather than paying twice. A
    gateway failure is recorded as a FAILED ``Refund`` (so it stays auditable)
    and surfaced as ``PAYMENT_REFUND_FAILED``; no money moved, so a retry
    reserves a fresh PENDING row.

    The provider is resolved *before* a row is written (like
    :func:`create_payment_attempt`), so a config error is a 503 with no
    half-recorded refund.
    """
    payment = (
        Payment.objects.select_related("booking").filter(pk=payment_id).first()
    )
    if payment is None:
        raise PaymentNotFoundError("No payment with this id exists.")

    try:
        gateway = get_payment_gateway()
    except PaymentGatewayError as exc:
        raise PaymentGatewayUnavailableError(str(exc)) from exc

    refund = _reserve_refund(payment_id=payment.id, reason=reason)
    if refund is None:
        # Nothing left to move. If a refund already settled (or is in flight),
        # this is a harmless retry -- return it. Otherwise it is a refusal.
        existing = (
            Refund.objects.filter(payment=payment)
            .order_by("-created_at", "-id")
            .first()
        )
        if existing is not None and existing.status in _REFUND_RESERVING_STATUSES:
            return existing
        raise PaymentNotRefundableError(
            "No amount is refundable on this payment."
        )

    try:
        result = gateway.refund_payment(
            gateway_payment_id=payment.provider_payment_id,
            amount=refund.amount,
        )
    except PaymentGatewayError as exc:
        refund.status = Refund.Status.FAILED
        refund.reason = (refund.reason or "gateway_error")[:255]
        refund.save(update_fields=["status", "reason", "updated_at"])
        raise PaymentRefundFailedError(
            "The gateway could not process the refund; retry."
        ) from exc

    refund.status = Refund.Status.SUCCEEDED
    refund.provider_refund_id = result.refund_id
    refund.save(update_fields=["status", "provider_refund_id", "updated_at"])
    return refund


def refund_booking(booking, *, reason="booking_cancelled"):
    """Refund every charge owed on a cancelled booking (5.5, D61).

    Called by the cancellation path after ``cancel_booking`` (D53) has stored
    ``refund_due_amount``. Best-effort by design: this project has no background
    workers, so each payment is attempted once here; a failure is recorded as a
    FAILED ``Refund`` (auditable) and retriable through
    ``POST /api/payments/{id}/refund/``. Returns the ``Refund`` rows touched.
    """
    payments = booking.payments.filter(
        status=Payment.Status.SUCCEEDED,
        method=Payment.Method.ONLINE,
    )
    refunds = []
    for payment in payments:
        try:
            refunds.append(refund_payment(payment_id=payment.id, reason=reason))
        except PaymentError:
            # Already recorded as a FAILED Refund, or simply nothing owed; keep
            # going so one bad payment cannot suppress another's refund.
            continue
    return refunds

def payment_receipt_number(payment):
    """The customer-facing receipt number (D59/D64).

    The public booking reference (D52) plus the payment row id -- the same string
    Phase 5 sends the gateway as its ``receipt``, so a provider reference can be
    reconciled to a receipt. One definition, two call sites.
    """
    return f"{payment.booking.reference}-{payment.id}"

def get_payment_receipt(*, payment_id, user):
    """Return the settled payment a consumer may read a receipt for (5.8, D64).

    Owner-scoped, so a foreign or unknown id is ``PAYMENT_NOT_FOUND`` (Invariant
    2). Only a ``SUCCEEDED`` charge has a receipt; a pending or failed one is
    ``RECEIPT_NOT_AVAILABLE``. The receipt is a projection built by the serializer
    -- nothing is stored (D64).
    """
    payment = (
        Payment.objects.select_related("booking__slot__lot")
        .filter(pk=payment_id, booking__user=user)
        .first()
    )
    if payment is None:
        raise PaymentNotFoundError("No payment with this id exists.")
    if payment.status != Payment.Status.SUCCEEDED:
        raise ReceiptNotAvailableError("This payment does not have a receipt.")
    return payment

def filter_payments(
    queryset,
    *,
    statuses=None,
    method=None,
    purpose=None,
    booking_id=None,
    lot_id=None,
    created_from=None,
    created_to=None,
    ordering=None,
):
    """Refine a payment queryset for a transaction read (5.9, D65).

    Pure and read-only, like ``bookings.services.filter_bookings`` (D43). Every
    argument is optional: the caller (the view) has already scoped the queryset
    to what this user may see, so this only narrows it.
    """

    if statuses:
        queryset = queryset.filter(status__in=statuses)
    if method:
        queryset = queryset.filter(method=method)
    if purpose:
        queryset = queryset.filter(purpose=purpose)
    if booking_id is not None:
        queryset = queryset.filter(booking_id=booking_id)
    if lot_id is not None:
        queryset = queryset.filter(booking__slot__lot_id=lot_id)
    if created_from is not None:
        queryset = queryset.filter(created_at__gte=created_from)
    if created_to is not None:
        queryset = queryset.filter(created_at__lte=created_to)
    if ordering:
        # ``-id`` keeps the page stable regardless of the chosen sort key.
        queryset = queryset.order_by(ordering, "-id")
    return queryset

def annotate_refunded_amount(queryset):
    """Add a derived ``refunded_amount`` (settled refunds) per payment (5.9, D65).

    The total is read from the ``Refund`` ledger (D61), never stored on the
    payment, so it can never drift from the money that actually moved. A payment
    with no refunds gets ``0.00``.
    """
    return queryset.annotate(
        refunded_amount=Coalesce(
            Sum(
                "refunds__amount",
                filter=Q(refunds__status=Refund.Status.SUCCEEDED),
            ),
            Decimal("0.00"),
        )
    )