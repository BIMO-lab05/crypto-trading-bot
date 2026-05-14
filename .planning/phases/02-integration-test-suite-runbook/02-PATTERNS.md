# Phase 2: Integration Test Suite & RUNBOOK - Pattern Map

**Mapped:** 2026-05-07
**Files analyzed:** 9 (5 new, 4 extend)
**Analogs found:** 7 / 9 with strong matches; 2 require synthesis

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `tests/integration/conftest.py` | test (fixtures) | session/function-scoped lifecycle | `tests/integration/conftest.py` (existing) + `tests/e2e/conftest.py` | EXTEND existing (with bug-fix; see warnings) |
| `tests/integration/test_*.py` (INFRA-01 e2e suite) | test | request-response + timing assertions | `tests/integration/test_e2e_trading_flow.py` + `test_end_to_end_trading.py` | role-match (must NOT propagate `pytest.skip` pattern from `test_phase3_integration.py`) |
| `services/bybit-connector/app/main.py` (add `POST /admin/tape/reset`) | controller (admin) | request-response, state-mutating | `services/bybit-connector/app/main.py:954-970` (`/api/v1/status/circuit-breaker/reset`) | exact (state-mutating POST + rate-limited + no auth) |
| `services/bybit-connector/app/tape_replay_client.py` (add `reset()` method) | service (in-process state) | internal cursor reset | `tape_replay_client.py:50-112` (`_load_fixtures`) | role-match (cursor structure exists; reset semantics new) |
| `services/trading-engine/app/handlers/orchestration.py` (add `POST /api/trading/force-signal`) **OR** `services/api-gateway/app/main.py` (add admin route + proxy) | controller (admin) | request-response, emits event | trading-engine: `handlers/orchestration.py:646-692` + `:713-783` (admin_indicator_router) **OR** api-gateway: `main.py:1391-1448` (emergency_stop) | TWO viable analogs — planner must pick (see Discriminator) |
| `scripts/iter-fix.sh` | utility (shell harness) | event-driven (test-run → diff → approve → commit) | `bootstrap.sh` (style only) | NO functional analog — synthesize |
| `RUNBOOK.md` (new at repo root) | docs (failure-triage-first) | n/a | `docs/operations/RUNBOOK.md` (existing 6-section ops format) | conflict — see RUNBOOK section below |
| `Makefile` (new at repo root, `make build-no-buildkit`) | config (build target) | n/a | `bootstrap.sh:42-49` (`DOCKER_BUILDKIT=0` workaround logic) | NO Makefile in repo — synthesize |
| `.github/workflows/integration.yml` (new) | config (CI) | event-driven (push/PR) | `.github/workflows/live-smoke.yml` (Phase 1 Plan 04, host-runs `bootstrap.sh`) | exact shape; diverge on triggers + add anti-mock guard |
| `.env.test.example` (new) | config (env template) | n/a | `.env.example` (style only) | NO test-env analog — synthesize |

---

## Pattern Assignments

### `tests/integration/conftest.py` (EXTEND — fixtures, session/function-scoped)

**Analog:** `tests/integration/conftest.py` (existing, lines 1-68) + `tests/e2e/conftest.py` (lines 1-50, ServiceClient pattern)

> WARNING — DO NOT propagate two bugs in the existing file:
> 1. **Port mapping inverted** (lines 27, 30): `trading_engine: 8001` and `bybit_connector: 8005` are SWAPPED vs CLAUDE.md (8001=bybit-connector, 8005=trading-engine). Phase 2 EXTEND MUST correct.
> 2. **`wait_for_services` is `scope="function"`** (line 41). Phase 2 D-03 mandates session-scoped, single boot. Refactor to session-scope.

**Imports + scope pattern** (existing lines 1-19, KEEP shape):
```python
import pytest
import asyncio
import httpx
from typing import AsyncGenerator, Dict
import os


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
```

**HTTP client fixture pattern** (existing lines 34-38, KEEP):
```python
@pytest.fixture(scope="session")
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client
```

