---
phase: 07-tournament-view-smoke-test
plan: 02
subsystem: frontend
tags: [tournament, dashboard, frontend, react-query, dash-04]
requires:
  - Plan 01 gateway routes (GET /api/tournament/snapshots[/{id}]) — shipped commit a8dd788
provides:
  - tournamentAPI named export on frontend/src/services/api.js
  - useTournamentList() React Query hook
  - useTournamentSnapshot(tournamentId) React Query hook
affects:
  - Wave 3 (TournamentDashboard page + TournamentLeaderboard component) imports tournamentAPI + both hooks verbatim
tech-stack:
  added: []
  patterns:
    - "React Query single-fetch / cold-data semantics (staleTime: Infinity, no refetchInterval, manual refetch)"
    - "axios response interceptor unwrap — callers see body directly, no .data.data nesting"
    - "enabled-gated query for falsy selector state (snapshot hook)"
    - "D-23 rationale embedded in JSDoc to defend against future 'fix this to 5s poll' pressure"
key-files:
  created:
    - frontend/src/hooks/useTournamentList.js
    - frontend/src/hooks/useTournamentSnapshot.js
  modified:
    - frontend/src/services/api.js
decisions:
  - "D-23 implemented: useTournamentList + useTournamentSnapshot use staleTime: Infinity + no refetchInterval; page-level refresh button (Wave 3) will call query.refetch() manually."
  - "D-24 implemented: no new global state — tournament data lives in React Query cache keyed ['tournament-list'] / ['tournament-snapshot', id]."
  - "D-25 implemented: tournamentAPI added alongside existing portfolioAPI / tradingAPI groups in api.js (extension, not replacement)."
  - "D-23 citation embedded in both hook files (JSDoc block + inline comment on staleTime line) so the rationale travels with the code."
metrics:
  duration: ~5 minutes
  completed: 2026-05-14
  tasks: 2
  files: 3
  commits: 2
  tests_added: 0
  tests_passing: n/a
---

# Phase 7 Plan 02: Frontend Tournament Data Layer — Summary

## One-liner
Frontend data plumbing for the Tournament view: `tournamentAPI` extension on `api.js` (`listSnapshots()` + `getSnapshot(id)`) plus two React Query hooks (`useTournamentList`, `useTournamentSnapshot`) wired with cold-batch semantics (staleTime: Infinity, no auto-poll, manual refetch, snapshot hook gated on truthy id) per D-23 / D-24 / D-25.

## Hook Signatures

```javascript
// frontend/src/hooks/useTournamentList.js
export function useTournamentList()
// returns React Query result whose data is:
//   { success: true, count: <int>, tournaments: [ { tournament_id, exported_at,
//     n_rows, n_success, n_failed, architectures: [...], symbols: [...] } ] }

// frontend/src/hooks/useTournamentSnapshot.js
export function useTournamentSnapshot(tournamentId)
// returns React Query result whose data is:
//   { success: true, snapshot: <object>, ensemble: <object|null>, significance: <object|null> }
// Gated: query is disabled while `tournamentId` is falsy.
```

Both hooks default-export the named function (mirrors the `useSafetyState` shape).

## React Query Configuration

| Option | useTournamentList | useTournamentSnapshot | Rationale |
|--------|-------------------|------------------------|-----------|
| `queryKey` | `['tournament-list']` | `['tournament-snapshot', tournamentId]` | Stable, cache-friendly, predictable invalidation. |
| `staleTime` | `Infinity` | `Infinity` | D-23: tournaments are cold batches; cache stays fresh until manual refetch. |
| `refetchOnWindowFocus` | `false` | `false` | D-23: tab-focus is not a tournament event. |
| `refetchOnMount` | `false` | `false` | D-23: page navigations re-using cached data must not silently refetch. |
| `refetchInterval` | (absent) | (absent) | D-23: no 5s poll cadence — the dashboard-wide default is deliberately inverted here. |
| `enabled` | (always) | `!!tournamentId` | Snapshot hook does not fire before the parent has a selector state. |
| `retry` | `2` | `2` | Match `useSafetyState` resilience. |
| `retryDelay` | `1000` | `1000` | Same. |

## Manual-Refetch Model (No Auto-Poll)

The tournament view bucks the dashboard-wide 5-second poll. Tournaments do not update mid-session — they are written once by `tournament run` and stay static. The cached query body is reused across renders and route navigations until the operator explicitly clicks a refresh control.

**Refresh flow (Wave 3 wires this):**
1. `TournamentDashboard.jsx` calls `useTournamentList()` once; on mount, the query fires and caches indefinitely.
2. Operator picks a tournament from the dropdown; `useTournamentSnapshot(selectedId)` fires once for that id.
3. Switching back to a previously viewed tournament returns from cache instantly (`staleTime: Infinity` + key change → cache hit).
4. The sticky header's refresh button calls `query.refetch()` on whichever query the operator wants fresh — never on a timer.

