# Phase 5 decisions — Payment

Status as of **2026-10-08**:

- **Accepted (2026-10-08):** **D56** — the payment gateway is **Stripe in test
  mode**, behind the provider-agnostic payment abstraction. This decision was
  taken *before* coding so the first Phase 5 increment has a concrete gateway to
  build against.
- **Open:** the payment model and states, the create/verify/refund surfaces,
  webhook handling, receipts and the transaction views. Each will be surfaced as
  its own decision when its increment is opened (see "Open questions to decide
  before coding").

> A "Decision" below is the human's, not the agent's. Rationale/Consequence
> record why, so the choice can be defended later.

PROJECT.md's Phase 5 scope is: *Payment model, payment states, payment
creation, payment confirmation, receipt, refund* — with **no real financial
processing** (§4, §26).

---

## D56 — Payment gateway: Stripe test mode behind the abstraction (accepted 2026-10-08)

PROJECT.md §26 requires a **payment abstraction** — a `PaymentGateway` interface
(`create_payment`, `verify_payment`, `refund_payment`) that the application
depends on, so it "should not directly depend on a specific payment provider".
PROJECT.md's Phase 5 list and §4 default that interface's implementation to a
**mock payment gateway**. This decision replaces that default with a real
provider's sandbox.

- **Decision:**
  - **Gateway: B — Stripe test mode.** The concrete `PaymentGateway`
    implementation is a **Stripe test-mode (sandbox) adapter**, using Stripe's
    hosted **test web interface** for the actual payment step (Stripe Checkout
    or Payment Element — the exact surface is settled when the payment-creation
    increment opens). Stripe's test mode simulates success, failure and refund,
    and returns a test transaction id, exactly the behaviours §4 asks a mock to
    simulate.
  - **Abstraction retained.** The provider-agnostic interface of §26 stays the
    boundary the rest of the app talks to. Views/services never import the
    Stripe SDK directly; only the adapter does. Swapping in a different provider
    (or a pure mock) is therefore a small, contained change.
  - **Mock adapter stays for tests.** A lightweight in-memory **`MockGateway`**
    implementing the same interface remains for automated tests, so the suite
    never makes network calls or needs Stripe credentials. The Stripe adapter is
    exercised by **opt-in** integration tests against the sandbox.
  - **Test keys only, secrets never committed.** `STRIPE_SECRET_KEY` /
    `STRIPE_PUBLISHABLE_KEY` (test-mode `sk_test_…` / `pk_test_…`) load from
    `.env` (D9), with placeholders added to `.env.example`. **No live keys.**
  - **No card data touches our servers.** The payment UI is Stripe-hosted
    (Checkout / Elements), so card number, expiry and CVC are entered on
    Stripe's domain. PROJECT.md §4's "never store card number / CVV / UPI PIN /
    banking credentials" is satisfied by construction.
  - **Verification, not trust.** A payment is only treated as successful after
    the backend **verifies** it with Stripe (server-side retrieve against the
    PaymentIntent/Checkout Session), or after a **signature-verified webhook**.
    The client is never the source of truth (PROJECT.md §24/§25).
  - **Idempotency.** Stripe idempotency keys are used for create/refund, and our
    own confirmation seam stays idempotent (D51), so a duplicated webhook or a
    retried callback cannot double-confirm or double-charge.

- **Explicit scope exclusion — "no external tools" does not apply to payments.**
  PROJECT.md §12 ("must not introduce unnecessary infrastructure") and the
  general "no external tools" working rule are **waived for the payment
  gateway**. A sandboxed provider adapter is not "unnecessary infrastructure"
  and not "real financial processing": it moves **no real money**, stores **no
  financial credentials**, and is the §26 abstraction's intended plug-in point.
  This waiver is **scoped to the payment gateway only** — every other external
  tool or new service still needs explicit human approval.

- **Rationale:** The project's §26 abstraction was designed for a real provider
  to sit behind it; a hand-rolled mock proves less (it cannot demonstrate a
  genuine redirect/confirm/refund lifecycle) and would have to be discarded or
  duplicated once the Stripe adapter exists. Stripe's test mode is industry
  standard for demonstrating a payment flow safely, its hosted test UI keeps
  card data off our systems, and the retained abstraction means the academic
  "don't couple to a provider" requirement is still met. Keeping the mock for
  tests preserves a fast, offline, deterministic suite (D7).

- **Rejected:** a hand-rolled mock as the *only* gateway (less realistic, no real
  redirect/webhook round trip); the Stripe SDK imported directly into
  services/views (breaks §26's abstraction); live-mode keys or real charges
  (out of scope, §4); trusting a client-supplied "paid" flag (breaks §24/§25);
  letting automated tests hit the network (slow, flaky, needs secrets).

- **Consequence:** the payment gateway slice introduces a **network boundary**
  into an otherwise offline backend. `requirements.txt` will gain the `stripe`
  SDK when 5.2 lands; `.env.example` gains the two test-key placeholders;
  `settings.py` gains a thin Stripe configuration (test keys, webhook signing
  secret) read through the stdlib loader. The `payments` app gains a
  `gateway.py` (the interface + `MockGateway` + `StripeGateway`) and the adapter
  is chosen by settings. Everything downstream still calls only the interface.

- **Status:** Accepted (2026-10-08).

---

## Open questions to decide before coding

These are **not decided yet**. Each is a decision point (PROJECT.md §9) that
must be settled *with the human* when its increment opens; the agent proposes
options and trade-offs first. They are listed here so the next session does not
have to rediscover them.

1. **Payment model shape** — fields, the `Booking` link, amount/currency, the
   provider's transaction id / client secret storage, timestamps.
2. **Payment states** — the enum (e.g. `PENDING`, `SUCCEEDED`, `FAILED`,
   `REFUNDED`) and how it relates to `Booking.status`.
3. **Payment creation surface** — endpoint shape, who may initiate, and whether
   the response returns a Stripe Checkout URL / PaymentIntent client secret.
4. **Confirmation** — synchronous verify on return **and** the webhook; webhook
   route, signature verification, and how it calls `confirm_booking` (D51).
5. **Amount source** — the `Booking.base_amount` snapshot (D39 revised) for the
   initial charge; the extension quote (D54) for an extension charge.
6. **Refund** — how `Booking.refund_due_amount` (D53) drives the Stripe refund,
   who triggers it, and how partial/zero refunds are recorded.
7. **Extension charge path** — charge the D54 quote, then call `extend_booking`.
8. **Walk-in cash payment** — the manager-recorded cash path (§3.1, §19).
9. **Receipt** — shape, endpoint, and whether it is generated from the payment
   record.
10. **Transaction visibility** — consumer payment history vs manager/admin
    transaction listing (PROJECT.md §22 `/api/payments/`).
11. **Test strategy** — which behaviours use `MockGateway` in the automated
    suite and which get opt-in Stripe-sandbox integration tests.
12. **Failure/timeout handling** — the §35 cases (payment fails, timeout,
    duplicate callback) and how they map to refusal codes/statuses.

---
