# Smart Parking Management System (SPMS)

An academic mini-project: a software-based parking management platform that lets
consumers discover lots and book slots, managers operate lots and walk-ins, and
administrators manage users and view platform reports.

**Phase 4 (booking) is complete.** Phases 0 (repository setup), 1 (backend
foundation), 2 (authentication and users) and 3 (the parking domain, 3.1–3.4)
are complete. Implemented so far: the custom email-based user model, consumer
self-registration, the JWT authentication surface, consumer profile self-update,
Administrator user management, role-based authorization, consumer **vehicle
registration**, and the parking domain — the `City`/`ParkingLot` catalogue, the
`ParkingSlot` model and API, per-`(lot, slot_type)` **tariffs** capped by the
Administrator's **`BusinessRule` maximum rate** (Invariant 4),
**manager-scoped lot reads** (Invariant 3), and the per-slot **duration policy**
(`min_booking_hours` / `max_booking_hours`, capped by `max_booking_hours`, D45).
Phase 4 has delivered increments **4.1** (the `Booking` model and state enum,
D39–D41), **4.2** (the booking rule layer: `quote_booking`, the D41 conflict
predicate, lazy hold expiry, the stored **`base_amount`** snapshot — D39 revised
— and the per-slot duration policy **D45**), **4.3** (the read-only, derived
time-window availability query, D46), **4.4** (booking creation — the first write
path — with the D3/D41 slot-locked concurrency guard, D47–D49), **4.5**
(effective status for a lapsed hold: a read-only, computed `effective_status`,
D50), **4.6** (the confirmation seam for Phase 5's payment gateway, and a
random, unguessable public `reference` on every booking — D51/D52), **4.7**
(cancellation: the §19 refund cutoff, the stored `refund_due_amount` snapshot
and `POST /api/bookings/{id}/cancel/` — D53), **4.8** (extension: a read-only
quote and the slot-locked `extend_booking` seam for Phase 5's charge — D54; no
migration) and **4.9** (booking history filters and the rich single-booking
detail read — D55; no migration). **Phase 4 is complete.** The next phase is
**Phase 5 (payment)**, built on the §26 provider-agnostic payment abstraction
with **Razorpay in test mode** as the concrete gateway (D56, revised). The authoritative
specification is [`PROJECT.md`](PROJECT.md). Documentation is split per phase —
start at [`docs/README.md`](docs/README.md), the navigation entry point, phase
tracker and reading protocol.

---

## Stack

| Layer     | Technology                                             |
|-----------|--------------------------------------------------------|
| Backend   | Python 3.13, Django 6, Django REST Framework           |
| Database  | PostgreSQL (mandatory — never substitute, D4)           |
| Frontend  | React 19, TypeScript, Vite                             |
| Auth      | JWT via `djangorestframework-simplejwt` (D1)           |
| Testing (planned) | Django `TestCase` / `TransactionTestCase` (not pytest, D7) |

---

## Repository layout

```text
ParkingManagementSystem/
├── PROJECT.md              # authoritative specification
├── README.md               # this file
├── requirements.txt        # Python dependencies (pinned)
├── .gitignore              # ignores .env, db.sqlite3, venvs, caches
├── docs/                   # per-phase docs (start at docs/README.md)
│   ├── README.md           # navigation, phase tracker, reading protocol
│   ├── decisions-index.md  # D-number -> the file holding the full entry
│   ├── deferred-features.md
│   ├── foundation/         # phases 0-1 + cross-cutting decisions (D1-D10)
│   ├── phase-2-authentication/
│   ├── phase-3-parking/
│   ├── phase-4-booking/    # booking model, rules, lifecycle (D39-D55; D39 revised in 4.2)
│   └── phase-5-payment/    # payment scope, plan and decisions (D56 next)
├── backend/
│   ├── manage.py
│   ├── .env                # local secrets (git-ignored)
│   ├── .env.example        # template for .env
│   ├── config/             # project configuration package
│   │   ├── settings.py     # single settings module (not yet split)
│   │   ├── urls.py         # root URLconf (admin, /api/health/, app routes)
│   │   ├── views.py        # project-level health view
│   │   ├── wsgi.py
│   │   └── asgi.py
│   └── apps/               # modular-monolith domain apps
│       ├── accounts/       # users, roles, auth, vehicles
│       ├── parking/        # lots, slots, slot types, pricing
│       ├── bookings/       # bookings, lifecycle, holds
│       ├── payments/       # payments, Razorpay test-mode gateway, refunds
│       ├── notifications/  # in-app notification records
│       └── reports/        # occupancy / revenue / stats
└── frontend/
    ├── package.json
    ├── vite.config.ts      # dev proxy: /api -> http://localhost:8000
    └── src/
```

