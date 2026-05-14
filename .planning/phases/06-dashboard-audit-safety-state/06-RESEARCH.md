# Phase 6: Dashboard Audit & Safety State - Research (Backfill)

**Researched:** 2026-05-13
**Mode:** BACKFILL — plans already written + verified iteration 2; this run pressure-tests them against the running codebase
**Domain:** React 18 dashboard + FastAPI api-gateway + trading-engine status surface
**Confidence:** HIGH (every load-bearing claim verified against committed source, not training data)

## Summary

Five plans cover DASH-01/02/03/05 across 2 waves. They are structurally sound — the audit deliverable shape, the StatusBar extension pattern, the `<TileState/>` wrapper API, the env-var migration, and the per-page commit strategy all match the existing codebase well. **However, four concrete runtime defects in Plan 6-02 will crash the safety-state endpoint at first call, and one tile-inventory gap in Plan 6-05 will leave the home page (`Dashboard.jsx`) un-refactored.** All are mechanical mistakes (wrong field shape, wrong return type, missing env, missing parent page) — none reveal a design flaw with the phase itself.

**Primary recommendation:** Revise Plan 6-02 Task 2 + Plan 6-05 Task 0 file lists before Wave 1 starts. The fixes are listed below in `## Plan Revisions Required (BLOCKING)`. Validation Architecture downstream (`## Validation Architecture` section) is fully populated so a follow-up VALIDATION.md can be generated mechanically.

---

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Audit deliverable:**
- **D-01:** Ship BOTH `06-TILE-AUDIT.md` (markdown table) AND `scripts/audit_tiles.py` (runtime probe).
- **D-02:** Each audit row verdict ∈ `{FIXED, LABELED_STALE, REMOVED}`. Operator reviews before commit.

**Safety state — content:**
- **D-03:** Surface exactly five flags: `TRADING_MODE`, `auto_trading_enabled`, kill-switch (RISK-01 5%-daily-loss), `EMERGENCY_STOP` presence+mtime, `ENABLE_ML_PREDICTIONS`. Per-trade-cap percentages and daily-P&L-vs-budget stay in body tiles.
- **D-04:** "Kill-switch" maps to the 5%-daily-loss circuit-breaker (ARMED / TRIPPED), sourced from trading-engine risk-budget. 5-consecutive-losses limit NOT in safety strip.

**Safety state — surfacing:**
- **D-05:** Extend existing `StatusBar.jsx` (no new component). Three new cells: TRADING_MODE pill, kill-switch badge, ML toggle. No layout-shift in `App.jsx`.
- **D-06:** PAPER/LIVE shown as pill in StatusBar AND 1-2px viewport border (red LIVE / neutral PAPER). Border is the secondary affordance.
- **D-07:** `EMERGENCY_STOP` cell renders Active/Inactive badge + last-modified timestamp ("ACTIVE — since 12:43:01" / "INACTIVE"). Reason text deferred.

**Safety state — backend wiring:**
- **D-08:** New `GET /api/config/safety-state` on api-gateway. Schema includes `trading_mode`, `paper_trading_mode`, `auto_trading_enabled`, `emergency_stop{active,mtime}`, `ml_predictions_enabled`, `kill_switch{daily_loss_armed,daily_pnl_pct,tripped}`, `last_updated_at`.
- **D-09:** api-gateway owns the endpoint. Reads its own env + proxies trading-engine for fan-out fields.
- **D-10:** `EMERGENCY_STOP` file read by trading-engine only. Gateway proxies trading-engine for `emergency_stop.{active, mtime}`.
- **D-11:** Frontend polls every 5s via React Query (`staleTime: 5000`, `refetchInterval: 5000`).

**Empty/error/stale (DASH-05):**
- **D-12:** New `frontend/src/components/TileState.jsx` wraps every audited tile body.
- **D-13:** `<TileState/>` distinguishes `loading | empty | error | stale`. Skeleton / "No data yet" / "Failed (HTTP code): short message [Retry]" / corner badge.
- **D-14:** Error UI = HTTP status + short message + Retry. No stack traces. No raw `error.message`.
- **D-15:** Stale-data detection is backend-driven via `last_updated_at`. Phase 6 scope-down: real `last_updated_at` emitted ONLY by `/api/config/safety-state`; other tiles use `forceStale={true}`.

**Config-driven URLs (DASH-02):**
- **D-16:** Migrate single remaining `ws://localhost:8000/ws` literal in `useGatewayWebSocket.js:34` to `VITE_WS_URL`. Document `VITE_API_BASE_URL` + `VITE_WS_URL` in `vite.config.js`.

### Claude's Discretion

- Markdown structure for `06-TILE-AUDIT.md`.
- `<TileState/>` visual styling (match existing Editorial Trading Floor palette).
- Exact threshold values per tile in staleness map.
- Whether new gateway endpoint requires auth (recommend no).
- Audit script CLI shape.

### Deferred Ideas (OUT OF SCOPE)

- Tournament leaderboard view (DASH-04 → Phase 7).
- Playwright smoke (DASH-06 → Phase 7).
- WebSocket push for safety state (v2).
- Reason text for EMERGENCY_STOP (later phase).
- Full `frontend/src/config.js` module (v2).
- Modal-on-LIVE-flip (rejected).
- Per-trade-cap + daily-P&L in safety strip (body tile).
- Auth on `/api/config/safety-state` (open in this phase).
- Per-tile `last_updated_at` on non-safety-state endpoints (Phase 7 follow-up).

---

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DASH-01 | End-to-end audit of every tile/route — backing endpoint + verified shape + verdict | Plans 6-01 + 6-05. Tile inventory list verified against `frontend/src/components/` (see `## Findings`). |
| DASH-02 | Hardcoded URLs replaced with config-driven values | Plan 6-03. `useGatewayWebSocket.js:34` is the single remaining literal; verified by grep. Existing `VITE_ENABLE_WEBSOCKET` pattern at `useGatewayWebSocket.js:38` is the analog. |
| DASH-03 | Safety-state header with five flags | Plans 6-02 + 6-04. **Plan 6-02 needs revisions** — see `## Plan Revisions Required`. |
| DASH-05 | Empty/error/stale states on every tile | Plan 6-05. **Plan 6-05 Task 0 file list incomplete** — see `## Plan Revisions Required`. |

---

## Plan Revisions Required (BLOCKING)

> The planner consumes this section first. Each finding identifies (a) which plan/task is affected, (b) what's wrong, (c) the corrected approach. **These four items must be fixed before Wave 1 execution; otherwise Plan 6-02 will crash at first request and Plan 6-05 will skip ~10 tile sites.**

### F-01: `emergency_mode` shape mismatch in Plan 6-02 Task 2 [VERIFIED: services/trading-engine/app/handlers/risk_budget.py:50]

**Affected:** Plan 6-02 Task 2 (lines 207-223 of `06-02-PLAN.md`), Pattern map line 376-380 of `06-PATTERNS.md`, B-01 derivation explicitly instructed.

**What's wrong:** Plan 6-02 + PATTERNS.md instruct the executor to derive `daily_loss_armed` and `tripped` via:
```python
"daily_loss_armed": bool(te_budget.get("emergency_mode", {}).get("armed", False)),
"tripped": bool(te_budget.get("emergency_mode", {}).get("active", False)),
```
**Actual response shape** (verified at `services/trading-engine/app/handlers/risk_budget.py:50` `CurrentBudgetResponse`):
```python
emergency_mode: bool = Field(description="Whether emergency mode is active")
```
`emergency_mode` is a **flat boolean**, NOT a dict with `armed`/`active` sub-keys. The chained `.get("armed", False)` on a `bool` raises `AttributeError: 'bool' object has no attribute 'get'` when the proxy call succeeds. The try/except in the plan only catches proxy failure (sets `te_budget = {}`), so on the happy path the endpoint crashes with HTTP 500.

**Why the existing test in Plan 6-02 Task 2 Test 9 passes:** the test mocks the proxy to return `{"emergency_mode": {"armed": True, "active": False}, ...}` — a shape that does NOT exist in production. Tests pass green; production crashes.

**Corrected approach:**

The risk-budget module has only ONE `_emergency_mode` flag (verified at `services/trading-engine/app/risk/dynamic_risk_budget.py:354`, exposed as `emergency_mode: bool` in `CurrentBudgetResponse` line 50). There is no "armed vs active" distinction at the data-model level — armed and tripped are the SAME state per the current implementation. To honor D-04's intent (operator wants to see two distinct signals), the plan has two options:

