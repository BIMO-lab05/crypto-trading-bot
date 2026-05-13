# Phase 6: Dashboard Audit & Safety State - Pattern Map

**Mapped:** 2026-05-13
**Files analyzed:** 9 new/modified targets (+ ~15 audit-refactor tile sites)
**Analogs found:** 9 / 9 (every new/modified file has at least a strong analog in-repo)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `frontend/src/components/TileState.jsx` *(new)* | shared frontend wrapper component | render-driven by React Query status + backend `last_updated_at` | `frontend/src/components/StatusBar.jsx` `Cell` helper + `KeyMetricsStrip.jsx` `Cell` `isLoading` skeleton + `ActiveTrades.jsx` `isLoading` early-return | exact (3 partial sources combined) |
| `frontend/src/hooks/useSafetyState.js` *(new)* | frontend React-Query polling hook | request-response, 5s poll | `frontend/src/hooks/usePortfolio.js` `usePortfolio()` + `usePositions.js` `useTradingStatus()` | exact |
| `frontend/src/components/StatusBar.jsx` *(modify)* | fixed-bottom safety strip | read-only display, multi-hook compositor | self (already in repo; extend `Cell` pattern + add hook) | self-reference (in-place extension) |
| `frontend/src/App.jsx` *(modify)* | root layout / route shell | wrap content with class-driven border | self (already wraps `<ToastProvider>`, mounts `<StatusBar/>` at bottom) | self-reference |
| `frontend/src/hooks/useGatewayWebSocket.js` *(modify line 34)* | env-var migration only | unchanged | self | self-reference |
| `frontend/vite.config.js` *(modify — doc block)* | dev/prod URL convention doc | n/a | self (already carries the dev/prod block at lines 16-40) | self-reference |
| `services/api-gateway/app/main.py` *(modify — new route)* | FastAPI gateway route, fan-out aggregator | request-response, reads local env + proxies trading-engine | `services/api-gateway/app/main.py:1027` `get_trading_status` (proxy passthrough) + `services/api-gateway/app/main.py:544` `health_check` (env + fan-out) | exact (two analogs in same file) |
| `services/trading-engine/app/handlers/health.py` *(modify — `get_status`)* | extend status to surface `emergency_stop.mtime` | file-stat read | self at `services/trading-engine/app/handlers/health.py:183-232` (already builds `emergency_stop_state` dict) | self-reference (extend dict) |
| `scripts/audit_tiles.py` *(new)* | operational Python CLI script | one-shot HTTP probe → shape assert → PASS/FAIL exit | `scripts/check_ml_training_status.py` (HTTP-probe + summary + recommendations) + `scripts/monitor.py` (services table + httpx + ANSI colors) | exact |
| `.planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.md` *(new doc artifact)* | markdown table only, no code | n/a | none required — operator artifact | n/a |

---

## Pattern Assignments

### `frontend/src/components/TileState.jsx` (shared wrapper, React Query consumer)

**Combined analogs:** `StatusBar.jsx` `Cell` (lines 26-46) for editorial styling tokens; `KeyMetricsStrip.jsx` `Cell` (lines 65-143) for the **loading skeleton** pattern + corner-tick decoration; `ActiveTrades.jsx` lines 68-79 for the loading-state early return.

**Imports + color tokens to copy** (lift from `KeyMetricsStrip.jsx:40-52`):
```jsx
import React from 'react'

// Color tokens lifted from performance-theme.css. Inlined for components
// outside .perf-page where the CSS variables aren't in scope.
const C = {
  bg: '#0a0a0b',
  surface: '#18181c',
  surface2: '#1f1f24',
  border: '#2a2a32',
  borderStrong: '#3a3a44',
  text: '#f5f3ee',
  text2: '#a09e98',
  text3: '#8a8982',
  gain: '#5eead4',
  loss: '#fb7185',
  gold: '#d4af6a',
}
```

**Loading skeleton pattern to copy** (from `KeyMetricsStrip.jsx:105-110`):
```jsx
isLoading ? (
  <div className="space-y-1.5">
    <div className="h-7 rounded" style={{ background: C.surface2, width: hero ? '70%' : '60%' }} />
    <div className="h-3 rounded" style={{ background: C.surface2, width: '40%' }} />
  </div>
) : (
  // render body
)
```