**Health-poll loop** (existing lines 41-55, REFACTOR to session-scoped + fix port map; keep retry shape):
```python
# REPLACE with session-scoped + correct ports:
@pytest.fixture(scope="session")
async def services_config() -> Dict[str, str]:
    return {
        "api_gateway":      os.getenv("API_GATEWAY_URL",      "http://localhost:8000"),
        "bybit_connector":  os.getenv("BYBIT_CONNECTOR_URL",  "http://localhost:8001"),  # was 8005 — fix
        "market_data":      os.getenv("MARKET_DATA_URL",      "http://localhost:8002"),
        "portfolio":        os.getenv("PORTFOLIO_URL",        "http://localhost:8003"),
        "technical_analysis": os.getenv("TA_URL",             "http://localhost:8004"),
        "trading_engine":   os.getenv("TRADING_ENGINE_URL",   "http://localhost:8005"),  # was 8001 — fix
        "notification":     os.getenv("NOTIFICATION_URL",     "http://localhost:8006"),
        # ML + sentiment + risk metrics: 8007 / 8008 / 8009
    }
```

**NEW fixtures to add** (no direct analog, synthesize per CONTEXT D-01..D-08, CD-04):
- `bootstrap_stack` (session-scoped) — shells out to `subprocess.run(["./bootstrap.sh"], cwd=tmp_clone, check=True)`; captures exit code + last 50 log lines on failure (mirrors `bootstrap.sh:127-133`).
- `tmp_fresh_clone` (session-scoped) — `git clone file://$(repo_root) /tmp/cb-test-<sha>` per D-05; `shutil.rmtree` only on success per D-08.
- `tape_reset` (function-scoped) — HTTPs `POST :8001/admin/tape/reset` before each test per D-04.
- `db_truncate` (function-scoped) — uses `asyncpg.create_pool` pattern from `services/portfolio-manager/app/main.py:165-170`; `TRUNCATE klines, tickers, positions, orders RESTART IDENTITY CASCADE` (no in-repo analog; synthesize).
- `force_signal` (function-scoped) — POSTs synthetic signal to `force-signal` endpoint (CD-04); helper for test bodies.

**Anti-pattern reference — DO NOT IMITATE** (`tests/integration/test_phase3_integration.py:71-76`):
```python
# DO NOT COPY — this is the exact pattern D-12 forbids:
if not all(services_status.values()):
    pytest.skip(
        f"Required services not available: {services_status}. ..."
    )
# Phase 2 tests MUST fail hard when stack isn't healthy. iter-fix.sh diff-grep
# rejects additions of `pytest.skip` / `pytest.mark.xfail` in tests/ per D-12.
```

---

### `tests/integration/test_*.py` (NEW — INFRA-01 e2e suite)

**Analog:** `tests/integration/test_e2e_trading_flow.py` (lines 1-187) + `tests/integration/test_end_to_end_trading.py` (E2ETestRunner pattern, lines 51-700)

**Test signature pattern** (`test_e2e_trading_flow.py:10-26`):
```python
@pytest.mark.asyncio
async def test_complete_trading_flow(
    services_config,
    http_client,
    wait_for_services,    # rename to bootstrap_stack in Phase 2 (session-scoped)
    test_symbol
):
    """Test complete trading flow ..."""
    api_gateway = services_config["api_gateway"]
    response = await http_client.get(f"{api_gateway}/api/market/ticker/{test_symbol}")
    assert response.status_code == 200
```

**Latency-assertion pattern** (`test_e2e_trading_flow.py:101-132` — adapt for paper-trade <60s per CD-04):
```python
import time
start_time = time.time()
response = await http_client.get(f"{api_gateway}/api/trading/signals/{test_symbol}")
signal_time = time.time() - start_time
assert response.status_code == 200
assert signal_time < 1.0
```

