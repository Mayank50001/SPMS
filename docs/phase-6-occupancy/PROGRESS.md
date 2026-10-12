# Progress — Phase 6 (Occupancy simulation) 🚧 IN PROGRESS — 6.1–6.3 done

> **Scope (PROJECT.md §36):** software-controlled slot occupancy, Manager
> occupancy controls, booking/occupancy interaction and entry/exit simulation.
> **No hardware** (§4: no sensors, gates, barriers, ANPR). This phase also
> completes the **manager/admin workflow** by adding **operator booking reads**
> (6.1) before the frontend starts.
> Working conventions and the reading protocol: [`../README.md`](../README.md).
> Phase 4/5 context (the seams and rules this phase builds on):
> [`../phase-4-booking/PROGRESS.md`](../phase-4-booking/PROGRESS.md),
> [`../phase-5-payment/PROGRESS.md`](../phase-5-payment/PROGRESS.md).

Last updated: **2026-10-13** · **6.1–6.3 done; 6.4 next (settle D70).**

---

## Agreed ordering (decided 2026-10-12)

The frontend (Phase 9) **waits** until the manager/admin workflow is complete:

```text
Phase 6 (occupancy + operator booking reads)
        ↓
Phase 8 (reports — the manager/admin dashboards)
        ↓
Phase 9 (React frontend)
```

**Phase 7 (notifications) is deferred** until after the frontend. **Walk-in /
cash (D63) stays deferred.** Rationale: many §30 manager/admin pages
(Dashboard, Reports, occupancy) are empty without Phases 6 and 8, so the
frontend would otherwise be built against half-finished operator flows.

> **Prerequisite (met):** D66 (paginated envelope) is applied — commit
> `a4a0a4b` added `config/pagination.py` project-wide, so the operator booking
> list can be a paginated collection read.

---

## Start here (fresh session)

1. [`../README.md`](../README.md) — conventions + reading protocol.
2. This file — scope, the increment plan, what is next.
3. [`DECISIONS.md`](DECISIONS.md) — **D67** (6.1), **D68** (6.2) and **D69** (6.3)
   implemented; D70–D72 open, each to be settled with the human *before* its
   increment's code.
4. Only if a task touches them: the "Dependencies on earlier phases" table below.

---

## Increment plan

> **Draft — confirm at phase open.** Each increment is a coherent feature and
> surfaces its decision **before** its code, recorded as its own `D<n>`.

> **Implementation order (revised 2026-10-13):** `6.1 → 6.3 → 6.2 → 6.4 → 6.5`.
> 6.3 (entry/exit) and 6.2 (manual occupancy control) were **swapped**: D68
> deferred its composition rule ("who writes `slot.status`") to D69, and
> entry/exit co-owns that field, so the lifecycle is settled first and the manual
> control then layers on the occupancy write 6.3 introduces. They stay **two**
> increments — 6.3 carries the `actual_entry_at`/`actual_exit_at` migration, and
> §42/§43 want that DB change isolated.

| # | Increment | Decision | Status |
|---|-----------|----------|--------|
| 6.1 | **Operator booking reads** — role-scoped `GET /api/bookings/` (consumer own / manager assigned lots / admin all) | D67 | ✅ Done (2026-10-12) |
| 6.3 | **Entry / exit simulation** — booking `CONFIRMED → IN_PROGRESS → COMPLETED`, slot occupancy follows | D69 | ✅ Done (2026-10-13) |
| 6.2 | **Occupancy controls** — Manager marks a slot `OCCUPIED` / back `AVAILABLE` | D68 | ✅ Done (2026-10-13) |
| 6.4 | **Overstay settlement** — the §19 `1.5 × hourly rate` rule, `BusinessRule.overstay_multiplier` | D70 | 🔜 Next (settle D70) |
| 6.5 | **Occupancy board read** — the Manager's live per-lot view | D71 · D72 | ⚪ Not started |

### Brief per increment

- **6.1** turns the consumer-only `GET /api/bookings/` into a role-scoped read
  (mirroring D65's payments route) and adds the operator row shape. This is the
  §3.1 "View bookings" (Manager) and "View all bookings" (Administrator) slice.
  **Delivered 2026-10-12:** `_visible_bookings` scopes the queryset
  (Consumer own / Manager `slot__lot__manager` / Admin all), `GET` is
  `IsAuthenticated` while `POST` stays `IsConsumer`, and
  `BookingOperatorSerializer` adds `lot`, `consumer_email`, `consumer_name`.
  The 4.9 filters and the D66 envelope apply unchanged. No migration; the full
  suite is green.
- **6.3** owns `IN_PROGRESS` / `COMPLETED` (the Phase 4 boundary explicitly
  leaves these to Phase 6) and the simulated entry/exit that drives them. It also
  introduces the occupancy write that entry/exit performs on the slot.
- **6.2** exposes the stored, physical `ParkingSlot.status = OCCUPIED` to the
  lot's Manager (§28) as a manual control, reusing the occupancy write from 6.3.
  Keeping this distinct from booking reservation and hold is the §18 constraint
  (D33). **Code is drafted; it lands after 6.3** (see the sequencing note).
- **6.4** implements §19's overstay penalty for a booking that runs past its
  booked end.
- **6.5** is the read behind the "Occupancy" page: slot states plus the live
  booking on each slot.

---

## Dependencies on earlier phases

Read these **only** when a Phase 6 task touches them.

| Decision / artefact | Why Phase 6 needs it |
|---------------------|----------------------|
| **D33 / §18** | Stored slot state is physical only (`AVAILABLE`/`OCCUPIED`/`OUT_OF_SERVICE`); `RESERVED`/`HELD` stay derived from bookings. Do not collapse occupancy, reservation and hold. |
| **D40** | The booking state enum; `IN_PROGRESS`/`COMPLETED` already defined, never written before this phase. |
| **D41 / D43** | The half-open conflict predicate and lazy expiry that occupancy must not contradict. |
| **D45** | Per-slot duration policy; overstay is measured against the booked end. |
| **D51** | `confirm_booking` — the `PENDING_PAYMENT → CONFIRMED` seam; entry starts from a `CONFIRMED` booking. |
| **D53** | `cancel_booking` — a cancelled booking must not be enterable. |
| **D6** | Expiry is lazy; occupancy must not introduce a scheduler. |
| **D65** | The role-scoped queryset pattern 6.1 mirrors. |
| **D66** | The paginated envelope every list read in this phase returns. |
| **PROJECT.md §28** | The simulated-occupancy behaviour (Manager marks a slot occupied). |
| **PROJECT.md §19** | The overstay rule (1.5 × applicable hourly rate). |

---

## Guardrails for this phase

- **No hardware, ever** — no sensors, gates, barriers, ANPR or IoT (§4). Every
  entry/exit and occupancy change is a software action.
- **Don't collapse concepts** — physical occupancy, booking reservation and
  temporary hold stay three separate things (§18, D33).
- **Decisions before code** — D70–D72 are core logic (§9); each is surfaced with
  options and trade-offs and recorded before its increment.
- **Manager scoping** — a Manager may only act on their assigned lots
  (Invariant 3); an unassigned lot is a `404`, never a `403`.
- **Small, scoped commits** in `feat(domain): ...` style (PROJECT.md §43).
- **Migrations** — state model change → expected DB change → data implications
  before generating one (§42).
