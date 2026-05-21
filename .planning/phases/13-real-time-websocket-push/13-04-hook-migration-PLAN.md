---
phase: 13-real-time-websocket-push
plan: 04
type: execute
wave: 2
depends_on:
  - 13-02
  - 13-03
files_modified:
  - services/api-gateway/app/main.py
  - services/api-gateway/app/ws/snapshot_poller.py
  - services/api-gateway/tests/unit/test_dashboard_snapshot_endpoint.py
  - frontend/src/hooks/useSafetyState.js
  - frontend/src/hooks/useLiveReadiness.js
  - frontend/src/hooks/useCarryIns.js
  - frontend/src/hooks/useDashboardSnapshot.js
  - frontend/src/hooks/__tests__/useSafetyState.test.js
  - frontend/src/hooks/__tests__/useLiveReadiness.test.js
  - frontend/src/hooks/__tests__/useCarryIns.test.js
  - frontend/src/hooks/__tests__/useDashboardSnapshot.test.js
autonomous: true
requirements:
  - WS-03
tags:
  - websocket
  - frontend
  - api-gateway

must_haves:
  truths:
    - "useSafetyState, useLiveReadiness, useCarryIns, useDashboardSnapshot consume useWsSubscription(channel) for their primary fetch path"
    - "None of the four hooks call setInterval — the only setTimeout calls present are the REST fallback re-arm (allowlisted with sentinel comment)"
    - "Component value-contract is unchanged: each hook still returns an object with at least { data, isLoading, isError, isSuccess } so existing consumers (Dashboard.jsx, PathToLiveTile.jsx, StatusBar.jsx, KeyMetricsStrip via downstream wiring) render unchanged"
    - "When useWsSubscription reports restFallbackActive: true, each hook arms a 5s REST poll AND reuses React Query's cache so component re-renders work as before; when restFallbackActive flips back to false, the REST poll is cancelled within one push cycle"
    - "GET /api/dashboard/snapshot exists on api-gateway and returns a non-empty global snapshot dict (no symbol param) consumed by the dashboard-snapshot channel"
  artifacts:
    - path: "services/api-gateway/app/main.py"
      provides: "Existing safety-state / live-readiness handlers UNTOUCHED; new /api/dashboard/snapshot global aggregator endpoint added"
      contains: "/api/dashboard/snapshot"
    - path: "frontend/src/hooks/useDashboardSnapshot.js"
      provides: "New hook consuming /api/dashboard/snapshot via useWsSubscription"
      min_lines: 40
    - path: "frontend/src/hooks/useSafetyState.js"
      provides: "Migrated to useWsSubscription('safety-state', '/config/safety-state') with REST fallback re-arm"
      min_lines: 30
  key_links:
    - from: "frontend/src/hooks/useSafetyState.js"
      to: "frontend/src/hooks/useWsSubscription.ts"
      via: "import { useWsSubscription } from './useWsSubscription'"
      pattern: "useWsSubscription"
    - from: "services/api-gateway/app/main.py"
      to: "services/api-gateway/app/ws/snapshot_poller.py"
      via: "SnapshotPoller._fetch_dashboard_snapshot calls the new handler"
      pattern: "_fetch_dashboard_snapshot"
---

<objective>
Migrate the four production hooks to the WS subscription layer (Plan 13-02 server + Plan 13-03 client) and add the missing `/api/dashboard/snapshot` global aggregator endpoint + `useDashboardSnapshot.js` hook. Each hook keeps a REST fallback re-arm that fires `setInterval(5000)` ONLY when useWsSubscription reports `restFallbackActive: true` — sentinel comment `// allowlist:rest-fallback-rearm` flags these sites so the CI grep gate (Plan 13-05) tolerates them.

Why a new endpoint: phase goal lists four channels including `dashboard-snapshot`, but no production hook or endpoint exists today. `/api/dashboard/{symbol}` is per-symbol aggregation, not the global snapshot the WS channel needs. This plan creates `/api/dashboard/snapshot` (no params) composing portfolio + trading-status + performance into one payload, and the matching hook.

CRITICAL: component value-contract is unchanged. `Dashboard.jsx`, `PathToLiveTile.jsx`, `StatusBar.jsx`, `KeyMetricsStrip` import the existing hook names; the hook return shape must continue to support `{ data, isLoading, isError, isSuccess }` (the keys those components destructure). React Query is still used in the fallback path so cache shape stays identical.

