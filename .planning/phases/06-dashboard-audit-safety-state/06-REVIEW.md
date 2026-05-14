---
phase: 06-dashboard-audit-safety-state
reviewed: 2026-05-14T00:00:00Z
depth: standard
files_reviewed: 39
files_reviewed_list:
  - docker-compose.unified.yml
  - frontend/package.json
  - frontend/scripts/check-no-hardcoded-urls.sh
  - frontend/src/App.jsx
  - frontend/src/__tests__/App.test.jsx
  - frontend/src/components/ActiveTrades.jsx
  - frontend/src/components/HybridStrategyPanel.jsx
  - frontend/src/components/KeyMetricsStrip.jsx
  - frontend/src/components/PerformanceAnalyticsPanel.jsx
  - frontend/src/components/PortfolioCard.jsx
  - frontend/src/components/PriceChart.jsx
  - frontend/src/components/PriceTickerGrid.jsx
  - frontend/src/components/RegimeIndicator.jsx
  - frontend/src/components/Sparkline.jsx
  - frontend/src/components/StatusBar.jsx
  - frontend/src/components/TileState.jsx
  - frontend/src/components/TradeHistory.jsx
  - frontend/src/components/TradingEnhancementsPanel.jsx
  - frontend/src/components/TradingSignals.jsx
  - frontend/src/components/__tests__/StatusBar.test.jsx
  - frontend/src/components/__tests__/TileState.test.jsx
  - frontend/src/hooks/__tests__/useSafetyState.test.jsx
  - frontend/src/hooks/useGatewayWebSocket.js
  - frontend/src/hooks/useSafetyState.js
  - frontend/src/pages/Phase1Dashboard.jsx
  - frontend/src/pages/Phase3Dashboard.jsx
  - frontend/src/pages/Portfolio.jsx
  - frontend/src/styles/safety-border.css
  - frontend/vite.config.js
  - scripts/__init__.py
  - scripts/audit_tiles.py
  - scripts/test_audit_tiles.py
  - services/api-gateway/app/main.py
  - services/api-gateway/tests/test_safety_state.py
  - services/trading-engine/app/handlers/health.py
  - services/trading-engine/app/risk/dynamic_risk_budget.py
  - services/trading-engine/tests/test_health_status.py
  - services/trading-engine/tests/test_risk_budget_daily_pnl_pct.py
findings:
  critical: 1
  warning: 7
  info: 4
  total: 12
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-05-14T00:00:00Z
**Depth:** standard
**Files Reviewed:** 39
**Status:** issues_found

## Summary

Phase 6 delivered the operator safety-state surface (D-08 schema route, `useSafetyState` hook, three new StatusBar cells, viewport `outline` border, F-01/F-02/F-03/F-04 fixes), a shared `<TileState/>` wrapper applied to 12 tiles with F-05 precedence, the `audit_tiles.py` runtime probe with fail-closed `--against`, and a hardcoded-URL grep gate. Test coverage for the new artifacts is reasonable.

Three load-bearing claims hold up under read:
- **F-01 kill_switch derivation** at `services/api-gateway/app/main.py:1131-1137` correctly uses `bool(te_budget)` for `daily_loss_armed` and reads the FLAT bool `te_budget["emergency_mode"]` for `tripped` — matches the trading-engine handler shape.
- **F-02 daily_pnl_pct math** at `services/trading-engine/app/risk/dynamic_risk_budget.py:1476-1480` preserves sign and guards zero-equity.
- **F-03 decode pattern** `json.loads(resp.body.decode())` is the correct way to read a `JSONResponse` body and is exercised end-to-end by `test_proxy_returns_jsonresponse_decoded_via_body_decode`.

One BLOCKER and seven WARNING-level defects found, including one pre-existing JS operator-precedence bug in `Phase3Dashboard.jsx` that renders alignment-score percentages as ~1% instead of ~85%. The file is in review scope; not a Phase 6 regression but unaddressed by the wrap.

