# Phase 3 decisions — Parking domain

Status as of **2026-10-03**:

- **Accepted:** D29 (incl. S1 and S2 below), D30, D31, D32, D33 (revises D2),
  D34, D35, D36, D37, D38.
- **Open:** none. Increment 3.3 is complete; its decisions are recorded in the
  "Increment 3.3 implementation decisions" section at the end of this file.
  The next increment (3.4) is manager-scoped lot catalogue reads.

> A "Decision" below is the human's, not the agent's. Rationale/Consequence
> record why, so the choice can be defended later.

---

## D2 revision — stored slot states (accepted via D33)

D2 originally listed `AVAILABLE`, `HELD`, `OCCUPIED`, `OUT_OF_SERVICE` as stored
physical state. PROJECT.md §18 instead lists `RESERVED` and explicitly warns not
to collapse **physical occupancy**, **booking reservation** and **temporary
hold**. D33 therefore revises D2's *enumeration* (the principle is unchanged):

- **D2 (revised):** `ParkingSlot.status` stores only **physical/operational**
  state — `AVAILABLE`, `OCCUPIED`, `OUT_OF_SERVICE`. `RESERVED` and `HELD` are
  **derived from bookings** in Phase 4/5 and must never be stored on the slot.
- The revision is recorded in
  [`../foundation/DECISIONS.md`](../foundation/DECISIONS.md) as a note on D2.

---

## D29 — `ParkingLot` identity (accepted)

- **Decision:** A surrogate `BigAutoField` is the real primary key. The lot also
  carries a **unique canonical `code`** formed from a **city code + a per-city
  number**, e.g. `BLR-001`. The client/Admin supplies the parts (like the
  vehicle plate segments, D28); the backend joins and normalises them. The
  database unique constraint is the backstop; the serializer pre-checks so a
  duplicate is a clean `400`. The API may later address lots by `code` via
  `lookup_field="code"`.
- **Rationale:** This gives the citycode-numeric identifier without a natural
  primary key. A formatted-string PK would make every child FK a meaningful
  string, make renaming a city code a cascade rewrite (PKs are immutable), and
  force a race-prone "next number" counter. A surrogate key keeps FKs small,
  stable and opaque; the business code stays a display/reference concern. The
  pattern deliberately mirrors D28's canonical-plate design.
- **Consequence:** `code` is derived at write time (like the lower-cased email,
  D13, and the canonical plate). Uniqueness is enforced on `code` and on
  `(city, number)`.
- **Status:** Accepted in principle. Two implementation sub-decisions remain.

### D29-S1 — how city codes are stored (accepted)

The full Indian city-code database is infeasible (the developer's point: it is
as large as the railway station-code list). The agreed approach: **seed a small
set of well-known city codes and let an Administrator add new ones** through the
API.

- **Option A — a `City` lookup model** (`code` unique, `name`), seeded by a data
  migration, with an Administrator list/create surface; `ParkingLot.city` is a
  FK. Controlled vocabulary, city names for display/search, referential
  integrity, and a place to hang regional grouping later. Cost: one extra model
  + endpoint + seed migration. `City` is **not** in PROJECT.md §15's entity
  list.
- **Option B — `city_code` + `city_name` CharFields on the lot**, validated
  against a seeded constant. No new model, but the vocabulary is not stored
  centrally, so a typo can create a near-duplicate city.

**Decision (Option A):** `City` lookup model, seeded by a data migration.
City codes are **immutable after creation** — the API exposes list/create only
(no `PATCH`), because every lot `code` is derived from the city code and a
change would invalidate them. An Administrator adds a new city before creating
its first lot.
- **Status:** Accepted.

### D29-S2 — who supplies the lot number (accepted)

- **Option A — Administrator types the number**, uniqueness enforced per city
  (mirrors the typed plate segments, D28). No race; duplicate → clean `400`.
- **Option B — the backend allocates the next number per city** automatically.
  Friendlier, but "next number" is a check-then-act race needing a retry or a
  locked per-city counter.

**Decision (Option A):** the Administrator types the number; the backend joins
`CITY-NNN` and enforces uniqueness.
- **Status:** Accepted.

---

## D30 — Lot lifecycle ownership (accepted)

- **Decision:** The **Administrator creates, edits and deactivates** a
  `ParkingLot` and **assigns its manager**. The **Manager operates only inside
  an assigned lot** — slots, tariffs within the maximum, occupancy — and cannot
  create, delete or reassign a lot.
