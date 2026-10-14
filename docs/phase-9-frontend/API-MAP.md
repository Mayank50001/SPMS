# SPMS API map — the frontend build reference

Every route the React frontend may call, with the exact request and response
fields, taken from the backend serializers as they exist today. This is the
**agent-facing companion** to [`../api-contract.md`](../api-contract.md) (the
cross-cutting rules) and the root [`../../README.md`](../../README.md) API section.

> **Rule (PROJECT.md §11/§23).** The frontend talks only to this API and must
> **never invent an endpoint**. If a screen needs data with no route here, emit
> `// TODO: Backend endpoint required` and stop — do not guess a URL or a field.

Last updated: **2026-10-14** (Phase 8 reports).

---

## 0. What is callable today

| Area | Status |
|------|--------|
| Health, auth, users, vehicles, cities, lots, slots, tariffs, business rules | ✅ Live |
| Bookings (create / list / detail / cancel / extension-quote / check-in / check-out) | ✅ Live |
| Payments (create / confirm / webhook / refund / receipt / list) | ✅ Live |
| Availability + occupancy board (HTTP + WebSocket) | ✅ Live |
| Reports: `/api/reports/bookings/`, `/revenue/`, `/occupancy/` | ✅ Live (8.1–8.4) |
| Reports: `/api/reports/platform/` | ✅ Contract below (8.5). If it 404s, 8.5 is not yet wired — stub the Admin Reports page meanwhile. |
| Reports: `/api/reports/dashboard/` | ❌ **Not built** (D78, optional). Call the metric families directly. |
| Walk-in booking + manager cash payment | ❌ Deferred (D63). Stub. |
| Notifications | ❌ Phase 7, deferred. No API. |
| Audit logs | ❌ Deferred. No API. |
| Public QR / gate lookup by `reference` | ❌ Deferred. Stub. |

---

## 1. Global conventions (memorise these)

- **Base URL.** Call **relative** `/api/...`. The Vite dev proxy
  (`frontend/vite.config.ts`) forwards `/api/*` to `http://localhost:8000`. Never
  hardcode the backend origin in a component.
- **Content type.** `application/json` for every request and response.
- **Trailing slash.** Every route ends in `/`. A missing slash may redirect or
  404 — always include it.
- **Auth.** `Authorization: Bearer <access>` on protected routes. Anonymous →
  `401`; authenticated with the wrong role → `403`; an object outside the caller's
  authority → **`404`, never `403`** (Invariant 2/3). Do not render a "forbidden"
  screen where the API deliberately says "not found".
- **Money** is a `Decimal` serialised as a **string** (`"40.00"`). Type it as
  `string`; format for display, never `Number()` it for arithmetic.
- **Timestamps** are ISO-8601 UTC with `Z` (`"2026-10-07T10:00:00Z"`). Parse with
  `new Date(...)`, render in IST (`Asia/Kolkata`) or local as the screen requires.
- **Pagination envelope (D66)** on collection lists:
  `{ count, next, previous, results: [...] }`. Read `results`; drive paging with
  `?page=N` from `count`; do not follow the absolute `next`/`previous` URLs.
  Default page size **20**, `?page_size=` up to **100**. Out-of-range `?page=` is
  a `404`.
  **Opted out (bare array, not an envelope):** `/api/cities/`,
  `/api/parking-lots/{lot}/availability/`, `/api/parking-lots/{lot}/occupancy/`
  and every `/api/reports/*` response (a computed object, not a collection).
