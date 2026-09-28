# Smart Parking Management System (SPMS)

An academic mini-project: a software-based parking management platform that lets
consumers discover lots and book slots, managers operate lots and walk-ins, and
administrators manage users and view platform reports.

Currently at **Phase 2 (authentication and users)**. Phase 0 (repository setup)
and Phase 1 (backend foundation) are complete. Implemented so far: the custom
email-based user model, consumer self-registration, the JWT authentication
surface, consumer profile self-update, Administrator user management
(list/create/suspend/role change) and role-based authorization. The one
remaining Phase 2 feature is consumer **vehicle registration**, after which
Phase 3 (the parking domain) begins. The authoritative specification is
[`PROJECT.md`](PROJECT.md). For what is built and what comes next see
[`docs/PROGRESS.md`](docs/PROGRESS.md); for the agreed architecture decisions see
[`docs/DECISIONS.md`](docs/DECISIONS.md).

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
├── docs/
│   ├── DECISIONS.md        # decision log (agreed architecture decisions)
│   └── PROGRESS.md         # phase tracker + current working state
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

> Authorisation is enforced server-side on every request (D15, D18). `Admin`
> above means the authenticated account's `role` must be `ADMIN`; a `403` is
> returned otherwise and a `401` when unauthenticated. Self-registration can
> only produce a `CONSUMER`; privileged accounts exist only via `POST /api/users/`.

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
