# Progress — Phase 3 (Parking domain) 🟡 IN PROGRESS

> **Scope (PROJECT.md §36):** `ParkingLot`, `ParkingSlot`, slot types, pricing and
> manager assignment, plus the manager-authorization and lot-assignment rules.
> Decisions are in [`DECISIONS.md`](DECISIONS.md) (D29–D38, all **accepted**).
> Working conventions and the reading protocol: [`../README.md`](../README.md).

Last updated: 2026-10-01 · **Increment 3.1 complete.** Next: **increment 3.2 —
`ParkingSlot`** (see "Start here" below).

---

## Start here (fresh session)

Reading order — do not read anything else unless a task needs it:

1. [`../README.md`](../README.md) — conventions + reading protocol.
2. This file — state, what 3.1 built, and the 3.2 brief.
3. [`DECISIONS.md`](DECISIONS.md) — D29–D38 (the parking decisions).
4. Only if a task touches it: the "Dependencies on earlier phases" table below.

Then: answer the "Decisions to confirm at the start of 3.2" list, and build
increment 3.2 only.

---

## Decision status

All parking decisions are **accepted** (full entries in `DECISIONS.md`):
D29 (+ S1, S2), D30, D31, D32, D33 (**revises D2**), D34, D35, D36, D37, D38.

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

Expected: no check issues; **24 tests OK** (10 model + 14 API).

### Testing gotcha (already handled — remember it for later increments)

A **data migration runs when Django builds the test database**, so the seeded
cities (`BLR`, `DEL`, …) exist before any test. Test classes must therefore clear
or `get_or_create` the `City` table rather than assume it is empty. The current
tests use `City.objects.all().delete()` in `setUp` / `setUpTestData`. Every later
parking test meets the same seed data.

### Known, deliberate gaps from 3.1

- **Manager-scoped lot views are not built.** A Manager currently browses active
  lots like a consumer; D37 says a Manager should see assigned lots. This lands
  with the slot/manager-authorization work (3.2/3.4).
- **No pagination** (Phase 10 hardening), consistent with accounts.
- **`City` has no update endpoint** — codes are immutable by design (D29-S1).

---

## Next — increment 3.2: `ParkingSlot`

### Goal

The slot model and its API: numbered slots inside a lot, typed, with stored
physical state. Model + migration + tests first, then the API (same two-part
shape as 3.1), unless the developer prefers it whole.

### Decisions already made (do not re-litigate)

- **D31** — manager-supplied `number` (string), unique per lot; optional `floor`.
- **D32** — `slot_type` is a `TextChoices` enum.
- **D33 / D2 (revised)** — `status` stores `AVAILABLE` / `OCCUPIED` /
  `OUT_OF_SERVICE` only; `RESERVED` and `HELD` are **derived in Phase 4** and
  must never be stored on the slot.
- **D38** — `OUT_OF_SERVICE` (not deletion) withdraws a slot; no hard `DELETE`.
- **D37** — reads public; writes restricted (Admin, or the lot's assigned
  Manager — this is where object-level Invariant 3 first becomes real).

### Decisions to confirm at the start of 3.2 (small — surface, don't assume)

1. **`lot` FK `on_delete`** — **CASCADE** (recommended: a slot has no meaning
   without its lot; D38 already forbids lot deletion via the API) vs `PROTECT`.
2. **`floor` type** — optional `CharField(max_length=10, blank=True)`
   (recommended: floors read naturally as `G`, `1`, `B1`) vs `IntegerField`.
3. **Final `slot_type` list** (D32 left this open): recommended
   `REGULAR`, `COMPACT`, `LARGE`, `TWO_WHEELER`, `EV`; add `ACCESSIBLE` only if
   required.
4. **Manager write enforcement in the slot API** — enforce "Admin **or**
   `lot.manager == request.user`" now (recommended; realizes Invariant 3 for
   slots), or defer all manager writes to a later increment and ship model +
   Admin-only API in 3.2.
5. **Ordering vs. pricing (D34).** D34 says creating a slot of a *priced-less*
   type is rejected, but `Tariff` does not exist until 3.3. Options:
   (a) build slots in 3.2 without that check and add it in 3.3 (recommended —
   keeps increments small and the rule lands with the data it needs);
   (b) swap the order: `Tariff` first, then slots, so the check exists from the
   start. Record whichever is chosen.

### Files 3.2 will touch

| File | Change |
|------|--------|
| `apps/parking/models.py` | add `ParkingSlot` |
| `apps/parking/migrations/0003_parking_slot.py` | generated (PROJECT.md §42) |
| `apps/parking/serializers.py` | `ParkingSlot` read/write serializers |
| `apps/parking/views.py` | slot views (nested under the lot for listing/creation) |
| `apps/parking/urls.py` | slot routes |
| `apps/parking/tests.py` | model + API tests |

### Patterns to reuse (from 3.1 / accounts)

- Derived/validated write shape, read shape returned from POST/PATCH
  (`VehicleSerializer` / `VehicleWriteSerializer`, `ParkingLotSerializer` /
  `ParkingLotWriteSerializer`).
- `get_permissions()` returning `[AllowAny()]` for safe methods and role
  permissions otherwise.
- Pre-check uniqueness in the serializer for a clean `400`; keep the DB
  `UniqueConstraint` as the concurrent backstop.
- Business logic beyond validation goes in `apps/parking/services.py`
  (created when needed).

---

## Planned increments

| # | Increment | Status |
|---|-----------|--------|
| 3.1 | `City` + `ParkingLot` catalogue | ✅ Done |
| 3.2 | `ParkingSlot` model + API + tests | ▶ Next |
| 3.3 | `Tariff` per `(lot, slot_type)` + Invariant 4 (max rate) + `BusinessRule` singleton | ⚪ |
| 3.4 | Manager-to-lot authorization across slot/tariff writes (Invariant 3) | ⚪ |
| 3.5 | Consumer lot search / slot listing refinements | ⚪ |

Not a commitment: PROJECT.md §38 forbids jumping milestones; each row starts
only after the previous is verified.

> **Note:** D36 replaced the `ManagerLotAssignment` join table with a single
> `manager` FK on the lot, so there is no separate "assignment model" increment.
> Assignment is a `PATCH /api/parking-lots/{id}/` (Admin), already available.
> Invariant 3 enforcement is object-level ("is this manager the lot's manager?").

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