**Option A — collapse to one signal (matches reality):**
```python
emergency_active = bool(te_budget.get("emergency_mode", False))
"kill_switch": {
    "daily_loss_armed": True,  # armed whenever the risk-budget module is reachable
    "daily_pnl_pct": <see F-02>,
    "tripped": emergency_active,
},
```
Document in the response docstring: "daily_loss_armed mirrors the risk-budget module's readiness (always True when te_budget is reachable per RISK-01 always-on policy from CLAUDE.md). `tripped` is True when the 5%-daily-loss circuit-breaker has fired."

**Option B — surface a distinct armed flag (requires backend change):**
Add an `armed` field to `CurrentBudgetResponse` (always True per CLAUDE.md project rule "5% daily-loss circuit-breaker (always)"), then keep the .get() chain but flatten:
```python
"daily_loss_armed": bool(te_budget.get("armed", False)),
"tripped": bool(te_budget.get("emergency_mode", False)),
```

**Recommendation:** Option A. The B-01 grep gate (no hardcoded `True` literal) still has value — but the load-bearing requirement is "tripped is sourced from te_budget.emergency_mode and falls to False when te_budget is empty/unreachable" — that requirement IS satisfied by Option A. The `armed` field is conceptual; in the current code there is no disarming mechanism. Update the test names + assertions accordingly:
- Test 8 (rename): `test_tripped_defaults_false_when_budget_empty` — asserts `kill_switch.tripped` is False when proxy raises.
- Test 9 (rename): `test_tripped_true_when_budget_emergency_mode_true` — asserts `kill_switch.tripped` is True when te_budget returns `{"emergency_mode": True, ...}`.

### F-02: `utilization.daily_pnl_pct` does not exist in trading-engine response [VERIFIED: handlers/risk_budget.py:72-77]

**Affected:** Plan 6-02 Task 2 action (line 213 of `06-02-PLAN.md`), PATTERNS.md line 378.

**What's wrong:** Plan instructs:
```python
"daily_pnl_pct": float(te_budget.get("utilization", {}).get("daily_pnl_pct", 0.0)),
```
**Actual `utilization` keys** in `CurrentBudgetResponse` example (lines 72-77 of risk_budget.py):
```python
"utilization": {
    "total_budget_usd": 1600.0,
    "used_budget_usd": 400.0,
    "available_budget_usd": 1200.0,
    "utilization_pct": 25.0,
}
```
There is no `daily_pnl_pct` key. The `.get("daily_pnl_pct", 0.0)` silently returns 0.0 forever. The endpoint won't crash but the field is uselessly stuck at zero — operator can never see daily-loss progress.

**Corrected approach:** The risk-budget manager DOES track `self._daily_pnl` (line 362 of `dynamic_risk_budget.py`) and the trip threshold at line 1157:
```python
if abs(self._daily_pnl) >= self._current_equity * (self.config.max_daily_loss_pct / 100):
```
So daily-PnL-as-percentage = `_daily_pnl / _current_equity * 100`. This is NOT currently surfaced in any HTTP response. Pick one:

**Option A — extend risk_budget.py model with `daily_pnl_pct` field (preferred):**
Add to `CurrentBudgetResponse.utilization` dict shape (it's `Dict[str, Any]` so no model edit needed — just augment what `get_current_budget` returns in the handler at risk_budget.py:406+). Computed as `(manager._daily_pnl / manager._current_equity) * 100` where defined and `0.0` otherwise.

**Option B — use existing `utilization_pct` instead (changes the meaning of the field):**
Update D-08 schema to rename `daily_pnl_pct` → `budget_utilization_pct` and read `te_budget.utilization.utilization_pct`. This is a different signal (budget USED, not P&L direction) — operator sees how much of the daily risk envelope has been allocated, not how much P&L has been realized.

**Recommendation:** Option A (additive backend change). Add a new task to Plan 6-02 (Task 1.5 or Task 3) that extends `get_current_budget` handler at `risk_budget.py:378-455` to compute and return `utilization.daily_pnl_pct`. Two-line change, no model edit, falls out naturally from the existing `manager._daily_pnl / manager._current_equity` computation. Then the gateway code reads `te_budget.utilization.daily_pnl_pct` as-planned.

### F-03: `proxy_request` returns `JSONResponse`, not `dict` [VERIFIED: services/api-gateway/app/services/service_proxy.py:137-141]

**Affected:** Plan 6-02 Task 2 action (entire `try/except` block, lines 196-208 of `06-02-PLAN.md`), PATTERNS.md lines 354-365.

**What's wrong:** Plan instructs:
```python
try:
    te_status = await proxy.proxy_request(service_name="trading-engine", path="/status", method="GET")
except Exception:
    te_status = {}
...
"auto_trading_enabled": bool(te_status.get("auto_trading_enabled", False)),
```
**Actual return type** (service_proxy.py:137-141):
```python
return JSONResponse(
    content=response.json() if response.text else {},
    status_code=response.status_code,
    headers=forwarded,
)
```
`proxy_request` returns a Starlette `JSONResponse` object. `JSONResponse` does NOT implement `.get()` — calling `te_status.get("auto_trading_enabled", ...)` raises `AttributeError`.

**Existing pattern in the same file** (main.py:271) for "get the body of a `proxy_request` result":
```python
portfolio_data = json.loads(portfolio_resp.body.decode())
```

**Corrected approach:** Two layers of fix:

1. **In the route handler:**
   ```python
   import json
   ...
   try:
       te_status_resp = await proxy.proxy_request(service_name="trading-engine", path="/status", method="GET")
       te_status = json.loads(te_status_resp.body.decode()) if te_status_resp.status_code == 200 else {}
   except Exception:
       te_status = {}
   # ...same for te_budget
   ```

2. **In PATTERNS.md (lines 354-365):** update the analog code block so subsequent agents don't repeat the bug. Change the `te_status =` line to the decoded form.

**Tests will catch this on first real `pytest` run only if** the mock returns a `JSONResponse` object, not a plain dict. The Plan 6-02 Test 1 mock pattern is unspecified ("match whatever pattern existing tests in `services/api-gateway/tests/` already use"). If the executor reads `tests/test_websocket_router.py` (which DOES exercise `JSONResponse` paths) the pattern propagates; if they read a simpler handler test the bug ships.

### F-04: api-gateway compose block is missing `TRADING_MODE` / `PAPER_TRADING_MODE` / `ENABLE_ML_PREDICTIONS` env vars [VERIFIED: docker-compose.unified.yml:253-282]

**Affected:** Plan 6-02 Task 2 action (lines 196-202 of `06-02-PLAN.md`), D-09 (CONTEXT.md line 58: "api-gateway owns the endpoint. It reads its own env (`TRADING_MODE`, `PAPER_TRADING_MODE`, `ENABLE_ML_PREDICTIONS`)").

**What's wrong:** The api-gateway compose block at `docker-compose.unified.yml:253-282` declares 30+ env vars (SERVICE_NAME, POSTGRES_*, REDIS_*, service URLs, EMERGENCY_STOP_FILE) but does NOT include `TRADING_MODE`, `PAPER_TRADING_MODE`, or `ENABLE_ML_PREDICTIONS`. Those vars are only injected into the **trading-engine** block (lines 548, 573 etc.).

Result: in production, `os.environ.get("TRADING_MODE", "PAPER")` always returns the default `"PAPER"`. The PAPER/LIVE pill will be **stuck on PAPER** even after the operator sets `TRADING_MODE=LIVE` for real-money trading. Pill is then a safety-misleading widget — the worst kind of bug in this phase.

**Corrected approach:** Two options; planner must pick one and the choice has architectural implications.

**Option A — patch compose to inject the three vars into api-gateway (matches D-09 verbatim):**
Add to api-gateway compose env block:
```yaml
- TRADING_MODE=${TRADING_MODE:-PAPER}
- PAPER_TRADING_MODE=${PAPER_TRADING_MODE:-true}
- ENABLE_ML_PREDICTIONS=${ENABLE_ML_PREDICTIONS:-false}
- LIVE_TRADING_ACK=${LIVE_TRADING_ACK:-}
```
Add a new Plan 6-02 Task 1.5 or extend Task 2's `<files>` to include `docker-compose.unified.yml`. Operator restart of api-gateway propagates the env. Test harness uses `monkeypatch.setenv(...)` per-test.

**Option B — proxy `/status` for `trading_mode` instead of reading env (changes D-09 ownership):**
`StatusResponse` already returns `trading_mode: TradingMode` at the top level (verified at `services/trading-engine/app/models/response.py:27`). The gateway can derive everything from the existing `/status` proxy call. Same for `auto_trading_enabled` (already returned at `:28`). `PAPER_TRADING_MODE` and `ENABLE_ML_PREDICTIONS` would still need to come from somewhere — either compose patch (Option A subset) OR additional `/status` fields (trading-engine extends `StatusResponse`).

**Recommendation:** Option A. It's a 4-line compose patch + 1-line file_modified addition to Plan 6-02. Keeps D-09 intent intact ("gateway is the single ingress; reads what gateway needs"). Option B is more changes (StatusResponse model edit + gateway handler refactor + new tests) for the same observable behavior.

**Also recommended (related but not blocking):** Add `LIVE_TRADING_ACK` to the D-08 schema as `live_trading_acknowledged: bool` so the UI can warn when the gateway reports `TRADING_MODE=LIVE` but trading-engine is dead because the ack is missing (`services/trading-engine/app/main.py:251-258` refuses to boot in LIVE without `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`). Without it: UI shows LIVE pill while the engine is refusing to start. Document as Phase 6 polish OR explicitly defer to Phase 7.

### F-05: `Dashboard.jsx` + `PerformanceDashboard.jsx` missing from Plan 6-05 file list [VERIFIED: frontend/src/components/Dashboard.jsx:1-13, App.jsx:30]

**Affected:** Plan 6-05 Task 0 (lines 175-219 of `06-05-PLAN.md`), Plan 6-05 `files_modified` frontmatter, PATTERNS.md line 606 tile inventory.

**What's wrong:** Plan 6-05's "parent pages to edit for REMOVED tiles" (Task 0 step 2c) lists only `Phase1Dashboard.jsx`, `Phase3Dashboard.jsx`, `Portfolio.jsx`. **But `frontend/src/components/Dashboard.jsx` is the home `/` route page** (registered at `App.jsx:30` `import Dashboard from './components/Dashboard'`) and imports **12 of the 14 audited tiles** (verified at Dashboard.jsx:2-13: PortfolioCard, PriceTickerGrid, EmergencyStop, TradingSignals, PriceChart, KeyMetricsStrip, ActiveTrades, TradeHistory, TradingEnhancementsPanel, PerformanceAnalyticsPanel, HybridStrategyPanel, RegimeIndicator).

If ANY tile gets verdict=REMOVED in Plan 6-01, Plan 6-05 Task 0 won't identify `Dashboard.jsx` as the parent page that needs the import + JSX deletion. Result: removed tile keeps rendering on the home page.

Similarly, `frontend/src/pages/PerformanceDashboard.jsx` is a separate route page imported at `App.jsx:33` (verified) — Plan 6-01 PATTERNS.md doesn't include it in the audit scope BUT the route exists and renders tiles, so the audit table needs to either include it or explicitly state "no data tiles, skip".

**Corrected approach:**

1. **Plan 6-01 Task 1 (tile inventory walk):** Add `frontend/src/components/Dashboard.jsx` and `frontend/src/pages/PerformanceDashboard.jsx` to the "pages to walk" list. Each may surface NEW tiles (Dashboard does NOT; the 12 tiles it imports are already in the inventory) OR confirm "no data tiles".

2. **Plan 6-05 Task 0 step 2c:** Change the parent-page list to dynamically resolve from grep — for each REMOVED tile, run:
   ```bash
   grep -rln "<TileNameComponent\|import TileNameComponent" frontend/src/
   ```
   and edit every match. Hardcoding the 3-page list will miss `Dashboard.jsx`.

3. **Plan 6-05 `files_modified` frontmatter:** Add `frontend/src/components/Dashboard.jsx` to the optimistic list. (Frontmatter is immutable mid-execution per W-06, but the SUMMARY can record overruns — this is the planning-time fix.)

**Severity:** HIGH but not BLOCKING in the same way as F-01..F-04 — Plan 6-05 won't CRASH if Dashboard.jsx is missed; it will silently leave the removed tile rendering. The Task 3 manual smoke catches it ("REMOVED tile still visible on home page") and the operator fixes it then. But surface this now so the planner can prevent the rework.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Reading config env vars (TRADING_MODE, ML toggle) | API / Backend (api-gateway) | — | Gateway owns env-disclosure boundary per D-09; frontend should not read env directly. |
| Reading EMERGENCY_STOP file state | API / Backend (trading-engine) | API / Backend (api-gateway proxy) | D-10: trading-engine is the single reader; gateway proxies. (Note: gateway HAS the bind-mount per compose line 287, but D-10 deliberately routes through trading-engine for source-of-truth.) |
| Reading risk-budget kill-switch state | API / Backend (trading-engine) | API / Backend (api-gateway proxy) | Risk-budget manager lives in trading-engine process; gateway proxies. |
| Polling cadence + retry policy | Frontend Server (React Query) | — | React Query owns hook-level cadence; QueryClient at `main.jsx:47-74` sets defaults (no global `refetchInterval`, `refetchOnWindowFocus: false`). |
| Stale-data detection | API / Backend (`last_updated_at` field) | Frontend Server (TileState compares to Date.now) | D-15 backend-driven; frontend has the threshold map and renders the badge. |
| Empty/error/loading rendering | Frontend Server (TileState component) | — | Pure UI state machine; no backend involvement. |
| PAPER/LIVE viewport border | Frontend Server (App.jsx + CSS outline) | — | Pure CSS, derived from `safety.trading_mode` from the polled hook. |
| Env-var injection at build time | CDN / Static (Vite build) | — | `VITE_*` vars baked at build, read via `import.meta.env`. |
| WebSocket connection (existing) | Frontend Server | API / Backend (api-gateway `/ws`) | Out of scope for safety state per D-11 (no SSE/WS in Phase 6). |
| Audit script runtime probe | Operator CLI (Python) | API / Backend (api-gateway endpoints) | scripts/audit_tiles.py runs from operator shell; hits gateway over HTTP. |

---

## Standard Stack

### Core (already installed — Phase 6 adds zero new runtime deps)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| React | ^18.2.0 | UI rendering | Already core dep [VERIFIED: frontend/package.json:18] |
| @tanstack/react-query | ^5.12.2 | Polling/cache hook | Already core dep — v5 — `staleTime`, `refetchInterval` API stable [VERIFIED: frontend/package.json:14] |
| axios | ^1.6.2 | HTTP client | Already core dep, baseURL '/api' + response interceptor unwraps `.data` [VERIFIED: frontend/src/services/api.js:9-39] |
| FastAPI | (container-pinned 0.109) | api-gateway routes | Existing gateway framework; same `@app.get` decorator pattern [VERIFIED: services/api-gateway via CLAUDE.md "Gotchas"] |
| httpx | (gateway dep) | Inter-service async HTTP | Used in `ServiceProxy.proxy_request` with `timeout=30.0` for fan-out + `timeout=5.0` for health [VERIFIED: services/api-gateway/app/services/service_proxy.py:38,174] |

### Testing

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| vitest | ^1.6.0 | Frontend unit test runner | **Already installed** with `"test": "vitest"` script [VERIFIED: frontend/package.json:11,42]. Plan 6-04 Task 0 Branch A applies. |
| @testing-library/react | ^14.2.0 | Component rendering tests | Already installed [VERIFIED: frontend/package.json:28] |
| @testing-library/jest-dom | ^6.4.0 | DOM assertion matchers | Already installed; setup file at `frontend/src/__tests__/setup.js:1` |
| jsdom | ^24.0.0 | Browser-env shim for vitest | Already installed [VERIFIED: frontend/package.json:38] |
| pytest | (per service) | Backend tests | Existing convention; api-gateway tests run inside container (fastapi 0.109 vs 0.136 caveat) |

**Plan 6-04 Task 0 specifics:**
- Branch A applies (vitest pre-existing).
- Existing setup file is `./src/__tests__/setup.js` (NOT `./src/test-setup.js` as Plan 6-04 Branch B would create).
- Existing vitest config block is INSIDE `vite.config.js` at lines 205-211 (NOT a separate `vitest.config.js`).
- **If executor follows Branch B logic accidentally, two separate config sources will compete.** The `files_modified` line `frontend/vitest.config.js` in the plan's frontmatter is misleading — under Branch A it should NOT be created.
- Acceptance criterion needs adjustment: `cd frontend && npm run test:run` (NOT `npm run test -- --run --passWithNoTests` which assumes the script is `vitest run` with the flag — actual script is `vitest` which DOES start watch mode; the `test:run` script at line 12 is what should be invoked).

### Installation

No new packages. Phase 6 is config + new routes + new React components only.

**Version verification (executed 2026-05-13):**
- React Query v5 confirmed via `frontend/package.json` lockfile dep.
- FastAPI version asymmetry confirmed via CLAUDE.md "Gotchas" — tests must run in-container.

---

## Architecture Patterns

### System Architecture Diagram

```
                         ┌─────────────────────────────┐
                         │  Operator (Browser)         │
                         │  http://localhost:3000      │
                         └──────────────┬──────────────┘
                                        │ React Query poll every 5s
                                        │ GET /api/config/safety-state
                                        ▼
              ┌──────────────────────────────────────────────────┐
              │  api-gateway :8000  (FastAPI, fastapi 0.109)     │
              │  - reads its OWN env (TRADING_MODE, etc)         │  ← F-04: env vars MISSING
              │    in compose for api-gateway block              │     (must be added)
              │  - calls ServiceProxy.proxy_request() (httpx)    │
              │    ↳ returns JSONResponse, body needs decode    │  ← F-03: decode body
              │      (existing pattern at main.py:271)           │
              └──────┬───────────────────────────────────┬───────┘
                     │                                   │
                     │ proxy GET /status                 │ proxy GET /api/v1/risk/budget/current
                     ▼                                   ▼
        ┌────────────────────────┐         ┌────────────────────────────────┐
        │  trading-engine :8005  │         │  trading-engine handlers/      │
        │  StatusResponse:       │         │  risk_budget.py /current       │
        │  - status              │         │  CurrentBudgetResponse:        │
        │  - trading_mode (PAPER)│         │  - emergency_mode: BOOL (flat) │  ← F-01: NOT a dict
        │  - auto_trading_enabled│         │  - utilization{utilization_pct,│  ← F-02: no daily_pnl_pct
        │  - emergency_stop{     │         │     used_budget_usd, ...}      │
        │      file_path,        │         │  - budget{...}, config{...}    │
        │      active,           │         └────────────────────────────────┘
        │      mtime ← NEW (06-02 T1)│
        │      last_checked,     │
        │      auto_trader_running}│
        └──────┬─────────────────┘
               │ at file boot + each loop iteration
               ▼
        ┌────────────────────────────────────┐
        │  Path("/app/EMERGENCY_STOP")       │
        │  RO bind-mount: ./EMERGENCY_STOP   │
        │  Currently: DIRECTORY (empty)      │
        │  is_file() returns False ⇒ mtime null
        └────────────────────────────────────┘
                                ▲
                                │ ALSO RW bind-mount at api-gateway compose:287
                                │ (gateway COULD read directly but D-10 routes via TE)

                       ─────────────────────────

                    Frontend tile-rendering subsystem
                                │
                                ▼
            ┌──────────────────────────────────────────────────────┐
            │  <TileState query={...} forceStale isEmpty title>    │  ← NEW (Plan 6-05)
            │  State machine: forceStale OR isStale → badge        │
            │                 isLoading → skeleton                 │
            │                 isError → "Failed (code): msg" + Retry│ ← D-14: NO raw error.message
            │                 isSuccess + isEmpty → "No data yet"  │
            │                 else → children                      │
            └──────────────────────────────────────────────────────┘
                                ▲
            wrapped around each FIXED-verdict tile body
                                │
            ┌───────────────────┴───────────────────┐
            │  parent pages:                        │
            │   - frontend/src/components/Dashboard.jsx   ← F-05: MISSING from 6-05 list
            │   - frontend/src/pages/Phase1Dashboard.jsx  │
            │   - frontend/src/pages/Phase3Dashboard.jsx  │
            │   - frontend/src/pages/Portfolio.jsx        │
            │   - frontend/src/pages/PerformanceDashboard.jsx ← F-05: verify scope
            └───────────────────────────────────────┘
```

### Recommended Project Structure

```
.planning/phases/06-dashboard-audit-safety-state/
├── 06-CONTEXT.md            # locked decisions (D-01..D-16) — existing
├── 06-PATTERNS.md           # analog code map — existing (needs F-01/F-03 fix)
├── 06-RESEARCH.md           # this file
├── 06-TILE-AUDIT.md         # operator audit table (Plan 6-01 produces)
├── 06-TILE-AUDIT.json       # machine sidecar (Plan 6-01 produces)
└── 06-0{1..5}-PLAN.md       # 5 plans, 2 waves — existing (need F-01..F-05 revisions)

frontend/src/
├── App.jsx                  # add safety-border wrapper (Plan 6-04 T2)
├── components/
│   ├── StatusBar.jsx        # extend +3 cells (Plan 6-04 T1)
│   ├── Dashboard.jsx        # ← MISSING from 6-05 — F-05
│   ├── TileState.jsx        # NEW (Plan 6-05 T1)
│   └── …existing tiles…     # wrapped per verdict (Plan 6-05 T2)
├── hooks/
│   ├── useGatewayWebSocket.js  # 1-line VITE_WS_URL migration (Plan 6-03)
│   └── useSafetyState.js    # NEW polling hook (Plan 6-04 T1)
├── pages/
│   ├── Phase1Dashboard.jsx
│   ├── Phase3Dashboard.jsx
│   ├── Portfolio.jsx
│   └── PerformanceDashboard.jsx  # ← verify in 6-01 audit
└── styles/safety-border.css # NEW (Plan 6-04 T2)

services/api-gateway/app/
└── main.py                  # add @app.get("/api/config/safety-state") (Plan 6-02 T2)

services/trading-engine/app/
├── handlers/health.py       # extend emergency_stop with mtime (Plan 6-02 T1)
└── handlers/risk_budget.py  # add daily_pnl_pct to utilization dict — F-02 fix

scripts/
└── audit_tiles.py           # NEW (Plan 6-01 T2)
```

### Pattern 1: api-gateway aggregator endpoint with proxy fan-out

**What:** Read gateway-local env + decode JSONResponse bodies from one or more `proxy_request` calls.
**When to use:** Any new gateway route that combines local config with backend state (Plan 6-02 T2 is the canonical case).
**Example:**
```python
import json
import os
from datetime import datetime, timezone

@app.get("/api/config/safety-state")
async def get_safety_state():
    """Aggregated safety/posture endpoint. Unauthenticated read-only (D-09)."""
    proxy = get_proxy()
    trading_mode = os.environ.get("TRADING_MODE", "PAPER").upper()
    paper_trading_mode = os.environ.get("PAPER_TRADING_MODE", "true").lower() == "true"
    ml_predictions_enabled = os.environ.get("ENABLE_ML_PREDICTIONS", "false").lower() == "true"

    # Fan-out + decode (NOT .get() on JSONResponse directly — F-03 fix)
    try:
        resp = await proxy.proxy_request("trading-engine", "/status", "GET")
        te_status = json.loads(resp.body.decode()) if resp.status_code == 200 else {}
    except Exception:
        te_status = {}
    try:
        resp = await proxy.proxy_request("trading-engine", "/api/v1/risk/budget/current", "GET")
        te_budget = json.loads(resp.body.decode()) if resp.status_code == 200 else {}
    except Exception:
        te_budget = {}

    es = te_status.get("emergency_stop", {}) if isinstance(te_status, dict) else {}
    util = te_budget.get("utilization", {}) if isinstance(te_budget, dict) else {}

    return {
        "trading_mode": trading_mode,
        "paper_trading_mode": paper_trading_mode,
        "auto_trading_enabled": bool(te_status.get("auto_trading_enabled", False)),
        "emergency_stop": {
            "active": bool(es.get("active", False)),
            "mtime": es.get("mtime"),  # ISO string or None
        },
        "ml_predictions_enabled": ml_predictions_enabled,
        "kill_switch": {
            # F-01 fix: emergency_mode is a flat bool in CurrentBudgetResponse
            "daily_loss_armed": True,  # always armed per RISK-01 (CLAUDE.md "Project rules")
            # F-02 fix: requires daily_pnl_pct to be added to utilization dict in risk_budget.py
            "daily_pnl_pct": float(util.get("daily_pnl_pct", 0.0)),
            "tripped": bool(te_budget.get("emergency_mode", False)),
        },
        "last_updated_at": datetime.now(timezone.utc).isoformat(),
    }
```
**Source:** Composed from existing `main.py:1027-1034` (proxy passthrough) + `main.py:268-273` (decode body) + fix overlays.

### Pattern 2: React Query polling hook

**What:** Single-poll hook for a scalar/object endpoint with sub-minute cadence.
**When to use:** Any new periodic data fetch (Plan 6-04 T1 useSafetyState).
**Example:**
```javascript
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'

export function useSafetyState() {
  return useQuery({
    queryKey: ['safety-state'],
    queryFn: async () => api.get('/config/safety-state'),  // interceptor strips .data
    refetchInterval: 5000,
    staleTime: 5000,
    retry: 2,
    retryDelay: 1000,
    // Note: refetchOnWindowFocus inherited as `false` from QueryClient defaults at main.jsx:54
  })
}
```
**Source:** `frontend/src/hooks/usePortfolio.js:10-21` + `usePositions.js:55-69`. **Verified:** global `QueryClient` at `main.jsx:47-74` already sets `refetchOnWindowFocus: false`, so the hook will not double-poll on tab focus.

### Pattern 3: WSL bind-mount file-stat guard

**What:** `is_file()` (NOT `.exists()`) before reading `stat()` of a bind-mounted file.
**When to use:** Any code that reads a file at a known Docker bind-mount path.
**Example:**
```python
mtime_iso = None
try:
    p = auto_trader.emergency_stop_file
    if p.is_file():
        from datetime import datetime, timezone
        mtime_iso = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()
except Exception:
    mtime_iso = None
```
**Source:** `services/trading-engine/app/main.py:282`, `auto_trader.py:874`. **Verified on disk 2026-05-13:** `./EMERGENCY_STOP` is currently a DIRECTORY (`ls -la` returns dir contents, mtime 2026-05-07). `is_file()` correctly returns False; mtime will be `null` until operator runs `rmdir EMERGENCY_STOP && touch EMERGENCY_STOP`.

### Anti-Patterns to Avoid

- **`.get()` on `proxy_request` return value** — it's a `JSONResponse`, not a dict. Decode first.
- **`os.environ.get(...)` without compose plumbing** — verify the var is in the compose env block; default values mask missing-env bugs.
- **`Path.exists()` for bind-mount files** — use `is_file()` per CLAUDE.md WSL gotcha.
- **Hardcoded URLs in frontend/src/** — D-16 grep gate catches this. Use `import.meta.env.VITE_*` with documented fallback.
- **Patching `builtins.open` to test pathlib reads** — pathlib bypasses builtins.open (per project memory). Patch `pathlib.Path.write_text` / `read_text` / `is_file` directly.
- **Asserting `.data` after axios interceptor strip** — the existing interceptor at `services/api.js:33-39` already unwraps `.data`. Don't double-unwrap in hooks (verified in Plan 6-04 T1 action — correct).
- **forceStale suppressing error rendering** — Plan 6-05 Task 1 behavior 7 says "forceStale shows the stale badge regardless of lastUpdatedAt". Should this also show stale-badge if `query.isError`? The intent of D-13 "errors are loud" says NO — error wins over stale. Document the precedence: error > loading > empty > stale > success. Test 7 in Plan 6-05 needs explicit "+ when forceStale AND isError, render error UI (not stale badge)" — currently ambiguous.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Polling interval + retry + cache | Custom `useEffect` + `setInterval` | `@tanstack/react-query` `useQuery` | Already installed; handles dedupe, backoff, focus/reconnect refetch, in-flight cancellation. |
| HTTP client + error normalization | `fetch` + manual try/catch | `axios` via `services/api.js` | Already exports an instance with `/api` baseURL, 20s timeout, interceptor that strips `.data` and lifts error.response. |
| FastAPI client to backend service | Custom `httpx` calls in main.py | `ServiceProxy.proxy_request` | Existing wrapper at `services/service_proxy.py:47-160` — timeout handling, error mapping, JSONResponse wrapping. |
| ANSI colors in CLI script | Custom escape codes | Copy from `scripts/monitor.py:30-58` | Pattern already exists in repo; PATTERNS.md line 494 documents. |
| File-mtime → ISO timestamp | Custom string formatting | `datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()` | Standard library; matches existing health.py `last_checked` formatting. |
| Editorial palette tokens | New shared `tokens.js` module | Inlined `C` object | Per PATTERNS.md line 618: explicitly out of scope for this phase. |
| State machine for tile rendering | Reducer + state machine library | React Query's `isLoading/isFetching/isError/isSuccess` flags + props | All four signals already on the query result; TileState is just a switch statement. |
| Test runner config | New `vitest.config.js` separate file | The existing `test:` block inside `vite.config.js:205-211` | Vitest reads from `vite.config.js` automatically — no separate config file needed. |

**Key insight:** Phase 6 is overwhelmingly composition of existing pieces — no new infrastructure decisions needed. The risk is mechanical (wrong field name, wrong type, missing env) not architectural.

---

## Runtime State Inventory

> Phase 6 is a config/code change — no rename, no datastore migration, no OS-registered state to update. Most categories empty.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None | None |
| Live service config | api-gateway compose env block is MISSING `TRADING_MODE`/`PAPER_TRADING_MODE`/`ENABLE_ML_PREDICTIONS` — see F-04 | Patch `docker-compose.unified.yml:253-282` |
| OS-registered state | None | None |
| Secrets/env vars | `LIVE_TRADING_ACK` env-name unchanged; not affected by Phase 6 (but consider surfacing in D-08 schema — see F-04 also-recommended) | None |
| Build artifacts | Frontend Vite build will bundle `VITE_WS_URL` and `VITE_API_BASE_URL` defaults at build time | Document in `vite.config.js` doc block (Plan 6-03 already does) |
| Bind-mount on disk | `./EMERGENCY_STOP` is currently a DIRECTORY (empty, mtime 2026-05-07) — confirmed via `ls -la` | `is_file()` guard handles this; no action. Operator must `rmdir && touch` if they want to populate mtime in dev. |

---

## Common Pitfalls

### Pitfall 1: Testing against wrong response shape masks F-01/F-02

**What goes wrong:** Plan 6-02 Test 9 builds a mock `{"emergency_mode": {"armed": True, "active": False}, ...}` — a shape that does NOT exist in real production. Tests pass green; production crashes with `AttributeError`.
**Why it happens:** Plan author assumed the field shape from D-04's prose ("armed vs tripped") without verifying the response model.
**How to avoid:** When mocking external HTTP responses, the mock body MUST be a verbatim copy from a real response (curl against running stack) or from the explicit `Config.json_schema_extra.example` block in the Pydantic model. Never invent the shape from natural-language requirements.
**Warning signs:** Test passes locally but live curl returns 500 / different shape. Schema docs in `Field(description=...)` mention "bool" but mock builds a dict.

### Pitfall 2: `proxy_request` return type confusion (F-03)

**What goes wrong:** Treating the `JSONResponse` return from `ServiceProxy.proxy_request` as a dict.
**Why it happens:** PATTERNS.md analog code (lines 354-365) and Plan 6-02 action both omit the `json.loads(resp.body.decode())` step.
**How to avoid:** Search `services/api-gateway/app/main.py` for the pattern `json.loads.*body.decode` (one hit at line 271 — the `fetch_dashboard_updates` method). Copy that pattern verbatim.
**Warning signs:** `AttributeError: 'JSONResponse' object has no attribute 'get'` at first real call. Tests pass because the test mock returns a raw dict from `proxy_request` (incorrect mock).

### Pitfall 3: Hardcoded `daily_loss_armed: True` masks disarmed kill-switch

**What goes wrong:** PATTERNS.md line 376 has `"daily_loss_armed": True` as a stale literal. Plan 6-02 explicitly calls this out (B-01 override) and adds a grep gate. **Good.** The pitfall is downstream — if someone refactors Plan 6-02's code later without re-reading the B-01 commentary, they may simplify back to the literal.
**Why it happens:** "Always-armed per RISK-01" is project policy in CLAUDE.md ("Project rules" → "5%-daily-loss circuit-breaker (always)") — so the literal "feels right". The point of D-04 sourcing is to surface gateway-vs-engine disconnection, not the engine-internal armed/disarmed state.
**How to avoid:** Keep the B-01 grep gate (`grep -nE 'daily_loss_armed.*:\s*True\s*[,}]'` returns 0) in Plan 6-02. Add a code comment: `# daily_loss_armed reflects whether the risk-budget module is reachable — True when te_budget != {}`.
**Warning signs:** Grep gate trips; or operator-perceived state diverges from trading-engine logs.

### Pitfall 4: Stale-in-memory false-pass after gateway env change

**What goes wrong:** Operator sets `TRADING_MODE=LIVE` in `.env`, restarts trading-engine container, reloads dashboard. UI still shows PAPER pill because api-gateway wasn't restarted — its `os.environ` is the boot-time snapshot.
**Why it happens:** CLAUDE.md "Verification standards" explicitly calls this out: "Stale in-memory state = most common false-pass."
**How to avoid:** Plan 6-04 Task 2 acceptance criterion already requires gateway restart on TRADING_MODE flip. Make sure the manual smoke step uses `docker compose restart api-gateway` (NOT just `docker exec ... reload`).
**Warning signs:** Test pass green; manual smoke shows wrong pill. Logs show old TRADING_MODE value at gateway boot.

### Pitfall 5: Vitest separate-config conflict (Plan 6-04 Task 0 Branch B)

**What goes wrong:** Branch B creates `frontend/vitest.config.js`. Existing `vite.config.js:205-211` already has a `test:` block. Two configs compete (vitest reads vite.config.js's test block automatically). The new file with a different `setupFiles` (`./src/test-setup.js` vs existing `./src/__tests__/setup.js`) breaks the existing 2 tests at `frontend/src/__tests__/PerformanceDashboard.test.jsx` and `performance.test.jsx`.
**Why it happens:** Plan 6-04 Task 0's "Branch A vs Branch B" detection logic checks for `vitest.config.js` existence — but the real signal is the inline `test:` block in vite.config.js, which Branch B's detector misses.
**How to avoid:** Branch A wins. Skip the install step entirely. The `files_modified` line `frontend/vitest.config.js` in Plan 6-04's frontmatter is a planning-time error — record in SUMMARY that it was NOT touched.
**Warning signs:** New tests fail with `Cannot find module '@/services/api'`; existing tests stop running.

### Pitfall 6: Frontend dev proxy bypass hides gateway middleware in dev

**What goes wrong:** `frontend/vite.config.js` dev proxy at lines 53-165 routes `/api/portfolio/...` directly to `portfolio-manager:8003` (NOT through the gateway). The new `/api/config/safety-state` route has no specific proxy rule, so it falls through to the catch-all at line 158 (`/api → localhost:8000`, the gateway). **This works.** But if a dev tests `npm run dev` against a stack without api-gateway running, they will see "connection refused" for safety-state while every other tile works. Confusing.
**Why it happens:** Documented in vite.config.js comment block (lines 16-41). Dev proxy bypasses gateway middleware as a feature.
**How to avoid:** Plan 6-04 manual smoke step MUST `docker compose up api-gateway` first. Plan 6-03's doc-block extension should explicitly mention "the new `/api/config/safety-state` route is gateway-only — running dev without api-gateway will fail this one request."
**Warning signs:** safety-state hook returns network error; all other tiles fine.

### Pitfall 7: TileState state-machine precedence ambiguity

**What goes wrong:** Plan 6-05 Task 1 lists 8 behaviors but doesn't make precedence explicit. What if `query.isError && forceStale === true`? Should the tile show "Failed (...)" or the stale badge?
**Why it happens:** D-13 lists four states but doesn't specify mutual exclusion order.
**How to avoid:** Define explicit precedence in TileState.jsx: **error > loading > empty > stale-badge-on-children > children**. `forceStale` only suppresses the success-without-stale-marker rendering; errors and loading still win.
**Warning signs:** LABELED_STALE tile whose endpoint dies shows "stale" badge instead of "Failed (...)". Operator misses the broken endpoint.

### Pitfall 8: `daily_pnl_pct` silently stuck at 0.0 (F-02)

**What goes wrong:** `te_budget.utilization.daily_pnl_pct` doesn't exist — `.get(..., 0.0)` always returns 0.0. The kill-switch tile shows "Daily P&L: 0%" even after a 4% drop.
**Why it happens:** Plan + PATTERNS.md inherited a field name from D-08 schema design (intuitive) without checking what the backend actually returns.
**How to avoid:** Per F-02 fix, either backend extension or schema rename. Either way, add a test that mocks `{"utilization": {"daily_pnl_pct": -2.5}}` AND asserts the gateway response reflects -2.5 — not the default zero.
**Warning signs:** kill-switch cell stuck at 0% in any operational scenario including known losses.

---

## Code Examples

### Example 1: Decode JSONResponse from `proxy_request` (corrects F-03)

```python
# Source: services/api-gateway/app/main.py:271 (existing pattern)
import json

try:
    resp = await proxy.proxy_request("trading-engine", "/status", "GET")
    te_status = json.loads(resp.body.decode()) if resp.status_code == 200 else {}
except Exception:
    te_status = {}
```

### Example 2: `emergency_stop.mtime` with WSL is_file guard (Plan 6-02 T1)

```python
# Source: services/trading-engine/app/auto_trader.py:874 + main.py:282 (existing precedent)
mtime_iso = None
try:
    p = auto_trader.emergency_stop_file
    if p.is_file():
        from datetime import datetime, timezone
        mtime_iso = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()
except Exception:
    mtime_iso = None

emergency_stop_state = {
    "file_path": str(auto_trader.emergency_stop_file),
    "active": auto_trader.emergency_stop_active,
    "mtime": mtime_iso,                              # ← NEW for D-08
    "last_checked": (...)
    "auto_trader_running": auto_trader.is_running,
}
```

### Example 3: TileState state-machine precedence (Plan 6-05 T1)

```jsx
// Precedence: error > loading > empty > stale-overlay > children
export default function TileState({query, isEmpty, lastUpdatedAt, staleAfterMs,
                                   thresholdKey, title, forceStale, children}) {
  const threshold = staleAfterMs ?? STALE_THRESHOLDS_MS[thresholdKey] ?? STALE_THRESHOLDS_MS.default
  const _isEmpty = isEmpty ?? ((d) => d == null || (Array.isArray(d) && d.length === 0))

  // 1. Error wins (D-13 "errors are loud")
  if (query.isError) {
    const code = query.error?.response?.status ?? 'network'
    const msg = query.error?.response?.data?.detail ?? query.error?.response?.statusText ?? 'request failed'
    return (
      <div style={{position:'relative'}}>
        <div>Failed ({code}): {msg}.</div>
        <button onClick={() => query.refetch()}>Retry</button>
      </div>
    )
  }
  // 2. Loading
  if (query.isLoading && !query.data) {
    return <div className="skeleton">{/* skeleton blocks */}</div>
  }
  // 3. Empty
  if (query.isSuccess && _isEmpty(query.data)) {
    return <div>No data yet</div>
  }
  // 4. Stale-overlay on success (NOT on error)
  const stale = forceStale || (lastUpdatedAt && Date.now() - new Date(lastUpdatedAt).getTime() > threshold)
  return (
    <div style={{position:'relative'}}>
      {children}
      {stale && <span style={{position:'absolute', top:0, right:0, color:'#8a8982'}}>stale</span>}
    </div>
  )
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Polling without `staleTime`/`refetchOnWindowFocus` overrides | Global QueryClient defaults set `refetchOnWindowFocus: false` + `staleTime: 10s` | main.jsx as of v5 migration | useSafetyState inherits sane defaults; no need to add `refetchOnWindowFocus` per-hook. |
| React Query v4 `keepPreviousData` | v5 `placeholderData` | Migrated in main.jsx (comment at :66-67) | Plan 6-05 TileState should NOT rely on `keepPreviousData` — it's deprecated. |
| `border: …px solid …` for viewport accent | `outline: …px solid …` with negative offset | Plan 6-04 T2 (D-06 rationale) | No layout shift on safety-state hydration; PATTERNS.md line 230 documents. |
| Custom config module (`frontend/src/config.js`) | Direct `import.meta.env.VITE_*` reads | D-16 explicit defer to v2 | One env-var migration only this phase; full module is a Phase 7+ refactor. |