- **Rationale:** This is PROJECT.md §16 ("Administrator … manage parking lots",
  "assign managers to lots"; Manager manages *assigned* lots). Manager-created
  lots would make Invariant 3 vacuous for creation (any Manager could mint lots
  for any city) and remove the gatekeeper between a Manager and the platform.
- **Consequence:** The chicken-and-egg ("a lot must exist before it can be
  assigned") is resolved by the Administrator creating it unassigned or assigned
  in one action. An unassigned lot has no operating Manager.

---

## D31 — Slot numbering (accepted)

- **Decision:** A slot's identifier within a lot is a **manager-supplied
  `number`** (string, e.g. `A-01`), required and non-blank, with a
  `UniqueConstraint(lot, number)`. An optional `floor` may be recorded.
- **Rationale:** Matches physical bay signage, lets the manager keep their own
  scheme, and the same number in two different lots is independent. Auto
  sequencing or structured (floor/row/position) layouts add burden without a
  requirement.
- **Consequence:** Duplicate number within a lot is a clean `400`; slot identity
  is stable for the whole booking lifetime (Phase 4).

---

## D32 — Slot types (accepted)

- **Decision:** Slot types are a **`TextChoices` enum** on `ParkingSlot`
  (`REGULAR`, `COMPACT`, `LARGE`, `TWO_WHEELER`, `EV`; add `ACCESSIBLE` only if
  required). Not a `SlotType` table.
- **Rationale:** The types are fixed domain knowledge; a table would add a model,
  an Admin surface and retirement handling for flexibility nothing has asked for
  (PROJECT.md §47). Adding a type later is a migration.
- **Consequence:** Pricing (D34) keys on this enum value. If the SRS later
  demands Administrator-defined types, that is a deliberate model change.

---

## D33 — Slot state model (accepted — see the D2 revision above)

- **Decision:** `ParkingSlot.status` stores **`AVAILABLE` / `OCCUPIED` /
  `OUT_OF_SERVICE`** only. `RESERVED` and `HELD` are derived from bookings.
- **Rationale:** Physical occupancy is genuinely manual/simulated state (Phase 6)
  and is not derivable; reservation and hold are `booking + time` derived.
  Storing them is exactly the drift D2 warns about and the collapse §18 forbids.
- **Consequence:** Consumer/manager reads that need "reserved now" must combine
  `status` with a booking lookup — Phase 4's availability query. Until then the
  slot listing shows stored state only (the D37 boundary).
- **Status:** Accepted, and it **revises D2** as recorded above.

---

## D34 — Pricing granularity (accepted)

- **Decision:** A `Tariff` row per **`(lot, slot_type)`** carries one
  `hourly_rate`, a `DecimalField(max_digits=8, decimal_places=2)` in **INR**.
  `UniqueConstraint(lot, slot_type)`. A slot whose `(lot, slot_type)` has no
  tariff is **not bookable**, and creating a slot of an unpriced type is rejected
  at the API.
- **Rationale:** Different vehicle sizes/energy types price differently; keying
  off `(lot, slot_type)` matches real lots and gives Invariant 4 one obvious
  field to cap. `Decimal`, never `float`, because binary floats cannot represent
  money exactly. The hour is the billing unit (PROJECT.md §19's overstay uses
  "hourly rate").
- **Consequence:** Managers set rates per type; a `daily_rate` is deliberately
  deferred as speculative.

---

## D35 — Administrator maximum rate / Invariant 4 (accepted)

- **Decision:** A **`BusinessRule` singleton** row carries `max_hourly_rate`
  (Admin-editable). The check `hourly_rate <= max_hourly_rate` lives in
  `apps/parking/services.py`, not the serializer, so no caller can bypass it
  (same reasoning as D27). Lowering the maximum while any existing tariff
  exceeds it is rejected, so the invariant is never violated by data at rest.
- **Rationale:** Invariant 4 is singular ("the Administrator-defined maximum")
  and §16 gives Administrators "configure global business rules". The singleton
  carries only the field this phase needs; the other §19 rule fields (hold
  minutes, cancellation cutoff, overstay multiplier) are added in their own
  phases (PROJECT.md §41 — no speculative fields).
- **Consequence:** A single-row strategy is needed (fixed PK or a
  refuse-a-second-row manager); the Admin surface for it is a Phase 3 increment.

---

## D36 — Manager assignment (accepted)

- **Decision:** A **single nullable `manager` FK on `ParkingLot`** (one manager
  per lot; a manager may hold many lots). Assignment is done by an Administrator
  (via the lot update surface); unassigning sets it to null. The
  `ManagerLotAssignment` entity named in PROJECT.md §15 is **deliberately not
  created**.
- **Rationale:** The developer rejected multiple concurrent managers as
  unjustified (ambiguous responsibility, complex Invariant 3), so a join table's
  only remaining value would be history. History is better owned by the records
  themselves: Phase 4 bookings and Phase 6 occupancy actions will store
  `created_by`, so a handover does not hide past entries — the new manager sees
  them as the lot's history. Assignment *history* ("who held lot 7 last month")
  is the deferred `AuditLog`'s job.
- **Consequence:** Deviation from §15's entity list must be documented (it is).
  Phase 4 must record the acting user on bookings/occupancy; that will be
  surfaced as its own decision then.

---

## D38 — Deactivation and deletion (accepted)

- **Decision:** Lifecycle **flags only; no hard `DELETE` via the API** for lots
  or slots. `ParkingLot.is_active=False` hides a lot from consumers and blocks
  booking; `ParkingSlot.status=OUT_OF_SERVICE` withdraws one slot (Invariant 5).
  Unassigning a manager sets `lot.manager = null` (an authority change, not a
  historical record).
- **Rationale:** Avoids the "deleted a slot that has history" bug class and
  keeps Phase 8 reports correct (a hard-deleted lot cannot be reported on). §16
  frames slots as available/unavailable, and §28 as simulated occupancy.
- **Consequence:** Deactivated lots still appear to Managers/Administrators, not
  to consumers. Hard delete is revisited only if a real requirement appears.

---

## D37 — API surface, permissions and the availability boundary (accepted)

Names follow PROJECT.md §22 ("starting points, not immutable").

| Method | Endpoint | Consumer | Manager | Admin |
|--------|----------|----------|---------|-------|
| GET | `/api/cities/` | ✅ (list) | ✅ | ✅ |
| POST | `/api/cities/` | — | — | ✅ |
| GET | `/api/parking-lots/` | active lots (search `city`, `search`) | assigned lots | all |
| POST | `/api/parking-lots/` | — | — | ✅ |
| GET | `/api/parking-lots/{id}/` | active only | assigned only | all |
| PATCH | `/api/parking-lots/{id}/` | — | — | ✅ (incl. `manager`, `is_active`) |

- **Style:** `generics.*` views + a hand-written `urls.py` (current project
  style), **not** `ViewSet` + `DefaultRouter`.
- **Reads:** the **catalogue is public** — `AllowAny` on `GET /api/cities/`,
  `GET /api/parking-lots/` and `GET /api/parking-lots/{id}/`, so a visitor can
  browse before signing in (how real parking apps behave). This is a deliberate,
  documented opt-out of D18 for read-only, non-PII data. All writes require
  `IsAdmin`. Only `is_active=True` lots are visible to non-Administrators.
  Manager-scoped lot views land with the assignment increment (D36).
- **Boundary:** Phase 3 slot listing returns current `status` only; the
  time-window availability query (`?start=&end=`) is **Phase 4**, because it
  depends on bookings.
- **No pagination** (consistent with `/api/users/`, `/api/vehicles/`); Phase 10.
- **Unassigned/unowned access returns `404`, not `403`** (same rule as D28), so
  the API does not leak which lots exist.

**Status:** Accepted (2026-10-01). The developer delegated the style/permission
choice with the instruction to do "what's best according to a real world parking
system and user convenience"; the public-read decision above follows that.
Increment 3.1 implements the city and lot catalogue endpoints; increment 3.2
implements the nested slot endpoints (permissions and scoping as described
above).

---

## Increment 3.2 implementation decisions (accepted 2026-10-01)

These settle the questions D31/D32 left open and the ordering question for the
`ParkingSlot` increment. They refine D29–D38; they do not replace them.

- **D31 — slot `lot` FK deletion behaviour** — `ParkingSlot.lot` uses
  `on_delete=CASCADE`. A slot has no meaning without its lot, and D38 already
  forbids lot deletion through the API, so this only governs direct DB/admin
  deletion. Mirrors the `Vehicle → owner` precedent (V4).
- **D31 — `floor` type** — optional `CharField(max_length=10, blank=True)`, so
  `G`, `1`, `B1`, `Basement-2` all read naturally.
- **D32 — final `slot_type` enum** — `REGULAR`, `COMPACT`, `LARGE`,
  `TWO_WHEELER`, `EV`. `ACCESSIBLE` is deliberately not added (no SRS
  requirement; adding a type later is a migration, D32).
- **D37 — manager slot writes** — enforced now, not deferred to 3.4: a slot
  write requires an Administrator **or** the lot's assigned Manager.
  Object-level enforcement is done by scoping the lot queryset, so an
  unassigned/unowned lot is a **`404`, never a leak** (consistent with D37/D28).
- **D34 — ordering** — slots are built in 3.2 **without** the "creating a slot of
  an unpriced type is rejected" check; that check lands in 3.3 together with
  `Tariff`, the data it needs. Recorded as a deliberate temporary gap.
- **D38 — slot status writes** — a Phase 3 caller (Admin or the lot's Manager)
  may set only `AVAILABLE` / `OUT_OF_SERVICE` through the slot API. `OCCUPIED`
  is written by Phase 6 occupancy actions, not by this increment (PROJECT.md §28
  boundary). The model still stores all three values (D33).

---

## Increment 3.3 implementation decisions (accepted 2026-10-03)

These settle the questions D34/D35 left open and record the API and business
choices made while building `Tariff`, Invariant 4 and the `BusinessRule`
singleton. They refine D34/D35/D37; they do not replace them.

- **D35 — singleton strategy (Q1)** — fixed PK. `BusinessRule.save()` pins
  `pk=1`; `BusinessRule.load()` `get_or_create`s the row. One row, no ambiguity,
  no seed migration. Rejected: a refuse-a-second-row `save()` guard — more code
  for a case the API cannot reach.
- **D35 — lowering the cap (Q2)** — lowering `max_hourly_rate` below an existing
  tariff is refused with `409` and
  `{"error": "MAX_RATE_BELOW_TARIFF", "message": ...}` (PROJECT.md §33; the
  accounts `LAST_ADMINISTRATOR` precedent). The cap is left unchanged, so
  Invariant 4 holds at rest.
- **D35 — tariff above the cap** — refused with `400 {"hourly_rate": [...]}`
  (the submitted value is out of range, so the error is field-shaped). The check
  itself still lives in `services.set_tariff`, not the serializer.
- **D34 — unpriced slot types (Q3)** — creating a slot whose `(lot, slot_type)`
  has no tariff is refused with `400 {"slot_type": [...]}`; changing an existing
  slot *to* an unpriced type is refused the same way. Only the type being set is
  checked, so an existing slot can still have its number/floor/status edited.
  Enforced in `ParkingSlotWriteSerializer.validate()`; Phase 4 re-checks at
  booking time. No grandfathering was needed — the database held no stale slots.
- **D34 / Q4 — rate floor** — `hourly_rate` and `max_hourly_rate` must be
  `> 0`, enforced by `MinValueValidator(Decimal("0.01"))` at the serializer and
  model plus a `CheckConstraint` at the database.
- **D35 — concurrency** — `services.set_tariff` and
  `services.set_max_hourly_rate` both run in `transaction.atomic` and lock the
  `BusinessRule` row with `select_for_update` first, so a tariff write and a cap
  change serialise and Invariant 4 cannot be broken by a race (the D27
  `update_user_access` pattern).
- **D34 / Invariant 3 — tariff writes** — Admin or the lot's Manager, via the
  shared `LotScopedMixin` + `IsAdminOrManager`; an unassigned lot is a `404`.
  Invariant 3 now covers tariffs as well as slots.
- **D37 — reads (Q5/Q6)** — tariff reads and `GET /api/business-rules/` are
  public (non-PII; a consumer needs prices to choose, a Manager needs the cap to
  price within it). Writes are Admin/Manager. URLs are nested
  `/api/parking-lots/{lot_pk}/tariffs/` (+ `/{pk}/`) and flat
  `/api/business-rules/`. No `PUT`/`DELETE`.
- **D35 — default cap** — a first-created singleton defaults to
  `max_hourly_rate = 100.00` INR, created lazily by `BusinessRule.load()` (no
  data migration). The Administrator edits it via `PATCH /api/business-rules/`.