A code-comment block in both hook files cites **D-23** explicitly (both JSDoc and inline on the `staleTime` line). Two `grep`-verified hits per file ensure the citation survives future formatter passes.

## Response-Body Plumbing (No Double-Unwrap)

`frontend/src/services/api.js:34` registers `api.interceptors.response.use((response) => response.data, ...)`. The resolved value of `api.get(...)` therefore **IS** the response body; there is no `.data.data` nesting in the hook layer or in downstream components. JSDoc in both hooks states this explicitly so Wave 3 consumers don't reach for a non-existent `.data` wrapper.

## `tournamentAPI` Surface

Added at the end of `frontend/src/services/api.js` (after `autoTraderAPI`), pre-`export default api`:

```javascript
// Tournament endpoints (Phase 7, DASH-04). Gateway reads committed snapshot files from a RO bind-mount per CONTEXT.md D-01.
// Path shape is `/tournament/snapshots` (NO `/v1/` prefix per ADR-007). The shared `api` axios instance has
// baseURL '/api' and a response interceptor (line 34) that strips `.data`, so callers see the body directly.
export const tournamentAPI = {
  // List all committed snapshots (gateway reads ./services/tournament-harness/data/snapshots/*.json)
  listSnapshots: () => api.get('/tournament/snapshots'),
  // Merged snapshot + ensemble + significance for one tournament
  getSnapshot: (tournamentId) => api.get(`/tournament/snapshots/${tournamentId}`),
}
```

No existing exports were modified; the axios instance, interceptors, and other API groupings (portfolioAPI, tradingAPI, mlAPI, sentimentAPI, autoTraderAPI, etc.) are untouched.

## ESLint Status

`./node_modules/.bin/eslint src/services/api.js src/hooks/useTournamentList.js src/hooks/useTournamentSnapshot.js` exits **0** under the project's pinned config (`eslint ^8.55`, `eslint-plugin-react`, `eslint-plugin-react-hooks`, `.eslintrc.json` at `frontend/`).

Worktree note: `frontend/node_modules/` does not exist on a fresh worktree clone, so a one-shot `npm install --no-save eslint@^8.55.0 eslint-plugin-react@^7.33.2 eslint-plugin-react-hooks@^4.6.0` was run inside the worktree to satisfy the plan's lint gate. The install directory is gitignored (line 181 of `.gitignore`) and not part of any commit.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Comment phrasing tripped the acceptance grep**
- **Found during:** Task 2 acceptance verification
- **Issue:** Initial JSDoc copied the verbatim phrasing from the plan spec — `\`staleTime: Infinity\`, no \`refetchInterval\`, no \`refetchOnWindowFocus\`, no \`refetchOnMount\`` — which is helpful prose but makes the plan's `grep -nE 'refetchInterval|setInterval'` "must return no matches" check fail (matched the comment) and the `grep -nE 'staleTime: Infinity' ... matches 1 line` check return 2 lines per file.
- **Fix:** Rewrote the JSDoc paragraph in plain English ("the cache is held forever, window-focus does not trigger refetch, mounting does not trigger refetch, and no recurring interval is wired") so the prohibition is documented without re-using the literal option names. Behavior unchanged; rationale still travels with the code.
- **Files modified:** `frontend/src/hooks/useTournamentList.js`, `frontend/src/hooks/useTournamentSnapshot.js`
- **Commit:** folded into `a8be35d` (single commit for the hook pair).

### Logged as Deferred

None — all in-scope acceptance criteria pass after the JSDoc rewrite above.

## Threat Surface Scan

No new attack surface introduced. Pure frontend data plumbing; both endpoints already declared in Plan 01's threat register (T-07-09 information disclosure, T-07-10 client-side cache tampering, both accepted per Phase 6 D-09). React Query cache lives per-tab in browser memory; no `localStorage` / `sessionStorage` writes. No secrets touched. No PII fields surfaced. No new network egress.

## Self-Check: PASSED
- Files exist:
  - `frontend/src/services/api.js` (modified, +10 LOC)
  - `frontend/src/hooks/useTournamentList.js` (new, 54 LOC)
  - `frontend/src/hooks/useTournamentSnapshot.js` (new, 50 LOC)
- Commits on branch `worktree-agent-a529d9c8eeb5786b9`:
  - `a94b205` feat(07-02): extend api.js with tournamentAPI for snapshot endpoints
  - `a8be35d` feat(07-02): add tournament React Query hooks with cold-data semantics
- Verification block (5 checks): all pass
  - tournamentAPI exported at line 219 of api.js
  - both hook files present
  - `staleTime: Infinity` appears once per hook file (2 lines total)
  - `refetchInterval|setInterval` returns no matches in either hook file
  - `eslint` exits 0 on all three files
- Success criteria from orchestrator prompt: 7/7 satisfied