---

## Backend setup

PostgreSQL must be running and a database must exist. Create it once, for
example:

```bash
createdb spms
```

Create the virtual environment and install dependencies (from the repository
root):

```bash
python -m venv env
./env/bin/pip install -r requirements.txt
```

Configure environment variables:

```bash
cp backend/.env.example backend/.env
# then edit backend/.env and set DB_NAME / DB_USER / DB_PASSWORD / DB_HOST / DB_PORT
```

Run migrations:

```bash
cd backend
../env/bin/python manage.py migrate
```

Start the development server:

```bash
cd backend
../env/bin/python manage.py runserver
```

Useful checks:

```bash
cd backend
../env/bin/python manage.py check
```

> Settings are loaded from `backend/.env` by a small standard-library loader in
> `config/settings.py`. No third-party dotenv package is required. If the file
> is absent, local-development fallbacks documented in `settings.py` apply.

---

## Frontend setup

```bash
cd frontend
npm install
npm run dev
```

The dev server runs on `http://localhost:5173` and proxies any `/api/*` request
to the Django backend at `http://localhost:8000`, so the browser talks to a
single origin during development.

Production build:

```bash
cd frontend
npm run build
```

---

## API

| Method | Endpoint              | Auth        | Purpose                          |
|--------|-----------------------|-------------|----------------------------------|
| GET    | `/api/health/`        | Public      | Liveness probe                   |
| POST   | `/api/auth/register/` | Public      | Consumer self-registration       |
| POST   | `/api/auth/login/`    | Public      | Obtain JWT access + refresh      |
| POST   | `/api/auth/refresh/`  | Public      | Exchange refresh for access      |
| POST   | `/api/auth/logout/`   | Bearer      | Invalidate the refresh token     |
| GET    | `/api/auth/me/`       | Bearer      | Current user profile             |
| PATCH  | `/api/auth/me/`       | Bearer      | Update own `full_name` / `phone` |
| GET    | `/api/users/`         | Admin       | List/filter the user directory   |
| POST   | `/api/users/`         | Admin       | Create a `MANAGER`/`ADMIN`       |
| GET    | `/api/users/{id}/`    | Admin       | Retrieve one account             |
| PATCH  | `/api/users/{id}/`    | Admin       | Change role / suspend-activate   |
| GET    | `/api/vehicles/`      | Consumer    | List the caller's own vehicles   |
| POST   | `/api/vehicles/`      | Consumer    | Register a vehicle               |
| GET    | `/api/vehicles/{id}/` | Consumer    | Retrieve one own vehicle         |
| PUT/PATCH | `/api/vehicles/{id}/` | Consumer | Edit an own vehicle              |
| DELETE | `/api/vehicles/{id}/` | Consumer    | Remove an own vehicle            |
| GET    | `/api/cities/`        | Public      | List the city vocabulary         |
| POST   | `/api/cities/`        | Admin       | Add a city                       |
| GET    | `/api/parking-lots/`  | Public      | List active lots (`?city=`, `?search=`) |
| POST   | `/api/parking-lots/`  | Admin       | Create a lot                     |
| GET    | `/api/parking-lots/{id}/` | Public   | Retrieve one active lot          |
| PATCH  | `/api/parking-lots/{id}/` | Admin    | Edit a lot / assign its manager  |
| GET    | `/api/parking-lots/{lot}/slots/` | Public | List a lot's slots        |
| POST   | `/api/parking-lots/{lot}/slots/` | Admin/Manager | Add a slot         |
| GET    | `/api/parking-lots/{lot}/slots/{id}/` | Public | Retrieve a slot     |
| PATCH  | `/api/parking-lots/{lot}/slots/{id}/` | Admin/Manager | Edit a slot |
| GET    | `/api/parking-lots/{lot}/tariffs/` | Public | List a lot's tariffs    |
| POST   | `/api/parking-lots/{lot}/tariffs/` | Admin/Manager | Add a tariff     |
| GET    | `/api/parking-lots/{lot}/tariffs/{id}/` | Public | Retrieve a tariff |
| PATCH  | `/api/parking-lots/{lot}/tariffs/{id}/` | Admin/Manager | Edit a tariff |
| GET    | `/api/business-rules/` | Public     | The max-hourly-rate singleton    |
| PATCH  | `/api/business-rules/` | Admin      | Change the rate/duration ceilings, hold length or refund cutoff |
| GET    | `/api/parking-lots/{lot}/availability/` | Public | Slots bookable for `?start=&end=` (4.3) |
| GET    | `/api/bookings/`       | Consumer   | List/filter the caller's own bookings (4.4/4.9) |
| GET    | `/api/bookings/{id}/`  | Consumer   | Read one own booking: lot location + `can_cancel`/`can_extend` (4.9) |
| POST   | `/api/bookings/`       | Consumer   | Create a booking (4.4) |
| POST   | `/api/bookings/{id}/cancel/` | Consumer | Cancel an own booking, recording the refund due (4.7) |
| GET    | `/api/bookings/{id}/extension-quote/` | Consumer | Price extending an own booking's end time (4.8) |

