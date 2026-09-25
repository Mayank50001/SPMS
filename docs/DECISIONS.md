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

## D11 — Custom User model: email login, single `role` field, `is_active` suspension

- **Decision:** `apps.accounts.User` extends `AbstractBaseUser` +
  `PermissionsMixin`. `email` is the `USERNAME_FIELD` (unique login
  identifier); `phone` is optional and unique; `full_name` is required;
  `role` is a `TextChoices` enum (`CONSUMER`, `MANAGER`, `ADMIN`) defaulting
  to the least-privileged `CONSUMER`; account suspension is modelled by
  `is_active=False`. A custom `UserManager` provides `create_user` /
  `create_superuser` (the latter forces `is_staff`, `is_superuser`,
  `role=ADMIN`). `AUTH_USER_MODEL = 'accounts.User'`.
- **Rationale:** Email is the natural login identifier for an SPA (no separate
  username); a single role field models the three actors in PROJECT.md §16
  without a permissions-matrix table; `is_active=False` gives the
  Administrator the "suspend users" capability required by §16. The database
  was reset (dropped and recreated) before the first accounts migration
  because `auth_user` had already been created by an earlier `migrate`.
- **Status:** Model, manager, settings wiring, admin registration, consumer
  self-registration (`POST /api/auth/register/`) and the full JWT surface
  (login, refresh, logout, `me`) implemented and manually verified. Role and
  authorization enforcement (`TODO(HUMAN)` at `models.py:84`), the `Vehicle`
  model and Administrator-only account creation remain open.

## D12 — Password hashing is guaranteed by overriding `create()`, not by the field

- **Decision:** `RegisterSerializer` overrides `create()` and delegates to
  `User.objects.create_user()` (which calls `set_password`). A password never
  reaches the model's default `ModelSerializer.create()` path.
- **Rationale:** `AbstractBaseUser.password` is an ordinary `CharField`, and only
  the manager hashes it. Django's default serializer path calls
  `User.objects.create(**validated_data)`, which is unaware of that contract and
  would store the password in clear text. The override is therefore a
  correctness requirement, not a preference. It lives on the serializer rather
  than in the view's `perform_create()` so that every caller of the serializer
  inherits the guarantee.
- **Status:** Implemented and manually verified.

## D13 — Email is canonicalised to lower case; uniqueness is case-insensitive

- **Decision:** `User.save()` strips and lower-cases `email` before persisting,
  and the registration serializer checks duplicates with
  `UniqueValidator(lookup="iexact")`.
- **Rationale:** `email` is the login identifier and needs exactly one stored
  representation. RFC 5321 permits a case-sensitive local part, but every major
  provider (Gmail, Outlook, Yahoo, iCloud) treats addresses case-insensitively —
  Gmail additionally ignores dots — so two accounts differing only in case are a
  login bug in practice. Normalising in `save()` covers the serializer, the
  Django admin, `createsuperuser`, the shell and fixtures;
  `UserManager.normalize_email` lower-cases only the *domain* part and is not
  sufficient alone. The `iexact` lookup exists so that a case-variant duplicate
  returns a clean `400` rather than a Postgres `IntegrityError` (`500`).
- **Known gap:** `.update()` querysets bypass `save()`. Nothing does this today.
  A database-level `UniqueConstraint(Lower("email"))` is the Phase 10 hardening
  step.
- **Status:** Implemented and manually verified.

## D14 — Password policy is Django's validator stack, invoked at object level

- **Decision:** `AUTH_PASSWORD_VALIDATORS` is the single source of password
  policy. It is invoked by calling
  `validate_password(password, user=<unsaved User>)` inside the serializer's
  `validate()`, not via a field-level `validators=[validate_password]`.
- **Rationale:** The field-level shorthand passes no `user`, which silently
  disables `UserAttributeSimilarityValidator` — the code would appear to run four
  validators while actually running three. Passing an unsaved `User` carrying the
  incoming email and full name makes the similarity check fire. Keeping the
  policy in settings means tightening it later is a settings change with no code
  change.
- **Status:** Implemented and manually verified.

## D15 — `role` is never a JWT claim; authorization reads it from the database

- **Decision:** The access token carries `token_type`, `exp`, `iat`, `jti` and
  `user_id` only. No role or profile data is embedded. `role` is returned in the
  login *response body* and by `GET /api/auth/me/`, but authorization decisions
  always read `request.user.role`.
