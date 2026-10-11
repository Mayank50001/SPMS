# Foundation decisions (D1–D10, plus cross-cutting D66)

Cross-cutting decisions that every later phase depends on. D1–D10 were agreed
during Phase 0/1 planning; later cross-cutting additions (currently **D66**) are
appended at the end. They are implemented across phases (see the "Implemented
in" column in [`../decisions-index.md`](../decisions-index.md)). These are not
open for re-litigation by the coding agent.

> Read this file only when the current phase's "Dependencies on earlier phases"
> section names one of these IDs.

---

## D1 — Authentication: JWT via `djangorestframework-simplejwt`

- **Decision:** Authentication will use JWT access/refresh tokens issued by
  `djangorestframework-simplejwt`.
- **Rationale:** Stateless, standard for DRF, avoids session coupling to the
  SPA frontend, and requires no extra infrastructure.
- **Status:** Implemented and verified. Configured in `config/settings.py`
  (`SIMPLE_JWT`, `JWTAuthentication`); login/refresh/logout/`me` live (D15–D19).

## D2 — Slot status is LIVE state only; availability is DERIVED

- **Decision:** `ParkingSlot.status` is a stored field representing *live*
  physical state: `AVAILABLE`, `HELD`, `OCCUPIED`, `OUT_OF_SERVICE`. Here
  "unavailable" means `OUT_OF_SERVICE`. Time-window availability is **not**
  stored — it is derived by querying overlapping bookings.
- **Rationale:** Prevents the stored status from drifting out of sync with the
  booking schedule; a single source of truth for each concern.
- **Status:** Design agreed. No `ParkingSlot` model exists yet.
- **⚠ Revised by D33 (2026-10-01):** the stored enumeration is reduced to
  `AVAILABLE`, `OCCUPIED`, `OUT_OF_SERVICE`. `HELD` (a temporary booking hold)
  and `RESERVED` are **derived from bookings**, never stored — PROJECT.md §18
  forbids collapsing physical occupancy, reservation and hold. See
  [`../phase-3-parking/DECISIONS.md`](../phase-3-parking/DECISIONS.md).

## D3 — Booking concurrency: atomic transaction + row lock + overlap check

- **Decision:** Booking creation will use `transaction.atomic()` with
  `select_for_update()` on the slot row followed by an overlap check.
- **Rationale:** Serialises competing bookings for the same slot and upholds
  Invariant 1 (no two confirmed overlapping bookings for the same slot).
- **Status:** Design agreed; implementation lands in Phase 4 increments
  4.3–4.4. **Confirmed and elaborated by D41** (half-open `[start, end)` window;
  blocking states; lazy-hold exclusion; no DB `EXCLUDE` constraint) in
  [`../phase-4-booking/DECISIONS.md`](../phase-4-booking/DECISIONS.md).

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

## D66 — List endpoints return a paginated envelope

- **Decision:** every collection-list endpoint is paginated globally with a
  custom `PageNumberPagination` (`config.pagination.DefaultPagination`): default
  page size **20**, a client-tunable `?page_size=` capped at **100**, and the
  standard envelope `{"count", "next", "previous", "results"}`. Two
  bounded/derived reads opt out with `pagination_class = None` —
  `GET /api/cities/` (a seeded vocabulary used as a `<select>`) and
  `GET /api/parking-lots/{lot}/availability/` (a computed window set the slot
  grid consumes whole). `GET /api/business-rules/` is a singleton, not a list,
  and is unaffected.
- **Rationale:** freezes the list contract **before** the frontend binds to it,
  so the Phase 10 hardening pass does not have to re-shape every list response.
  Page numbers map directly onto table pagination and `count` supports "x of y".
- **Options considered:** page-number vs limit/offset vs cursor pagination.
  Page-number chosen: academic datasets are small and bounded, page numbers are
  human-visible in the UI, and `count` is available (cursor pagination exposes
  no `count` and cannot seek an arbitrary page).
- **Consequences:** D55 (booking history) and D65 (payment history) said "no
  pagination"; those reads are now paginated, so D66 **revises** that note. D46
  (availability) is unchanged — the grid read is explicitly exempted. The
  frontend reads `results` and drives `?page=` itself from `count`; an invalid
  `?page=` is DRF's `404`.
- **Status:** Accepted 2026-10-11. Applied in `config/settings.py`
  (`REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"]`) with the class in
  `config/pagination.py`; the two exemptions live in `apps/parking/views.py`.
  The frozen frontend-facing contract is [`../api-contract.md`](../api-contract.md).
