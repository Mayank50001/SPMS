# Phase 9 decisions (D79–D83)

Decisions made for the React Single Page Application (frontend) implementation
against the frozen backend API.

---

## D79 — Frontend stack: routing, state, data fetching and styling

**Accepted 2026-10-14 (phase open).**

- **Routing:** `react-router-dom` (v7) provides client-side role-scoped routing, nested layouts, and URL query-param-driven filters and pagination.
- **Data fetching:** Lightweight typed API client (`apiFetch`) with integrated refresh handling, combined with bespoke React hooks (`useApi`, `usePaginated`). Avoids heavyweight external cache dependencies while guaranteeing strict contract adherence and full control over error serialization and lifecycle.
- **Styling:** Practical, clean CSS design system (`app.css` / variables / utility classes) prioritizing readability, crisp typographic hierarchy, responsive data tables and cards, form validation feedback, and distinct role workspaces. Avoids gratuitous animation per PROJECT.md §31.
- **Build & Quality:** Standard Vite + React 19 + TypeScript (`tsc -b`) and `oxlint`.

---

## D80 — Token storage and single-flight refresh rotation

**Accepted 2026-10-14 (phase open).**

- **Storage:** JWT `access`, `refresh` tokens and current `user` profile are persisted in `localStorage`. Documented as an acceptable academic/development compromise (vulnerable to XSS if untrusted scripts run, but cleanly stateless across page reloads).
- **Refresh rotation (D17):** `POST /api/auth/refresh/` invalidates the presented refresh token and issues a new access token AND a new refresh token. The client persists the new refresh token immediately upon response.
- **Single-flight synchronization:** Concurrent API requests receiving `401 Unauthorized` are queued behind a single shared in-flight refresh `Promise`. If refresh succeeds, the queued requests replay once with the new access token. If refresh fails, session is cleared and the user is redirected to `/login`.

---

## D81 — Reports and Dashboard composition

**Accepted 2026-10-14 (phase open).**

- **Fan-out:** Because the backend `/api/reports/dashboard/` route is optional and unbuilt (D78), dashboard views for Managers and Administrators fan out directly to the metric family endpoints:
  - Manager: `GET /api/reports/bookings/`, `GET /api/reports/occupancy/`, `GET /api/reports/revenue/` (scoped to assigned lots).
  - Admin: `GET /api/reports/platform/` alongside metric family drill-downs.
- **Error isolation:** Metric tiles fetch in parallel; failure in one family displays an error state for that tile without tearing down the entire dashboard.

---

## D82 — Explicit stubs for deferred/unavailable features

**Accepted 2026-10-14 (phase open).**

- Features identified as deferred or without backend API surfaces (Walk-in booking / manager cash payment per D63, Notifications per Phase 7, Audit logs, Public QR code lookup) are presented with clear, deliberate stub screens or badges marked with `// TODO: Backend endpoint required`.
- Under no circumstances will the frontend fake backend routes, simulate offline database writes, or invent mock data payloads.

---

## D83 — Payment integration and verification

**Accepted 2026-10-14 (phase open).**

- **Provider:** Razorpay test mode integration loading `https://checkout.razorpay.com/v1/checkout.js` on demand.
- **Mock fallback:** For local testing environments where `PAYMENT_GATEWAY=mock`, the payment screen provides a 1-click test confirmation helper passing the mock payload.
- **Server verification:** The client never treats client-side payment completion as success. Confirmation is always delegated to `POST /api/payments/{id}/confirm/` which verifies signatures server-side.

