# Phase 6 decisions (D67–D72)

Decisions the occupancy phase made. **D67–D72** are **implemented** (6.1–6.5).
Entries are added here, and indexed in
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

## D70 — Overstay settlement

Settle before 6.4's code. **Decided 2026-10-13 (code in 6.4).**

- **Rule (§19):** `overstay_hours × booking.hourly_rate × overstay_multiplier`.
  `booking.hourly_rate` is the creation snapshot, not today's tariff, so a later
  price change cannot rewrite a past bill (the `base_amount` reasoning).
- **Grace window (revised from a bare §19 reading):** check-out is a *human*
  click, so a customer who left on time must not be penalised for the operator's
  latency, and a small harmless overrun should be forgiven. The overstay clock
  therefore starts **after** the grace:
  `billable = actual_exit_at − (end_time + overstay_grace_minutes)`, rounded up;
  within the grace there is no overstay. The true `actual_exit_at` is still
  stored — only the penalty is affected. It is operational tolerance, not a free
  pass, and it is a tunable rule.
- **Rounding:** the overrun is charged per whole hour **or part thereof** — the
  same `hours_between` `ceil` used for billed hours (D42), reused rather than
  re-implemented.
- **Multiplier source:** `BusinessRule.overstay_multiplier`, `Decimal(4,2)`
  default `1.50`, `>= 1` (a penalty is never a discount), Administrator-settable.
  Grace: `BusinessRule.overstay_grace_minutes`, default `15`, `>= 1`. Both are a
  migration.
- **Storage:** snapshot on the booking at check-out — `overstay_hours`
  (`PositiveIntegerField`, default 0) and `overstay_amount` (`Decimal(12,2)`,
  default 0.00). Migration, defaults, no backfill.
- **Settlement timing:** check-out always reaches `COMPLETED`; an unsettled
  overstay is a **recorded debt**, it never blocks the transition (the car has
  left and §17/D40 make `COMPLETED` terminal).
- **Charging surface:** 6.4 **computes and records only**; **collection is
  deferred**. The natural settlement is cash at the gate — D63, deferred — and an
  online `OVERSTAY` charge (`Payment.Purpose` + migration) would be a flow
  nothing initiates after the vehicle has left. D70's scope note sanctions
  "computing and recording, not collecting".
- **Reads:** `overstay_hours` / `overstay_amount` are exposed on the booking read
  (consumer detail and the operator row), so the debt is visible.

---

## D71 — Occupancy board read

Settle before 6.5's code. **Decided 2026-10-14 · implemented in 6.5 (2026-10-14).**

- **Route:** `GET /api/parking-lots/{lot}/occupancy/` — the lot's **Manager**
  (scoped to an assigned lot) and an **Administrator** (any lot). An unassigned
  lot is a `404`, never a `403` (Invariant 3).
- **Response — the whole board, not paginated** (it opts out of D66, like cities
  and availability): the lot reference, a generated-at timestamp, a `summary`
  count block (`total` / `available` / `occupied` / `out_of_service`) and the
  full `slots` array. A board must show every bay at once.
- **Time basis — stored status AND live booking, together (§18/D33):** each row
  carries the bay's stored physical `status` (written by 6.3 entry/exit and 6.2's
  manual mark) **and** its `current_booking` — the live `IN_PROGRESS` booking, or
  `null` when a bay is occupied with no booking or is free. The status is
  authoritative; the booking is derived. They are not collapsed.
- **Freshness:** this snapshot is the transport-neutral source that the live
  channel (D72) seeds from, and the endpoint a client may fall back to.

---

## D72 — Live occupancy-board delivery

Raised 2026-10-12 while opening 6.1. **Decided 2026-10-14 (implemented in 6.5):
WebSockets via Django Channels + a Redis channel layer** — an explicitly
approved PROJECT.md §12 infrastructure exception.

- **Goal:** the Manager's occupancy board updates without a manual refresh, so it
  never reads as static.
- **Chosen: WebSockets (Channels + Redis).** The human approved the §12
  exception on 2026-10-14 and chose the two-way transport over SSE and polling.
  Recorded here as the Razorpay-style documented exception (D56).
- **Why not SSE:** a streaming HTTP response holds its connection open for its
  whole life, so on a synchronous WSGI worker pool each open stream pins a worker
  for its duration (raised 2026-10-13). Channels runs the stack under ASGI, so
  websocket connections never pin a worker — the price is a running **Redis**
  broker.
- **Infrastructure added:** `channels`, `channels-redis`, `daphne` (the ASGI
  server; once `daphne` is in `INSTALLED_APPS`, `manage.py runserver` serves
  ASGI, so websockets work in dev); a Redis server; and a `CHANNEL_LAYERS`
  setting. `config/asgi.py` routes both `http` and `websocket`.
- **Transport shape:** one group per lot (`occupancy.<lot_id>`). A consumer joins
  on connect and immediately sends the **same snapshot D71 returns**; slot and
  booking writes broadcast to the group, and each consumer re-serialises and
  pushes. The board is read-only over the socket (the two-way capability is not
  used, but it is why the transport was chosen).
- **Auth (D15/§24):** the connection is authorised **server-side**. The JWT
  access token is presented on connect, the scope is resolved to a user, and
  role + lot scoping are enforced **before** the group is joined; an
  unauthorised or unassigned connection is closed with a policy close code.
  Role and lot are never trusted from the client.

**Implemented in 6.5:**

- **Snapshot builder:** `build_occupancy_board(lot)` lives in
  `bookings/services.py` (it composes parking slots with live bookings) and
  returns a **JSON-ready** dict, so the HTTP view and the socket push the same
  shape byte-for-byte.
- **HTTP:** `ParkingLotOccupancyView` (`parking/views.py`) serves
  `GET /api/parking-lots/{lot}/occupancy/`; its lot lookup is stricter than the
  public catalogue — a Manager may only address an **assigned** lot, so
  unassigned is a `404` (never `403`, Invariant 3).
- **Broadcast:** `parking/occupancy.py` holds `board_group_name` and
  `notify_board_changed(lot_id)`. The occupancy **actions** (`set_occupancy` in
  6.2, `check_in_booking`/`check_out_booking` in 6.3) call it; the message is
  deferred with `transaction.on_commit`, so a rolled-back write never pushes a
  phantom board. The payload is tiny (`{"type": "board.changed"}`) — the consumer
  re-reads rather than trusting the message.
- **Consumer:** `OccupancyConsumer` (`parking/consumers.py`) joins the lot group
  on an authorised connect and pushes the initial snapshot; `board_changed`
  re-reads and pushes. Close codes: `4401` unauthenticated, `4403`
  wrong role / unassigned lot. Read-only (no client frames used).
- **Routing:** `parking/routing.py` exposes
  `ws/parking-lots/<lot_pk>/occupancy/`, aggregated by `config/routing.py`.
- **Tests:** the board/consumer tests run under `TransactionTestCase` with the
  **in-memory** channel layer (`apps/parking/test_websockets.py`), so the suite
  never needs Redis; the WebSocket JWT resolver is covered directly.
