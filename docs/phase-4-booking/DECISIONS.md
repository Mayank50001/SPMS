# Phase 4 decisions — Booking

Status as of **2026-10-06**:

- **Accepted:** D39 (persistence, relationships, snapshot — **revised in 4.2**,
  see below), D40 (state model), D41 (conflict window and concurrency) —
  increment 4.1. D42 (upfront fixed-window model), D43 (shared D41 predicates
  and lazy-expiry evaluation), D44 (helper module and refusal contract), D45
  (per-slot duration policy) — increment 4.2. D46 (availability query shape and
  semantics) — increment 4.3, also **delivered** (availability is a read-only,
  derived query; the phase's `apps.parking` + `apps.bookings` suite covers the
  conflict, liveness, out-of-service and duration-policy cases).
- **Accepted (4.4, 2026-10-06):** D47 (creation contract: actor, status, hold
  assignment, deferred walk-in reference), D48 (creation refusals and the HTTP
  status map), D49 (creation locking strategy and idempotency deferral) —
  increment 4.4, **delivered** (creation is the first write path; the
  `apps.bookings` suite includes a two-thread concurrency test proving
  Invariant 1 under the slot lock).
- **Accepted (4.5, 2026-10-06):** D50 (effective-status reads for a lapsed hold;
  no early release; no extra expiry writer) — increment 4.5, **delivered** (the
  read side now reports a lapsed `PENDING_PAYMENT` as `EXPIRED` with no write;
  the stored status is unchanged).
- **Accepted (4.6, 2026-10-06):** D51 (the confirmation seam: an internal
  `PENDING_PAYMENT → CONFIRMED` transition, slot-locked and guarded), D52 (the
  public, unguessable booking `reference`) — increment 4.6, **delivered** (a
  Phase 5 gateway can confirm a live booking; every booking now carries a
  receipts/QR code).
- **Open:** nothing blocking 4.1–4.6. Increment **4.7** (cancellation) will add
  its own decisions (see "Open questions carried to later increments").

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

## D46 — Availability query: shape and semantics (accepted 2026-10-05)

The time-window availability read (increment 4.3). All questions decided.

- **Decision:**
  - **Endpoint: B.** `GET /api/parking-lots/{lot}/availability/?start=&end=` —
    a dedicated, **derived** sub-resource (D2/D33), not a filter on the
    catalogue collection. Both `start` and `end` are required, offset-aware
    ISO-8601 instants; the project stores UTC (D5). The read is public
    (`AllowAny`), consistent with the rest of the parking catalogue (D37). The
    lot follows the existing nested-read scoping (`LotScopedMixin`), so an
    inactive lot is a `404` for a consumer while its Manager may still address
    it (D38).
  - **"Available" means:** the slot is not `OUT_OF_SERVICE` (Invariant 5, §19)
    **and** the requested window fits the slot's D45 duration policy
    (`min_booking_hours <= billed_hours <= max_booking_hours`) **and** no
    booking blocks the window per `blocking_window_q` (D41).
  - **`OCCUPIED` is not excluded.** It is a time-unbounded physical state
    written by Phase 6 (§28); availability is about a *future window*, so the
    occupancy policy is deferred to Phase 6 rather than guessed here.
  - **Response shape:** the bookable subset, serialised with the existing
    `ParkingSlotSerializer` — the client's `/slots/` parsing is unchanged.
  - **Refusals:** a window with `end <= start` is `400 INVALID_WINDOW` (the same
    rule creation enforces); missing/unparseable params are field-shaped `400`s.
  - **Read-only (D43):** the query never persists expiry. A lapsed
    `PENDING_PAYMENT` hold is excluded by the predicate, not by a write, so
    Invariant 6 holds without a GET mutating rows.
- **Placement:** the selector `available_slots(*, lot, start_time, end_time,
  now=None)` lives in `apps/bookings/services.py` (the rule layer, D44); the view
  lives in `apps/parking/views.py` because it is a lot-scoped read reusing
  `LotScopedMixin`. `apps.bookings` already imports `apps.parking.models`, so the
  view → bookings-service call respects the established dependency direction at
  the service layer.
- **Rejected:** filtering the existing `GET .../slots/` collection with
  `?start=&end=` (Option A). It overloads the management listing — which must
  keep returning *all* slots including out-of-service ones — with a
  parameter-dependent consumer shape, and gives no natural home for later
  availability-specific fields.
- **Consequence:** no migration (read-only; no schema change). The correlated
  `EXISTS` is backed by `booking_slot_window_idx` (`(slot, start_time,
  end_time)`); serialisation uses `select_related("lot")`. Advanced availability
  (per-slot reasons, pagination, pricing in the response) stays additive.
- **Status:** Accepted (2026-10-05).

---

