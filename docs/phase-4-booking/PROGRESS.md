# Progress — Phase 4 (Booking) 🔵 IN PROGRESS

> **Scope (PROJECT.md §36):** the booking domain — model, states, availability
> query, creation, temporary hold, confirmation, cancellation, extension and
> booking history. This is described as "the most important backend phase".
> Decisions are in [`DECISIONS.md`](DECISIONS.md) (D39–D49 accepted; D39 revised
> in 4.2).
> Working conventions and the reading protocol: [`../README.md`](../README.md).
> Phase 3 context (parking catalogue, slots, tariffs): 
> [`../phase-3-parking/PROGRESS.md`](../phase-3-parking/PROGRESS.md).

Last updated: 2026-10-06 · **Increments 4.1–4.4 are complete; 4.5 is planned and
its decisions are open.**
4.1 delivered the `Booking` model + state enum (D39–D41). 4.2 delivered the
booking rule layer whole: the tariff quote (`quote_booking`, the single pricing
seam), the D41 conflict predicate, lazy hold expiry, the **stored `base_amount`
snapshot** (D39 revised), and the **per-slot duration policy (D45)** — which
reopened two Phase 3 models once (`ParkingSlot.min/max_booking_hours`,
`BusinessRule.max_booking_hours`). 4.3 delivered the read-only **time-window
availability query** (D46): the derived `.../availability/` read, consuming
`blocking_window_q` (D43) inside a correlated `EXISTS` with no schema change.
4.4 delivered the first **write** path: `POST /api/bookings/` and an atomic,
slot-locked `create_booking` that persists lazy expiry, re-checks the window
under the lock and assigns the §19 hold (D47–D49) — verified by a two-thread
concurrency test.
**Next: 4.5, temporary hold + lazy expiry (D6)** — the remaining hold semantics
now that 4.4 owns the field and the create-time expiry; its worksheet is at the
end of [`DECISIONS.md`](DECISIONS.md).

---

## Start here (fresh session)

1. [`../README.md`](../README.md) — conventions + reading protocol.
2. This file — the increment plan, what is delivered, and what is next.
3. [`DECISIONS.md`](DECISIONS.md) — D39–D49 (accepted; D39 revised in 4.2), the
   **4.5 decision worksheet** (open), and the open questions carried to later
   increments.
4. Only if a task touches it: the "Dependencies on earlier phases" table below.

**Next session starts here:** increment **4.5 — temporary hold + lazy expiry**.
It consumes the hold already assigned by 4.4 (`create_booking` sets
`hold_expires_at`; `expire_stale_holds` and `blocking_window_q` implement D6/D43)
and lands the remaining hold semantics. The plan is in "Increment 4.5" below; the
choices still owed by the human are the **4.5 decision worksheet** in
[`DECISIONS.md`](DECISIONS.md).

---

## Increment plan

| # | Increment | Status |
|---|-----------|--------|
| 4.1 | `Booking` model + state enum + migration + model tests | ✅ Done |
| 4.2 | Pricing / duration / (lazy) expiry helpers + per-slot duration policy (D45) | ✅ Done |
| 4.3 | Time-window availability query (D46) | ✅ Done |
| 4.4 | Booking creation + concurrency (D3/D41) | ✅ Done |
| 4.5 | Temporary hold + lazy expiry (D6) | 🟡 Planned (decision worksheet open) |
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

## Increment 4.4 — booking creation + concurrency ✅

### What it delivers

The first *write* path of the booking domain: create a `Booking` for one slot
and window, atomically. It consumes the 4.2 rule layer (`quote_booking`,
`blocking_window_q`, `expire_stale_holds`) and 4.3's read semantics, and
implements D3/D41's concurrency mechanism: one `transaction.atomic`, a
`select_for_update()` lock on the **slot** row, lazy-expiry persistence and an
overlap re-check **inside** the transaction before insert (Invariants 1 & 6).
The only schema change is `BusinessRule.hold_minutes` (D47/Q3), which lets the
create path assign the §19 hold.