**Deprecated/outdated:**
- `keepPreviousData` (React Query v4) — use `placeholderData` per-query in v5.
- `npm run test -- --run --passWithNoTests` flag pattern from Plan 6-04 Task 0 — actual frontend uses `npm run test:run` script.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | F-01 Option A ("daily_loss_armed always True per RISK-01") matches operator intent | F-01 | Operator may want a real disarm signal (none exists in code today). If wrong, choose Option B (backend addition). |
| A2 | Adding `daily_pnl_pct` to `utilization` dict (F-02 Option A) is the right backend change | F-02 | If risk-budget refactor in Phase 7 changes the manager interface, this field may need re-derivation. Acceptable risk. |
| A3 | LIVE_TRADING_ACK surfacing is Phase 7 polish, not Phase 6 must-have | F-04 also-rec | If operator considers the "UI shows LIVE while engine refuses to boot" gap critical, add to Phase 6 scope. |
| A4 | Stale-overlay-wins-over-error precedence is wrong; error should win | Pitfall 7 | If D-13 actually intends stale to win over error (operator wants quiet failure on known-stale tiles), revise. Currently no test covers this case. |

All other claims in this research are verified against committed source (file:line citations).

---

## Open Questions

1. **Should `/api/config/safety-state` include a `live_trading_acknowledged` field?**
   - What we know: trading-engine refuses to boot with `TRADING_MODE=LIVE` AND missing `LIVE_TRADING_ACK` (main.py:251-258).
   - What's unclear: whether D-03's "five flags" intent leaves room for a sixth derived flag.
   - Recommendation: defer to Phase 7 (matches "BYBIT_TESTNET shown via vite.config.js doc, not strip" pattern from D-06).