## D47 — Booking creation contract: actor, status, hold and reference (accepted 2026-10-06)

Increment 4.4 is the first **write** path. This entry settles the worksheet's
Q1–Q4; the options as originally presented are kept below for the record.

- **Decision:**
  - **Q1 — actor: A.** `POST /api/bookings/` is **Consumer self-booking only**
    (`IsConsumer`). The acting account is attached as
    `user = created_by = request.user`. Manager walk-ins are their own later
    increment; D8 already keeps the model ready (`user`/`vehicle` nullable,
    free-text `vehicle_plate`).
  - **Q2 — status: A.** A successful create always writes `PENDING_PAYMENT`.
    Confirmation (4.6, wired to Phase 5's gateway) moves it to `CONFIRMED`;
    nothing in 4.4 marks a booking paid.
  - **Q3 — hold: A.** 4.4 assigns the hold:
    `hold_expires_at = now + BusinessRule.hold_minutes` (§19 default **5**), and
    introduces `BusinessRule.hold_minutes` on the existing singleton (positive
    check, migration `parking/0006_businessrule_hold_minutes_and_more.py`). The
    field is exposed on the read/update serializers and written by
    `set_business_rules`. A `PENDING_PAYMENT` with no deadline never expires
    (D43), so the hold must be assigned with the booking; the 4.5 increment then
    owns the remaining expiry semantics.
  - **Q4 — reference: A (defer).** No public `reference`/`ticket_code` column in
    4.4. The walk-in/receipt identifier's shape is a function of its
    presentation (QR, printed ticket) and is decided in **4.6**. The surrogate
    `id` is the internal key and is not exposed as a bearer key.
  - **`vehicle` is required on the create request** (implementation choice made
    while coding 4.4). The booking's authoritative plate is the `vehicle_plate`
    snapshot copied from the registered vehicle (D39/V6); requiring the FK keeps
    that snapshot non-blank without accepting free text on the consumer path.
    Walk-in free-text plates arrive with the walk-in flow.

- **Rationale:** A is the smallest coherent write path and keeps 4.4 reviewable;
  it matches §36's ordering (creation first, walk-in flows later). Assigning the
  hold in 4.4 avoids the foot-gun of a pending booking that reserves its slot
  forever (a `NULL` hold is live under D43), and `hold_minutes` is a one-line
  addition to the singleton already used for the D45 cap. Always
  `PENDING_PAYMENT` keeps 4.4/4.5/4.6 honest: the slot is protected by the hold,
  lazy expiry frees it (D6), and only Phase 5's payment confirms it. Deferring
  the reference avoids committing a public identifier format before the receipt
  contract exists.

- **Consequence:** `create_booking` writes `PENDING_PAYMENT` with a non-null
  `hold_expires_at`; `apps.parking` gains one field and one migration; the
  consumer path never accepts a client-supplied plate or price. The remaining
  §18 hold behaviour (how a lapsed hold is *presented*, early release) is 4.5.

- **Status:** Accepted (2026-10-06).

---

## D48 — Booking creation refusals and the HTTP status map (accepted 2026-10-06)

Settles worksheet Q5–Q7 and Q10. Every refusal keeps the §33
`{"error": "CODE", "message": ...}` shape.

- **Decision:**
  - **Q5 — in-lock overlap: A.** `409 BOOKING_CONFLICT`. The in-transaction
    conflict is a *state* refusal, not a shape error, so it is not a `400`.
  - **Q6 — past window: A.** A window already over (`end_time <= now`) is
    `400 WINDOW_IN_PAST`, distinct from the shape error `INVALID_WINDOW`
    (`end <= start`). "Starts in the past, ends in the future" is deliberately
    **not** refused here; that is the walk-in case and belongs to the walk-in
    increment.
  - **Q7 — target not bookable: A.** Inactive lot → `404 LOT_NOT_BOOKABLE`
    (unaddressable, consistent with the `LotScopedMixin` reads); `OUT_OF_SERVICE`
    slot → `409 SLOT_UNAVAILABLE` (a real, actionable state).
  - **Q10 — full map: A.**
    - `400` (shape/client): `INVALID_WINDOW`, `WINDOW_IN_PAST`,
      `MIN_DURATION_NOT_MET`, `MAX_DURATION_EXCEEDED`
    - `404` (absent target): `SLOT_NOT_FOUND`, `LOT_NOT_BOOKABLE`
    - `409` (state/config): `SLOT_UNAVAILABLE`, `BOOKING_CONFLICT`, `NO_TARIFF`

- **Rationale:** A lets a client tell "fix your request" (`400`) from
  "retry / pick another slot" (`409`) from "that target is gone" (`404`), exactly
  how the existing parking writes (`RATE_ABOVE_MAXIMUM`, `MAX_DURATION_*`) and
  §33 already behave. Keeping `WINDOW_IN_PAST` distinct from `INVALID_WINDOW`
  lets a UI explain the two different problems.

- **Consequence:** `apps/bookings/views.py` holds a `REFUSAL_STATUS` map from
  stable code → status; the service raises the D44-family exceptions and never
  knows HTTP.

- **Status:** Accepted (2026-10-06).

---

## D49 — Creation locking strategy and idempotency (accepted 2026-10-06)

Settles worksheet Q8–Q9.

- **Decision:**
  - **Q8 — locking: A.** `create_booking` takes the lock itself:
    `ParkingSlot.objects.select_for_update(of=("self",))` on the addressed slot
    row, then checks lot-active / in-service / duration / conflict under that
    lock. `available_slots` (4.3) stays a read and is **never** used as a
    correctness guard: an unlocked pre-read deciding a write is TOCTOU — another
    request can take the slot between the read and the lock.
  - **Q9 — idempotency: A (defer).** No `Idempotency-Key` in 4.4; it stays a
    Phase 10 hardening candidate (D41). A duplicate must ultimately be caught at
    Phase 5's confirmation/payment seam anyway.

- **Rationale:** The lock must be taken before the check to satisfy Invariant 1
  under READ COMMITTED; there is no cheaper correct ordering. The lock is scoped
  to one slot (`of=("self",)` keeps `FOR UPDATE` off the joined lot row), so only
  same-slot contenders queue — for a re-check plus an insert, with no I/O inside
  the transaction.

- **Consequence:** The correctness of 4.4 rests on a single ordering: lock →
  expire → re-check → insert. `CreateBookingConcurrencyTests`
  (`TransactionTestCase`, two threads, PostgreSQL) is the test that fails if
  that order is broken; every other test still passes if the lock moves after the
  check.

- **Status:** Accepted (2026-10-06).

---

## D50 — Effective status for a lapsed hold, and read-only expiry (accepted 2026-10-06)

Increment 4.5 is the §18 **temporary hold**. Because D47/Q3 pulled the hold
assignment and `BusinessRule.hold_minutes` into 4.4, the field, the create-time
expiry write and the liveness predicate already existed; 4.5 settles the
remaining, presentation-side semantics. This entry records the answers to the
4.5 worksheet.

- **Decision:**
  - **Q1 — scope: A.** 4.5 lands *effective-expiry reads* and hold reporting:
    the read side must never show a dead hold as live. It adds no new storage
    and no new endpoint.
  - **Q2 — reads report a lapsed pending booking as `EXPIRED`: A.** A computed
    `effective_status` is exposed on the booking read serializer
    (`EXPIRED` when `status == PENDING_PAYMENT` and `hold_expires_at <= now`;
    otherwise the stored status). It is computed by
    `services.effective_status`, which reuses `is_hold_live` so reads and the
    conflict predicate cannot drift (D43).
  - **Q3 — consumer early release: B.** A consumer may **not** release a
    `PENDING_PAYMENT` booking in 4.5; that is **4.7 cancellation**, so there is
    one owner of the transition. 4.5 stays read-side.
  - **Q4 — other endpoints persist expiry: A (no).** Only the creation path
    writes expiry (`expire_stale_holds`, inside the slot lock). Reads —
    including `GET /api/bookings/` — remain side-effect-free (D43); effective
    reads (Q2) cover presentation.

- **Rationale:** A computed `effective_status` closes the only real gap left by
  4.4 — a client that trusts the raw `status` could treat an expired hold as a
  live reservation — while preserving the project's "GETs do not mutate"
  guarantee (D43) and the single-writer rule. Deferring early release to 4.7
  keeps cancellation's rules (cutoff, refund eligibility, `cancelled_by`) in one
  increment instead of splitting them across two.

- **Consequence:** `BookingSerializer` gains the read-only `effective_status`
  field; the stored `status` and `hold_expires_at` stay in the payload for
  transparency. No model change ⇒ **no migration**. `services.effective_status`
  is the single definition of the presented state; tests cover the live,
  lapsed, no-deadline and non-pending cases, and prove the read does not
  persist.

- **Status:** Accepted (2026-10-06).

---

## D51 — Confirmation seam: the `PENDING_PAYMENT → CONFIRMED` transition (accepted 2026-10-06)

Increment 4.6. 4.4 creates a booking as `PENDING_PAYMENT`; this is the only
doorway that moves a paid booking to `CONFIRMED`. Phase 4 does **not** process a
payment — Phase 5's gateway calls this transition when a payment succeeds.

- **Decision:**
  - **Q1 — surface: A.** An internal service function
    `services.confirm_booking(*, booking_id)` only. No HTTP endpoint: a
    consumer-facing "confirm" route would let an unpaid booking be confirmed,
    and the Phase 4 API has no payment to trigger it. Phase 5 supplies the
    trigger.
  - **Q2 — guards and refusals: A.** Only a **live** `PENDING_PAYMENT` may
    confirm. A booking already `CONFIRMED` returns unchanged — an **idempotent**
    success, because payment gateways retry callbacks. Every other state is
    refused with the new error **code** `BOOKING_NOT_CONFIRMABLE` (409), not a
    new state: a lapsed hold is swept to the existing `EXPIRED` state first, so
    "payment too late" and "cancelled" share one refusal. A missing id raises
    `BOOKING_NOT_FOUND`.
  - **Q3 — concurrency: A.** `confirm_booking` takes the **slot** row lock
    (not the booking row), reuses `expire_stale_holds`, and re-checks
    `blocking_window_q` for *other* blocking bookings before committing — the
    creation ordering of D49, mirrored. This keeps Invariant 1 even in the race
    after a hold lapses.
  - **Q4 — hold on success: A.** Confirmation sets `hold_expires_at = NULL` (a
    hold means something only while pending). The in-lock sweep also retires any
    other lapsed holds on the slot, and commits with the confirmation.
    A **refused** attempt is atomic and rolls the sweep back, leaving the stale
    row untouched — harmless, because a lapsed hold no longer blocks (D41) and
    reads report it as `EXPIRED` (D50).

- **Rationale:** A pure service seam keeps Phase 4 free of payment processing
  (§26/§36 boundary) while giving Phase 5 a single, correct transition to call.
  Idempotency matters because a gateway may deliver the same success twice
  (§35 "duplicate payment callback"); the ordering matters because confirmation
  is the second writer that can create a stored `CONFIRMED` overlap, so it must
  serialize with creation exactly as creation serializes with itself. Refusing a
  lapsed hold honours §19's timeout: once the 5-minute hold is gone the slot may
  already be someone else's.

- **Consequence:** `services.py` gains `BookingNotFoundError`/`BOOKING_NOT_FOUND`
  and `BookingNotConfirmableError`/`BOOKING_NOT_CONFIRMABLE`; the existing
  `BOOKING_CONFLICT` (409) is reused for the taken-window guard. No model change
  ⇒ **no migration**. The HTTP status map is not extended yet, because 4.6 adds
  no endpoint; `confirm_booking` is called directly and covered by service
  tests. Because the two new codes are *refusal codes*, the seven booking states
  in `models.py` are unchanged.

- **Status:** Accepted (2026-10-06).

---

## D52 — Public booking reference (accepted 2026-10-06)

Increment 4.6. D47/Q4 deferred the walk-in/receipt identifier to this increment;
this entry settles its scope, format and exposure.

- **Decision:**
  - **Scope: A.** **Every** booking gets a `reference` — consumer and walk-in
    alike. Receipts and the §30 booking QR code apply to both, so one uniform
    code path is simpler than a walk-in-only field.
  - **Format: A.** A **random, unguessable** code: `REFERENCE_LENGTH = 10`
    characters drawn from a 32-character human-friendly alphabet
    (`A–Z` minus `I`/`O`, plus `2–9`; no ambiguous `0`/`1`). It encodes no lot,
    date or sequence, so the population cannot be enumerated; uniqueness is
    enforced by the database, with the value generated by
    `apps/bookings/references.generate_reference` as the field's `default`.
  - **`reference` is the stored field name** (not `ticket_code`); a printed
    ticket or QR just presents this value. It is `editable=False` (server-only;
    a client cannot set or spoof it) and exposed on the authenticated read
    serializer.
  - **Exposure: A (minimal).** 4.6 stores the field and reports it on
    `GET /api/bookings/`; it adds **no** public lookup endpoint and **no**
    single-booking detail route. The unauthenticated QR/gate lookup arrives with
    the walk-in/gate flow that defines its response, and
    `GET /api/bookings/{id}/` stays in 4.9.

- **Rationale:** A walk-in has no login, so the receipt/QR needs a bearer key
  that works without an account; the same key serves a consumer's digital
  receipt. Randomness is the security property — a structured code
  (`BLR-20261006-0007`) is guessable and would leak the booking. Storing it at
  creation, before any walk-in flow exists, means no later backfill migration.

- **Consequence:** `Booking.reference` (`CharField(max_length=12, unique=True,
  editable=False, default=generate_reference)`) plus migration
  `bookings/0003_booking_reference.py`, written as three operations (add
  nullable → data-backfill existing rows → tighten to unique/non-null) so a
  non-empty table migrates safely. No new state. The public lookup and detail
  endpoints remain deferred.

- **Status:** Accepted (2026-10-06).

---

## Increment 4.4 implementation decisions (accepted 2026-10-06)

Recorded while delivering 4.4; they refine D47–D49, D41 and D44, not replace
them.

- **`create_booking` shape (D49)** — in `apps/bookings/services.py`, decorated
  `@transaction.atomic`, keyword-only
  (`*, slot_id, start_time, end_time, user, vehicle`). It calls
  `validate_window`, refuses `end_time <= now`, locks the slot row with
  `select_for_update(of=("self",))`, checks lot-active / in-service, calls
  `quote_booking` for the snapshot, calls
  `expire_stale_holds(slot=slot, now=now)` (the only writer of lazy expiry, D43),
  re-checks `blocking_window_q` under the lock, then inserts.
- **Refusal classes (D44/D48)** — `SlotNotFoundError`/`SLOT_NOT_FOUND`,
  `LotNotBookableError`/`LOT_NOT_BOOKABLE`,
  `SlotUnavailableError`/`SLOT_UNAVAILABLE`,
  `WindowInPastError`/`WINDOW_IN_PAST`,
  `BookingConflictError`/`BOOKING_CONFLICT`, all subclasses of
  `BookingRuleError`.
- **`BusinessRule.hold_minutes` (D47/Q3)** — `PositiveIntegerField` default `5`
  with `business_rule_hold_minutes_positive`; migration
  `parking/0006_businessrule_hold_minutes_and_more.py`; exposed by
  `BusinessRuleSerializer` / `BusinessRuleUpdateSerializer` and written by
  `set_business_rules`. No backfill.
- **API surface (D47/D48)** — `apps/bookings/serializers.py`
  (`BookingSerializer` read, `BookingCreateSerializer` write with required
  `slot`, `vehicle`, `start_time`, `end_time` and an owner check on `vehicle`),
  `apps/bookings/views.py` (`BookingListCreateView`, `IsConsumer`, queryset
  scoped to `request.user`, `REFUSAL_STATUS`), `apps/bookings/urls.py`
  (`bookings/`), and `config/urls.py` includes it. `GET` lists only the caller's
  bookings (Invariant 2).
- **Tests (D7)** — `CreateBookingServiceTests`, `CreateBookingApiTests` and
  `CreateBookingConcurrencyTests` (`TransactionTestCase`, two threads, exactly
  one winner; requires PostgreSQL, D4) in `apps/bookings/tests.py`, and
  `HoldMinutesRuleTests` in `apps/parking/tests.py`. Combined `apps.parking` +
  `apps.bookings` run: **179 tests OK**.

---

## 4.4 decision worksheet (resolved 2026-10-06 — kept for the record)

Increment 4.4 is the first **write** path. PROJECT.md §9/§21 required the
consequential choices below to be decided *with* the human before coding. Every
question was answered with the recommended option; the answers are recorded as
**D47**, **D48** and **D49** above. The options are retained here so the
reasoning can be re-read later.

### Q1 — Who may create a booking, and how is ownership set?

- **Decision:** which callers reach `POST /api/bookings/`, and how the acting
  account is attached.
- **Options:**
  - **A — Consumer self-booking only.** `IsConsumer`; `user = created_by =
    request.user`. Walk-ins arrive in a later increment.
  - **B — Consumer self + Manager walk-in in the same increment.** `IsConsumer`
    for a self-booking; `IsManager` may post on behalf of a lot they manage with
    `user=null`, `created_by=request.user`, `vehicle_plate` free text.
- **Trade-offs:** A is the smallest coherent write path and matches §36's
  ordering (creation 4.4, walk-in flows later); it keeps 4.4 reviewable. B closes
  the Manager-walk-in use case now but drags in Invariant 3 (is this manager
  assigned to *that* lot?) and the walk-in identity question (Q4) at the same
  time, roughly doubling the surface.
- **Recommendation:** **A.** A manager walk-in is its own coherent increment
  (it is a distinct §3.1 "Parking Manager Features" slice), and D8 already
  keeps the model ready. State the eventual walk-in behaviour now, implement it
  when its increment opens.

### Q2 — What status does a new booking have, and who confirms it?

- **Decision:** the status a successful create writes, and the lifecycle until
  Phase 5.
- **Options:**
  - **A — `PENDING_PAYMENT` always**, with `hold_expires_at` set. Confirmation
    (4.6) moves it to `CONFIRMED` when Phase 5's gateway says paid.
  - **B — `CONFIRMED` immediately** for the create path, bypassing the hold.
- **Trade-offs:** A is exactly §17/§19 and keeps 4.4, 4.5 (hold) and 4.6
  (confirmation) separate and honest; the slot is protected by the hold, and
  lazy expiry (D6) frees it. B would make 4.4 instantly "booked" but then 4.5
  has nothing to model and payments would confirm something already confirmed —
  it collapses the §18 hold/reservation distinction.
- **Recommendation:** **A.**

### Q3 — Does 4.4 assign the hold, or does 4.5?

- **Decision:** where `hold_expires_at` is set on creation.
- **Options:**
  - **A — 4.4 sets `hold_expires_at = now + hold_minutes`** and adds
    `BusinessRule.hold_minutes` (the §19 5-minute default) now.
  - **B — 4.4 creates `PENDING_PAYMENT` with `hold_expires_at = NULL`**;
    4.5 owns the hold duration, the `hold_minutes` field and its tests.
- **Trade-offs:** A gives a fully working "slot frees itself after 5 minutes"
  in one increment, but introduces the one schema change (Q4 aside) and a §19
  number inside 4.4. B keeps 4.4 a pure create+conflict increment and lets the
  "temporary hold" feature land whole in 4.5, exactly as §36 sequences it — but a
  `NULL` hold never expires (D43 treats it as live), so between 4.4 and 4.5 a
  pending booking holds forever. That is acceptable only if 4.5 lands next.
- **Recommendation:** **A**, with the field introduced as its own tiny decision
  — a pending booking that never expires is a foot-gun, and `hold_minutes` is a
  one-line addition to the existing `BusinessRule` singleton (D6/D45 pattern
  already established). Keep the 4.5 increment for the *expiry sweeps/reporting*
  and edge cases.

### Q4 — Walk-in public identifier (`reference` / `ticket_code`)

- **Decision:** by what identifier a walk-in (and a booked consumer) is looked
  up when there is no login — the unguessable bearer key that a QR/receipt will
  carry.
- **Options:**
  - **A — defer entirely to 4.6** (no new field in 4.4; the surrogate `id` is
    not exposed as a public key).
  - **B — add a stored, unique `reference` now** (short, unguessable, e.g. a
    random token) on every booking, used by walk-in lookup and receipts.
- **Trade-offs:** A keeps 4.4 schema-free and avoids inventing a public
  identifier before the confirmation/receipt contract (4.6, Phase 5) exists —
  the identifier's shape is a function of how it is presented (QR, printed
  ticket). B makes the booking externally referenceable immediately but commits a
  format early; changing it later is a migration.
