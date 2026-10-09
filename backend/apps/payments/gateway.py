"""Payment gateway abstraction (PROJECT.md §26 — D56 revised, D58).

The rest of the application depends only on :class:`PaymentGateway`. Two adapters
implement it:

* :class:`MockGateway` — deterministic and offline; the default, so the test
  suite and local development need no network or credentials (D7).
* :class:`RazorpayGateway` — the Razorpay test-mode sandbox (D56 revised).

:func:`get_payment_gateway` selects the adapter from ``settings.PAYMENT_GATEWAY``.
Only this module imports the Razorpay SDK, and it does so **lazily**, so importing
this module never requires the package to be installed.
"""

from __future__ import annotations

import hashlib, hmac, itertools, json

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.conf import settings

class PaymentGatewayError(Exception):
    """The gateway could not be configured or reached (not a card decline)."""

@dataclass(frozen=True)
class PaymentInitiation:
    """What a client needs to complete a payment."""

    gateway_order_id: str
    client_payload: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class PaymentVerification:
    """The outcome of verifying a completion callback (D56: verify, not trust)."""

    success: bool
    gateway_payment_id: str | None = None
    failure_reason: str = ""

@dataclass(frozen=True)
class RefundResult:
    """The provider's acknowledgement of a refund."""

    refund_id: str
    amount: Decimal

@dataclass(frozen=True)
class WebhookEvent:
    """A provider webhook, verified and normalised to our vocabulary (D60).

    ``event`` is the provider's event name (e.g. ``payment.captured``);
    ``success`` says whether it represents money captured. The ids are the
    provider handles we correlate against our stored ``Payment``.
    """

    event: str
    gateway_order_id: str | None = None
    gateway_payment_id: str | None = None
    success: bool = False

class PaymentGateway(ABC):
    """The provider-agnostic payment interface (PROJECT.md §26).

    Methods take primitives -- never domain models -- so an adapter stays thin
    and the persistence layer (the service) owns every database write (D58).
    """

    @abstractmethod
    def create_payment(
        self, *, amount: Decimal, currency: str, receipt: str
    ) -> PaymentInitiation:
        """Open a charge with the provider and return its handle."""

    @abstractmethod
    def verify_payment(
        self, *, gateway_order_id: str, payload: Mapping[str, str]
    ) -> PaymentVerification:
        """Verify a completion callback; the client is never trusted (§24/§25)."""

    @abstractmethod
    def refund_payment(
        self, *, gateway_payment_id: str, amount: Decimal
    ) -> RefundResult:
        """Refund (part of) a settled payment."""

    @abstractmethod
    def parse_webhook(
        self, *, body: bytes, headers: Mapping[str, str]
    ) -> WebhookEvent | None:
        """Verify and normalise a provider webhook (D60).

        Returns ``None`` when the webhook cannot be verified -- a bad or missing
        signature -- so the caller refuses it rather than trusting it.
        """

def verify_razorpay_signature(
    *, order_id: str, payment_id: str, signature: str, secret: str
) -> bool:
    """Return whether ``signature`` matches Razorpay's HMAC-SHA256 scheme.

    Razorpay signs ``"<order_id>|<payment_id>"`` with the account key secret.
    This is pure stdlib, so the security-critical path is unit-tested offline.
    """
    if not order_id or not payment_id or not signature or not secret:
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{order_id}|{payment_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

def verify_razorpay_webhook_signature(
    *, body: bytes, signature: str, secret: str
) -> bool:
    """Return whether a Razorpay webhook signature matches its raw body (D60).

    Razorpay signs the **raw request body** with the webhook secret, so the
    bytes must be verified *before* they are parsed. Pure stdlib, unit-tested
    offline, exactly like :func:`verify_razorpay_signature`.
    """

    if not body or not signature or not secret:
        return False
    expected = hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)



#: Shared across MockGateway instances. ``get_payment_gateway()`` builds a fresh
#: adapter on every call, so a per-instance counter would restart at 1 and mint
#: duplicate ids -- which the unique ``provider_order_id`` / ``provider_payment_id``
#: constraints reject once a second attempt exists (5.3, D59).
_MOCK_SEQUENCE = itertools.count(1)