Output:
- 1 new api-gateway endpoint + handler test
- 1 new frontend hook (useDashboardSnapshot.js)
- 3 migrated frontend hooks (useSafetyState.js, useLiveReadiness.js, useCarryIns.js)
- 4 contract tests proving the value-shape is unchanged
- Update SnapshotPoller's _fetch_dashboard_snapshot to call the new endpoint (replaces the placeholder from Plan 13-02)

Note: 4 tasks instead of the standard 2-3. Task 4 is intentionally a deploy + observe step (separated per the verify-stack project skill — "never declare working on HTTP 200 alone"). Tasks 1-3 are code; Task 4 is end-to-end browser DevTools observation of the integrated WS pipeline.
</objective>

<execution_context>
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/workflows/execute-plan.md
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/REQUIREMENTS.md
@./CLAUDE.md

@.planning/phases/13-real-time-websocket-push/13-02-SUMMARY.md
@.planning/phases/13-real-time-websocket-push/13-03-SUMMARY.md

@services/api-gateway/app/main.py
@services/api-gateway/app/ws/snapshot_poller.py
@services/api-gateway/app/ws/channels.py

@frontend/src/hooks/useSafetyState.js
@frontend/src/hooks/useLiveReadiness.js
@frontend/src/hooks/useCarryIns.js
@frontend/src/lib/wsClient.ts
@frontend/src/hooks/useWsSubscription.ts
@frontend/src/components/Dashboard.jsx
@frontend/src/components/PathToLiveTile.jsx
@frontend/src/components/StatusBar.jsx
@frontend/src/components/KeyMetricsStrip.jsx

<interfaces>
<!-- Existing hook return shapes. Migration must preserve these keys. -->

useSafetyState (current):
```js
// Returns react-query result: { data, isLoading, isFetching, isError, isSuccess, error, refetch }
// data shape (from /api/config/safety-state):
{
  trading_mode: "PAPER" | "LIVE",
  paper_trading_mode: boolean,
  auto_trading_enabled: boolean,
  emergency_stop: { active: boolean, mtime: string|null },
  ml_predictions_enabled: boolean,
  sentiment_analysis_enabled: boolean,
  kill_switch: { daily_loss_armed: boolean, daily_pnl_pct: number, tripped: boolean },
  last_updated_at: string
}
```

useLiveReadiness: data shape per /api/preflight/live-readiness (six checks: cap, paper_mode, trading_mode, ack, emergency_stop, dsr_evidence)

useCarryIns: data shape per /api/preflight/carry-ins (carry_ins[], window, overall, live_readiness embedded snapshot)

useDashboardSnapshot (NEW — must be designed):
- Must NOT conflict with existing per-symbol /api/dashboard/{symbol}
- Should be a global snapshot — aggregates portfolio balance + trading-status + recent perf metrics into one payload
- Consumers will use it on subsequent UI work; for this plan, no existing component consumes it — but the hook + endpoint must exist so the WS channel has data flowing
- Proposed shape (lock during execution if needed):
  ```json
  {
    "schema_version": 1,
    "evaluated_at": "<ISO>",
    "portfolio": { ... }, // from portfolio-manager /api/v1/portfolio/balance
    "trading_status": { ... }, // from trading-engine /api/v1/trading/status (existing proxy at main.py:1041)
    "performance": { ... }  // from trading-engine /api/v1/performance
  }
  ```

