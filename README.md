# Smart Parking Management System (SPMS)

An academic mini-project: a software-based parking management platform that lets
consumers discover lots and book slots, managers operate lots and walk-ins, and
administrators manage users and view platform reports.

**Phase 4 (booking) is in progress.** Phases 0 (repository setup), 1 (backend
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
— and the per-slot duration policy **D45**) and **4.3** (the read-only, derived
time-window availability query, D46), **4.4** (booking creation — the first write
path — with the D3/D41 slot-locked concurrency guard, D47–D49), **4.5**
(effective status for a lapsed hold: a read-only, computed `effective_status`,
D50) and **4.6** (the confirmation seam for Phase 5's payment gateway, and a
random, unguessable public `reference` on every booking — D51/D52); its lifecycle
lands increment by increment, next **4.7**, cancellation. The authoritative
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
│   └── phase-4-booking/    # booking model, rules, duration policy (D39-D52; D39 revised in 4.2)
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
│       ├── payments/       # payments, mock gateway, refunds
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
| PATCH  | `/api/business-rules/` | Admin      | Change the max hourly rate / max booking hours |
| GET    | `/api/parking-lots/{lot}/availability/` | Public | Slots bookable for `?start=&end=` (4.3) |
| GET    | `/api/bookings/`       | Consumer   | List the caller's own bookings (4.4) |
| POST   | `/api/bookings/`       | Consumer   | Create a booking (4.4) |

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
