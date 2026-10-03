# Progress — Phase 4 (Booking) 🔵 IN PROGRESS

> **Scope (PROJECT.md §36):** the booking domain — model, states, availability
> query, creation, temporary hold, confirmation, cancellation, extension and
> booking history. This is described as "the most important backend phase".
> Decisions are in [`DECISIONS.md`](DECISIONS.md) (D39–D41 accepted so far).
> Working conventions and the reading protocol: [`../README.md`](../README.md).
> Phase 3 context (parking catalogue, slots, tariffs): 
> [`../phase-3-parking/PROGRESS.md`](../phase-3-parking/PROGRESS.md).

Last updated: 2026-10-04 · **Phase 4 opened.** Increment **4.1** (the `Booking`
model + state enum) has its decisions accepted (D39–D41) and its code supplied.
The developer types the code in and runs the verification before the increment
is marked done. Later increments are decided one at a time.

---

## Start here (fresh session)

1. [`../README.md`](../README.md) — conventions + reading protocol.
2. This file — the increment plan, what is delivered, and what is next.
3. [`DECISIONS.md`](DECISIONS.md) — D39–D41 (accepted) and the open questions
   carried to later increments.
4. Only if a task touches it: the "Dependencies on earlier phases" table below.

---

## Increment plan

| # | Increment | Status |
|---|-----------|--------|
| 4.1 | `Booking` model + state enum + migration + model tests | 🔵 Code supplied — awaiting implementation/verification |
| 4.2 | Pricing / duration / (lazy) expiry helpers | ⚪ Not started |
| 4.3 | Time-window availability query | ⚪ Not started |
| 4.4 | Booking creation + concurrency (D3/D41) | ⚪ Not started |
| 4.5 | Temporary hold + lazy expiry (D6) | ⚪ Not started |
| 4.6 | Confirmation seam (Phase 5 wires the gateway) | ⚪ Not started |
| 4.7 | Cancellation | ⚪ Not started |
| 4.8 | Extension | ⚪ Not started |
| 4.9 | Booking history / listing | ⚪ Not started |

---

## Increment 4.1 — `Booking` model + state enum 🔵

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

- **D39** — `user` / `created_by` / `vehicle` nullable `SET_NULL`; `slot`
  `PROTECT`; `slot_type`, `hourly_rate`, `billed_hours`, `vehicle_plate`
  snapshotted; `lot` and `base_amount` derived; two indexes; three checks
  (`end > start`, `billed_hours >= 1`, non-blank plate).
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
| **D31 / D32 / D34** | The slot's `number`, `slot_type` enum and the `Tariff` the snapshot price comes from. |
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
- **No real charge amount stored on the booking** — `base_amount` is derived;
  the charged amount belongs to Phase 5's `Payment`.
- **No refunds** — the refund-due *rule* is Phase 4 (4.7 derives eligibility
  from the cancellation cutoff); the money movement is Phase 5.

## Boundary with Phase 6 (do not cross)

- **`IN_PROGRESS` / `COMPLETED` are not written in Phase 4** — Phase 6 occupancy
  actions own them (§28). Phase 4 only *defines* the states.
- **No occupancy controls** and no overstay settlement — Phase 6.
