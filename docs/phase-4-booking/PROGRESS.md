# Progress — Phase 4 (Booking) 🔵 IN PROGRESS

> **Scope (PROJECT.md §36):** the booking domain — model, states, availability
> query, creation, temporary hold, confirmation, cancellation, extension and
> booking history. This is described as "the most important backend phase".
> Decisions are in [`DECISIONS.md`](DECISIONS.md) (D39–D45 accepted; D39 revised
> in 4.2).
> Working conventions and the reading protocol: [`../README.md`](../README.md).
> Phase 3 context (parking catalogue, slots, tariffs): 
> [`../phase-3-parking/PROGRESS.md`](../phase-3-parking/PROGRESS.md).

Last updated: 2026-10-05 · **Increments 4.1, 4.2 and 4.3 are complete.**
4.1 delivered the `Booking` model + state enum (D39–D41). 4.2 delivered the
booking rule layer whole: the tariff quote (`quote_booking`, the single pricing
seam), the D41 conflict predicate, lazy hold expiry, the **stored `base_amount`
snapshot** (D39 revised), and the **per-slot duration policy (D45)** — which
reopened two Phase 3 models once (`ParkingSlot.min/max_booking_hours`,
`BusinessRule.max_booking_hours`). 4.3 delivered the read-only **time-window
availability query** (D46): the derived `.../availability/` read, consuming
`blocking_window_q` (D43) inside a correlated `EXISTS` with no schema change.
**Next: 4.4, booking creation + concurrency (D3/D41).**

---

## Start here (fresh session)

1. [`../README.md`](../README.md) — conventions + reading protocol.
2. This file — the increment plan, what is delivered, and what is next.
3. [`DECISIONS.md`](DECISIONS.md) — D39–D45 (accepted; D39 revised in 4.2) plus
   the open questions carried to later increments.
4. Only if a task touches it: the "Dependencies on earlier phases" table below.

**Next session starts here:** increment **4.4 — booking creation and
concurrency**. It consumes `available_slots` (4.3) / `blocking_window_q` (D43)
and `quote_booking` (4.2), and is the first *write* path: an atomic,
slot-locked transaction that re-checks the window before insert (D3/D41). It
also decides the walk-in public `reference`/`ticket_code` (see the open
questions in `DECISIONS.md`).

---

## Increment plan

| # | Increment | Status |
|---|-----------|--------|
| 4.1 | `Booking` model + state enum + migration + model tests | ✅ Done |
| 4.2 | Pricing / duration / (lazy) expiry helpers + per-slot duration policy (D45) | ✅ Done |
| 4.3 | Time-window availability query (D46) | ✅ Done |
| 4.4 | Booking creation + concurrency (D3/D41) | ⚪ Not started |
| 4.5 | Temporary hold + lazy expiry (D6) | ⚪ Not started |
| 4.6 | Confirmation seam (Phase 5 wires the gateway) | ⚪ Not started |
| 4.7 | Cancellation | ⚪ Not started |
| 4.8 | Extension | ⚪ Not started |
| 4.9 | Booking history / listing | ⚪ Not started |

---

## Increment 4.1 — `Booking` model + state enum ✅

### What it delivers

Only the **persistence** layer: the `Booking` record, its relationships, the
price/plate snapshots, the state enumeration and the database constraints. No
serializers, views, URLs, availability or lifecycle logic — those are 4.2+.
This follows PROJECT.md §36's "implement incrementally" instruction.

### Files

| File | State |
|------|-------|
| `apps/bookings/models.py` | `Booking` (+ `Status` enum, `BLOCKING_STATUSES`, snapshots, indexes, checks) |
| `apps/bookings/migrations/0001_initial.py` | to be generated (`makemigrations bookings`) |
| `apps/bookings/admin.py` | registers `Booking` (read-mostly) |
| `apps/bookings/tests.py` | `BookingModelTests` (11 model tests) |

Suggested commit (PROJECT.md §43):
`feat(bookings): add booking model and state enum`

### Decisions realized in the code

- **D39** (as built in 4.1; **revised in 4.2**) — `user` / `created_by` /
  `vehicle` nullable `SET_NULL`; `slot` `PROTECT`; `slot_type`, `hourly_rate`,
  `billed_hours`, `vehicle_plate` snapshotted; `lot` derived; two indexes; three
  checks (`end > start`, `billed_hours >= 1`, non-blank plate). **4.2 replaced
  the derived `base_amount` with a stored snapshot (+ a fourth check).**