> Authorisation is enforced server-side on every request (D15, D18). `Admin`
> above means the authenticated account's `role` must be `ADMIN`; a `403` is
> returned otherwise and a `401` when unauthenticated. Self-registration can
> only produce a `CONSUMER`; privileged accounts exist only via `POST /api/users/`.
> Vehicles are consumer-only and scoped to the caller — another account's
> vehicle returns `404`, not `403`. Parking reads are public (D37); a logged-in
> Manager's `GET /api/parking-lots/` returns their assigned lots (including
> deactivated ones), while the single-lot read is active-or-assigned. Parking
> writes are Administrator-only, except slots and tariffs which also accept the
> lot's assigned Manager (Invariant 3) — an unassigned lot returns `404`, never
> `403`. `BusinessRule` is a singleton at `/api/business-rules/` and carries two
> ceilings: lowering `max_hourly_rate` below an existing tariff is a `409`
> `MAX_RATE_BELOW_TARIFF`, and lowering `max_booking_hours` below an existing
> slot's maximum is a `409` `MAX_DURATION_BELOW_SLOT`. A slot whose
> `max_booking_hours` exceeds the cap is a `409` `MAX_DURATION_ABOVE_CAP`.

### Vehicles

A vehicle's registration number is the Indian `SSRRLLNNNN` form (e.g.
`KA01AB1234`). The client does **not** type the combined string; it sends the
four segments and the backend validates and joins them (D28):

```text
POST /api/vehicles/
```

```json
{
  "state_code": "KA",
  "rto_code": "01",
  "series": "AB",
  "unique_number": "1234",
  "make": "Maruti",
  "model": "Swift",
  "color": "White"
}
```

Response `201` — the canonical plate plus the echoed segments:

```json
{
  "id": 1,
  "registration_number": "KA01AB1234",
  "state_code": "KA",
  "rto_code": "01",
  "series": "AB",
  "unique_number": "1234",
  "make": "Maruti",
  "model": "Swift",
  "color": "White"
}
```

Authenticated requests use the standard header:

```text
Authorization: Bearer <access_token>
```

### Health endpoint

```text
GET /api/health/
```

Response `200`:

```json
{ "status": "ok" }
```

Example:

```bash
curl -i http://127.0.0.1:8000/api/health/
```

### Registration

```text
POST /api/auth/register/
```

Request:

```json
{
  "email": "Test.User@Example.COM",
  "full_name": "Test User",
  "phone": "9876543210",
  "password": "Tr0ub4dor&3",
  "password_confirm": "Tr0ub4dor&3"
}
```

Response `201` — note the email is returned lower-cased (D13):

```json
{
  "id": 1,
  "email": "test.user@example.com",
  "full_name": "Test User",
  "phone": "9876543210"
}
```

`role` is never accepted from the client; self-registration always produces a
`CONSUMER` (D11).

### Parking domain (Phase 3)