- **Errors — two shapes:**
  - **Coded business refusal** (§33): `{ "error": "CODE", "message": "..." }`.
  - **Field validation**: `{ "field": ["...", "..."], ... }`.
  Status codes: `400` bad input · `401` unauthenticated · `403` wrong role ·
  `404` not found (also another account's object) · `409` conflict/refusal ·
  `502` gateway refund error · `503` gateway unavailable.

### Role scoping (server-side, always)

| Role | Sees |
|------|------|
| `CONSUMER` | Only their own bookings, payments and vehicles |
| `MANAGER` | Bookings/payments in **lots assigned to them** (`lot.manager`); can operate those lots |
| `ADMIN` | Everything |

A caller who owns no rows gets an **empty list**, never a `403`.

---

## 2. Vocabulary (the only source for dropdowns)

```
role:            CONSUMER | MANAGER | ADMIN
booking status:  PENDING_PAYMENT | CONFIRMED | IN_PROGRESS | COMPLETED |
                 CANCELLED | EXPIRED | TERMINATED
slot status:     AVAILABLE | OCCUPIED | OUT_OF_SERVICE      (stored physical state only)
slot type:       REGULAR | COMPACT | LARGE | TWO_WHEELER | EV
payment method:  ONLINE | CASH
payment purpose: BOOKING | EXTENSION
payment status:  PENDING | SUCCEEDED | FAILED
refund status:   PENDING | SUCCEEDED | FAILED
```

`REGULAR / COMPACT / LARGE / TWO_WHEELER / EV` also have display labels returned
as `slot_type_label` on a tariff (`Regular`, `Electric vehicle`, …).

---

## 3. Endpoint summary

| Method | Path | Role | Paginated |
|--------|------|------|-----------|
| GET | `/api/health/` | Public | — |
| POST | `/api/auth/register/` | Public | — |
| POST | `/api/auth/login/` | Public | — |
| POST | `/api/auth/refresh/` | Public | — |
| POST | `/api/auth/logout/` | Bearer | — |
| GET / PATCH | `/api/auth/me/` | Bearer | — |
| GET / POST | `/api/users/` | Admin | yes |
| GET / PATCH | `/api/users/{id}/` | Admin | — |
| GET / POST | `/api/vehicles/` | Consumer | yes |
| GET / PUT / PATCH / DELETE | `/api/vehicles/{id}/` | Consumer | — |
| GET / POST | `/api/cities/` | Public / Admin | **no** |
| GET / POST | `/api/parking-lots/` | Public / Admin | yes |
| GET / PATCH | `/api/parking-lots/{id}/` | Public / Admin | — |
| GET / POST | `/api/parking-lots/{lot}/slots/` | Public / Admin+Manager | yes |
| GET / PATCH | `/api/parking-lots/{lot}/slots/{id}/` | Public / Admin+Manager | — |
| POST | `/api/parking-lots/{lot}/slots/{id}/occupancy/` | Manager | — |
| GET / POST | `/api/parking-lots/{lot}/tariffs/` | Public / Admin+Manager | yes |
| GET / PATCH | `/api/parking-lots/{lot}/tariffs/{id}/` | Public / Admin+Manager | — |
| GET | `/api/parking-lots/{lot}/availability/` | Public | **no** |
| GET | `/api/parking-lots/{lot}/occupancy/` | Manager+Admin | **no** |
| WS | `/ws/parking-lots/{lot}/occupancy/?token=` | Manager+Admin | — |
| GET / POST | `/api/bookings/` | Role-scoped / Consumer | yes |
| GET | `/api/bookings/{id}/` | Consumer | — |
| POST | `/api/bookings/{id}/cancel/` | Consumer | — |
| GET | `/api/bookings/{id}/extension-quote/` | Consumer | — |
| POST | `/api/bookings/{id}/check-in/` | Manager | — |
| POST | `/api/bookings/{id}/check-out/` | Manager | — |
| GET / POST | `/api/payments/` | Role-scoped / Consumer | yes |
| POST | `/api/payments/{id}/confirm/` | Consumer | — |
| POST | `/api/payments/webhook/` | Public | — |
| POST | `/api/payments/{id}/refund/` | Admin+Manager | — |
| GET | `/api/payments/{id}/receipt/` | Consumer | — |
| GET | `/api/reports/bookings/` | Manager+Admin | **no** |
| GET | `/api/reports/revenue/` | Manager+Admin | **no** |
| GET | `/api/reports/occupancy/` | Manager+Admin | **no** |
| GET | `/api/reports/platform/` | Admin | **no** |
| GET | `/api/business-rules/` | Public / Admin | — |
| GET | `/api/business-rules/` PATCH | Admin | — |

---

## 4. Health & auth

### `GET /api/health/` — Public
`200 { "status": "ok" }`.

### `POST /api/auth/register/` — Public
Body: `{ "email", "full_name", "phone"?, "password", "password_confirm" }`.
`201 { id, email, full_name, phone }`. `role` is **never** accepted; always
`CONSUMER`. Duplicate email → field error; weak password → `{ "password": [...] }`.

### `POST /api/auth/login/` — Public
Body: `{ "email", "password" }`.
`200 { access, refresh, user }` where `user` is
`{ id, email, full_name, phone, role, created_at }`.
Bad credentials or a suspended account → `401` (deliberately vague).

### `POST /api/auth/refresh/` — Public
Body: `{ "refresh" }` → `200 { access, refresh }`.
**Rotation is on** (D17): the response carries a **new** `refresh` and the one
presented is blacklisted. **Persist the new refresh**, or the next refresh fails.
A failed refresh → `401` → log the user out.

### `POST /api/auth/logout/` — Bearer
Body: `{ "refresh" }` → `204`. Invalid/revoked → `400`.

### `GET /api/auth/me/` — Bearer → `200` `user` (the login `user` shape).
### `PATCH /api/auth/me/` — Bearer
Body: `{ "full_name"?, "phone"? }` → `200` `user`.

---

## 5. Users (Admin) and vehicles (Consumer)

### `GET /api/users/` — Admin, paginated
Query: `?role=`, `?is_active=true|false`, `?search=` (email or name), `?page=`,
`?page_size=`. Rows: `user` shape.

### `POST /api/users/` — Admin
Body: `{ "email", "full_name", "phone"?, "role": "MANAGER"|"ADMIN", "password" }`
→ `201` `user` shape.

### `GET /api/users/{id}/` — Admin → `200` `user`.
### `PATCH /api/users/{id}/` — Admin
Body: `{ "role"?, "is_active"? }` (at least one) → `200` `user`.
Refusal: `409 { "error": "LAST_ADMINISTRATOR", ... }` — cannot demote/suspend the
last Administrator.

### `GET /api/vehicles/` — Consumer, paginated
Rows: `{ id, registration_number, state_code, rto_code, series, unique_number,
make, model, color, created_at, updated_at }`.

### `POST /api/vehicles/` — Consumer
Body (four segments + optional description):
`{ "state_code": "KA", "rto_code": "01", "series": "AB", "unique_number": "1234",
"make"?, "model"?, "color"? }` → `201` the read row (canonical plate + segments).
The client never sends `registration_number`.

### `GET / PUT / PATCH / DELETE /api/vehicles/{id}/` — Consumer
A foreign or unknown id is `404`. Segments are all-or-nothing on update.

---

## 6. Parking catalogue

### `GET /api/cities/` — Public, **bare array**
`[ { id, code, name, created_at } ]`. Use for the city `<select>`.

### `POST /api/cities/` — Admin
Body: `{ "code": "BLR", "name": "Bengaluru" }` → `201` city. Code is 2–4 letters,
canonicalised to upper case.

### `GET /api/parking-lots/` — Public, paginated
Query: `?city=<CODE>`, `?search=` (name/address), `?page=`, `?page_size=`.
A logged-in Manager sees their assigned lots (incl. deactivated); everyone else
sees active lots only.
Row:
```
{ id, code, name, address_line,
  city: { id, code, name, created_at },
  number, state, postal_code, is_active, manager, created_at, updated_at }
```
`manager` is a user id or `null`.

### `POST /api/parking-lots/` — Admin
Body: `{ "city_code", "number", "name", "address_line", "state"?, "postal_code"?,
"is_active"?, "manager"? }` → `201` the read row. `manager` must be a `MANAGER` id.

### `GET /api/parking-lots/{id}/` — Public → `200` the read row.
### `PATCH /api/parking-lots/{id}/` — Admin → body as POST (partial) → `200`.

### `GET /api/parking-lots/{lot}/slots/` — Public, paginated
Row:
```
{ id, lot, lot_code, number, floor, slot_type, status,
  min_booking_hours, max_booking_hours, created_at, updated_at }
```

### `POST /api/parking-lots/{lot}/slots/` — Admin or the lot's Manager
Body: `{ "number", "floor"?, "slot_type"?, "status"?: "AVAILABLE"|"OUT_OF_SERVICE",
"min_booking_hours"?, "max_booking_hours"? }` → `201` the read row.
Notes: `status` here accepts only `AVAILABLE`/`OUT_OF_SERVICE` (`OCCUPIED` is
Phase 6). `slot_type` must already have a tariff in the lot, else `400`.
Refusal: `409 { "error": "MAX_DURATION_ABOVE_CAP", "max_booking_hours": [...] }`.

### `GET /api/parking-lots/{lot}/slots/{id}/` — Public → `200` the read row.
### `PATCH /api/parking-lots/{lot}/slots/{id}/` — Admin or the lot's Manager.
Withdraw a bay with `{"status": "OUT_OF_SERVICE"}`; restore with `"AVAILABLE"`.

### `POST /api/parking-lots/{lot}/slots/{id}/occupancy/` — Manager
Body: `{ "status": "OCCUPIED" | "AVAILABLE" }` → `200` the slot read row.
Refusals: `409 SLOT_NOT_OCCUPIABLE`; `400` if `OUT_OF_SERVICE` (use the slot
`PATCH` for that axis). Unassigned lot → `404`.

### `GET /api/parking-lots/{lot}/tariffs/` — Public, paginated
Row:
```
{ id, lot, lot_code, slot_type, slot_type_label, hourly_rate,
  created_at, updated_at }
```
`hourly_rate` is a money **string**.

### `POST /api/parking-lots/{lot}/tariffs/` — Admin or the lot's Manager
Body: `{ "slot_type": "EV", "hourly_rate": "30.00" }` → `201` the read row.
Refusal: `409 { "error": "RATE_ABOVE_MAXIMUM", "hourly_rate": [...] }`.

### `GET /api/parking-lots/{lot}/tariffs/{id}/` — Public → `200` the read row.
### `PATCH /api/parking-lots/{lot}/tariffs/{id}/` — Admin or the lot's Manager.

### `GET /api/business-rules/` — Public
```
{ id, max_hourly_rate, max_booking_hours, hold_minutes,
  cancellation_cutoff_minutes, overstay_multiplier, overstay_grace_minutes,
  updated_at }
```
### `PATCH /api/business-rules/` — Admin, any subset of the same fields.
Refusals: `409 MAX_RATE_BELOW_TARIFF`, `409 MAX_DURATION_BELOW_SLOT`.

### `GET /api/parking-lots/{lot}/availability/?start=<iso>&end=<iso>` — Public, **bare array**
Both params **required**, offset-aware ISO-8601. Returns the **bookable subset**
of the lot's slots, each in the slot read shape (above). `400 INVALID_WINDOW` for
a backwards/empty window. Does not exclude `OCCUPIED` (that only blocks a window
that has already begun).

---

## 7. Bookings

### `GET /api/bookings/` — any authenticated role, paginated, **role-scoped**
Query: `?status=` (csv of stored states), `?scope=upcoming|ongoing|past`,
`?lot=`, `?ordering=` (`start_time`/`-start_time`/`end_time`/`-end_time`/
`created_at`/`-created_at`), `?page=`, `?page_size=`.
The row shape depends on the role:

- **Consumer** row — the read shape:
```
{ id, reference, status, effective_status, slot, slot_number, lot_code, lot_name,
  slot_type, user, vehicle, vehicle_plate, start_time, end_time, billed_hours,
  hourly_rate, base_amount, refund_due_amount, hold_expires_at, cancelled_at,
  actual_entry_at, actual_exit_at, overstay_hours, overstay_amount,
  created_at, updated_at }
```
- **Manager/Admin** row — the same **plus**:
```
{ lot, consumer_email, consumer_name, can_check_in, can_check_out }
```
`hourly_rate`, `base_amount`, `refund_due_amount`, `overstay_amount` are money
strings. **Render `effective_status`**, not `status`: a lapsed
`PENDING_PAYMENT` hold reads `EXPIRED` there while the stored `status` stays
`PENDING_PAYMENT` (lazy expiry — reads never write).

### `POST /api/bookings/` — Consumer
Body: `{ "slot": <id>, "vehicle": <own id>, "start_time": "<iso>", "end_time": "<iso>" }`
→ `201` the consumer read row (status `PENDING_PAYMENT`, `hold_expires_at` set).
Refusals (§33): `400 INVALID_WINDOW` / `WINDOW_IN_PAST` / `MIN_DURATION_NOT_MET` /
`MAX_DURATION_EXCEEDED`; `404 SLOT_NOT_FOUND` / `LOT_NOT_BOOKABLE`; `409
SLOT_UNAVAILABLE` / `BOOKING_CONFLICT` / `NO_TARIFF`. On a `409` re-fetch
availability and let the user pick again.

### `GET /api/bookings/{id}/` — **Consumer only**
The read row **plus**:
```
{ lot, lot_address_line, lot_city, lot_state, lot_postal_code, slot_floor,
  can_cancel, can_extend }
```
A foreign/unknown id → `404 BOOKING_NOT_FOUND`. **Manager/Admin cannot call this
route** — they read the list row instead.

### `POST /api/bookings/{id}/cancel/` — Consumer → `200` the read row
(status `CANCELLED`, `refund_due_amount` set). Implements the §19 cutoff;
a paid booking cancelled in time records a full refund. Idempotent.
`409 BOOKING_NOT_CANCELLABLE` for a non-cancellable state; foreign id → `404`.

### `GET /api/bookings/{id}/extension-quote/?end_time=<iso>` — Consumer
→ `200 { added_hours, extension_amount, new_billed_hours, new_base_amount,
hourly_rate, new_end_time }` (money strings). Read-only; no charge.

### `POST /api/bookings/{id}/check-in/` — Manager
`CONFIRMED → IN_PROGRESS`, stamps `actual_entry_at`, marks the slot `OCCUPIED`.
→ `200` the **operator** row. Repeat is idempotent.
`409 BOOKING_NOT_CHECKINABLE`; foreign/unassigned → `404`.

### `POST /api/bookings/{id}/check-out/` — Manager
`IN_PROGRESS → COMPLETED`, stamps `actual_exit_at`, frees the slot, snapshots
`overstay_hours`/`overstay_amount`. → `200` the operator row.
`409 BOOKING_NOT_CHECKOUTABLE`; foreign/unassigned → `404`.

---

## 8. Payments

### `GET /api/payments/` — any authenticated role, paginated, **role-scoped**
Query: `?status=` (csv), `?method=`, `?purpose=`, `?booking=`, `?lot=`,
`?created_from=`, `?created_to=`, `?ordering=` (`created_at`/`-created_at`/
`paid_at`/`-paid_at`/`amount`/`-amount`), `?page=`, `?page_size=`.
Row depends on role:
- **Consumer** — the slim history row:
```
{ id, booking, booking_reference, slot_number, lot_code, lot_name, purpose, method,
  status, amount, currency, refunded_amount, receipt_available, paid_at, created_at }
```
- **Manager/Admin** — the transaction row (the same **plus**):
```
{ lot, consumer, consumer_email, vehicle_plate, extension_end_time }
```
`amount`/`refunded_amount` are money strings. `receipt_available` is `true` when
the payment is `SUCCEEDED` — offer the receipt link only then.
**Receipts are Consumer-only**: a Manager/Admin transaction row has no receipt
read (call `GET /api/payments/{id}/receipt/` as a Consumer only).

### `POST /api/payments/` — Consumer
Body: `{ "booking": <id>, "purpose"?: "BOOKING"|"EXTENSION", "end_time"?: "<iso>" }`
(`end_time` is **required for `EXTENSION`, forbidden for `BOOKING`**).
→ `201` the payment read row **plus `client_payload`**:
```
{ id, booking, purpose, method, status, amount, currency, provider_order_id,
  provider_payment_id, extension_end_time, failure_reason, paid_at,
  booking_applied, created_at, updated_at, client_payload: {...} }
```
Refusals: `409 BOOKING_NOT_PAYABLE` / `BOOKING_ALREADY_PAID`,
`404 BOOKING_NOT_FOUND`, `503 PAYMENT_GATEWAY_UNAVAILABLE`.

### `POST /api/payments/{id}/confirm/` — Consumer
Body: `{ "payload": { ...gateway callback... } }` → `200` the payment read row.
The server verifies the gateway signature; **the client must never assert
success**. Refusals: `409 PAYMENT_VERIFICATION_FAILED` /
`PAYMENT_CAPTURED_NOT_APPLIED`, `404 PAYMENT_NOT_FOUND`.

### `POST /api/payments/webhook/` — Public (server-to-server; the browser never calls it).

### `POST /api/payments/{id}/refund/` — Admin/Manager
No body → `201` the refund row
`{ id, payment, amount, status, provider_refund_id, reason, created_at, updated_at }`.
Idempotent. `409 PAYMENT_NOT_REFUNDABLE`, `502 PAYMENT_REFUND_FAILED`.

### `GET /api/payments/{id}/receipt/` — Consumer
```
{ receipt_number, payment, status, amount, currency, method, purpose, paid_at,
  transaction_id, booking, booking_reference, slot_number, lot_code, lot_name,
  start_time, end_time, billed_hours }
```
`409 RECEIPT_NOT_AVAILABLE` for an unsettled charge; foreign id → `404`.

---

## 9. Occupancy board

### `GET /api/parking-lots/{lot}/occupancy/` — Manager (assigned) or Admin, **bare object**
```
{ lot: { id, code, name },
  generated_at: "<iso>",
  summary: { total, available, occupied, out_of_service },
  slots: [
    { id, number, floor, slot_type, status,
      current_booking: null | { id, reference, vehicle_plate, status, start_time,
                                end_time, actual_entry_at, consumer_email } }
  ] }
```
Unassigned lot → `404`. `current_booking` is the single live `IN_PROGRESS`
booking (or `null`); `status` is the stored physical state — the two are not
collapsed.

### `WS /ws/parking-lots/{lot}/occupancy/?token=<access>` — Manager/Admin
The browser cannot set WebSocket headers, so the JWT access token goes in the
**query string**. On connect the server sends `{ "type": "occupancy", "board":
<the same object as the HTTP read> }`, then re-pushes on every change.
Server close codes: **`4401`** unauthenticated, **`4403`** wrong role / unassigned
lot. The socket is **read-only** (the client sends nothing). Fall back to polling
the HTTP read if the socket cannot connect.

---

## 10. Reports (Phase 8)

All reports share: **Manager+Admin** (platform is **Admin-only**), a half-open
period `?from=&to=` (ISO date **or** datetime, bucketed in `Asia/Kolkata`),
`?lot=` to narrow within scope (**except** platform, which has no lot), and a
**bare computed object** (no pagination). Omitted period = the trailing 30 days.
`from >= to` → `400 INVALID_WINDOW`; a `?lot=` outside scope → `404 LOT_NOT_FOUND`.

### `GET /api/reports/bookings/?from=&to=&lot=`
```
{ period: { from, to, timezone },
  scope: { lot, lots },
  total, by_status: { <all seven states> }, active_now, completed, cancelled }
```
`total` is the cohort **created** in the window; `by_status` is that cohort's
*current* status (all seven keys always present, zero-filled). `active_now` is a
*now* snapshot (`IN_PROGRESS`), independent of the period.

### `GET /api/reports/revenue/?from=&to=&lot=`
```
{ period, scope, currency: "INR",
  gross, refunded, net,
  by_purpose: { BOOKING, EXTENSION },
  payment_failures, overstay_recorded }
```
Money fields are strings. `overstay_recorded` is **recorded, not collected** —
display it separately, never add it to revenue.

### `GET /api/reports/occupancy/?from=&to=&lot=`
```
{ scope, period,
  current: { total, available, occupied, out_of_service, rate },
  window:  { bookings, booked_hours, bookable_hours, booked_rate } }
```
`current.rate` is the live rate; `window.booked_rate` is a **booked-hours proxy**
(no occupancy history is stored) — label them differently in the UI.

### `GET /api/reports/platform/?from=&to=` — **Admin only**
```
{ period,
  users:    { total, active, by_role: { CONSUMER, MANAGER, ADMIN } },
  lots:     { total, active },
  slots:    { total, by_status: { AVAILABLE, OCCUPIED, OUT_OF_SERVICE } },
  bookings: { total, active_now, completed, cancelled },
  revenue:  { gross, refunded, net },
  occupancy_rate, payment_failures, cancellations }
```
No `?lot=`. A Manager calls this and gets `403`.

> `/api/reports/dashboard/` (D78) is **not built**. For a landing page, call the
> metric families above directly (Manager: bookings + occupancy + revenue for the
> trailing day; Admin: platform + revenue).