## Critical Issues

### CR-01: Operator-precedence bug renders alignment-score % wrong (off by 100x)

**File:** `frontend/src/pages/Phase3Dashboard.jsx:486-489`
**Issue:** JS `*` binds tighter than `??`. The expression

```jsx
{(enhancedSignal.metadata?.multi_timeframe?.alignment_score ??
  enhancedSignal.components?.mtf?.alignment_score * 100).toFixed(0)}%
```

parses as `(a ?? (b * 100)).toFixed(0)`. When `metadata.multi_timeframe.alignment_score` is set (the common case — Phase 3 normalisation at line 238 populates it from `technical_analysis.confidence` which is a 0-1 decimal), the `* 100` never executes, so a real value of `0.85` renders as `"1%"` instead of `"85%"`. The gate on lines 486-487 is OK (`!= null` is outside the multiplication), only the rendering expression is wrong.

Pre-existing bug; Phase 6 wrapped the page in `<TileState forceStale/>` (line 330-337) without fixing it. Flagged BLOCKER per file-in-scope rule.

**Fix:**
```jsx
{(() => {
  const score =
    enhancedSignal.metadata?.multi_timeframe?.alignment_score ??
    enhancedSignal.components?.mtf?.alignment_score
  return `${(score * 100).toFixed(0)}%`
})()}
```

## Warnings

### WR-01: Unbounded `_alerts` list growth amplified by Phase 6 5s poll cadence

**File:** `services/trading-engine/app/risk/dynamic_risk_budget.py:403, 1149, 1327, 1338, 1351`
**Issue:** `self._alerts: List[RiskBudgetAlert] = []` has no `maxlen` cap (unlike `_budget_history`, which uses `deque(maxlen=720)`). `_check_and_generate_alerts` is invoked from `calculate_risk_budget()`, which the new safety-state route now calls every 5s through the `/api/v1/risk/budget/current` proxy. The risk_pct-near-minimum branch at line 1350 fires when `risk_pct <= min_risk_pct * 1.2`; if the bot enters emergency mode (a common state at minimum risk) the branch appends one alert per poll, ~17.3k entries/day. Pre-existing problem amplified by Phase 6's polling cadence.

**Fix:** Make `_alerts` a bounded deque:
```python
from collections import deque
# in __init__:
self._alerts: deque[RiskBudgetAlert] = deque(maxlen=500)
```
`get_alerts()` already slices `[-limit:]`; `clear()` semantics still work on a deque.

### WR-02: `asyncio.get_event_loop().run_until_complete()` deprecated on Python 3.12

**File:** `services/trading-engine/tests/test_health_status.py:34-36`
**Issue:** Python 3.12 (per CLAUDE.md the pinned runtime) emits `DeprecationWarning` for `asyncio.get_event_loop()` when there is no running loop and the policy has not been set. Future Python versions remove implicit loop creation entirely. Tests will start raising under `-W error::DeprecationWarning` or strict pytest-asyncio configurations.

**Fix:**
```python
def _run(coro):
    return asyncio.run(coro)
```
`asyncio.run` is the documented replacement; the helper is only called once per test from sync test bodies, so there is no reuse concern.

### WR-03: TileState `forceStale` ignores `isFetching` — refresh has no spinner affordance

**File:** `frontend/src/components/TileState.jsx:240-246, 258-273`
**Issue:** TileState branches: error → loading → empty → stale → children. `query.isLoading` is only `true` on the first fetch; a background refetch sets `query.isFetching` but leaves `isLoading=false`. Tiles in stable state show no refresh indicator. For LABELED_STALE tiles with `forceStale=true`, this is double-bad: operators see a "stale" badge that never goes away even during an in-flight refetch that could clear staleness. Pre-existing pattern, but the Phase 6 design (D-15 per-tile staleness) assumes stale signalling is dynamic.

