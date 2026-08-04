# Testing Patterns

**Analysis Date:** 2026-05-22

## Test Framework

**Runner:** pytest (configured in `pytest.ini` and `pyproject.toml`)

**Key plugins:**
- `pytest-asyncio >= 0.21.0` — async test support
- `pytest-cov >= 4.1.0` — coverage
- `pytest-mock >= 3.11.0` — mock helpers
- `respx` — httpx mock library for async HTTP
- `aioresponses` — aiohttp mock (where aiohttp is used)
- `pytest-timeout` — 300s default timeout per test

**Assertion library:** stdlib `assert` + `unittest.mock` (no Hamcrest or similar)

**Run commands:**
```bash
# All repo-level integration + e2e tests
pytest tests/

# Single service unit tests
pytest services/<svc>/tests/

# With coverage
pytest services/<svc>/tests/ --cov=. --cov-report=xml --cov-report=term-missing

# Skip slow tests (CI default)
pytest services/<svc>/tests/ -m "not slow"

# ML-gated tests (requires ENABLE_ML_PREDICTIONS=true)
pytest -m "ml_on"

# Run from repo root (all services)
pytest --cov=services --cov-report=term
```

**Config files:**
- Root: `pytest.ini` (repo-wide, authoritative for `tests/` directory)
- Per-service: `services/<svc>/pytest.ini` — **authoritative in CI** (CI runs `cd services/<svc> && pytest tests/`, not from root)

## Async Mode

**`asyncio_mode = auto`** — set in both root `pytest.ini` and all service-level `pytest.ini` files.

This means: **do NOT add `@pytest.mark.asyncio`** to new async tests. The decorator is redundant and creates noise.

**Legacy decoration:** 1,476 existing `@pytest.mark.asyncio` decorators remain from before auto mode was enabled. These are harmless but should not be copied when writing new tests.

**DO NOT define a custom `event_loop` fixture.** It was deprecated in pytest-asyncio 0.23 and removed from `services/trading-engine/tests/conftest.py` because it caused `linecache` errors in container. Use the default event loop provided by pytest-asyncio.

## Test File Organization

**Layout: bimodal (per-service unit + repo-level integration)**

```
crypto-trading-bot/
├── pytest.ini                          # root config
├── tests/
│   ├── integration/
│   │   ├── conftest.py                 # bootstrap_stack, db fixtures
│   │   └── test_*.py                   # multi-service integration tests
│   ├── e2e/
│   │   ├── conftest.py                 # ServiceClient hierarchy, e2e fixtures
│   │   └── test_*.py                   # end-to-end scenarios
│   └── test_bootstrap_script_static.py # static bootstrap.sh analysis (no Docker)
└── services/
    └── <svc>/
        ├── pytest.ini                  # service-level config (authoritative in CI)
        └── tests/
            ├── conftest.py             # service-specific fixtures
            └── test_*.py              # unit tests
```

**Naming:** `test_<module>.py` required (pre-commit `name-tests-test --pytest-test-first` enforces this).

## Test Markers

Defined in root `pytest.ini`. Use `@pytest.mark.<marker>` or `pytestmark = pytest.mark.<marker>` at module level.

| Marker | Use |
|--------|-----|
| `unit` | Fast, no external deps |
| `integration` | Requires running containers |
| `e2e` | Full stack end-to-end |
| `slow` | Long-running (excluded from CI default: `-m "not slow"`) |
| `security` | Security-focused tests |
| `performance` | Load/perf tests |
| `smoke` | Quick health checks |
| `database` | Requires real DB |
| `redis` | Requires Redis |
| `rabbitmq` | Requires RabbitMQ |
| `api` | HTTP API tests |
| `websocket` | WS tests |
| `bybit` | Bybit-specific |
| `ml` | ML-related |
| `ml_on` | Requires `ENABLE_ML_PREDICTIONS=true` (opt-in, nightly+manual only) |
| `skip_ci` | Skip in CI |

## CRITICAL: Skip Density Health Signal

**75 test files** contain the exact line:
```python
pytestmark = pytest.mark.skip(reason="stale tests after PR #86 refactor; needs rewrite")
```

This is the dominant health signal — many service test suites are nearly empty of real running tests. When a file shows this mark, treat the entire file's tests as non-running. **Do not assume test presence = test coverage.**

