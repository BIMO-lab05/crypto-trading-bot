---
phase: 10-path-to-live-dashboard
plan: "02"
subsystem: frontend
tags:
  - frontend
  - react
  - tile
  - phase-10
  - dashlive

dependency_graph:
  requires:
    - 10-01  # carry-ins endpoint (GET /api/preflight/carry-ins) must exist for hooks to resolve
  provides:
    - PathToLiveTile React component (DASHLIVE-01 visibility surface)
    - useLiveReadiness hook (5s poll, preflight-live-readiness queryKey)
    - useCarryIns hook (5s poll, preflight-carry-ins queryKey, D-10-16 authoritative)
  affects:
    - frontend/src/components/Dashboard.jsx (PathToLiveTile prepended)
    - 10-03 smoke (data-testid contracts must match assertions)

tech_stack:
  added: []
  patterns:
    - react-query useQuery idiom (verbatim useSafetyState shape, D-10-15)
    - TileState wrapper with thresholdKey=default (D-10-14)
    - lucide-react icons: Check, X, HelpCircle, Circle, CheckCircle2
    - Tailwind locked tokens: bg-rose-700 / bg-amber-600 / bg-emerald-700 (banner)
    - Optional-chaining throughout for degraded-payload resilience (T-10-02-03)

key_files:
  created:
    - frontend/src/hooks/useLiveReadiness.js
    - frontend/src/hooks/useCarryIns.js
    - frontend/src/components/PathToLiveTile.jsx
  modified:
    - frontend/src/components/Dashboard.jsx

decisions:
  - D-10-04: Banner reads carryInsQuery.data.overall directly — no client-side recompute
  - D-10-12: PathToLiveTile prepended as first child of Dashboard wrapper, above KeyMetricsStrip
  - D-10-13: Locked banner tokens bg-rose-700/bg-amber-600/bg-emerald-700; chip tokens honoured
  - D-10-14: TileState thresholdKey="default" (60s stale threshold)
  - D-10-15: Both hooks at refetchInterval/staleTime=5000, retry=2, retryDelay=1000
  - D-10-16: useCarryIns authoritative for overall + window; useLiveReadiness fallback for checks only

metrics:
  duration: ~15 min
  completed: "2026-05-17T19:20:44Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 3
  files_modified: 1
---

# Phase 10 Plan 02: PathToLiveTile React Component Summary

**One-liner:** 5s-poll PathToLiveTile component with DO NOT FLIP/ALMOST/READY banner + 6 PREFLIGHT rows + 5 carry-in rows wired above KeyMetricsStrip via react-query + TileState wrapper.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create useLiveReadiness + useCarryIns hooks | 3863a62 | useLiveReadiness.js, useCarryIns.js |
| 2 | Create PathToLiveTile.jsx + wire into Dashboard.jsx | bc7948f | PathToLiveTile.jsx, Dashboard.jsx |

## What Was Built

### Task 1: Two react-query hooks

Both hooks copy the useSafetyState idiom verbatim (D-10-15):
- `useLiveReadiness`: queryKey `['preflight-live-readiness']`, path `/preflight/live-readiness`
- `useCarryIns`: queryKey `['preflight-carry-ins']`, path `/preflight/carry-ins`
- Both: `refetchInterval: 5000`, `staleTime: 5000`, `retry: 2`, `retryDelay: 1000`
- `useCarryIns` JSDoc documents D-10-16 authority rule explicitly ("authoritative source", "D-10-16")

### Task 2: PathToLiveTile component + Dashboard wire-in

**PathToLiveTile.jsx** (270 lines):
- Calls both hooks; wraps in `<TileState query={carryInsQuery} thresholdKey="default" title="Path to LIVE">`
- Banner: `carryInsQuery.data.overall` → `bg-rose-700` / `bg-amber-600` / `bg-emerald-700` via map (no client recompute, D-10-04). ALMOST state shows elapsed/required subtitle.
- PREFLIGHT checks: reads from `carryInsQuery.data.live_readiness?.checks` (authoritative per D-10-16); falls back to `liveReadinessQuery.data?.checks` only on degraded payload
- Carry-in rows: `carryInsQuery.data.carry_ins[]`, amber for open / emerald for closed
- 24h window footer: `fmtSeconds(elapsed) / fmtSeconds(required)` using plain Math.floor (no dayjs)
- All required `data-testid` contracts present: root, banner, per-check (`path-to-live-check-{name}`), per-carry-in (`path-to-live-carry-in-{id}`)
- XSS: all text via JSX interpolation, no raw-HTML injection props (T-10-02-02 mitigated)
- Error resilience: TileState handles isError; optional-chaining on all nested fields (T-10-02-03 mitigated)

**Dashboard.jsx** changes (2 lines only):
- Added `import PathToLiveTile from './PathToLiveTile'` at line 8
- Prepended `<PathToLiveTile />` before `<KeyMetricsStrip />` per D-10-12

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

One structural adjustment (not a deviation):

**Default export style**: plan verify `/export default PathToLive/` requires the string "export default PathToLive" to appear literally. Using `export default function PathToLiveTile()` causes the regex to fail because "function" sits between "default" and "PathToLive". Fixed by separating to `function PathToLiveTile() { ... }` + `export default PathToLiveTile` at end of file (standard React pattern).

## Known Stubs

None — all data paths are wired to live queries. The component renders empty arrays gracefully when hooks are loading or the endpoint hasn't shipped yet (10-01 carries the endpoint).

## Threat Flags

No new network endpoints, auth paths, or file access patterns introduced. The tile is a read-only render surface consuming the carry-ins and live-readiness endpoints defined in Plan 10-01. All threats from the plan's threat register are mitigated or accepted as documented:

| Threat | Disposition | Notes |
|--------|-------------|-------|
| T-10-02-02 XSS | mitigated | All text via JSX interpolation |
| T-10-02-03 tile crash on null | mitigated | TileState + optional-chaining throughout |
| T-10-02-04 client recomputes overall | mitigated | Reads carryInsQuery.data.overall directly |
| T-10-02-01 fabricated READY | accept | Tile is informational; PREFLIGHT-02 is the control plane |
| T-10-02-05 repudiation | accept | TileState shows evaluated_at timestamp |

## Self-Check

Files exist:
- FOUND: frontend/src/hooks/useLiveReadiness.js
- FOUND: frontend/src/hooks/useCarryIns.js
- FOUND: frontend/src/components/PathToLiveTile.jsx

Commits exist:
- FOUND: 3863a62 (hooks)
- FOUND: bc7948f (tile + dashboard)

Task 1 verify: OK
Task 2 verify: OK

## Self-Check: PASSED
