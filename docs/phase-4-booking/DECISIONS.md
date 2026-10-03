# Phase 4 decisions — Booking

Status as of **2026-10-04**:

- **Accepted:** D39 (persistence, relationships, snapshot), D40 (state model),
  D41 (conflict window and concurrency). These are increment 4.1's decisions.
- **Open:** none blocking increment 4.1. Later increments will add their own
  decisions (see "Open questions carried to later increments" at the end).

> A "Decision" below is the human's, not the agent's. Rationale/Consequence
> record why, so the choice can be defended later.

This phase inherits (does not re-decide) the following cross-cutting decisions:

- **D2 (revised by D33)** — `ParkingSlot.status` stores physical/operational
  state only; `RESERVED`/`HELD` are derived from bookings.
- **D3** — booking concurrency uses an atomic transaction + row lock + overlap
  check (confirmed here as D41).
- **D5** — timestamps are stored UTC; report day-bucketing uses the business tz.
- **D6** — holds/pending payments expire lazily; no scheduler.
- **D8** — `Booking.user` is nullable for walk-ins.
- **D18** — DRF permissions are deny-by-default; reads opt out explicitly.

---

## D39 — Booking persistence, relationships and price snapshot (accepted)

- **Decision:** A `Booking` stores:
  - `user` — nullable, `SET_NULL` (D8; walk-ins have no account).
  - `created_by` — nullable, `SET_NULL` (D36; the acting account: the consumer
    or a manager creating a walk-in).
  - `vehicle` — nullable, `SET_NULL`; plus an **authoritative `vehicle_plate`
    snapshot** (V6/V7). The plate is stored for every booking; the FK is only a
    convenience link.
  - `slot` — `PROTECT` (a booking must never be orphaned).
  - `slot_type` — a **snapshot** of `slot.slot_type`.
  - `start_time` / `end_time` — UTC (D5).
  - `billed_hours` — whole hours, part-hours rounded up (PROJECT.md §19).
  - `hourly_rate` — `Decimal(max_digits=8, decimal_places=2)`, INR, snapshot.
  - `hold_expires_at`, `cancelled_at`, `cancelled_by` (lifecycle bookkeeping).
  - `created_at` / `updated_at`.

  `lot` is **derived** via `slot.lot`, not stored (single source of truth).
  `base_amount` is **derived** (`hourly_rate * billed_hours`), not stored; the
  amount actually charged will live on Phase 5's `Payment`. Indexes on
  `(slot, start_time, end_time)` and `(user, status)`; check constraints that
  `end_time > start_time`, `billed_hours >= 1`, and the plate is non-blank.

- **Rationale:** A booking is a *contract at an agreed price*. Snapshotting
  `hourly_rate`, `slot_type`, `billed_hours` and `vehicle_plate` means a later
  tariff edit, slot-type change, or vehicle edit/removal cannot retroactively
  change what an existing booking cost or which plate it was for — essential for
  payments (Phase 5), occupancy (Phase 6) and reports (Phase 8). `PROTECT` on
  the slot keeps history from being orphaned even if a slot is deleted outside
  the API (D38 already forbids that path). `SET_NULL` on `user`/`vehicle` lets
  accounts and vehicles be removed without erasing history, because the
  snapshots carry what is actually needed.

- **Consequence:** **V6 (vehicle delete) is resolved**: a vehicle referenced by
  a booking may be deleted; the booking keeps `vehicle_plate` and the FK becomes
  `null`. Walk-ins (V7) are representable with `user=null`, `vehicle=null` and a
  free-text `vehicle_plate`.

- **Status:** Accepted (2026-10-04).

---

## D40 — Booking state model (accepted)

- **Decision:** `Booking.status` uses the full PROJECT.md §17 set:

  ```text
  PENDING_PAYMENT, CONFIRMED, IN_PROGRESS, COMPLETED, CANCELLED, EXPIRED, TERMINATED
  ```

  `NO_SHOW` is deliberately **not** added. The **blocking** states — those that
  occupy the slot's window — are
  `BLOCKING_STATUSES = (PENDING_PAYMENT, CONFIRMED, IN_PROGRESS)`. The proposed
  transitions are:

  ```text
  PENDING_PAYMENT ──payment/cash──> CONFIRMED
  PENDING_PAYMENT ──hold lapse────> EXPIRED
  PENDING_PAYMENT ──owner─────────> CANCELLED
  CONFIRMED       ──entry─────────> IN_PROGRESS
  CONFIRMED       ──owner─────────> CANCELLED
  CONFIRMED       ──manager/admin─> TERMINATED
  IN_PROGRESS     ──exit──────────> COMPLETED
  IN_PROGRESS     ──manager/admin─> TERMINATED
  ```

