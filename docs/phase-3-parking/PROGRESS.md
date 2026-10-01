# Progress — Phase 3 (Parking domain) 🟡 IN PROGRESS

> **Scope (PROJECT.md §36):** `ParkingLot`, `ParkingSlot`, slot types, pricing and
> manager assignment, plus the manager-authorization and lot-assignment rules.
> Decisions are in [`DECISIONS.md`](DECISIONS.md) (D29–D38, all **accepted**,
> plus the increment-3.2 refinements at the end of that file).
> Working conventions and the reading protocol: [`../README.md`](../README.md).

Last updated: 2026-10-01 · **Increment 3.2 complete.** Next: **increment 3.3 —
`Tariff`, Invariant 4 and the `BusinessRule` singleton** (see "Next" below).

---

## Start here (fresh session)

Reading order — do not read anything else unless a task needs it:

1. [`../README.md`](../README.md) — conventions + reading protocol.
2. This file — state, what 3.2 built, and the 3.3 brief.
3. [`DECISIONS.md`](DECISIONS.md) — D29–D38 (the parking decisions).
4. Only if a task touches it: the "Dependencies on earlier phases" table below.

Then: answer the "Decisions to confirm at the start of 3.3" list, and build
increment 3.3 only.

---

## Decision status

All parking decisions are **accepted** (full entries in `DECISIONS.md`):
D29 (+ S1, S2), D30, D31, D32, D33 (**revises D2**), D34, D35, D36, D37, D38,
plus the **Increment 3.2 implementation decisions** recorded at the end of
`DECISIONS.md` (FK cascade, `floor` type, final `slot_type` enum, manager slot
writes, D34 ordering, status-write scope).

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

- **Manager-scoped lot views are not built.** A Manager currently browses active
  lots like a consumer; D37 says a Manager should see assigned lots. Slot
  reads/writes already honour manager assignment (3.2); the manager-scoped lot
  *list* remains for 3.4/3.5.
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
  `Tariff` is currently allowed; the rejection lands in 3.3 with `Tariff`
  (recorded in `DECISIONS.md`, increment 3.2 decisions).
- **`OCCUPIED` is not settable through the slot API** — Phase 6 occupancy
  actions own that write (PROJECT.md §28 boundary).
- **Manager-scoped `GET /api/parking-lots/` is still not built.** A Manager
  browses the active lot list like a consumer; lot-level scoping for reads
  arrives with a later lot-catalogue refinement (3.4/3.5). Slot reads already
  honour manager assignment.
- **No pagination** (Phase 10), consistent with the rest.

---

## Next — increment 3.3: `Tariff`, Invariant 4, `BusinessRule`

### Goal

Price a lot per slot type and cap it. A `Tariff` row per `(lot, slot_type)`
carrying an `hourly_rate` in INR; a `BusinessRule` singleton carrying the
Administrator-defined `max_hourly_rate`; and the Invariant 4 rule
`hourly_rate <= max_hourly_rate` enforced in `apps/parking/services.py`
(D35 — not in the serializer, so no caller can bypass it). This increment also
adds the deferred D34 check: a slot whose `(lot, slot_type)` has no tariff is
not bookable, and creating such a slot is rejected.

### Decisions already made (do not re-litigate)

- **D34** — `Tariff` per `(lot, slot_type)`; one `hourly_rate`,
  `DecimalField(max_digits=8, decimal_places=2)`, INR; `UniqueConstraint(lot,
  slot_type)`. Hour is the billing unit; `daily_rate` deliberately deferred.
- **D35** — `BusinessRule` singleton with `max_hourly_rate`; the
  `hourly_rate <= max_hourly_rate` check lives in `apps/parking/services.py`;
  lowering the maximum while any existing tariff exceeds it is **rejected**, so
  the invariant never breaks at rest. Only the field this phase needs — the
  other §19 fields arrive in their own phases.
- **Invariant 3** — tariff writes are Admin or the lot's Manager, using the same
  `LotScopedMixin` + `IsAdminOrManager` mechanism as slots.
- **D37** — style: `generics.*` + hand-written `urls.py`; reads public where the
  data is non-PII.

### Decisions to confirm at the start of 3.3 (small — surface, don't assume)

