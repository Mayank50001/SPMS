# Progress — Phase 5 (Payment) 🔵 NEXT

> **Scope (PROJECT.md Phase 5):** the payment domain — the `Payment` model,
> payment states, **payment creation**, **payment confirmation**, **receipt** and
> **refund**. No real financial processing (§4). The concrete gateway is
> **Razorpay in test mode**, behind the provider-agnostic abstraction of §26 —
> decisions **D56** (revised), **D58** and **D59** in
> [`DECISIONS.md`](DECISIONS.md).
> Working conventions and the reading protocol: [`../README.md`](../README.md).
> Phase 4 context (the seams Phase 5 calls):
> [`../phase-4-booking/PROGRESS.md`](../phase-4-booking/PROGRESS.md).

Last updated: **2026-10-11** · **5.1–5.6 are delivered; batch B (5.7–5.9) is next.**
**D56** (revised: Razorpay test mode behind the payment abstraction),
**D57** (the `Payment` model and states), **D58** (the gateway interface,
adapter selection and offline test strategy; **revised by D60** to a four-method
interface), **D59** (the creation surface), **D60** (confirmation: return
verify + signed webhook, one apply core, captured-but-not-applied policy),
**D61** (refund is a ledger event, automatic on cancellation, Manager/Admin
retry, `REFUNDED` removed) and **D62** (extension charge: reuse
`POST /api/payments/` with `purpose=EXTENSION` + `end_time`, store
`extension_end_time`, apply via `extend_booking`) are accepted. Everything else
in [`DECISIONS.md`](DECISIONS.md) → "Open questions to decide before coding" is
still open and must be settled with the human as each increment opens.

---

## Start here (fresh session)

1. [`../README.md`](../README.md) — conventions + reading protocol.
2. This file — the scope, the draft increment plan, and what is next.
3. [`DECISIONS.md`](DECISIONS.md) — **D56** (revised), **D57**, **D58** and
   **D59** (accepted), plus the open questions to decide before each increment.
4. Phase 4's seams, only when a task calls them:
   [`../phase-4-booking/DECISIONS.md`](../phase-4-booking/DECISIONS.md) —
   **D51** (`confirm_booking`), **D53** (`refund_due_amount` /
   `cancel_booking`), **D54** (`quote_extension` / `extend_booking`) and
   **D39 revised** (`base_amount`).

**Next session starts here:** **batch B — 5.7 + 5.8 + 5.9** (walk-in cash, receipt,
transaction views). A session delivers several progressive increments of the same
component (see the batching rule in [`../README.md`](../README.md)). Each
increment still settles its open question and records its own `D<n>` before its
code:

- **5.7 — walk-in cash payment** (open question 4): a Manager records cash against
  a walk-in booking; no gateway is involved.
- **5.8 — receipt** (open question 5): the receipt shape and endpoint.
- **5.9 — transaction views** (open question 6): consumer payment history and a
  manager/admin transaction listing on `GET /api/payments/` (D59 reserved the
  route for this).

Do **not** start Phase 6.

---

## Increment plan

> **Draft — confirm at phase open.** The split follows Phase 4's pattern: a
> coherent feature per increment, decisions surfaced before each. It may be
> re-cut as the payment surfaces are decided. From 2026-10-10 the remaining
> increments are **batched** (5.1–5.6 delivered; batch B: 5.7–5.9) because they
> are progressive stages of the same component — see the batching rule in
> [`../README.md`](../README.md).

| # | Increment | Status |
|---|-----------|--------|
| 5.1 | `Payment` model + payment states + migration | ✅ Done |
| 5.2 | Gateway abstraction + `RazorpayGateway` (test mode) + `MockGateway` | ✅ Done |
| 5.3 | Payment creation for a `PENDING_PAYMENT` booking (Razorpay Order / hosted Checkout) | ✅ Done |
| 5.4 | Payment confirmation (server verify + signed webhook → `confirm_booking`) | ✅ Done |
| 5.5 | Refund (drive it from `refund_due_amount`; `POST /api/payments/{id}/refund/`) | ✅ Done |
| 5.6 | Extension charge (charge the D54 quote, store the target end time → `extend_booking`) | ✅ Done |
| 5.7 | Walk-in cash payment recording (Manager) | ⚪ (batch B) |
| 5.8 | Receipt | ⚪ (batch B) |
| 5.9 | Payment history / transaction views (consumer, manager/admin) | ⚪ (batch B) |

