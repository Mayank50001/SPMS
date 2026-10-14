# Phase 8 decisions (D73–D78)

Decisions the reports phase made. These were **proposed** (2026-10-14) and were
**settled at phase open the same day**, **before** any code (§9). Each is
indexed in [`../decisions-index.md`](../decisions-index.md).

> **Read-only phase.** None of these decisions introduces a model, a migration or
> a write path. Every figure is computed from tables Phases 3–6 built. If a
> migration ever appears in this phase, the plan has drifted — stop and re-decide.

---

## D73 — Reports surface and access model

**Accepted 2026-10-14 (phase open).**

- **Home:** `apps/reports/` (created in Phase 0, still empty). It gains `urls.py`,
  `views.py`, `serializers.py`, `services.py` and tests; `config/urls.py` includes
  it under `/api/reports/`. **No `models.py`, no migrations.**
- **Shape — metric families, not role pages:** `GET /api/reports/bookings/`
  (D74), `.../revenue/` (D75), `.../occupancy/` (D76), `.../platform/` (D77) and
  `.../dashboard/` (D78). A family is the unit of reuse: the *same* revenue figure
  feeds the Manager Reports page, the Manager dashboard and the Admin page.
- **Who:** Manager and Administrator (`IsAdminOrManager`). A Consumer is `403`;
  anonymous is `401`.
- **Scope:** Admin → every lot; Manager → their assigned lots (`lot__manager`).
  `?lot=<id>` narrows **within** scope; a Manager naming an **unassigned** lot is
  `404` `LOT_NOT_FOUND`, never a `403` (Invariant 3 — the D65/D67 pattern).
- **Period:** `?from=&to=`, ISO 8601 date or datetime, **half-open `[from, to)`**
  (the D41 convention). Omitted → the **trailing 30 days** ending now.
  `from >= to` → `400` `INVALID_WINDOW` (the code `available_slots` already uses).
  Calendar dates are bucketed in **`BUSINESS_TIMEZONE`** (`Asia/Kolkata`, D5).
- **Shape:** an **unpaginated computed object** (D66 opt-out, like
  `/availability/` and the occupancy board). A report is one statement, not a
  browsable collection.
- **Read-only:** `GET` only.

**Rationale.** Mirrors the two read patterns the project already has: the
role-scoped queryset (D65/D67) and the whole-set unpaginated exception for a
computed view (D66).

**Rejected.**

- **A `/reports/manager/` + `/reports/admin/` pair.** Couples each figure to a
  page; the same numbers are needed in three places, so a page-shaped route would
  duplicate the logic or force the frontend to re-derive it.
- **Nesting under a lot** (`/parking-lots/{lot}/reports/…`). The Administrator
  report is platform-wide and has no lot, so this needs a second parallel surface.
- **Datetime-only filters.** The frontend sends calendar dates; the API accepts
  both and normalises.

---

## D74 — Booking statistics

Code in 8.2. **Accepted 2026-10-14.**

```text
GET /api/reports/bookings/?from=&to=&lot=
```

```json
{
  "period": { "from": "…", "to": "…", "timezone": "Asia/Kolkata" },
  "scope":  { "lot": null, "lots": [1, 2] },
  "total": 42,
  "by_status": { "PENDING_PAYMENT": 2, "CONFIRMED": 7, "IN_PROGRESS": 3,
                 "COMPLETED": 26, "CANCELLED": 4 },
  "active_now": 3,
  "completed": 26,
  "cancelled": 4
}
```

- **`total` is a cohort:** bookings **created** in `[from, to)` (`created_at`)
  within scope. §29's "total bookings" for a period means bookings *made* in it.
- **`by_status` is the current status of that same cohort.** A booking created in
  the window may since have been completed or cancelled. There is **no status
  history stored**, so "status at the window's end" cannot be reconstructed; the
  report says so in its docstring and never pretends otherwise.
- **`active_now` is a snapshot, not windowed:** bookings currently `IN_PROGRESS`
  in scope. §29's "active bookings" reads as *who is parked now*, so it is
  deliberately independent of the period.
- **`completed` / `cancelled`** restate the cohort's `COMPLETED` / `CANCELLED`
  counts as named fields, because §29 lists them by name.