The parking catalogue is public to read. Endpoints are nested under a lot for
slots and tariffs; `BusinessRule` is a flat singleton. Every rate is in INR per
hour and `Decimal`-backed.

Tariffs price one slot type within one lot (`D34`), and the backend rejects any
rate above the Administrator's `max_hourly_rate` (`D35`, Invariant 4):

```text
POST /api/parking-lots/1/tariffs/       (Admin, or lot 1's Manager)
```

```json
{ "slot_type": "EV", "hourly_rate": "30.00" }
```

Response `201`:

```json
{
  "id": 1,
  "lot": 1,
  "lot_code": "BLR-001",
  "slot_type": "EV",
  "slot_type_label": "Electric vehicle",
  "hourly_rate": "30.00",
  "created_at": "2026-10-03T10:15:00Z",
  "updated_at": "2026-10-03T10:15:00Z"
}
```

The cap is read and set at the singleton:

```text
GET   /api/business-rules/                -> { "id": 1, "max_hourly_rate": "100.00", ... }
PATCH /api/business-rules/                (Admin only)
{ "max_hourly_rate": "50.00" }
```

If an existing tariff already charges more than the proposed maximum, lowering
the cap is refused so the invariant never breaks at rest:

```json
{ "error": "MAX_RATE_BELOW_TARIFF", "message": "The maximum cannot be lowered below an existing tariff." }
```

The hour is the billing unit; `daily_rate` is deliberately deferred (`D34`).

Each slot also carries a **per-slot duration policy** (D45, Phase 4):
`min_booking_hours` / `max_booking_hours` in whole hours, defaults `1` / `24`,
set by the lot's Manager (or an Administrator) through the slot create/PATCH
surface. The Administrator's `BusinessRule.max_booking_hours` (default `72`) caps
any slot's maximum — the duration twin of the rate cap. A requested booking whose
rounded duration falls outside the slot's range is refused with
`MIN_DURATION_NOT_MET` / `MAX_DURATION_EXCEEDED` (enforced by the booking rules in
Phase 4, not by the parking API).

### Availability (Phase 4, increment 4.3)

Which of a lot's slots can be booked for a given window. Availability is
**derived from bookings** (D2/D33), never stored, and the read is
**side-effect free** — a lapsed hold is filtered out by the query, not expired by
it (D43).

```text
GET /api/parking-lots/1/availability/?start=2026-10-06T10:00:00Z&end=2026-10-06T12:00:00Z
```

Both `start` and `end` are required, offset-aware ISO-8601 instants (stored UTC,
D5). The response is the **bookable subset** of the lot's slots, in the same
shape as `GET /api/parking-lots/1/slots/`:

```json
[
  {
    "id": 1,
    "lot": 1,
    "lot_code": "BLR-001",
    "number": "A-01",
    "floor": "",
    "slot_type": "REGULAR",
    "status": "AVAILABLE",
    "min_booking_hours": 1,
    "max_booking_hours": 24,
    "created_at": "2026-10-03T10:15:00Z",
    "updated_at": "2026-10-03T10:15:00Z"
  }
]
```

A slot is bookable when all three hold (D46): it is **not `OUT_OF_SERVICE`**
(Invariant 5); the window fits its **D45 duration policy**; and **no booking
blocks the window** — i.e. no `CONFIRMED` / `IN_PROGRESS` overlap, and no
`PENDING_PAYMENT` whose hold is still live. Adjacent windows do **not** conflict:
a booking ending at `12:00` leaves a `12:00–14:00` request free (D41's half-open
rule). `OCCUPIED` is deliberately **not** excluded — it is a physical, time-
unbounded state owned by Phase 6. A backwards or empty window is a `400`
`INVALID_WINDOW`; the lot follows the usual nested-read scoping, so a consumer
gets a `404` for an inactive lot while its Manager may still address it (D38).

### Bookings (Phase 4, increments 4.4–4.6)

A Consumer creates a booking for one of their own vehicles and a slot window;
the backend prices it, protects the slot against overlapping bookings and holds
it while payment is pending. The price, status, hold and plate snapshot are
computed server-side — the client never supplies them (D47, §45/§46).

```text
POST /api/bookings/
```

```json
{ "slot": 1, "vehicle": 1,
  "start_time": "2026-10-07T10:00:00Z", "end_time": "2026-10-07T12:00:00Z" }
```