**Phase 2 adapts this for round-trip per CD-04** (use `time.monotonic()`, poll DB at 250ms cadence):
```python
# Synthesize per CD-04 — no exact analog:
import time
t0 = time.monotonic()
await http_client.post(f"{trading_engine}/api/trading/force-signal", json=synthetic_signal)
deadline = t0 + 60.0
position_row = None
while time.monotonic() < deadline:
    position_row = await db.fetchrow(
        "SELECT created_at FROM positions WHERE strategy_id=$1 ORDER BY created_at DESC LIMIT 1",
        synthetic_signal["strategy_id"],
    )
    if position_row and position_row["created_at"] is not None:
        break
    await asyncio.sleep(0.25)
elapsed = time.monotonic() - t0
assert position_row is not None, "no position row created within 60s"
assert elapsed < 60.0, f"paper trade round-trip took {elapsed:.2f}s, exceeds 60s budget"
```

**Notification-assertion pattern (CD-01)** — no in-repo analog. Synthesize:
- `NOTIFICATION_TEST_MODE=record` (local default): assert file `tests/.notifications.log` contains expected payload after `force-signal`.
- `NOTIFICATION_TEST_MODE=live` (CI): poll `https://api.telegram.org/bot{TEST_BOT_TOKEN}/getUpdates`, assert latest message matches expected text.
- Reuse `services/notification-service/app/telegram_notifier.py:60-80` (httpx.AsyncClient.post pattern) for inverse — the test reads `getUpdates`, not `sendMessage`.

**ML-on test variant marker** (CD-05) — no in-repo analog:
```python
# Synthesize:
@pytest.mark.ml_on
@pytest.mark.asyncio
async def test_ml_models_loaded(services_config, http_client, bootstrap_stack):
    """Run only with `pytest -m ml_on` + ENABLE_ML_PREDICTIONS=true."""
    response = await http_client.get(f"{services_config['ml_prediction']}/api/v1/predictions/SOLUSDT")
    assert response.status_code == 200
    assert response.json()["prediction"]["confidence"] != 0.0  # default-confidence sentinel
```

---

### `services/bybit-connector/app/main.py` — add `POST /admin/tape/reset`

**Analog:** `services/bybit-connector/app/main.py:954-970` (`/api/v1/status/circuit-breaker/reset`) — EXACT pattern.

**Existing analog (copy structure)**:
```python
@app.post("/api/v1/status/circuit-breaker/reset", tags=["Monitoring"])
@limiter.limit("10/minute")
async def reset_circuit_breaker(
    request: Request,
    client: BybitRestClient = Depends(get_rest_client)
):
    """Reset circuit breaker — manually resets to closed state.
    Rate limited to 10 requests/minute (admin operation)
    """
    logger.warning("Circuit breaker manually reset")
    client.reset_circuit_breaker()
    return {"success": True, "message": "Circuit breaker reset"}
```

**Phase 2 adaptation (synthesize gate per CONTEXT D-04)**:
```python
@app.post("/admin/tape/reset", tags=["Admin"])
@limiter.limit("60/minute")  # higher than circuit-breaker; called per-test
async def reset_tape_cursor(
    request: Request,
    client = Depends(get_rest_client),
    settings: Settings = Depends(get_settings),
):
    """Reset the tape replay cursor to fixture position 0.
    Gated to MARKET_DATA_SOURCE=tape mode only (D-04).
    """
    # SYNTHESIS: D-04 gate — no analog has this:
    if settings.market_data_source != "tape":
        raise HTTPException(
            status_code=403,
            detail="tape/reset only available when MARKET_DATA_SOURCE=tape",
        )
    if not isinstance(client, TapeReplayClient):
        raise HTTPException(status_code=503, detail="tape client not initialized")
    logger.warning("TAPE_REPLAY: cursor reset")  # grep-able log line per main.py:314 convention
    client.reset()
    return {"success": True, "message": "tape cursor reset"}
```

**Auth note** — bybit-connector has NO auth middleware (consistent with `services/trading-engine/app/handlers/orchestration.py:703-705`: "trading-engine has no auth middleware; all admin routes are protected upstream at the api-gateway"). The `/admin/tape/reset` route is reachable only from within the docker network in tape mode; no admin guard needed at this layer.

---

### `services/bybit-connector/app/tape_replay_client.py` — add `reset()` method

**Analog:** `tape_replay_client.py:50-112` (`_load_fixtures` shows current cursor structure)

