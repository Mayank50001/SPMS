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
  identifier); `phone` is optional and non-unique (see D23); `full_name` is
  required; `role` is a `TextChoices` enum (`CONSUMER`, `MANAGER`, `ADMIN`)
  defaulting to the least-privileged `CONSUMER`; account suspension is modelled
  by `is_active=False`. A custom `UserManager` provides `create_user` /
  `create_superuser` (the latter forces `is_staff`, `is_superuser`,
  `role=ADMIN`). `AUTH_USER_MODEL = 'accounts.User'`.
- **Rationale:** Email is the natural login identifier for an SPA (no separate
  username); a single role field models the three actors in PROJECT.md §16
  without a permissions-matrix table; `is_active=False` gives the
  Administrator the "suspend users" capability required by §16. The database
  was reset (dropped and recreated) before the first accounts migration
  because `auth_user` had already been created by an earlier `migrate`.
- **Status:** Model, manager, settings wiring, admin registration, consumer
  self-registration, the full JWT surface, role-based authorization
  (`permissions.py`), Administrator account creation and role
  change/suspend (D24, D26, D27) are implemented and verified. Within Phase 2
  only the `Vehicle` model + CRUD remains open.

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
- **Status:** Fully implemented. Creation (`POST /api/users/`, D26), listing and
  retrieval, and changing an **existing** account's role or `is_active`
  (D24/D27) are all live; only an Administrator can reach the surface.

## D21 — Email login canonicalises the identifier, then matches exactly

- **Decision:** `email` is stored canonicalised (stripped and lower-cased) by
  `User.save()`, and `UserManager.get_by_natural_key` strips and lower-cases the
  *incoming* identifier before an exact `get(email=...)`. No case-insensitive
  (`iexact`/`UPPER()`) database comparison is used.
- **Rationale:** D13 makes email the login identifier and requires matching to be
  case-insensitive, but `ModelBackend.authenticate` looks the user up through
  `get_by_natural_key`, which was a plain exact `get`. That made login
  case-sensitive: a user who registered as `John@Gmail.com` (stored
  `john@gmail.com`) could not log in by typing `John@Gmail.com`. Canonicalising
  both sides satisfies D13's intent while keeping the comparison exact, so it
  still uses the unique index. Placing the rule in the manager — rather than in
  `LoginSerializer` — makes every authentication path benefit, including the
  Django admin and `manage.py shell`, so no future entry point has to remember
  to normalise. The rejected alternative, an `iexact` lookup at the manager, was
  functionally equivalent here but would have forced a non-indexed comparison.
- **Consequence:** Two accounts differing only by email case remain impossible via
  the API (the registration serializer's `iexact` `UniqueValidator` rejects
  them); a raw-SQL/`.update()` insert bypassing `save()` could still create one,
  which is the same Phase 10 gap D13 already records.
- **Status:** Implemented and verified (`apps/accounts/tests.py`:
  `EmailNormalisationTests`).

## D22 — Password similarity is checked against `email` and `full_name`

- **Decision:** The `UserAttributeSimilarityValidator` entry in
  `AUTH_PASSWORD_VALIDATORS` is configured with
  `OPTIONS: {"user_attributes": ("email", "full_name")}`, replacing Django's
  default list (`username`, `first_name`, `last_name`, `email`). Configuration is
  done through `OPTIONS` in settings rather than a validator subclass.
- **Rationale:** None of the default attribute names exists on this `User` model
  (its name field is `full_name`, and there is no `username`/`first_name`/
  `last_name`), and the validator silently skips attributes that are absent. As a
  result the password was compared against the email only, voiding D14's claim
  that the name was covered. `OPTIONS` is sufficient because Django's
  `get_password_validators` constructs each validator as `klass(**OPTIONS)` and
  the validator's constructor accepts `user_attributes` directly; a subclass
  would add a class to maintain for no extra behaviour. Keeping the policy in
  settings preserves D14's single-source-of-truth property.
- **Consequence:** A password equal to the full name, or to one word of it, is
  now rejected (`password_too_similar`). `phone` is intentionally not compared:
  the registration serializer's unsaved `User` candidate does not carry it, and
  it is optional. Revisit if password/phone similarity is wanted.
