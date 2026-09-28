# Progress & Working State

Companion to [`DECISIONS.md`](DECISIONS.md) (agreed architecture decisions) and
[`PROJECT.md`](../PROJECT.md) (authoritative specification).

**Purpose:** one place to re-establish context at the start of a session — what
is built, what is next, and which decisions are still open. Update at the end of
every milestone.

Last updated: 2026-09-29 · Current phase: **2 — Authentication and users**
(next: the `Vehicle` model — the last Phase 2 feature)

---

## Phase tracker

| Phase | Scope | Status |
|-------|-------|--------|
| 0 | Repository setup | ✅ Done |
| 1 | Backend foundation (config, PostgreSQL, health) | ✅ Done |
| 2 | **Authentication and users** | 🔵 In progress — auth, profile, privileged accounts, role change/suspend done; `Vehicle` remains |
| 3 | Parking domain (lots, slots, pricing) | ⚪ Not started |
| 4 | Booking | ⚪ Not started |
| 5 | Payment | ⚪ Not started |
| 6 | Occupancy simulation | ⚪ Not started |
| 7 | Notifications | ⚪ Not started |
| 8 | Reports | ⚪ Not started |
| 9 | React frontend | ⚪ Not started |
| 10 | Testing and hardening | ⚪ Not started |

---

## Phase 2 — completed

### Custom user model (D11)

- `apps/accounts/models.py` — `User` on `AbstractBaseUser` + `PermissionsMixin`,
  `email` as `USERNAME_FIELD`, single `role` field (`CONSUMER` / `MANAGER` /
  `ADMIN`), suspension via `is_active=False`. `UserManager` with `create_user` /
  `create_superuser`.
- `apps/accounts/admin.py` — `UserAdmin` registration.
- `apps/accounts/migrations/0001_initial.py` — applied.
- `config/settings.py` — `AUTH_USER_MODEL = "accounts.User"`.

> The database was dropped and recreated before this migration because
> `auth_user` already existed from an earlier `migrate`. Any local database
> created before that point is not reusable.

### Consumer self-registration

- `POST /api/auth/register/` → `201` with `id`, `email`, `full_name`, `phone`.
- Password hashed via `UserManager.create_user` (D12), validated by the
  `AUTH_PASSWORD_VALIDATORS` stack invoked at object level (D14).
- Email canonicalised to lower case; duplicates detected case-insensitively
  (D13).
- `role` is not a serializer field, so a client cannot propose one.
- Verified: hashing, weak-password rejection, similarity rejection, case-variant
  duplicate rejection, role-injection ignored.

### JWT authentication surface (D15–D19)

- `SIMPLE_JWT` configured in `config/settings.py`; `token_blacklist` app
  installed and its migrations applied.
- `DEFAULT_AUTHENTICATION_CLASSES = [JWTAuthentication]` — JWT only, no session
  auth. `DEFAULT_PERMISSION_CLASSES = [IsAuthenticated]` — deny by default.
- `config/views.py` — `health` gained an explicit `AllowAny` and the unrouted
  `health_plain` fallback was removed.

| Method | Endpoint | Auth | Notes |
|---|---|---|---|
| POST | `/api/auth/register/` | public | `AllowAny` opt-out |
| POST | `/api/auth/login/` | public | returns `access`, `refresh`, `user` |
| POST | `/api/auth/refresh/` | public | rotates the refresh token |
| POST | `/api/auth/logout/` | Bearer | blacklists the refresh token |
| GET | `/api/auth/me/` | Bearer | own profile, no id in the URL |
| PATCH | `/api/auth/me/` | Bearer | update own `full_name` / `phone` (D25) |
| GET | `/api/health/` | public | needed the new `AllowAny` (D18) |

- Verified by hand: token pair issued; no role present in the token claims;
  `/me/` without a header → `401`; refresh rotation; replay of a consumed
  refresh token → `401`; logout revocation; and an immediate `401` on a
  still-unexpired access token once `is_active=False`.
- Known limitation (D17): logout revokes refresh tokens only. A live access token
  stays valid until it expires — inherent to stateless JWT, bounded by the
  30-minute lifetime.

### Account and user management surface (D23, D25, D26)