- **Recommendation:** **A — defer, and record the deferral here.** The core 4.4
  path needs no public identifier; D39 already establishes the surrogate `id` as
  the internal key and §22 does not require a human-facing code until receipts.

### Q5 — How is a window conflict refused?

- **Decision:** the code and status when the in-lock re-check finds an overlap.
- **Options:**
  - **A — `409 BOOKING_CONFLICT`** with the §33 `{"error", "message"}` shape,
    matching `RATE_ABOVE_MAXIMUM` / `MAX_DURATION_*` / `LAST_ADMINISTRATOR`.
  - **B — `400` as a serializer validation error.**
- **Trade-offs:** A is consistent with every other conflict-shaped refusal in
  the project and lets the frontend branch on a stable code; B is simpler but
  conflates "your payload is malformed" with "the world changed while you were
  deciding", which are different recovery paths for the client.
- **Recommendation:** **A.** The in-transaction conflict is a *state* refusal,
  not a *shape* refusal — same reasoning as D44 and §33.

### Q6 — Is a window entirely in the past refused?

- **Decision:** does 4.4 reject `end_time <= now`, or only `end_time <=
  start_time` (the D41 shape rule)?
- **Options:**
  - **A — refuse past windows** with a stable code (`INVALID_WINDOW` or a
    distinct `WINDOW_IN_PAST`) — §35 lists "booking in the past" as an edge
    case.
  - **B — allow them**, treating the shape rule as the only window rule.