**Current structure** (lines 46-48 — note: today there is NO cursor; `_klines` is fully loaded list):
```python
self.fixtures_path = Path(fixtures_path)
self._klines: Dict[str, List[List[str]]] = {}   # symbol -> list of klines
self._tickers: Dict[str, Dict[str, Any]] = {}   # symbol -> ticker dict
```

**Phase 2 adaptation (synthesize cursor + reset)**:
The current implementation returns `list(reversed(klines))[:limit]` on every call (line 176) — there is no cursor advancing. If Phase 2 needs per-test reset semantics, the planner must decide whether:
- (a) The current stateless replay already satisfies D-04 (each call is deterministic given same params). In which case `reset()` is a no-op + log line, and the fixture exists for symmetry only.
- (b) Add a `_kline_cursor: Dict[str, int]` field if the suite needs sequential consumption (e.g., "next 5 candles" semantics). Then `reset()` zeroes all cursors.

Default stance (matches D-04 wording "cursor reset"): implement (b) with cursor zeroing — even if today's loader is stateless, the API contract should support stateful tests.

```python
def reset(self) -> None:
    """Reset all in-memory cursors to fixture position 0 (D-04).
    Called by POST /admin/tape/reset between integration tests."""
    self._kline_cursor = {sym: 0 for sym in self._klines}  # if cursor added
    self._ticker_cursor = {sym: 0 for sym in self._tickers}
    logger.warning("TAPE_REPLAY: cursors reset (klines=%d, tickers=%d)",
                   len(self._kline_cursor), len(self._ticker_cursor))
```

---

### `force-signal` endpoint — TWO viable hosts (planner discriminator)

**CONTEXT CD-04 leaves this open: trading-engine OR api-gateway. The planner picks. Both analogs documented.**

#### Option A: Add to trading-engine `handlers/orchestration.py`

**Analog 1 — signal-submission shape:** `services/trading-engine/app/handlers/orchestration.py:646-692`
```python
@router.post("/signals/submit", summary="Submit trading signal")
async def submit_signal(request: SignalSubmissionRequest):
    try:
        orchestrator = get_strategy_orchestrator()
        try:
            direction = SignalDirection(request.direction)
        except ValueError:
            direction = SignalDirection.FLAT
        signal = StrategySignal(
            signal_id=f"sig_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
            strategy_id=request.strategy_id,
            symbol=request.symbol,
            timestamp=datetime.now(timezone.utc),
            direction=direction,
            action=request.action,
            strength=request.strength,
            confidence=request.confidence,
            ...
        )
        result = orchestrator.submit_signal(signal)
        return {"success": result.get("accepted", False), "signal_id": signal.signal_id, **result, ...}
    except Exception as e:
        logger.error(f"Error submitting signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

**Analog 2 — admin-router prefix convention:** `handlers/orchestration.py:713-783` (`admin_indicator_router`)
```python
admin_indicator_router = APIRouter(
    prefix="/api/v1/admin/indicators",
    tags=["Admin: Indicator Gate"],
)

@admin_indicator_router.post("/{name}/enable", summary="...")
async def enable_indicator(name: str) -> Dict[str, Any]:
    ...
```

**Phase 2 force-signal sketch (Option A)**:
```python
admin_force_signal_router = APIRouter(
    prefix="/api/v1/admin/force-signal",
    tags=["Admin: Force Signal"],
)

@admin_force_signal_router.post("", summary="Force a synthetic signal for integration tests")
async def force_signal(request: ForceSignalRequest) -> Dict[str, Any]:
    """Inject a deterministic synthetic signal — used by integration suite per CD-04.
    No auth at this layer (trading-engine has no auth middleware; protected upstream)."""
    # ... build StrategySignal ... orchestrator.submit_signal(signal) ...
