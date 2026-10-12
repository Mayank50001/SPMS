# Decision index

Every agreed decision has a stable ID (`D1`, `D2`, …). Code comments reference
these IDs, so this index is how you find the full entry. The entry itself lives
in the `DECISIONS.md` of the phase that owns the concern.

> Opening a decision entry is a **targeted read**, not the default. Start from
> the current phase's docs.

## Foundation — cross-cutting (phases 0–10)
Full entries: [`foundation/DECISIONS.md`](foundation/DECISIONS.md)

| ID | Title | Implemented in |
|----|-------|----------------|
| D1 | Authentication: JWT via `djangorestframework-simplejwt` | Phase 2 |
| D2 | Slot status is LIVE state only; availability is DERIVED | Phase 3 (reconciled) |
| D3 | Booking concurrency: atomic transaction + row lock + overlap check | Phase 4 |
| D4 | PostgreSQL is mandatory | Phase 0/1 |
| D5 | Time: store UTC, business timezone for reports | Phase 1 |
| D6 | Hold / payment expiry is LAZY-evaluated | Phase 4/5 |
| D7 | Testing: Django's built-in test runner (not pytest) | ongoing |
| D8 | `Booking.user` is nullable (walk-in support) | Phase 4 |
| D9 | `.env` loading uses the Python standard library | Phase 1 |
| D10 | Health endpoint lives in `config`, not a new app | Phase 1 |
| D66 | List endpoints return a paginated envelope (page-number, `?page_size=`); cities and availability opt out | All list reads |

## Phase 2 — Authentication and users
Full entries: [`phase-2-authentication/DECISIONS.md`](phase-2-authentication/DECISIONS.md)

| ID | Title |
|----|-------|
| D11 | Custom User model: email login, single `role`, `is_active` suspension |
| D12 | Password hashing guaranteed by overriding `create()` |
| D13 | Email canonicalised to lower case; uniqueness case-insensitive |
| D14 | Password policy is Django's validator stack, invoked at object level |
| D15 | `role` is never a JWT claim; authorization reads it from the database |
| D16 | Login returns the account profile alongside the token pair |
| D17 | Refresh tokens rotate and are blacklisted; logout is server-side |
| D18 | DRF permissions are deny-by-default |
| D19 | JWT signing key is separate from `SECRET_KEY` |
| D20 | Manager and Administrator accounts are created only by an Administrator |
| D21 | Email login canonicalises the identifier, then matches exactly |
| D22 | Password similarity is checked against `email` and `full_name` |
| D23 | `phone` is optional, non-unique contact info |
| D24 | `role` is mutable by an Administrator; the last Administrator is protected |
| D25 | Consumer profile self-update via `PATCH /api/auth/me/` |
| D26 | Administrator user-management endpoints |
| D27 | Role change / suspension endpoint `PATCH /api/users/{id}/` |
| D28 | `Vehicle`: consumer vehicle registration (Phase 2 close-out) |

## Phase 3 — Parking domain
Full entries: [`phase-3-parking/DECISIONS.md`](phase-3-parking/DECISIONS.md)
(Increments 3.2, 3.3 and 3.4 also record implementation decisions refining
D31/D32/D34/D35/D37/D38 at the end of that file.)

| ID | Title | Status |
|----|-------|--------|
| D29 | `ParkingLot` identity: surrogate id + unique city-numeric code | Accepted |
| D30 | Lot lifecycle ownership | Accepted |
| D31 | `ParkingSlot` identity and numbering | Accepted |
| D32 | Slot types: `TextChoices` | Accepted |
| D33 | Slot state model (revises D2) | Accepted |
| D34 | Pricing granularity | Accepted |
| D35 | Administrator maximum rate (Invariant 4) | Accepted |
| D36 | Manager assignment: single `manager` FK | Accepted |
| D37 | Parking API surface and permissions | Accepted |
| D38 | Lot/slot deactivation and deletion | Accepted |

## Phase 4 — Booking
Full entries: [`phase-4-booking/DECISIONS.md`](phase-4-booking/DECISIONS.md)

| ID | Title | Status |
|----|-------|--------|
| D39 | Booking persistence, relationships and price snapshot (revised in 4.2: stored `base_amount`) | Accepted |
| D40 | Booking state model | Accepted |
| D41 | Conflict window and concurrency | Accepted |
| D42 | Upfront pricing model and fixed-window paradigm (revised) | Accepted |
| D43 | Shared D41 predicates and lazy-expiry evaluation | Accepted |
| D44 | Booking helper module layout and refusal contract | Accepted |
| D45 | Per-slot duration policy + Administrator duration cap (reopens Phase 3 models) | Accepted |
| D46 | Availability query: derived `.../availability/` endpoint and its bookability rules | Accepted |
| D47 | Booking creation contract: actor, status, hold assignment, deferred walk-in reference | Accepted |
| D48 | Booking creation refusals and the HTTP status map | Accepted |
| D49 | Booking creation locking strategy and idempotency deferral | Accepted |
| D50 | Effective `status` for a lapsed hold; read-only expiry (4.5) | Accepted |
| D51 | Confirmation seam: slot-locked, idempotent `PENDING_PAYMENT → CONFIRMED` (4.6) | Accepted |
| D52 | Public booking `reference`: random, unguessable receipt/QR code (4.6) | Accepted |
| D53 | Cancellation: refund cutoff, stored `refund_due_amount`, slot-locked transition (4.7) | Accepted |
| D54 | Extension: consumer quote, whole-window pricing, slot-locked `extend_booking` seam (4.8) | Accepted |
| D55 | Booking history filters, rich detail read and action hints (4.9) | Accepted |

