# Phase 5 decisions — Payment

Status as of **2026-10-09**:

- **Accepted (2026-10-08; revised 2026-10-08):** **D56** — the payment gateway
  is **Razorpay in test mode**, behind the provider-agnostic payment abstraction.
  Revised from Stripe to Razorpay: SPMS is India-scoped and every amount is INR.
- **Accepted (2026-10-08):** **D57** — the `Payment` model shape and states:
  one row per charge attempt, a small state enum, and a clean separation from
  `Booking.status`.
- **Accepted (2026-10-09):** **D58** — the `PaymentGateway` interface (three
  methods, primitives in/out), adapter selection by settings, and the offline
  `MockGateway` / lazy-SDK test strategy.
- **Open:** the create/verify/refund surfaces, webhook handling, receipts and
  the transaction views. Each will be surfaced as its own decision when its
  increment is opened (see "Open questions to decide before coding").

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

## Open questions to decide before coding

These are **not decided yet**. Each is a decision point (PROJECT.md §9) that
must be settled *with the human* when its increment opens; the agent proposes
options and trade-offs first. They are listed here so the next session does not
have to rediscover them.

1. **Payment creation surface** — endpoint shape, who may initiate, and whether
   the response returns a Razorpay order handle for the client to open Checkout.
2. **Confirmation** — synchronous verify on return **and** the webhook; webhook
   route, signature verification, and how it calls `confirm_booking` (D51).
3. **Refund** — how `Booking.refund_due_amount` (D53) drives the Razorpay refund,
   who triggers it, and how partial/zero refunds are recorded.
4. **Extension charge path** — charge the D54 quote, then call `extend_booking`.
5. **Walk-in cash payment** — the manager-recorded cash path (§3.1, §19).
6. **Receipt** — shape, endpoint, and whether it is generated from the payment
   record.
7. **Transaction visibility** — consumer payment history vs manager/admin
   transaction listing (PROJECT.md §22 `/api/payments/`).
8. **Failure/timeout handling** — the §35 cases (payment fails, timeout,
   duplicate callback) and how they map to refusal codes/statuses.

> *Decided since:* the model/states and the amount source (D57); the gateway
> interface, adapter selection and test strategy (D58).

---
