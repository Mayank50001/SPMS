# Progress — Phase 2 (Authentication and users) ✅

> Phase 2 is **complete**. Its decisions are in
> [`DECISIONS.md`](DECISIONS.md) (D11–D28); cross-cutting decisions are in
> [`../foundation/DECISIONS.md`](../foundation/DECISIONS.md).

Last updated: 2026-10-01 · All work committed (`0e5a1c8` and earlier)

---

## Summary

Phase 2 built the custom email-based user model, consumer self-registration, the
full JWT authentication surface, consumer profile self-update, Administrator
user management (list / create / role change / suspend), role-based
authorization, and consumer **vehicle registration**.

`manage.py test apps.accounts` → **62 tests, all pass.**

---

## Custom user model (D11)

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

## Consumer self-registration

- `POST /api/auth/register/` → `201` with `id`, `email`, `full_name`, `phone`.
- Password hashed via `UserManager.create_user` (D12), validated by the
  `AUTH_PASSWORD_VALIDATORS` stack invoked at object level (D14).
- Email canonicalised to lower case; duplicates detected case-insensitively
  (D13).
- `role` is not a serializer field, so a client cannot propose one.
- Verified: hashing, weak-password rejection, similarity rejection, case-variant
  duplicate rejection, role-injection ignored.

## JWT authentication surface (D15–D19)

- `SIMPLE_JWT` configured in `config/settings.py`; `token_blacklist` app
  installed and its migrations applied.
- `DEFAULT_AUTHENTICATION_CLASSES = [JWTAuthentication]` — JWT only, no session
  auth. `DEFAULT_PERMISSION_CLASSES = [IsAuthenticated]` — deny by default.
- `config/views.py` — `health` gained an explicit `AllowAny`.

| Method | Endpoint | Auth | Notes |
|---|---|---|---|
| POST | `/api/auth/register/` | public | `AllowAny` opt-out |
| POST | `/api/auth/login/` | public | returns `access`, `refresh`, `user` |
| POST | `/api/auth/refresh/` | public | rotates the refresh token |
| POST | `/api/auth/logout/` | Bearer | blacklists the refresh token |
| GET | `/api/auth/me/` | Bearer | own profile, no id in the URL |
| PATCH | `/api/auth/me/` | Bearer | update own `full_name` / `phone` (D25) |
| GET | `/api/health/` | public | needed the explicit `AllowAny` (D18) |

- Verified by hand: token pair issued; no role present in the token claims;
  `/me/` without a header → `401`; refresh rotation; replay of a consumed
  refresh token → `401`; logout revocation; and an immediate `401` on a
  still-unexpired access token once `is_active=False`.
- Known limitation (D17): logout revokes refresh tokens only. A live access token
  stays valid until it expires — inherent to stateless JWT, bounded by the
  30-minute lifetime.

## Account and user management surface (D23, D25, D26)

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

## Role change and suspension (D24, D27)

- `PATCH /api/users/{id}/` is Administrator-only. It accepts `role` and/or
  `is_active`; both optional, at least one required, `PUT` disabled.
- The write is delegated to `apps/accounts/services.py::update_user_access`, not
  performed in the serializer or view, so the last-active-Administrator guard
  (D24) cannot be bypassed by a second caller.
- The guard locks every row the decision depends on — the currently active
  Administrators plus the target — in one ordered `select_for_update()`,
  inside `transaction.atomic()`. This closes the concurrent mutual-demotion
  race (the same check-then-act class as D3).
- A refused change returns `409 {"error": "LAST_ADMINISTRATOR", ...}`
  (PROJECT.md §33 error shape).
- Verified by `apps/accounts/tests.py::UserAccessUpdateTests`.

## Consumer vehicles (D28)

The last Phase 2 feature. A `Vehicle` is the *identity* of a consumer's car; it
holds no occupancy state — occupancy is `slot + active booking` (D2).

- `apps/accounts/models.py` — `Vehicle` with a non-null `owner` FK, a globally
  unique canonical `registration_number`, optional `make` / `model` / `color`.
  `INDIAN_STATE_CODES` back the state-code validation; read-only properties
  derive the four plate segments.
- `apps/accounts/migrations/0003_vehicle.py` — applied.