```

**Then mount** in `services/trading-engine/app/main.py:415` style:
```python
app.include_router(admin_force_signal_router)
```

#### Option B: Add to api-gateway `app/main.py`

**Analog:** `services/api-gateway/app/main.py:1391-1448` (`emergency_stop`) — admin-guarded pattern
```python
@app.post("/api/portfolio/emergency-stop")
async def emergency_stop(current_user: User = Depends(get_current_admin_user)):
    """Admin-only. Writes EMERGENCY_STOP file the trading-engine watches."""
    stop_file = Path(os.getenv("EMERGENCY_STOP_FILE", "/app/EMERGENCY_STOP"))
    activated_at_ms = int(time.time() * 1000)
    ...
    try:
        stop_file.parent.mkdir(parents=True, exist_ok=True)
        stop_file.write_text(...)
    except OSError as e:
        logger.error(f"Failed to write {stop_file}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="...")
    logger.warning(f"EMERGENCY STOP ACTIVATED by {current_user.username} → {stop_file}")
    return JSONResponse(content={"success": True, ...})
```

**Test-side fixture for Option B:** `services/api-gateway/tests/conftest.py:30-46` (`admin_client`)
```python
@pytest.fixture
def admin_client():
    """TestClient with auth dependencies overridden to a fake admin user."""
    user = _fake_admin()
    app.dependency_overrides[get_current_admin_user] = lambda: user
    app.dependency_overrides[get_current_active_user] = lambda: user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_admin_user, None)
        app.dependency_overrides.pop(get_current_active_user, None)
```

#### Discriminator for the planner
- **Pick Option A (trading-engine)** if the test fixture talks directly to trading-engine port 8005 (host-side pytest, CONTEXT D-02). No JWT minting. Simplest.
- **Pick Option B (api-gateway)** if the suite must exercise the gateway auth path end-to-end (matches "fresh-clone proof boundary" stronger). Adds JWT-mint complexity OR `admin_client` dep-override (only works inside `services/api-gateway/tests/`, not host-side suite).
- Default stance per CONTEXT code_context note ("force-signal admin endpoint ↔ trading-engine — synthetic-signal entry point (CD-04)"): **Option A**.

---

### `scripts/iter-fix.sh` (NEW)

**Analog:** `bootstrap.sh` (style only — color codes, `set -e`, step-numbered echoes)

**No functional analog in the codebase.** Synthesize per CONTEXT D-09..D-12.

**Style reference** (`bootstrap.sh:22-23, 27-32`):
```bash
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
cd "$REPO_ROOT"
```

**Required behaviors per D-09..D-12 (all synthesis)**:
1. Run `pytest tests/integration -x` and capture failure log on first red.
2. Allow operator (or wrapped Claude `-p`) to propose a fix → `git diff` to terminal.
3. Diff-grep enforcement (D-12) — `grep -E '^\+.*(unittest\.mock|mocker\.patch|pytest\.skip|pytest\.mark\.xfail)' <(git diff -- 'tests/')` MUST be empty before applying.
4. Threshold-lowering check — refuse diffs that lower numeric assertions in `tests/` (e.g., `< 60.0` → `< 120.0`). Suggested implementation: `grep -E '^[+-].*assert.*<\s*[0-9]'` and require manual approval if both - and + variants present.
5. Inline `Apply? [y/N]` prompt; on yes → `git add -p` + `git commit -m "fix(<service>): <one-line>"`.
6. Per-fix atomic commits (D-09, D-11) — one commit per accepted fix; failed-attempt branches tagged `wip(iter)` so `git restore` is cheap.

**No-auto-retry rule** (matches `bootstrap.sh:135` "D-13: NO auto-teardown, NO auto-retry"). After one fix attempt, hand control back to operator. No "iterate until 3 green" loop (Goodhart trap, project rule).

---

### `RUNBOOK.md` at repo root (NEW)

**EXISTING FILE CONFLICT — planner must decide:**

There is already a `docs/operations/RUNBOOK.md` (lines 1-100 read; 6-section ops format: Service Management, Monitoring & Alerts, Common Issues & Solutions, Deployment Procedures, Emergency Procedures, Maintenance Tasks). It dates 2025-11-16 and references `docker-compose.yml` (NOT canonical `docker-compose.unified.yml`).

**CONTEXT CD-03 specifies a NEW failure-triage-first RUNBOOK at `RUNBOOK.md` (repo root) with sections per symptom: BuildKit hang, docker context misconfig, bind-mount race, stale-model restart, bootstrap-test failure triage, EMERGENCY_STOP recovery.**

**Three viable resolutions for the planner:**
- (a) **Two RUNBOOKs** — root `RUNBOOK.md` = failure-triage (Phase 2 deliverable); `docs/operations/RUNBOOK.md` = nominal ops. Most operator-friendly (root = "stack broke, what now"; docs/ = "how do I deploy"). Add cross-link in both.
- (b) **Move + replace** — delete `docs/operations/RUNBOOK.md` (stale references, points at non-canonical compose), put failure-triage at root.
- (c) **Merge** — extend existing `docs/operations/RUNBOOK.md` with a new "Failure Triage" section, no root file. Diverges from CONTEXT CD-03 ("`RUNBOOK.md` covering ...").

Default stance per CONTEXT CD-03 wording: **(a) Two RUNBOOKs** — keep nominal ops where it is, add failure-triage at root.

**Symptom format (no in-repo failure-triage analog; synthesize):**
```markdown
### Symptom: BuildKit hang on `docker compose up --build`