2. **Plan 6-01 audit scope: does `Settings.jsx` truly have no data tiles?**
   - What we know: CONTEXT.md and PATTERNS.md both say "Settings page has no data tiles — skip".
   - What's unclear: Verified Settings.jsx not read directly in this research.
   - Recommendation: Plan 6-01 Task 1 includes a one-line grep of `frontend/src/pages/Settings.jsx` for `useQuery|api.get` calls — if zero, the skip is correct. If non-zero, audit it.

3. **Does Plan 6-05 Task 2 commit-per-page-group strategy work when a tile is shared across pages?**
   - What we know: `Dashboard.jsx` imports 12 of 14 tiles; `Phase1Dashboard`/`Phase3Dashboard`/`Portfolio` import subsets. A tile like `ActiveTrades` may appear on multiple parents.
   - What's unclear: which "page group" owns a shared tile's commit.
   - Recommendation: tile component file edits (FIXED + LABELED_STALE wraps) commit per **component group**, not per page. Three commits: (a) Phase1/Phase3-exclusive tiles, (b) Portfolio-exclusive tiles, (c) Dashboard.jsx tiles (the home-page tiles, which are the majority). REMOVED-tile parent-page deletions can land in the same commit as their corresponding component group, OR in a separate "parent-page cleanup" commit.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node + npm | frontend build, vitest | ✓ | from package-lock.json | — |
