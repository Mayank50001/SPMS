# Progress — Phase 8 (Reports) ✅ COMPLETE — 8.1–8.5 delivered; 8.6 optional, deferred

> **Scope (PROJECT.md §36 / §29):** the Manager and Administrator **reports** and
> the numbers behind the two **dashboards** — booking statistics, revenue
> aggregation and occupancy aggregation. This is a **read-only** phase: it creates
> no model and no migration, and computes everything from tables Phases 3–6
> already built.
> Working conventions and the reading protocol: [`../README.md`](../README.md).
> What reports must expose: PROJECT.md **§29**; the pages they fill: PROJECT.md
> **§30** (Manager *Dashboard*/*Reports*, Administrator *Dashboard*/*Reports*).
> Phase 6 context (the occupancy the reports summarise):
> [`../phase-6-occupancy/PROGRESS.md`](../phase-6-occupancy/PROGRESS.md).

Last updated: **2026-10-14** · **Complete: 8.1–8.5 delivered. 8.6 (the dashboard
bundle, D78) is optional and deferred — the frontend calls the metric families
directly instead. The API surface is now frozen for Phase 9.**

---

## Where this sits

Phase 6 completed the **manager/admin workflow** for bookings and occupancy
(6.1–6.5). Phase 8 is the last backend phase: it fills the **Reports** pages and
the **dashboard tiles** that Phase 6 left empty, after which the API surface is
frozen and the React frontend (Phase 9) can be built against it once.

```text
Phase 6 (occupancy + operator booking reads)   ✅ done
        ↓
Phase 8 (reports)                              ✅ done (8.1–8.5; 8.6 optional)
        ↓
Phase 9 (React frontend)                       📋 opened — docs ready
```

**Why before the frontend** (agreed 2026-10-12): the two role **dashboards** are
the landing page for a Manager and an Administrator, and the **Reports** pages are
part of §30. Building the frontend first would mean stubbing exactly the screens
users see first and returning to rebuild them.

> **No new infrastructure.** Unlike Phase 6 (D72's Channels + Redis exception),
> this phase adds **no** package, **no** service and **no** setting. It is
> ordinary DRF reads over existing tables.

---

## Start here (fresh session)

1. [`../README.md`](../README.md) — conventions + reading protocol.
2. This file — scope, the increment plan, what is next.
3. [`DECISIONS.md`](DECISIONS.md) — **D73–D78 (settled 2026-10-14 at phase
   open); implement 8.1–8.5, then decide 8.6.**
4. Only if a task touches them: the "Dependencies on earlier phases" table below.

---

## Increment plan

> **Draft — confirm at phase open.** Each increment is a coherent feature and
> surfaces its decision **before** its code, recorded as its own `D<n>`.

> **Batching (from 2026-10-10).** These increments are independent in business
> logic — 8.1 is the one shared seam they all sit on, and 8.6 composes the rest —
> so under the batching rule they **may be delivered together in one session**
> once D73–D78 are settled. Batching must not blur them: each stays a coherent,
> separately-decided and separately-committable unit (§43).

| # | Increment | Decision | Status |
|---|-----------|----------|--------|
| 8.1 | **Reports foundation** — the `/api/reports/` namespace, role scoping, the shared period/lot filter, error shape | D73 | ✅ Done (2026-10-14) |
| 8.2 | **Booking statistics** — totals and per-status counts for a period | D74 | ✅ Done (2026-10-14) |
| 8.3 | **Revenue aggregation** — gross/refunded/net from the payment + refund ledgers | D75 | ✅ Done (2026-10-14) |
| 8.4 | **Occupancy aggregation** — the live rate and a windowed booked-rate proxy | D76 | ✅ Done (2026-10-14) |
| 8.5 | **Administrator platform report** — the §29 administrator block, platform-wide | D77 | ✅ Done (2026-10-14) |
| 8.6 | **Dashboard bundles** — one role-scoped call per landing page (optional) | D78 | ⏸ Deferred (optional) |

### Brief per increment

- **8.1** wires a new `apps/reports/urls.py` into `config/urls.py` and settles the
  seam every later increment reuses: the access rule (Manager assigned lots /
  Admin all; a Consumer is `403`, an unassigned lot is `404`), the shared
  `?from=&to=` + `?lot=` filter, the `BUSINESS_TIMEZONE` day-bucketing, and the
  unpaginated response shape (D66 opt-out). **Read-only; no model, no migration.**
- **8.2** answers §29's *total / active / completed / cancellations* for the
  Manager's lots (Admin platform-wide) over a period.
- **8.3** answers §29's *revenue*: `Payment` rows are the source of truth (not
  `Booking.base_amount`), the refund ledger (D61) nets them, and the §19 overstay
  debt is reported **separately** — recorded, not collected (D70).
