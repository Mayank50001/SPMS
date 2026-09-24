# Decision Log

Agreed, finalised architecture decisions for SPMS. These are not open for
re-litigation by the coding agent; each entry records the decision and its
one-line rationale. Complements the spec in [`PROJECT.md`](../PROJECT.md).

---

## D1 — Authentication: JWT via `djangorestframework-simplejwt`

- **Decision:** Authentication will use JWT access/refresh tokens issued by
  `djangorestframework-simplejwt`.
- **Rationale:** Stateless, standard for DRF, avoids session coupling to the
  SPA frontend, and requires no extra infrastructure.
- **Status:** Planned only. Not installed or configured in Phase 0/1.

## D2 — Slot status is LIVE state only; availability is DERIVED

- **Decision:** `ParkingSlot.status` is a stored field representing *live*
  physical state: `AVAILABLE`, `HELD`, `OCCUPIED`, `OUT_OF_SERVICE`. Here
  "unavailable" means `OUT_OF_SERVICE`. Time-window availability is **not**
  stored — it is derived by querying overlapping bookings.
- **Rationale:** Prevents the stored status from drifting out of sync with the
  booking schedule; a single source of truth for each concern.
- **Status:** Design agreed. No `ParkingSlot` model exists yet.

## D3 — Booking concurrency: atomic transaction + row lock + overlap check

- **Decision:** Booking creation will use `transaction.atomic()` with
  `select_for_update()` on the slot row followed by an overlap check.
- **Rationale:** Serialises competing bookings for the same slot and upholds
  Invariant 1 (no two confirmed overlapping bookings for the same slot).
- **Status:** Design agreed; implementation is the human developer's TODO.

## D4 — PostgreSQL is mandatory

- **Decision:** The database engine is PostgreSQL; it will not be replaced
  (incl. no silent fallback to SQLite).
- **Rationale:** Required for row-level locking (`select_for_update`) and
  transactional integrity the concurrency design depends on.

## D5 — Time: store UTC, display business timezone for reports

- **Decision:** `USE_TZ = True` and `TIME_ZONE = 'UTC'` for storage. A separate
  `BUSINESS_TIMEZONE = 'Asia/Kolkata'` setting is used **only** for report
  day-bucketing.
- **Rationale:** Unambiguous absolute timestamps in the DB, while business
  reports still group by local (IST) calendar days.

## D6 — Hold / payment expiry is LAZY-evaluated

- **Decision:** Temporary holds and pending payments expire via lazy evaluation
  at read/query time — no background scheduler.
- **Rationale:** Avoids introducing Celery/Redis; keeps the modular monolith
  simple while still honouring Invariant 6 (expired holds must not block slots).

## D7 — Testing: Django's built-in test runner

- **Decision:** Use Django's `TestCase` / `TransactionTestCase`; not pytest.
- **Rationale:** Zero extra dependencies and first-class support for database
  transaction test isolation, which matters for concurrency tests.

## D8 — `Booking.user` is nullable (walk-in support)

- **Decision:** The future `Booking.user` foreign key will be nullable to
  represent manager-created walk-in bookings.
- **Rationale:** Walk-ins may not correspond to a registered consumer account.
- **Status:** Planned; no models are created in this phase.

## D9 — `.env` loading uses the Python standard library

- **Decision:** `backend/.env` is parsed by a small stdlib loader in
  `config/settings.py`; real process environment variables always take
  precedence over file values.
- **Rationale:** Satisfies the environment-variable requirement (§44) without
  adding a new dependency, keeping the setup minimal and auditable.

## D10 — Health endpoint lives in `config`, not a new app

- **Decision:** `GET /api/health/` is implemented in `config/views.py` and
  routed in `config/urls.py`.
- **Rationale:** It is an infrastructure concern, not a domain concern; adding
  an app for it would be premature structure.
