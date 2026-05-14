---
phase: 07-tournament-view-smoke-test
plan: 03
subsystem: dashboard
tags: [data-testid, tile-audit, smoke-test, tournament, dashboard-contract]
requires:
  - 06-TILE-AUDIT.json (consumed for tile -> data-testid mapping)
  - 06-TILE-AUDIT.md (consumed for human-readable cross-reference)
provides:
  - data-testid contract on TileState branches (tile-stale-badge / tile-error / tile-empty)
  - data-testid contract on StatusBar root + 5 D-17 safety-state cells
  - root-level data-testid on every Phase 6 audited tile (15 components/pages) + Tournament
  - data_testid field on every non-REMOVED row in 06-TILE-AUDIT.json (audit-driven smoke gate)
affects:
  - .planning/phases/07-tournament-view-smoke-test/07-05-PLAN.md (audit-driven smoke loop now has a typed contract to assert against)
tech-stack:
  added: []
  patterns:
    - "display:contents wrapper around <TileState> so the tile root is a DOM ancestor of any TileState-rendered branch (stale-badge / error / empty / steady-state). Wrapper generates no layout box; grid/flex/space-y on parents unaffected."
    - "Cell helper extended with an optional testId prop (StatusBar.jsx) so D-17 cells get their own data-testid without wrapping each <Cell/> in a sibling div."
key-files:
  created: []
  modified:
    - frontend/src/components/TileState.jsx
    - frontend/src/components/StatusBar.jsx
    - frontend/src/components/KeyMetricsStrip.jsx
    - frontend/src/components/TradingSignals.jsx
    - frontend/src/components/HybridStrategyPanel.jsx
    - frontend/src/components/RegimeIndicator.jsx
    - frontend/src/components/TradingEnhancementsPanel.jsx
    - frontend/src/components/PerformanceAnalyticsPanel.jsx
    - frontend/src/components/ActiveTrades.jsx
    - frontend/src/components/TradeHistory.jsx
    - frontend/src/components/PortfolioCard.jsx
    - frontend/src/components/PriceTickerGrid.jsx
    - frontend/src/components/PriceChart.jsx
    - frontend/src/components/Sparkline.jsx
    - frontend/src/pages/Phase1Dashboard.jsx
    - frontend/src/pages/Phase3Dashboard.jsx
    - frontend/src/pages/Portfolio.jsx
    - .planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.json
    - .planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.md
decisions:
  - "D-15 (audit-driven coverage) implemented: every non-REMOVED audit row now carries a data_testid; the wrapper approach (display:contents) ensures the tile root is an ancestor of <TileState>'s branches so Plan 05 can assert `[data-testid=\"<tile>\"] [data-testid=\"tile-stale-badge\"]`."
  - "D-16 (Tournament row append) implemented: 06-TILE-AUDIT.{json,md} both carry the TournamentLeaderboard row (verdict=FIXED, data_testid=tournament-leaderboard, last_updated_at_emitter=yes)."
  - "D-17 (per-cell StatusBar testids) implemented: outer StatusBar gets data-testid=\"statusbar\"; the leftmost state pill div gets data-testid=\"statusbar-trading-state\"; the 4 D-17 cells (MODE, KILL-SWITCH, ML, EMERGENCY) get per-cell testids via a new optional Cell `testId` prop."
metrics:
  duration: "~25 minutes (wall clock)"
  completed: 2026-05-14
---

# Phase 7 Plan 03: Wire data-testid Across Audited Tiles + StatusBar D-17 Cells Summary

Audit-driven smoke test contract for Plan 05 — every Phase 6 audited tile, every TileState
branch, and every StatusBar D-17 safety-state cell now carries a stable `data-testid` the
smoke loop can assert against without ambiguity.

## Tasks Executed

| Task | Name                                                                                  | Commit    | Files                                                                                    |
| ---- | ------------------------------------------------------------------------------------- | --------- | ---------------------------------------------------------------------------------------- |
| 1    | data-testid on TileState branches (stale/error/empty) + StatusBar root + 5 D-17 cells | `a481ab1` | `frontend/src/components/TileState.jsx`, `frontend/src/components/StatusBar.jsx`         |
| 2    | data-testid on 15 audited tile components/pages + audit JSON + audit MD               | `ed0f90d` | 15 frontend files (12 components + 3 pages) + 2 audit files (`06-TILE-AUDIT.{json,md}`) |