- **D39/V6** — the plate is authoritative; `save()` copies it from the vehicle
  FK when present, otherwise canonicalises the walk-in free text
  (`strip().upper()`, the D13/D28/D31 single-representation rule).
- **D40** — full seven-state `Status` enum; no `NO_SHOW`;
  `BLOCKING_STATUSES = (PENDING_PAYMENT, CONFIRMED, IN_PROGRESS)`. Transitions
  are enforced by later increments' services, not here.
- **D41** — half-open `[start, end)` conflict rule and the lazy-expiry exclusion
  are documented in the model; enforcement code lands in 4.3/4.4. No DB
  `EXCLUDE` constraint (recorded rationale in `DECISIONS.md`).

### Migration note (PROJECT.md §42)

- **Model change:** new `Booking` model with five FKs (`user`, `created_by`,
  `vehicle`, `slot`, `cancelled_by`), two indexes, three check constraints.
- **Expected DB change:** `CREATE TABLE bookings_booking` plus indexes,
  constraints and FK constraints. Referenced tables already exist.
- **Data implications:** none — a new empty table; no existing rows touched.

### Verification

```bash
cd backend
../env/bin/python manage.py makemigrations bookings
../env/bin/python manage.py migrate
../env/bin/python manage.py check
../env/bin/python manage.py test apps.bookings
```

Expected: migration applies cleanly; no check issues; **11 tests OK**.

### Known, deliberate gaps from 4.1

- **No API yet** — the model has no serializer, view or URL. The `Booking` is
  not reachable over HTTP until 4.3/4.4.
- **No state-transition enforcement** — the enum exists, but the legal
  transitions of D40 are enforced by service functions from 4.4 onward.
- **No conflict enforcement code** — D41's half-open rule is recorded, not yet
  implemented (4.3/4.4).
- **No public reference/ticket code** — only the surrogate `id` exists; the
  unguessable walk-in reference is an open question for 4.4/4.6.
- **No pagination** (Phase 10), consistent with the rest of the project.

---

## Increment 4.2 — booking helpers (pricing, D41 predicate, duration policy) ✅

### What it delivers

The shared rule layer later increments consume, delivered whole: the tariff
quote, the single encoding of D41's conflict predicate, the lazy-expiry sweep,
the window/duration validation, the **per-slot duration policy (D45)** and the
**stored `base_amount` snapshot** (D39 revised). No API, no views, no
create/cancel — availability is 4.3 and creation is 4.4.

### Files

| File | State |
|------|-------|
| `apps/bookings/services.py` | **created** — `hours_between`, `validate_window`, `validate_duration`, `quote_booking`, `blocking_window_q`, `is_hold_live`, `expire_stale_holds`, `BookingQuote`, error classes |
| `apps/bookings/models.py` | `base_amount` property → stored `Decimal(12,2)` field + `booking_base_amount_positive` check |
| `apps/bookings/migrations/0002_booking_base_amount_and_more.py` | generated |
| `apps/bookings/admin.py` | `base_amount` added to the admin list |
| `apps/bookings/tests.py` | `BookingServicesTests` + stored-snapshot model tests |
| `apps/parking/models.py` | `ParkingSlot.min/max_booking_hours` (+ min<=max check); `BusinessRule.max_booking_hours` (+ positive check) |
| `apps/parking/migrations/0005_businessrule_max_booking_hours_and_more.py` | generated |
| `apps/parking/services.py` | `save_slot`, `set_business_rules`, `SlotDurationAboveMaximumError`, `MaxDurationBelowSlotError` |
| `apps/parking/serializers.py` / `views.py` | expose/validate the duration fields; map the two `409`s |
| `apps/parking/tests.py` | `SlotDurationPolicyTests` |

Suggested commit (PROJECT.md §43):
`feat(bookings): add pricing and conflict helpers`

### Decisions realized in the code

- **D42 (revised)** — fixed-window only; `hours_between` is pure ceil-to-whole-
  hours; `quote_booking` is the single pricing seam.
