# Phase 10: Path-to-LIVE Dashboard - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-17
**Phase:** 10-path-to-live-dashboard
**Areas discussed:** Carry-ins endpoint design, 24h continuous-PASS window mechanics, Tile placement + visual layout, Smoke test scope + CI workflow
**Mode:** `/gsd-discuss-phase 10` with user override "make reasonable calls, redirect if wrong" — single batched round of headline forks (AskUserQuestion 4-question), remaining specifics locked inline.

---

## Carry-ins endpoint design

| Option | Description | Selected |
|--------|-------------|----------|
| File only — `.planning/state/carry_ins.json` | Single JSON file with `{id, state, closed_at?, evidence_path?}` per OP-01..04 + INFRA-02. Backend reads on each request. Phase 11 writes when closing. Simplest, survives restart, easy to inspect. Matches existing `.planning/` artifact-as-state convention. | ✓ |
| Git tags only — `carry-in/closed/<id>` | Immutable closure audit trail. Backend runs `git tag --list 'carry-in/closed/*'` per request. No file to maintain. Downside: state read requires git in container; commit-bound closure is heavier ceremony. | |
| Both — file primary, tags as backup audit | File is read source; closing also writes git tag. Two-write places to keep in sync. More moving parts for Phase 11. | |

**User's choice:** File only (Recommended).
**Notes:** Locked the schema in D-10-02; endpoint owner = api-gateway (D-10-03); bind-mount the directory (not the single file) per WSL gotcha (D-10-05).

---

## 24h continuous-PASS window mechanics

| Option | Description | Selected |
|--------|-------------|----------|
| Persist in `carry_ins.json` `_state` key | `_state.first_all_pass_at` written by api-gateway each poll; ANY FAIL/UNKNOWN resets to null; UNKNOWN counts as reset (safer). Survives restart. | ✓ |
| In-memory only on api-gateway | Simpler — module-level dict. Restart loses progress, operator restarts the wait. Acceptable since LIVE flip should be deliberate. | |
| Append-only transition log `preflight_history.jsonl` | Every state change appended; READY computed by scanning recent rows. Full audit, but heavier reads + more complexity. | |

**User's choice:** Persist in `_state` (Recommended).
**Notes:** UNKNOWN explicitly treated as reset (D-10-08). Atomic file writes via temp + rename (D-10-07). Window seconds env-overridable for tests (D-10-09).

---

## Tile placement + visual layout

| Option | Description | Selected |
|--------|-------------|----------|
| Top of `/` (Dashboard.jsx) above KeyMetricsStrip | Full-width card. First thing operator sees. Highest visibility. Per-row detail visible. | ✓ |
| New dedicated `/preflight` route + nav entry | Focused page. Less main-dashboard clutter. Operator must navigate. | |
| Compact strip in StatusBar (header) | Always visible across all routes. Tight space — banner + count only; detail moves to a separate page. | |

**User's choice:** Top of `/` (Recommended).
**Notes:** Wrapped in `TileState` (D-10-14). Two react-query hooks at 5s cadence (D-10-15). Banner text/colors locked in D-10-13.

---

## Smoke test scope + CI workflow

| Option | Description | Selected |
|--------|-------------|----------|
| `tests/e2e/test_path_to_live_smoke.py` + new `.github/workflows/dashboard-smoke.yml` | pytest-playwright, Chromium-only, mirrors Phase 7 fixtures. New workflow keeps preflight smoke independent of integration lane. | ✓ |
| Add to existing `tests/integration/test_dashboard_smoke.py` | Reuse Phase 7 audit-driven walker. Lower setup cost. Downside: ROADMAP SC#4 expects separate path; file grows; failures couple to dashboard-audit lane. | |
| JS Playwright in `frontend/e2e/` with new `dashboard-smoke.yml` | Native frontend test. Downside: project has no JS Playwright infra; pytest-playwright already proven in Phase 7. | |

**User's choice:** `tests/e2e/` + new workflow (Recommended).
**Notes:** Required assertions itemised in D-10-18 (7 items). CI triggers on `pull_request` with paths filter + `workflow_dispatch`; no nightly cron yet (Phase 12 territory). Two grep gates added under `tests/integration/test_dashlive_grep_gates.py` (D-10-20).

---

## Claude's Discretion

User explicitly deferred mid-grain detail to Claude under the "make reasonable calls" override. The following were locked by Claude with rationale documented in CONTEXT.md and remain open to redirection if the planner finds friction:

- Carry-ins file schema details (`schema_version: 1`, `_state` ownership boundary).
- Endpoint response shape (D-10-04).
- Required-window seconds env-override mechanism (D-10-09).
- Atomic-rename concurrency model (D-10-10).
- UNKNOWN → DO_NOT_FLIP banner mapping (D-10-11).
- Per-row icon choices (`Check`, `X`, `HelpCircle`, `Circle`, `CheckCircle2`).
- Banner copy strings and ALMOST subtitle wording.
- Whether to add a row to `06-TILE-AUDIT.json` (planner's call).

## Deferred Ideas

Captured under `<deferred>` in CONTEXT.md. Highlights:

- Per-carry-in click-to-expand with evidence preview — Phase 12+.
- Telegram alert on READY → DO_NOT_FLIP transition — defer until first occurrence.
- WebSocket replacement for 5s poll — explicitly out (D-11 lock).
- Storing `_state` in PostgreSQL — overkill.
- "Force READY" operator override button — explicitly rejected (defeats the 24h safety property).
- Append-only banner-state history log — possible future audit feature.
- Nightly cron for `dashboard-smoke.yml` — Phase 12.
- Backporting tile to `06-TILE-AUDIT.json` — single-line optional add, not load-bearing.