**Editorial corner-tick decoration to copy** (from `KeyMetricsStrip.jsx:77-91`):
```jsx
<span
  aria-hidden="true"
  style={{
    position: 'absolute', top: -1, left: -1, width: 8, height: 8,
    borderTop: `1px solid ${C.text3}`, borderLeft: `1px solid ${C.text3}`,
  }}
/>
<span
  aria-hidden="true"
  style={{
    position: 'absolute', bottom: -1, right: -1, width: 8, height: 8,
    borderBottom: `1px solid ${C.text3}`, borderRight: `1px solid ${C.text3}`,
  }}
/>
```

**API for callers** (D-12 contract — TileState consumes React Query's `useQuery` result + optional `lastUpdatedAt`):
```jsx
// Example call site (refactor inside e.g. ActiveTrades.jsx)
const q = usePositions()
return (
  <TileState
    query={q}                                  // { isLoading, isFetching, isError, isSuccess, error, data, refetch }
    isEmpty={(d) => !d || (d.positions ?? []).length === 0}
    lastUpdatedAt={q.data?.last_updated_at}    // optional, drives stale badge
    staleAfterMs={60_000}                       // per-tile threshold (D-15)
    title="Active Trades"                      // for error message context
  >
    {/* body */}
  </TileState>
)
```

**Error rendering shape** (D-14): `Failed (HTTP code): short message [Retry]`. Pull HTTP code from `query.error?.response?.status` (axios shape — `frontend/src/services/api.js:33-39` confirms axios is the only HTTP client and exposes `error.response.data`). Retry calls `query.refetch()`.

**Stale-detection constants** (D-15 — define inside `TileState.jsx`):
```jsx
// Per-tile staleness thresholds; ms. Callers pass a key OR an explicit ms value.
export const STALE_THRESHOLDS_MS = {
  ticker: 60_000,
  signals: 30_000,
  performance: 5 * 60_000,
  portfolio: 30_000,
  positions: 30_000,
  // default if none specified
  default: 60_000,
}
```

---

### `frontend/src/hooks/useSafetyState.js` (new polling hook)

**Analog:** `frontend/src/hooks/usePortfolio.js` `usePortfolio()` + `frontend/src/hooks/usePositions.js` `useTradingStatus()`.

**Pattern to copy** (combine `usePortfolio.js:10-21` shape with the `staleTime`/`retry` knobs from `usePositions.js:55-69`):

```js
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'   // axios instance; baseURL '/api', response interceptor strips `.data`

/**
 * useSafetyState — single source of truth for the operator safety strip.
 *
 * Polls /api/config/safety-state every 5s (matches StatusBar cadence per D-11).
 * Returns the full SafetyState payload + React Query metadata.
 */
export function useSafetyState() {
  return useQuery({
    queryKey: ['safety-state'],
    queryFn: async () => {
      // response interceptor in services/api.js already unwraps `.data`
      return await api.get('/config/safety-state')
    },
    refetchInterval: 5000,   // D-11: match StatusBar/usePositions cadence
    staleTime: 5000,         // D-11
    retry: 2,
    retryDelay: 1000,
  })
}
```

**Note on path:** `api` client (`services/api.js:9-15`) has `baseURL: '/api'` with the response interceptor at `services/api.js:33-39` (`response.data`). Call site is `api.get('/config/safety-state')` → resolves to `/api/config/safety-state`. **No `v1` prefix** per CLAUDE.md "Project rules".

---

### `frontend/src/components/StatusBar.jsx` (modify — add 3 cells + safety pill)

**Self-reference.** Existing `Cell` helper at `StatusBar.jsx:26-46` is the exact shape for the 3 new cells:

```jsx
const Cell = ({ eyebrow, value, valueStyle, accent, mono = true }) => (
  <div className="flex flex-col gap-0.5 px-4 py-1.5 min-w-0" style={{ borderRight: '1px solid #2a2a32' }}>
    <span className="text-[9px] uppercase tracking-[0.18em] truncate" style={{ color: '#65645e', fontWeight: 600 }}>
      {eyebrow}
    </span>
    <span className="text-xs truncate" style={{
      color: accent || '#f5f3ee',
      fontFamily: mono ? 'JetBrains Mono, monospace' : 'Manrope, system-ui, sans-serif',
      fontFeatureSettings: '"tnum" 1',
      ...valueStyle,
    }}>
      {value}
    </span>
  </div>
)
```

**Three new cells to add** (per D-05, after the existing `P&L` cell at lines 125-129):

1. `TRADING_MODE` pill — green `#5eead4` for PAPER, red `#fb7185` for LIVE (matching existing `pnlAccent`/`runColor` palette at lines 65-72).
2. Kill-switch ARMED/TRIPPED — neutral `#a09e98` for ARMED, red `#fb7185` for TRIPPED.
3. ML toggle ON/OFF — gold `#d4af6a` for ON, neutral `#65645e` for OFF.

**Hook call to add at top of `StatusBar()`** (mirror existing hooks at lines 49-51):
```jsx
const { data: safety } = useSafetyState()
const tradingMode = safety?.trading_mode || 'PAPER'
const killSwitchTripped = !!safety?.kill_switch?.tripped
const mlOn = !!safety?.ml_predictions_enabled
```

**Imports to add at top** (mirror existing import shape line 2-3):
```jsx
import { useSafetyState } from '../hooks/useSafetyState'
```

**Keep existing breath-pulse + `aria-live="polite"` + `aria-label` block intact** — these match the existing accessibility contract.

---

### `frontend/src/App.jsx` (modify — viewport border wrapper)

**Self-reference.** Existing root container at `App.jsx:271`:
```jsx
<div className="min-h-screen bg-slate-50 dark:bg-slate-900 transition-colors duration-200">
```

**Pattern to apply** (D-06 — class-driven border, no layout shift):
```jsx
import { useSafetyState } from './hooks/useSafetyState'

function App() {
  const { data: safety } = useSafetyState()
  const mode = (safety?.trading_mode || 'PAPER').toLowerCase()
  return (
    <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ToastProvider>
        <div className={`min-h-screen bg-slate-50 dark:bg-slate-900 transition-colors duration-200 safety-border safety-border--${mode}`}>
          {/* ... existing content unchanged ... */}
        </div>
      </ToastProvider>
    </Router>
  )
}
```

**Border CSS** — add inline `<style>` block alongside the existing `kms-breath`/`sb-breath` keyframes (`StatusBar.jsx:147-152`, `KeyMetricsStrip.jsx:311-316`), OR add to an existing global CSS file. Width: 1-2px per D-06.

```css
.safety-border { outline: 1px solid transparent; outline-offset: -1px; }
.safety-border--paper { outline-color: #5eead4; }      /* mint */
.safety-border--live  { outline-color: #fb7185; }      /* rose — operator cannot miss */
```

**Why `outline` not `border`:** outline does not affect layout (no layout shift on safety-state arrival; matches D-05 "No layout-shift in `App.jsx`").

---

### `frontend/src/hooks/useGatewayWebSocket.js` (modify line 34)

**Self-reference, surgical 1-line change.** Current code at lines 31-36:
```js
function resolveUrl() {
  if (typeof window === 'undefined') return null
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  if (import.meta.env.DEV) return 'ws://localhost:8000/ws'   // ← line 34: target
  return `${protocol}//${window.location.host}/ws`
}
```

**Replacement** (D-16):
```js
function resolveUrl() {
  if (typeof window === 'undefined') return null
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  if (import.meta.env.DEV) return import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws'
  return `${protocol}//${window.location.host}/ws`
}
```

**Grep gate must pass after change** (per ROADMAP success criterion 3):
```
grep -rn "http://localhost\|ws://localhost" frontend/src/
```
Allowed remaining matches:
- `services/api.js:7` (doc comment about Vite proxy target — keep, it's documentation)
- `useGatewayWebSocket.js:34` fallback after `||` (dev-config default — keep, it's the documented fallback)

---

### `frontend/vite.config.js` (modify — extend dev/prod doc block)

**Self-reference.** Existing doc block at lines 16-41 already documents the `/api/<domain>/<resource>` vs `/api/v1/...` divergence. Extend it with the new env-var convention (D-16).

**Block to extend** (append after current line 41):
```js
/**
 * ...existing dev/prod doc block at lines 16-41...
 *
 * --- ENV VAR CONVENTION (Phase 6, DASH-02) ---
 *
 * Frontend reads two `import.meta.env.*` vars; both are optional with
 * sensible dev defaults so the unconfigured dev path keeps working:
 *
 *   VITE_API_BASE_URL  — overrides the axios `baseURL` for REST calls.
 *                        Defaults to '/api' (relative; works behind the
 *                        Vite proxy in dev and behind nginx in prod).
 *   VITE_WS_URL        — overrides the WebSocket URL used by
 *                        useGatewayWebSocket. Defaults to
 *                        'ws://localhost:8000/ws' in dev, and
 *                        `${ws/wss}://${window.location.host}/ws` in prod.
 *
 * No `http://localhost` / `ws://localhost` literal should appear in
 * frontend/src/ outside this file's doc and the documented dev fallback
 * inside useGatewayWebSocket.js — see the DASH-02 grep gate.
 */
