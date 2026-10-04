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
D39–D41) and **4.2** (the booking rule layer: `quote_booking`, the D41 conflict
predicate, lazy hold expiry, the stored **`base_amount`** snapshot — D39 revised
— and the per-slot duration policy **D45**); its API and lifecycle land increment
by increment, next **4.3**, the time-window availability query. The authoritative
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
│   └── phase-4-booking/    # booking model, rules, duration policy (D39-D45; D39 revised in 4.2)
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