- **Trade-offs:** A prevents nonsense bookings and matches §35, but needs a
  policy for the clock boundary and a decision whether the *start* may be in the
  past with a future *end* (e.g. a walk-in that started 5 minutes ago). B is the
  minimal rule but stores records that can never be honoured.
- **Recommendation:** **A**, refusing only when `end_time <= now` (a booking
  whose window is wholly over), leaving "starts in the past, ends in the future"
  to the walk-in increment — that is the only legitimate case for it. Choose the
  code now (`WINDOW_IN_PAST` keeps it distinct from the shape error).

### Q7 — Inactive lot / out-of-service slot: status and code

- **Decision:** the refusal when the target cannot be booked.
- **Options:**
  - **A — `404` for an inactive lot** (not addressable, consistent with the
    `LotScopedMixin` reads) and **`409 SLOT_UNAVAILABLE`** for an
    `OUT_OF_SERVICE` slot.
  - **B — `409` for both.**
- **Trade-offs:** A reuses the established "unaddressable ⇒ 404" rule for the
  lot and reserves `409` for a real, actionable state conflict; B is uniform but
  leaks the existence of cancelled lots.
- **Recommendation:** **A.**

### Q8 — Where does the generic bookable-slot lookup live?

- **Decision:** how the create path turns `slot` + window into a locked row.
- **Options:**
  - **A — the service locks the slot by id, then checks lot-active /
    in-service / available itself.**
  - **B — the view resolves the slot through `available_slots(...)` first, then
    the service locks.** 