> Increment **4.5** (temporary hold) landed **D50**, increment **4.6**
> (confirmation seam + public `reference`) landed **D51–D52**, increment
> **4.7** (cancellation) landed **D53**, increment **4.8** (extension)
> landed **D54**, and increment **4.9** (booking history / detail) landed
> **D55**; their worksheets are resolved and kept in that file. **Phase 4 is
> complete.**
> This index intentionally lists only *accepted* decisions.

## Phase 5 — Payment
Full entries: [`phase-5-payment/DECISIONS.md`](phase-5-payment/DECISIONS.md)

| ID | Title | Status |
|----|-------|--------|
| D56 | Payment gateway: Razorpay test mode behind the provider-agnostic payment abstraction (revised 2026-10-08 from Stripe) | Accepted |
| D57 | Payment model and states: one row per charge attempt | Accepted |
| D58 | Payment gateway interface and adapter selection (mock + Razorpay, lazy SDK) | Accepted |
| D59 | Payment creation surface: `POST /api/payments/` | Accepted |
| D60 | Payment confirmation: return verify + signed webhook, one apply core; captured-but-not-applied policy (`booking_applied`) | Accepted |
| D61 | Refund is a ledger event (`Refund` row), not a mutation of a captured `Payment`; automatic on cancellation, Manager/Admin retry, `REFUNDED` removed | Accepted (code in 5.5) |
| D62 | Extension charge: reuse `POST /api/payments/` (`purpose=EXTENSION` + `end_time`), store `extension_end_time`, apply via `extend_booking` | Accepted (code in 5.6) |
| D63 | Walk-in booking creation and cash payment deferred to a future addition | Deferred (2026-10-11) |
| D64 | Receipt: per-payment JSON read (`GET /api/payments/{id}/receipt/`), derived from a settled payment | Accepted (2026-10-11; code in 5.8) |
| D65 | Transaction views: one role-scoped `GET /api/payments/` (consumer own / manager assigned lots / admin all), two read shapes, derived refund totals, 4.9-style filters, no pagination | Accepted (2026-10-11; code in 5.9) |

> D56 is decided ahead of coding so the first Phase 5 increment has a concrete
> gateway to build against; it was **revised (Stripe → Razorpay)** on 2026-10-08
> because SPMS is India-scoped and everything is INR. D57 fixes the `Payment`
> model and states; D58 fixes the gateway interface, adapter selection and the
> offline test strategy (revised by D60 to a four-method interface); D59 fixes
> the creation surface; D60 fixes confirmation (return verify + signed webhook,
> one apply core, captured-but-not-applied); D61 makes the refund a ledger event,
> automatic on cancellation with a Manager/Admin retry; D62 is the extension
> charge, D63 defers the walk-in/cash flow, D64 is the per-payment receipt
> read and D65 makes the transaction views one role-scoped `GET /api/payments/`.
> Phase 5's decision points are now complete — see
> [`phase-5-payment/`](phase-5-payment/).

## Phase 6 — Occupancy simulation
Full entries: [`phase-6-occupancy/DECISIONS.md`](phase-6-occupancy/DECISIONS.md)

| ID | Title | Status |
|----|-------|--------|
| D67 | Operator booking reads: one role-scoped `GET /api/bookings/` (consumer own / manager assigned lots / admin all), mirroring D65 | Implemented (2026-10-12; 6.1) |
| D68 | Occupancy model: `OCCUPIED` is a stored physical flag written by an explicit manager action (dedicated `POST .../occupancy/`) and by entry/exit; occupied bays stay bookable for future windows (only an already-started window is blocked) | Implemented (2026-10-13; 6.2, after 6.3) |
| D69 | Entry/exit simulation and the `IN_PROGRESS` / `COMPLETED` lifecycle: Manager check-in/check-out on an assigned lot, stored actual times, occupancy follows | Implemented (2026-10-13; 6.3) |
| D70 | Overstay settlement: `BusinessRule.overstay_multiplier` and the charging surface | **Open** (6.4) |
| D71 | Occupancy board read (per-lot live view) | **Open** (6.5) |
| D72 | Live occupancy-board delivery: polling vs SSE vs WebSockets (Channels/Redis) | **Open** (6.5) |
