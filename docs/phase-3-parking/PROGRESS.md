# Progress — Phase 3 (Parking domain) ✅ COMPLETE

> **Scope (PROJECT.md §36):** `ParkingLot`, `ParkingSlot`, slot types, pricing and
> manager assignment, plus the manager-authorization and lot-assignment rules.
> Decisions are in [`DECISIONS.md`](DECISIONS.md) (D29–D38, all **accepted**,
> plus the increment-3.2, 3.3 and 3.4 refinements at the end of that file).
> Working conventions and the reading protocol: [`../README.md`](../README.md).

Last updated: 2026-10-05 · **Phase 3 closed — §36 scope delivered (3.1–3.4).**
Post-close (2026-10-05): Phase 4's **D45** reopened two parking models once, to
add the per-slot duration policy (`ParkingSlot.min/max_booking_hours`,
`BusinessRule.max_booking_hours`); see [`DECISIONS.md`](DECISIONS.md) →
"Post-close change". `apps.parking` is now **103 tests green** (89 at close + the
new duration tests). The former increment 3.5 is retired: its optional ideas are
folded into later phases (see "Optional follow-ups" below). Phase 4 (Booking) is
the current phase.

---

## Start here (fresh session)

Phase 3 is closed; read this file only for parking context. The reading order is:

1. [`../README.md`](../README.md) — conventions + reading protocol.
2. This file — what the parking domain built and the optional follow-ups.
3. [`DECISIONS.md`](DECISIONS.md) — D29–D38 (the parking decisions).
4. Only if a task touches it: the "Dependencies on earlier phases" table below.

Then: start **Phase 4 (Booking)** in a new session — surface its decisions first,
write no code until they are chosen. Nothing in Phase 3 is left open.

---

## Decision status

All parking decisions are **accepted** (full entries in `DECISIONS.md`):
D29 (+ S1, S2), D30, D31, D32, D33 (**revises D2**), D34, D35, D36, D37, D38,
plus the **Increment 3.2 implementation decisions** (FK cascade, `floor` type,
final `slot_type` enum, manager slot writes, D34 ordering, status-write scope),
the **Increment 3.3 implementation decisions** (singleton fixed PK, cap-change
`409`, unpriced-type rejection, rate floor, lock-based concurrency, public reads,
URL shapes, default cap) and the **Increment 3.4 implementation decisions**
(assigned-only manager list, active-or-assigned detail, filters, admin unchanged)
recorded at the end of `DECISIONS.md`.

---

## Increment 3.1 — City + ParkingLot catalogue ✅

### What it delivers

The parking catalogue's persistence and read/write API. No slots, tariffs or
rules yet (those are later increments).

### Files

| File | State |
|------|-------|
| `apps/parking/models.py` | `City`, `ParkingLot` (+ derived `code`, constraints) |
| `apps/parking/serializers.py` | `CitySerializer`, `ParkingLotSerializer` (read), `ParkingLotWriteSerializer` |
| `apps/parking/views.py` | `CityListCreateView`, `ParkingLotListCreateView`, `ParkingLotDetailView` |
| `apps/parking/urls.py` | city + lot routes |
| `config/urls.py` | mounts `apps.parking.urls` at `api/` |
| `apps/parking/admin.py` | registers both models (optional, for data inspection) |
| `apps/parking/migrations/0001_initial.py` | generated |
| `apps/parking/migrations/0002_seed_cities.py` | seeds ~15 well-known cities |
| `apps/parking/tests.py` | `CityModelTests`, `ParkingLotModelTests`, `ParkingApiTests` |

Suggested commit (PROJECT.md §43):
`feat(parking): add city and parking lot catalogue`

### Decisions realized in the code

- **D29** — surrogate `id` PK; `code` (`BLR-007`) derived in `ParkingLot.save()`,
  never accepted from the client (test: `test_client_supplied_code_is_ignored`).
- **D29-S1** — `City` lookup model, seeded by a data migration; codes
  canonicalised to upper case in `save()`.
- **D29-S2** — the Admin sends `city_code` + `number`; the backend joins them.
- **D30** — all writes are `IsAdmin`; reads are public.
- **D36** — single nullable `manager` FK, `SET_NULL`; `ParkingLotWriteSerializer`
  restricts the field to `role=MANAGER` accounts.