**Fix:** Plumb an `isFetching`-aware refresh indicator next to the stale badge, or invalidate the badge when `query.isFetching && query.isSuccess`:
```jsx
const showStale =
  !query?.isFetching && (
    Boolean(forceStale) ||
    isStaleByTimestamp(lastUpdatedAt, effectiveStaleAfterMs)
  )
```

### WR-04: Two components bypass the configured axios client

**File:** `frontend/src/components/TradeHistory.jsx:22-25`, `frontend/src/components/PerformanceAnalyticsPanel.jsx:230-238`
**Issue:** Both call `axios.get('/api/...')` directly instead of the project's `services/api.js` client. The shared client carries the `baseURL` (which `VITE_API_BASE_URL` is supposed to control per Phase 6 DASH-02), the request/response interceptors that unwrap `.data`, and the auth header plumbing. Bypassing it works today only because the gateway happens to return `{trades:..., stats:...}` directly and the Vite dev proxy fans out by URL, but:
1. A baseURL override via env var will not apply to these calls — operator changing `VITE_API_BASE_URL` to a non-`/api` value silently splits the dashboard between two backends.
2. The response interceptor unwrapping is inconsistently bypassed — `TradeHistory.jsx:25` uses `response.data` (correct for raw axios) while every other component using `services/api` consumes the unwrapped body.
3. Auth headers / token refresh installed on the shared client are not applied.

**Fix:** Import the shared client:
```jsx
import api from '../services/api'
// ...
queryFn: async () => api.get('/trading/trades/history', { params: { limit: 1000 } }),
```
Then drop the local `.data` unwrap.

### WR-05: TileState empty branch ignores `isLoading=true && data!=null` — stale data flashes to "No data yet"

**File:** `frontend/src/components/TileState.jsx:240, 249-256`
**Issue:** Branch 2 checks `query.isLoading && !query.data`. If a tile holds a prior payload in cache and a refetch is in flight, both `isLoading` (or rather `isFetching`) and `isSuccess` are true with `data` populated. Branch 2 falls through. Branch 3 then checks `query.isSuccess && isEmptyFn(query.data)`. If the predicate returns true (e.g. on a payload that just became empty server-side, like `{positions: []}`), the "No data yet" panel renders immediately instead of keeping the cached non-empty view. For LABELED_STALE tiles this is doubly jarring because the stale-badged populated view is replaced by an empty one mid-refetch. Minor UX defect.

**Fix:** Defer the empty branch when a previous-success snapshot exists:
```jsx
if (query?.isSuccess && isEmptyFn(query.data) && !query.isFetching) {
  // render EmptyState
}
```

### WR-06: `audit_tiles.py` writes ANSI escape codes unconditionally — corrupts non-TTY output

**File:** `scripts/audit_tiles.py:52-56, 273, 279, 284, 293-294`
**Issue:** The script prints `\033[0;32m` / `\033[0m` etc. without checking `sys.stdout.isatty()`. When run inside CI, piped to a file, or captured by Docker logs, the codes are written as literal bytes (e.g. `[0;32mPASS[0m`). The five pytest tests at `scripts/test_audit_tiles.py` only assert `"PASS"` / `"FAIL"` substring presence so they pass either way, but the regression-gate output becomes unreadable in CI logs.

**Fix:**
```python
import sys
_use_color = sys.stdout.isatty()
GREEN = "\033[0;32m" if _use_color else ""
RED = "\033[0;31m" if _use_color else ""
YELLOW = "\033[1;33m" if _use_color else ""
NC = "\033[0m" if _use_color else ""
```

### WR-07: `check-no-hardcoded-urls.sh` allowlist relies on substring grep — false-negative on multi-line block-comment URLs in api.js