- **Rationale:** This is exactly §17's machine. `IN_PROGRESS` and `COMPLETED`
  are **defined** here because the enum must be complete before bookings can be
  created, but they are **written** by Phase 6 occupancy actions (PROJECT.md §28
  boundary) — the same split Phase 3 used for `OCCUPIED` (D33). Adding `NO_SHOW`
  later is a migration, so it is not added speculatively (§41).

- **Consequence:** State transitions are validated in the **service layer** from
  their own increments (creation 4.4, confirmation 4.6, cancellation 4.7,
  extension 4.8, completion Phase 6), never by the model. A `PENDING_PAYMENT`
  whose hold has lapsed is treated as `EXPIRED` **lazily** at read/query time
  (D6/D41), not by a background job.

- **Status:** Accepted (2026-10-04).

---

## D41 — Conflict window and concurrency (accepted)

- **Decision:**
  - The busy window is the **half-open interval** `[start_time, end_time)`.
    Two bookings conflict iff
    `existing.start_time < new.end_time AND existing.end_time > new.start_time`.
    Adjacent windows (10–11 and 11–12) therefore do **not** conflict.
  - A window is blocked by an existing booking whose status is in
    `BLOCKING_STATUSES`, **except** a `PENDING_PAYMENT` whose `hold_expires_at`
    has already lapsed — that one is treated as expired (D6) and does not block.
  - Enforcement is **D3's mechanism**: `transaction.atomic()` +
    `select_for_update()` on the slot row + an overlap re-check inside the
    transaction, before insert.
  - **No** PostgreSQL `EXCLUDE` range constraint is added in this phase.

- **Rationale:** Half-open intervals are the standard way to let one booking end
  exactly when the next begins without a spurious conflict. The row lock is
  scoped to a single slot, so only same-slot contenders queue — for the length
  of a re-check plus an insert (milliseconds), with no payment I/O inside the
  transaction. An `EXCLUDE` constraint would reject the loser without queueing
  (better for very hot rows), but PostgreSQL cannot encode **lazy hold expiry**
  in a static constraint, so it could not guarantee Invariant 1 on its own; a
  constraint that looks like a backstop but is not would be false assurance.

- **Rejected:** Redis/Celery-based queueing of booking writes. It moves waiting
  out of the request path but adds a broker, a worker tier and delivery
  semantics — explicitly out of scope (§12, §47). It is the right answer only
  when contention genuinely exceeds what bounded row locks can serve.

- **Consequence:** `lock_timeout` (fail fast with a conflict-shaped `409`) and
  an idempotency key for booking creation are recorded as **Phase 10 hardening
  candidates**, not built now.

- **Status:** Accepted (2026-10-04).

---

## Open questions carried to later increments

These are deliberately **not** decided in 4.1; each will be surfaced as its own
decision when its increment is opened.

| Question | Lands in |
|----------|----------|
| `BusinessRule.max_booking_hours` (cap on a single booking's duration) | 4.2 |
| `BusinessRule.hold_minutes` (temporary hold length, §19 default 5) | 4.5 |
| `BusinessRule.cancellation_cutoff_minutes` (§19 default 30) | 4.7 |
| `BusinessRule.overstay_multiplier` (§19 default 1.5) | Phase 6 / 4.2 helper |
| Confirmation seam in Phase 4 vs deferring to Phase 5's gateway | 4.6 |
| Walk-in public `reference`/`ticket_code` (unguessable bearer key) | 4.4 / 4.6 |
| Availability endpoint shape (`?start=&end=` on slot list vs a separate view) | 4.3 |
| Extension charge seam (Phase 5 payment handoff) | 4.8 |
| Whether `CANCELLED` and `TERMINATED` need distinct refusal messages | 4.7 |