- **D37** — public reads (`AllowAny` on safe methods), Admin writes,
  `generics` + explicit URLs, no `PUT`/`DELETE`, non-Admin sees only
  `is_active=True`, inactive detail → `404` for non-Admins.
- **D38** — `is_active`/status flags; no hard delete.

### Endpoints added

| Method | Endpoint | Access |
|--------|----------|--------|
| GET | `/api/cities/` | public |
| POST | `/api/cities/` | Admin |
| GET | `/api/parking-lots/` (`?city=`, `?search=`) | public (active only) |
| POST | `/api/parking-lots/` | Admin |
| GET | `/api/parking-lots/{id}/` | public (active only) |
| PATCH | `/api/parking-lots/{id}/` | Admin |

### Verification

```bash
cd backend
../env/bin/python manage.py check
../env/bin/python manage.py test apps.parking
```

Expected: no check issues; **24 tests OK** (9 model + 15 API).

### Testing gotcha (already handled — remember it for later increments)

A **data migration runs when Django builds the test database**, so the seeded
cities (`BLR`, `DEL`, …) exist before any test. Test classes must therefore clear
or `get_or_create` the `City` table rather than assume it is empty. The current
tests use `City.objects.all().delete()` in `setUp` / `setUpTestData`. Every later
parking test meets the same seed data.

### Known, deliberate gaps from 3.1

- **Manager-scoped lot views were not built in 3.1.** A Manager once browsed
  active lots like a consumer; D37's assigned-lot scoping for the lot catalogue
  landed in 3.4 (slot/tariff scoping earlier).
- **No pagination** (Phase 10 hardening), consistent with accounts.
- **`City` has no update endpoint** — codes are immutable by design (D29-S1).

---

## Increment 3.2 — `ParkingSlot` ✅

### What it delivers

The slot model and its API: numbered, typed bays inside a lot, carrying only
**physical/operational** state. Writes are the first place **Invariant 3**
becomes real — a Manager may write only inside an assigned lot.

### Files

| File | State |
|------|-------|
| `apps/accounts/permissions.py` | `IsAdminOrManager` added (role gate for slot writes) |
| `apps/parking/models.py` | `ParkingSlot` (+ `SlotType`, `Status` enums, `UniqueConstraint`) |
| `apps/parking/serializers.py` | `ParkingSlotSerializer` (read), `ParkingSlotWriteSerializer` |
| `apps/parking/views.py` | `LotScopedMixin`, `ParkingSlotListCreateView`, `ParkingSlotDetailView` |
| `apps/parking/urls.py` | two nested slot routes |
| `apps/parking/admin.py` | registers `ParkingSlot` |
| `apps/parking/migrations/0003_parkingslot.py` | generated |
| `apps/parking/tests.py` | `ParkingSlotModelTests`, `ParkingSlotApiTests` |

Suggested commit (PROJECT.md §43):
`feat(parking): add parking slot model and API`

### Decisions realized in the code

- **D31** — manager-supplied `number`, unique per lot via
  `unique_slot_number_per_lot`; optional `floor` as
  `CharField(max_length=10, blank=True)`. `number` is canonicalised
  (`strip().upper()`) in both the model and the serializer, so `a-01` and `A-01`
  are one slot (the D13/D28/D29-S1 single-representation rule).
- **D32** — `slot_type` is a `TextChoices` enum:
  `REGULAR`, `COMPACT`, `LARGE`, `TWO_WHEELER`, `EV`.
- **D33 / D2 (revised)** — `status` stores `AVAILABLE` / `OCCUPIED` /
  `OUT_OF_SERVICE` only; `RESERVED` and `HELD` are absent and remain Phase 4/5
  derived values.
- **D38** — `status=OUT_OF_SERVICE` withdraws a slot; no hard `DELETE`. Phase 3
  writes accept only `AVAILABLE` / `OUT_OF_SERVICE`; `OCCUPIED` is written by
  Phase 6 occupancy actions.
- **D37 + Invariant 3** — reads public (active lot; a Manager also sees an
  assigned inactive lot, D38); writes require Admin **or** the lot's assigned
  Manager. Object scoping makes an unassigned lot a **`404`**, never a leak.
- **D31 (3.2 decision 1)** — `lot` FK is `on_delete=CASCADE`.

### Endpoints added

