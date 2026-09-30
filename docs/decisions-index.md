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
