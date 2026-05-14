# Phase 7: Tournament View & Smoke Test - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-14
**Phase:** 07-tournament-view-smoke-test
**Mode:** `--auto` (user requested no clarifying questions; first-option / recommended-option default applied across every area)
**Areas discussed:** Tournament data path, Significance markers, Empty-state semantics, Dashboard nav placement, Filter UX, Smoke "major tile" scope, Smoke runner wiring, Frontend data plumbing

---

## A. Tournament data path

| Option | Description | Selected |
|--------|-------------|----------|
| Gateway proxy reads committed snapshot JSON (RO bind-mount) | api-gateway mounts `services/tournament-harness/data/snapshots:/app/snapshots:ro` and exposes `/api/tournament/snapshots[/{id}]`. tournament-harness service stays opt-in. | ✓ |
| Gateway proxies to tournament-harness `:8010` live SQLite | Requires `--profile tournament` up. Frontend gets real-time progress but smoke needs the harness running. | |
| Frontend reads static snapshot via vite proxy / static file route | Cuts gateway out of the loop. Doesn't match Phase 6 ingress posture. | |

**Auto-selected:** Gateway proxy + snapshot files (D-01). Reuses Phase 6 D-09 gateway-owns-ingress posture; tournament-harness profile remains opt-in (D-02); recorded-tape smoke test works without bringing tournament-harness up.

## B. Significance markers

| Option | Description | Selected |
|--------|-------------|----------|
| Backend merges snapshot + ensemble + significance into one response | Single React Query fetch. Gateway joins on filename convention. | ✓ |
| Frontend fetches three artifacts and merges client-side | Three React Query keys; client-side complexity. | |
| Phase 3 schema bump — embed significance in snapshot at export time | Schema rev breaks reproducibility of historical snapshots; couples two phases. | |

**Auto-selected:** Backend merge (D-03), badge column + tooltip rendering (D-04), graceful "—" when artifacts missing (D-05).

## C. Empty-state semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit "No tournaments yet — run CLI" empty state + commit fixture snapshot for smoke | Pure empty-state for fresh-clone operators; fixture only used in smoke. | ✓ |
| Bundle a synthetic demo snapshot in `data/snapshots/` (production-visible) | Operators see fake data on first run. Bad signal. | |
| Skip Tournament tile if no snapshot present | Smoke partial; obscures regressions. | |

**Auto-selected:** Empty state + fixture-driven smoke (D-06, D-07, D-08).

## D. Dashboard nav placement & view structure

| Option | Description | Selected |
|--------|-------------|----------|
| New top-level `/tournament` route, dedicated page | Sibling to `/performance`, `/portfolio`. | ✓ |
| Sub-tile on `Phase3Dashboard.jsx` (ML-themed page) | Phase3 is currently LABELED_STALE; mixing live tournament view in feels wrong. | |
| Both — summary tile + full route | Doubles surface for the same data. | |

**Auto-selected:** Top-level `/tournament` (D-09); selector + filter chips + table + footer layout (D-10); plain `<table>` (D-11); `dsr DESC` default sort (D-12).

## E. Filter UX

| Option | Description | Selected |
|--------|-------------|----------|
| Chip multi-select (symbol + architecture) + segmented status, URL-backed | Reuses Phase 6 `useSearchParams` pattern. Shareable links. | ✓ |
| Per-column header dropdowns (TanStack Table) | Adds dependency; not needed at v1 scale. | |
| URL params only (no visible UI controls) | Power-user only; bad first impression. | |

**Auto-selected:** Chip filters + URL params (D-13, D-14).

## F. Smoke "major tile" scope

| Option | Description | Selected |
|--------|-------------|----------|
| Audit-driven — every row in `06-TILE-AUDIT.json` asserted | Comprehensive; FIXED/LABELED_STALE/REMOVED branches per verdict. Tournament tile added to audit. | ✓ |
| Strict ROADMAP 4 (Performance, Portfolio, Safety State, Tournament) | Bare minimum; misses LABELED_STALE regressions. | |
| Hybrid — ROADMAP 4 gate + audit table observable but not asserted | Two failure modes; bookkeeping cost. | |

**Auto-selected:** Audit-driven (D-15); Tournament tile added to audit (D-16); Safety state cells get a special-case assertion (D-17).

## G. Smoke runner wiring

| Option | Description | Selected |
|--------|-------------|----------|
| `pytest-playwright` plugin, Chromium only | One language, one CI command, reuses Phase 2 fixtures. | ✓ |
| Standalone `frontend/e2e/` + `npx playwright test` | Two runners, two CI invocations, two failure modes. | |
| Pytest subprocess → `npx playwright test` → junit-xml | Worst of both worlds. | |

**Auto-selected:** pytest-playwright (D-18) + Phase 2 fixture reuse (D-19) + single CI workflow (D-20) + local invocation parity (D-21) + screenshots-on-failure artifacts (D-22).

## H. Frontend data plumbing

| Option | Description | Selected |
|--------|-------------|----------|
| React Query, single fetch on mount, `staleTime: Infinity`, manual refresh | Matches cold-data semantics. Code comment explains why we buck the 5-second cadence. | ✓ |
| React Query default polling (5s) | Wastes cycles; data doesn't change mid-session. | |
| `useEffect` + `fetch`, no React Query | Inconsistent with rest of dashboard. | |

**Auto-selected:** React Query single-fetch (D-23); URL filter state, no global store (D-24); `api.js` extension matches existing groupings (D-25).

---

## Claude's Discretion

Logged in `07-CONTEXT.md` `<decisions>` under "Claude's Discretion". Summary:
- Exact column widths / tooltip library / table CSS — pick to match Editorial Trading Floor.
- Smoke origin (gateway `:8000` vs vite dev `:3000`) — recommend gateway.
- Multi-browser smoke — Chromium-only v1.
- Linking the new view from existing dashboard cards — recommend yes, don't block.

## Deferred Ideas

Logged in `07-CONTEXT.md` `<deferred>` section. Summary:
- Live SQLite read path (v2)
- Per-run drill-down page (v2)
- Cross-tournament comparison view (v2)
- Triggering tournament runs from the UI (v2)
- WebSocket / SSE push (v2)
- Embedding significance into snapshot (v2)
- Visual regression / screenshot diffing (v2)
- Multi-browser smoke (v2)
- Mobile responsive layout (v2)
- Pagination / virtualization (v2)
- Back-fill `last_updated_at` on every body-tile endpoint (DASH-07 or v2)
- Stale-badge threshold for snapshot `exported_at` (v2 if needed)

---

*This log is intentionally auto-mode brief. Every alternative was considered against Phase 6 / Phase 3 / Phase 4 CONTEXT.md decisions and CLAUDE.md rules; the chosen option is the one that minimizes new coupling and matches existing patterns. If the operator wants a different option, edit the matching `D-NN` in `07-CONTEXT.md` and re-run `/gsd-plan-phase 7`.*
