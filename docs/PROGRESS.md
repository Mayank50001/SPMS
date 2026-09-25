# Progress & Working State

Companion to [`DECISIONS.md`](DECISIONS.md) (agreed architecture decisions) and
[`PROJECT.md`](../PROJECT.md) (authoritative specification).

**Purpose:** one place to re-establish context at the start of a session — what
is built, what is next, and which decisions are still open. Update at the end of
every milestone.

Last updated: 2026-09-25 · Current phase: **2 — Authentication and users**

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

## Phase 2 — remaining

| Item | Notes |
|------|-------|
| `permissions.py` | Role permission classes (`IsConsumer`, `IsManager`, `IsAdmin`) reading `request.user.role`. Closes `TODO(HUMAN)` at `models.py:84` |
| Consumer profile | Update endpoint for `full_name` / `phone`; `/api/auth/me/` is read-only today |
| `Vehicle` model + CRUD | Consumer vehicle registration, scoped to the owner (§16, Invariant 2) |
| Manager/Admin account creation | Administrator-only endpoint (D20) |
| Throttling | `AnonRateThrottle` on login and registration (§45). **Deliberately scheduled after vehicles** (decided 2026-09-25) |

---

## Open decisions

Deliberately deferred. Each needs a human decision before the code that depends
on it is written.

1. **Phone normalisation** — `models.py:78`. Store raw, normalise to E.164, or
   validate format only? §35 lists "duplicate phone".
2. **Role mutability** — `models.py:84`. Is `role` frozen at account creation, or
   mutable afterwards? D20 settles *who* may create privileged accounts
   (Administrators only); it does not settle whether an existing role can change.
3. **Where role checks live** — `models.py:84`. DRF permission class, model
   method, view mixin, or a combination? A `permissions.py` module is the natural
   home.
4. **`Booking.user` nullability** — D8, planned for Phase 4.

Resolved since the last update:

- ~~Suspension scope~~ → D15. `JWTAuthentication` re-reads the user on every
  request, so `is_active=False` blocks all authenticated requests immediately;
  no revocation list needed.
- ~~Refresh-token blacklisting~~ → D17. Enabled, with rotation.

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