- **D43** — `blocking_window_q` / `is_hold_live` are the one definition of D41;
  the predicate is positive (no `~Q`), so a NULL `hold_expires_at` cannot break
  liveness; reads do not write; `expire_stale_holds` is called only by creation.
- **D44** — one `services.py`; refusals carry stable codes (`INVALID_WINDOW`,
  `MIN_DURATION_NOT_MET`, `MAX_DURATION_EXCEEDED`, `NO_TARIFF`).
- **D45** — per-slot whole-hour duration policy on `ParkingSlot` (defaults
  1/24), capped by `BusinessRule.max_booking_hours` (default 72); both ends
  reject; the cap is enforced in `parking/services` under the singleton lock.
- **D39 revision** — `base_amount` is a stored snapshot, computed by
  `quote_booking`.

### Migration note (PROJECT.md §42)

- **Model change:** `Booking.base_amount` stored (+ positive check);
  `ParkingSlot` duration fields (+ min<=max check); `BusinessRule.max_booking_hours`
  (+ positive check).
- **Expected DB change:** `ALTER TABLE bookings_booking ADD base_amount` +
  constraint; `ALTER TABLE parking_parkingslot ADD min/max_booking_hours` +
  constraint; `ALTER TABLE parking_businessrule ADD max_booking_hours` +
  constraint.
- **Data implications:** none — `bookings_booking` was empty; the new parking
  columns take defaults, so **no backfill** (D45-Q5).

### Verification

```bash
cd backend
../env/bin/python manage.py makemigrations
../env/bin/python manage.py migrate
../env/bin/python manage.py check
../env/bin/python manage.py test apps.parking apps.bookings
```

Result: no check issues; **137 tests OK** (`apps.parking` 103, `apps.bookings`
34).

### Known, deliberate gaps from 4.2

- **Availability endpoint** — added in 4.3 as
  `GET /api/parking-lots/{lot}/availability/` (D46); `blocking_window_q` is now
  reachable over HTTP.
- **No creation path** — `expire_stale_holds` is tested directly but is not yet
  *called* by the creation transaction (4.4 wires it).
- **`hold_minutes` / `cancellation_cutoff_minutes` / `overstay_multiplier` not
  added** — 4.5 / 4.7 / Phase 6.
- **Advanced pricing deferred** — tiers, day caps, peak/demand; the seam is
  `quote_booking` (see [`../deferred-features.md`](../deferred-features.md)).

---

## Increment 4.3 — time-window availability query ✅

### What it delivers

The read side of the booking domain: given a lot and a window `[start, end)`,
which of its slots can be booked. Availability is **derived** from bookings
(D2/D33) and the query is **read-only** (D43) — it never persists expiry. No
model change, so **no migration**. Creation is 4.4.

### Files

| File | State |
|------|-------|
| `apps/bookings/services.py` | **extended** — `available_slots(*, lot, start_time, end_time, now=None)` selector (reuses `validate_window`, `hours_between`, `blocking_window_q`) |
| `apps/parking/serializers.py` | **extended** — `AvailabilityQuerySerializer` (`start` / `end` `DateTimeField`) |
| `apps/parking/views.py` | **extended** — `ParkingLotAvailabilityView` (`LotScopedMixin` + `ListAPIView`) |
| `apps/parking/urls.py` | **extended** — `parking-lots/<int:lot_pk>/availability/` |
| `apps/bookings/tests.py` | **extended** — `AvailabilityQueryTests` (12 selector tests) |
| `apps/parking/tests.py` | **extended** — `AvailabilityApiTests` (7 API / permission tests) |

Suggested commit (PROJECT.md §43):
`feat(bookings): add time-window availability query`

### Decisions realized in the code

- **D46** — dedicated `.../availability/?start=&end=` sub-resource; "available"
  = not `OUT_OF_SERVICE` + window within the slot's D45 duration policy + no
  blocking overlap; `OCCUPIED` deliberately not excluded; response is the
  bookable `ParkingSlotSerializer` subset.
- **D41/D43** — the overlap and liveness test is `blocking_window_q`, used
  unchanged inside a correlated `Exists`; a lapsed `PENDING_PAYMENT` does not
  hide the slot and is left untouched (Invariant 6, read-only reads).
- **D44** — the selector is a service in `apps/bookings/services.py`; the
  refusal `INVALID_WINDOW` is mapped to `400 {"error": ..., "message": ...}`.
