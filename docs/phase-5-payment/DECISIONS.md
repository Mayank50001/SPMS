# Phase 5 decisions — Payment

Status as of **2026-10-10**:

- **Accepted (2026-10-08; revised 2026-10-08):** **D56** — the payment gateway
  is **Razorpay in test mode**, behind the provider-agnostic payment abstraction.
  Revised from Stripe to Razorpay: SPMS is India-scoped and every amount is INR.
- **Accepted (2026-10-08):** **D57** — the `Payment` model shape and states:
  one row per charge attempt, a small state enum, and a clean separation from
  `Booking.status`.
- **Accepted (2026-10-09):** **D58** — the `PaymentGateway` interface (three
  methods, primitives in/out), adapter selection by settings, and the offline
  `MockGateway` / lazy-SDK test strategy. *(Revised by D60: a 4th method,
  `parse_webhook`.)*
- **Accepted (2026-10-10):** **D59** — the payment-creation surface:
  `POST /api/payments/`, consumer-only, server-authoritative amount, one
  `PENDING` attempt per request, `client_payload` in the response.
- **Accepted (2026-10-10):** **D60** — payment confirmation: a server-verified
  return callback **and** a signature-verified webhook, both funnelling through
  one apply core into the D51 `confirm_booking` seam; the
  **captured-but-not-applied** policy (`Payment.booking_applied`); and the
  revision of D58 to a four-method gateway interface.
- **Accepted (2026-10-10):** **D61** — a refund is a **ledger event** (a child
  `Refund` row), never a mutation of a captured `Payment`. Revises D57 by
  **removing** the `REFUNDED` state; triggered automatically on the D53
  cancellation refund, with a Manager/Admin `POST /api/payments/{id}/refund/`
  retry. See the entry below.