- **Trade-offs:** A is the honest D3 shape: the lock is taken on the slot row
  *before* the check, so the check cannot go stale. B is a pre-filter only —
  using it as the guard would be TOCTOU: another request can take the slot
  between the read and the lock. A costs one `select_for_update` regardless of
  availability; B would save nothing because the lock is still needed.
- **Recommendation:** **A.** `available_slots` stays a *read* (4.3); creation
  never relies on it for correctness, only, optionally, for a friendly
  pre-message.

### Q9 — Idempotency key for create

- **Decision:** guard against a double-submitted create (retry, double-click).
- **Options:**
  - **A — defer to Phase 10** (D41 already names it a hardening candidate).
  - **B — require/accept an `Idempotency-Key` header now.**
- **Trade-offs:** A keeps 4.4 focused; the danger is a user charged twice in
  Phase 5, but Phase 5's confirmation path is where a duplicate must be caught
  anyway. B adds a store and a contract.
- **Recommendation:** **A — defer**, recorded as a Phase 10 candidate (D41).

### Q10 — Refusal → HTTP status map

- **Decision:** the status each service refusal becomes (the §33 `{"error",
  "message"}` codes are stable either way).
- **Options:**
  - **A — shape/client errors are `400`; state/config conflicts are `409`:**
    `INVALID_WINDOW` → 400, `WINDOW_IN_PAST` → 400, `MIN_DURATION_NOT_MET` → 400,
    `MAX_DURATION_EXCEEDED` → 400, `SLOT_NOT_FOUND` → 404, `SLOT_UNAVAILABLE` →
    409, `BOOKING_CONFLICT` → 409, `NO_TARIFF` → 409.
  - **B — every booking refusal is `409`**, reserving `400` for malformed JSON
    and field types only.