- **D45** — the requested `billed_hours` is checked against each slot's
  `min_booking_hours` / `max_booking_hours` in the queryset, so availability
  never offers a slot that creation would refuse.

### Migration note (PROJECT.md §42)

- **Model change:** none.
- **Expected DB change:** none — read-only increment.
- **Data implications:** none.

### Verification

```bash
cd backend
../env/bin/python manage.py check
../env/bin/python manage.py test apps.parking apps.bookings
```

Expected: no check issues; all tests pass, including the new availability
selector (`apps.bookings`) and API (`apps.parking`) tests. Manual spot-check:

```bash
curl "http://127.0.0.1:8000/api/parking-lots/1/availability/?start=2026-10-06T10:00:00Z&end=2026-10-06T12:00:00Z"
```

A missing `start` / `end`, or `end <= start`, is a `400`.

### Known, deliberate gaps from 4.3

- **No creation path** — availability says "free"; 4.4 makes the atomic,
  slot-locked booking that guarantees it under concurrency.
- **`OCCUPIED` policy deferred** — Phase 6 owns physical occupancy (§28).
- **No per-slot availability reason** — the endpoint returns bookable slots
  only; an annotated `is_available` / `reason` shape is additive if the UI needs
  to grey out slots.
- **No pagination** (Phase 10).

---

## Dependencies on earlier phases

Read these **only** when a Phase 4 task touches them. Full entries live in the
foundation and earlier-phase decision files.

| Decision | Why Phase 4 needs it |
|----------|----------------------|
| **D2 (revised D33)** | Stored slot state is physical only; `RESERVED`/`HELD` derive from bookings. `OCCUPIED` is Phase 6. |
| **D3** | The agreed booking-concurrency mechanism (confirmed as D41). |
| **D4** | PostgreSQL is mandatory — row locking and the constraint set rely on it. |
| **D5** | `start_time` / `end_time` / `hold_expires_at` are stored UTC. |
| **D6** | Hold/payment expiry is lazy — no scheduler. |
| **D7** | Tests use Django's `TestCase` / `TransactionTestCase`. |
| **D8** | `Booking.user` is nullable (walk-ins). |
| **D28 / V6 / V7** | The `Vehicle → Booking` chain; V6 (delete semantics) is resolved by D39, V7 (free-text plates) is covered by the `vehicle_plate` snapshot. |
| **D31 / D32 / D34 / D45** | The slot's `number`, `slot_type` enum, the `Tariff` the snapshot price comes from, and the per-slot duration policy availability/creation must honour. |
| **D38** | Lifecycle flags; no hard delete of lots/slots referenced by bookings. |
| **D18** | Deny-by-default permissions; availability reads will opt out explicitly. |

**Existing patterns to reuse:**

- `apps/accounts/permissions.py` — `IsConsumer` / `IsManager` / `IsAdmin`; role
  only, object-level scoping is done in the view's queryset.
- `apps/accounts/services.py` and `apps/parking/services.py` — where business
  logic beyond validation lives. Booking rules belong in
  `apps/bookings/services.py` (created in 4.2+).
- Read/write serializer split; explicit `generics.*` + hand-written `urls.py`.
- Error shape `{"error": "CODE", "message": ...}` for conflict-shaped refusals
  (PROJECT.md §33), as in `RATE_ABOVE_MAXIMUM` / `MAX_RATE_BELOW_TARIFF`.

---

## Boundary with Phase 5 (do not cross)

- **No payment model, gateway or receipt** — Phase 5. Phase 4 may define a
  *confirmation seam* (4.6) so a booking can move to `CONFIRMED`, but it does
  not process a payment.
- **`base_amount` is the agreed price, not the charge** — Phase 5 records what
  was actually charged on `Payment`; 4.2 stores `base_amount` as the contract
  price of the booked duration (D39 revised).
- **No refunds** — the refund-due *rule* is Phase 4 (4.7 derives eligibility
  from the cancellation cutoff); the money movement is Phase 5.

## Boundary with Phase 6 (do not cross)

- **`IN_PROGRESS` / `COMPLETED` are not written in Phase 4** — Phase 6 occupancy
  actions own them (§28). Phase 4 only *defines* the states.
- **No occupancy controls** and no overstay settlement — Phase 6.