**File:** `frontend/scripts/check-no-hardcoded-urls.sh:76-84`
**Issue:** The api.js allowlist requires the line to either contain `//` or start with `*` (after whitespace). A block comment opening on one line and the URL on the very next without a leading `*`:
```js
/* example
http://localhost:8000 is the dev target */
```
would fail the regex and trip the gate. Conversely, a code line that contains `//` somewhere (e.g. embedded URL fragment or inline comment after a string literal) gets silently allowlisted. The script is documented as a regression guard, not a sandbox (T-06-03-02), so this is WARNING not BLOCKER, but the heuristic is fragile.

**Fix:** Use `awk` to track block-comment state across lines, or simply require the URL to live inside a single-line `//`-style comment in api.js. The current production layout (api.js has only a single-line JSDoc reference) is compatible with the stricter rule.

## Info

### IN-01: Production debug `console.log` calls in three components

**File:** `frontend/src/components/PortfolioCard.jsx:30-38`, `frontend/src/pages/Phase1Dashboard.jsx:31, 33, 46, 48, 60, 62, 77-100`, `frontend/src/pages/Phase3Dashboard.jsx:277-280`
**Issue:** Components emit dataflow `console.log` on every render. Phase 1 dashboard renders 7+ log entries per render including raw API payloads. These leak shape information to the browser console and clutter production logs for any operator with devtools open.
**Fix:** Gate behind `import.meta.env.DEV` or remove. The PortfolioCard logs in particular include `performanceError?.message` which could carry stack-trace fragments.

### IN-02: `D-14` "forbid raw error.message" rule violated by inline error panels (pre-existing)

**File:** `frontend/src/pages/Phase3Dashboard.jsx:410, 646, 811, 1014`
**Issue:** Inline error panels render `*ErrorDetails?.message` as a fallback. D-14 (`TileState.jsx:147-156` comment) forbids axios `.message` because it may contain stack-trace fragments. The page-level `<TileState forceStale/>` wrapper only consumes `mlQuery` and catches its error; the four inline panels still render their own error UI with raw `.message`. Pre-existing; Phase 6 did not introduce these. Not a regression but worth noting because the wrap design implied the page is now D-14-compliant.
**Fix:** Switch inline panels to use the D-14 fallback chain (`response.data.detail` → `response.statusText` → generic) or rely entirely on the per-query TileState wrapper instead of dual-pathing.

### IN-03: PerformanceAnalyticsPanel duplicates `<TileState/>` empty handling with internal `!hasData` guard

**File:** `frontend/src/components/PerformanceAnalyticsPanel.jsx:268-274, 293-300`
**Issue:** The component wraps its body in `<TileState isEmpty={...}>` AND keeps its inner `!hasData` early-return ("No trading data available yet"). When TileState's emptiness predicate matches it shows "No data yet". When the inner predicate matches separately (e.g. metrics present but trade history empty), the inner empty UI shows. Two competing empty states diverge in copy and visual style. Minor confusion for operators.
**Fix:** Pick one. The audit guidance (`D-13`) is that TileState owns the empty UX; remove the inner fallback or include `trades.length === 0` in the TileState `isEmpty` predicate.

### IN-04: `useSafetyState` test relies on textual grep of source file

**File:** `frontend/src/hooks/__tests__/useSafetyState.test.jsx:72-89`
**Issue:** The second test reads the hook source file as text and asserts literal `refetchInterval: 5000`, `staleTime: 5000`, `retry: 2`, `retryDelay: 1000` substrings. This is brittle:
- Refactoring to extract constants (e.g. `const POLL_MS = 5000; refetchInterval: POLL_MS`) makes the test fail even though behaviour is unchanged.
- It does not actually verify the option is applied at runtime — only that the literal exists somewhere in the source.

Useful as a regression hint but unsound as a behaviour test.
**Fix:** If runtime introspection of React Query options is hard to mock, at least replace the textual grep with an AST-level extraction (e.g. parse the file and inspect the object literal). Better: spy on `useQuery` and assert its argument shape.

---

_Reviewed: 2026-05-14T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
