# Phase 6 decisions (D67–D72)

Decisions the occupancy phase made or must make. **D67** (6.1), **D68** (6.2) and
**D69** (6.3) are **implemented**; **D70–D72** are **open** and must be settled
with the human before their increment's code (PROJECT.md §9). Entries are added here, and indexed in
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
- **Status:** **Implemented in 6.1 (2026-10-12)**; accepted 2026-10-12.
- **Resolved at 6.1:**
  - **Operator row fields:** the operator shape adds `lot`, `consumer_email` and
    `consumer_name` to the existing booking row; the payer id is already `user`,
    and `vehicle_plate` / `slot_number` / `lot_code` were already present, so
    nothing is duplicated.
  - **Read-only:** yes — 6.1 carries no action hints. Operator actions on a
    booking (terminate, entry/exit) belong to 6.2–6.4.
  - **Manager filter:** implicit. The queryset is assigned-lot-scoped, so `?lot=`
    only narrows within it and an unassigned lot returns an empty list, never a
    `403` (tested).

---

## D68 — Occupancy model: how a slot becomes `OCCUPIED`

**The core §18 question.** Decided 2026-10-12; implemented in 6.2 (sequenced
after 6.3 — see the ordering note in [`PROGRESS.md`](PROGRESS.md)).

- **Decision:** `OCCUPIED` stays the single **stored physical** flag on
  `ParkingSlot.status` (`AVAILABLE` / `OCCUPIED` / `OUT_OF_SERVICE`); reservation
  and hold stay derived from bookings (D33/§18). **Both** an explicit Manager
  action and — later, in 6.3 — booking entry/exit write that one field. 6.2 adds
  only the explicit action; the automatic writer is D69's.
- **With or without a booking:** a Manager may mark a slot `OCCUPIED` with **no
  booking** (an unauthorised car). That case is the reason software occupancy
  exists, and the reason 6.2 stands alone from 6.3.
- **Surface:** a **dedicated action**,
  `POST /api/parking-lots/{lot}/slots/{id}/occupancy/` with
  `{"status": "OCCUPIED" | "AVAILABLE"}`. The structural slot `PATCH` keeps
  rejecting `OCCUPIED` (D38), so the *identity/edit* surface never sets an
  operational state a booking will own; lot scoping is the existing
  `LotScopedMixin` (an unassigned lot is a `404`, never a `403`).
- **Only `AVAILABLE` ↔ `OCCUPIED`:** the action never sets or clears
  `OUT_OF_SERVICE`; marking an `OUT_OF_SERVICE` slot occupied (or freeing it) is
  a `409` `SLOT_NOT_OCCUPIABLE`, so the two axes stay independent.
