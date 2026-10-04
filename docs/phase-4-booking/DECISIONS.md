# Phase 4 decisions — Booking

Status as of **2026-10-05**:

- **Accepted:** D39 (persistence, relationships, snapshot — **revised in 4.2**,
  see below), D40 (state model), D41 (conflict window and concurrency) —
  increment 4.1. D42 (upfront fixed-window model), D43 (shared D41 predicates
  and lazy-expiry evaluation), D44 (helper module and refusal contract), D45
  (per-slot duration policy) — increment 4.2, which is **delivered and
  verified** (137 tests across `apps.parking` + `apps.bookings`).
- **Open:** nothing blocking. Later increments add their own decisions (see
  "Open questions carried to later increments" at the end).

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
  `base_amount` is **stored** (revised in 4.2, below); the amount actually
  charged still lives on Phase 5's `Payment`. Indexes on
  `(slot, start_time, end_time)` and `(user, status)`; check constraints that
  `end_time > start_time`, `billed_hours >= 1`, the plate is non-blank, and
  `base_amount > 0`.

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

- **Revision (4.2, 2026-10-05):** `base_amount` is no longer a derived property;
  it is a stored `Decimal(12, 2)` snapshot computed by
  `services.quote_booking` and written alongside `hourly_rate`. Rationale: a
  booking is a *contract at an agreed price*, so the amount must survive a later
  pricing-rule change exactly as `hourly_rate` and the plate do. Keeping it
  derived would silently rewrite history the moment pricing becomes non-linear
  (tiers, day caps, peak). It is **not** `Payment.amount` — that is Phase 5's
  record of what was actually charged; `base_amount` is the agreed price of the
  booked duration, and the overstay surcharge (Phase 6) is added separately.

- **Status:** Accepted (2026-10-04); revised 2026-10-05 to store `base_amount`
  (4.2).

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

## D42 — Upfront pricing model and fixed-window paradigm (accepted; revised)

- **Clarification (2026-10-04):** The developer's "flexible slots" question does
  **not** introduce a second booking model. SPMS is **upfront /
  pay-at-booking**, with a **fixed window**: `start_time` and `end_time` are both
  known when the booking is created. A pay-as-you-go / open-ended stay (enter,
  pay on exit) is **not** in the project's phases and is explicitly out of scope.
  The earlier revision of this decision, which derived an open-ended model, is
  withdrawn.
- **Decision (confirmed):**
  - Phase 4 is the fixed-window reservation model. Walk-ins are fixed-window too
    (the manager sets an expected end), so there is one billing code path.
  - Billing is by whole hours, part-hours rounded up (§19). The pure clock math
    `hours_between(start, end)` is separated from any policy wrapper so the
    policy can change without touching the arithmetic.
  - Overstay remains measured in hours (§19): the overrun beyond the booked
    `end_time` is billed `hours_between(booked_end, actual_end)` × the overstay
    multiplier × rate, applied at completion (Phase 6).