When adding new tests to a service, check `grep -r "pytestmark = pytest.mark.skip" services/<svc>/tests/` first to understand actual coverage baseline.

## CI Status Warning

**GH Actions billing is blocked (OP-04).** CI workflows in `.github/workflows/ci.yml` exist but do not run.

Even when CI was active:
- All linter steps end with `|| true` — linter failures never block PRs
- `--cov-fail-under` is intentionally omitted from the matrix job (comment: "restore once coverage is back above threshold")
- Coverage is reported as warning only, never as a gate

**"Green CI" is not a meaningful signal for this project.** Verification requires running tests locally or in containers.

## Mocking Conventions

### Service Unit Tests: DB Mocking at Import Level

Unit tests in service `tests/` mock the database at module import time. This is the canonical pattern from `services/trading-engine/tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
def mock_database_connection():
    """Mock database at import level for all unit tests."""
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock(return_value=MagicMock())
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)

    with patch.dict('sys.modules', {
        'database.connection': MagicMock(get_db_connection=AsyncMock(return_value=mock_conn))
    }):
        yield mock_conn
```

**Why `patch.dict('sys.modules', ...)`:** Intercepts at import resolution, not at call site. Required when the module-under-test imports `database.connection` at module load time.

**MockAsyncSession pattern:**
```python
class MockAsyncSession:
    async def execute(self, *args, **kwargs): return MagicMock()
    async def commit(self): pass
    async def rollback(self): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
```

### Integration Tests: Real DB Required

Integration tests in `tests/integration/` use **real containers** via `bootstrap_stack` fixture. No DB mocking. Real asyncpg connections to TimescaleDB and PostgreSQL.

```python
# tests/integration/conftest.py
@pytest.fixture(scope="session")
def bootstrap_stack():
    """Shell to bootstrap.sh in fresh clone, poll /health for 10 services."""
    ...

@pytest.fixture
async def db_truncate(bootstrap_stack):
    """TRUNCATE klines/tickers (timescale) and positions/orders (postgres) via asyncpg."""
    ...
```

**Never mock the DB in integration tests.** The whole point is verifying real persistence.

### HTTP Mocking: respx for httpx

All async HTTP client mocking uses `respx`. Canonical pattern from `services/notification-service/tests/test_slack_client.py`:

```python
import respx
from httpx import Response

@respx.mock
async def test_bot_token_calls_chat_postmessage(monkeypatch):
    route = respx.post("https://slack.com/api/chat.postMessage").mock(
        return_value=Response(200, json={"ok": True, "ts": "1.2"})
    )
    client = SlackClient()
    result = await client.send("hello", ...)
    assert route.called
    sent = route.calls[0].request
    assert json.loads(sent.content)["text"] == "hello"
```

**Use `@respx.mock` decorator** (not `with respx.mock():` context) for cleaner async test functions.

### General Mocking: unittest.mock

Primary mock framework is stdlib `unittest.mock`:
- `MagicMock` for synchronous mocks
- `AsyncMock` for coroutines (required for any `async def` method)
- `patch` / `patch.dict` / `patch.object` for targeted replacement
- `monkeypatch` (pytest fixture) for env vars and simple attribute replacement

```python
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# AsyncMock required for async methods
proxy = Mock(spec=ServiceProxy)
proxy.initialize = AsyncMock()
proxy.proxy_request = AsyncMock(return_value={"status": 200})

# patch.dict for env vars
@pytest.fixture(autouse=True)
def test_environment(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("BYBIT_TESTNET", "false")
```

### What NOT to Mock

**In unit tests:**
- Do mock: DB connections, external HTTP calls, message queue connections, file I/O
- Do NOT mock: Pydantic validation, the service's own business logic, pure functions

**In integration tests:**
- Do NOT mock: DB, Redis, RabbitMQ, inter-service HTTP (real containers required)
- Do mock: External exchange APIs (Bybit) — use `market_data_source=tape` or `respx`

## Conftest Patterns

### Root conftest: `tests/integration/conftest.py`

Key fixtures available to integration tests:

