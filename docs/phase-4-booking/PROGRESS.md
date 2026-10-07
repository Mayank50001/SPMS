# Progress — Phase 4 (Booking) 🔵 IN PROGRESS

> **Scope (PROJECT.md §36):** the booking domain — model, states, availability
> query, creation, temporary hold, confirmation, cancellation, extension and
> booking history. This is described as "the most important backend phase".
> Decisions are in [`DECISIONS.md`](DECISIONS.md) (D39–D52 accepted; D39 revised
> in 4.2).
> Working conventions and the reading protocol: [`../README.md`](../README.md).
> Phase 3 context (parking catalogue, slots, tariffs): 
> [`../phase-3-parking/PROGRESS.md`](../phase-3-parking/PROGRESS.md).

Last updated: 2026-10-07 · **Increments 4.1–4.7 are complete; 4.8 is next.**
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
concurrency test. 4.5 delivered the **temporary-hold presentation** (D50): a
read-only, computed `effective_status` that reports a lapsed `PENDING_PAYMENT`
as `EXPIRED` with no write, so a GET never shows a dead hold as live (no schema
change). 4.6 delivered the **confirmation seam** (D51) and the public
**`reference`** (D52): a slot-locked, idempotent `confirm_booking` that Phase 5's
gateway calls, plus a random unguessable receipt/QR code on every booking.
4.7 delivered **cancellation** (D53): the §19 refund cutoff on the
`BusinessRule` singleton, a slot-locked, idempotent `cancel_booking` that stores
the **`refund_due_amount`** snapshot, and `POST /api/bookings/{id}/cancel/` —
Phase 5's gateway performs the actual refund.
**Next: 4.8, extension** (extending a booking's end time; its decisions are
still open).

---

## Start here (fresh session)

1. [`../README.md`](../README.md) — conventions + reading protocol.
2. This file — the increment plan, what is delivered, and what is next.
3. [`DECISIONS.md`](DECISIONS.md) — D39–D52 (accepted; D39 revised in 4.2), and
   the open questions carried to later increments.
4. Only if a task touches it: the "Dependencies on earlier phases" table below.

**Next session starts here:** increment **4.8 — extension** (extending a
`CONFIRMED` booking's end time: the slot re-check, the incremental price and the
Phase 5 charge handoff). It consumes the `CONFIRMED` state, `quote_booking`
(4.2) and the confirmation seam (4.6); its decisions have not been opened yet.

---

## Increment plan

| # | Increment | Status |
|---|-----------|--------|
| 4.1 | `Booking` model + state enum + migration + model tests | ✅ Done |
| 4.2 | Pricing / duration / (lazy) expiry helpers + per-slot duration policy (D45) | ✅ Done |
| 4.3 | Time-window availability query (D46) | ✅ Done |
| 4.4 | Booking creation + concurrency (D3/D41) | ✅ Done |
| 4.5 | Effective status for a lapsed hold (D50) | ✅ Done |
| 4.6 | Confirmation seam (D51) + public `reference` (D52) | ✅ Done |
| 4.7 | Cancellation (D53) | ✅ Done |
| 4.8 | Extension | ⚪ Next |
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

## Increment 4.5 — effective status for a lapsed hold ✅

### What it delivers

The presentation half of the §18 "temporary hold": a `PENDING_PAYMENT` booking
reports its **effective** state at read time, so a hold that has lapsed reads as
`EXPIRED` even though its stored `status` is untouched. Because D47/Q3 pulled the
hold assignment, `BusinessRule.hold_minutes` and the create-time expiry write
into 4.4, 4.5 is a small, read-side increment: no new storage, no new endpoint,
no migration, and the single-writer rule is preserved (D43/D50).

### Files

| File | State |
|------|-------|
| `apps/bookings/services.py` | **extended** — `effective_status(booking, now=None)` reusing `is_hold_live` |
| `apps/bookings/serializers.py` | **extended** — read-only `effective_status` `SerializerMethodField` on `BookingSerializer` |
| `apps/bookings/tests.py` | **extended** — `EffectiveStatusTests` (5 service tests) + 2 API tests |

Suggested commit (PROJECT.md §43):
`feat(bookings): report effective expiry for lapsed holds`

### Backend flow