- **8.4** answers §29's *occupancy* and *occupancy rate*. Slot state is live-only
  (D2/D33) with **no history stored**, so the increment reports the **current**
  rate (reusing 6.5's summary) plus a **windowed booked-rate proxy** derived from
  bookings, clearly labelled.
- **8.5** composes 8.2–8.4 platform-wide for the Administrator's §29 block, plus
  the platform totals (users / lots / slots) and payment failures.
- **8.6** (optional) returns the tile set for a role's landing page in **one**
  call, so the dashboard is not four round-trips. It introduces no new figure —
  it only bundles 8.2–8.5.

---

## Dependencies on earlier phases

Read these **only** when a Phase 8 task touches them.

| Decision / artefact | Why Phase 8 needs it |
|---------------------|----------------------|
| **D2 / D33 / §18** | Slot state is **live only**; occupancy has **no stored history**. This is *why* 8.4 must separate the current rate from a booked-hours proxy. |
| **D5** | Time is stored UTC; report **day-bucketing** uses `BUSINESS_TIMEZONE` (`Asia/Kolkata`, `config/settings.py`). |
| **D34 / §46** | Money is `Decimal`, **INR-only**; aggregates stay `Decimal`, never float. |
| **D40** | The booking state enum the statistics group by (`PENDING_PAYMENT`/`CONFIRMED`/`IN_PROGRESS`/`COMPLETED`/`CANCELLED`). |
| **D41** | The half-open window predicate — the period filter uses the same `[from, to)` convention. |
| **D57** | `Payment.status` (`PENDING`/`SUCCEEDED`/`FAILED`) — revenue counts `SUCCEEDED` only. |
| **D61** | The **refund ledger** — "how much was refunded" is the sum of `Refund` rows, never a mutated payment. |
| **D65 / D67** | The role-scoped queryset pattern these reports mirror (Manager → assigned lots, Admin → all, empty-not-`403` for a caller who owns none). |
| **D66** | The pagination envelope reports **opt out of** (a computed object, like availability and the occupancy board). |
| **D70** | Overstay is a **recorded debt, not collected** — reported separately, never added to revenue. |
| **D71** | The occupancy board's `summary` block is reused for the current occupancy figures. |
| **PROJECT.md §29** | The exact metric lists for the Manager and Administrator reports. |

---

## Guardrails for this phase

- **Read-only, and provably so** — **no new model, no migration, no write path**
  (§42). If a migration ever appears, the plan has drifted; stop and re-decide.
- **Nothing is invented** — every figure is computed from tables Phases 3–6
  built. No cached/denormalised counters (they would be a model, and a source of
  drift).
- **Role scoping is server-side** — Manager → assigned lots, Admin → all;
  a Consumer gets `403`, an unassigned lot is `404`, never `403` (Invariant 3).
- **Aggregation is the human's decision** (§Phase 8, §9) — the *definitions*
  ("what counts as revenue", "what does a day mean", "what is occupancy rate")
  are settled in `DECISIONS.md` **before** the query is written.
- **No fake data** — figures are real aggregates; an empty scope is a real `0`,
  never a hardcoded placeholder (§Phase 9's rule extends to the backend).
- **Aggregates are `Decimal`** and serialised as strings for money (D34); counts
  are integers. Never float.
- **Small, scoped commits** in `feat(reports): ...` style (PROJECT.md §43).
