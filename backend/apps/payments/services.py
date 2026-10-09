"""Payment creation (increment 5.3, D59).

The service layer between the HTTP surface and the gateway. It owns **every**
database write, so the adapters in :mod:`apps.payments.gateway` stay
primitive-only (D58), and it reuses the Phase 4 seams rather than re-deriving
booking rules.

5.3 creates a ``PENDING`` attempt only. Confirming a payment -- verifying the
callback and calling ``bookings.services.confirm_booking`` (D51) -- is 5.4.
"""

from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.services import BookingNotFoundError, is_hold_live

from .gateway import PaymentGatewayError, get_payment_gateway
from .models import Payment

class PaymentError(Exception):
    """Base class for payment refusals; ``code`` is stable (PROJECT.md §33)."""

    code = "PAYMENT_ERROR"

class BookingNotPayableError(PaymentError):
    """The booking is not a live PENDING_PAYMENT, so it cannot be paid (D59)."""

    code = "BOOKING_NOT_PAYABLE"

class BookingAlreadyPaidError(PaymentError):
    """This booking already has a successful initial charge (D59)."""

    code = "BOOKING_ALREADY_PAID"

class PaymentGatewayUnavailableError(PaymentError):
    """The gateway could not be configured or reached (not a card decline)."""

    code = "PAYMENT_GATEWAY_UNAVAILABLE"

def create_payment_attempt(*, booking_id, user):
    """Start an initial ONLINE charge for ``user``'s own booking (5.3, D59).

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

    # Payable = a live hold (D6/D50). Everything else -- confirmed, expired,
    # cancelled, lapsed hold -- is refused.
    if booking.status != Booking.Status.PENDING_PAYMENT or not is_hold_live(
        booking, timezone.now()
    ):
        raise BookingNotPayableError("This booking is not awaiting payment.")

    if Payment.objects.filter(
        booking=booking,
        purpose=Payment.Purpose.BOOKING,
        status=Payment.Status.SUCCEEDED,
    ).exists():
        raise BookingAlreadyPaidError("This booking has already been paid.")

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
        purpose=Payment.Purpose.BOOKING,
        method=Payment.Method.ONLINE,
        amount=booking.base_amount,
        status=Payment.Status.PENDING,
    )

    # A unique per-attempt receipt: the public booking reference (D52) plus the
    # row id.
    receipt = f"{booking.reference}-{payment.id}"
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