```text
GET /api/bookings/                (IsConsumer; caller's bookings only)
   ↓
BookingSerializer
   ├── status            (stored, unchanged)
   ├── effective_status  → services.effective_status(booking)   (D50)
   └── hold_expires_at   (stored)
```

### Decisions realized in the code

- **D50 (Q1/Q2)** — `effective_status` returns `EXPIRED` when the stored status
  is `PENDING_PAYMENT` and its hold is not live; otherwise the stored status. It
  reuses `is_hold_live`, so the presented state and `blocking_window_q` share one
  definition (D43).
- **D50 (Q4)** — the helper computes only; the serializer does not persist. The
  stored `status` stays `PENDING_PAYMENT` after a read (asserted by a test).
- **D50 (Q3)** — early release of a pending booking is deliberately **not** here;
  it belongs to 4.7 cancellation.

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

Result: no check issues; **186 tests OK** (`apps.parking` 112, `apps.bookings`
74), including the new effective-status service and API tests. Manual
spot-check: a pending booking whose `hold_expires_at` has passed returns
`"effective_status": "EXPIRED"` and `"status": "PENDING_PAYMENT"` from
`GET /api/bookings/`.

### Known, deliberate gaps from 4.5

- **No early release** — cancelling a pending booking is 4.7 (D50/Q3).
- **No single-booking read** — `BookingDetailView` is still 4.9 unless an earlier
  increment needs it.
- **No confirmation** — `PENDING_PAYMENT → CONFIRMED` is 4.6.
- **No pagination** (Phase 10).

---

## Increment 4.6 — confirmation seam + public `reference` ✅

### What it delivers

The doorway from `PENDING_PAYMENT` to `CONFIRMED` and the unguessable code a
receipt or QR carries. Phase 4 still does **not** process a payment (§26/§36
boundary): the confirmation is an internal service that Phase 5's gateway calls
when a payment succeeds. The `reference` is generated for every booking at
creation (consumer and walk-in alike), so no later backfill is needed.

### Files

| File | State |
|------|-------|
| `apps/bookings/references.py` | **created** — `generate_reference`, `REFERENCE_ALPHABET`, `REFERENCE_LENGTH` |
| `apps/bookings/models.py` | **extended** — `Booking.reference` (`unique`, `editable=False`, `default=generate_reference`) |
| `apps/bookings/migrations/0003_booking_reference.py` | generated — add nullable → backfill → tighten |
| `apps/bookings/services.py` | **extended** — `confirm_booking(*, booking_id, now=None)` + `BookingNotFoundError`/`BOOKING_NOT_FOUND`, `BookingNotConfirmableError`/`BOOKING_NOT_CONFIRMABLE` |
| `apps/bookings/serializers.py` | **extended** — `reference` on the read serializer |
| `apps/bookings/admin.py` | **extended** — `reference` in list display / search |
| `apps/bookings/tests.py` | **extended** — `ReferenceTests`, `ConfirmBookingServiceTests`, 2 reference API tests |

Suggested commit (PROJECT.md §43):
`feat(bookings): add confirmation seam and public reference`

### Backend flow

```text
Phase 5 gateway ── payment success ──> services.confirm_booking(booking_id=…)
                                          (transaction.atomic)
   ├── read booking → find its slot
   ├── select_for_update(of=("self",)) slot row      (D51/Q3)
   ├── expire_stale_holds(slot=…)                     (D43, the one sweep)
   ├── re-read booking: CONFIRMED → return (idempotent)
   │                    not PENDING → BOOKING_NOT_CONFIRMABLE
   ├── re-check blocking_window_q (excluding self) → BOOKING_CONFLICT
   └── status = CONFIRMED, hold_expires_at = NULL
```

### Decisions realized in the code

- **D51** — service-only transition (no endpoint); only a live
  `PENDING_PAYMENT` confirms; already-`CONFIRMED` is an idempotent success;
  the slot lock + sweep + window re-check mirror `create_booking` (D49), so
  Invariant 1 holds for this second writer. `hold_expires_at` is cleared on
  success.
- **D52** — every booking carries a random, unguessable `reference`
  (10 chars, 32-char unambiguous alphabet), unique, `editable=False`, generated
  by `references.generate_reference`; exposed on the authenticated read. No
  public lookup / detail endpoint (deferred to the walk-in/gate flow and 4.9).