- **Trade-offs:** A lets the client treat "fix your request" (400) differently
  from "retry/try another slot" (409), which is how the existing parking writes
  already behave; B is uniform but tells the client nothing about recovery.
- **Recommendation:** **A.** It matches the `RATE_ABOVE_MAXIMUM` /
  `MAX_DURATION_*` / `LAST_ADMINISTRATOR` precedent (409 for state, 400 for
  shape) and §33.

---

## 4.5 decision worksheet (resolved 2026-10-06 — kept for the record)

Increment 4.5 is the §18 **temporary hold**. Because D47/Q3 pulled the hold
assignment and `BusinessRule.hold_minutes` into 4.4, the field, the create-time
expiry write and the liveness predicate already existed; 4.5 became the
remaining hold semantics. PROJECT.md §9/§21 required the choices below to be
decided *with* the human before they were coded. Every question was answered
with the recommended option; the answers are recorded as **D50** above. The
options are retained here so the reasoning can be re-read later.

### Q1 — What is the remaining scope of 4.5?

- **Decision:** what 4.5 builds now that 4.4 assigns and expires holds.
- **Options:**
  - **A — "effective expiry" reads + hold reporting.** Make the read side honest:
    a lapsed `PENDING_PAYMENT` is presented as its effective state (e.g. a
    computed `EXPIRED`) **without** persisting it (D43 keeps reads
    side-effect-free). Tightest change that closes the "dead hold looks live"
    gap.
  - **B — fold 4.5 into 4.7 (cancellation).** Keep only 4.4's create-time
    expiry; let release/cancel land in 4.7 and mark 4.5 absorbed.
  - **C — add a sweep endpoint/command.** Rejected by D6 (lazy, no scheduler)
    unless a concrete need appears.