Response `201` (excerpt) — `base_amount` is the agreed price of the booked
duration, `hold_expires_at` is `now + BusinessRule.hold_minutes` (default 5):

```json
{
  "id": 1,
  "reference": "7GQ4M2XK9P",
  "status": "PENDING_PAYMENT",
  "effective_status": "PENDING_PAYMENT",
  "vehicle_plate": "KA01AB1234",
  "billed_hours": 2,
  "hourly_rate": "20.00",
  "base_amount": "40.00",
  "hold_expires_at": "2026-10-06T10:05:00Z"
}
```

Creation refusals use the §33 `{"error": "CODE", "message": ...}` shape (D48):
`400` `INVALID_WINDOW` / `WINDOW_IN_PAST` / `MIN_DURATION_NOT_MET` /
`MAX_DURATION_EXCEEDED`; `404` `SLOT_NOT_FOUND` / `LOT_NOT_BOOKABLE`; `409`
`SLOT_UNAVAILABLE` / `BOOKING_CONFLICT` / `NO_TARIFF`. The window conflict is
re-checked under a per-slot row lock, so two simultaneous requests cannot both
win the same slot (Invariant 1, D41).

`GET /api/bookings/` lists only the caller's own bookings (Invariant 2). While a
booking is `PENDING_PAYMENT`, a lapsed hold is reported as
`"effective_status": "EXPIRED"` **without** changing the stored `status` — expiry
is lazy and reads never write (D6/D43/D50). Clients should render
`effective_status`; `status` and `hold_expires_at` stay in the payload for
transparency.

Every booking also carries a random, unguessable **`reference`** (D52) — the
bearer code a receipt or QR ticket presents, so a walk-in with no login can be
looked up. It is generated server-side (a client cannot set it) and shown on the
authenticated read. The public QR/gate lookup route arrives with the walk-in
flow, so it is **not** exposed at an endpoint yet.

Confirmation (`PENDING_PAYMENT → CONFIRMED`) is **implemented as a service seam**
(D51) that Phase 5's payment gateway will call when a payment succeeds — Phase 4
itself performs no charge and adds no confirmation endpoint. It confirms only a
live pending booking, is idempotent if called twice, and takes the same per-slot
lock as creation; a late or cancelled booking is refused with
`BOOKING_NOT_CONFIRMABLE` (409), and a window meanwhile taken refuses with
`BOOKING_CONFLICT` (409).

### Cancellation (Phase 4, increment 4.7)

A Consumer cancels one of their own bookings, which frees the slot immediately
and records the refund the §19 cutoff entitles them to. Phase 4 decides the
refund and stores it; **no money moves** — Phase 5's gateway reads
`refund_due_amount`.

```text
POST /api/bookings/1/cancel/
```

Response `200` (excerpt):

```json
{
  "id": 1,
  "status": "CANCELLED",
  "refund_due_amount": "40.00",
  "cancelled_at": "2026-10-06T09:40:00Z"
}
```

A `PENDING_PAYMENT` (including a lapsed hold) and a `CONFIRMED` booking may be
cancelled; both record `refund_due_amount` at cancellation time. Only a paid
(`CONFIRMED`) booking can owe a refund: the full `base_amount` when cancelled at
least `BusinessRule.cancellation_cutoff_minutes` (default **30**) before the
start, otherwise `0.00`. The value is a **stored snapshot** (D53), so changing
the cutoff later cannot rewrite a booking already cancelled. Re-cancelling an
already-`CANCELLED` booking is an idempotent success. A booking in progress,
completed, expired or terminated is refused with
`409 {"error": "BOOKING_NOT_CANCELLABLE"}`; another consumer's booking is a
`404 BOOKING_NOT_FOUND`, never a `403` (Invariant 2). Cancellation takes the
same per-slot lock as creation and confirmation (D49/D51), so a cancel cannot
race the payment-success that confirms the same booking. `BusinessRule`'s
`cancellation_cutoff_minutes` is exposed at `/api/business-rules/` and is
Administrator-only to change.

### Extension (Phase 4, increment 4.8)