1. **`BusinessRule` singleton strategy** (D35 left this open): a **fixed-PK
   row** (`pk=1`, created/fetched by a `load()` classmethod) vs a
   **refuse-a-second-row** `save()` guard. Fixed PK is simpler and makes "the
   rule" unambiguous; recommend fixed PK.
2. **Rejecting a lowered maximum**: `400` (validation-shaped) vs `409` with a
   stable `error` code like `LAST_ADMINISTRATOR` (accounts precedent). A
   conflict is arguably a `409`; recommend `409` with
   `{"error": "MAX_RATE_BELOW_TARIFF", ...}` (PROJECT.md §33).
3. **Where the D34 check applies.** Existing 3.2 slots of unpriced types may
   already exist. Options: (a) enforce only on **new** slot creation and on
   booking (grandfather existing rows); (b) also expose an "unpriced slot" flag
   in the read shape so Managers can find them; (c) treat it purely as a
   Phase 4 booking-time rule and not reject slot creation at all. Recommend
   **(a)** now, with (b) noted for later if needed — it matches D34's wording
   without retroactively breaking saved data.
4. **Is `hourly_rate = 0` allowed?** Recommend **no**: require `> 0` (a
   free-but-priced bay is a modelling smell; use `OUT_OF_SERVICE` for
   withdrawal). Confirm the `MinValueValidator`.
5. **Tariff reads**: public like the lot catalogue (a consumer needs to see
   prices to choose) vs authenticated-only. Recommend **public read**, writes
   Admin/Manager — consistent with D37.
6. **Tariff endpoints**: nested `/api/parking-lots/{lot_pk}/tariffs/`
   (+ `/{pk}/`) and a flat `/api/business-rules/` singleton. Confirm names.

### Files 3.3 will touch

| File | Change |
|------|--------|
| `apps/parking/models.py` | add `Tariff`, `BusinessRule` |
| `apps/parking/migrations/0004_*.py` | generated (PROJECT.md §42) |
| `apps/parking/services.py` | **created** — the Invariant 4 check + singleton access |
| `apps/parking/serializers.py` | `Tariff` and `BusinessRule` read/write serializers |
| `apps/parking/views.py` | tariff views (nested) + business-rule view (singleton) |
| `apps/parking/urls.py` | tariff + business-rule routes |
| `apps/parking/admin.py` | register `Tariff`, `BusinessRule` |
| `apps/parking/tests.py` | model + service + API tests |

### Patterns to reuse (from 3.1 / 3.2 / accounts)

- `LotScopedMixin` + `IsAdminOrManager` for the nested tariff views (Invariant 3
  for free, with `404` scoping).
- Read/write serializer split; POST/PATCH return the read shape.
- Pre-check uniqueness `(lot, slot_type)` in the serializer for a clean `400`;
  keep the DB `UniqueConstraint` as the concurrent backstop.
- Business logic beyond validation goes in `apps/parking/services.py` — the
  Invariant 4 check and the D35 "cannot lower the cap below an existing tariff"
  guard both belong there, ideally inside one `transaction.atomic` with
  `select_for_update` (the `update_user_access` pattern, D27).

---

## Planned increments

| # | Increment | Status |
|---|-----------|--------|
| 3.1 | `City` + `ParkingLot` catalogue | ✅ Done |
| 3.2 | `ParkingSlot` model + API + tests | ✅ Done |
| 3.3 | `Tariff` per `(lot, slot_type)` + Invariant 4 (max rate) + `BusinessRule` singleton | ▶ Next |
| 3.4 | Manager-to-lot authorization across slot/tariff writes (Invariant 3) | ⚪ — **partly absorbed into 3.2/3.3** |
| 3.5 | Consumer lot search / slot listing refinements | ⚪ |

Not a commitment: PROJECT.md §38 forbids jumping milestones; each row starts
only after the previous is verified.

> **Note:** D36 replaced the `ManagerLotAssignment` join table with a single
> `manager` FK on the lot, so there is no separate "assignment model" increment.
> Assignment is a `PATCH /api/parking-lots/{id}/` (Admin), already available.
> Invariant 3 enforcement is object-level ("is this manager the lot's manager?").
> **3.2 already enforced it for slot writes** (and reads), and **3.3 extends it
> to tariffs** through the shared `LotScopedMixin`; the remaining exposed
> surface is the manager-scoped `GET /api/parking-lots/` list, so increment 3.4
> is largely absorbed and may be re-scoped or dropped when 3.3 lands.

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