| vitest | frontend tests (Plan 6-04, 6-05) | ✓ | ^1.6.0 (in devDeps) | — |
| jsdom | vitest env | ✓ | ^24.0.0 | — |
| @testing-library/react | component tests | ✓ | ^14.2.0 | — |
| Python 3.12 | scripts/audit_tiles.py, backend tests | ✓ (per repo) | — | — |
| requests / httpx | audit_tiles HTTP probe | requests already used in `scripts/check_ml_training_status.py` | — | — |
| Docker + docker-compose | running stack for verification | ✓ | per CLAUDE.md | — |
| crypto-bot-api-gateway container | pytest in-container | ✓ | fastapi 0.109 pinned | host-level pytest will spuriously fail per CLAUDE.md "Gotchas" |
| `EMERGENCY_STOP` repo-root path | trading-engine read | ✓ but is DIRECTORY | mtime 2026-05-07 | `is_file()` returns False; mtime emits null — correct fail-safe |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:**
- vitest from Plan 6-04 Task 0 Branch B install — NOT needed (Branch A applies). No fallback required.

---

## Validation Architecture

> Required per `workflow.nyquist_validation` default (config.json check). This section drives a follow-up `06-VALIDATION.md`.

### Test Framework

| Property | Value |
|----------|-------|
| Backend framework | pytest (per-service) + `docker exec` for api-gateway |
| Backend config | `services/api-gateway/tests/conftest.py` (test_client + admin_client fixtures); `services/trading-engine/tests/` (no central conftest in this dir) |
| Frontend framework | vitest 1.6.0 + @testing-library/react |
| Frontend config | `vite.config.js:205-211` (`test:` block, jsdom env, `./src/__tests__/setup.js` setupFiles) |
| Quick run (gateway) | `docker exec crypto-bot-api-gateway pytest /app/tests/test_safety_state.py -x` |
| Quick run (trading-engine) | `pytest services/trading-engine/tests/test_health_status.py -x` |
| Quick run (frontend) | `cd frontend && npm run test:run -- TileState StatusBar useSafetyState` |
| Full suite (frontend) | `cd frontend && npm run test:run` |
| Full suite (audit) | `python3 scripts/audit_tiles.py --against http://localhost:8000` |
| Regression harness | `verify-stack` skill (per CLAUDE.md "Verification standards") |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DASH-01 | 06-TILE-AUDIT.md has row per tile with verdict ∈ {FIXED, LABELED_STALE, REMOVED} | smoke | `python3 -c "import json; d=json.load(open('.planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.json')); assert len(d['tiles']) >= 15"` | ❌ Plan 6-01 produces |
| DASH-01 | audit_tiles.py probes documented endpoints and asserts shape | unit | `pytest scripts/test_audit_tiles.py -x` | ❌ Plan 6-01 T2 produces |
| DASH-01 | audit_tiles.py against running stack PASS | integration | `python3 scripts/audit_tiles.py --against http://localhost:8000` | ❌ Plan 6-01 + 6-05 |
| DASH-02 | useGatewayWebSocket.js:34 reads VITE_WS_URL with fallback | smoke | `grep -nE "VITE_WS_URL\s*\|\|\s*'ws://localhost:8000/ws'" frontend/src/hooks/useGatewayWebSocket.js` returns 1 match | ❌ Plan 6-03 |
| DASH-02 | grep gate enforces no hardcoded URLs | smoke | `bash frontend/scripts/check-no-hardcoded-urls.sh` exits 0 | ❌ Plan 6-03 |
| DASH-03 | /api/config/safety-state returns D-08 schema | behavior | `docker exec crypto-bot-api-gateway pytest /app/tests/test_safety_state.py -x` | ❌ Plan 6-02 produces |
| DASH-03 | /status emits emergency_stop.mtime | behavior | `pytest services/trading-engine/tests/test_health_status.py -x` | ❌ Plan 6-02 produces |
| DASH-03 | useSafetyState polls every 5s | unit | `cd frontend && npm run test:run -- useSafetyState` | ❌ Plan 6-04 produces |
| DASH-03 | StatusBar shows MODE/KILL-SWITCH/ML cells + mtime in emergency_stop cell | unit | `cd frontend && npm run test:run -- StatusBar` | ❌ Plan 6-04 produces |
| DASH-03 | LIVE flip → viewport border turns rose | manual-only | Manual smoke per Plan 6-04 T2 acceptance | ❌ Manual checkpoint |
| DASH-03 | safety-state stays 200 when trading-engine down (graceful) | behavior | `docker stop crypto-bot-trading-engine && curl -sS http://localhost:8000/api/config/safety-state \| jq '.kill_switch.tripped'` returns `false` | ❌ Plan 6-02 |
| DASH-05 | TileState state machine renders all four states | unit | `cd frontend && npm run test:run -- TileState` | ❌ Plan 6-05 T1 produces |
| DASH-05 | gateway-down → every FIXED tile shows "Failed (...)" + Retry | manual-only + integration | Plan 6-05 T3 manual smoke + audit_tiles.py | ❌ Manual checkpoint |
| DASH-05 | empty endpoint → tile shows "No data yet" not blank | manual-only | Plan 6-05 T3 manual smoke | ❌ Manual checkpoint |
| DASH-05 | LABELED_STALE tile shows badge regardless of last_updated_at | unit | `cd frontend && npm run test:run -- TileState` (Test 7) | ❌ Plan 6-05 T1 |