| Method | Endpoint | Auth | Notes |
|---|---|---|---|
| GET | `/api/vehicles/` | Consumer | list the caller's own vehicles |
| POST | `/api/vehicles/` | Consumer | register a vehicle (segments + metadata) |
| GET | `/api/vehicles/{id}/` | Consumer | retrieve one own vehicle |
| PUT/PATCH | `/api/vehicles/{id}/` | Consumer | edit (segments all-or-nothing) |
| DELETE | `/api/vehicles/{id}/` | Consumer | remove an own vehicle |

- Ownership is structural: the queryset is `filter(owner=request.user)` and the
  owner is set from `request.user`, never the request body. Another account's
  vehicle returns `404`, not `403` (Invariant 2).
- Verified by `apps/accounts/tests.py::{VehicleModelTests, VehicleApiTests}`.

---

## Correctness review (2026-09-25) — addressed 2026-09-27

Found by reading the code and reproducing each case in `manage.py shell`. All
confined to `apps/accounts/`; none changes the architecture. B1–B6 are resolved.

### B1 — `role` was writable (broke D11/D20) 🔴 — RESOLVED

`RegisterSerializer.Meta.fields` listed `role`, so `POST /api/auth/register/`
with `{"role": "ADMIN"}` created an Administrator. Fix: `"role"` removed from
`Meta.fields`; the model default supplies `CONSUMER`.

### B2 — `password` was not `write_only`, so the hash was returned 🟠 — RESOLVED

Fix: `password` declared explicitly with `write_only=True` (and `max_length=128`).

### B3 — `User.save()` never persisted the lower-cased email (broke D13) 🔴 — RESOLVED

`self.email.strip().lower()` discarded its result. Also corrected the original
false claim that login still passed: `get_by_natural_key` does an exact lookup,
so mixed-case registration broke login. Fix: `self.email = self.email.strip().lower()`.

### B3b — login lookup was case-sensitive — RESOLVED (with B3)

The lookup half is handled in `UserManager.get_by_natural_key`, which
canonicalises the incoming identifier before an exact match (D21).

### B4 — password/name similarity could not run (voided D14's rationale) 🟡 — RESOLVED

`UserAttributeSimilarityValidator` compares against attributes the model does
not have (`username`, `first_name`, ...). Fix (D22): pass
`OPTIONS: {"user_attributes": ("email", "full_name")}`. Settings-only change.

### B5 — `User = get_user_model()` at import time 🟡 — DOCUMENTED (accepted)

Constraint documented in the `serializers.py` docstring: the module must not be
imported from `models.py`, `apps.py` or any other app-loading code.

### B6 — stale docstrings 🟢 — RESOLVED

Docstrings updated across `models.py`, `serializers.py`, `config/urls.py`,
`config/settings.py`.

---

## Deferred hardening (recorded for Phase 10 unless noted)

| Item | Notes |
|------|-------|
| Forced password change | Privileged accounts keep the Administrator-set initial password (D26); needs a `must_change_password` flag + change-password endpoint |
| List pagination | `/api/users/` and `/api/vehicles/` return unpaginated lists (D26, D28) |
| Throttling | `AnonRateThrottle` on login and registration (§45) |
| Refresh-serializer error shape | `TokenRefreshView` returns simplejwt's default `detail`, not the `{"refresh": [...]}` shape `LogoutView` uses. Cosmetic |
| Bare `/api/` route | `config/urls.py` mounts `apps.accounts.urls` at `api/` directly. Deliberate until parking routes land |
| Vehicle delete semantics (V6) | Hard delete today; revisit with `PROTECT`/soft-delete once bookings reference vehicles (Phase 4) |

### Pending data check

After the phone migration, existing rows are not retro-normalised:

```sql
SELECT id, phone FROM accounts_user WHERE phone IS NOT NULL AND phone !~ '^[0-9]+$';
```

---

## Carried into later phases

- **`Booking.user` nullability** — D8, Phase 4.
- **`Vehicle` delete semantics (V6)**, **walk-in free-text plates (V7)**,
  **default vehicle (V8)**, **shared/family ownership** — Phase 4/6/9 per D28.
- **Repository hygiene** (`redis`/`pillow` pinned but unused) —
  [`../deferred-features.md`](../deferred-features.md).

## Resolved open decisions (for the record)

- ~~Phone normalisation~~ → D23 · ~~Role mutability~~ → D24 ·
  ~~Password-name similarity~~ → B4/D22 · ~~Where role checks live~~ →
  `apps/accounts/permissions.py` · ~~`Vehicle` model + ownership~~ → D28 ·
  ~~Suspension scope~~ → D15 · ~~Refresh blacklisting~~ → D17 ·
  ~~Email case-sensitivity on login~~ → D21.
