# Phase 10: Path-to-LIVE Dashboard — Pattern Map

**Mapped:** 2026-05-17
**Files analyzed:** 11 (8 NEW, 3 MOD; `frontend/src/services/api.js` MOD is conditional)
**Analogs found:** 10 / 11 (one — atomic temp+rename writer — has NO in-repo analog; canonical Python idiom prescribed below)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| NEW `frontend/src/components/PathToLiveTile.jsx` | React component | request-response (polled) | `frontend/src/components/StatusBar.jsx` (operator palette) + `frontend/src/components/TileState.jsx` (wrapper contract) | role-match (composite tile, not exact 1-to-1) |
| NEW `frontend/src/hooks/useLiveReadiness.js` | react-query hook | request-response (polled, 5s) | `frontend/src/hooks/useSafetyState.js` | **exact** (CONTEXT.md D-15: "copy verbatim") |
| NEW `frontend/src/hooks/useCarryIns.js` | react-query hook | request-response (polled, 5s) | `frontend/src/hooks/useSafetyState.js` | **exact** (CONTEXT.md D-15: "copy verbatim") |
| MOD `frontend/src/components/Dashboard.jsx` | React route host | render composition | self (single-line prepend above `<KeyMetricsStrip />`) | n/a — minimal edit |
| NEW `services/api-gateway/app/routes/preflight_carry_ins.py` | FastAPI router module | request-response + file-I/O (RW) + httpx fan-out | **shape**: `services/trading-engine/app/handlers/preflight.py` (APIRouter module) + **body**: `services/api-gateway/app/main.py:1168-1231` (proxy + graceful-degradation) | role-match (composite — first route module under api-gateway) |
| MOD `services/api-gateway/app/main.py` | FastAPI app | router registration | `services/trading-engine/app/main.py:485-487` (`include_router` for preflight) | role-match — first `include_router` in api-gateway main.py |
| NEW `.planning/state/carry_ins.json` | JSON state file | static seed (Phase 10) → RW (api-gateway writes `_state`) | none — schema is the contract (CONTEXT.md D-10-02) | n/a — data, not code |
| MOD `docker-compose.unified.yml` | container orchestration | bind-mount | `docker-compose.unified.yml:300-309` (api-gateway `EMERGENCY_STOP` RW + `snapshots` RO) | **exact** (same service block, same mount idiom) |
| NEW `tests/e2e/test_path_to_live_smoke.py` | pytest-playwright e2e | browser-driven smoke | `tests/integration/test_dashboard_smoke.py` | **exact** (shape, fixtures, gateway-origin assertion) |
| NEW `tests/e2e/conftest.py` **OR** MOD existing | pytest fixtures | fixture re-export | `tests/integration/conftest.py` (`bootstrap_stack` + `tape_reset` + `tournament_snapshot_seeded`) | **divergence callout** — `tests/e2e/` already exists with async/httpx shape; see "Shared Patterns → Test infra coexistence" below |
| NEW `tests/integration/test_dashlive_grep_gates.py` | pytest integration | static-text scan | `tests/integration/test_preflight_grep_gates.py` | **exact** (dual-form `rglob` + `subprocess grep`) |
| NEW `.github/workflows/dashboard-smoke.yml` | CI workflow | trigger + job-skeleton | `.github/workflows/preflight-live-readiness.yml` (paths-filter / unit + grep job split) + `.github/workflows/live-smoke.yml` (bootstrap.sh in CI) | role-match (paths-filtered PR trigger, no nightly) |
| MOD `frontend/src/services/api.js` (optional, CONTEXT.md line 245) | axios helper | request-response | self — only if a typed helper is added | n/a — CONTEXT.md says hooks may call `api.get('/preflight/...')` directly (the `useSafetyState` line 39 idiom is sufficient) |

---

## Pattern Assignments

### NEW `frontend/src/hooks/useLiveReadiness.js` + `frontend/src/hooks/useCarryIns.js`

**Analog:** `frontend/src/hooks/useSafetyState.js` (full file, 49 lines — copy verbatim with cache key + path swapped).

**Imports + hook body** (`useSafetyState.js:1-46`):
```javascript
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'

/**
 * useSafetyState — single source of truth for the operator safety strip.
 * [...] The axios client (services/api.js) has baseURL '/api' and a response
 * interceptor that unwraps `.data`, so the resolved value of api.get is
 * the body itself — no `.data.data` nesting.
 */
export function useSafetyState() {
  return useQuery({
    queryKey: ['safety-state'],
    queryFn: async () => {
      return await api.get('/config/safety-state')
    },
    refetchInterval: 5000, // D-11: match StatusBar polling cadence
    staleTime: 5000, // D-11
    retry: 2,
    retryDelay: 1000,
  })
}

export default useSafetyState
```

**Substitutions per hook:**