- Every status key is present, `0` when empty, so the frontend never guards for a
  missing key. **Settled 2026-10-14:** "every status" means **all seven**
  stored states — the five §29 names plus `EXPIRED` and `TERMINATED` — so a
  lapsed hold or a terminated booking is counted, not silently dropped.

**Rationale.** The only honest reading given no stored status history. Splitting
"volume in a period" (cohort) from "who is here now" (snapshot) keeps both
meaningful, instead of blending them into a number that means neither.

**Rejected.**

- **Anchoring on `start_time`.** `start_time` is the *plan*; creation date is the
  natural volume metric, and §29 filters by date.
- **"All bookings overlapping the window".** A booking window rarely matches the
  report window; that set is hard to explain and rarely what a manager means.

---

## D75 — Revenue aggregation

Code in 8.3. **Accepted 2026-10-14.**

```text
GET /api/reports/revenue/?from=&to=&lot=
```

```json
{
  "period": { "…": "…" }, "scope": { "…": "…" }, "currency": "INR",
  "gross": "12340.00", "refunded": "340.00", "net": "12000.00",
  "by_purpose": { "BOOKING": "11000.00", "EXTENSION": "1340.00" },
  "payment_failures": 5,
  "overstay_recorded": "90.00"
}
```

- **Source of truth is `Payment`, `status = SUCCEEDED`** (D57) — never
  `Booking.base_amount`. A booking can be unpaid or lapsed; only the payment
  ledger records money that actually moved.
- **Window on `paid_at`** (the moment of capture); a `SUCCEEDED` row always has
  one.
- **`gross`** = Σ `Payment.amount` over the window + scope.
- **`refunded`** = Σ `Refund.amount` where `Refund.status = SUCCEEDED` and the
  parent payment is in scope (D61). `PENDING`/`FAILED` refunds are *not* yet money
  returned and are excluded — a pending refund counts the moment it is
  acknowledged.
- **`net` = `gross` − `refunded`.**
- **`by_purpose`** splits `gross` into `BOOKING` / `EXTENSION` (D57 purposes).
- **`payment_failures`** is a *count* of `FAILED` payments in the window, not
  money.
- **`overstay_recorded`** = Σ `Booking.overstay_amount` recorded in the window
  (D70). **Settled 2026-10-14:** the window is measured on `actual_exit_at` — the
  check-out moment the debt was recorded — not the booked `end_time`. It is
  **reported separately and never added to revenue**: it was never
  collected (collection is deferred, D63), so folding it in would overstate
  income. Shown so the recorded debt is not silently lost.
- Money is serialised as **strings** (`Decimal` → `str`), INR-only (D34).

**Rationale.** The payment and refund ledgers are append-only (D57/D61); summing
them is the only way "how much was refunded" stays truthful over time.

**Rejected.**

- **Deriving revenue from `Booking.base_amount`.** Ignores refunds and unpaid
  bookings.
- **Counting `PENDING` refunds as returned.** They have not moved yet.
- **Adding overstay to revenue.** It was never collected (D70/D63).

---

## D76 — Occupancy aggregation

Code in 8.4. **Accepted 2026-10-14.**

```text
GET /api/reports/occupancy/?from=&to=&lot=
```

```json
{
  "scope":   { "…": "…" }, "period": { "…": "…" },
  "current": { "total": 40, "available": 12, "occupied": 26,
               "out_of_service": 2, "rate": "0.6842" },
  "window":  { "bookings": 37, "booked_hours": "312.00",
               "bookable_hours": "586.00", "booked_rate": "0.5324" }
}
```

- **Two figures, never blended.**
- **`current`** is the **live** board summary (reused from 6.5's
  `build_occupancy_board`) with `rate = occupied / (total − out_of_service)`. A
  point-in-time truth.
- **`window`** is a **booked-rate proxy**: `booked_hours` = Σ booked slot-hours
  of bookings **overlapping** `[from, to)` (clipped to the window), and
  `bookable_hours` = (slots in scope, **excluding `OUT_OF_SERVICE`**) × window
  length, so `booked_rate = booked_hours / bookable_hours`. This is *booked*
  time, **not** measured occupancy.
- **Withdrawn bays leave the denominator** — they are not capacity.