- **Open:** receipts and the transaction views. Each will be surfaced as its own
  decision when its increment is opened (see "Open questions to decide before
  coding").

> A "Decision" below is the human's, not the agent's. Rationale/Consequence
> record why, so the choice can be defended later.

PROJECT.md's Phase 5 scope is: *Payment model, payment states, payment
creation, payment confirmation, receipt, refund* — with **no real financial
processing** (§4, §26).

---

## D56 — Payment gateway: Razorpay test mode behind the abstraction (accepted 2026-10-08; revised 2026-10-08)

> **Revision (2026-10-08):** the concrete gateway changed from Stripe to
> **Razorpay (test mode)**. SPMS is India-scoped and every amount is INR;
> Razorpay gives immediate sandbox access to Indian accounts, settles in INR
> and needs no invite, whereas Stripe's India onboarding is invite-only. The
> decision's *shape* is unchanged — a sandbox provider behind the §26
> abstraction, a `MockGateway` for tests, no card data on our servers,
> server-side verification, idempotency. Only the provider adapter, its
> configuration and its env vars change.

PROJECT.md §26 requires a **payment abstraction** — a `PaymentGateway` interface
(`create_payment`, `verify_payment`, `refund_payment`) that the application
depends on, so it "should not directly depend on a specific payment provider".
PROJECT.md's Phase 5 list and §4 default that interface's implementation to a
**mock payment gateway**. This decision replaces that default with a real
provider's sandbox.

- **Decision:**
  - **Gateway: Razorpay test mode.** The concrete `PaymentGateway` implementation
    is a **Razorpay test-mode (sandbox) adapter**, using Razorpay **Orders**
    (`order_...`) plus the **hosted Checkout** for the payment step (Checkout vs
    Payment Element is settled when the creation increment opens). Razorpay's
    test mode simulates success, failure and refund and returns a test
    transaction id — exactly the behaviours §4 asks a mock to simulate.
  - **Abstraction retained.** Views/services never import the Razorpay SDK;
    only the adapter does, and the gateway is chosen by configuration. Swapping
    in another provider (or a pure mock) stays a small, contained change.
  - **Mock adapter stays for tests.** A lightweight in-memory `MockGateway`
    implementing the same interface remains for automated tests, so the suite
    never makes network calls or needs Razorpay credentials. The Razorpay
    adapter is exercised by **opt-in** integration tests against the sandbox.
  - **Test keys only, secrets never committed.** `RAZORPAY_KEY_ID` /
    `RAZORPAY_KEY_SECRET` (test-mode `rzp_test_...`) and
    `RAZORPAY_WEBHOOK_SECRET` load from `.env` (D9), with placeholders in
    `.env.example`. **No live keys.**
  - **No card data touches our servers.** Payment happens on Razorpay-hosted
    Checkout, so card number, expiry and CVC never reach us. PROJECT.md §4's
    "never store card number / CVV / UPI PIN / banking credentials" is
    satisfied by construction.
  - **Verification, not trust.** A payment is only treated as successful after
    the backend **verifies** the Razorpay signature server-side
    (`HMAC-SHA256(order_id + "|" + payment_id, key_secret)` compared to
    `razorpay_signature`), or after a signature-verified webhook
    (`X-Razorpay-Signature`). The client is never the source of truth
    (PROJECT.md §24/§25).
  - **Idempotency.** Razorpay's provider ids are stored unique and our own
    confirmation seam stays idempotent (D51), so a duplicated webhook or retried
    callback cannot double-confirm or double-charge.
  - **Money unit.** Our database stores **rupees** (`Decimal`, D34); the adapter
    converts to **paise** at the Razorpay API boundary (×100). The conversion
    lives only in the adapter.

- **Explicit scope exclusion — "no external tools" does not apply to payments.**
  PROJECT.md §12 and the general "no external tools" rule are **waived for the
  payment gateway only**: a sandboxed provider adapter moves **no real money**,
  stores **no financial credentials**, and is the §26 abstraction's intended
  plug-in point. Every other external tool or new service still needs explicit
  human approval.

- **Rationale:** the §26 abstraction was designed for a real provider to sit
  behind it; a hand-rolled mock proves less. Razorpay is the India/INR-appropriate
  sandbox and is available immediately, so it demonstrates a genuine
  order → checkout → verify → refund lifecycle safely. Keeping the mock for
  tests preserves a fast, offline, deterministic suite (D7).

- **Rejected:** Stripe (superseded — invite-only onboarding in India and an INR
  mismatch for this project); a hand-rolled mock as the *only* gateway (no real
  round trip); importing the SDK into services/views (breaks §26); live keys or
  real charges (§4); trusting a client-supplied "paid" flag (§24/§25); letting
  automated tests hit the network (slow, flaky, needs secrets).

- **Consequence:** `.env.example` gains the three test/secret placeholders;
  `settings.py` gains a thin Razorpay configuration read through the stdlib
  loader. The `payments` app gains a `gateway.py` (interface + `MockGateway` +
  `RazorpayGateway`) chosen by settings, and `requirements.txt` gains the
  `razorpay` SDK when the sandbox path is first exercised (the adapter imports it
  lazily, so the suite never needs it — D58). Everything downstream still calls
  only the interface.

- **Status:** Accepted (2026-10-08); revised (2026-10-08) — Stripe → Razorpay.

---

## D57 — Payment model and states: one row per charge attempt (accepted 2026-10-08)

D56 fixes *which gateway*; D57 fixes *what we store* and *how payment states
relate to the booking*. (Open questions 1–2 of the previous list.)

- **Decision:**
  - **One `Payment` row per charge attempt, not one per booking.** A booking may
    accumulate several rows — a failed attempt, a retry, an extension charge —
    but at most one `SUCCEEDED` initial charge. This is what lets a consumer
    retry a failed card and lets the extension increment (5.6) charge again
    without overwriting history. *Rejected: one row per booking — it cannot
    represent a retry or an extension.*
  - **`Payment` and `Booking` are separate aggregates.** `Payment.status` tracks
    **money**; `Booking.status` tracks the **reservation**. A successful payment
    does not write `Booking.status` directly — it calls the D51
    `confirm_booking` seam, which owns that transition. The two lifecycles stay
    independent and every Phase 4 guarantee (holds, slot locking, idempotency)
    is preserved.
  - **States (deliberately small):** `PENDING → SUCCEEDED | FAILED`, and
    `SUCCEEDED → REFUNDED` (5.5). `PENDING` = an order exists but the gateway
    has not confirmed; `FAILED` = the gateway reported failure (a retry is a new
    row); `SUCCEEDED` = server-verified paid; `REFUNDED` = money returned.
    Further states (partial refund, cancelled) are added only if a later
    increment proves they are needed (PROJECT.md §41/§47).
  - **Fields:** `booking` (FK, `PROTECT`), `purpose` (`BOOKING` / `EXTENSION`),
    `method` (`ONLINE` / `CASH`), `amount` (Decimal, INR snapshot), `currency`
    (INR, server-set), `status`, `provider_order_id` / `provider_payment_id`
    (Razorpay handles; unique; NULL for cash), `failure_reason`, `paid_at`,
    `created_at`, `updated_at`.
  - **Amount source (server-authoritative, §46):** the initial charge is
    `Booking.base_amount` (D39 revised); an extension charge is the D54 quote.
    The client never supplies the amount.
  - **Money unit:** the database stores **rupees**; the Razorpay adapter
    converts to **paise** at the API boundary (×100), so no stored value changes
    meaning.
  - **Deduplication:** Razorpay's `order_...` / `pay_...` ids are stored unique,
    so a retried webhook or callback matches exactly one row; `confirm_booking`
    stays idempotent (D51). No double-charge, no double-confirm.
  - **Refund metadata is deferred to 5.5** (refund id, refunded amount/time):
    the `REFUNDED` state exists now, but no refund fields are added
    speculatively (§41).
  - **No card data, ever** (D56/§4): the UI is Razorpay-hosted; we store only
    Razorpay ids.

- **Rationale:** a payment that can only exist once per booking would force an
  in-place overwrite on every retry and extension, destroying the audit trail
  the SRS's transaction views will need. Keeping a small state enum avoids
  modelling states we cannot yet justify, while `PENDING/SUCCEEDED/FAILED/
  REFUNDED` already cover every §35 payment edge case.

- **Rejected:** one row per booking; storing refund fields now; a single
  combined money+booking status (breaks the D51 seam); storing the provider
  signature (transient — verify and discard).

- **Consequence:** a new `Payment` table (migration `payments/0001_initial`),
  FK `PROTECT` to `bookings.Booking`. Downstream increments add the serializer,
  views, gateway and receipt on top of this model.

- **Status:** Accepted (2026-10-08).

---

## D58 — Payment gateway interface and adapter selection (accepted 2026-10-09)

D56 fixes *which* provider (Razorpay test mode); D58 fixes the **interface** the
rest of the app codes against, the **selection** mechanism and the **test
strategy** for the gateway. (Pins the §26 contract before 5.3 builds on it, and
resolves the test-strategy open question.)

- **Decision:**
  - **Interface:** `PaymentGateway` with exactly the three PROJECT.md §26 methods
    — `create_payment`, `verify_payment`, `refund_payment`.
  - **Primitives, not models:** methods take plain values (`amount`, `currency`,
    `receipt`, provider order/payment ids, the callback `payload`) and return
    small frozen dataclasses (`PaymentInitiation`, `PaymentVerification`,
    `RefundResult`). No Django model crosses the boundary, so adapters stay thin
    and the service layer (5.3–5.5) owns every database write.
  - **Selection by configuration:** `settings.PAYMENT_GATEWAY` (`mock` default,
    `razorpay` for the sandbox) resolves through `get_payment_gateway()`. The
    default is `mock`, so development and the automated suite need no network and
    no credentials (D7).
  - **Lazy SDK import:** only `RazorpayGateway` imports the `razorpay` package,
    inside `__init__`; importing the module never requires it. A missing SDK or
    missing keys raises `PaymentGatewayError` at construction, never at import.
  - **Signature verification is stdlib:** the Razorpay HMAC-SHA256
    (`order_id|payment_id`) check is a pure `hmac`/`hashlib` helper
    (`verify_razorpay_signature`) unit-tested offline. The **stored** order id —
    never a client-supplied one — is what gets signed.
  - **Money boundary:** amounts cross to Razorpay in **paise** (×100); the
    database keeps rupees (D57).
  - **Test strategy:** `MockGateway` covers the offline suite;
    `RazorpayGateway`'s network calls get opt-in sandbox integration tests.

- **Rationale:** the §26 abstraction exists so the provider is a plug-in. Passing
  primitives keeps adapters testable without a database and keeps the money/state
  logic in one place (the service), where the D51/D53/D54 seams already live.

- **Rejected:** passing the `Payment` model into adapters (couples the provider to
  the ORM and makes mocking heavier); importing the SDK at module load (would
  break the suite wherever the package is absent); one monolithic gateway
  (untestable and violates §26).

- **Consequence:** new `payments/gateway.py` (interface + `MockGateway` +
  `RazorpayGateway` + `get_payment_gateway`); `settings.py` gains
  `PAYMENT_GATEWAY` and the `RAZORPAY_*` keys; `.env.example` gains the template;
  `requirements.txt` gains the `razorpay` SDK when the sandbox path is first
  exercised (deferred — the mock keeps the suite offline). The service layer
  calls only `get_payment_gateway()`.

- **Status:** Accepted (2026-10-09).

---

## D59 — Payment creation surface: `POST /api/payments/` (accepted 2026-10-10)

Open question 1. D57 fixes *what* a `Payment` is and D58 fixes the gateway
interface; D59 fixes how an attempt is **started over HTTP** and what the client
receives back.

- **Decision:**
  - **Endpoint:** `POST /api/payments/` with body `{"booking": <id>}`, matching
    PROJECT.md §22 and the collection style of the other domains. The 5.9
    history read adds `GET` on the same route.
  - **Actor:** the booking's **owner**, `IsConsumer`. Manager walk-in cash is
    5.7; extension charges are 5.6.
  - **Amount/currency are server-side:** `amount = Booking.base_amount`
    (D57/§46) and `currency = "INR"`; any `amount`/`currency` in the body is
    ignored. The write shape accepts only the target booking.
  - **One request = one attempt:** every call writes a new `PENDING` row and
    opens a new provider order (D57's "one row per charge attempt"). Duplicates
    are harmless -- provider ids are unique and 5.4's confirmation is idempotent
    (D51), so at most one can succeed.
  - **Response:** `201` with the payment's read fields plus `client_payload`
    (exactly what the adapter returned for the client to open Razorpay Checkout).
  - **Payable = a live `PENDING_PAYMENT` booking** (`is_hold_live`, D6/D50); a
    lapsed hold or any other state is `BOOKING_NOT_PAYABLE` (409). A booking
    whose initial charge already `SUCCEEDED` is `BOOKING_ALREADY_PAID` (409),
    which also covers the window before 5.4's confirmation runs.
  - **No slot lock here:** starting an attempt changes no booking/slot state, and
    `base_amount` cannot move while `PENDING_PAYMENT` (extensions require
    `CONFIRMED`/`IN_PROGRESS`, D54). Confirmation owns the lock (5.4).
  - **Gateway errors are `PAYMENT_GATEWAY_UNAVAILABLE` (503):** the adapter is
    resolved *before* the row is written, so a pure configuration error writes
    nothing; a provider failure during the call marks the row `FAILED` and is
    surfaced as the same 503.
  - **Receipt string:** `f"{booking.reference}-{payment.id}"` -- unique per
    attempt (the D52 reference plus the row id).
  - **5.2 regression fixed:** `MockGateway`'s id counter is now module-level
    (shared), so repeat attempts mint distinct `order_mock_*` ids and satisfy the
    unique provider-id constraints.

- **Rationale:** the §22 endpoint list already names `/api/payments/`, so
  creation and the later history read share one resource. Keeping the amount
  server-side and the attempt-per-request model preserves D57's audit trail, and
  resolving the adapter before writing keeps a misconfiguration from leaving
  junk rows.

- **Rejected:** a booking-scoped `POST /api/bookings/{id}/pay/` (still needs the
  collection route for history); reusing an outstanding `PENDING` attempt (the
  model stores no client payload, so it would need a rebuild helper); refusing a
  second attempt with 409 (a refresh would hard-fail the user); accepting a
  client amount/currency (§46).

- **Consequence:** new `payments/services.py` (`create_payment_attempt` +
  `PaymentError` subclasses), `serializers.py` (`PaymentCreateSerializer`,
  `PaymentSerializer`), `views.py` (`PaymentCreateView`) and `urls.py`; a new
  `path("api/payments/", ...)`; `MockGateway`'s shared counter; new API tests.
  No migration (no model change).

- **Status:** Accepted (2026-10-10).

---

## D60 — Payment confirmation: return verify + signed webhook, one apply core (accepted 2026-10-10)

D56 fixes the provider and D58 the interface; D59 starts an attempt. D60 closes
the loop: how a paid attempt is **learned, verified and applied** to the booking.
(Resolves open question 1.)

- **Decision:**
  - **Two trusted channels, one core.** (1) **Return verify** —
    `POST /api/payments/{id}/confirm/`, consumer-only and owner-scoped, body
    `{"payload": {...}}` (whatever Checkout's handler gave the browser).
    (2) **Webhook** — `POST /api/payments/webhook/`, public, authenticated by
    the **raw-body signature** (`X-Razorpay-Signature`) alone. Both call
    `services.apply_payment_outcome`, the single place that writes
    `SUCCEEDED`/`FAILED` and calls the D51 `confirm_booking` seam, so the two
    channels cannot drift.
  - **Verify, don't trust (§24/§25).** Only a server-side signature check — the
    **stored** order id is what gets signed, never a client-supplied one — can
    move a booking to `CONFIRMED`.
  - **Idempotent by construction.** Provider ids are unique, a `Payment` is
    terminal once resolved, and `confirm_booking` is already idempotent (D51);
    a duplicate callback or webhook is a no-op.
  - **Captured but not applied.** If the gateway captured the money but the
    booking can no longer be confirmed (lapsed hold, slot taken): the money row
    is committed `SUCCEEDED` and `booking_applied=False`, with
    `failure_reason = "booking_not_confirmable:<CODE>"`. The return path answers
    `409 PAYMENT_CAPTURED_NOT_APPLIED`; the webhook acknowledges `200` so the
    provider does not retry. The owed refund is D61 (5.5); the **automated
    reconciler is deferred post-project** (see
    [`../deferred-features.md`](../deferred-features.md)) because the project
    deliberately has no background workers (D6, §12, §47).
  - **New field.** `Payment.booking_applied` (`BooleanField`, default `False`),
    migration `payments/0002_payment_booking_applied`. It is the exact key the
    deferred reconciler will query, so it is not speculative.
  - **Interface revision (D58).** `PaymentGateway` gains a 4th method,
    `parse_webhook(*, body, headers) -> WebhookEvent | None`; `None` means the
    webhook could not be verified. `verify_razorpay_webhook_signature` is the
    stdlib raw-body HMAC helper. This supersedes D58's "exactly three methods",
    because a webhook's signature scheme and payload shape are provider-specific
    and must stay inside the adapter (§26).
  - **Refusals.** `PAYMENT_NOT_FOUND` (404), `PAYMENT_NOT_CONFIRMABLE` (409),
    `PAYMENT_VERIFICATION_FAILED` (409), `PAYMENT_CAPTURED_NOT_APPLIED` (409),
    `INVALID_WEBHOOK_SIGNATURE` (400), `PAYMENT_GATEWAY_UNAVAILABLE` (503).

- **Rationale:** §26 exists so the application never depends on the provider; a
  webhook's signature and payload *are* provider details, so the adapter owns
  them. Keeping one apply core writes the money/booking ordering once, and the
  money row is committed *before* the booking seam so a booking refusal can
  never roll back captured money — the honest outcome for a real charge.

- **Rejected:** webhook-only (breaks the local demo); an unverified webhook
  (trusting the client); provider parsing in the service (leaks past §26);
  mutating a captured `Payment` to `REFUNDED` (D61 makes refund a ledger event);
  one big transaction around verify+money+booking (would lose captured money);
  encoding the not-applied case as a bare `failure_reason` string with no field
  (stringly-typed and not queryable by the future reconciler).

- **Status:** Accepted (2026-10-10).

---

## D61 — Refund is a ledger event, not a mutation of a captured `Payment` (accepted 2026-10-10)

A captured payment's terminal state is **immutable**. A refund is a new ledger
event: a child `Refund` row (`payment` FK, `amount`, `provider_refund_id`,
`status`, `reason`, timestamps), so "how much of this payment was refunded?" is
a derived sum and the original capture is never rewritten. This **revises D57**
by **removing** the unreachable `REFUNDED` `Payment.Status` value, so a captured
payment only ever becomes `SUCCEEDED`/`FAILED`.

- **Decision:**
  - **Ledger, not mutation.** Each refund is its own `Refund` row; the captured
    `Payment.status` is never edited. The amount owed is a **derived** value
    (`refundable_amount`), never client-supplied (§46), and net of refunds
    already reserved (`PENDING`) or settled (`SUCCEEDED`).
  - **What is owed.** A charge is refundable only when it was **captured but not
    applied** to a booking (D60) — the whole capture — or when its booking was
    **cancelled with a §19 entitlement** (D53) —
    `min(captured, refund_due_amount)`. §19 is all-or-nothing, so each applied
    charge refunds in full.
  - **Trigger — automatic on cancellation.** The cancellation *view* composes
    the domains: after `cancel_booking` (D53) commits, Phase 5's
    `refund_booking` refunds each owed payment. Phase 4's service still moves no
    money (its contract is unchanged). A failure is recorded as a `FAILED`
    `Refund` and never un-cancels the booking; there is no background retry.
  - **Surface — Manager/Admin only.** `POST /api/payments/{id}/refund/` is the
    operational refund/retry tool; a consumer's refund is automatic, so they do
    not call it. It is idempotent: a repeat after a settled (or in-flight)
    refund returns that same row.
  - **Partials — ledger-capable, policy all-or-nothing.** `Refund.amount`
    accepts any positive value (so a future partial policy needs no migration),
    but the 5.5 rule only ever refunds the full owed amount.
  - **Concurrency.** `_reserve_refund` locks the payment row and counts
    `PENDING` refunds, so two concurrent requests cannot reserve the same
    balance twice; only then is the gateway called (mirroring the D59/D60
    ordering).
  - **Refusals.** `PAYMENT_NOT_REFUNDABLE` (409), `PAYMENT_REFUND_FAILED` (502).
  - **Migration.** `payments/0003` = `CreateModel(Refund)` +
    `AlterField(Payment.status)` (choices only; no data change).

- **Rationale:** keeping the capture immutable makes the ledger trustworthy — a
  later reader can always reconstruct exactly what was charged and what was
  given back, which is what "no mutation" (D61) is for. Deriving the owed amount
  server-side from the D53 snapshot keeps the §19 rule in one place.

- **Rejected:** mutating a captured `Payment` to `REFUNDED` (loses history, and
  cannot express partial or multiple refunds); client-supplied refund amounts;
  a background refund sweeper (no workers — D6/§12/§47); a consumer-callable
  refund endpoint (the consumer path is automatic).

- **Status:** Accepted (2026-10-10).

---

## Open questions to decide before coding

These are the Phase 5 decision points (PROJECT.md §9). Each is settled *with
the human* when its increment opens; the agent proposes options and trade-offs
first. Items already resolved are annotated below. They are listed here so the
next session does not have to rediscover them.

1. **Confirmation** — *decided as **D60** (return verify + signed webhook, one
   apply core, captured-but-not-applied policy).*
2. **Refund** — *decided as **D61** (a `Refund` ledger event; automatic on the
   D53 cancellation refund, Manager/Admin retry endpoint, `REFUNDED` removed).*
3. **Extension charge path** — charge the D54 quote, then call `extend_booking`.
4. **Walk-in cash payment** — the manager-recorded cash path (§3.1, §19).
5. **Receipt** — shape, endpoint, and whether it is generated from the payment
   record.
6. **Transaction visibility** — consumer payment history vs manager/admin
   transaction listing (PROJECT.md §22 `/api/payments/`).
7. **Failure/timeout handling** — the §35 cases (payment fails, timeout,
   duplicate callback) and how they map to refusal codes/statuses.

> *Decided since:* the model/states and the amount source (D57); the gateway
> interface, adapter selection and test strategy (D58, revised by D60); the
> creation surface (D59); confirmation and the captured-but-not-applied policy
> (D60); the refund ledger event, its automatic cancellation trigger, the
> Manager/Admin retry surface and the removal of `REFUNDED` (D61).

---
