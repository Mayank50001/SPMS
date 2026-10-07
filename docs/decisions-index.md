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

> Increment **4.5** (temporary hold) landed **D50**, increment **4.6**
> (confirmation seam + public `reference`) landed **D51–D52**, increment
> **4.7** (cancellation) landed **D53**, and increment **4.8** (extension)
> landed **D54**; their worksheets are resolved and kept in that file.
> This index intentionally lists only *accepted* decisions.