- `phone` is optional, non-unique and stored digits-only (D23, migration
  `0002_alter_user_phone`).
- `MeView` is a `RetrieveUpdateAPIView`; `GET` and `PATCH` act on the caller's
  own profile (D25). `PUT` is disabled so a partial payload cannot blank it.

| Method | Endpoint | Auth | Notes |
|---|---|---|---|
| PATCH | `/api/auth/me/` | Bearer | edit own `full_name` / `phone`; `email`/`role` are not writable |
| GET | `/api/users/` | Admin | user directory; filters `role`, `is_active`, `search` |
| POST | `/api/users/` | Admin | create a `MANAGER` or `ADMIN` account (D20, D26) |
| GET | `/api/users/{id}/` | Admin | retrieve one account |
| PATCH | `/api/users/{id}/` | Admin | change `role` and/or `is_active` (D24, D27) |

- Verified by `apps/accounts/tests.py::{PhoneFieldTests, ProfileUpdateTests,
  AdminUserManagementTests}`. A Manager or Consumer gets `403` on the admin
  surface; anonymous gets `401`.

### Role change and suspension (D24, D27)

- `PATCH /api/users/{id}/` is Administrator-only. It accepts `role` and/or
  `is_active`; both are optional, at least one is required, and `PUT` is
  disabled (D27). Response is always the `UserSerializer` read shape.
- The write is delegated to `apps/accounts/services.py::update_user_access`,
  not performed in the serializer or view, so the last-active-Administrator
  guard (D24) cannot be bypassed by a second caller.
- The guard locks every row the decision depends on — the currently active
  Administrators plus the target — in one `select_for_update()` statement
  ordered by primary key, inside `transaction.atomic()`. This closes the
  concurrent mutual-demotion race (the same check-then-act class as D3).
- A refused change returns `409` with `{"error": "LAST_ADMINISTRATOR", ...}`
  (PROJECT.md §33 error shape) rather than a generic validation error.
- `role` takes effect on the next request, and suspension blocks the next
  request immediately, because `JWTAuthentication` re-reads the user (D15).
- Verified by `apps/accounts/tests.py::UserAccessUpdateTests`: demotion,
  suspend/reactivate, self-demotion with a second admin present, the
  last-Administrator guard on both demotion and suspension, immediate `401`
  after suspension of a live token, `403` for non-admins, `400` for an invalid
  role or an empty payload, and `405` for `PUT`.

---

## Phase 2 — correctness review (2026-09-25) — addressed 2026-09-27

Found by reading the code and reproducing each case in `manage.py shell`. All are
confined to `apps/accounts/`; none changes the architecture.

> **Status (2026-09-27):** B1–B5 resolved (B5 documented rather than refactored;
> see below); B6 resolved. Resolutions are recorded against each item. Regression
> tests added in `apps/accounts/tests.py`; `manage.py test apps.accounts` passed
> 33 tests at that point (44 after the role-change increment).

### B1 — `role` is writable (breaks D11 and D20) 🔴 — RESOLVED (verified 2026-09-27)

`RegisterSerializer.Meta.fields` listed `role` and did not mark it read-only, so
`POST /api/auth/register/` with `{"role": "ADMIN"}` created an Administrator. The
summary below that said "`role` is not a serializer field, so a client cannot
propose one" was **wrong**. This is the privilege-escalation path §24/§45 exist to
close.

**Fix applied:** `"role"` is not in `Meta.fields`. The model default supplies
`CONSUMER`.

### B2 — `password` is not `write_only`, so the hash is returned 🟠 — RESOLVED

`password_confirm` is declared `write_only=True`; `password` was left as the
auto-generated model field, which is not. Serialising a saved instance returned
`pbkdf2_sha256$1200000$...` in the response body.

**Fix applied:** `password` is now declared explicitly with `write_only=True`
(and `max_length=128`, mirroring the model field, so declaring it by hand does not
silently drop the limit). Both password fields are covered by the new tests.

### B3 — `User.save()` never persists the lower-cased email (breaks D13) 🔴 — RESOLVED

```python
def save(self, *args, **kwargs):
    if self.email:
        self.email.strip().lower()     # result discarded
    super().save(*args, **kwargs)
```