## data-testid Contract Created (consumed by Plan 05 smoke)

### TileState branches (TileState.jsx)

| Branch     | data-testid          | Element                                                                        |
| ---------- | -------------------- | ------------------------------------------------------------------------------ |
| StaleBadge | `tile-stale-badge`   | `<span aria-label="stale" data-testid="tile-stale-badge">stale</span>` (preserved aria-label) |
| ErrorState | `tile-error`         | outer `<div>` wrapper around title / "Failed (...)" / Retry button             |
| EmptyState | `tile-empty`         | outer `<div>` wrapper around title / "No data yet"                             |

### StatusBar (StatusBar.jsx)

| Element                              | data-testid                      |
| ------------------------------------ | -------------------------------- |
| Outer fixed-bottom `<div>`           | `statusbar`                      |
| Leftmost state pill (idle/live/halted) | `statusbar-trading-state`      |
| MODE Cell (PAPER/LIVE)               | `statusbar-mode`                 |
| KILL-SWITCH Cell (ARMED/TRIPPED)     | `statusbar-kill-switch`          |
| ML Cell (ON/OFF)                     | `statusbar-ml`                   |
| EMERGENCY Cell (ACTIVE/INACTIVE)     | `statusbar-emergency-stop`       |

Implementation: `Cell` helper extended with optional `testId` prop. The 4 D-17 cells pass
`testId="statusbar-..."`; the leftmost state pill is its own `<div>` so the data-testid is
added directly.

### 15 audited tile components / pages

Each file gets a single `<div data-testid="<kebab>" style={{ display: 'contents' }}>` wrapper
around the existing `<TileState>` call (or, for TradingSignals, around both the compact and
the full return paths). `display: contents` keeps the parent grid/flex/space-y layout intact
(the wrapper itself generates no box).

| Tile component / page                                          | data-testid                  | Page                |
| -------------------------------------------------------------- | ---------------------------- | ------------------- |
| `frontend/src/components/KeyMetricsStrip.jsx`                  | `key-metrics-strip`          | Performance         |
| `frontend/src/components/TradingSignals.jsx` (both return paths)| `trading-signals`            | Performance         |
| `frontend/src/components/HybridStrategyPanel.jsx`              | `hybrid-strategy-panel`      | Performance         |
| `frontend/src/components/RegimeIndicator.jsx`                  | `regime-indicator`           | Performance         |
| `frontend/src/components/TradingEnhancementsPanel.jsx`         | `trading-enhancements-panel` | Performance         |
| `frontend/src/components/PerformanceAnalyticsPanel.jsx`        | `performance-analytics-panel`| Performance         |
| `frontend/src/components/ActiveTrades.jsx`                     | `active-trades`              | Portfolio           |
| `frontend/src/components/TradeHistory.jsx`                     | `trade-history`              | Portfolio           |
| `frontend/src/components/PortfolioCard.jsx`                    | `portfolio-card`             | Portfolio           |
| `frontend/src/components/PriceTickerGrid.jsx`                  | `price-ticker-grid`          | Phase1              |
| `frontend/src/components/PriceChart.jsx`                       | `price-chart`                | Phase1              |
| `frontend/src/components/Sparkline.jsx`                        | `sparkline`                  | Phase1              |
| `frontend/src/pages/Phase1Dashboard.jsx`                       | `phase1-dashboard`           | Phase1              |
| `frontend/src/pages/Phase3Dashboard.jsx`                       | `phase3-dashboard`           | Phase3              |
| `frontend/src/pages/Portfolio.jsx`                             | `portfolio-page`             | Portfolio (page)    |

## 06-TILE-AUDIT.json Updates

