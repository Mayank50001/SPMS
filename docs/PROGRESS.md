# Progress & Working State

Companion to [`DECISIONS.md`](DECISIONS.md) (agreed architecture decisions) and
[`PROJECT.md`](../PROJECT.md) (authoritative specification).

**Purpose:** one place to re-establish context at the start of a session — what
is built, what is next, and which decisions are still open. Update at the end of
every milestone.

Last updated: 2026-09-27 · Current phase: **2 — Authentication and users**

---

## Phase tracker

| Phase | Scope | Status |
|-------|-------|--------|
| 0 | Repository setup | ✅ Done |
| 1 | Backend foundation (config, PostgreSQL, health) | ✅ Done |
| 2 | **Authentication and users** | 🔵 In progress — auth complete, users incomplete |
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
| GET | `/api/health/` | public | needed the new `AllowAny` (D18) |

- Verified by hand: token pair issued; no role present in the token claims;
  `/me/` without a header → `401`; refresh rotation; replay of a consumed
  refresh token → `401`; logout revocation; and an immediate `401` on a
  still-unexpired access token once `is_active=False`.
- Known limitation (D17): logout revokes refresh tokens only. A live access token
  stays valid until it expires — inherent to stateless JWT, bounded by the
  30-minute lifetime.

---

## Phase 2 — correctness review (2026-09-25) — addressed 2026-09-27

Found by reading the code and reproducing each case in `manage.py shell`. All are
confined to `apps/accounts/`; none changes the architecture.

> **Status (2026-09-27):** B1, B2, B3 and B5 are resolved; B4 is consciously left
> open (now item 2b); B6 is resolved. Resolutions are recorded against each item.
> Regression tests added in `apps/accounts/tests.py`; `manage.py test
> apps.accounts` passes (9 tests).

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

### B4 — `validate_password(..., user=candidate)` cannot run the similarity check (voids D14's rationale) 🟡 — OPEN

`UserAttributeSimilarityValidator.DEFAULT_USER_ATTRIBUTES` is
`('username', 'first_name', 'last_name', 'email')`. This user model has no
`username` and no `first_name`; its name field is `full_name`, which is not in
that list. Verified:

| password equals | result |
|---|---|
| the email | rejected — "too similar to the email" |
| `full_name` | **accepted** |

So the unsaved-`User` construction only enables the *email* comparison, not the
name comparison D14 claims. Consciously accepted for now; tracked as open item 2b.

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
| Consumer profile | Update endpoint for `full_name` / `phone`; `/api/auth/me/` is read-only today |
| `Vehicle` model + CRUD | Consumer vehicle registration, scoped to the owner (§16, Invariant 2) |
| Manager/Admin account creation | Administrator-only endpoint (D20) |
| Throttling | `AnonRateThrottle` on login and registration (§45). **Deliberately scheduled after vehicles** (decided 2026-09-25) |
| Refresh-serializer error shape | `TokenRefreshView` uses simplejwt's default serializer, so a bad/expired refresh token returns `detail`, not the `{"refresh": [...]}` shape `LogoutView` uses. Cosmetic, decided 2026-09-25 |
| Bare `/api/` route | `config/urls.py` mounts `apps.accounts.urls` at `api/` directly. Deliberate; a namespaced prefix can wait until parking routes land |

Done since the last update: the correctness-review fixes B1/B2/B3/B5 (and B6
docstrings), the B3b case-insensitive login lookup (D21), and regression tests in
`apps/accounts/tests.py` (registration leaks nothing; email normalisation; login
accepts any casing). `manage.py test apps.accounts` → 9 tests, all pass.

---

## Open decisions

Deliberately deferred. Each needs a human decision before the code that depends
on it is written.

1. **Phone normalisation** — `models.py:78`. Store raw, normalise to E.164, or
   validate format only? §35 lists "duplicate phone". Note the side effect that
   makes this urgent: `phone` is globally unique and writable, so anyone may
   register with a number they do not own, permanently blocking the real owner and
   turning the endpoint into an account-existence oracle for that number. Do
   consumers need to verify a phone at all before booking?
2. **Role mutability** — `models.py:84`. Is `role` frozen at account creation, or
   mutable afterwards? D20 settles *who* may create privileged accounts
   (Administrators only); it does not settle whether an existing role can change.
2b. **Password-name similarity** — see B4. Accept that `full_name` is not checked,
   or add a `UserAttributeSimilarityValidator` subclass with
   `DEFAULT_USER_ATTRIBUTES = ("email", "full_name")`.
3. ~~**Where role checks live**~~ → resolved: `apps/accounts/permissions.py`
   (`HasRole` base + `IsConsumer` / `IsManager` / `IsAdmin`), verified by
   `apps/accounts/tests.py` through DRF's real view machinery.
4. **`Booking.user` nullability** — D8, planned for Phase 4.

Resolved since the last update:

- ~~Suspension scope~~ → D15. `JWTAuthentication` re-reads the user on every
  request, so `is_active=False` blocks all authenticated requests immediately;
  no revocation list needed.
- ~~Refresh-token blacklisting~~ → D17. Enabled, with rotation.
- ~~Email case-sensitivity on login (B3b)~~ → D21. Storage and lookup both
  canonicalise the identifier, then match exactly.

---

## Working conventions

- **Increment rule** (PROJECT.md §1/§38): size an increment by the *coherent
  feature boundary*, not by file count. One feature per session, delivered whole.
  The rule that binds is *don't implement future phases* — not *build less of the
  current feature*.
- **Agent role** (PROJECT.md §8 Rule 2): the agent supplies complete runnable
  code including business logic, plus the decisions it embeds; the human reads,
  approves each decision, types it in and owns it. The phase lists in §36 that
  read "human writes X" are superseded by §8 — they mean the human owns the
  decision, not that they author the code. `TODO(HUMAN)` markers in code mean
  "a decision is pending here".
- **Verification** is manual: `manage.py check`, `manage.py shell`, and `curl`
  against the dev server. Automated tests (§34) are Phase 10.
- **Git**: small, scoped commits following §43's `feat(domain): ...` style.

---

## Repository hygiene notes

- `requirements.txt` pins `redis==8.1.0` and `pillow==12.3.0`, neither of which
  is imported anywhere. D6 avoids Redis and §12 forbids introducing it without
  approval. Left in place pending a decision; they are currently misleading.