REST fallback contract (each migrated hook):
- When useWsSubscription returns `{ restFallbackActive: true }`, arm a setInterval(REST_FETCH, 5000) AND mark it with the allowlist sentinel comment
- When restFallbackActive flips back to false, clear the interval within one push cycle
- React Query cache key remains the existing one (`['safety-state']`, `['preflight-live-readiness']`, etc.) — components consuming via useQuery on those keys remain unaffected
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: /api/dashboard/snapshot endpoint + SnapshotPoller wiring</name>
  <files>services/api-gateway/app/main.py, services/api-gateway/app/ws/snapshot_poller.py, services/api-gateway/tests/unit/test_dashboard_snapshot_endpoint.py</files>
  <read_first>
    - services/api-gateway/app/main.py:1598-1660 (existing portfolio endpoints)
    - services/api-gateway/app/main.py:1039-1047 (existing get_trading_status)
    - services/api-gateway/app/main.py:1393-1400 (existing get_trading_performance)
    - services/api-gateway/app/main.py:2257-2312 (existing per-symbol /api/dashboard/{symbol} for comparison — the new endpoint must NOT collide with this route)
    - services/api-gateway/app/ws/snapshot_poller.py (the placeholder _fetch_dashboard_snapshot from Plan 13-02)
  </read_first>
  <behavior>
    Add `GET /api/dashboard/snapshot` to services/api-gateway/app/main.py (place it BEFORE the per-symbol `/api/dashboard/{symbol}` route so path-matching prefers the literal "snapshot" over the symbol placeholder — confirm FastAPI route ordering).

    Handler behavior:
    - Async function `async def get_dashboard_snapshot() -> dict`
    - Fans out 3 parallel proxy calls via service_proxy: portfolio-manager `/api/v1/portfolio/balance`, trading-engine `/api/v1/trading/status`, trading-engine `/api/v1/performance`
    - Aggregates into `{schema_version: 1, evaluated_at: ISO, portfolio: ..., trading_status: ..., performance: ...}`
    - Graceful degradation: any failing leg returns null for that key with no 500 (same pattern as existing safety-state handler at main.py:1093-1107). Never raises 500 for downstream-unreachable; this matches the unauthenticated read-only-disclosure pattern used by Phase 6/8/10 dashboard endpoints.
    - Unauthenticated (D-09 carryforward — read-only operational metadata, no balances mutation).

    Update SnapshotPoller._fetch_dashboard_snapshot (in services/api-gateway/app/ws/snapshot_poller.py) to call the new handler in-process — same pattern as the other 3 channels.

    Tests (test_dashboard_snapshot_endpoint.py):
    - 200 OK with valid shape when all 3 downstreams succeed (mock service_proxy.proxy_request to return canned responses)
    - 200 OK with null portfolio when portfolio leg raises (degraded payload, NOT 500)
    - schema_version is always 1
    - evaluated_at is a valid ISO-8601 string
  </behavior>
  <action>
    Edit services/api-gateway/app/main.py to add the handler. Insert it AFTER `/api/preflight/carry-ins` (around line 1245) and BEFORE the `/api/tournament/snapshots` block so it is grouped with other Phase 8/10/13 read-only dashboard endpoints. Use the same `proxy_request` pattern + `_parse(resp)` helper used by `/api/dashboard/{symbol}` (line 2284).
    Edit services/api-gateway/app/ws/snapshot_poller.py — replace the placeholder `_fetch_dashboard_snapshot` with `return await get_dashboard_snapshot()` (in-process call). Keep the LATE import pattern from Plan 13-02 to avoid circular imports.
    Create tests/unit/test_dashboard_snapshot_endpoint.py — use the standard test_client fixture + monkeypatch on get_proxy().
    Run tests inside the container: container has fastapi 0.109; host has 0.136 (project memory).
  </action>
  <verify>
    <automated>docker exec crypto-bot-api-gateway pytest services/api-gateway/tests/unit/test_dashboard_snapshot_endpoint.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "/api/dashboard/snapshot" services/api-gateway/app/main.py` returns >=1 hit at a line LESS THAN 2257 (the per-symbol route line)
    - `curl -sf http://localhost:8000/api/dashboard/snapshot | python -m json.tool` (after Task 5 deploy) returns valid JSON with keys `schema_version`, `evaluated_at`, `portfolio`, `trading_status`, `performance`
    - pytest reports >=4 tests passed
    - `grep -n "_fetch_dashboard_snapshot" services/api-gateway/app/ws/snapshot_poller.py` shows it calls `get_dashboard_snapshot` (not the placeholder)
  </acceptance_criteria>
  <done>New global snapshot endpoint live; SnapshotPoller calls it; tests green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Migrate useSafetyState, useLiveReadiness, useCarryIns to useWsSubscription</name>
  <files>frontend/src/hooks/useSafetyState.js, frontend/src/hooks/useLiveReadiness.js, frontend/src/hooks/useCarryIns.js, frontend/src/hooks/__tests__/useSafetyState.test.js, frontend/src/hooks/__tests__/useLiveReadiness.test.js, frontend/src/hooks/__tests__/useCarryIns.test.js</files>
  <read_first>
    - frontend/src/hooks/useSafetyState.js (current 5s setInterval poll — being replaced)
    - frontend/src/hooks/useLiveReadiness.js (current 5s setInterval poll — being replaced)
    - frontend/src/hooks/useCarryIns.js (current 5s setInterval poll — being replaced)
    - frontend/src/hooks/useWsSubscription.ts (Plan 13-03 — the new hook these three will consume)
    - frontend/src/components/StatusBar.jsx (consumer of useSafetyState — confirm destructure shape)
    - frontend/src/components/PathToLiveTile.jsx (consumer of useLiveReadiness + useCarryIns — confirm destructure shape)
    - frontend/src/components/App.jsx (also consumes useSafetyState — confirm destructure shape)
  </read_first>
  <behavior>
    For each of the three hooks, refactor to:
    1. Call `useWsSubscription(channel, restPath)` with the appropriate channel and existing REST path
    2. Wrap the result inside a useQuery() result-shaped object so consumers see the SAME interface:
       ```js
       export function useSafetyState() {
         const ws = useWsSubscription('safety-state', '/config/safety-state')
         // REST fallback re-arm:
         const restQuery = useQuery({
           queryKey: ['safety-state'],
           queryFn: async () => api.get('/config/safety-state'),
           enabled: ws.restFallbackActive,
           refetchInterval: ws.restFallbackActive ? 5000 : false,  // allowlist:rest-fallback-rearm
           staleTime: 5000,
         })
         // Prefer WS data when fresh; fall back to REST query data otherwise.
         const data = ws.data ?? restQuery.data
         return {
           data,
           isLoading: !data,
           isFetching: ws.restFallbackActive ? restQuery.isFetching : false,
           isError: !!ws.error || restQuery.isError,
           isSuccess: !!data,
           error: ws.error ?? restQuery.error,
           refetch: restQuery.refetch,  // preserved so existing manual-refresh callers work
           // New fields (additive — existing consumers ignore):
           isLive: ws.isLive,
           lastUpdatedAt: ws.lastUpdatedAt,
           restFallbackActive: ws.restFallbackActive,
         }
       }
       ```
    3. The `refetchInterval: 5000` line — and ONLY that line — receives the sentinel comment `// allowlist:rest-fallback-rearm` so the Plan 13-05 grep gate can recognize it.
    4. No other `setInterval` / `refetchInterval: <number>` may remain in these three files outside of the allowlisted spots.

    Tests (one per hook, vitest + @testing-library/react renderHook):
    1. Initial render: ws.data undefined → restFallbackActive false → hook returns { data: undefined, isLoading: true, isFetching: false }
    2. ws delivers frame → hook returns { data: <frame.data>, isLoading: false, isSuccess: true, isLive: true }
    3. ws reports restFallbackActive: true → restQuery is enabled with refetchInterval (assert via spy on react-query's queryFn being called periodically with fake timers)
    4. ws reports restFallbackActive: false → restQuery disabled (refetchInterval becomes false; spy not called again)
    5. Value-contract test: rendered hook result has all of `{ data, isLoading, isFetching, isError, isSuccess, error, refetch }` keys present (snapshot the result.current keys against the existing useQuery key set; must be a superset)
  </behavior>
  <action>
    Refactor each of the three .js files following the pattern in `behavior`. Preserve JSDoc comments — update them to describe the new WS-primary / REST-fallback semantics and pin the load-bearing keys (D-10-16 for useCarryIns specifically — keep that section).
    Add the sentinel comment string EXACTLY as `// allowlist:rest-fallback-rearm` (Plan 13-05 will grep for this string).
    Create the three test files following the test bullets above. Mock useWsSubscription via `vi.mock('./useWsSubscription', () => ({ useWsSubscription: vi.fn() }))` and feed canned return values per test.
    For the refetch behavior: do NOT alias refetchInterval as a variable; the literal token must be on the same source line so the grep gate's regex can pin it: `refetchInterval: 5000, // allowlist:rest-fallback-rearm`.
  </action>
  <verify>
    <automated>cd frontend && npx vitest run src/hooks/__tests__/useSafetyState.test.js src/hooks/__tests__/useLiveReadiness.test.js src/hooks/__tests__/useCarryIns.test.js</automated>
  </verify>
  <acceptance_criteria>
    - Each migrated hook file contains exactly ONE line matching `/refetchInterval: [0-9]+/` AND that line contains `// allowlist:rest-fallback-rearm` (verify: `grep -P "refetchInterval:\s*[0-9]+" frontend/src/hooks/useSafetyState.js frontend/src/hooks/useLiveReadiness.js frontend/src/hooks/useCarryIns.js | grep -v 'allowlist:rest-fallback-rearm' | wc -l` returns 0)
    - No `setInterval(.*[0-9]{4,})` in any of the 3 hook files (verify: `grep -cE "setInterval\([^)]*[0-9]{4,}" frontend/src/hooks/useSafetyState.js frontend/src/hooks/useLiveReadiness.js frontend/src/hooks/useCarryIns.js` returns 0 across all 3)
    - Each hook imports useWsSubscription (verify: `grep -c "useWsSubscription" frontend/src/hooks/useSafetyState.js frontend/src/hooks/useLiveReadiness.js frontend/src/hooks/useCarryIns.js` returns >=3, one per file)
    - vitest reports >=15 tests passed (5 per hook × 3 hooks)
    - Pre-existing PathToLiveTile test still passes: `cd frontend && npx vitest run src/components/__tests__/PathToLiveTile.test.jsx`
  </acceptance_criteria>
  <done>Three production hooks consume useWsSubscription with REST fallback; value-contract unchanged; existing component tests still pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Create useDashboardSnapshot.js hook</name>
  <files>frontend/src/hooks/useDashboardSnapshot.js, frontend/src/hooks/__tests__/useDashboardSnapshot.test.js</files>
  <read_first>
    - frontend/src/hooks/useSafetyState.js (just migrated in Task 2 — copy its pattern)
    - frontend/src/hooks/useWsSubscription.ts
  </read_first>
  <behavior>
    Same shape as Task 2's migrated hooks:
    - useWsSubscription('dashboard-snapshot', '/dashboard/snapshot')
    - REST fallback via useQuery with `// allowlist:rest-fallback-rearm` sentinel
    - Returns { data, isLoading, isFetching, isError, isSuccess, error, refetch, isLive, lastUpdatedAt, restFallbackActive }

    No existing component consumes this hook yet (that wires in v1.3); the hook exists so the WS channel has a frontend client and Phase 13 satisfies "the four production hooks" criterion structurally — the channel data flows end-to-end.

    Tests:
    1. Initial render → restFallbackActive false → data undefined → isLoading true
    2. First WS frame arrives → data populated → isLive true
    3. restFallbackActive flips true → REST query becomes enabled with refetchInterval 5000
    4. Value-contract test mirrors Task 2 — result has the expected key set
  </behavior>
  <action>
    Create frontend/src/hooks/useDashboardSnapshot.js by copying the just-migrated useSafetyState.js pattern, swapping channel + REST path. JSDoc must reflect the new global-snapshot endpoint.
    Create test file mirroring useSafetyState.test.js pattern.
  </action>
  <verify>
    <automated>cd frontend && npx vitest run src/hooks/__tests__/useDashboardSnapshot.test.js</automated>
  </verify>
  <acceptance_criteria>
    - File frontend/src/hooks/useDashboardSnapshot.js exists and exports `useDashboardSnapshot`
    - `grep -c "useWsSubscription" frontend/src/hooks/useDashboardSnapshot.js` >=1
    - `grep -c "allowlist:rest-fallback-rearm" frontend/src/hooks/useDashboardSnapshot.js` >=1
    - vitest reports >=4 tests passed
  </acceptance_criteria>
  <done>useDashboardSnapshot.js hook exists with WS-primary / REST-fallback pattern.</done>
</task>

<task type="auto">
  <name>Task 4: Rebuild api-gateway, rebuild frontend, observe end-to-end push-to-render</name>
  <files>(no source files — deploy + verify-stack)</files>
  <read_first>
    - .claude/skills/deploy/SKILL.md
    - .claude/skills/verify-stack/SKILL.md
  </read_first>
  <action>
    1. Use `deploy` skill to rebuild + recreate `api-gateway` (picks up new /api/dashboard/snapshot endpoint + updated SnapshotPoller).
    2. Use `deploy` skill to rebuild + recreate `frontend` (picks up new wsClient.ts, useWsSubscription.ts, migrated hooks + useDashboardSnapshot.js).
    3. Smoke test:
       a. `curl -sf http://localhost:8000/api/dashboard/snapshot` returns 200 + valid JSON
       b. Open http://localhost:3000 in browser; DevTools → Network → WS → confirm a WebSocket connection to `/ws/metrics` is established (status 101)
       c. DevTools → WS frames pane → click the connection → confirm a subscribe frame is sent first, then 4 inbound snapshot frames (one per channel) arrive within 1s
       d. In a second terminal: `touch safety/EMERGENCY_STOP` — within 500ms a new safety-state frame should arrive in the WS frames pane (visual confirmation); the StatusBar in the running UI should flip its emergency-stop indicator. Then `rm safety/EMERGENCY_STOP` to restore.
       e. DevTools console: kill `api-gateway` (`docker compose -f docker-compose.unified.yml stop api-gateway`); within ~30s console shows the silenceTimeoutMs trigger and the Network tab shows REST polls firing on /api/config/safety-state. Bring it back (`docker compose -f docker-compose.unified.yml start api-gateway`); within one push cycle, REST polls cease.

    Use `verify-stack` skill format to record each PASS/FAIL.
  </action>
  <verify>
    <automated>curl -sf http://localhost:8000/api/dashboard/snapshot >/dev/null && curl -sf http://localhost:3000 >/dev/null && echo PASS</automated>
  </verify>
  <acceptance_criteria>
    - `curl -sf http://localhost:8000/api/dashboard/snapshot` returns 200 with valid JSON containing keys schema_version, evaluated_at
    - Frontend served on :3000 (200 on root)
    - Browser DevTools observation captured in SUMMARY.md: subscribe frame visible + 4 snapshot frames received within 1s + EMERGENCY_STOP toggle frame within 500ms (paste measured ms)
    - REST fallback observation: after killing api-gateway, REST poll requests resume; after restart, they stop. Record the exact event sequence in SUMMARY.md.
  </acceptance_criteria>
  <done>End-to-end push-to-render verified manually; REST fallback round-trip verified.</done>
</task>

</tasks>

<verification>
- WS-03 satisfied: 4 hooks consume useWsSubscription; no setInterval polling outside allowlisted re-arm sites; value-contract preserved
- WS-01 fully satisfied: dashboard-snapshot channel now has a real handler (Task 1 replaces the placeholder)
- New /api/dashboard/snapshot endpoint exists and works
- Component tests (PathToLiveTile, StatusBar) still pass (regression check)
</verification>

<success_criteria>
- [ ] /api/dashboard/snapshot endpoint exists on api-gateway and returns valid JSON
- [ ] SnapshotPoller's _fetch_dashboard_snapshot calls the real handler (not the placeholder)
- [ ] useSafetyState.js, useLiveReadiness.js, useCarryIns.js refactored to useWsSubscription with allowlisted REST fallback
- [ ] useDashboardSnapshot.js created
- [ ] All 4 hooks have value-contract tests proving { data, isLoading, isFetching, isError, isSuccess, error, refetch } keys present
- [ ] Pre-existing PathToLiveTile test still green (no regression)
- [ ] Browser smoke captures subscribe + 4 snapshot frames + sub-500ms EMERGENCY_STOP propagation
- [ ] REST fallback round-trip (kill → REST polls → restart → polls stop) observed in DevTools
- [ ] WS-03 satisfied
</success_criteria>

<output>
After completion, create `.planning/phases/13-real-time-websocket-push/13-04-SUMMARY.md` documenting:
- Files migrated (3) + files created (2 hooks + 1 endpoint + 4 test files)
- Sentinel string used: `// allowlist:rest-fallback-rearm` (exact)
- Measured EMERGENCY_STOP-toggle latency in browser DevTools (ms)
- REST fallback round-trip timing observation (kill → first REST poll latency, restart → REST stop latency)
- Any value-contract deviations and how they were resolved
</output>
</content>
</invoke>