| New hook | `queryKey` | `api.get(...)` path | JSDoc shape (top-level keys to document) |
|----------|------------|---------------------|------------------------------------------|
| `useLiveReadiness` | `['preflight-live-readiness']` | `/preflight/live-readiness` | `schema_version`, `overall`, `evaluated_at`, `checks[]` (per `services/trading-engine/app/handlers/preflight.py`) |
| `useCarryIns` | `['preflight-carry-ins']` | `/preflight/carry-ins` | `schema_version`, `evaluated_at`, `overall`, `carry_ins[]`, `window`, `preflight_summary`, **AND** joined `live_readiness` block per CONTEXT.md D-10-16 |

**Divergence to call out (CONTEXT.md D-10-16, load-bearing):** `useCarryIns().data` is authoritative for `overall` + `window`. `useLiveReadiness()` is only used for per-check detail rows. If they disagree (race), `useCarryIns` wins. The JSDoc on `useCarryIns.js` MUST document this.

---

### NEW `frontend/src/components/PathToLiveTile.jsx`

**Analog (palette + cell shape):** `frontend/src/components/StatusBar.jsx`.
**Analog (wrapper contract):** `frontend/src/components/TileState.jsx`.

**TileState wrapping pattern** (`TileState.jsx:207-297`) — every audited tile wraps; PathToLiveTile MUST. Excerpt of the props contract:
```jsx
/**
 * TileState — props:
 *   query          React Query result {isLoading,isError,isSuccess,error,data,refetch}
 *   isEmpty        (data) => boolean (default: null/undefined or empty array)
 *   lastUpdatedAt  ISO string | epoch ms — drives stale badge
 *   staleAfterMs   number — explicit threshold (preferred over thresholdKey)
 *   thresholdKey   keyof STALE_THRESHOLDS_MS — falls back to STALE_THRESHOLDS_MS.default
 *   title          string — shown above error/empty affordances
 *   forceStale     boolean — LABELED_STALE-verdict tiles set true
 *   children       React.ReactNode — rendered when not loading/empty/error
 */
```
PathToLiveTile uses `thresholdKey="default"` (60s, per CONTEXT.md D-10-14). The tile is NOT LABELED_STALE — do not set `forceStale`.

**Branch precedence (`TileState.jsx:30-30`):** errors are LOUD. PathToLiveTile MUST render `null` for banner inside TileState when `query.isError` — TileState handles the Failed/Retry UI. Do NOT short-circuit the banner before TileState evaluates.

**Banner palette** — operator-state precedent in `StatusBar.jsx:88-90` uses these tokens (caveman: red = loss, gold = warn, teal = gain):
```javascript
const modeAccent = tradingMode === 'LIVE' ? '#fb7185' : '#5eead4'   // rose / teal
const killSwitchAccent = killSwitchTripped ? '#fb7185' : '#a09e98'  // rose / muted
const mlAccent = mlOn ? '#d4af6a' : '#65645e'                       // gold / dim
```
For the 3-state banner, CONTEXT.md D-10-13 locks tailwind tokens (NOT the inline-style palette above):
- `DO_NOT_FLIP` → `bg-rose-700`
- `ALMOST` → `bg-amber-600`
- `READY` → `bg-emerald-700`

Status chips (per CONTEXT.md D-10-13):
- PASS → `bg-emerald-700/30 text-emerald-300`
- FAIL → `bg-rose-700/30 text-rose-300`
- UNKNOWN → `bg-slate-600/30 text-slate-300`

