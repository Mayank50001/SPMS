# Progress — Phases 0 & 1 (foundation)

> Combines Phases 0 (repository setup) and 1 (backend foundation): Phase 0 is
> repository scaffolding with no behaviour, Phase 1 is the Django/PostgreSQL/DRF
> wiring. Both are complete. Cross-cutting decisions live in
> [`DECISIONS.md`](DECISIONS.md).

Last updated: 2026-10-01

---

## Phase 0 — Repository setup ✅

- Git repository at the project root; `PROJECT.md` is the authoritative spec.
- Backend: Django project (`backend/manage.py`, `backend/config/`) with a
  modular-monolith app layout under `backend/apps/` (`accounts`, `parking`,
  `bookings`, `payments`, `notifications`, `reports`).
- Frontend: React + TypeScript + Vite scaffold under `frontend/`, with the Vite
  dev proxy routing `/api` to the Django dev server. **Not developed further
  until Phase 9.**
- PostgreSQL database provisioned (`createdb spms`).
- Environment configuration: `backend/.env` (git-ignored) and
  `backend/.env.example`; loaded by the stdlib loader (D9).
- Root `README.md`, `.gitignore`.

## Phase 1 — Backend foundation ✅

- `config/settings.py`: single settings module; PostgreSQL is the fixed engine
  (D4); `USE_TZ=True`, `TIME_ZONE="UTC"`, `BUSINESS_TIMEZONE` (D5).
- `config/urls.py`: routes the Django admin, `GET /api/health/` (D10) and,
  since Phase 2, the accounts API. Future domain APIs are added incrementally,
  each through its own `apps/<domain>/urls.py`.
- `config/views.py`: the health view (`{"status": "ok"}`). It later gained an
  explicit `AllowAny` when DRF permissions became deny-by-default (D18).
- DRF configured (`REST_FRAMEWORK`); CORS restricted to the Vite dev origin.
- `requirements.txt` pins the backend dependencies (Django 6, DRF,
  simplejwt, psycopg2, cors-headers).

### Database reset note

The database was dropped and recreated before the first `accounts` migration,
because `auth_user` already existed from an earlier `migrate` that ran before
`AUTH_USER_MODEL` was set. **Any local database created before that point is not
reusable.** See Phase 2 for the custom user model.

### Known repository hygiene

`requirements.txt` still pins `redis==8.1.0` and `pillow==12.3.0`, neither of
which is imported. D6 avoids Redis and PROJECT.md §12 forbids introducing it
without approval. See [`../deferred-features.md`](../deferred-features.md).