**Diagnose:**
- `docker context show` — must be `default` (Unix socket), NOT `desktop-linux`
- `cat /proc/version | grep -i microsoft` — confirms WSL2

**Action:**
```bash
DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml build <svc>
# OR use:
make build-no-buildkit
```

**Verification:**
- `docker compose -f docker-compose.unified.yml ps` — service shows `Up (healthy)`
- `docker compose logs <svc> | tail -20` — no build-stage stalls
```

Pull each symptom from CLAUDE.md "Environment" + "Gotchas" sections (load-bearing per CONTEXT canonical_refs).

---

### `Makefile` at repo root (NEW)

**No Makefile exists in the repo.** Synthesize per CONTEXT CD-02.

**Style references (synthesis sources):**
- `bootstrap.sh:42-49` — `DOCKER_BUILDKIT=0` workaround logic to encode as `make build-no-buildkit`
- `health_check.sh` — pattern for `make health-check` if added

**Suggested skeleton (per CD-02 + INFRA-06):**
```makefile
.PHONY: bootstrap build-no-buildkit health-check test-integration iter-fix

bootstrap:
	bash bootstrap.sh

build-no-buildkit:
	DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml build $(SVC)

health-check:
	bash health_check.sh

test-integration:
	pytest tests/integration -v

iter-fix:
	bash scripts/iter-fix.sh
```

---

### `.github/workflows/integration.yml` (NEW)

**Analog:** `.github/workflows/live-smoke.yml` (Phase 1 Plan 04 — read in full above) — host-runs `bootstrap.sh`, host-side pytest, log-artifact upload, `down -v` cleanup.

**Triggers diverge from live-smoke** (per CONTEXT D-07: "local + CI, same `pytest tests/integration` invocation"):
```yaml
# COPY shape from live-smoke.yml:1-21, BUT change triggers:
on:
  push:
    branches: ['**']
  pull_request:
    branches: [main, develop]
# NOT: schedule.cron — that's live-smoke. Phase 2 deterministic CI runs on every push/PR.

concurrency:
  group: integration-${{ github.ref }}
  cancel-in-progress: true
