# Progress — Phase 9 (React frontend) 📋 OPENED

> **Scope (PROJECT.md §11, §30, §31):** build the React SPA against the frozen
> backend API — the Consumer, Parking Manager and Administrator experiences, as
> the page lists in PROJECT.md **§30**, guided by the design principle in **§31**
> (practical, usable, correct integration; no gratuitous animation).
> Working conventions and the reading protocol: [`../README.md`](../README.md).

Last updated: **2026-10-14** · **Docs written (API map + build guide). No
frontend code yet.**

---

## Where this sits

Phase 8 completed the backend API surface (reports). Phase 9 is the **only**
remaining build phase before hardening (Phase 10). The backend is frozen for the
frontend's purpose: the frontend must be built against the real API once, not
stubbed against guessed routes.

```text
Phase 8 (reports — backend)        ✅ done (8.1–8.5; 8.6 optional, deferred)
        ↓
Phase 9 (React frontend — THIS PHASE)   📋 opened; docs ready
        ↓
Phase 10 (testing & hardening)
```

---

## Start here (fresh session)

1. [`../README.md`](../README.md) — conventions + reading protocol.
2. [`../api-contract.md`](../api-contract.md) — the frozen cross-cutting contract.
3. [`API-MAP.md`](API-MAP.md) — every route and field (the build reference).
4. [`FRONTEND-GUIDE.md`](FRONTEND-GUIDE.md) — stack, structure, patterns, tips,
   page → endpoint map.
5. PROJECT.md **§30** (pages) and **§31** (design principle).

---

## Increment plan (draft — confirm at phase open)

The frontend is delivered as **vertical slices per role**, each slice a coherent,
separately-reviewable unit (§38). A slice is done when its screens work against
the live API with loading/empty/error states.

| # | Slice | Depends on | Status |
|---|-------|-----------|--------|
| 9.1 | **App shell + API client + auth** — routing, `apiFetch`, token store with single-flight refresh, role guards, Login/Register, Profile | API map §4–§5 | ⏳ Planned |
| 9.2 | **Consumer journey** — search → lot details → availability → booking → payment → confirmation → my bookings → cancel/extend; Vehicles | 9.1 | ⏳ Planned |
| 9.3 | **Manager workspace** — my lots, slot management, pricing, bookings + check-in/out, occupancy board (+ WS), reports | 9.1 | ⏳ Planned |
| 9.4 | **Administrator workspace** — users/managers, lots + manager assignment, business rules, bookings, transactions + refund, reports/platform | 9.1 | ⏳ Planned |
| 9.5 | **Polish** — responsive pass, loading/empty/error audit, the §31 checklist, stub markers for unavailable features | 9.2–9.4 | ⏳ Planned |

---

## Guardrails for this phase

- **Never invent an endpoint or a field** (§11/§23). A missing route is a
  `// TODO: Backend endpoint required`, not a guess.
- **The backend is authoritative.** UI role guards are UX; a `403`/`404` from the
  API is the truth (Invariant 2/3 — a foreign object is `404`, not `403`).
- **No fake data.** Empty is a real empty state.
- **Practical over pretty** (§31): usability, navigation, correct integration,
  loading states, error handling, form validation, responsive layout.
- **Unavailable features are stubbed, not faked:** walk-in/cash (D63),
  notifications (Phase 7), audit logs, the public QR lookup, and the optional
  `/api/reports/dashboard/` bundle (D78).
- **Small, scoped commits** in `feat(frontend): ...` style (PROJECT.md §43).

---

## Open questions (decide before/at 9.1)

1. **Routing/state/data stack** — `react-router` + TanStack Query vs plain hooks;
   CSS approach. Record as Phase 9 decisions.
2. **Token storage** — `localStorage` (simple, XSS-sensitive) vs in-memory +
   refresh; for an academic build `localStorage` with a comment is acceptable.
3. **`/api/reports/dashboard/` (D78)** — build the bundle, or have the dashboard
   fan out to the metric families? (Backend D78 remains optional.)