`strip()` and `lower()` return new strings; nothing was assigned. Verified: input
`CaseTest@Example.com` was stored as `CaseTest@example.com`
(`create_user` calls `normalize_email`, which lower-cases only the *domain*).

> **Correction:** the original note claimed `authenticate()` matches with
> `__iexact`, so "login still passes". That is **false**. `ModelBackend` calls
> `UserManager.get_by_natural_key`, which does an exact `get(email=...)`;
> reproduced against the live database, `authenticate("casetest@example.com")`
> returned `None`. The bug therefore broke login for any user who registered with
> mixed-case email.

**Fix applied:** `self.email = self.email.strip().lower()`. Reproduced before and
after: stored value is now `verifysave@example.com` and every casing authenticates.

### B3b — login lookup was case-sensitive — RESOLVED (with B3)

Fixing storage alone would have introduced a new trap: register `John@Gmail.com`
(stored `john@gmail.com`), then fail to log in when typing `John@Gmail.com`. The
lookup half is now handled in `UserManager.get_by_natural_key`, which strips and
lower-cases the incoming identifier before an exact match. Because both sides are
canonical, the comparison stays exact and index-friendly (no `iexact`). See D21.

### B4 — `validate_password(..., user=candidate)` cannot run the similarity check (voids D14's rationale) 🟡 — RESOLVED (2026-09-27)

`UserAttributeSimilarityValidator.DEFAULT_USER_ATTRIBUTES` is
`('username', 'first_name', 'last_name', 'email')`. This user model has no
`username` and no `first_name`; its name field is `full_name`, which is not in
that list. Verified with a name sharing no words with the email:

| password equals | before | after |
|---|---|---|
| the email | rejected | rejected |
| `full_name` | **accepted** | rejected |
| one word of the name | **accepted** | rejected |
| unrelated strong password | accepted | accepted |

The unsaved-`User` construction therefore enabled only the *email* comparison,
not the name comparison D14 claims.

**Fix applied (D22):** the first entry in `AUTH_PASSWORD_VALIDATORS` now passes
`OPTIONS: {"user_attributes": ("email", "full_name")}`. This is a **settings-only**
change — the registration serializer already builds its unsaved `User` with both
fields, so no code change was needed. The subclass the review suggested was
unnecessary: Django's loader constructs validators with `klass(**OPTIONS)`.
Tests: `PasswordSimilarityTest`.

### B5 — `User = get_user_model()` at import time 🟡 — DOCUMENTED (accepted)

`serializers.py` resolves the model during module import. Anything that imports
this module while apps are still loading raises `AppRegistryNotReady`. It works
today only because nothing imports it early.

> **Correction:** the suggested fix — "`Meta.model = User` (a lazy string)" — is
> **not possible**. DRF 3.18.1's `ModelSerializer` reads `self.Meta.model`
> directly and does not accept a `"app.Model"` string. Also,
> `UniqueValidator(queryset=User.objects.all())` is itself an import-time registry
> access, so a lazy `Meta.model` would not fully de-lazify the module anyway.

**Resolution (Option B, 2026-09-27):** keep `ModelSerializer` and the eager
`get_user_model()`, and document the constraint in the module docstring: the
module must not be imported from `models.py`, `apps.py` or any other app-loading
code. The realistic alternative (plain `serializers.Serializer` with explicit
fields and lazy lookups) was declined because the risk is latent and the benefit
does not justify hand-maintaining field constraints today.

### B6 — stale docstrings 🟢 — RESOLVED

- `apps/accounts/models.py` module docstring now points at `permissions.py` for
  role/authorization and no longer claims that logic is unimplemented; the
  resolved `is_active` `TODO(HUMAN)` (superseded by D15) was replaced with a note.
- `serializers.py` is now `black`-clean and documents the B5 constraint;
  `config/urls.py` docstring no longer says only health and admin are routed;
  `config/settings.py` no longer says JWT is "not configured in this task".

---

## Phase 2 — remaining