```

**Job body pattern (copy from `live-smoke.yml:18-50`, adjust for tape-mode default)**:
```yaml
jobs:
  integration:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - name: Boot stack via bootstrap.sh in tape mode
        env:
          MARKET_DATA_SOURCE: tape    # default per Phase 1 D-14
          PAPER_TRADING_MODE: 'true'
          TRADING_MODE: PAPER
          AUTO_TRADING_ENABLED: 'true'
          ENABLE_ML_PREDICTIONS: 'false'
          ENABLE_SENTIMENT_ANALYSIS: 'false'
          NOTIFICATION_TEST_MODE: live  # CD-01 — CI uses real test bot
          TELEGRAM_BOT_TOKEN: ${{ secrets.TEST_TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TEST_TELEGRAM_CHAT_ID }}
        run: |
          : > .env  # D-06: empty .env on bootstrap entry
          bash bootstrap.sh
      - name: Run integration suite
        run: |
          pytest tests/integration -v
      - name: Anti-mock guard
        run: |
          # D-12: refuse diffs that added mocks/skips/threshold-lowering to tests/
          git diff origin/main..HEAD -- 'tests/' \
            | grep -E '^\+.*(unittest\.mock|mocker\.patch|pytest\.skip|pytest\.mark\.xfail)' \
            && (echo "::error::Disallowed test mutation"; exit 1) || true
      - name: Collect logs
        if: always()
        run: docker compose -f docker-compose.unified.yml logs > integration-logs.txt 2>&1
      - name: Upload logs
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: integration-logs
          path: integration-logs.txt
          retention-days: 14
      - name: Cleanup
        if: always()
        run: docker compose -f docker-compose.unified.yml down -v || true
```

**Diverge from live-smoke (do NOT copy):**
- `continue-on-error: true` on probe step — Phase 2 deterministic suite must FAIL hard on red. live-smoke is allowed to be flaky; integration is not (D-07).
- Nightly cron — Phase 2 runs on every push/PR.

---

### `.env.test.example` (NEW)

**Analog:** `.env.example` (style only — KEY=VALUE per line, comments with `#`)

**No test-env analog in repo.** Synthesize per CONTEXT CD-01.

**Suggested content:**
```bash
# Test-mode environment overrides for tests/integration/
# Copy to .env.test (gitignored) and fill in TEST_TELEGRAM_BOT_TOKEN / TEST_TELEGRAM_CHAT_ID
# Local default uses NOTIFICATION_TEST_MODE=record; flip to live only with real test bot.

MARKET_DATA_SOURCE=tape
PAPER_TRADING_MODE=true
TRADING_MODE=PAPER
AUTO_TRADING_ENABLED=true
ENABLE_ML_PREDICTIONS=false
ENABLE_SENTIMENT_ANALYSIS=false

# Notification verification (CD-01)
# - record (default, local): write would-be sends to tests/.notifications.log
# - live (CI):   send to dedicated test Telegram bot in private channel; assert via getUpdates
NOTIFICATION_TEST_MODE=record
TEST_TELEGRAM_BOT_TOKEN=
TEST_TELEGRAM_CHAT_ID=
```

---

## Shared Patterns

### Loud, grep-able startup/state-transition log lines
**Source:** `services/bybit-connector/app/main.py:314-316`
```python
logger.warning(
    "BYBIT_PRICE_SOURCE: mode=tape source_dir=%s tape_version=1",
    settings.tape_fixtures_path,
)
```
**Apply to:** All new admin endpoints and state mutations (`/admin/tape/reset`, `force-signal`, `iter-fix.sh` accepted-fix commits). Log a single grep-able prefix line per state change. Example shape: `TAPE_REPLAY: cursor reset`, `FORCE_SIGNAL: strategy_id=... symbol=... action=...`. CI log audits + RUNBOOK triage rely on these.

### Auth boundary — services have no auth; api-gateway does
**Sources:**
- `services/trading-engine/app/handlers/orchestration.py:703-705` ("trading-engine has no auth middleware; all admin routes are protected upstream at the api-gateway")
- `services/api-gateway/tests/conftest.py:30-46` (`admin_client` fixture for api-gateway-only tests)

**Apply to:** `force-signal` host decision (Option A vs B). Tests against bybit-connector / trading-engine ports use plain `httpx.AsyncClient` — no JWT. Tests against api-gateway port use `admin_client` fixture WHICH IS api-gateway-tests-only (cannot import from `tests/integration/`). Phase 2 host-side suite cannot dep-override `app.dependency_overrides`; it goes over the wire and would need a real JWT.

### `pathlib.Path.write_text` mocking trap
**Source:** Memory `feedback_pathlib_mocking.md` + `services/api-gateway/app/main.py:1428` (`stop_file.write_text(...)`)
**Apply to:** Any new test mocking file IO (e.g., notification log writer, EMERGENCY_STOP recovery test). `mock.patch("builtins.open")` is silently a no-op — `Path.write_text` / `Path.read_text` go through `_io.open` (C-level). Patch `pathlib.Path.write_text` directly.