### Delivered so far

- **5.1** — `apps/payments/models.py` (`Payment`, D57) + migration
  `payments/0001_initial`.
- **5.2** — `apps/payments/gateway.py` (interface, `MockGateway`,
  `RazorpayGateway`, `get_payment_gateway`, `verify_razorpay_signature`);
  `settings.py` gains `PAYMENT_GATEWAY` / `RAZORPAY_*`; `.env.example` gains the
  template; `apps/payments/tests.py` covers the model and the offline gateway
  path. The `razorpay` SDK is **not installed / not pinned yet** — it is only
  needed for the sandbox path, and the mock keeps the suite offline (D58).
- **5.3** — `apps/payments/services.py` (`create_payment_attempt` +
  `PaymentError` subclasses), `serializers.py` (`PaymentCreateSerializer`,
  `PaymentSerializer`), `views.py` (`PaymentCreateView`) and `urls.py`; route
  `POST /api/payments/` wired in `config/urls.py`; `MockGateway`'s id counter is
  now shared so repeat attempts get distinct order ids (D59). API tests added.
  **No migration** (no model change).
- **5.4** — confirmation (D60): the shared `apply_payment_outcome` core, the
  return-verify route `POST /api/payments/{id}/confirm/`, the public
  signature-verified webhook `POST /api/payments/webhook/`, the 4th gateway
  method `parse_webhook` (+ `verify_razorpay_webhook_signature`), and
  `Payment.booking_applied` (migration `payments/0002_payment_booking_applied`).
  Captured-but-not-applied is **recorded, not dropped**; the automated
  reconciler is deferred post-project. API + gateway tests added.
- **5.5** — refund (D61): the `Refund` ledger model + migration
  `payments/0003_refund_alter_payment_status` (also removes the unreachable
  `Payment.Status.REFUNDED`); `refundable_amount` / `_reserve_refund` /
  `refund_payment` / `refund_booking` in `services.py`; the Manager/Admin
  `POST /api/payments/{id}/refund/` (`PaymentRefundView`, `RefundSerializer`);
  the automatic refund wired into `BookingCancelView` after `cancel_booking`.
  The captured `Payment.status` is **never mutated**; a failed refund is a
  `FAILED` row, retriable. Ledger-capable for partials; the business rule stays
  all-or-nothing. API + model + auto-refund tests added.
- **5.6** — extension charge (D62): `Payment.extension_end_time` (migration
  `payments/0004_payment_extension_end_time` + a purpose/nulling
  `CheckConstraint`); `create_payment_attempt` gained `purpose`/`end_time`, prices
  an extension with the D54 `quote_extension`, refuses a duplicate paid extension
  (`EXTENSION_ALREADY_PAID`) and stores the target end time;
  `apply_payment_outcome` now branches to `extend_booking` for an `EXTENSION`
  charge, keeping the captured-but-not-applied policy for a taken window;
  `confirm_payment_attempt` accepts an online extension as well as a booking
  charge; `PaymentCreateSerializer` gained `purpose`/`end_time`; `views.py` maps
  the extension refusal codes. No new route. API tests added.

---

## Decisions already recorded

- **D56 (accepted 2026-10-08; revised 2026-10-08)** — **Razorpay test mode** is
  the concrete gateway (revised from Stripe, because SPMS is India-scoped and
  everything is INR), behind the §26 `PaymentGateway` abstraction; a
  `MockGateway` stays for the automated suite; test keys only, in `.env`; no
  card data on our servers; the §12 / "no external tools" restriction is
  **waived for the payment gateway**. See [`DECISIONS.md`](DECISIONS.md).
- **D57 (accepted 2026-10-08)** — one `Payment` row per charge attempt (not one
  per booking); a small `PENDING`/`SUCCEEDED`/`FAILED`/`REFUNDED` state enum; the
  `Payment` money lifecycle is kept separate from `Booking.status` and drives it
  only through the D51 `confirm_booking` seam. See [`DECISIONS.md`](DECISIONS.md).
- **D58 (accepted 2026-10-09)** — the `PaymentGateway` interface (three §26
  methods, primitives in/out), adapter selection through
  `settings.PAYMENT_GATEWAY` via `get_payment_gateway()`, a lazy SDK import so
  the suite needs no package or keys, and the stdlib `verify_razorpay_signature`
  helper. `MockGateway` is the offline default. See [`DECISIONS.md`](DECISIONS.md).