### Migration note (PROJECT.md §42)

- **Model change:** `Booking.reference` — `CharField(max_length=12, unique=True,
  editable=False, default=generate_reference)`.
- **Expected DB change:** `ALTER TABLE bookings_booking ADD COLUMN reference
  varchar(12)` (nullable) → backfill → `SET NOT NULL` + unique index.
- **Data implications:** existing bookings are each assigned a freshly generated
  unique code by the data migration; no other column changes. The dev database
  held **0** bookings, so the backfill was a no-op there, but it is written to be
  safe on a non-empty table.

### Verification

```bash
cd backend
../env/bin/python manage.py makemigrations --check
../env/bin/python manage.py migrate
../env/bin/python manage.py check
../env/bin/python manage.py test
```

Result: `makemigrations --check` reports no changes; `check` is clean;
**261 tests OK** (was 248). New coverage: `ReferenceTests` (shape, per-booking
generation, uniqueness, non-editable), `ConfirmBookingServiceTests` (confirm +
clear hold, idempotent repeat, lapsed hold refused, cancelled refused, unknown
refused, taken-window conflict, success sweeps other stale holds) and two
reference API tests (generated on create, client cannot choose it).

### Known, deliberate gaps from 4.6

- **No confirmation endpoint** — the seam is called internally; Phase 5 supplies
  the trigger (D51/Q1).
- **No payment** — `confirm_booking` performs no charge and records no
  `Payment`; that is Phase 5 (§26).
- **No public reference lookup** — the unauthenticated QR/gate lookup is deferred
  to the walk-in/gate flow (D52).
- **No single-booking read** — `BookingDetailView` is 4.9.
- **No pagination** (Phase 10).

---

## Increment 4.7 — cancellation ✅

### What it delivers

The §19 "change of mind" path: a Consumer cancels one of their own bookings, the
slot is freed immediately and the **refund rule** is applied and recorded. Phase
4 still does **not** move money (§26 boundary): the refund is decided and stored
on the booking; Phase 5's gateway pays it. Cancellation is the second consumer
write after creation, so it reuses creation's slot-lock ordering to serialize
with confirmation (D51) rather than introducing a second concurrency mechanism.
The increment adds the §19 cutoff to the `BusinessRule` singleton and the stored
refund snapshot to `Booking`.

### Files

| File | State |
|------|-------|
| `apps/bookings/services.py` | **extended** — `cancel_booking(...)` (atomic, slot-locked, idempotent), `refund_due_for(...)`, `BookingNotCancellableError`/`BOOKING_NOT_CANCELLABLE` |
| `apps/bookings/models.py` | **extended** — stored `refund_due_amount` `Decimal(12,2)` default `0.00` (+ non-negative check) |
| `apps/bookings/migrations/0004_booking_refund_due_amount_and_more.py` | generated |
| `apps/bookings/serializers.py` | **extended** — `refund_due_amount`, `cancelled_at` on the read serializer |
| `apps/bookings/views.py` | **extended** — `BookingCancelView` (`IsConsumer`); `BOOKING_NOT_FOUND`/`BOOKING_NOT_CANCELLABLE` added to `REFUSAL_STATUS` |
| `apps/bookings/urls.py` | **extended** — `bookings/<int:pk>/cancel/` |
| `apps/bookings/admin.py` | **extended** — `refund_due_amount` in the admin list |
| `apps/parking/models.py` | **extended** — `BusinessRule.cancellation_cutoff_minutes` (default 30, positive check) |
| `apps/parking/migrations/0007_businessrule_cancellation_cutoff_minutes_and_more.py` | generated |
| `apps/parking/services.py` / `serializers.py` / `views.py` | **extended** — expose/validate `cancellation_cutoff_minutes`; `set_business_rules` writes it |
| `apps/bookings/tests.py` | **extended** — `RefundDueTests`, `CancelBookingServiceTests`, `CancelBookingApiTests` |
| `apps/parking/tests.py` | **extended** — `CancellationCutoffRuleTests` |

Suggested commit (PROJECT.md §43):
`feat(bookings): implement booking cancellation and refund eligibility`

### Backend flow