### api-gateway test environment quirk (do NOT subsume)
**Source:** Memory `feedback_api_gateway_test_env.md`
**Apply to:** Phase 2 suite scope. The host-side `pytest tests/integration` does NOT subsume `services/api-gateway/tests/` — that suite still runs `docker exec crypto-bot-api-gateway pytest` because host pip has fastapi 0.136 (returns 401 on HTTPBearer auto_error) while container pins 0.109 (returns 403). Integration suite asserts service-level behavior; api-gateway unit suite asserts internal middleware. Both stay.

### asyncpg pool + DB TRUNCATE between tests
**Source:** `services/portfolio-manager/app/main.py:165-170`
```python
db_pool = await asyncpg.create_pool(
    settings.database_url,
    min_size=2,
    max_size=10,
    command_timeout=60
)
```
**Apply to:** New `db_truncate` fixture in `tests/integration/conftest.py`. No `TRUNCATE`-between-tests fixture exists in repo — synthesize. Tables to clear per CONTEXT code_context: `klines`, `tickers`, `positions`, `orders`. Schema preserved; `RESTART IDENTITY CASCADE` clears.

---

## No Analog Found

Files with no close match in the codebase (planner should synthesize from CONTEXT decisions or RESEARCH.md):

| File | Role | Data Flow | Why no analog |
|------|------|-----------|---------------|
| `scripts/iter-fix.sh` | utility | event-driven | No interactive shell harness exists; closest is `bootstrap.sh` (style only, no diff-review loop) |
| `RUNBOOK.md` (root, failure-triage-first) | docs | n/a | Existing `docs/operations/RUNBOOK.md` is nominal-ops format (6 standard ops sections); failure-triage-first is a different shape |
| `Makefile` | config | n/a | No Makefile in repo — encode `bootstrap.sh:42-49` BuildKit-off logic as a `make` target |
| `.env.test.example` | config | n/a | No test-env template exists; synthesize from CD-01 + `.env.example` style |
| `tape_replay_client.py:reset()` | service | internal state | Current loader is stateless (no cursor); planner decides whether to add cursor or make `reset()` a no-op |
| `db_truncate` fixture | test | db lifecycle | No `TRUNCATE`-between-tests fixture exists; synthesize using `asyncpg.create_pool` pattern |

---

## Discriminators for the planner

1. **`force-signal` host:** Option A (trading-engine `:8005/api/v1/admin/force-signal`, no auth) vs Option B (api-gateway `:8000/api/trading/force-signal`, admin-guarded). Default A per CONTEXT code_context note.
2. **`tape_replay_client.reset()` semantics:** No-op + log line (current loader is stateless) vs add cursor field then zero. Default add cursor for forward-compat.
3. **`RUNBOOK.md` placement:** (a) two files (root failure-triage + existing docs/ ops), (b) move/replace, (c) merge into existing. Default (a) per CD-03 wording.
4. **`Makefile` scope:** minimal (`build-no-buildkit` only) vs convenience targets (`bootstrap`, `health-check`, `test-integration`, `iter-fix`). Default minimal per "synthesize the smallest thing per CD-02" reading.
5. **NOTIFICATION_TEST_MODE local default:** `record` (writes to `tests/.notifications.log`) per CD-01; CI flips to `live`.

---

## Metadata

**Analog search scope:**
- `tests/integration/`, `tests/e2e/`
- `services/bybit-connector/app/`, `services/trading-engine/app/handlers/`, `services/api-gateway/app/`, `services/api-gateway/tests/`, `services/portfolio-manager/app/`, `services/notification-service/app/`
- `.github/workflows/`
- `bootstrap.sh`, `health_check.sh`, `scripts/`
- `docs/operations/`, `.env.example`

**Files scanned:** 18 source files, 7 test files, 3 workflow files, 2 shell scripts, 1 doc file.

**Pattern extraction date:** 2026-05-07