- **D59 (accepted 2026-10-10)** — the creation surface: `POST /api/payments/`
  (`{"booking": <id>}`), consumer-only, `amount = Booking.base_amount`
  server-side, one `PENDING` attempt per request, `201` with the payment plus
  `client_payload`; refusals `BOOKING_NOT_PAYABLE` / `BOOKING_ALREADY_PAID`
  (409), `BOOKING_NOT_FOUND` (404), `PAYMENT_GATEWAY_UNAVAILABLE` (503). See
  [`DECISIONS.md`](DECISIONS.md).
- **D60 (accepted 2026-10-10)** — confirmation: server-verified return callback
  **and** a signature-verified webhook, both funnelling through one apply core
  into `confirm_booking` (D51); `Payment.booking_applied` records a
  captured-but-not-applied charge instead of dropping it; D58's gateway
  interface is revised to four methods (`parse_webhook`). See
  [`DECISIONS.md`](DECISIONS.md).
- **D61 (accepted 2026-10-10)** — a refund is a **ledger event** (a child
  `Refund` row), never a mutation of a captured `Payment`; revises D57 by
  removing the `REFUNDED` state. Triggered automatically on the D53
  cancellation refund, with a Manager/Admin `POST /api/payments/{id}/refund/`
  retry; ledger-capable for partials but the policy stays all-or-nothing. See
  [`DECISIONS.md`](DECISIONS.md).
- **D62 (accepted 2026-10-11)** — the **extension charge** reuses
  `POST /api/payments/` (body gains `purpose=EXTENSION` + `end_time`), stores the
  target `extension_end_time` on the payment row (server-side, never supplied at
  confirm time, §46) and applies it by calling the D54 `extend_booking` seam on
  confirmation; amount is the D54 incremental quote. See
  [`DECISIONS.md`](DECISIONS.md).

---

## Dependencies on earlier phases

Read these **only** when a Phase 5 task touches them.

| Decision / artefact | Why Phase 5 needs it |
|---------------------|----------------------|
| **D39 (revised in 4.2)** | `Booking.base_amount` is the agreed price snapshot — the amount a payment charges. |
| **D51** | `services.confirm_booking` is the seam a successful payment calls (`PENDING_PAYMENT → CONFIRMED`). It locks the slot and is idempotent. |
| **D53** | `Booking.refund_due_amount` is the stored refund the gateway pays on cancellation; `cancel_booking` is the consumer path. |
| **D53 (Q3)** | `BusinessRule.cancellation_cutoff_minutes` fixes the refund rule the gateway merely executes. |
| **D54** | `quote_extension` prices an extension; `extend_booking` is the seam the gateway calls after charging it. |
| **D6** | Holds expire lazily; a payment callback after the §19 hold lapses must be refused (`BOOKING_NOT_CONFIRMABLE`). |
| **D4 / D5** | PostgreSQL and UTC storage; provider timestamps are normalised to UTC. |
| **D7** | Django's test runner; tests must stay offline, hence the `MockGateway`. |
| **D18** | Deny-by-default DRF permissions; the payment endpoints opt in explicitly. |
| **PROJECT.md §22** | The starting endpoint list: `/api/payments/`, `/api/payments/{id}/refund/`. |
| **PROJECT.md §33** | The `{"error": "CODE", "message": ...}` refusal shape. |

---

## Guardrails for this phase

- **No real money, ever** — test mode only; no live keys; no card/CVV/PIN
  storage (§4).
- **Never trust the client's "paid"** — only a server-side Razorpay signature
  verify or a signature-verified webhook confirms a booking (§24/§25).
- **Don't bypass the abstraction** — only the gateway adapter imports the
  Razorpay SDK; services and views call the interface (§26).
- **One decision per increment** — the open questions in
  [`DECISIONS.md`](DECISIONS.md) are surfaced and answered before coding, each
  recorded as its own `D<n>`. Increments may now be **batched** within this phase
  (progressive stages of the same component); each still gets its decision first.
- **Small, scoped commits** in `feat(domain): ...` style (PROJECT.md §43).
- **Migrations** — state model change → expected DB change → data implications
  before generating one (§42).

---