- **Bookability:** an `OCCUPIED` bay is unavailable **only for a window that has
  already begun** (`start <= now`) — the car is physically there *now*. A window
  that begins in the future does not overlap it, so the bay is still offered:
  otherwise a lot that is momentarily full could never take tomorrow's booking,
  which would make the software worse than asking the manager in person. The same
  condition lives in `available_slots` (excluded) and `create_booking` (refused
  with `SLOT_UNAVAILABLE`, 409), so the §46 rule ("only availability controls who
  can book") stays true and the grid agrees with the booking path. A bay that
  should leave the bookable pool **entirely** is `OUT_OF_SERVICE`, not
  `OCCUPIED`.
- **Revises the 4.3/D46 deferral:** Phase 4 deliberately left `OCCUPIED` out of
  the availability query because "Phase 6 owns it"; this is that answer — it is
  a *now*-fact, not a permanent bar.
- **Composition rule for 6.3 (recorded now, implemented then):** `status` is the
  one field both the manual action and entry/exit write; the automatic writer
  never overrides `OUT_OF_SERVICE`; last write wins — each write reflects what is
  physically true at that moment.
- **No migration:** `OCCUPIED` already exists on the enum (D33).
- **Options considered:** (a) widen the existing slot `PATCH` status enum;
  (b) a dedicated occupancy action. Chose (b): occupancy is an operational event,
  not a structural edit, and §28 calls it "Mark Occupied". Option (a) would also
  let a slot be *created* already `OCCUPIED` and mixes two concerns in one
  serializer.

---

## D69 — Entry / exit simulation and the booking lifecycle

Settle before 6.3's code. Owns `IN_PROGRESS` and `COMPLETED`. **Decided
2026-10-13; implemented in 6.3.**

- **Who triggers:** a **Manager**, on a booking in their **assigned lot** (the
  simulated gate); an unassigned lot is a `404` (Invariant 3). The Consumer does
  **not** self-report entry/exit — a client must not assert a physical fact
  (§24/§25) — which also mirrors 6.2's Manager-only authority.
- **Endpoints:** two explicit actions, flat like the existing ones —
  `POST /api/bookings/{id}/check-in/` (`CONFIRMED → IN_PROGRESS`) and
  `POST /api/bookings/{id}/check-out/` (`IN_PROGRESS → COMPLETED`). No generic
  "transition" action, so a client cannot post arbitrary states.
- **Storage:** `Booking.actual_entry_at` / `actual_exit_at`, nullable (a
  migration). `start_time`/`end_time` stay the **plan** snapshot, never
  overwritten; the actuals are what 6.4 measures overstay against. Migration
  impact: two nullable columns, **no backfill**.
- **Occupancy:** check-in sets the slot `OCCUPIED`, check-out sets it
  `AVAILABLE`, through **one shared writer**; neither overrides `OUT_OF_SERVICE`
  (D68's composition rule). Manual (6.2) and automatic (6.3) write the same
  field; last write wins.
- **No-show:** no new state (D40). A `CONFIRMED` booking whose window passes
  unentered stays `CONFIRMED` and is **inert** — it only ever blocked its own
  window, so future availability is unaffected. `TERMINATED` stays writeless in
  6.3; operator removal is a separate later action.
- **Guards:** check-in only from `CONFIRMED`, check-out only from `IN_PROGRESS`;
  both **idempotent** on a repeat (like confirm/cancel); both take the shared
  slot lock first (D49/D51/D53), so they cannot race cancel/confirm/extend.
  Refusals are `BOOKING_NOT_CHECKINABLE` / `BOOKING_NOT_CHECKOUTABLE` (409); a
  foreign or unassigned booking is `BOOKING_NOT_FOUND` (404), never a `403`.
- **Operator hints:** the operator row gains `can_check_in` / `can_check_out`
  (mirroring the consumer detail's `can_cancel` / `can_extend`), so the list
  knows which actions to offer without a second request.
- **Options considered:** (a) Consumer self check-in/out; (b) a generic
  transition action; (c) reuse `start_time`/`end_time` instead of storing
  actuals. Rejected (a) as client-asserted physical state, (b) as a state-machine
  hole, (c) as it would destroy the plan and block overstay.

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
- **Freshness:** ~~polling only — no websockets or push (§47)~~ **REOPENED
  2026-10-12.** The human wants a genuinely live board (a static board "reads
  naively"); this is now its own decision, **D72**, to be settled at 6.5. See
  the new entry below.

---

## D72 — Live occupancy-board delivery (OPEN)

Raised 2026-10-12 while opening 6.1. Settle at **6.5** (the board read), not
before — 6.1–6.4 do not depend on the transport.

- **Goal:** the manager's occupancy board should update without a manual
  refresh, so the UI does not read as static to a reviewer.
- **Options:** (a) **polling** — a timed re-fetch, no infra; (b) **SSE** —
  server pushes one-way over plain Django, no new infrastructure; (c)
  **WebSockets** via Django **Channels** — two-way, but needs an ASGI server
  (Daphne/Uvicorn) and normally **Redis** as the channel layer.
- **Consequence to decide:** WebSockets/Channels would introduce infrastructure
  PROJECT.md §12/§47 forbids without explicit approval (Redis in particular),
  so it must be an approved, documented exception — as Razorpay was for the
  payment gateway (D56). SSE adds no dependency, is one-way (enough for a
  read-only board) and works with the existing WSGI/Django stack.
- **Auth note:** a WebSocket/SSE stream must still be authorised server-side
  per connection (D15/§24) — role and lot scoping cannot be assumed from the
  client.
- **Recommendation:** decide at 6.5; prefer **SSE** unless two-way is required,
  and only adopt Channels + Redis if the human approves the §12 exception and
  accepts the added infrastructure.