```

---

### `services/api-gateway/app/main.py` (modify — new route `GET /api/config/safety-state`)

**Two analogs in the same file:**

**Analog A** — proxy passthrough at `services/api-gateway/app/main.py:1027-1034`:
```python
@app.get("/api/trading/status")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_trading_status():
    """Get trading bot status"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine", path="/api/v1/trading/status", method="GET"
    )
```

**Analog B** — env + fan-out aggregator at `services/api-gateway/app/main.py:544-578` (`health_check` — reads local config + calls `proxy.aggregate_health_checks()`):
```python
@app.get("/health")
async def health_check():
    """Gateway health check with backend service status"""
    proxy = get_proxy()
    health_checks = await proxy.aggregate_health_checks()
    all_healthy = all(health_checks.values())
    # ...
    return {
        "status": "healthy" if all_healthy else "degraded",
        "service": settings.service_name,
        # ...
    }
```

**New route shape to write** (per D-08/D-09 — reads gateway env + proxies trading-engine):

```python
import os
from datetime import datetime, timezone

@app.get("/api/config/safety-state")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_safety_state():
    """
    Aggregated safety/posture endpoint for the dashboard StatusBar.

    Reads gateway env (TRADING_MODE, PAPER_TRADING_MODE,
    ENABLE_ML_PREDICTIONS) and proxies trading-engine for
    `auto_trading_enabled`, `emergency_stop`, and risk-budget state.

    Unauthenticated read-only config disclosure (D-09 default).
    """
    proxy = get_proxy()

    # Read gateway-local env. Default to safe values (PAPER, ML off).
    trading_mode = os.environ.get("TRADING_MODE", "PAPER").upper()
    paper_trading_mode = os.environ.get("PAPER_TRADING_MODE", "true").lower() == "true"
    ml_predictions_enabled = os.environ.get("ENABLE_ML_PREDICTIONS", "false").lower() == "true"

    # ============================================================
    # ⚠ OVERRIDDEN by F-01 / F-03 — see 06-RESEARCH.md and 06-02 Task 2/4
    # ============================================================
    # The snippet below was the original draft and is WRONG on TWO points:
    #
    #   F-03  proxy.proxy_request() returns a FastAPI JSONResponse,
    #         NOT a dict. Calling .get(...) on it raises AttributeError
    #         on every request. The correct pattern is:
    #
    #             resp = await proxy.proxy_request(...)
    #             body = json.loads(resp.body.decode()) if resp.status_code == 200 else {}
    #
    #         Reference precedent: services/api-gateway/app/main.py:271
    #
    #   F-01  /api/v1/risk/budget/current returns `emergency_mode` as a
    #         FLAT BOOL (see services/trading-engine/app/handlers/risk_budget.py:50),
    #         NOT a dict with `.active` / `.armed` keys. The correct derivation is:
    #
    #             tripped           = bool(te_budget.get("emergency_mode", False))
    #             daily_loss_armed  = bool(te_budget)   # reachability-based
    #
    #         daily_loss_armed hardcoded to True (line 377 below) is the
    #         silent-safety-flag failure mode Phase 6 exists to eliminate.
    #
    #   F-02  utilization dict has NO `daily_pnl_pct` key; only
    #         utilization_pct / total_budget_usd / used_budget_usd /
    #         available_budget_usd. Plan 06-02 Task 2 extends
    #         get_current_budget to emit daily_pnl_pct as a top-level field;
    #         read it as te_budget.get("daily_pnl_pct", 0.0).
    #
    # DO NOT copy lines 376-380 verbatim. Plan 06-02 Task 4 carries the
    # corrected implementation; the read_first list and grep gates trip
    # on regression. This block is preserved for evidence/audit only.
    # ============================================================

    # Fan-out two reads to trading-engine.
    try:
        te_status = await proxy.proxy_request(
            service_name="trading-engine", path="/status", method="GET"
        )
    except Exception:
        te_status = {}
    try:
        te_budget = await proxy.proxy_request(
            service_name="trading-engine", path="/api/v1/risk/budget/current", method="GET"
        )
    except Exception:
        te_budget = {}

    return {
        "trading_mode": trading_mode,
        "paper_trading_mode": paper_trading_mode,
        "auto_trading_enabled": bool(te_status.get("auto_trading_enabled", False)),
        "emergency_stop": {
            "active": bool(te_status.get("emergency_stop", {}).get("active", False)),
            "mtime": te_status.get("emergency_stop", {}).get("mtime"),  # ISO ts or null
        },
        "ml_predictions_enabled": ml_predictions_enabled,
        "kill_switch": {
            "daily_loss_armed": True,
            "daily_pnl_pct": float(te_budget.get("utilization", {}).get("daily_pnl_pct", 0.0)),
            "tripped": bool(te_budget.get("emergency_mode", {}).get("active", False)),
        },
        "last_updated_at": datetime.now(timezone.utc).isoformat(),
    }
```

**Route shape per CLAUDE.md "Project rules":** `/api/<domain>/<resource>` with **no `v1` prefix**. The new resource is `/api/config/safety-state`. (Gateway-external routes are unversioned; internal `/api/v1/...` paths only exist on individual services and are the proxy targets.)

**Test pattern** — uses plain `test_client` fixture (read-only, no auth — D-09). From `services/api-gateway/tests/conftest.py:62-64`:
```python
@pytest.fixture
def test_client():
    """FastAPI test client"""
    return TestClient(app)
```

**Test environment caveat** (from CLAUDE.md "Gotchas"): tests for api-gateway MUST run inside the container (`docker exec crypto-bot-api-gateway pytest`). Host pip's fastapi 0.136 returns 401 from `HTTPBearer`; container's pinned 0.109 returns 403. The new endpoint is unauthenticated so this caveat doesn't bite directly, but other tests in the same file may regress on host.

---

### `services/trading-engine/app/handlers/health.py` (modify `get_status`)

**Self-reference.** The handler already builds the `emergency_stop_state` dict at lines 211-220. Currently surfaces `file_path`, `active`, `last_checked`, `auto_trader_running` but **not `mtime`**. Required addition per D-08/D-10.

**Existing code at lines 207-220:**
```python
# Surface emergency-stop file kill-switch state from the auto-trader singleton.
from app.auto_trader import get_auto_trader

auto_trader = get_auto_trader()
emergency_stop_state = {
    "file_path": str(auto_trader.emergency_stop_file),
    "active": auto_trader.emergency_stop_active,
    "last_checked": (
        auto_trader.emergency_stop_last_checked.isoformat()
        if auto_trader.emergency_stop_last_checked
        else None
    ),
    "auto_trader_running": auto_trader.is_running,
}
```

**Pattern to add** — read `mtime` via `stat()` only when the path **is a regular file** (CLAUDE.md WSL bind-mount race: path may be a directory when the host file is absent). Reuse the existing `is_file()` guard pattern at `services/trading-engine/app/main.py:282` and `services/trading-engine/app/auto_trader.py:874`:

```python
# Add mtime when the file actually exists as a regular file. The path may
# be a directory on a WSL host that hasn't created the file yet (bind-mount
# race documented in CLAUDE.md "Environment" gotchas); guard with is_file().
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
    "mtime": mtime_iso,                                        # ← new field for D-08
    "last_checked": (
        auto_trader.emergency_stop_last_checked.isoformat()
        if auto_trader.emergency_stop_last_checked else None
    ),
    "auto_trader_running": auto_trader.is_running,
}
```

**Schema update** — extend `StatusResponse` at `services/trading-engine/app/models/response.py:24-33`. `emergency_stop` is already `Optional[Dict]`, so the dict shape can grow without a model change. Optionally tighten to a `Dict[str, Any]` with a comment listing keys; not required for the patch to land.

**Note on the EMERGENCY_STOP file at repo root:** verified on disk that the path is currently a **directory** (`ls -la EMERGENCY_STOP/` returns dir contents). The `is_file()` guard above handles this correctly; gateway/UI will see `mtime: null` and `active: false`. To exercise the populated-mtime path during dev, the operator must `rmdir EMERGENCY_STOP && touch EMERGENCY_STOP` (or rely on the trading-engine restart-after-mount-fix gotcha).

---

### `scripts/audit_tiles.py` (new — operational CLI script)

**Analog A** — `scripts/check_ml_training_status.py` lines 1-95 (HTTP-probe CLI + status dict + per-step summary):

```python
#!/usr/bin/env python3
"""
ML Model Training Status Checker
...
"""
import requests, json, sys, time
from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parent.parent
from datetime import datetime
from typing import Dict, List, Optional

ML_SERVICE_URL = "http://localhost:8007"
# ...

class MLStatusChecker:
    def __init__(self):
        self.status = {
            'timestamp': datetime.utcnow().isoformat(),
            'service_health': None,
            ...
        }

    def check_service_health(self) -> bool:
        try:
            response = requests.get(f"{ML_SERVICE_URL}/health", timeout=5)
            health_status = response.json()
            print(f"✓ Service health: {health_status.get('status', 'unknown')}")
            return True
        except Exception as e:
            print(f"✗ Service health check failed: {e}")
            return False
```

**Analog B** — `scripts/monitor.py` lines 30-58 (ANSI color codes + services table + thresholds dict):

```python
# ANSI color codes
GREEN = '\033[0;32m'
RED   = '\033[0;31m'
YELLOW= '\033[1;33m'
NC    = '\033[0m'

SERVICES = {
    "api-gateway":  {"port": 8000, "critical": True},
    "trading-engine":{"port": 8005, "critical": True},
    ...
}
```

**Script shape to write** (per D-01 + Claude's Discretion line "single-binary, prints PASS/FAIL per tile, exits non-zero on any FAIL"):

```python
#!/usr/bin/env python3
"""
Tile Audit Runtime Probe (Phase 6, DASH-01)