| Method | Endpoint | Access |
|--------|----------|--------|
| GET | `/api/parking-lots/{lot_pk}/slots/` | public (active lot) |
| POST | `/api/parking-lots/{lot_pk}/slots/` | Admin or the lot's Manager |
| GET | `/api/parking-lots/{lot_pk}/slots/{pk}/` | public (active lot) |
| PATCH | `/api/parking-lots/{lot_pk}/slots/{pk}/` | Admin or the lot's Manager |

### Verification

```bash
cd backend
../env/bin/python manage.py check
../env/bin/python manage.py test apps.parking
```

Expected: no check issues; **46 tests OK** (24 from 3.1 + 6 slot model + 16
slot API).

### Known, deliberate gaps from 3.2

- **No D34 "unpriced type" check yet.** Creating a slot of a type with no
  `Tariff` was allowed in 3.2; the rejection landed in 3.3 with `Tariff`
  (recorded in `DECISIONS.md`, increment 3.2 decisions; resolved by 3.3).
- **`OCCUPIED` is not settable through the slot API** — Phase 6 occupancy
  actions own that write (PROJECT.md §28 boundary).
- **Manager-scoped `GET /api/parking-lots/` was still not built in 3.2.** A
  Manager browsed the active lot list like a consumer; lot-level read scoping
  landed in 3.4. Slot reads already honoured manager assignment.
- **No pagination** (Phase 10), consistent with the rest.

---

## Increment 3.3 — `Tariff`, Invariant 4, `BusinessRule` ✅

### What it delivers

Pricing for a lot per slot type, plus the Administrator-defined ceiling that no
price may exceed. The **Invariant 4** check is born here and lives in
`apps/parking/services.py` (D35) — not the serializer — so no write path can
bypass it. This increment also lands the D34 check deferred from 3.2: a slot of
a type the lot has not priced cannot be created (and is not bookable in Phase 4).

### Files

| File | State |
|------|-------|
| `apps/parking/models.py` | `Tariff`, `BusinessRule` (+ constraints; `Decimal` import) |
| `apps/parking/services.py` | **created** — `set_tariff`, `set_max_hourly_rate`, the two errors |
| `apps/parking/serializers.py` | `TariffSerializer`, `TariffWriteSerializer`, `BusinessRuleSerializer`, `BusinessRuleUpdateSerializer`; D34 check in `ParkingSlotWriteSerializer.validate()` |
| `apps/parking/views.py` | `TariffListCreateView`, `TariffDetailView`, `BusinessRuleView` |
| `apps/parking/urls.py` | nested tariff routes + `/api/business-rules/` |
| `apps/parking/admin.py` | registers `Tariff`, `BusinessRule` |
| `apps/parking/migrations/0004_*.py` | generated |
| `apps/parking/tests.py` | `TariffModelTests`, `Invariant4ServiceTests`, `TariffApiTests`; existing slot API tests seed tariffs (decision 3A) |

Suggested commit (PROJECT.md §43):
`feat(parking): add tariff pricing and the max-rate business rule`

### Decisions realized in the code

- **D34** — `Tariff` per `(lot, slot_type)`, one `hourly_rate`
  (`DecimalField(max_digits=8, decimal_places=2)`, INR),
  `UniqueConstraint(lot, slot_type)`. The hour is the billing unit.
- **D35 / Invariant 4** — `BusinessRule.max_hourly_rate` caps every
  `hourly_rate`; the check is in `services.set_tariff`, inside
  `transaction.atomic`, after locking the `BusinessRule` row with
  `select_for_update`. Lowering the cap below an existing tariff is refused
  (`set_max_hourly_rate`), so the invariant cannot break at rest.
- **D35 singleton** — fixed PK: `BusinessRule.save()` pins `pk=1`;
  `BusinessRule.load()` `get_or_create`s the row. No seed migration.
- **D34 unpriced type (3.3 decision)** — creating a slot of an unpriced type is
  a `400`; changing a slot to one is the same. Only the type being set is
  checked, so other edits to an existing slot still work.
- **Q4 rate floor** — `hourly_rate` / `max_hourly_rate` must be `> 0`
  (`MinValueValidator` + `CheckConstraint`).
- **D37 / Invariant 3** — tariff writes are Admin or the lot's Manager via the
  shared `LotScopedMixin` + `IsAdminOrManager`; an unassigned lot is a `404`.
- **D37 reads** — tariffs and `GET /api/business-rules/` are public; writes are
  Admin/Manager. No `PUT`/`DELETE`.