#: The fixed header value MockGateway accepts for a webhook, so the signature
#: gate is still exercised in the offline suite (a wrong/absent value is refused,
#: mirroring a bad Razorpay signature). Real deployments use RazorpayGateway.
MOCK_WEBHOOK_HEADER = "X-Mock-Signature"
MOCK_WEBHOOK_SIGNATURE = "mock-signature"
class MockGateway(PaymentGateway):
    
    """Offline, deterministic adapter for the automated suite (D58).

    Never touches the network. ``create_payment`` mints a fake order id,
    ``verify_payment`` succeeds unless the payload asks for a failure via
    ``{"outcome": "failure"}``, and ``refund_payment`` mints a fake refund id.
    """

    def _next(self, prefix: str) -> str:
        return f"{prefix}_mock_{next(_MOCK_SEQUENCE):06d}"

    def create_payment(self, *, amount, currency, receipt):
        order_id = self._next("order")
        return PaymentInitiation(
            gateway_order_id=order_id,
            client_payload={
                "gateway": "mock",
                "order_id": order_id,
                "amount": str(amount),
                "currency": currency,
                "receipt": receipt,
            },
        )

    def verify_payment(self, *, gateway_order_id, payload):
        if dict(payload or {}).get("outcome") == "failure":
            return PaymentVerification(
                success=False, failure_reason="mock_declined"
            )
        return PaymentVerification(
            success=True, gateway_payment_id=self._next("pay")
        )

    def refund_payment(self, *, gateway_payment_id, amount):
        return RefundResult(refund_id=self._next("rfnd"), amount=amount)

    def parse_webhook(self, *, body, headers):
        if (headers or {}).get(MOCK_WEBHOOK_HEADER) != MOCK_WEBHOOK_SIGNATURE:
            return None
        try:
            data = json.loads(body or b"{}")
        except (TypeError, ValueError):
            return None
        entity = (data.get("payload") or {}).get("payment", {}).get("entity", {})
        event = str(data.get("event", ""))
        return WebhookEvent(
            event=event,
            gateway_order_id=entity.get("order_id"),
            gateway_payment_id=entity.get("id"),
            success=event == "payment.captured",
        )

class RazorpayGateway(PaymentGateway):
    """Razorpay **test-mode** adapter (D56 revised, D58).

    The SDK is imported in ``__init__`` so this module imports cleanly without
    the package. Amounts cross the boundary in **paise** (₹1 = 100 paise); the
    database keeps rupees (D57).
    """ 

    def __init__(self) -> None:
        try:
            import razorpay  # noqa: PLC0415 -- imported lazily on purpose
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise PaymentGatewayError(
                "The 'razorpay' package is not installed; run `pip install razorpay`."
            ) from exc

        key_id = getattr(settings, "RAZORPAY_KEY_ID", "")
        key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", "")
        if not key_id or not key_secret:
            raise PaymentGatewayError(
                "RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set (test mode)."
            )

        self._client = razorpay.Client(auth=(key_id, key_secret))
        self._key_id = key_id
        self._key_secret = key_secret

    @staticmethod
    def _to_paise(amount: Decimal) -> int:
        return int((Decimal(amount) * 100).to_integral_value())

    def create_payment(self, *, amount, currency, receipt):
        order = self._client.order.create(
            {
                "amount": self._to_paise(amount),
                "currency": currency,
                "receipt": receipt,
                "payment_capture": 1,
            }
        )
        return PaymentInitiation(
            gateway_order_id=order["id"],
            client_payload={
                "gateway": "razorpay",
                "key_id": self._key_id,
                "order_id": order["id"],
                "amount": order["amount"],
                "currency": order["currency"],
            },
        )

    def verify_payment(self, *, gateway_order_id, payload):
        payload = dict(payload or {})
        # Never sign with a client-supplied order id: use the one we stored and
        # insist the callback agrees with it (D56: verify, not trust).
        if payload.get("razorpay_order_id") not in (None, "", gateway_order_id):
            return PaymentVerification(
                success=False, failure_reason="order_mismatch"
            )
        if not verify_razorpay_signature(
            order_id=gateway_order_id,
            payment_id=payload.get("razorpay_payment_id", ""),
            signature=payload.get("razorpay_signature", ""),
            secret=self._key_secret,
        ):
            return PaymentVerification(
                success=False, failure_reason="signature_mismatch"
            )
        return PaymentVerification(
            success=True,
            gateway_payment_id=payload.get("razorpay_payment_id", ""),
        )

    def refund_payment(self, *, gateway_payment_id, amount):
        refund = self._client.payment.refund(
            gateway_payment_id, {"amount": self._to_paise(amount)}
        )
        return RefundResult(refund_id=refund["id"], amount=amount)

    def parse_webhook(self, *, body, headers):
        signature = (headers or {}).get("X-Razorpay-Signature", "")
        if not verify_razorpay_webhook_signature(
            body=body,
            signature=signature,
            secret=getattr(settings, "RAZORPAY_WEBHOOK_SECRET", ""),
        ):
            return None
        try:
            data = json.loads(body or b"{}")
        except (TypeError, ValueError):
            return None
        entity = (data.get("payload") or {}).get("payment", {}).get("entity", {})
        event = str(data.get("event", ""))
        return WebhookEvent(
            event=event,
            gateway_order_id=entity.get("order_id"),
            gateway_payment_id=entity.get("id"),
            success=event == "payment.captured",
        )
    
def get_payment_gateway() -> PaymentGateway:
    """Return the adapter named by ``settings.PAYMENT_GATEWAY`` (D58).

    Defaults to the mock adapter so development and tests never require network
    access or credentials; test-mode selects ``razorpay``.
    """
    name = str(getattr(settings, "PAYMENT_GATEWAY", "mock")).strip().lower()
    if name == "mock":
        return MockGateway()
    if name == "razorpay":
        return RazorpayGateway()
    raise PaymentGatewayError(f"Unknown PAYMENT_GATEWAY: {name!r}")