| Item | Notes |
|------|-------|
| `Vehicle` model + CRUD | **Next increment.** Consumer vehicle registration, scoped to the owner (§16, Invariant 2). Decision points are listed below and are the human's to own (§9) |
| Forced password change | Privileged accounts keep the Administrator-set initial password until changed (D26); needs a `must_change_password` flag + change-password endpoint |
| List pagination | `/api/users/` returns an unpaginated list (D26); revisit at Phase 10 |
| Throttling | `AnonRateThrottle` on login and registration (§45). **Deliberately scheduled after vehicles** (decided 2026-09-25) |
| Refresh-serializer error shape | `TokenRefreshView` uses simplejwt's default serializer, so a bad/expired refresh token returns `detail`, not the `{"refresh": [...]}` shape `LogoutView` uses. Cosmetic, decided 2026-09-25 |
| Bare `/api/` route | `config/urls.py` mounts `apps.accounts.urls` at `api/` directly. Deliberate; a namespaced prefix can wait until parking routes land |

Done since the last update: role change and suspend/activate via
`PATCH /api/users/{id}/` with the transactional last-Administrator guard (D24,
D27) — the increment that completes the accounts *user-management* story and
closes the last open item under "Phase 2 — authentication and users" apart from
`Vehicle`. Regression tests added in `apps/accounts/tests.py`
(`UserAccessUpdateTests`). `manage.py test apps.accounts` → 44 tests, all pass.

Previously done: phone as non-unique, digits-only contact info (D23, migration
`0002_alter_user_phone`); consumer profile self-update via `PATCH /api/auth/me/`
(D25); Administrator user management — list, retrieve and create
`MANAGER`/`ADMIN` accounts at `/api/users/` (D26). **Pending data check** after
the phone migration:
`SELECT id, phone FROM accounts_user WHERE phone IS NOT NULL AND phone !~ '^[0-9]+$';`
(existing rows are not retro-normalised).

> **Status of the working tree:** the role-change increment is present but not
> yet committed. Commit it as `feat(accounts): add role change and suspension`
> before starting `Vehicle`, so the next increment has a clean base.

---

## Open decisions

Deliberately deferred. Each needs a human decision before the code that depends
on it is written.

1. ~~**Phone normalisation**~~ → resolved (D23). Drop global uniqueness; phone
   becomes optional, digits-only contact info with no verification (the lock was
   caused by uniqueness, not by the absence of verification). Email-OTP
   verification is scheduled separately — see "Deferred features" below.
2. ~~**Role mutability**~~ → resolved (D24). Global Administrators; `role` is
   mutable by an Administrator; the last active Administrator cannot be demoted
   or suspended; regional administration and audit logging are deferred.
2b. ~~**Password-name similarity**~~ → resolved (B4/D22).
   `AUTH_PASSWORD_VALIDATORS` now passes `user_attributes=("email", "full_name")`;
   the validator subclass the review suggested was unnecessary.
3. ~~**Where role checks live**~~ → resolved: `apps/accounts/permissions.py`
   (`HasRole` base + `IsConsumer` / `IsManager` / `IsAdmin`), verified by
   `apps/accounts/tests.py` through DRF's real view machinery.
4. **`Booking.user` nullability** — D8, planned for Phase 4.
5. **`Vehicle` model + ownership rules** — the last Phase 2 feature (§16 lists
   "Consumer vehicle registration" under Authentication). The model shape,
   plate normalisation/uniqueness, whether a vehicle is required to book, and
   how the owner is scoped are all §9 decisions, so they are listed here rather
   than assumed. See "Phase 2 — next increment: `Vehicle`" below.

Resolved since the last update:

- ~~Role change / suspend-activate~~ → implemented (D24, D27). Administrator-only
  `PATCH /api/users/{id}/`, last-active-Administrator guard under a single
  ordered row lock.
- ~~Suspension scope~~ → D15. `JWTAuthentication` re-reads the user on every
  request, so `is_active=False` blocks all authenticated requests immediately;
  no revocation list needed.
- ~~Refresh-token blacklisting~~ → D17. Enabled, with rotation.
- ~~Email case-sensitivity on login (B3b)~~ → D21. Storage and lookup both
  canonicalise the identifier, then match exactly.

## Phase 2 — next increment: `Vehicle`

Decisions to settle **before** code is written (PROJECT.md §9). The agent
proposes; the human decides.

