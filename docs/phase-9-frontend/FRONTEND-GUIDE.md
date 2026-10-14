# Building the SPMS frontend — Phase 9 guide

Audience: the implementing agent (and the human reviewing it). This is the
**how**; [`API-MAP.md`](API-MAP.md) is the **what**. Read both together with:

1. [`../api-contract.md`](../api-contract.md) — cross-cutting rules (base URL,
   auth, pagination, errors). **Read this first.**
2. [`API-MAP.md`](API-MAP.md) — every route, every field.
3. PROJECT.md **§30** (the page list per role) and **§31** (design principle:
   practical over flashy — usability, navigation, correct integration, loading
   states, error handling, form validation, responsive layout, no gratuitous
   animation).

> Golden rules: **never invent an endpoint or a field**, never hardcode the
> backend origin, and never decide authorization on the client — the backend is
> authoritative (a `403`/`404` is the truth).

Last updated: **2026-10-14**.

---

## 1. What already exists

- `frontend/` is a **Vite + React 19 + TypeScript** scaffold (default template).
  `npm run dev` serves `http://localhost:5173`; `vite.config.ts` already proxies
  `/api/*` → `http://localhost:8000`, so call **relative** URLs.
- `npm run build` runs `tsc -b && vite build`; `npm run lint` runs `oxlint`.
- The backend is complete and tested through Phase 8 (see `API-MAP.md` §0 for
  what is live, and the two stubs: walk-in/cash and the optional dashboard
  bundle).

Start by replacing the template's `App.tsx` and assets with the app shell.

---

## 2. Add a small, boring stack (and record the choices)

PROJECT.md §31 asks for **practical**, not clever. Recommended additions:

| Need | Recommendation | Why |
|------|----------------|-----|
| Routing | `react-router-dom` | Role-scoped route trees; keep filters in the URL. |
| Data fetching | **TanStack Query** (`@tanstack/react-query`) *or* plain `fetch` hooks | Query gives caching, retries and loading/error states for free. If you prefer zero deps, a small `useApi` hook is fine. |
| Forms | Controlled inputs + a tiny validator, or `react-hook-form` | Must surface the API's **field errors** next to inputs. |
| Payments | Razorpay **Checkout** script (`checkout.js`) loaded for the payment page | Test mode only; the card form is provider-hosted. |
| Styling | Plain CSS modules / one `app.css`, or Tailwind | Keep it simple and responsive. |

**Do not add:** Redux (overkill), any "mock API" that invents routes, or a
WebSocket library heavier than the browser's native `WebSocket`.

Record these as Phase 9 decisions (`D<n>`) before coding, per the project's
decision protocol.

---

## 3. Suggested structure

```text
frontend/src/
├── main.tsx                 # router + QueryClientProvider + AuthProvider
├── api/
│   ├── client.ts            # the one fetch wrapper (see §4)
│   ├── errors.ts            # ApiError type + code → message map
│   └── types.ts             # TS types mirroring API-MAP.md
├── auth/
│   ├── AuthProvider.tsx     # tokens + user in context, login/logout/refresh
│   └── guards.tsx           # <RequireAuth>, <RequireRole role="ADMIN">
├── hooks/
│   ├── useApi.ts            # query/mutation helpers over client.ts
│   └── usePaginated.ts      # drives the { count, results } envelope
├── lib/format.ts            # formatMoney, formatDateTime (Intl, IST)
├── components/              # Button, Table, Pagination, Spinner, ErrorState…
├── pages/
│   ├── auth/                # Login, Register
│   ├── consumer/            # Search, LotDetails, SlotSelection, Booking, Payment, MyBookings…
│   ├── manager/             # Dashboard, MyLots, LotDetails, Slots, Bookings, Occupancy, Reports, Profile
│   └── admin/               # Dashboard, Users, Managers, Lots, BusinessRules, Bookings, Transactions, Reports
└── routes.tsx               # the role-based route table
```

---

## 4. The API client — the single most important file

Everything goes through **one** wrapper so auth, errors and the base URL are
handled in exactly one place.

```ts
// api/client.ts
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code?: string,          // the { "error": "CODE" } value, if any
    readonly fieldErrors?: Record<string, string[]>,
    message?: string,
  ) { super(message ?? code ?? `HTTP ${status}`); }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`/api${path}`, {   // relative — the Vite proxy handles the origin
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...authHeader(),                        // 'Authorization': `Bearer ${access}`
      ...(init.headers ?? {}),
    },
  })

  if (res.status === 401) {                   // try one silent refresh, then retry once
    const refreshed = await refreshOnce()     // see §5 — single-flight
    if (refreshed) return apiFetch<T>(path, init)
    logout()
    throw new ApiError(401)
  }

  if (!res.ok) throw await toApiError(res)
  return res.status === 204 ? (undefined as T) : res.json()
}
```