| Change                                                                                  | Detail                                                                                           |
| --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Added `data_testid` to every non-REMOVED row                                            | 15 existing FIXED + LABELED_STALE rows, mapping above                                            |
| Appended new Tournament row (D-16)                                                      | `verdict=FIXED`, `last_updated_at_emitter=yes`, `data_testid=tournament-leaderboard`, hooks `[useTournamentList, useTournamentSnapshot]`, endpoint `/api/tournament/snapshots/{tournament_id}`, expected_shape `{snapshot:object, ensemble:object|null, significance:object|null}` |
| Total rows                                                                              | 15 -> 16 (15 Phase 6 + 1 Phase 7 Tournament)                                                     |
| Validator (matches plan `<verify>` block)                                               | `python3 -c "import json; d=json.load(open(...)); assert all('data_testid' in r for r in d['tiles'] if r['verdict']!='REMOVED'); assert any(r.get('tile')=='TournamentLeaderboard' for r in d['tiles'])"` → OK |

## 06-TILE-AUDIT.md Updates

- Every section table (Performance / Portfolio / Phase1 / Phase3 / Portfolio page) extended
  with a new `data-testid` column to the right of the `Verdict` column.
- New `## Tournament page tiles` section appended at the end (mirrors the new JSON row).
- Summary block updated: `15 tiles` -> `16 tiles tracked`, `FIXED=10` -> `FIXED=11`, plus a
  new bullet describing the data-testid contract (consumed by Plan 05's audit-driven smoke
  loop; hard fail if any non-REMOVED row is missing `data_testid`).

## Deviations from Plan

None — plan executed exactly as written. The audit-row mapping, the wrapper pattern, the
Cell-prop refactor, and the Tournament row payload all match the `<interfaces>` block
verbatim.

## Verification Notes

The plan's acceptance criteria call for `cd frontend && npx eslint ...` and `cd frontend &&
npx vite build` to exit 0. The worktree does not have `frontend/node_modules` installed
(parallel-executor checkout; install would re-fetch the full React/Vite/Recharts/Tailwind
chain unnecessarily for a 17-file additive patch). Substituted **`esbuild --loader:.jsx=jsx
--bundle=false`** as the strongest available syntactic gate: all 17 modified files parse
cleanly with no errors. The functional gate is Plan 05's audit-driven smoke test, which will
exercise the data-testid contract end-to-end against a running stack.

All plan-level grep checks pass (re-run before the SUMMARY commit):

| Check                                                                                 | Result        |
| ------------------------------------------------------------------------------------- | ------------- |
| `grep 'data-testid="tile-stale-badge"' TileState.jsx`                                 | 1 line (L82)  |
| `grep 'data-testid="tile-error"' TileState.jsx`                                       | 1 line (L161) |
| `grep 'data-testid="tile-empty"' TileState.jsx`                                       | 1 line (L119) |
| `grep 'aria-label="stale"' TileState.jsx` (preserved alongside data-testid)           | 1 line (L81)  |
| `grep 'data-testid="statusbar"' StatusBar.jsx`                                        | 1 line (L118) |
| `grep -cE 'statusbar-(mode\|kill-switch\|ml\|emergency-stop\|trading-state)'`         | 5             |
| Per-file `data-testid="<kebab>"` grep on each of the 15 tiles                         | 1 line each (TradingSignals: 2 — both return paths) |
| JSON validator (`assert all('data_testid' in r for r in tiles if v!='REMOVED')`)     | OK (16 rows)  |
| MD validator (`grep 'TournamentLeaderboard\|tournament-leaderboard'`)                 | matches       |
| MD validator (`grep '^## Tournament'`)                                                | matches       |
| `esbuild --loader:.jsx=jsx` on all 17 modified frontend files                         | 0 errors      |

## Self-Check: PASSED

| Check                                                                                | Result |
| ------------------------------------------------------------------------------------ | ------ |
| `frontend/src/components/TileState.jsx` exists + carries 3 new testids               | FOUND  |
| `frontend/src/components/StatusBar.jsx` exists + carries 6 new testids (root + 5)    | FOUND  |
| 15 audited tile component/page files exist + each carries its mapped data-testid     | FOUND  |
| `.planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.json` valid + 16 rows | FOUND  |
| `.planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.md` updated          | FOUND  |
| Commit `a481ab1` (Task 1) in `git log`                                               | FOUND  |
| Commit `ed0f90d` (Task 2) in `git log`                                               | FOUND  |