### Sampling Rate

- **Per task commit:** quick-run for the touched file's domain (gateway pytest, trading-engine pytest, vitest for the touched component, OR grep gate for Plan 6-03).
- **Per wave merge:** full suite green:
  - Wave 1 (plans 6-01, 6-02, 6-03): `docker exec crypto-bot-api-gateway pytest /app/tests/test_safety_state.py -x` + `pytest services/trading-engine/tests/test_health_status.py -x` + `pytest scripts/test_audit_tiles.py -x` + `bash frontend/scripts/check-no-hardcoded-urls.sh`.
  - Wave 2 (plans 6-04, 6-05): Wave 1 commands + `cd frontend && npm run test:run` + `python3 scripts/audit_tiles.py --against http://localhost:8000`.
- **Phase gate:** All of the above + `verify-stack` skill checklist (live exchange URL, real DB row, gateway restart after env change, no shallow HTTP-200 false-pass).

### Acceptance Evidence Chain per Success Criterion

**ROADMAP Phase 6 success criterion 1** (every tile documented + verified):
1. `06-TILE-AUDIT.md` committed with all rows.
2. `python3 scripts/audit_tiles.py --against http://localhost:8000` exits 0.
3. Operator approves verdict column (Plan 6-01 Task 3 resume signal).

**ROADMAP Phase 6 success criterion 2** (operator sees safety state at first glance):
1. `curl -sS http://localhost:8000/api/config/safety-state | jq` returns D-08 schema (paste to SUMMARY).
2. Manual smoke: StatusBar shows MODE/KILL-SWITCH/ML cells + emergency_stop with mtime (Plan 6-04 T1 acceptance).
3. Manual smoke: `TRADING_MODE=LIVE` flip → rose viewport border + LIVE pill (both flip from same poll, Plan 6-04 T2 acceptance).
4. `verify-stack` skill PASS after gateway restart (Plan 6-02 T2 acceptance).