`toApiError` inspects the body: a `{ error, message }` refusal becomes
`ApiError(status, body.error, undefined, body.message)`; anything else is treated
as field errors. Never show a raw stack, SQL or message to the user.

**Never** call `fetch('http://localhost:8000/...')`. Always `apiFetch('/bookings/')`.

---

## 5. Auth, tokens and refresh (get this exactly right)

- Store `access`, `refresh` and `user` after `POST /auth/login/`. `localStorage`
  is fine for this project; note in a comment that it is XSS-sensitive.
- **Refresh rotates** (D17): `POST /auth/refresh/` returns a **new** `access`
  *and* a **new** `refresh`, and blacklists the old refresh. **Persist the new
  refresh**, or the next refresh fails and the user is logged out.
- **Single-flight the refresh.** Many parallel requests can each get a `401` at
  once; without a guard they fire N refreshes and the rotation invalidates each
  other. Keep one in-flight `Promise` and have every caller await it:

  ```ts
  let refreshing: Promise<boolean> | null = null
  function refreshOnce() {
    refreshing ??= doRefresh().finally(() => { refreshing = null })
    return refreshing
  }
  ```

- Access tokens live **30 minutes**; refresh 7 days. On a failed refresh, clear
  storage and route to `/login`.
- **Role is not in the token** (D15). Read it from the login `user` or
  `GET /auth/me/`, and re-check `me` on app load to pick up role changes.
- Route guards (`<RequireRole role="MANAGER">`) are **UX only**. The backend is
  authoritative; still handle a `403` from any call.

---

## 6. Data conventions — three helpers save you everywhere

```ts
// money: API sends strings. Never Number() for arithmetic.
export const formatMoney = (s: string) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(Number(s))

// dates: ISO-8601 UTC "Z". Render in IST for a parking context.
export const formatDateTime = (iso: string) =>
  new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short',
    timeZone: 'Asia/Kolkata' }).format(new Date(iso))
```

- **Pagination.** Collections return `{ count, next, previous, results }`. Read
  **`results`**. Drive `?page=N` from `count` and `page_size`; ignore the absolute
  `next`/`previous` URLs (they point at the backend origin). Keep the page and
  filters in the URL query string so a refresh/back keeps the view.
- **Bare arrays** (no envelope): `/cities/`, `/availability/`, `/occupancy/`, and
  every `/reports/*` object. Do not read `.results` there.
- Money fields are **strings** everywhere (`hourly_rate`, `base_amount`,
  `amount`, `refunded_amount`, `overstay_amount`, `gross`, …).

---

## 7. Error handling UX

- **Field errors** (`{ "start_time": ["…"] }`) → render under the offending input.
- **Coded refusals** (`{ "error": "BOOKING_CONFLICT", "message": "…" }`) → show
  the `message`, and optionally a friendlier line per code. Keep a small
  `code → text` map for the ones users hit: `BOOKING_CONFLICT`,
  `SLOT_UNAVAILABLE`, `MAX_DURATION_EXCEEDED`, `MIN_DURATION_NOT_MET`,
  `INVALID_WINDOW`, `RATE_ABOVE_MAXIMUM`, `MAX_DURATION_ABOVE_CAP`,
  `MAX_RATE_BELOW_TARIFF`, `LAST_ADMINISTRATOR`, `PAYMENT_GATEWAY_UNAVAILABLE`.
- **`404`, not `403`, for another user's object.** Render "Not found", not
  "Forbidden". This is deliberate (Invariant 2/3) — do not "fix" it in the UI.
- **`409` is a state conflict**, not a crash: for `BOOKING_CONFLICT` /
  `SLOT_UNAVAILABLE`, re-fetch availability and ask the user to pick again.
- Every data screen needs **loading**, **empty** and **error** states. PROJECT.md
  §31 lists loading states and error handling explicitly.

---

## 8. Feature notes and gotchas

**Bookings**
- Render **`effective_status`**, never raw `status`. A lapsed hold reads
  `EXPIRED` there while the stored `status` stays `PENDING_PAYMENT`.