### Files

| File | State |
|------|-------|
| `apps/bookings/services.py` | **extended** — `create_booking(...)` (atomic, slot-locked) + refusal classes `SlotNotFoundError`, `LotNotBookableError`, `SlotUnavailableError`, `WindowInPastError`, `BookingConflictError` |
| `apps/bookings/serializers.py` | **created** — `BookingSerializer` (read) + `BookingCreateSerializer` (write; required slot + vehicle + window) |
| `apps/bookings/views.py` | **created** — `BookingListCreateView` (`IsConsumer`; `REFUSAL_STATUS` map) |
| `apps/bookings/urls.py` | **created** — `bookings/` (`booking-list`) |
| `config/urls.py` | **extended** — `include("apps.bookings.urls")` |
| `apps/parking/models.py` | **extended** — `BusinessRule.hold_minutes` (+ positive check) |
| `apps/parking/serializers.py` / `views.py` / `services.py` | **extended** — expose/validate `hold_minutes`; `set_business_rules` writes it |
| `apps/parking/migrations/0006_businessrule_hold_minutes_and_more.py` | generated |
| `apps/bookings/tests.py` | **extended** — `CreateBookingServiceTests`, `CreateBookingConcurrencyTests`, `CreateBookingApiTests` |
| `apps/parking/tests.py` | **extended** — `HoldMinutesRuleTests` |

Suggested commit (PROJECT.md §43):
`feat(bookings): implement booking creation with slot locking`

### Backend flow

```text
POST /api/bookings/                          (IsConsumer)
   ↓
BookingCreateSerializer   (window shape, slot id, vehicle ownership)
   ↓
services.create_booking   (transaction.atomic)
   ├── validate_window + reject end <= now        (D41/D48)
   ├── select_for_update(of=("self",)) slot row   (D3)
   ├── lot active + slot not OUT_OF_SERVICE        (Invariant 5)
   ├── quote_booking → price snapshot              (4.2)
   ├── expire_stale_holds(slot=...)                (D6/D43)
   ├── re-check blocking_window_q inside the lock  → BOOKING_CONFLICT (Invariant 1)
   └── Booking.objects.create(status=PENDING_PAYMENT, hold_expires_at)
   ↓
BookingSerializer (201)
```

### Decisions realized in the code

- **D47** — consumer self-booking only (`IsConsumer`;
  `user = created_by = request.user`); always `PENDING_PAYMENT`; 4.4 assigns the
  hold from `BusinessRule.hold_minutes` (default 5); the walk-in `reference` is
  deferred to 4.6; `vehicle` is required so the snapshot plate is never blank.
- **D48** — refusal codes and status map: `BOOKING_CONFLICT` /
  `SLOT_UNAVAILABLE` / `NO_TARIFF` → `409`,
  `WINDOW_IN_PAST` / `INVALID_WINDOW` / the duration refusals → `400`,
  `SLOT_NOT_FOUND` / `LOT_NOT_BOOKABLE` → `404`; §33
  `{"error", "message"}` shape.
- **D49** — the service locks the slot by id then checks; `available_slots`
  stays read-only and is never a correctness guard; no idempotency key (Phase
  10).
- **D41/D43** — the lock is scoped with `of=("self",)` so the joined lot row is
  not locked; `expire_stale_holds` runs inside the lock (the only writer); the
  conflict re-check uses `blocking_window_q` unchanged, so 4.3 and 4.4 cannot
  drift.

### Migration note (PROJECT.md §42)

- **Model change:** `BusinessRule.hold_minutes` (`PositiveIntegerField`,
  default `5`) + `business_rule_hold_minutes_positive` check.
- **Expected DB change:** `ALTER TABLE parking_businessrule ADD COLUMN
  hold_minutes integer NOT NULL DEFAULT 5` + the check constraint.
- **Data implications:** none — the singleton row takes the default; no
  backfill.

### Verification