**ROADMAP Phase 6 success criterion 3** (no hardcoded backend URLs):
1. `bash frontend/scripts/check-no-hardcoded-urls.sh` exits 0.
2. `grep -rn "http://localhost\|ws://localhost" frontend/src/` shows only documented defaults (line in useGatewayWebSocket.js after `||` + doc comment in services/api.js).
3. Negative test: temp file with hardcoded URL triggers script non-zero exit (Plan 6-03 T2 acceptance).

**ROADMAP Phase 6 success criterion 4** (explicit empty/error states):
1. `cd frontend && npm run test:run -- TileState` passes (8 tests).
2. Manual smoke: `docker stop crypto-bot-trading-engine` → tile shows "Failed (...)" + Retry (Plan 6-05 T3).
3. Manual smoke: tile whose endpoint returns `[]` → "No data yet" (Plan 6-05 T3).
4. Python coverage gate: every FIXED/LABELED_STALE verdict row in 06-TILE-AUDIT.json maps to a file containing `TileState`.

### Wave 0 Gaps

> Tests/fixtures needed before implementation. All gaps below are produced by the listed plan, not by a separate Wave 0.

- [ ] `scripts/test_audit_tiles.py` — covers DASH-01 audit script behavior (Plan 6-01 T2)
- [ ] `services/trading-engine/tests/test_health_status.py` — covers DASH-03 mtime field (Plan 6-02 T1)
- [ ] `services/api-gateway/tests/test_safety_state.py` — covers DASH-03 endpoint behavior (Plan 6-02 T2)
- [ ] `frontend/src/hooks/__tests__/useSafetyState.test.js` — Plan 6-04 T1
- [ ] `frontend/src/components/__tests__/StatusBar.test.jsx` — Plan 6-04 T1
- [ ] `frontend/src/components/__tests__/TileState.test.jsx` — Plan 6-05 T1
- [ ] App.jsx test for safety-border className flip (Plan 6-04 T2)

**Framework install:** None needed (vitest already in devDeps per F-04 finding above).

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | New endpoint is intentionally unauthenticated (D-09 read-only config disclosure) |
| V3 Session Management | no | No new session state |
| V4 Access Control | yes (negative) | `/api/config/safety-state` returns ONLY config flags + booleans, NO secrets, balances, or API keys; verified by D-08 schema audit. Per D-09 Discretion: "If gateway grows public exposure later, reconsider." |
| V5 Input Validation | yes | New route has no input params (GET, no query string consumed). audit_tiles.py `--against` flag is operator-supplied URL; argparse validates type. |
| V6 Cryptography | no | No new crypto. |
| V7 Error Handling | yes | TileState error UI uses `error.response.data.detail` (server-controlled text rendered as JSX text node — escaped). NO `error.message` rendering (D-14 forbids; covers stack-trace leak). |
| V8 Data Protection | yes (limited) | Endpoint discloses `TRADING_MODE`, `auto_trading_enabled`, `kill_switch` state. All accepted in T-06-02-01/T-06-04-03/T-06-02-03 threat-register entries as same-operator threat model (no public exposure). |
| V12 File and Resources | yes | EMERGENCY_STOP file path read via `Path.is_file()` + `stat()` — no symlink-follow vulnerability beyond what already exists in trading-engine. |
| V14 Configuration | yes | New compose env vars (per F-04) inject TRADING_MODE etc. into api-gateway — same threat model as the trading-engine's existing env-read. |

### Known Threat Patterns for the safety-state subsystem

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Stale gateway env shows LIVE while engine refuses to boot | Spoofing | Add `live_trading_acknowledged` to D-08 (recommend) OR document the gap in operator runbook |
| Hardcoded `daily_loss_armed: True` masks disarmed breaker | Spoofing | B-01 grep gate (Plan 6-02 acceptance) — already present |
| forceStale flag suppresses real error rendering | Tampering | Pitfall 7 — make error precedence explicit in TileState |
| XSS via `error.response.data.detail` text | Spoofing/Tampering | JSX text-node escaping (React default) + D-14 disallows raw `error.message` |
| Public access to `/api/config/safety-state` | Information Disclosure | Accepted in T-06-02-01 (single-operator threat model); reconsider if gateway becomes public |
| Audit_tiles --against accepts arbitrary URL | Tampering | Argparse default kept localhost-only; operator can target prod URL with explicit flag (T-06-01-01 mitigation already in Plan 6-01) |

---

## Sources

### Primary (HIGH confidence)

- `services/api-gateway/app/main.py` (lines 240-290, 540-580, 1027-1034) — proxy_request body decode pattern, /health analog, /api/trading/status analog.
- `services/api-gateway/app/services/service_proxy.py` (lines 18-200) — JSONResponse return type, timeout settings, error mapping.
- `services/trading-engine/app/handlers/health.py` (lines 180-235) — current `get_status` shape; emergency_stop_state dict.
- `services/trading-engine/app/handlers/risk_budget.py` (lines 30-130, 378-455) — CurrentBudgetResponse schema (emergency_mode: bool, utilization dict keys).
- `services/trading-engine/app/risk/dynamic_risk_budget.py` (lines 116, 132, 351-362, 1157, 1265) — `_emergency_mode: bool`, `_daily_pnl`, trip threshold.
- `services/trading-engine/app/models/response.py` (lines 24-33) — StatusResponse fields, emergency_stop is `Optional[Dict]`.
- `services/trading-engine/app/main.py` (lines 240-290, 485-490) — `/status` route, LIVE_TRADING_ACK gate, is_file() guard precedent.
- `services/trading-engine/app/auto_trader.py` (lines 230-250, 842-882) — emergency_stop_file, is_running, emergency_stop_active attributes.
- `frontend/src/components/StatusBar.jsx` (full file) — Cell helper, existing hooks at lines 49-51, palette tokens.
- `frontend/src/hooks/useGatewayWebSocket.js` (lines 31-36) — line 34 target literal.
- `frontend/src/components/Dashboard.jsx` (lines 1-13) — tile imports proving F-05 (Dashboard.jsx imports 12 audited tiles).
- `frontend/src/App.jsx` (line 30) — Dashboard route registration.
- `frontend/vite.config.js` (lines 16-41, 205-211) — dev/prod proxy doc, **inline vitest config**.
- `frontend/package.json` (lines 11, 14-44) — vitest 1.6.0 + jsdom + testing-library already in devDeps.
- `frontend/src/main.jsx` (lines 47-74) — QueryClient defaults (refetchOnWindowFocus: false).
- `frontend/src/__tests__/setup.js` (line 1) — existing setup file path.
- `docker-compose.unified.yml` (lines 245-307) — api-gateway env block (missing TRADING_MODE etc.).
- `CLAUDE.md` (project rules, gotchas, verification standards) — gateway route convention, fastapi version asymmetry, WSL bind-mount race, EMERGENCY_STOP semantics.

### Secondary (MEDIUM confidence)

- Existing tile component reads (KeyMetricsStrip.jsx, ActiveTrades.jsx) — referenced via PATTERNS.md line citations rather than full read; pattern descriptions trusted.
- React Query v5 default behavior (`refetchOnWindowFocus`, `staleTime`) — confirmed by main.jsx project-internal default override at line 54.

### Tertiary (LOW confidence)

None — all load-bearing findings are verified against committed source.

---

## Metadata

**Confidence breakdown:**
- Plan revisions (F-01..F-05): HIGH — each cites the exact file:line where the actual shape contradicts the planned shape.
- Validation Architecture: HIGH — every command verified against existing repo conventions or plan-acceptance text.
- Architectural responsibility map: HIGH — derived from CONTEXT.md decisions D-08..D-15 + verified code paths.
- Pitfalls: HIGH (mostly) — Pitfall 7 (TileState precedence) is reasoned-from-D-13 not verified-in-code (the component doesn't exist yet); flagged as A4 in assumptions log.

**Research date:** 2026-05-13

**Valid until:** Stable for ~30 days as long as:
- `CurrentBudgetResponse.emergency_mode` stays a flat bool (no Phase 7 schema refactor).
- `ServiceProxy.proxy_request` keeps returning JSONResponse (current implementation since at least 2026-04 per service_proxy.py file shape).
- vitest stays at 1.6.0 in package.json (any major upgrade would invalidate Plan 6-04 Task 0 assumptions).

**If `06-VALIDATION.md` is generated:** consume the `## Validation Architecture` section above verbatim.