- `GET /bookings/{id}/` is **Consumer-only**. The Manager/Admin "Bookings" page
  must use the **list row** (which carries `lot`, `consumer_email`,
  `can_check_in`, `can_check_out`); it cannot open a per-id detail.
- The list is **role-scoped** by the backend: a Consumer passing `?lot=` still
  only sees their own rows; a Manager sees only their assigned lots. Never build
  client-side scoping to "help".
- Check-in/check-out are **Manager** actions gated by `can_check_in` /
  `can_check_out` on the row; both are idempotent.

**Payments**
- Flow: `POST /payments/` → open Razorpay Checkout with `client_payload` → on
  the callback, `POST /payments/{id}/confirm/` with `{ payload }` → re-read the
  booking/payment. **Never** treat the browser callback as proof of success; the
  server verifies the signature.
- `receipt_available` tells you whether to show the receipt link
  (`GET /payments/{id}/receipt/`, **Consumer-only**).
- Extensions reuse `POST /payments/` with `purpose: "EXTENSION"` and the new
  `end_time`. Price it first with `GET /bookings/{id}/extension-quote/`.
- With `PAYMENT_GATEWAY=mock` the backend runs offline; the `client_payload`
  shape still comes back, so the Payment page should handle both.

**Occupancy board**
- HTTP read returns the whole board (no envelope). The WebSocket pushes the
  **same** object: `{ type: "occupancy", board: {...} }`.
- The WebSocket URL needs the access token as **`?token=<access>`**, and it
  connects to the **backend origin** (`ws://localhost:8000/ws/...`), which the
  current Vite proxy does **not** forward. Either connect directly to
  `ws://localhost:8000/...`, or add `ws: true` to the `/api` proxy (or a new
  `'/ws'` proxy entry) in `vite.config.ts`.
- Handle close codes **`4401`** (reconnect after re-login) and **`4403`** (no
  access to this lot). Reconnect with backoff; always keep the HTTP read as a
  fallback/poll.

**Reports**
- All report responses are **plain objects** (no `results`), scoped and
  windowed. The platform report is **Admin-only**; hide it from Managers and
  expect a `403` if called.
- `overstay_recorded` is **recorded, not collected** — show it in its own tile,
  never summed into revenue.
- Occupancy has **two** figures: the live `current.rate` and the windowed
  `window.booked_rate` (a booked-hours proxy). Label them so they are not read as
  the same number.

**Not available — stub, do not invent**
- Walk-in booking / manager cash payment (D63) → `// TODO: Backend endpoint required`.
- Notifications (Phase 7), Audit logs, public QR/gate lookup (deferred).
- `/api/reports/dashboard/` (D78, optional) → fan out to the metric endpoints.

---

## 9. Page → endpoint map (PROJECT.md §30)

| Role | Page | Endpoints |
|------|------|-----------|
| All | Login / Register | `POST /auth/login/`, `POST /auth/register/` |
| Consumer | Dashboard | `GET /bookings/?scope=upcoming`, `GET /auth/me/` |
| Consumer | Parking Search | `GET /parking-lots/?city=&search=`, `GET /cities/` |
| Consumer | Parking Lot Details | `GET /parking-lots/{id}/`, `GET /parking-lots/{lot}/tariffs/` |
| Consumer | Slot Selection / Booking | `GET /parking-lots/{lot}/availability/?start=&end=`, `POST /bookings/` |
| Consumer | Payment | `POST /payments/`, `POST /payments/{id}/confirm/`, `GET /bookings/{id}/` |
| Consumer | Booking Confirmation | `GET /bookings/{id}/`, `GET /payments/{id}/receipt/` |
| Consumer | My Bookings | `GET /bookings/?status=&scope=&ordering=` |
| Consumer | Booking Details | `GET /bookings/{id}/`, `POST /bookings/{id}/cancel/`, `GET /bookings/{id}/extension-quote/`, `POST /payments/` (extension) |
| Consumer | Vehicles | `GET/POST /vehicles/`, `PUT/PATCH/DELETE /vehicles/{id}/` |
| Consumer | Profile | `GET/PATCH /auth/me/` |
| Manager | Dashboard | `GET /reports/bookings/`, `GET /reports/occupancy/`, `GET /reports/revenue/` |
| Manager | My Parking Lots | `GET /parking-lots/` (Manager sees assigned) |
| Manager | Lot Details | `GET /parking-lots/{id}/`, `GET /parking-lots/{lot}/slots/` |
| Manager | Slot Management | `GET/POST /parking-lots/{lot}/slots/`, `PATCH /parking-lots/{lot}/slots/{id}/` |
| Manager | Pricing (Tariff) | `GET/POST /parking-lots/{lot}/tariffs/`, `PATCH …/{id}/`, `GET /business-rules/` |
| Manager | Bookings | `GET /bookings/`, `POST /bookings/{id}/check-in/`, `POST /bookings/{id}/check-out/` |
| Manager | Occupancy | `GET /parking-lots/{lot}/occupancy/` + WS, `POST …/slots/{id}/occupancy/` |
| Manager | Reports | `GET /reports/bookings/`, `/reports/revenue/`, `/reports/occupancy/` |
| Manager | Profile | `GET/PATCH /auth/me/` |
| Manager | Walk-in Booking | ❌ not available (D63) — stub |
| Admin | Dashboard | `GET /reports/platform/` |
| Admin | Users / Managers | `GET/POST /users/`, `GET/PATCH /users/{id}/` |
| Admin | Parking Lots | `GET/POST /parking-lots/`, `PATCH /parking-lots/{id}/` |
| Admin | Business Rules | `GET/PATCH /business-rules/` |
| Admin | Bookings | `GET /bookings/` (operator rows) |
| Admin | Transactions | `GET /payments/` (transaction rows), `POST /payments/{id}/refund/` |
| Admin | Reports | `GET /reports/platform/` (+ the three metric families) |
| Admin | Audit Logs | ❌ not available — stub |