```text
POST /api/bookings/{id}/cancel/              (IsConsumer)
   ↓
BookingCancelView → services.cancel_booking(booking_id, user)
   (transaction.atomic)
   ├── look up the caller's booking → BOOKING_NOT_FOUND (Invariant 2)
   ├── select_for_update(of=("self",)) slot row   (D49/D51, same first lock)
   ├── re-read booking
   │     ├── CANCELLED → return unchanged (idempotent)
   │     ├── not PENDING_PAYMENT/CONFIRMED → BOOKING_NOT_CANCELLABLE
   ├── refund_due_for(booking, cutoff) → stored snapshot    (D53/§19)
   └── status = CANCELLED, cancelled_at/by, refund_due_amount
        ↓
BookingSerializer (200)
```

### Decisions realized in the code

- **D53 (Q1/Q2)** — Consumer self-cancel only; `PENDING_PAYMENT` (including a
  lapsed hold) and `CONFIRMED` are cancellable; `IN_PROGRESS`/`COMPLETED`/
  `EXPIRED`/`TERMINATED` are refused. Owner-scoped lookup: a foreign booking is
  `404 BOOKING_NOT_FOUND`, never `403` (Invariant 2).
- **D53 (Q3/Q4)** — the refund rule lives in `refund_due_for`; only a paid
  (`CONFIRMED`) booking can owe one, and it is the full `base_amount` at or
  before `start_time - cutoff`, else `0.00`. The result is a **stored snapshot**
  on the booking, computed from `BusinessRule.cancellation_cutoff_minutes`.
- **D53 (Q5)** — cancellation locks the **slot** row first, exactly as creation
  (D49) and confirmation (D51); it needs no window re-check, but the shared
  first lock is what stops a cancel racing the confirming payment.
- **D53 (Q6)** — an already-`CANCELLED` booking returns unchanged (idempotent),
  matching confirmation's retry-safe contract.
- **D53 (Q7)** — endpoint + refusal map: `POST /api/bookings/{id}/cancel/`,
  `200` with `status = CANCELLED` and `refund_due_amount`; `BOOKING_NOT_FOUND`
  → `404`, `BOOKING_NOT_CANCELLABLE` → `409`.

### Migration note (PROJECT.md §42)

- **Model change:** `Booking.refund_due_amount` (`Decimal(12,2)`, default
  `0.00`, `>= 0` check); `BusinessRule.cancellation_cutoff_minutes`
  (`PositiveIntegerField`, default `30`, positive check).
- **Expected DB change:** `ALTER TABLE bookings_booking ADD refund_due_amount`
  + check; `ALTER TABLE parking_businessrule ADD cancellation_cutoff_minutes`
  + check. Both columns are non-null with a default, so existing rows take the
  default with **no backfill**.
- **Data implications:** none — active bookings read `0.00`; the singleton takes
  `30`.

### Verification

```bash
cd backend
../env/bin/python manage.py makemigrations --check
../env/bin/python manage.py migrate
../env/bin/python manage.py check
../env/bin/python manage.py test
```

Result: `makemigrations --check` reports no changes; `check` is clean;
**288 tests OK** (was 261). New coverage: `RefundDueTests` (before/at/inside the
cutoff, pending, past-start), `CancelBookingServiceTests` (pending release,
lapsed-hold release, confirmed refund, cutoff from the singleton, idempotency,
non-cancellable states, foreign/unknown booking) and `CancelBookingApiTests`
(auth, refund payload, 404/409 refusals, manager 403), plus
`CancellationCutoffRuleTests` (default 30, read, Admin-only update).

### Known, deliberate gaps from 4.7

- **No money movement** — `refund_due_amount` is a record; Phase 5's gateway
  performs the refund (D53/Q3, §26).
- **No manager/admin cancellation** — removing a booking is the `TERMINATED`
  transition owned by a later phase; `cancel_booking` is consumer-only.
- **No `cancelled_by` in the payload** — stored for audit, not yet exposed.
- **No booking detail / history route** — `BookingDetailView` is still 4.9.
- **No pagination** (Phase 10).
- **No cancel-vs-confirm concurrency test** — the shared slot lock is the
  argument (documented in D53/Q5); a deterministic two-writer test is a Phase 10
  hardening candidate.

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