- **Recommendation:** **A**, scoped by Q2–Q4.

### Q2 — Should reads report a logically-expired pending booking as `EXPIRED`?

- **Options:**
  - **A — yes, a computed `effective_status`** in the read serializer
    (`EXPIRED` when `status == PENDING_PAYMENT` and `hold_expires_at <= now`,
    with no write).
  - **B — no; expose only the stored status and `hold_expires_at`** and document
    that the client must compare.
- **Recommendation:** **A** — a client must never render a dead hold as live;
  the computation keeps D43 intact.

### Q3 — Can a consumer release a `PENDING_PAYMENT` booking early?

- **Options:**
  - **A — yes, in 4.5** (owner sets `CANCELLED`, freeing the slot immediately).
  - **B — defer to 4.7 cancellation** so there is one cancellation path.
- **Recommendation:** **B** — one owner of the transition; 4.5 stays read-side.

### Q4 — Should any endpoint other than creation persist expiry?

- **Options:**
  - **A — no; keep D43** (creation is the only writer).
  - **B — add a lazy sweep on list/detail.**
- **Recommendation:** **A** — preserving "GETs do not mutate" is worth more than
  a tidy stored status; effective reads (Q2) cover presentation.

---

## 4.6 decision worksheet (resolved 2026-10-06 — kept for the record)