Reads the tile inventory recorded in
.planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.md
(or a YAML/JSON sidecar derived from it), hits every documented backing
endpoint against a running stack, asserts the response shape matches the
recorded one, and prints PASS/FAIL per tile. Exits non-zero on any FAIL.

Usage:
    python scripts/audit_tiles.py --against http://localhost:3000
    python scripts/audit_tiles.py --against http://localhost:8000   # gateway direct
"""
import argparse, json, sys
from pathlib import Path
from datetime import datetime, timezone
import requests   # already used by scripts/check_ml_training_status.py

_REPO_ROOT = Path(__file__).resolve().parent.parent
_AUDIT_DOC = _REPO_ROOT / ".planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.md"

# ANSI color codes (from scripts/monitor.py)
GREEN, RED, YELLOW, NC = '\033[0;32m', '\033[0;31m', '\033[1;33m', '\033[0m'

def load_inventory(path: Path) -> list[dict]:
    """Parse the audit table; pull out rows with verdict=FIXED that have
    a documented endpoint + expected_shape. LABELED_STALE rows are
    skipped (Phase 7 backlog); REMOVED rows are skipped (tile is gone).
    """
    # impl reads the markdown table or a paired JSON; simplest path is
    # a paired audit_tiles.json that the markdown generation produces.
    ...

def probe(base_url: str, row: dict) -> dict:
    """One probe: GET row['endpoint'], assert shape against row['expected_shape']."""
    url = f"{base_url.rstrip('/')}{row['endpoint']}"
    t0 = datetime.now(timezone.utc)
    try:
        r = requests.get(url, timeout=10)
        return {
            "tile": row["tile"],
            "endpoint": row["endpoint"],
            "status_code": r.status_code,
            "ok": r.status_code == 200 and _shape_matches(r.json(), row["expected_shape"]),
            "elapsed_ms": int((datetime.now(timezone.utc) - t0).total_seconds() * 1000),
            "error": None,
        }
    except Exception as e:
        return {"tile": row["tile"], "endpoint": row["endpoint"],
                "status_code": None, "ok": False, "elapsed_ms": None, "error": str(e)}

def _shape_matches(got, expected) -> bool:
    """Shallow shape match: all keys in `expected` present in `got` with
    compatible types. Lists check element-0 shape, not length."""
    ...

def main():
    parser = argparse.ArgumentParser(description="Tile audit runtime probe")
    parser.add_argument("--against", default="http://localhost:3000",
                        help="Base URL (Vite dev proxy or gateway prod)")
    parser.add_argument("--inventory", default=str(_AUDIT_DOC.with_suffix(".json")),
                        help="JSON sidecar derived from 06-TILE-AUDIT.md")
    args = parser.parse_args()

    rows = load_inventory(Path(args.inventory))
    fails = 0
    for row in rows:
        result = probe(args.against, row)
        mark = f"{GREEN}PASS{NC}" if result["ok"] else f"{RED}FAIL{NC}"
        print(f"  {mark}  {result['tile']:30s}  {result['endpoint']:50s}  "
              f"http={result['status_code']}  {result['elapsed_ms']}ms")
        if not result["ok"]:
            fails += 1
            if result["error"]:
                print(f"        error: {result['error']}")

    print()
    summary_color = GREEN if fails == 0 else RED
    print(f"{summary_color}{len(rows) - fails}/{len(rows)} tiles PASS{NC}")
    sys.exit(0 if fails == 0 else 1)

if __name__ == "__main__":
    main()
```

**Why JSON sidecar over parsing markdown:** matches the precedent in `scripts/check_ml_training_status.py:29` which reads `training_results.json` (a paired artifact). The markdown stays operator-readable; the JSON is the machine input.

---

### `.planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.md` (new doc artifact)

**No code analog.** Markdown table only. Per D-01: columns `tile → component file → backing endpoint → expected shape → observed shape → verdict (FIXED | LABELED_STALE | REMOVED)`. Operator-readable per Claude's Discretion line. The paired JSON sidecar (`06-TILE-AUDIT.json` or similar) is what `scripts/audit_tiles.py` consumes.

**Tile inventory to walk** (from canonical_refs + code_context in CONTEXT.md):
`KeyMetricsStrip`, `ActiveTrades`, `TradeHistory`, `PortfolioCard`, `PerformanceAnalyticsPanel`, `TradingSignals`, `TradingEnhancementsPanel`, `HybridStrategyPanel`, `PriceChart`, `PriceTickerGrid`, `RegimeIndicator`, `Sparkline`, `Phase1Dashboard`, `Phase3Dashboard`, `Portfolio` page tiles. `Settings` page has no data tiles — skip per `<code_context>`.

---

## Shared Patterns

### Cross-cutting: editorial palette tokens

**Source:** `frontend/src/components/KeyMetricsStrip.jsx:40-52` (color tokens lifted from `performance-theme.css` and inlined). Same token set is referenced inline in `StatusBar.jsx` (`#5eead4`, `#fb7185`, `#a09e98`, `#d4af6a`, `#f5f3ee`).

**Apply to:** `TileState.jsx` (new), `StatusBar.jsx` extension, `App.jsx` safety-border CSS.

**Single source-of-truth check:** the same hex values appear in **both** components without a shared module. For Phase 6, **do not introduce a new shared `tokens.js`** — out of scope; just keep using the inlined `C` object pattern. (Operator can hoist later.)

```js
const C = {
  bg: '#0a0a0b', surface: '#18181c', surface2: '#1f1f24',
  border: '#2a2a32', borderStrong: '#3a3a44',
  text: '#f5f3ee', text2: '#a09e98', text3: '#8a8982',
  gain: '#5eead4',   // PAPER mode / kill-switch ARMED / positive P&L
  loss: '#fb7185',   // LIVE mode / kill-switch TRIPPED / emergency / negative P&L
  gold: '#d4af6a',   // open positions / ML predictions ON
}
```

### Cross-cutting: React Query polling cadence + retry

**Source:** `frontend/src/hooks/usePositions.js:32-44` and `:55-69` (the two best-shaped hooks — both expose `refetchInterval`, `staleTime`, `retry`, `retryDelay`).

**Apply to:** `useSafetyState.js` (new). Use `refetchInterval: 5000`, `staleTime: 5000` per D-11. Retry shape `retry: 2`, `retryDelay: 1000`.

### Cross-cutting: api-gateway route convention

**Source:** `services/api-gateway/app/main.py` — every gateway-external route is `/api/<domain>/<resource>` with **no `v1` prefix**. The proxied internal target on the per-service container uses `/api/v1/<resource>`. See `:1027` (`/api/trading/status` → `/api/v1/trading/status`) for the canonical example.

**Apply to:** new `/api/config/safety-state` route. The gateway-internal call to trading-engine targets `/status` (yes, ungrouped — that route exists at `services/trading-engine/app/main.py:485`) and `/api/v1/risk/budget/current` (router-prefixed; see `services/trading-engine/app/handlers/risk_budget.py:36`).

### Cross-cutting: WSL bind-mount EMERGENCY_STOP guard

**Source:** `services/trading-engine/app/main.py:282` and `services/trading-engine/app/auto_trader.py:874` — both use `.is_file()` (not `.exists()`) because the path can be a **directory** when the host file is missing (Docker creates a directory at the bind-mount point if the host source is absent — CLAUDE.md "Environment" gotcha).

**Apply to:** the new `mtime` reader in `handlers/health.py`. **Verified on disk 2026-05-13:** `EMERGENCY_STOP` at repo root is currently a directory; `is_file()` correctly returns False and `mtime` will be `null` until the operator replaces it with a real file.

### Cross-cutting: axios response interceptor strips `.data`

**Source:** `frontend/src/services/api.js:33-39` (also duplicated in `frontend/src/hooks/usePositions.js:16-22`). After interceptor, hook code receives the JSON body **directly** (no `.data` unwrap in callers).

**Apply to:** `useSafetyState.js` — the `queryFn` returns `await api.get('/config/safety-state')` and the resulting `data` IS the safety-state payload (no `.data.data` nesting).

---

## No Analog Found

None. Every new file in the phase has at least one strong in-repo analog:

| File | Why no gap |
|------|-----------|
| `06-TILE-AUDIT.md` | Pure markdown deliverable; no code pattern needed. |
| All others | Mapped above. |

---

## Metadata

**Analog search scope:**
- `frontend/src/components/` (16 files listed)
- `frontend/src/hooks/` (focused on `usePortfolio`, `usePositions`, `useGatewayWebSocket`)
- `frontend/src/services/api.js`
- `frontend/vite.config.js`
- `services/api-gateway/app/main.py` (1100+ lines; targeted reads at `/health` `:544`, `/api/trading/status` `:1027`, app-init `:351`)
- `services/api-gateway/app/config.py`
- `services/api-gateway/tests/conftest.py`
- `services/trading-engine/app/main.py` (lifespan `:260`, `/status` `:485`, risk-budget include `:104`/`:427`)
- `services/trading-engine/app/handlers/health.py` (`get_status` `:183`)
- `services/trading-engine/app/handlers/risk_budget.py` (`/current` `:378`)
- `services/trading-engine/app/auto_trader.py` (file-stat guard `:847`-`:881`, `get_status` `:3633`)
- `services/trading-engine/app/models/response.py` (`StatusResponse` `:24`)
- `scripts/check_ml_training_status.py`, `scripts/monitor.py`

**Files scanned (read in full or targeted-range):** ~14
**Pattern extraction date:** 2026-05-13

---

## PATTERN MAPPING COMPLETE

**Phase:** 06 - Dashboard Audit & Safety State
**Files classified:** 9 (+ 1 doc-only artifact, + ~15 audit-refactor tile sites consuming the new `TileState`)
**Analogs found:** 9 / 9

### Coverage
- Files with exact analog: 6 (`TileState.jsx`, `useSafetyState.js`, `safety-state` route, `audit_tiles.py`, plus 2 with multi-analog composition)
- Files with self-reference (in-place extension): 4 (`StatusBar.jsx`, `App.jsx`, `useGatewayWebSocket.js`, `vite.config.js`, `health.py get_status`)
- Files with no analog: 0 (the markdown audit doc has no code component)

### Key Patterns Identified
- **Frontend tile contract:** every audited tile consumes a React Query result + an `isEmpty` predicate + optional `lastUpdatedAt`; `<TileState/>` wraps the body and renders skeleton/empty/error/stale per D-13. Reuses the editorial palette tokens + corner-tick decoration from `KeyMetricsStrip.jsx`.
- **React Query polling hooks** all follow the same shape — `useQuery({ queryKey, queryFn, refetchInterval, staleTime, retry, retryDelay })` — copy directly from `usePositions.js`. `useSafetyState` uses 5s/5s per D-11.
- **api-gateway route convention** is `/api/<domain>/<resource>` (no `v1` prefix on the external side) with a proxy fan-out to per-service `/api/v1/...` internal paths. New `/api/config/safety-state` reads gateway env + proxies two trading-engine reads (`/status` + `/api/v1/risk/budget/current`).
- **EMERGENCY_STOP file-stat guard** must use `is_file()` (not `exists()`) per the documented WSL bind-mount race. Currently a **directory** on disk; the guard makes the `mtime` field gracefully return `null` until the operator fixes it.
- **Audit script** mirrors `scripts/check_ml_training_status.py` + `scripts/monitor.py` (httpx/requests + status dict + ANSI colors + PASS/FAIL exit code).

### File Created
`/mnt/d/Bimo_max/crypto-trading-bot/.planning/phases/06-dashboard-audit-safety-state/06-PATTERNS.md`

### Ready for Planning
Pattern mapping complete. Planner can now reference analog patterns in PLAN.md files.