```python
bootstrap_stack       # session-scoped, shells bootstrap.sh in fresh clone
db_truncate           # truncates klines/tickers/positions/orders
tape_reset            # POST /admin/tape/reset to bybit-connector
notification_received # mode-aware (record vs live Telegram)
force_signal          # sends synthetic signal to trading-engine
tmp_fresh_clone       # git clone to temp dir
```

### E2E conftest: `tests/e2e/conftest.py`

Imports integration conftest:
```python
pytest_plugins = ["tests.integration.conftest"]
```

Key fixtures:
```python
ensure_services_healthy       # session-scoped health probe
cleanup_between_tests         # autouse teardown
leaderboard_dsr_seeded        # seeds sqlite3 + MLGATE marker
all_preflight_checks_passing  # LIVE-mode override compose
```

**ServiceClient hierarchy:**
```python
class ServiceClient:  # base class
    ...
class MarketDataClient(ServiceClient): ...
class TradingEngineClient(ServiceClient): ...
class PortfolioClient(ServiceClient): ...
class TechnicalAnalysisClient(ServiceClient): ...
class APIGatewayClient(ServiceClient): ...
```

### api-gateway conftest: `services/api-gateway/tests/conftest.py`

**`admin_client` fixture** — required for admin-guarded routes:

```python
@pytest.fixture
def admin_client():
    """Override FastAPI dependency injection to bypass real auth."""
    user = _fake_admin()
    app.dependency_overrides[get_current_admin_user] = lambda: user
    app.dependency_overrides[get_current_active_user] = lambda: user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_admin_user, None)
        app.dependency_overrides.pop(get_current_active_user, None)
```

Use `admin_client` (not `test_client`) for any route decorated with `get_current_admin_user`. Plain `test_client` returns 403 on these routes — that's correct behavior, not a bug.

**`test_client` fixture** — plain TestClient, no auth overrides:
```python
@pytest.fixture
def test_client():
    return TestClient(app)
```

### trading-engine conftest: `services/trading-engine/tests/conftest.py`

Autouse DB mock (described above), autouse test env vars, repository mocks:
```python
@pytest.fixture
def position_repository():
    return MagicMock()

@pytest.fixture
def trade_repository():
    return MagicMock()
```

## Critical Mocking Gotchas

### pathlib.Path.write_text — MUST patch directly

`Path.write_text`, `Path.read_text`, `Path.open` go through `_io.open` (C-level), **not** `builtins.open`. Patching `builtins.open` silently does nothing.

**Wrong:**
```python
with patch("builtins.open") as mock_open:  # silently fails for Path.write_text
    response = client.post("/api/portfolio/emergency-stop")
    mock_open.assert_called()  # never called
```

**Correct:**
```python
with patch("pathlib.Path.write_text") as mock_write:  # intercepts Path.write_text
    response = client.post("/api/portfolio/emergency-stop")
    mock_write.assert_called_once()
```

Reference: `services/api-gateway/tests/test_main.py` line 283.

### api-gateway tests: run in container only

Host pip has `fastapi 0.136` — `HTTPBearer` returns HTTP 401 (RFC 6750 compliant).
Container pins `fastapi 0.109` — `HTTPBearer` returns HTTP 403.

Tests assert 403. Running on host produces 401 → spurious failures.

**Always run api-gateway tests in the container:**
```bash
docker exec crypto-bot-api-gateway pytest tests/
```

Not: `cd services/api-gateway && pytest tests/`

## Coverage

**Target:** 80% line + branch coverage (`fail_under = 80`, `branch = true` in `pyproject.toml`)

**Currently enforced:** Warning only. `--cov-fail-under` omitted from CI job. Coverage below 80% does not block anything in practice.

**View coverage:**
```bash
pytest services/<svc>/tests/ --cov=. --cov-report=term-missing
pytest services/<svc>/tests/ --cov=. --cov-report=html  # open htmlcov/index.html
```

**Exclusions:** `[tool.coverage.report]` in `pyproject.toml` excludes `tests/`, `*/__init__.py`, stubs.

## Test Types

### Unit Tests (`services/<svc>/tests/`)

- Scope: single service, no external deps
- DB mocked via `patch.dict('sys.modules', ...)`
- HTTP mocked via `respx` or `unittest.mock`
- Run without Docker: `pytest services/<svc>/tests/ -m "not integration"`
- Fast: < 5s per file expected

### Integration Tests (`tests/integration/`)