- **Status:** Implemented and verified (`settings.py`,
  `apps/accounts/tests.py::PasswordSimilarityTest`).

## D23 — `phone` is optional, non-unique contact info

- **Decision:** `User.phone` keeps `null=True` / `blank=True` but **drops**
  `unique=True`. It is stored digits-only (spaces/`+`/dashes stripped), is
  optional, may be shared by more than one account, and is **not** verified in
  the core project. Email-OTP verification is a separate deferred feature.
- **Rationale:** The original design made `phone` globally unique and writable
  with no way to prove ownership. Anyone could register someone else's number,
  permanently blocking the real owner, and the endpoint became an
  account-existence oracle for any number. The proposed email-OTP fix does not
  address this: it proves ownership of the **email**, not the phone, so the lock
  would survive untouched. Phone is not an authentication factor (login is by
  email), so global uniqueness buys nothing and only creates the lock.
- **Consequence:** Two accounts may share a phone number; PROJECT.md §35's
  "duplicate phone" is no longer an error by design. If duplicate detection is
  later wanted it is a soft/admin concern, or a constraint on *verified* numbers
  once phone verification exists. Digits-only storage avoids `"98765 43210"`
  and `"9876543210"` being treated as different values; `max_length=15` still
  holds (E.164's maximum is 15 digits).
- **Status:** Implemented and verified (`models.py::User.normalize_phone` +
  `save()`, migration `0002_alter_user_phone`, `apps/accounts/tests.py::PhoneFieldTests`).
  Existing rows are not retro-normalised; a data check is in PROGRESS.md.

## D24 — `role` is mutable by an Administrator; the last Administrator is protected

- **Decision:** `role` is **not** frozen at creation. An Administrator may change
  another account's role or active status through `PATCH /api/users/{id}/`
  (D27). Authority is
  **global** — there is one pool of Administrators, not region-scoped ones. The
  **last active Administrator** (an account with `role=ADMIN` and
  `is_active=True`) can neither be demoted nor suspended, so the platform can
  never be left with zero administrators. Regional administration is explicitly
  deferred (see PROGRESS.md "Deferred features"), and audit logging of role and
  suspension changes is deferred.
- **Rationale:** PROJECT.md §16 gives Administrators user management, and the
  operating model needs to correct mistakes (a Manager promoted in error). The
  lockout risk is the one guard that matters: without it, a single demotion could
  make user management impossible with no in-app recovery. Global scope is chosen
  deliberately for simplicity (PROJECT.md §47): region-scoped administrators —
  where each Administrator supervises the lots and Managers of one region —
  are a real design but add a `Region` entity, a conditional
  `role=ADMIN ⇒ region` constraint, region-scoped authorization across accounts,
  parking and reports, and a region-aware demotion guard. That is out of scope
  for the academic build and is recorded for a future phase instead.
- **Consequence:** An Administrator can change their own role when other active
  Administrators remain (the guard, not a self-check, prevents lockout). The guard
  is a count of active Administrators and must be evaluated inside a transaction
  with row locking at implementation time: two Administrators demoting each other
  concurrently could each observe "another admin exists" and both proceed, ending
  with zero — the same class of race as booking (D3). Role changes take effect on
  the next request with no token invalidation, because D15 re-reads the user.
- **Status:** Implemented. `PATCH /api/users/{id}/` carries the guard, and the
  single-ordered-lock transactional check described above lives in
  `apps/accounts/services.py::update_user_access` (see D27). Verified by
  `apps/accounts/tests.py::UserAccessUpdateTests`.

## D25 — Consumer profile self-update via `PATCH /api/auth/me/`

- **Decision:** `MeView` becomes a `RetrieveUpdateAPIView`. `GET` returns the full
  profile through `UserSerializer`; `PATCH` accepts only `full_name` and `phone`
  through `ProfileUpdateSerializer` and responds with the full read shape again.
  `PUT` is disabled. `email` is **not** editable (it is the login identifier and
  changing it needs re-verification), and `role`, `is_active` and `password` are
  not fields, so a consumer cannot alter their own privileges or status.
- **Rationale:** The object is always `request.user` and no id appears in the URL,
  so ownership (PROJECT.md §20 Invariant 2) is structural rather than a permission
  check that can be forgotten. Disabling `PUT` prevents a partial payload from
  blanking the profile. Answering `PATCH` with the read serializer keeps one shape
  per resource, so a frontend never special-cases GET versus PATCH.
- **Consequence:** `email` changes remain an open gap until email-OTP verification
  exists. Phone changes reuse D23's digits-only normalisation. No migration.
- **Status:** Implemented and verified (`apps/accounts/tests.py::ProfileUpdateTests`).

## D26 — Administrator user-management endpoints

- **Decision:** `apps/accounts` exposes an Administrator-only user surface:
  `GET /api/users/` (list; optional `role`, `is_active` and `search` filters),
  `GET /api/users/{id}/`, and `POST /api/users/`. All three require `IsAdmin`.
  `POST` creates only `MANAGER` and `ADMIN` accounts (D20): `role` is a
  `ChoiceField` limited to those two, so a `CONSUMER` cannot be created here.
  Every response is a `UserSerializer`, and `is_staff`/`is_superuser` are never
  exposed, keeping API authority (`role`) separate from Django-admin access.
- **Rationale:** D20 names Administrators as the creators of privileged accounts,
  which makes this the only path to a `MANAGER`/`ADMIN` account (self-registration
  is hardwired to `CONSUMER`). Restricting the roles prevents two divergent
  registration paths for consumers. Returning one read shape for `GET` and `POST`
  makes password leakage structurally impossible. The filter/search logic is
  written with query-param `if`s rather than `django-filter`, because that package
  is not installed and PROJECT.md §12 forbids adding dependencies unapproved.
- **Consequence:** The Administrator sets the initial password and it is validated
  by the same `AUTH_PASSWORD_VALIDATORS` stack as registration (D14); there is no
  forced-change-on-first-login yet. The list endpoint is unpaginated (Phase 10
  hardening). Role change and suspend/activate are implemented separately (D27).
- **Status:** Implemented and verified
  (`apps/accounts/tests.py::AdminUserManagementTests`).

## D27 — Role change / suspension endpoint `PATCH /api/users/{id}/`

- **Decision:** The Administrator access-management surface is a `PATCH` on the
  existing `UserDetailView`. It accepts `role` and/or `is_active`, both optional
  but at least one required, and answers with the `UserSerializer` read shape.
  `PUT` is disabled. The write is **not** performed in the view or serializer:
  both delegate to `apps/accounts/services.py::update_user_access`, which applies
  the D24 last-active-Administrator guard. A refusal returns
  `409 {"error": "LAST_ADMINISTRATOR", "message": ...}`.
- **Rationale:** Keeping the guard in a service function, rather than inline,
  means a future caller (a bulk action, a management command, the admin) cannot
  perform an unguarded role change by accident. A plain `serializers.Serializer`
  — not a `ModelSerializer` — is enough because no field is written directly;
  the serializer only validates the request shape, and a model serializer would
  invite a default `update()` that bypasses the service. `409 Conflict` is used
  because the request is well-formed and the caller is authorized: the refusal is
  about the resulting system state, which `400` would misrepresent. Disabling
  `PUT` mirrors D25 — a partial `PUT` must not be able to blank `role`/`is_active`.
- **Consequence:** `update_user_access` locks, in a single
  `select_for_update()` query ordered by primary key, every active Administrator
  **plus** the target. Locking the whole decision set in one ordered statement
  gives all callers the same lock order, so two mutual demotions cannot deadlock
  and cannot both observe "another admin exists". The predicate
  `stop_being_active_admin` compares current vs. new state, so a no-op `PATCH`
  (e.g. setting an active Administrator to `role=ADMIN`) is allowed. A role
  change or reactivation takes effect on the next request (D15). Audit logging
  of these changes remains deferred.
- **Status:** Implemented and verified
  (`apps/accounts/tests.py::UserAccessUpdateTests`; 44 tests pass for the app).