Result: `manage.py check` clean; **179 tests OK** across `apps.parking` +
`apps.bookings`, including `CreateBookingConcurrencyTests` (two threads, one
slot, exactly one `created` and one `BOOKING_CONFLICT`) and
`CreateBookingApiTests`.

```bash
cd backend
../env/bin/python manage.py makemigrations parking
../env/bin/python manage.py migrate
../env/bin/python manage.py check
../env/bin/python manage.py test apps.parking apps.bookings
```

Manual spot-check:

```bash
curl -X POST http://127.0.0.1:8000/api/bookings/ \
  -H "Authorization: Bearer <access>" -H "Content-Type: application/json" \
  -d '{"slot": 1, "vehicle": 1, "start_time": "2026-10-07T10:00:00Z", "end_time": "2026-10-07T12:00:00Z"}'
```

A second overlapping request for the same slot returns `409 BOOKING_CONFLICT`;
an `OUT_OF_SERVICE` slot returns `409 SLOT_UNAVAILABLE`; an inactive lot returns
`404 LOT_NOT_BOOKABLE`; a wholly-past window returns `400 WINDOW_IN_PAST`.

### Known, deliberate gaps from 4.4

- **No single-booking read** — only `GET /api/bookings/` (list) exists;
  `BookingDetailView` is 4.9 (history/listing) unless 4.5 needs it.
- **No state transitions** — confirmation (4.6), cancellation (4.7), extension
  (4.8) and Phase 6 occupancy own their transitions; 4.4 only creates
  `PENDING_PAYMENT`.
- **No public `reference`** — deferred to 4.6 (D47/Q4).
- **No idempotency key** — Phase 10 (D49/Q9).
- **Manager walk-ins are not creatable over HTTP** — the model supports them
  (D8); the API path is a later increment (D47/Q1).
- **No pagination** (Phase 10).

---

## Increment 4.5 — temporary hold + lazy expiry (D6) 🟡 PLANNED

### What it delivers

The §18 "temporary hold": the rule that a `PENDING_PAYMENT` booking reserves its
slot only until `hold_expires_at`, after which the slot is free again — evaluated
**lazily**, with no scheduler (D6). Because D47/Q3 chose to assign the hold and
add `BusinessRule.hold_minutes` in **4.4**, part of this feature already exists:
`create_booking` sets `hold_expires_at` and calls `expire_stale_holds` inside its
slot lock, and `blocking_window_q` (D43) already treats a lapsed hold as
non-blocking. 4.5 therefore lands the remaining, deliberately-deferred pieces
(scope to be confirmed by its worksheet) rather than the field itself.

### What already exists (from 4.4)

- `BusinessRule.hold_minutes` (default 5) + migration
  `parking/0006_businessrule_hold_minutes_and_more.py`.
- `create_booking` assigns `hold_expires_at = now + hold_minutes` and persists
  lazy expiry via `expire_stale_holds(slot=...)`.
- `blocking_window_q` / `is_hold_live` already encode the liveness rule (D43).

### Candidate scope (to be settled)

- Whether reads should report a lapsed `PENDING_PAYMENT` as an *effective*
  `EXPIRED` (a computed field) without persisting it (D43 keeps reads
  side-effect-free) — or leave the stored status and let the client infer.
- Whether a pending booking can be **released/cancelled** by its owner here or in
  4.7 (cancellation).
- Whether any endpoint other than creation should persist expiry (D43 currently
  says no).
- Whether `BookingDetailView` (a single-booking read) is needed to surface the
  hold.

### Decisions to be settled before coding

A **4.5 decision worksheet** is at the end of
[`DECISIONS.md`](DECISIONS.md). It is not coded until those choices are locked.

### Migration note (PROJECT.md §42)

To be determined with the worksheet; the likely answer is **none** (the field
and its migration already landed in 4.4).

### Verification

To be filled when the increment is delivered; expect a mix of service tests
(effective status / liveness) and API tests, run against PostgreSQL (D4).

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