A Consumer prices lengthening one of their own live bookings and — once Phase 5
has charged it — the booking's `end_time` moves later. As with confirmation,
Phase 4 performs **no charge** and adds **no apply endpoint**: `extend_booking`
is a **service seam** Phase 5's gateway calls after payment, so `base_amount`
only ever reflects money actually charged. Pricing is a read, so a client can
show the cost first:

```text
GET /api/bookings/1/extension-quote/?end_time=2026-10-07T14:00:00Z
```

Response `200` (excerpt) — the extra the extension would cost:

```json
{
  "added_hours": 1,
  "extension_amount": "20.00",
  "new_billed_hours": 3,
  "new_base_amount": "60.00",
  "hourly_rate": "20.00",
  "new_end_time": "2026-10-07T14:00:00Z"
}
```

Only a `CONFIRMED` or `IN_PROGRESS` booking can be extended; the new `end_time`
must be strictly later than the current one and in the future (otherwise `400`
`INVALID_EXTENSION`). The **whole** window is re-priced
(`hours_between(start, new_end)`), not the rounded slice, so `billed_hours` stays
consistent (D42); the new total is re-checked against the slot's
`min_booking_hours` / `max_booking_hours` (`400` `MAX_DURATION_EXCEEDED`). Any
other state is `409 BOOKING_NOT_EXTENDABLE`, and another consumer's booking is a
`404 BOOKING_NOT_FOUND`, never a `403` (Invariant 2). The seam takes the same
per-slot lock as creation, confirmation and cancellation and re-checks the added
window, so an extension cannot collide with another booking (`409
BOOKING_CONFLICT`); re-sending the same `end_time` is an idempotent no-op.

### Booking history and detail (Phase 4, increment 4.9)

`GET /api/bookings/` lists only the caller's own bookings and is now
**filterable** (D55); `GET /api/bookings/{id}/` reads one of them in full. Both
are read-only: they never persist lazy hold expiry, so a lapsed
`PENDING_PAYMENT` is still returned by `?status=PENDING_PAYMENT` while its body
`effective_status` reads `EXPIRED` (D6/D43/D50).

```text
GET /api/bookings/?status=CONFIRMED,IN_PROGRESS&scope=upcoming&lot=1&ordering=-start_time
GET /api/bookings/1/
```

| Query param | Meaning |
|-------------|---------|
| `status` | One or more comma-separated **stored** states (`PENDING_PAYMENT`, `CONFIRMED`, …); an unknown token is a `400`. |
| `scope` | A time window independent of state: `upcoming`, `ongoing` or `past`. |
| `lot` | Only bookings in this lot. |
| `ordering` | `start_time` / `-start_time` / `end_time` / `-end_time` / `created_at` / `-created_at`; default is the model's `-start_time`, `-id`. |

The filters combine as an AND, so `?scope=upcoming&status=CONFIRMED` is the
"upcoming confirmed" tab. The list is **not paginated** (Phase 10).

The detail response is the list shape plus the lot/slot location
(`lot`, `lot_name`, `lot_address_line`, `lot_city`, `lot_state`,
`lot_postal_code`, `slot_floor`) and the action hints `can_cancel` / `can_extend`
— which mirror the cancel and extension rules exactly. Payment fields are
deliberately absent until Phase 5's `Payment`. Example (excerpt):

```json
{
  "id": 1,
  "reference": "7GQ4M2XK9P",
  "status": "CONFIRMED",
  "effective_status": "CONFIRMED",
  "lot": 1,
  "lot_name": "MG Road",
  "lot_address_line": "1 MG Road",
  "lot_city": "Bengaluru",
  "slot_number": "A-01",
  "slot_floor": "G",
  "can_cancel": true,
  "can_extend": true
}
```

Both routes are Consumer-only and scoped to the caller: another consumer's
booking — or a non-existent id — is a `404 {"error": "BOOKING_NOT_FOUND"}`, never
a `403` (Invariant 2).

### Payment (Phase 5) — next

Not implemented yet. Phase 5 adds the `Payment` model, payment states, creation,
confirmation, receipt and refund on top of Phase 4's seams, using **Razorpay in
test mode** behind the §26 provider-agnostic abstraction (D56, revised from
Stripe; the model and states are fixed by D57). No real charges are made and no
card data is stored. See [`docs/phase-5-payment/`](docs/phase-5-payment/).