---

## 10. Developer workflow

```bash
# Backend
cd backend && ../env/bin/python manage.py runserver      # :8000
# (for the live occupancy board only) start Redis, then run via ASGI/daphne

# Frontend
cd frontend && npm install && npm run dev                # :5173
```

Create test accounts:

```bash
cd backend
../env/bin/python manage.py createsuperuser     # an ADMIN (email + full_name + password)
# then, as that admin, create a MANAGER via POST /api/users/ (role=MANAGER),
# and register a CONSUMER via POST /api/auth/register/.
```

Quick token for manual checks:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"…"}' | python -c \
  "import sys,json;print(json.load(sys.stdin)['access'])")
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/bookings/
```

Build & lint before every checkpoint: `npm run build` and `npm run lint`.

---

## 11. Tips and tricks (the short version)

1. **Contract-first.** Build each screen against `API-MAP.md`; copy field names
   exactly. When a screen needs data with no route, write the `TODO` and stop.
2. **One client, one error mapper.** All requests through `apiFetch`; all errors
   through `ApiError`. No ad-hoc `fetch` in components.
3. **Type the API.** Put the row/request shapes from `API-MAP.md` in
   `api/types.ts` and reuse them; that is what makes `tsc -b` catch drift.
4. **Money is a string.** Format with `Intl`; never do arithmetic on it in the UI.
5. **Dates are UTC `Z`.** Parse then render; use `Asia/Kolkata` where the parking
   context implies IST.
6. **Render `effective_status`,** not `status`, for bookings.
7. **Pagination**: read `results`, keep `?page=`/filters in the URL, ignore
   `next`/`previous`.
8. **`404` means "not yours"**, by design — show "Not found", not "Forbidden".
9. **Handle `409`** by refreshing state, not by retrying blindly.
10. **Guard by role in the UI, but trust the backend.** Handle a `401` (re-login)
    and `403` (hide/redirect) from any call.
11. **Single-flight the token refresh**, and persist the rotated refresh token.
12. **WebSocket**: `?token=`, backend origin, handle `4401`/`4403`, reconnect with
    backoff, keep the HTTP read as fallback.
13. **Never assert a payment succeeded** — only the server confirms it.
14. **Loading / empty / error** on every list and form; disable submit while
    pending; show the API's field errors inline.
15. **Stub the missing features** (walk-in, notifications, audit logs, dashboard
    bundle) with an explicit `// TODO: Backend endpoint required` — do not invent
    routes or fake data.

---

## 12. Definition of done (per screen)

- [ ] Calls only routes in `API-MAP.md`; no invented endpoint or field.
- [ ] Renders loading, empty and error states; API field errors show next to the
      offending input.
- [ ] Money/date formatting via the shared helpers; no `Number()` on money.
- [ ] Role-guarded, and a backend `403`/`404` is handled gracefully.
- [ ] Filters/pagination reflected in the URL where the page lists data.
- [ ] `npm run build` and `npm run lint` pass.
- [ ] Cross-checked against the API map; any gap recorded as a `TODO`.