Increment 4.6 is the **confirmation seam** plus the walk-in `reference` deferred
by D47/Q4. It consumes 4.4's create path and 4.5's effective reads. The
questions below were decided with the human; the answers are recorded as
**D51** (confirmation) and **D52** (reference). Every question took the
recommended option.

> Clarification recorded at decision time: `BOOKING_NOT_CONFIRMABLE` and
> `BOOKING_NOT_FOUND` are **refusal codes** — the stable string in the §33
> `{"error": "CODE", ...}` response — not booking states. The seven states in
> `models.py` are unchanged. A lapsed hold needs no code of its own because the
> in-lock sweep turns it into the existing `EXPIRED` state.

### Q1 — How is confirmation triggered?

- **Options:** **A** internal service function only (Phase 5 calls it);
  **B** add an HTTP endpoint now as a stand-in.
- **Trade-offs:** B would let an unpaid booking be confirmed by its owner, since
  Phase 4 has no payment to gate it. A keeps Phase 4 out of payment processing.
- **Recommendation/answer:** **A** (`services.confirm_booking`).

### Q2 — What may be confirmed, and how is a refusal labelled?

- **Options:** **A** only a live `PENDING_PAYMENT`; already-`CONFIRMED` is an
  idempotent success; everything else is one new refusal code
  `BOOKING_NOT_CONFIRMABLE` (the lapsed hold having become `EXPIRED`);
  **B** no new code at all (return the current state); **C** two codes
  (`BOOKING_HOLD_EXPIRED` + `BOOKING_NOT_CONFIRMABLE`).
- **Recommendation/answer:** **A**, corrected from the earlier draft that
  proposed C. One code is enough, and it is an error code, not a state.

### Q3 — Does confirmation take the slot lock and re-check the window?

- **Options:** **A** yes, mirror creation (lock → sweep → re-check → write);
  **B** plain status transition, no lock.
- **Recommendation/answer:** **A** — Invariant 1 must hold for the second writer
  that can store `CONFIRMED`.

### Q4 — What happens to the hold?

- **Options:** **A** clear `hold_expires_at` and reuse the lazy sweep; **B**
  keep it as history.
- **Recommendation/answer:** **A**. A refused attempt rolls back (atomicity), so
  the sweep persists only on success.

### Q5 — Which bookings get a `reference`, in what format?

- **Options:** scope (everyone / walk-ins only); format (random short code /
  structured enumerable code / UUID).
- **Recommendation/answer:** **everyone**, as a **random, unguessable ~10-char**
  code; it is a bearer key, so it must not be enumerable.

### Q6 — Do 4.6's extra endpoints land now?

- **Options:** **A** neither the public reference lookup nor the booking detail
  route; **B** public lookup only; **C** both.
- **Trade-offs:** the public lookup returns booking data to anyone holding the
  code, so its response belongs with the walk-in/gate flow; the detail route is
  4.9.
- **Recommendation/answer:** **A** — store and expose the reference; defer both
  routes.

---

## Open questions carried to later increments

Each will be surfaced as its own decision when its increment is opened.

| Question | Lands in |
|----------|----------|
| `BusinessRule.hold_minutes` (temporary hold length, §19 default 5) | ✅ done in 4.4 (D47/Q3) |
| Remaining temporary-hold semantics (effective expiry reads, early release) | ✅ done in 4.5 (D50); early release deferred to 4.7 |
| `BusinessRule.cancellation_cutoff_minutes` (§19 default 30) | 4.7 |
| `BusinessRule.overstay_multiplier` (§19 default 1.5) | Phase 6 |
| Confirmation seam in Phase 4 vs deferring to Phase 5's gateway | ✅ done in 4.6 (D51) |
| Walk-in public `reference`/`ticket_code` (unguessable bearer key) | ✅ done in 4.6 (D52); field stored + exposed |
| Public reference lookup endpoint (QR/gate, unauthenticated) | walk-in/gate flow (deferred by D52) |
| Single-booking read `GET /api/bookings/{id}/` | 4.9 |
| Extension charge seam (Phase 5 payment handoff) | 4.8 |
| Whether `CANCELLED` and `TERMINATED` need distinct refusal messages | 4.7 |
| `Idempotency-Key` on booking create | Phase 10 (deferred by D49/Q9) |