**`data-testid` contract** (mirrors `StatusBar.jsx:118` + smoke at `test_dashboard_smoke.py:124`):
- Root: `data-testid="path-to-live-tile"` (smoke assertion D-10-18 #1).
- Per-check row: `data-testid="path-to-live-check-{check_name}"` (e.g., `path-to-live-check-cap`).
- Per-carry-in row: `data-testid="path-to-live-carry-in-{id}"` (e.g., `path-to-live-carry-in-OP-01`).
- Banner: `data-testid="path-to-live-banner"`.

**`Cell` mini-component pattern** (`StatusBar.jsx:31-55`) — reuse if rendering the per-check / per-carry-in rows feels repetitive:
```jsx
const Cell = ({ eyebrow, value, valueStyle, accent, mono = true, testId }) => (
  <div className="flex flex-col gap-0.5 px-4 py-1.5 min-w-0"
       style={{ borderRight: '1px solid #2a2a32' }}
       data-testid={testId}>
    <span className="text-[9px] uppercase tracking-[0.18em] truncate"
          style={{ color: '#65645e', fontWeight: 600 }}>{eyebrow}</span>
    <span className="text-xs truncate"
          style={{ color: accent || '#f5f3ee',
                   fontFamily: mono ? 'JetBrains Mono, monospace' : 'Manrope, system-ui, sans-serif',
                   fontFeatureSettings: '"tnum" 1', ...valueStyle }}>{value}</span>
  </div>
)
```

**Time formatter for the 24h window** — copy `StatusBar.jsx:58-67` `fmtMtime` shape (returns `null` on invalid; uses `toLocaleTimeString('en-GB', { hour12: false, timeZone: 'UTC' })`). For "X:XX:XX of 24:00:00 elapsed" use plain `Math.floor` over `window.elapsed_seconds` from the endpoint payload — CONTEXT.md "Specific Ideas" says no moment/dayjs.

---

### MOD `frontend/src/components/Dashboard.jsx`

**Analog:** self — single-line insertion. Existing structure (`Dashboard.jsx:72-76`):
```jsx
return (
  <div className="min-h-screen bg-slate-900 transition-colors duration-200">
    {/* Key Metrics Strip - Research-backed essential metrics */}
    <KeyMetricsStrip />
```

**Change:** add `import PathToLiveTile from './PathToLiveTile'` at the top (alphabetical-ish — line 7 area, near `KeyMetricsStrip`), and prepend `<PathToLiveTile />` immediately above `<KeyMetricsStrip />` (CONTEXT.md D-10-12). No prop drilling.

---

### NEW `services/api-gateway/app/routes/preflight_carry_ins.py`

**This file introduces the `app/routes/` directory to api-gateway** — there is no existing precedent in `services/api-gateway/app/`. The closest analog is split between two services:

**(a) APIRouter module shape — analog `services/trading-engine/app/handlers/preflight.py`:**
```python
"""[module docstring — unauth read-only by design; UNKNOWN is the safe default]"""
import logging
from fastapi import APIRouter, HTTPException
from app.preflight import run_all

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/preflight", tags=["preflight"])

@router.get("/live-readiness")
async def get_live_readiness() -> dict:
    try:
        report = run_all()
        return report.to_dict()
    except Exception as e:
        logger.error(f"Preflight live-readiness check failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Preflight check internal error: {e}")
```

**(b) Proxy + graceful-degradation body — analog `services/api-gateway/app/main.py:1168-1231`:**
```python
@app.get("/api/preflight/live-readiness")
async def get_preflight_live_readiness():
    """[Thin proxy to trading-engine. Graceful degradation: on any failure,
    return 200 with all checks UNKNOWN — NEVER fabricate a successful gate.]"""
    from datetime import datetime, timezone as _tz
    import json

    proxy = get_proxy()
    try:
        resp = await proxy.proxy_request(
            service_name="trading-engine",
            path="/api/preflight/live-readiness",
            method="GET",
        )
        if getattr(resp, "status_code", 500) == 200:
            return json.loads(resp.body.decode())
        raise Exception(f"trading-engine returned status_code={getattr(resp, 'status_code', 'unknown')}")
    except Exception as e:
        logger.warning(f"/api/preflight/live-readiness: trading-engine proxy failed: {e}")
        return {
            "schema_version": 1,
            "overall": "UNKNOWN",
            "evaluated_at": datetime.now(_tz.utc).isoformat(),
            "checks": [
                {"check": name, "status": "UNKNOWN", "detail": "trading-engine unreachable"}
                for name in ("cap", "paper_mode", "trading_mode", "ack",
                             "emergency_stop", "dsr_evidence")
            ],
        }
```

**Combined shape the new file MUST take:**

1. Module-level `router = APIRouter(prefix="/api/preflight", tags=["preflight"])` (shape from analog (a)).
2. `@router.get("/carry-ins")` async handler.
3. The handler MUST call its own proxy of `/api/preflight/live-readiness` via `get_proxy().proxy_request(service_name="trading-engine", path="/api/preflight/live-readiness", method="GET")` (analog (b) — do NOT duplicate the live-readiness handler; share the proxy idiom). CONTEXT.md D-10-16 requires the joined `live_readiness` block in the response.
4. Read `PREFLIGHT_CARRY_INS_PATH` env (default `/app/planning_state/carry_ins.json` per CONTEXT.md D-10-05).
5. Compute `all_pass`, mutate `_state.first_all_pass_at` per CONTEXT.md D-10-07 reset rule.
6. **Atomic write** of the mutated state — see Shared Patterns → "Atomic file write" below (NO in-repo analog).
7. Compute `overall` server-side: `DO_NOT_FLIP` if any check ≠ PASS (UNKNOWN counts as not-PASS per D-10-08; trading-engine unreachable → also `DO_NOT_FLIP` per D-10-11), `ALMOST` if all PASS but `elapsed < required`, `READY` if elapsed ≥ required.
8. Return the D-10-04 response shape (`schema_version`, `evaluated_at`, `overall`, `carry_ins`, `window`, `preflight_summary`, **plus** joined `live_readiness`).
9. **Graceful degradation:** on file read/write OR proxy failure, return 200 with `overall="DO_NOT_FLIP"` (D-10-11) and empty/null state — NEVER raise. UNKNOWN is the safe default for `live_readiness`; the tile banner maps that to `DO_NOT_FLIP`.

**Required new helper `app/routes/__init__.py`:** empty file (package marker). The grep gate test (`test_dashlive_grep_gates.py`) anchors on the path string `services/api-gateway/app/` so any of `routes/preflight_carry_ins.py` or moved-to-main.py satisfies it.

---

### MOD `services/api-gateway/app/main.py`

**Analog (router registration):** `services/trading-engine/app/main.py:485-487`:
```python
from app.handlers.preflight import router as preflight_router  # noqa: E402
app.include_router(preflight_router)
```
The `# noqa: E402` is for "module-level import not at top of file" — this style allows the router import to sit adjacent to its `include_router` call rather than 1,100 lines away from it. Project memory `feedback_main_imports_autoflake.md` is the reason imports are pinned at their use site in api-gateway main.py (see existing inline imports at `main.py:1155`, `:1193`).

**Required edit (single insertion block, adjacent to live-readiness proxy at `main.py:1168`):**
```python
# Phase 10 DASHLIVE-02 — carry-ins endpoint (state file + 24h window).
from app.routes.preflight_carry_ins import router as preflight_carry_ins_router  # noqa: E402
app.include_router(preflight_carry_ins_router)
```
This is the **first** `include_router` call in api-gateway/main.py — the file has been monolithic-inline up to now. Document the divergence in the plan.

---

### NEW `.planning/state/carry_ins.json`

**Analog:** none — schema IS the contract (CONTEXT.md D-10-02). Initial seed payload (verbatim from CONTEXT.md, with all 5 carry-ins `open`):
```json
{
  "schema_version": 1,
  "carry_ins": [
    {"id": "OP-01", "state": "open", "closed_at": null, "evidence_path": null, "description": "LIVECLOSE-05 LIVE-flip manual smoke"},
    {"id": "OP-02", "state": "open", "closed_at": null, "evidence_path": null, "description": "Migration 005 operator action"},
    {"id": "OP-03", "state": "open", "closed_at": null, "evidence_path": null, "description": "TOURNAMENT_READER_PASSWORD set"},
    {"id": "OP-04", "state": "open", "closed_at": null, "evidence_path": null, "description": "GH Actions billing resolved"},
    {"id": "INFRA-02", "state": "open", "closed_at": null, "evidence_path": null, "description": "Fresh-clone bootstrap checkpoint"}
  ],
  "_state": {
    "first_all_pass_at": null,
    "last_evaluated_at": null,
    "last_overall": "UNKNOWN"
  }
}
```
**Ownership split** (CONTEXT.md D-10-02): `carry_ins[]` array is Phase 11 LIVECLOSE writer territory; `_state` is api-gateway writer territory. Phase 10 ships the file; Phase 11 never edits `_state`.

---

### MOD `docker-compose.unified.yml`

**Analog:** `docker-compose.unified.yml:300-309` (api-gateway `volumes:` block, two existing bind-mounts):
```yaml
    volumes:
      - ./services/api-gateway/logs:/app/logs
      # RW for the gateway: it creates/overwrites the EMERGENCY_STOP file.
      # trading-engine mounts the same host file read-only.
      - ./EMERGENCY_STOP:/app/EMERGENCY_STOP
      # Phase 7 D-01: RO bind-mount of committed tournament snapshots.
      # Gateway reads /app/snapshots/*.json for /api/tournament/snapshots[/{id}].
      - ./services/tournament-harness/data/snapshots:/app/snapshots:ro
```

**Required addition** (append inside `api-gateway.volumes`, per CONTEXT.md D-10-05):
```yaml
      # Phase 10 DASHLIVE-02 — RW bind-mount for carry_ins.json state file.
      # Gateway writes _state.first_all_pass_at on each 5s poll cycle.
      # Mount the PARENT DIRECTORY (./.planning/state), NOT the single file —
      # see CLAUDE.md WSL bind-mount-race gotcha (docker silently creates an
      # empty dir at single-file mount points on WSL2). Container path
      # /app/planning_state/carry_ins.json is the default of
      # PREFLIGHT_CARRY_INS_PATH (overridable for tests).
      - ./.planning/state:/app/planning_state:rw
```
And add to `api-gateway.environment` block (near line 282–288 where `EMERGENCY_STOP_FILE` and `TRADING_MODE` live):
```yaml
      - PREFLIGHT_CARRY_INS_PATH=${PREFLIGHT_CARRY_INS_PATH:-/app/planning_state/carry_ins.json}
      - PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS=${PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS:-86400}
```

---

### NEW `tests/e2e/test_path_to_live_smoke.py`

**Analog:** `tests/integration/test_dashboard_smoke.py` (267 lines). Mirror the SHAPE; do NOT extend the file (CONTEXT.md `canonical_refs`).

**Imports + module-level constants** (`test_dashboard_smoke.py:33-67`):
```python
import json
from pathlib import Path

import pytest
from playwright.sync_api import expect

GATEWAY_ORIGIN = "http://localhost:8000"
```

**Viewport fixture** (`test_dashboard_smoke.py:75-79`):
```python
@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "viewport": {"width": 1440, "height": 900}}
```

**Test signature + fixture composition** (`test_dashboard_smoke.py:104-124`):
```python
@pytest.mark.usefixtures("bootstrap_stack", "tape_reset", "leaderboard_dsr_seeded")
def test_path_to_live_tile_renders(page):
    page.goto(f"{GATEWAY_ORIGIN}/", wait_until="networkidle", timeout=30000)
    page.wait_for_selector('[data-testid="path-to-live-tile"]', timeout=15000)
    # ... per-row + endpoint + banner assertions per D-10-18
```

**Required assertions** (CONTEXT.md D-10-18 — planner MUST cover all 7):

1. Tile visible at `data-testid="path-to-live-tile"` on `/`.
2. 6 PREFLIGHT rows render with status chip matching `/api/preflight/live-readiness` snapshot (use `httpx.get(f"{GATEWAY_ORIGIN}/api/preflight/live-readiness")` inside the test body — same pattern Phase 7's smoke uses for tournament-snapshot fixtures).
3. 5 carry-in rows render with state `open`.
4. Banner text matches `overall` from `/api/preflight/carry-ins` — in PAPER + no DSR row, expected `"DO NOT FLIP"`.
5. Endpoint shape assertion: `httpx.get` `/api/preflight/carry-ins` returns `schema_version=1` and top-level keys `{schema_version, evaluated_at, overall, carry_ins, window, preflight_summary}` (plus joined `live_readiness` per D-10-16).
6. **DSR row schema assertion** — seed `leaderboard` (use `_seed_leaderboard` helper pattern from `services/trading-engine/tests/test_ml_gate_auto_flip.py:74-111` — see Shared Patterns below); hit `/api/preflight/live-readiness`; assert `dsr_evidence.status == "PASS"` and `dsr_evidence.detail` contains numeric `dsr` + ISO `run_date`.
7. **24h window mechanics** — with `PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS=1` env override, force all 6 checks PASS via env stubs, wait 2s, hit endpoint twice, assert second response has `overall=="READY"` and `window.elapsed_seconds >= 1`.

**Failure-artifact convention** (`test_dashboard_smoke.py:23-25`): pytest-playwright CLI handles `--screenshot=only-on-failure --video=retain-on-failure`. No explicit capture in test body. The CI workflow (`dashboard-smoke.yml`) wires these flags.

---

### NEW `tests/e2e/__init__.py` + `tests/e2e/conftest.py` **— DIVERGENCE CALLOUT**

**Important:** `tests/e2e/` ALREADY EXISTS (CONTEXT.md got this wrong — claims "no precedent"). Current contents:
```
tests/e2e/__init__.py
tests/e2e/conftest.py             (async/httpx ServiceClient shape — NOT pytest-playwright)
tests/e2e/fixtures/mock_data.py
tests/e2e/utils/wait_for_health.py
tests/e2e/test_data_pipeline.py
tests/e2e/test_failure_scenarios.py
tests/e2e/test_order_execution.py
tests/e2e/test_performance_scalability.py
tests/e2e/test_risk_management.py
tests/e2e/test_signal_generation.py
tests/e2e/test_trading_cycle.py
```

The existing `tests/e2e/conftest.py:1-50` defines `ServiceClient` and pulls `wait_for_service_health` — it has NOTHING to do with pytest-playwright fixtures or `bootstrap_stack`/`tape_reset` (which live in `tests/integration/conftest.py`).

**Resolution (planner MUST choose):**

Option A (preferred — minimal touch): **Extend** the existing `tests/e2e/conftest.py` by adding:
```python
# Phase 10 DASHLIVE-04: pull bootstrap_stack, tape_reset, and the new
# leaderboard_dsr_seeded fixture from integration conftest so pytest-playwright
# smoke under tests/e2e/ can reuse the recorded-tape boot path.
pytest_plugins = ["tests.integration.conftest"]
```
This avoids the WRITE conflict with the existing file. The `__init__.py` already exists — do NOT overwrite.

Option B: place the new smoke in a subdirectory `tests/e2e/dashlive/` with a local `conftest.py`. Heavier, but isolates the pytest-playwright dependency from the async/httpx suite that already lives in `tests/e2e/`.

**Do NOT overwrite** `tests/e2e/__init__.py` or `tests/e2e/conftest.py` — they're load-bearing for the existing suite. CONTEXT.md's wording "NEW tests/e2e/__init__.py, tests/e2e/conftest.py (re-exports)" is incorrect given the on-disk reality. Planner picks A or B and documents the choice.

**Additional fixture needed (new — no analog in `tests/integration/conftest.py`):** `leaderboard_dsr_seeded`. Use the schema + insert pattern from `services/trading-engine/tests/test_ml_gate_auto_flip.py:48-111` (see Shared Patterns below).

---

### NEW `tests/integration/test_dashlive_grep_gates.py`

**Analog:** `tests/integration/test_preflight_grep_gates.py` (125 lines). Use the **dual-form scan** (pathlib + subprocess) verbatim.

**Imports + module-level constants** (`test_preflight_grep_gates.py:24-42`):
```python
from __future__ import annotations

import inspect
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TE_APP = REPO_ROOT / "services" / "trading-engine" / "app"  # template for scope constants
```

**Gate pattern** (`test_preflight_grep_gates.py:50-95`):
```python
def test_<gate_name>():
    pattern = re.compile(r"<LITERAL>")
    matches: list[str] = []
    for py_or_jsx in <SCOPE_DIR>.rglob("*.<ext>"):
        if "/tests/" in py_or_jsx.as_posix():
            continue
        try:
            text = py_or_jsx.read_text(errors="ignore")
        except OSError:
            continue
        if pattern.search(text):
            matches.append(str(py_or_jsx.relative_to(<SCOPE_DIR>)))
    assert matches, "<descriptive failure with rollback hint>"

    # Fidelity to the literal CI grep command — SCOPE IS LOAD-BEARING.
    result = subprocess.run(
        ["grep", "-r", "<LITERAL>", str(<SCOPE_DIR>)],
        capture_output=True, text=True,
    )
    assert result.stdout, "subprocess grep returned no matches under <SCOPE_DIR>."
```

**Two gates required (CONTEXT.md D-10-20):**

| Gate | Literal | Scope dir | Glob | Failure message hint |
|------|---------|-----------|------|----------------------|
| `test_path_to_live_tile_component_exists` | `PathToLiveTile` | `REPO_ROOT / "frontend" / "src"` | `*.jsx`/`*.js` | "PathToLiveTile component removed from frontend. DASHLIVE-01 contract requires the tile to live under frontend/src/. Restore the component file." |
| `test_carry_ins_endpoint_referenced` | `carry-ins` | `REPO_ROOT / "services" / "api-gateway" / "app"` | `*.py` | "carry-ins endpoint silently removed from api-gateway. DASHLIVE-02 contract requires /api/preflight/carry-ins. Check that services/api-gateway/app/routes/preflight_carry_ins.py still exists and is registered in main.py." |

**Scope discipline (load-bearing):** keep `SCOPE_DIR` narrow (frontend/src for tile, api-gateway/app for endpoint). Docs prose (CONTEXT.md, RUNBOOK.md, REQUIREMENTS.md) MUST NOT satisfy the gate — same precedent `test_preflight_grep_gates.py:36-39` documents for `LIVE_PREFLIGHT_REJECTED`.

---

### NEW `.github/workflows/dashboard-smoke.yml`

**Analog (job-skeleton):** `.github/workflows/preflight-live-readiness.yml` (65 lines).
**Analog (bootstrap.sh in CI):** `.github/workflows/live-smoke.yml:36-50` (env-block + cp `.env.example` + `bash bootstrap.sh`).

**Trigger block** (paths-filter per CONTEXT.md D-10-19 — NOT nightly):
```yaml
name: Dashboard Smoke (Path-to-LIVE)

on:
  pull_request:
    paths:
      - "frontend/**"
      - "services/api-gateway/**"
      - "services/trading-engine/app/preflight/**"
      - "services/trading-engine/app/handlers/preflight.py"
      - "tests/e2e/test_path_to_live_smoke.py"
      - ".planning/state/carry_ins.json"
  workflow_dispatch:

concurrency:
  group: dashboard-smoke-${{ github.ref }}
  cancel-in-progress: true
```

**Security note to preserve verbatim from analog** (`preflight-live-readiness.yml:6-13`):
```
# Security note: this workflow does NOT interpolate any user-controlled
# event payload (issue/PR title, body, commit message, head ref) into shell
# commands. The only ${{ }} expressions used are:
#   - github.ref in concurrency.group (Actions-sanitised context)
# No command-injection surface per the standard GH workflow security guide.
```

**Job skeleton** (combine `preflight-live-readiness.yml:26-43` step shape + `live-smoke.yml:22-50` boot-via-bootstrap.sh):
```yaml
jobs:
  dashboard-smoke:
    name: Dashboard smoke (PathToLiveTile + carry-ins endpoint)
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install playwright + integration deps
        run: |
          pip install --upgrade pip
          pip install pytest pytest-playwright httpx
          playwright install --with-deps chromium
      - name: Boot stack via bootstrap.sh (paper mode, tape source)
        env:
          MARKET_DATA_SOURCE: tape
          PAPER_TRADING_MODE: "true"
          TRADING_MODE: PAPER
          AUTO_TRADING_ENABLED: "false"
          ENABLE_ML_PREDICTIONS: "false"
          PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS: "1"  # D-10-09 fast-forward
        run: |
          cp .env.example .env
          { echo "MARKET_DATA_SOURCE=$MARKET_DATA_SOURCE"
            echo "PAPER_TRADING_MODE=$PAPER_TRADING_MODE"
            echo "TRADING_MODE=$TRADING_MODE"
            echo "AUTO_TRADING_ENABLED=$AUTO_TRADING_ENABLED"
            echo "ENABLE_ML_PREDICTIONS=$ENABLE_ML_PREDICTIONS"
            echo "PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS=$PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS"
          } >> .env
          bash bootstrap.sh
      - name: Run smoke
        run: pytest tests/e2e/test_path_to_live_smoke.py --screenshot=only-on-failure --video=retain-on-failure -v
      - name: Collect logs
        if: always()
        run: docker compose -f docker-compose.unified.yml logs > dashboard-smoke-logs.txt 2>&1 || true
      - name: Upload logs
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: dashboard-smoke-logs
          path: dashboard-smoke-logs.txt
          retention-days: 14
      - name: Cleanup
        if: always()
        run: docker compose -f docker-compose.unified.yml down -v || true
```

**No nightly cron** (CONTEXT.md "Deferred Ideas" — Phase 12 CI Recovery owns nightly cadence; Phase 10 conserves CI minutes under OP-04 billing pressure).

---

### MOD `frontend/src/services/api.js` (optional per CONTEXT.md line 245)

**Analog:** existing `portfolioAPI` / `tradingAPI` named-export-object pattern at `api.js:42-99`. CONTEXT.md says this MOD is needed ONLY if a typed helper is added — the hooks otherwise call `api.get('/preflight/...')` directly (the `useSafetyState.js:39` idiom is sufficient: `await api.get('/config/safety-state')`).

**Recommendation:** SKIP this MOD. The two new hooks each have exactly one endpoint; an indirection adds drag without value. Document in the plan that `useLiveReadiness` + `useCarryIns` call `api.get('/preflight/live-readiness')` / `api.get('/preflight/carry-ins')` directly per the `useSafetyState` precedent.

If added anyway, append at the bottom of `api.js` (near `tournamentAPI:216-224` shape):
```javascript
// Phase 10 DASHLIVE — Path-to-LIVE preflight + carry-ins.
// Gateway path shape is /api/preflight/... (NO /v1/ prefix per ADR-007).
export const preflightAPI = {
  getLiveReadiness: () => api.get('/preflight/live-readiness'),
  getCarryIns:      () => api.get('/preflight/carry-ins'),
}
```

---

## Shared Patterns

### Atomic file write (NO in-repo analog — canonical Python idiom prescribed)

**Important correction to CONTEXT.md / 10-CONTEXT.md "Established Patterns" claim:**
CONTEXT.md states `services/trading-engine/app/lifespan/ml.py` uses "temp file + os.rename" for marker writes. **This is wrong.** The actual code at `app/lifespan/ml.py:195` is:
```python
marker.write_text(json.dumps(payload))   # BARE WRITE — NOT ATOMIC
```
There is no `tempfile.NamedTemporaryFile` and no `os.rename`/`os.replace` anywhere in `ml.py`. That file is NOT an analog for atomic writes.

**No other in-repo writer follows the atomic temp+rename pattern either.** The api-gateway carry-ins writer needs to introduce it. Canonical Python idiom (works on POSIX + modern Windows; `os.replace` is atomic on both):
```python
import json
import os
import tempfile
from pathlib import Path

def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write `payload` as JSON to `path` atomically.

    Writes to a temp file in the same directory (same filesystem → atomic
    rename) then os.replace()s into place. os.replace() is atomic on POSIX
    and on Windows from Python 3.3+. No torn writes; concurrent readers
    see either the old file or the new file, never a half-written one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # delete=False so the file persists after close() for the rename.
    # dir=path.parent is REQUIRED — temp file MUST be on the same
    # filesystem as the target for os.replace to be atomic.
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f)
            f.flush()
            os.fsync(f.fileno())  # belt-and-braces durability
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
```

**Apply to:** the api-gateway carry-ins writer (`services/api-gateway/app/routes/preflight_carry_ins.py`). On any OSError, log a warning and continue serving the response with `window` fields set from the in-memory computed value — degrade gracefully. The next poll will retry.

**Test seam:** override `PREFLIGHT_CARRY_INS_PATH` via env to point at a tmp_path in pytest. Use `pathlib.Path.write_text` patches per project memory `feedback_pathlib_mocking.md` — `mock.patch("builtins.open")` will silently no-op against `os.fdopen`, so prefer the real-FS approach with `tmp_path` fixture.

### Graceful-degradation HTTP body (UNKNOWN is the safe default)

**Source:** `services/api-gateway/app/main.py:1208-1231` (verbatim above in preflight_carry_ins.py section).
**Apply to:** new `preflight_carry_ins.py` handler. On any exception (proxy fail, file-IO fail), return 200 with `overall="DO_NOT_FLIP"` (D-10-11 maps UNKNOWN-from-upstream to DO_NOT_FLIP for the banner; the per-check `live_readiness.checks` block can still surface UNKNOWN per check for the operator).

### `data-testid` contract for audited tiles

**Source:** `frontend/src/components/StatusBar.jsx:118` (`data-testid="statusbar"`) + per-cell test ids on `Cell` instances (`StatusBar.jsx:178, 187, 195, 203`).
**Apply to:** PathToLiveTile root + per-row chips + banner. Required test ids documented per-file above. The `tests/integration/test_dashboard_smoke.py:113-120` hard-gate pattern (asserting non-REMOVED rows carry a `data_testid`) is the load-bearing reason this convention is mandatory.

### Leaderboard schema seed (for DSR-row assertion in smoke)

**Source:** `services/trading-engine/tests/test_ml_gate_auto_flip.py:48-111`:
```python
LEADERBOARD_SCHEMA_SQL = """
CREATE TABLE leaderboard (
    run_id              TEXT NOT NULL,
    tournament_id       TEXT NOT NULL,
    architecture        TEXT NOT NULL,
    symbol              TEXT NOT NULL,
    horizon             INTEGER NOT NULL,
    target_mode         TEXT NOT NULL,
    hp_hash             TEXT NOT NULL,
    dsr                 REAL,
    git_sha             TEXT NOT NULL,
    tournament_start_ts TEXT NOT NULL,
    status              TEXT NOT NULL,
    run_date            TEXT,
    psr_ci_published    INTEGER NOT NULL DEFAULT 0
        CHECK (psr_ci_published IN (0, 1)),
    PRIMARY KEY (architecture, symbol, horizon, target_mode, hp_hash, run_id)
);
"""

def _seed_leaderboard(db_path, dsr_value=0.97, *,
                      psr_ci_published=1, run_date=None, status="success"):
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(LEADERBOARD_SCHEMA_SQL)
        cur.execute("INSERT INTO leaderboard (...) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (...))
        conn.commit()
    finally:
        conn.close()
```
**Apply to:** new `leaderboard_dsr_seeded` fixture in `tests/e2e/conftest.py` (extended via `pytest_plugins` per Option A above), called from the smoke for assertion #6 (D-10-18). Use `dsr_value=0.97`, `run_date=<today>`, `psr_ci_published=1`, `status='success'`.

### Schema versioning + unauth read-only preflight contract

**Source:** `services/trading-engine/app/handlers/preflight.py:10-13` (unauth by design) + `app/main.py:1186-1188` (schema v1 pinned).
**Apply to:** the new `/api/preflight/carry-ins` endpoint. NO auth dependency (matches `/api/preflight/live-readiness` and `/api/preflight/ml-gate-reason-counts` precedent). `schema_version: 1` is in the response body. No secrets in payload.

### Local imports for autoflake survival

**Source:** `services/api-gateway/app/main.py:1151-1155, 1189-1194`:
```python
# Local import: autoflake removes unused top-level imports across
# api-gateway/main.py refactors. Importing inside the function pins
# the use site and survives the autoflake pass (project memory:
# feedback_main_imports_autoflake.md).
from datetime import datetime, timezone as _tz
import json
```
**Apply to:** the new `preflight_carry_ins.py` handler — pin `datetime`, `json`, and `os` imports inside the handler body OR mark module-level imports with `# noqa: F401` if they're used only conditionally. Memory file `feedback_main_imports_autoflake.md` is the canonical reference.

---

## No Analog Found

Files with no close in-repo match (planner uses prescribed pattern):

| File | Role | Reason | Pattern source |
|------|------|--------|----------------|
| atomic JSON write helper inside `preflight_carry_ins.py` | utility | CONTEXT.md miscredits `ml/py` — bare write, not atomic; no other in-repo writer is atomic | Canonical Python `tempfile.mkstemp` + `os.replace` idiom prescribed in Shared Patterns |
| `.planning/state/carry_ins.json` | JSON state file | first repo-bound state JSON under `.planning/state/` | Schema verbatim from CONTEXT.md D-10-02 |
| `tests/e2e/conftest.py` "re-export" wiring | pytest fixture | existing conftest serves a different (async/httpx) suite | Option A `pytest_plugins = ["tests.integration.conftest"]` injection prescribed in callout above |

---

## Metadata

**Analog search scope:**
- `frontend/src/hooks/` (`useSafetyState.js`)
- `frontend/src/components/` (`TileState.jsx`, `StatusBar.jsx`, `Dashboard.jsx`)
- `frontend/src/services/api.js`
- `services/api-gateway/app/main.py` (1168-1231 + 1050-1165 safety-state + 1-80 imports)
- `services/trading-engine/app/handlers/preflight.py`
- `services/trading-engine/app/lifespan/ml.py` (full; falsifies CONTEXT.md atomic-write claim)
- `services/trading-engine/app/main.py` (`include_router` precedent)
- `services/trading-engine/tests/test_ml_gate_auto_flip.py` (leaderboard seed helper)
- `docker-compose.unified.yml:275-329` (api-gateway volumes + env)
- `tests/integration/test_dashboard_smoke.py` (267 lines)
- `tests/integration/conftest.py` (full; `bootstrap_stack`, `tape_reset`, `tournament_snapshot_seeded`)
- `tests/integration/test_preflight_grep_gates.py` (125 lines)
- `tests/e2e/conftest.py` + `tests/e2e/README.md` (divergence-detect)
- `.github/workflows/preflight-live-readiness.yml` (65 lines)
- `.github/workflows/live-smoke.yml` (88 lines)

**Files scanned:** 16 analog sources + 4 corroborating reads
**Pattern extraction date:** 2026-05-17