| # | Decision | Options | Recommendation |
|---|----------|---------|----------------|
| V1 | Vehicle fields | minimal (`registration_number`, `make`, `model`, `color`) vs. richer (year, type) | Minimal now; add columns when a screen needs them |
| V2 | Registration number canonicalisation | store as typed / upper-case + strip separators / validate format only | Upper-case and strip spaces/hyphens; store one representation (mirrors D13's email rule) |
| V3 | Uniqueness of `registration_number` | globally unique / unique per owner / not unique | Globally unique — a plate identifies one physical vehicle across the platform |
| V4 | Ownership relation | `Vehicle.owner` FK to `User` (non-null) | Non-null; only Consumers may own vehicles |
| V5 | Who may write | Consumer owns own vehicles; Manager/Admin read-only or none | Consumer CRUD scoped to `request.user`; staff read-only |
| V6 | Deletion vs. deactivation | hard delete / soft `is_active` | Decide with Phase 4: a vehicle referenced by a booking must not vanish. Likely soft-delete or `PROTECT` |
| V7 | Vehicle required to book | required / optional | Defer to Phase 4; do not force a field now that booking would inherit |
| V8 | Default/last used | `is_default` flag / implicit most-recent | Defer until a booking screen needs a preselected vehicle |

Endpoint shape (to confirm): `GET/POST /api/vehicles/`,
`GET/PATCH/DELETE /api/vehicles/{id}/`, scoped to the owner, no id in the body.
This follows the ownership-as-queryset pattern used by `MeView` (D25) so
Invariant 2 is structural rather than a permission check that can be forgotten.

## Deferred features

Scheduled, not dropped. Each is recorded here until it gets its own decision
entry.

- **Email-OTP verification (registration hardening).** Verify ownership of the
  email before an account becomes active, to reduce fake accounts and email
  squatting. Explicitly **not** a substitute for phone verification: it proves
  ownership of the email, not the phone. Scope: an OTP/token model, lazy expiry
  (D6 — no scheduler), an email-sending path (console backend locally), resend +
  throttling, and a multi-step registration contract (register → inactive →
  verify → activate), which changes the `/api/auth/register/` contract.
- **Regional administration.** An Administrator who supervises the lots and
  Managers of one region, with region-scoped rather than global authority.
  Considered and deliberately deferred until after the core project (D24): it
  needs a `Region` entity, a conditional `role=ADMIN ⇒ region` constraint,
  region-scoped authorization across accounts/parking/reports, and a
  region-aware demotion guard — and a Manager whose lots span several regions
  makes it more involved still. Revisit once the core system is complete.
- **Audit logging.** Recording who changed a user's role or suspended an account
  (`AuditLog`, PROJECT.md §15). Still deferred; the role-change endpoint now
  exists, so this is a matter of writing the audit records it should produce.

---

## Working conventions

- **Increment rule** (PROJECT.md §1/§38): size an increment by the *coherent
  feature boundary*, not by file count. One feature per session, delivered whole.
  The rule that binds is *don't implement future phases* — not *build less of the
  current feature*.
- **Agent role** (PROJECT.md §8 Rule 2): the agent supplies complete runnable
  code including business logic, plus the decisions it embeds; the human reads,
  approves each decision and owns the result. Everywhere PROJECT.md says "human
  writes X" (§36's phase lists, §21's "the human developer must design"), **§8 wins**:
  it means the human owns the *decision*, not that they author the code. The agent
  may therefore write backend logic, but it must name each consequential decision
  and its trade-offs rather than burying it in boilerplate (§9, §10). `TODO(HUMAN)`
  markers in code mean "a decision is pending here".
- **Frontend** (PROJECT.md §11): frontend implementation is delegated to the
  agent and may be written substantially or completely, but only against real
  backend APIs (never invented ones). No frontend feature starts before its
  backend contract is settled (§23).
- **Verification** is manual: `manage.py check`, `manage.py shell`, and `curl`
  against the dev server. `curl` may not be used if frontend is ready to showcase. Automated tests (§34) are Phase 10.
- **Git**: small, scoped commits following §43's `feat(domain): ...` style.

---

## Repository hygiene notes

- `requirements.txt` pins `redis==8.1.0` and `pillow==12.3.0`, neither of which
  is imported anywhere. D6 avoids Redis and §12 forbids introducing it without
  approval. Left in place pending a decision; they are currently misleading.