**Rationale.** §29 asks for "occupancy" *and* "occupancy rate", and the Reports
page filters by date, so a windowed figure is expected. But slot state is
**live only** (D2/D33) and the schema stores **no occupancy history**, so a true
time-averaged occupancy for a *past* window cannot be reconstructed. Giving the
two clearly-labelled figures is the truthful middle: refuse nothing the page
needs, fabricate no history.

**Rejected.**

- **Only the live snapshot.** Leaves the date filter meaningless on the Reports
  page.
- **Storing an occupancy history or a snapshot job.** A new model + migrations +
  a scheduler — exactly the infrastructure this phase avoids (and the lazy-
  evaluation spirit of D6).
- **Calling the proxy "occupancy".** It would read as measured history; it is
  *booked* time and is named so.

---

## D77 — Administrator platform report

Code in 8.5. **Accepted 2026-10-14.**

```text
GET /api/reports/platform/?from=&to=
```

```json
{
  "period": { "…": "…" },
  "users":   { "total": 120, "active": 118,
               "by_role": { "CONSUMER": 110, "MANAGER": 7, "ADMIN": 3 } },
  "lots":    { "total": 9, "active": 8 },
  "slots":   { "total": 540,
               "by_status": { "AVAILABLE": 300, "OCCUPIED": 210,
                              "OUT_OF_SERVICE": 30 } },
  "bookings": { "total": 420, "active_now": 61, "completed": 330,
                "cancelled": 29 },
  "revenue": { "gross": "…", "refunded": "…", "net": "…" },
  "occupancy_rate": "0.6842",
  "payment_failures": 12,
  "cancellations": 29
}
```

- **Administrator-only** (`IsAdmin`). A Manager gets `403` here; their surface is
  D74–D76.
- **Platform-wide by definition**, so there is **no `?lot=`** — §29's
  administrator block is the global view. The period filter still applies where
  meaningful.
- **Composes the 8.2–8.4 figures** (no new logic) plus the platform counts §29
  names: total users / lots / slots, occupancy rate, payment failures, cancelled
  bookings. `lots.total` counts all lots, `lots.active` the `is_active` ones.
- Because there is no lot scope, the `404`-for-unassigned-lot rule does not
  apply; the only gate is the role.

**Rationale.** §29's administrator list is a superset summary. Reusing the
manager computations guarantees Manager and Administrator see the *same* revenue
and occupancy for the same period — one definition, two views.

---

## D78 — Dashboard bundles (optional)

Code in 8.6. **Accepted 2026-10-14; go/no-go decided after 8.5.**

```text
GET /api/reports/dashboard/
```

- **Role-scoped single call** returning the tiles for the caller's landing page:
  - **Manager:** today's arrivals/departures (bookings whose `start_time` /
    `end_time` fall in today, `BUSINESS_TIMEZONE`), live occupancy rate, revenue
    today, active now.
  - **Administrator:** platform totals + revenue today.
- **Bundles only** D74–D76 figures for the caller's role. It introduces **no new
  number** — it exists so a landing page is one request instead of four.
- **No consumer variant.** A Consumer's dashboard is their own bookings, already
  served by D67's `GET /api/bookings/`; adding one here would duplicate D67.
- **Depends on 8.2–8.5**, so it is the one increment that may be dropped without
  loss if the session runs short — the Reports pages work without it.

**Rationale.** A dashboard should not fan out to four calls. Kept
composition-only so it can never become a second source of truth.

---

## Settled at phase open (2026-10-14)

The discretionary calls a human confirmed **before** 8.1's code; the rest
follows mechanically from the decisions above.

1. **Default period** — trailing **30 days** when `?from=&to=` is omitted (D73). ✅
2. **"Active"** — a *now* snapshot (`IN_PROGRESS`), not a windowed count (D74). ✅
3. **`by_status`** — current status of the created-in-window cohort (D74). ✅
4. **Status keys** — **all seven** stored states (`EXPIRED`/`TERMINATED`
   included), zero-filled (D74). ✅ resolved at open
5. **Refunds counted when** `SUCCEEDED`, not `PENDING` (D75). ✅
6. **Overstay** shown separately, never in revenue; windowed on `actual_exit_at`
   (D75). ✅ resolved at open
7. **Occupancy** reported as *live rate* + *booked-rate proxy*, labelled (D76). ✅
8. **D78** — go/no-go **after 8.5**; it composes only and can be dropped without
   loss (D78). ⏸ deferred to 8.5