- **Withdrawn (agent's addition, not the developer's):** global
  `BusinessRule.min_booking_hours` / `max_booking_hours` **as the duration
  policy itself**, and the "billing floor" reading of the minimum. The intended
  feature is the **per-slot duration policy** recorded below. (D45 later
  re-introduces `BusinessRule.max_booking_hours` in a different role — a ceiling
  on the manager's per-slot maximum, not a policy applied to every booking.)
- **Rationale:** keep only the SRS-backed model; do not add speculative
  paradigms (§41, §47).
- **Status:** Accepted; revised 2026-10-04 to remove the derived model and the
  global duration fields.

---

## D45 — Per-slot duration policy (min/max bookable duration) (accepted 2026-10-05)

The "flexible slots" feature: each bay carries a manager-set bookable duration
range. **All five questions are decided.**

- **Decision:**
  - **Q1 — location: A.** `min_booking_hours` / `max_booking_hours` live on
    **each `ParkingSlot`**, set by the lot's Manager (or an Administrator). Bays
    differ: a premium bay near a lift or an EV charger can enforce a short
    maximum while a long-stay bay allows a full day. Because the fields live in
    `apps/parking`, this deliberately reopens Phase 3's slot model — the
    Phase 3 impact is recorded in
    [`../phase-3-parking/DECISIONS.md`](../phase-3-parking/DECISIONS.md) →
    "Post-close change".
  - **Q2 — granularity: A.** Whole hours; stored as positive integers, `>= 1`.
  - **Q3 — out-of-policy: A.** **Both ends reject** — below the minimum is
    `MIN_DURATION_NOT_MET`, above the maximum is `MAX_DURATION_EXCEEDED`. The
    minimum is a true minimum bookable duration, not a billing floor.
  - **Q4 — bound: A.** `BusinessRule.max_booking_hours` caps any slot's
    `max_booking_hours`, exactly as `max_hourly_rate` caps a tariff. This is a
    **different role** from the global fields D42 withdrew: there the global
    field *was* the policy applied to every booking; here it is only a ceiling
    on the manager's per-slot maximum (the duration twin of Invariant 4).
  - **Q5 — defaults: A.** `ParkingSlot` min `1` / max `24`; `BusinessRule` cap
    `72`. Non-null with defaults, so existing rows keep working with **no
    backfill**.
- **Rationale:** the SRS asks for a minimum/maximum bookable duration; per-slot
  is the only placement that expresses "this specific bay has a limit". Whole
  hours match §19 and `billed_hours`; rejecting both ends is the predictable
  API; the cap reuses the Invariant-4 pattern already in the codebase rather than
  inventing a second one.
- **Consequence:** `apps/parking/services.py` grows `save_slot` (slot writes
  check the cap) and `set_business_rules` (one locked singleton write), with
  `SlotDurationAboveMaximumError`/`MAX_DURATION_ABOVE_CAP` and
  `MaxDurationBelowSlotError`/`MAX_DURATION_BELOW_SLOT`. Availability and
  creation consume the policy through `validate_duration` (4.2).
- **Status:** Accepted (2026-10-05).

The settled options, kept for the record: Q1 **A** per-slot (B per
`(lot, slot_type)`, C per lot); Q2 **A** whole hours (B sub-hour minutes);
Q3 **A** reject both ends (B minimum-as-billing-floor); Q4 **A** global cap
(B no cap); Q5 **A** defaults, no backfill.


---

## D43 — Shared D41 predicates and lazy-expiry evaluation (accepted)

- **Decision:**
  - The conflict rule (D41) is encoded **once**, in
    `apps/bookings/services.py`, as `blocking_window_q(start, end, now)` and
    `is_hold_live(booking, now)`. Availability (4.3) and creation (4.4) both
    consume these; neither re-implements the overlap/liveness logic.
  - The predicate is written as a **positive** `Q` (CONFIRMED/IN_PROGRESS, or
    PENDING_PAYMENT with a live/absent hold) rather than `~Q(...)`, so a NULL
    `hold_expires_at` cannot hit SQL three-valued logic and silently stop a
    pending booking from blocking.
  - **Reads do not persist expiry.** Availability filters lapsed holds out with
    `blocking_window_q` and stays side-effect-free; Invariant 6 holds because
    the lapsed hold never blocks.
  - **Only the creation path persists expiry**, via
    `expire_stale_holds(slot=..., now=...)`, inside the slot-locked transaction
    (4.4), where the status must be authoritative anyway.
- **Rationale:** one definition prevents 4.3 and 4.4 from drifting apart;
  avoiding writes on GETs avoids surprising side effects on reads while still
  satisfying D6's "lazy, no scheduler".
- **Consequence:** `expire_stale_holds` sets `updated_at` explicitly (a
  queryset `update()` does not trigger `auto_now`).
- **Status:** Accepted (2026-10-04).

---

## D44 — Booking helper module layout and refusal contract (accepted)

- **Decision:** Booking rules live in a single new `apps/bookings/services.py`
  (matching `accounts/services.py` and `parking/services.py`), not split into
  `pricing.py`/`selectors.py` yet. Refusals are exceptions with a stable `code`
  (`InvalidWindowError`/`INVALID_WINDOW`,
  `MinDurationNotMetError`/`MIN_DURATION_NOT_MET`,
  `MaxDurationExceededError`/`MAX_DURATION_EXCEEDED`,
  `NoTariffError`/`NO_TARIFF`), which the API layer maps to
  `{"error": CODE, "message": ...}` (§33).
- **Rationale:** consistency with the existing domain apps; a module split is
  cheap later if the file grows. Stable codes let the frontend branch without
  parsing prose.
- **Consequence:** `quote_booking` prices only; eligibility (active lot,
  in-service slot, availability) stays in 4.3/4.4.
- **Status:** Accepted (2026-10-04).

---

## Increment 4.2 implementation decisions (accepted 2026-10-05)

These record the implementation-level choices made while delivering the 4.2
helpers; they refine D39/D42/D43/D44/D45, not replace them.

- **D39 revision — `base_amount` stored** — `Booking.base_amount` is a
  `Decimal(12, 2)` field with a `base_amount > 0` check, computed by
  `services.quote_booking` at creation. Migration
  `bookings/0002_booking_base_amount_and_more.py`.
- **D45 — fields and migration** — `ParkingSlot.min_booking_hours` /
  `max_booking_hours` (defaults `1`/`24`, `slot_min_booking_hours_lte_max` check)
  and `BusinessRule.max_booking_hours` (default `72`,
  `business_rule_max_booking_hours_positive` check). Migration
  `parking/0005_businessrule_max_booking_hours_and_more.py`. No backfill; this
  reopens Phase 3's models once (see the Phase 3 note).
- **D45 — cap enforcement** — `parking/services.save_slot` checks a slot's
  effective maximum against the locked singleton (`409 MAX_DURATION_ABOVE_CAP`);
  `set_business_rules` refuses to lower the cap below an existing slot
  (`409 MAX_DURATION_BELOW_SLOT`). `set_max_hourly_rate` is kept as a wrapper for
  existing callers and tests.
- **D44 — refusals** — `MIN_DURATION_NOT_MET` and `MAX_DURATION_EXCEEDED` are
  added alongside `INVALID_WINDOW` and `NO_TARIFF`.
- **Pricing seam (D42)** — `quote_booking` is the single place that turns a
  window into `(billed_hours, hourly_rate, base_amount, slot_type)`. Advanced
  pricing (tiers, day caps, peak/demand) stays deferred with this function as
  the seam — see [`../deferred-features.md`](../deferred-features.md).

---

## Open questions carried to later increments

Each will be surfaced as its own decision when its increment is opened.

| Question | Lands in |
|----------|----------|
| `BusinessRule.hold_minutes` (temporary hold length, §19 default 5) | 4.5 |
| `BusinessRule.cancellation_cutoff_minutes` (§19 default 30) | 4.7 |
| `BusinessRule.overstay_multiplier` (§19 default 1.5) | Phase 6 |
| Confirmation seam in Phase 4 vs deferring to Phase 5's gateway | 4.6 |
| Walk-in public `reference`/`ticket_code` (unguessable bearer key) | 4.4 / 4.6 |
| Availability endpoint shape (`?start=&end=` on slot list vs a separate view) | 4.3 |
| Extension charge seam (Phase 5 payment handoff) | 4.8 |
| Whether `CANCELLED` and `TERMINATED` need distinct refusal messages | 4.7 |
