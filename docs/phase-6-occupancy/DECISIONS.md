# Phase 6 decisions (D67–D71)

Decisions the occupancy phase made or must make. **D67 is accepted**; D68–D71
are **open** and must be settled with the human before their increment's code
(PROJECT.md §9). Entries are added here, and indexed in
[`../decisions-index.md`](../decisions-index.md), as each is decided.

---

## D67 — Operator booking reads: one role-scoped `GET /api/bookings/`

- **Decision:** extend the existing `GET /api/bookings/` from consumer-only to
  **role-scoped**, mirroring D65's payments route: a **Consumer** sees only their
  own bookings, a **Manager** sees bookings in their **assigned lots**, an
  **Administrator** sees **all** — scoped in the queryset, so a caller who owns
  none gets an empty list, never a `403` (Invariants 2/3). The consumer row shape
  is unchanged; a distinct **operator row shape** adds the payer, plate, slot and
  lot. The 4.9 filters (`status`, `scope`, `lot`, `ordering`) and the D66
  paginated envelope apply.
- **Rationale:** §3.1 lists "View bookings" (Manager) and "View all bookings"
  (Administrator); no operator booking read exists today. One role-scoped route
  is consistent with D65 and keeps a single endpoint to document for the
  frontend.
- **Options considered:** (a) extend `GET /api/bookings/` role-scoped; (b) a
  separate operator route such as `GET /api/bookings/manage/`. Chose (a) for
  consistency with D65; (b) would leave two booking-list routes with diverging
  filters.
- **Status:** **Accepted 2026-10-12** (chosen at session close; **code in 6.1**).
- **Open sub-questions to settle at 6.1's open:**
  - Exact operator row fields (payer `email`/`full_name`, `vehicle_plate`,
    `slot_number`, `lot_code`, `status`, `effective_status`, window, amounts).
  - Whether the operator read is **read-only** in 6.1 (recommended: yes —
    Manager actions on a booking, e.g. terminate, are a separate decision) or
    carries action hints.
  - Whether a Manager filter is required or implicit: `?lot=` alone should be
    enough once the queryset is assigned-lot-scoped.

---

## D68 — Occupancy model: how a slot becomes `OCCUPIED` (OPEN)

**The core §18 question.** Settle before 6.2's code.

- Is `ParkingSlot.status = OCCUPIED` set **only** by an explicit Manager action,
  **only** automatically by booking entry (6.3), or **both**?
- Can a Manager mark a slot `OCCUPIED` with **no booking** at all (an unauthorised
  car, or a walk-in that was never system-booked)? If so, occupancy is
  independent of bookings and 6.2 stands alone.
- **Surface:** the existing slot PATCH currently exposes only
  `AVAILABLE`/`OUT_OF_SERVICE` (D38). Does 6.2 widen that enum, or add a dedicated
  occupancy action (e.g. `POST .../slots/{id}/occupancy/`)? A dedicated action
  documents intent and avoids a client PATCHing a state that a booking owns.
- Must a slot marked `OCCUPIED` still be blocked from booking by a separate
  mechanism (the §46 rule that only availability controls who can book)?
- What happens when a slot is `OUT_OF_SERVICE` but physically occupied?

---

## D69 — Entry / exit simulation and the booking lifecycle (OPEN)

Settle before 6.3's code. Owns `IN_PROGRESS` and `COMPLETED`.

- **Who triggers** entry/exit: a Manager's simulated-gate action on an assigned
  lot (recommended), or the Consumer, or both?
- **Endpoint shape:** e.g. `POST /api/bookings/{id}/check-in/` and
  `.../check-out/`, or a single transition action?
- **What is stored:** actual entry/exit instants (`actual_entry_at` /
  `actual_exit_at` — a migration) versus reusing `start_time`/`end_time`? Actual
  times are needed for overstay (6.4).
- **Interaction with occupancy:** does entry set the slot `OCCUPIED` and exit set
  it `AVAILABLE` — and how does that compose with D68's explicit control?
- **No-show:** §17 has no `NO_SHOW` state (D40) and §35 does not list it. What
  happens to a `CONFIRMED` booking whose window passed with no entry? Recommend
  deciding explicitly rather than importing a state the project rejected.
- **Guards:** only a `CONFIRMED` booking may check in; only an `IN_PROGRESS`
  booking may check out (idempotent on repeat), reusing the shared slot lock so
  it cannot race a cancel/confirm.

---

## D70 — Overstay settlement (OPEN)

Settle before 6.4's code.

- **Multiplier source:** `BusinessRule.overstay_multiplier`, default `1.5`
  (§19) — a new singleton field the Administrator may change (migration).
- **Rule:** `1.5 × hourly_rate` for **each additional hour or part thereof**
  beyond the booked end (the same whole-hour rounding as D42), measured from the
  actual exit time.
- **Charging surface:** reuse `POST /api/payments/` with a new
  `purpose = OVERSTAY` (a `Payment.Purpose` enum value + migration), or record
  the amount owed on the booking without an online charge? Reusing the payment
  abstraction keeps one money path; the manager-recorded cash path (D63) may be
  what actually settles it.
- **Settlement timing:** is the overstay charged at **check-out** (6.3)? Does an
  unsettled overstay block `COMPLETED`, or complete with a recorded debt?
- **Scope note:** if the charging surface needs the deferred walk-in/cash flow
  (D63), say so and keep 6.4 to **computing and recording** the overstay, not
  collecting it.

---

## D71 — Occupancy board read (OPEN)

Settle before 6.5's code.

- **Route:** e.g. `GET /api/parking-lots/{lot}/occupancy/`, Manager-only and
  scoped to an assigned lot (Invariant 3; unassigned → `404`).
- **Response:** per-slot `status` plus the current/live booking on each slot
  (reference, plate, window, state) and summary counts (total / available /
  occupied / out-of-service). Whether it is paginated (D66) or returned whole for
  a grid.
- **Time basis:** is "occupied now" the stored physical `status`, the live
  `IN_PROGRESS` booking, or both?
- **Freshness:** polling only — no websockets or push (§47).
