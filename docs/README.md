# SPMS documentation

Entry point for the SPMS docs. The **authoritative specification** is
[`../PROJECT.md`](../PROJECT.md); this folder holds the per-phase working
context — what each phase built (**PROGRESS**) and the decisions made or pending
(**DECISIONS**).

> Replaces the previous single `docs/PROGRESS.md` and `docs/DECISIONS.md`. Those
> files grew to cover every phase at once, so at the start of a session you had
> to read all of it to find the part that mattered. Docs are now split by phase.

---

## Phase tracker

| Phase | Scope | Status | Docs |
|-------|-------|--------|------|
| 0 | Repository setup | ✅ Done | [`foundation/PROGRESS.md`](foundation/PROGRESS.md) |
| 1 | Backend foundation (config, PostgreSQL, health) | ✅ Done | [`foundation/PROGRESS.md`](foundation/PROGRESS.md) |
| 2 | Authentication and users | ✅ Done | [`phase-2-authentication/`](phase-2-authentication/) |
| 3 | **Parking domain (lots, slots, pricing, assignments)** | ✅ Done (3.1–3.4; reopened once for D45 duration fields) | [`phase-3-parking/`](phase-3-parking/) |
| 4 | Booking | 🔵 In progress (4.1–4.7 ✅; next 4.8) | [`phase-4-booking/`](phase-4-booking/) |
| 5 | Payment | ⚪ Not started | — |
| 6 | Occupancy simulation | ⚪ Not started | — |
| 7 | Notifications | ⚪ Not started | — |
| 8 | Reports | ⚪ Not started | — |
| 9 | React frontend | ⚪ Not started | — |
| 10 | Testing and hardening | ⚪ Not started | — |

---

## Layout

```text
docs/
├── README.md                       # this file — navigation + reading protocol
├── decisions-index.md              # D-number -> the file that holds the full entry
├── deferred-features.md            # scheduled-but-not-dropped, cross-phase
├── foundation/                     # phases 0 & 1, plus the cross-cutting decisions
│   ├── PROGRESS.md
│   └── DECISIONS.md                # D1-D10
├── phase-2-authentication/
│   ├── PROGRESS.md
│   └── DECISIONS.md                # D11-D28
├── phase-3-parking/
│   ├── PROGRESS.md
│   └── DECISIONS.md                # D29-D38 (accepted; D33 revises D2) + 3.2-3.4 refinements + post-close D45 fields
└── phase-4-booking/
    ├── PROGRESS.md
    └── DECISIONS.md                # D39-D53 (accepted; D39 revised in 4.2; D51-D52 = 4.6, D53 = 4.7) + later-increment open questions
```

Each phase owns one `PROGRESS.md` (state) and one `DECISIONS.md` (decisions that
phase made or must make). A phase folder never re-states another phase's work;
it **references** it.

---

## Reading protocol (start of a session)

Read as little as possible:

1. **Always:** this file (phase tracker + protocol).
2. **Always:** the current phase's `PROGRESS.md` — where we are, what is next.
3. **Always:** the current phase's `DECISIONS.md` — the decisions that apply,
   and the ones still open.
4. **Only when the phase says so:** an earlier phase's `DECISIONS.md`, pulled in
   through the "Dependencies on earlier phases" section of the current phase's
   docs. Those sections name the exact decision IDs needed.
5. To find a specific `D<n>` referenced in code, use
   [`decisions-index.md`](decisions-index.md).

Do **not** read every phase's files by default. The point of the split is that
the current phase's docs plus a short dependency list are enough.

---

## Working conventions (apply to every phase)

- **Increment rule** (PROJECT.md §1/§38): size an increment by the *coherent
  feature boundary*, not by file count. One feature per session, delivered whole.
  The rule that binds is *don't implement future phases* — not *build less of the
  current feature*.
- **Agent role** (PROJECT.md §8 Rule 2): the agent supplies complete runnable
  code including business logic, plus the decisions it embeds; the human reads,
  approves each decision and owns the result. Everywhere PROJECT.md says "human
  writes X" (§36's phase lists, §21's "the human developer must design"), **§8
  wins**: it means the human owns the *decision*, not that they author the code.
  The agent may therefore write backend logic, but it must name each consequential
  decision and its trade-offs rather than burying it in boilerplate (§9, §10).
  `TODO(HUMAN)` markers in code mean "a decision is pending here".
- **Frontend** (PROJECT.md §11): frontend implementation is delegated to the
  agent and may be written substantially or completely, but only against real
  backend APIs (never invented ones). No frontend feature starts before its
  backend contract is settled (§23). Frontend is **Phase 9**; it is out of scope
  for every backend phase.
- **Core logic** (PROJECT.md §9): booking allocation, conflict detection,
  holds, state transitions, pricing, authorization, occupancy, aggregation and
  concurrency are decided *with* the human before they are coded.
- **Verification** is manual during domain phases: `manage.py check`,
  `manage.py shell`, and `curl` against the dev server (or the frontend once it
  exists). Automated tests are written incrementally where they add value
  (PROJECT.md §34); the dedicated hardening pass is Phase 10.
- **Migrations** (PROJECT.md §42): before generating one, state the model
  change → expected database change → data implications.
- **Git** (PROJECT.md §43): small, scoped commits in `feat(domain): ...` style.