- **Rationale:** simplejwt's `JWTAuthentication` loads the user from the database
  on every request (it needs `request.user` for ownership checks anyway), so
  `request.user.role` is always current. A role embedded in the token would be a
  second, staler source of truth, and a client holding a role that disagrees with
  the database is exactly how privilege-escalation bugs are built (§24, §45).
  This also settles the suspension question: because the user is re-read per
  request, `is_active=False` takes effect on the very next request with no
  revocation list, and `TokenObtainPairSerializer` refuses to issue tokens to an
  inactive account at all.
- **Status:** Implemented and manually verified (claims inspected; a
  still-unexpired access token was observed to fail immediately on suspension).

## D16 — Login returns the account profile alongside the token pair

- **Decision:** `POST /api/auth/login/` responds with `access`, `refresh` and
  `user` (`id`, `email`, `full_name`, `phone`, `role`, `created_at`).
  `UserSerializer` is shared between the login response and
  `GET /api/auth/me/` so both return one identical shape.
- **Rationale:** The SPA needs the role immediately in order to route, and a
  second request purely to learn it is a wasted round trip. Sharing one
  serializer prevents the two responses from drifting apart. The object is a
  display snapshot only — it is not an authority (D15).
- **Status:** Implemented and manually verified.

## D17 — Refresh tokens rotate and are blacklisted; logout is server-side

- **Decision:** `ROTATE_REFRESH_TOKENS` and `BLACKLIST_AFTER_ROTATION` are
  enabled, and `POST /api/auth/logout/` blacklists the presented refresh token
  via `rest_framework_simplejwt.token_blacklist`. Access tokens live 30 minutes,
  refresh tokens 7 days.
- **Rationale:** An access token cannot be revoked in any variant, so
  client-side logout would leave a stolen token usable until expiry. Rotation
  makes each refresh token single-use, so a stolen one is usable at most once and
  the thief's use invalidates the legitimate session — a detectable signal rather
  than silent long-term access. A short access lifetime bounds the residual
  window. The cost is one extra third-party app and its migrations.
- **Known limitation:** Logout revokes refresh tokens only; the caller's live
  access token remains valid until it expires. This is inherent to stateless JWT,
  not an implementation gap.
- **Status:** Implemented and manually verified (rotation, replay rejection,
  logout revocation).

## D18 — DRF permissions are deny-by-default

- **Decision:** `DEFAULT_PERMISSION_CLASSES = [IsAuthenticated]`. Public
  endpoints opt out explicitly with `permission_classes = [AllowAny]`.
- **Rationale:** The failure mode of forgetting matters more than the default's
  convenience. Deny-by-default fails closed — a forgetful omission produces a
  `401` that surfaces immediately, whereas allow-by-default produces an exposed
  endpoint. For a system with ownership invariants (§20) the closed failure mode
  is the only defensible default. Four endpoints opt out today:
  `/api/health/`, `/api/auth/register/`, `/api/auth/login/` and
  `/api/auth/refresh/`.
- **Consequence:** `/api/health/` is a DRF view and therefore needed an explicit
  `AllowAny`; without it the liveness probe returns `401`. Any future public
  endpoint needs the same opt-out.
- **Status:** Implemented and manually verified.

## D19 — JWT signing key is separate from `SECRET_KEY`

- **Decision:** `SIMPLE_JWT["SIGNING_KEY"]` reads `JWT_SIGNING_KEY` from the
  environment, falling back to `SECRET_KEY` when unset or empty.
- **Rationale:** Sharing one secret means rotating the Django secret silently
  invalidates every token in circulation, and rotating the JWT key would force a
  Django secret rotation. Separating them makes each rotation independent. The
  fallback keeps local development working with no extra configuration.
- **Status:** Implemented.

## D20 — Manager and Administrator accounts are created only by an Administrator

- **Decision:** There is no self-registration or invitation flow for privileged
  roles. `POST /api/auth/register/` can only ever produce a `CONSUMER` (D11); a
  Manager or Administrator account is created by an existing Administrator
  through an administrative endpoint.
- **Rationale:** PROJECT.md §16 specifies Administrator-created Manager and
  Administrator accounts, and the developer confirmed (2026-09-25) that this
  matches the intended operating process: a prospective manager contacts the
  platform out of band, and an Administrator then registers the account. Because
  the actor is always an Administrator, the privilege-escalation question
  ("may a Manager create an Administrator?") collapses to a single permission
  check rather than a role-transition matrix.
- **Status:** Decided; the endpoint is not yet implemented (Phase 2 remainder).