- Scope: multi-service, real containers required
- Requires `bootstrap_stack` (boots all 11 services + DBs)
- DB state reset via `db_truncate` fixture
- Run: `pytest tests/integration/` (requires running stack)

### E2E Tests (`tests/e2e/`)

- Scope: full user journeys across all services
- Builds on `tests/integration/conftest.py` via `pytest_plugins`
- ServiceClient classes make HTTP calls to real running services
- Run: `pytest tests/e2e/` (requires running stack)

### Static Analysis Tests (`tests/test_bootstrap_script_static.py`)

- No Docker required. Loads `bootstrap.sh` via `Path.read_text()` and asserts on text content.
- Module-scoped `script_text` fixture. Tests verify presence of critical steps (EMERGENCY_STOP creation, health probe logic, compose file reference, WSL2 BuildKit workaround).

```python
@pytest.fixture(scope="module")
def script_text():
    return Path("bootstrap.sh").read_text()

def test_creates_emergency_stop(script_text):
    assert "touch EMERGENCY_STOP" in script_text
```

### Frontend Tests (`frontend/src/__tests__/`)

- Framework: Vitest 1.6.0 + @testing-library/react 14
- Pattern: `vi.mock()` for module stubbing, `render()` + `screen` queries
- Run: `cd frontend && npm test` or `npm run test:ui`
- Reference: `frontend/src/__tests__/App.test.jsx`

```jsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('../api/marketData', () => ({ fetchTicker: vi.fn() }));

describe('App', () => {
  it('renders market data panel', () => {
    render(<App />);
    expect(screen.getByText('Market Data')).toBeInTheDocument();
  });
});
```

## ML / Backtest Validation

**ML tests require explicit opt-in:** `@pytest.mark.ml_on` (or `pytestmark = pytest.mark.ml_on`). These tests set `ENABLE_ML_PREDICTIONS=true` and require the leaderboard DSR gate seeded. Not run in default CI.

**CPCV validation tests:** `services/risk-metrics-service/tests/test_cpcv.py` — class-based `TestCombinatorics`. Tests cover: combinatorics math, fold coverage, purge/embargo correctness, leakage detection, DSR bridge.

**DSR gate:** `cpcv_to_dsr()` from `services/risk-metrics-service/app/cpcv.py`. Gate threshold: DSR > 0.95 on log-returns target. Evaluated via `sharpe_metrics.deflated_sharpe_ratio`.

**Returns metrics (not price-level R²):**
```python
# services/ml-retraining-service/app/core/returns_metrics.py
compute_returns_metrics(actual_prices, pred_prices, last_close, dataset_name)
# returns: r2_returns (R² on log-returns), dir_acc_corrected (no look-ahead)
```

**Backtest data filter — mandatory:**
```python
# Always filter is_mainnet=true
# TimescaleDB has mixed testnet/mainnet history before 2026-04-25 (testnet flip)
# Any candle without is_mainnet=true may be testnet price
WHERE is_mainnet = true
```

Failure to filter produces contaminated backtest results. This applies to all queries against `klines` and `tickers` tables for historical analysis.

## Async Testing Patterns

**Standard async test (no decorator needed):**
```python
async def test_fetch_ticker():
    # asyncio_mode=auto handles event loop
    result = await some_async_function()
    assert result["symbol"] == "BTCUSDT"
```

**respx async mock:**
```python
@respx.mock
async def test_http_call():
    respx.get("https://api.bybit.com/v5/market/tickers").mock(
        return_value=Response(200, json={"retCode": 0, "result": {...}})
    )
    result = await client.get_ticker("BTCUSDT")
    assert result["symbol"] == "BTCUSDT"
```

**Error testing:**
```python
async def test_raises_on_invalid_symbol():
    with pytest.raises(ValidationError, match="symbol"):
        await client.get_ticker("INVALID_SYMBOL_XYZ")
```

**Timeout testing:**
```python
async def test_circuit_breaker_opens():
    with patch("app.services.bybit_client.httpx.AsyncClient.get",
               side_effect=httpx.TimeoutException("timeout")):
        with pytest.raises(CircuitBreakerException):
            for _ in range(6):  # exceed threshold of 5
                await client.get_ticker("BTCUSDT")
```

---

*Testing analysis: 2026-05-22*