### Endpoints added

| Method | Endpoint | Access |
|--------|----------|--------|
| GET | `/api/parking-lots/{lot_pk}/tariffs/` | public (active lot) |
| POST | `/api/parking-lots/{lot_pk}/tariffs/` | Admin or the lot's Manager |
| GET | `/api/parking-lots/{lot_pk}/tariffs/{pk}/` | public (active lot) |
| PATCH | `/api/parking-lots/{lot_pk}/tariffs/{pk}/` | Admin or the lot's Manager |
| GET | `/api/business-rules/` | public |
| PATCH | `/api/business-rules/` | Admin |

### Verification

```bash
cd backend
../env/bin/python manage.py check
../env/bin/python manage.py test apps.parking
```

Expected: no check issues; **~75 tests OK** (46 from 3.1/3.2 + 29 from 3.3).
Existing slot API tests gained tariff rows because the D34 check now rejects
creating a slot of an unpriced type.

### Known, deliberate gaps from 3.3

- **No `daily_rate`** — deliberately deferred (D34); the hour is the only unit.
- **`OCCUPIED` is still not settable through the slot API** — Phase 6 occupancy
  actions own that write (PROJECT.md §28 boundary).
- **Manager-scoped `GET /api/parking-lots/` is still not built** — see Next.
- **No pagination** (Phase 10), consistent with the rest.

---

## Increment 3.4 — manager-scoped lot reads ✅

### What it delivers

The lot catalogue read is now role-aware, completing the Invariant 3 surface that
slots (3.2) and tariffs (3.3) already enforced on writes. A Manager's
`GET /api/parking-lots/` returns their assigned lots (including deactivated
ones); the single-lot read is "active or assigned"; Consumers, anonymous
visitors and Administrators are unchanged.

### Files

| File | State |
|------|-------|
| `apps/parking/views.py` | `_visible_lot_catalogue`, `_addressable_lot` helpers; used by `ParkingLotListCreateView` / `ParkingLotDetailView` |
| `apps/parking/tests.py` | `ManagerScopedLotReadTests` |

Suggested commit (PROJECT.md §43):
`feat(parking): scope the lot catalogue reads to the manager`

### Decisions realized in the code

- **D37 / 3.4 decision 1a** — a Manager's list is assigned-only
  (`manager=user`), including inactive assigned lots (D38).
- **3.4 decision 2** — the single-lot read is
  `Q(is_active=True) | Q(manager=user)`, matching `LotScopedMixin`; because the
  read is public, a Manager is never shown less than an anonymous visitor.
- **3.4 decisions 3/4** — `?city=` / `?search=` filter the already-scoped set;
  an Administrator still sees every lot.
- **Deliberate asymmetry** — the list (assigned-only) and the detail
  (active-or-assigned) differ for a Manager; the detail is public and cannot be
  more restrictive than anonymous access.

### Endpoints affected

| Method | Endpoint | Change |
|--------|----------|--------|
| GET | `/api/parking-lots/` | Manager → assigned lots (incl. inactive); others unchanged |
| GET | `/api/parking-lots/{id}/` | Manager → active or assigned; others unchanged |

### Verification

```bash
cd backend
../env/bin/python manage.py check
../env/bin/python manage.py test apps.parking
```

Expected: no check issues; **89 tests OK** (75 from 3.3 + 14 from 3.4).

### Known, deliberate gaps from 3.4

- **No pagination** (Phase 10), consistent with the rest.
- **A Manager's list omits unassigned active lots** — by design (1a); a Manager
  can still read any active lot by id, because the detail read is public.

---

## Optional follow-ups (Phase 3 closed)

Phase 3's PROJECT.md §36 scope — `City` / `ParkingLot`, `ParkingSlot`, slot types,
pricing, manager assignment, and the manager-authorization rules (Invariants 3
and 4) — is fully delivered by increments 3.1–3.4. **Nothing below is a missing
requirement, and increment 3.5 as a parking increment is retired.** The items
were considered and are deliberately deferred; each names the phase that should
own it, so Phase 3 carries no open work.

