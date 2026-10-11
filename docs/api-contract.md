# API contract — frozen for frontend integration

This is the **cross-cutting contract** the frontend is built against. It is the
frontend counterpart of PROJECT.md §23 ("define the contract, then integrate").
The **endpoint list** stays in the root [`../README.md`](../README.md#api); do
not duplicate it here. Read this file before writing any frontend code, and read
the root README's API section for the routes themselves.

> Rule (PROJECT.md §11/§23): the frontend talks only to the Django REST API,
> never to PostgreSQL, and must **never invent an endpoint**. If a screen needs
> data that has no route, emit `// TODO: Backend endpoint required` and stop.

Last updated: **2026-10-11** (pagination frozen — D66).

---

## 1. Base URL and development proxy

- Backend dev server: `http://localhost:8000`.
- Frontend dev server: `http://localhost:5173`.
- Vite proxies `/api/*` to the backend (`frontend/vite.config.ts`), so the
  browser calls **same-origin** `/api/...`. Use relative URLs — never hardcode
  `http://localhost:8000` in components.
- CORS allows the dev origin (`CORS_ALLOWED_ORIGINS`); no cookies are used.

## 2. Authentication

- Scheme: **JWT Bearer** (`djangorestframework-simplejwt`, D1). Send
  `Authorization: Bearer <access>` on every protected request.
- `POST /api/auth/login/` returns `{ "access", "refresh", "user" }`. `user` is
  `{ id, email, full_name, phone, role, created_at }`.
- Access lifetime is 30 minutes; refresh lifetime is 7 days.
- `POST /api/auth/refresh/` **rotates** the refresh token and blacklists the one
  presented (D17): persist the *new* `refresh` from its response, or the next
  refresh will fail. Handle a `401` on refresh by logging out.
- **Role is never a JWT claim** (D15). Read it from the login body or
  `GET /api/auth/me/`. The backend re-checks authority on every request.
- The frontend must **never** decide authorization. A route guard hides UI, but
  the backend is authoritative; treat a `403`/`401` as the source of truth.

### Roles

`role` is one of `CONSUMER`, `MANAGER`, `ADMIN`. Self-registration can only
produce `CONSUMER`; privileged accounts are created by an Administrator.

## 3. Content type, media type, trailing slashes

- All requests and responses are `application/json`.
- Every route **ends in a trailing slash** (`/api/bookings/`). A missing slash
  may redirect or 404 — always include it.
- `Decimal` money fields (`base_amount`, `hourly_rate`, `amount`, …) are
  serialised as **strings** (`"40.00"`). Type them as `string` in TypeScript and
  format for display; do not `Number()` them for arithmetic.
- Timestamps are **ISO-8601 UTC with `Z`** (`"2026-10-06T10:05:00Z"`). Parse with
  `new Date(...)`; render in the user's local or IST timezone as required.
- Unknown request fields are rejected by DRF; send only documented fields.

## 4. Pagination (D66)

**Collection-list** endpoints return the DRF envelope:

```json
{
  "count": 42,
  "next": "http://localhost:8000/api/bookings/?page=3",
  "previous": "http://localhost:8000/api/bookings/?page=1",
  "results": [ { "id": 1, "...": "..." } ]
}
```

- Default page size **20**; override with `?page_size=` (max **100**).
- Read rows from **`results`**, never the top level. Use `count` for "x of y".
- Drive paging with `?page=N` yourself (from `count` ÷ page size) — do not rely
  on `next`/`previous` URLs, which are absolute and point at the backend origin.
- An out-of-range `?page=` is a **`404`** (DRF default).
- **Paginated:** `/api/users/`, `/api/vehicles/`, `/api/parking-lots/`,
  `/api/parking-lots/{lot}/slots/`, `/api/parking-lots/{lot}/tariffs/`,
  `/api/bookings/`, `/api/payments/`.
- **Opted out** (bare JSON array, not an envelope):
  `/api/cities/` and `/api/parking-lots/{lot}/availability/`.
  For the availability grid, the whole set is returned so every slot can be
  rendered at once.

## 5. Error shape

Two shapes — both stable, do not conflate them:

- **Coded business refusals** (the `{"error", "message"}` envelope, PROJECT.md
  §33), used for conflict-shaped outcomes:

  ```json
  { "error": "BOOKING_CONFLICT", "message": "The selected slot is no longer available." }
  ```

  The exact codes per route are listed in the root README's API section. Status
  codes are meaningful: `400` bad input, `401` unauthenticated, `403` wrong role,
  `404` not found (also used for **another account's object**, by design —
  Invariant 2), `409` conflict/business refusal, `503` gateway unavailable.

- **DRF field-validation errors** for malformed request bodies, keyed by field:

  ```json
  { "start_time": ["Datetime has wrong format."], "slot": ["This field is required."] }
  ```

  Render these next to the offending form field.

Never surface stack traces, SQL, or secrets to the user; the API never returns
them.

## 6. Page inventory vs. what the API supports today

The authoritative page list is PROJECT.md §30. As of this freeze:

- **Fully buildable now:** the entire consumer journey; admin Users / Managers /
  Parking Lots / Business Rules / Transactions; manager My Lots / Lot Details /
  Slot Management / Tariff (pricing) management / Profile. (`GET /api/payments/`
  is role-scoped, so the transactions view serves consumer, manager and admin
  with the same route and different row shapes — see README.)
- **Not yet available — stub the page, do not invent the route:**
  - Manager/Admin **bookings-for-a-lot list** (there is currently no operator
    booking-list route; `GET /api/bookings/` is consumer-owner-scoped only).
  - Manager **Occupancy** and walk-in/cash flows (Phase 6; walk-in deferred D63).
  - **Notifications** (Phase 7; model exists, no API surface yet).
  - **Reports / dashboards / audit logs** (Phase 8; audit deferred).

## 7. Payments (Razorpay test mode)

- `POST /api/payments/` with `{ "booking": <id> }` returns the payment row plus
  a `client_payload`; the browser opens Razorpay Checkout with that payload.
  Card data never touches this application (the form is provider-hosted).
- After Checkout returns, the client posts the provider payload to
  `POST /api/payments/{id}/confirm/`; only the server's signature verify (or the
  signed webhook) can confirm a booking. **The client must never assert that a
  payment succeeded.**
- Extensions reuse the same route:
  `{ "booking": <id>, "purpose": "EXTENSION", "end_time": "<new end>" }`.
- Receipt: `GET /api/payments/{id}/receipt/` (consumer, own payment only).