| Idea | Deliberately deferred | Suggested landing phase |
|------|-----------------------|-------------------------|
| Lot availability summary (count of `AVAILABLE` slots per lot, optionally per type) | would duplicate the booking-aware availability query before Phase 4 defines it | **Phase 4** (with the time-window availability query), or **Phase 9** if only the UI needs it |
| Public lot filters by slot type / availability | depends on availability semantics | **Phase 4** (availability), or **Phase 9** (frontend-driven filters) |
| Pagination for the parking lists | Phase 10 hardening item across all list endpoints | **Phase 10** |

Rationale: the booking phase is where availability is actually defined, so
building a parking-side approximation now would mean designing it twice
(PROJECT.md §47 — no premature complexity; §38 — don't jump milestones).

**Next session:** open Phase 4 (Booking). It is the most important backend phase
(PROJECT.md §36) and its own decisions come first.

---

## Planned increments

| # | Increment | Status |
|---|-----------|--------|
| 3.1 | `City` + `ParkingLot` catalogue | ✅ Done |
| 3.2 | `ParkingSlot` model + API + tests | ✅ Done |
| 3.3 | `Tariff` per `(lot, slot_type)` + Invariant 4 (max rate) + `BusinessRule` singleton | ✅ Done |
| 3.4 | Manager-scoped lot catalogue reads (Invariant 3, remaining surface) | ✅ Done |
| ~~3.5~~ | ~~Consumer lot/slot refinements~~ — **retired**; ideas folded into Phase 4 / 9 / 10 | ⚪ — see "Optional follow-ups" |

**Phase 3 is closed:** all of its PROJECT.md §36 scope is done and verified
(89 tests green at close). No further parking increment is required; the only
post-close change is Phase 4's D45 duration fields (see the top of this file and
`DECISIONS.md`), which brings `apps.parking` to 103 tests.

> **Note:** D36 replaced the `ManagerLotAssignment` join table with a single
> `manager` FK on the lot, so there is no separate "assignment model" increment.
> Assignment is a `PATCH /api/parking-lots/{id}/` (Admin), already available.
> Invariant 3 enforcement is object-level ("is this manager the lot's manager?").
> **3.2 enforced it for slot writes** (and reads), **3.3 extended it to tariffs**,
> and **3.4 scoped the lot catalogue reads** — so Invariant 3 is now honoured on
> every parking surface.

---

## Dependencies on earlier phases

Read these **only** when a Phase 3 task touches them. Full entries live in the
foundation and Phase 2 decision files.

| Decision | Why Phase 3 needs it |
|----------|----------------------|
| **D2** — slot status is live state; availability derived | **Revised by D33**: stored state is physical only; `RESERVED`/`HELD` derive from bookings in Phase 4 |
| **D4** — PostgreSQL mandatory | Unique/check constraints rely on real DB constraints |
| **D5** — store UTC, business tz | Timestamps; reporting is Phase 8 |
| **D11** — custom `User`, single `role` | `manager` FK points at a `User` with `role=MANAGER` |
| **D15** — role read from DB per request | Authorization reads `request.user.role` |
| **D18** — deny-by-default permissions | New endpoints default to `IsAuthenticated`; opt out explicitly (D37 opts out for reads) |
| **D20 / D24 / D26** — Admins create accounts / user mgmt | Lot creation and manager accounts are Administrator-owned |
| **D28** — `Vehicle` | The `Vehicle → Booking → Slot` chain starts here; unused until Phase 4 |

**Existing patterns to reuse (from `apps/accounts/`):**

- `apps/accounts/permissions.py` — `HasRole` + `IsConsumer` / `IsManager` /
  `IsAdmin`. It answers role only; object-level "is this manager the lot's
  manager" is done by scoping the queryset/view.
- `apps/accounts/services.py` — where business logic beyond validation lives
  (the D24 guard is there). Phase 3 rules belong in `apps/parking/services.py`.
- Read/write serializer split; explicit `generics.*` + hand-written `urls.py`.

---

## Boundary with Phase 4 (do not cross)

- **Time-window availability is Phase 4.** Phase 3 exposes a slot's current
  `status` only; the "free between 3pm and 5pm?" query arrives with the booking
  availability endpoint. Do not fake it.
- **`RESERVED`/`HELD` are Phase 4/5 values**, derived from bookings. Never store
  them on the slot (D33).
- **Occupancy simulation is Phase 6.** Phase 3 may expose `status`; it does not
  build the manager occupancy controls.
- **No booking references yet**, so slot delete semantics stay simple; V6
  (vehicle delete) is Phase 4.
