# Testing Patterns

**Analysis Date:** 2026-05-12

## Test Framework

**Runner:** `pytest`

**Async support:** `pytest-asyncio` (FastAPI handlers are async)

**HTTP mocking:** `respx` (httpx-aware) for outbound HTTP stubs

**FastAPI test client:** `fastapi.testclient.TestClient` (sync) and `httpx.AsyncClient` (async)

**Run commands:**
```bash
pytest tests/                            # repo-level integration + e2e
pytest services/<svc>/tests/             # service-level unit tests
pytest --cov=services --cov-report=term  # with coverage
```

## Test File Organization

**Two-tier layout:**

```
crypto-trading-bot/
├── tests/                          # repo-level: integration, e2e, bootstrap
│   └── test_*.py
└── services/<svc>/
    └── tests/                      # service-level: unit tests
        ├── conftest.py             # service-specific fixtures
        └── test_*.py
```

**Naming:** `test_<module_under_test>.py`. Class-based grouping (`class TestFoo:`) for related cases; flat functions otherwise.

## Test Structure

**Suite Organization (typical):**
```python
import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)

class TestPortfolioRoutes:
    def test_get_balance_returns_200(self, client):
        response = client.get("/api/portfolio/balance")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_async_handler(self):
        ...
```

## Health Endpoints (every service)

- `GET /health` — liveness (process up, no deep checks)
- `GET /ready` — readiness (DB/Redis/RabbitMQ reachable)

Test both as smoke checks before running suite.

## Mocking

**HTTP outbound:** `respx`
```python
import respx, httpx

@respx.mock
async def test_bybit_call():
    respx.get("https://api.bybit.com/v5/market/tickers").mock(
        return_value=httpx.Response(200, json={...})
    )
    # call code under test
```

**Pathlib gotcha (load-bearing):**
- **Mock `pathlib.Path.write_text` / `Path.read_text` / `Path.open` directly — NOT `builtins.open`.**
- `Path.write_text` and `Path.read_text` route through `_io.open` (C-level), bypassing `builtins.open`.
- `mock.patch("builtins.open")` silently does nothing against Path methods.
- Example: `/api/portfolio/emergency-stop` writes the `EMERGENCY_STOP` file via `Path.write_text`. Tests must patch `pathlib.Path.write_text`.

```python
from unittest.mock import patch
with patch("pathlib.Path.write_text") as m:
    client.post("/api/portfolio/emergency-stop")
    m.assert_called_once()
```

**Imports stripped by autoflake:** if test mocks `service.main.foo`, the import of `foo` into `main.py` must carry `# noqa: F401` to survive autoflake — otherwise patch target vanishes after refactor.

## Fixtures and Factories

**`admin_client` fixture** (`services/api-gateway/tests/conftest.py`):
- Required for any admin-guarded route — plain `test_client` returns 403
- Overrides `get_current_admin_user` and `get_current_active_user` via `app.dependency_overrides`

```python
def test_admin_route_with_admin_client(admin_client):
    response = admin_client.post("/api/admin/something")
    assert response.status_code == 200
```

**Service-level conftest:** each `services/<svc>/tests/conftest.py` provides app/client fixtures, DB seeders, and mock external clients (Bybit, etc.).

## api-gateway Test Environment (load-bearing)

**Run inside the container — not on host:**

```bash
docker exec crypto-bot-api-gateway pytest
```

**Why:** host pip typically has **fastapi 0.136** which changed `HTTPBearer` `auto_error` behavior to return **401** per RFC 6750. Deployed container pins **fastapi 0.109** which returns **403**. Tests assert **403**. Running on host shows spurious failures only on these auth-related assertions.

## Local Pytest Without Docker

When the user explicitly opts out of Docker, install missing deps the host venv lacks:

```bash
pip install tensorflow-cpu respx aiohttp
```

- `tensorflow-cpu` — needed because GRU models import TF at module load (some service tests touch ml-prediction-service or technical-analysis paths)
- `respx` — httpx mocking for outbound HTTP stubs
- `aiohttp` — required by some legacy async clients

## Bootstrap Tests

**Run against a fresh clone in a tmp directory** — never against the live working tree.

- Avoids state contamination from local artifacts (`EMERGENCY_STOP` file, `.env`, cached models, mutated DB)
- Performance budget: full paper-trade round-trip (signal → order ack → portfolio update) **< 60 seconds** end-to-end

## Coverage

**Command:**
```bash
pytest --cov=services --cov-report=term
pytest --cov=services --cov-report=html  # local browser inspection
```

**Targets:** no hard-enforced threshold yet; treat <70% on a changed module as a smell.

## Test Types

**Unit tests** (`services/<svc>/tests/`):
- Single module / class scope
- External clients (Bybit, DB, Redis) mocked

**Integration tests** (`tests/`):
- Multi-service interactions through real HTTP between containers
- Require `docker compose -f docker-compose.unified.yml up -d` running first

**E2E tests** (`tests/`):
- Full flow: market data → signal → trading-engine → portfolio update → notification
- Run against compose stack with paper-trading mode

## ML Evaluation Standards

**Forbidden:** raw R² on price levels (look-ahead leakage trap that bit V0 of the GRU stack).

**Required for any ML edge claim:**
- `returns_metrics.py` — performance on log-returns target
- `sharpe_metrics.py` — PSR (Probabilistic Sharpe) and **DSR (Deflated Sharpe) > 0.95** acceptance gate
- `cpcv.py` — Combinatorial Purged Cross-Validation (no train/test leakage across embargo)

**Performance metric (Profit Factor) gotcha:**
- Use **pooled `sum(wins) / sum(losses)`** across folds — NOT mean of per-fold PFs.
- Mean-of-fold-PFs drags toward ≈1.0 on small folds; pooled PF reflects true edge.

## Common Patterns

**Async testing:**
```python
@pytest.mark.asyncio
async def test_async_route():
    async with httpx.AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/api/portfolio/balance")
    assert r.status_code == 200
```

**Error testing:**
```python
def test_returns_400_on_bad_input(client):
    r = client.post("/api/trading/order", json={"symbol": ""})
    assert r.status_code == 400
    assert "symbol" in r.json()["detail"].lower()
```

## Verification Standard (load-bearing — `verify-stack` skill)

**Never declare anything "working end-to-end" on HTTP 200 alone.** All four must pass:

1. **Live exchange URL in service logs** — confirm `api.bybit.com` (mainnet) appears, NOT `api-testnet.bybit.com`. Grep service logs.
2. **Downstream notification actually received** — Telegram message arriving on phone / email in inbox. `"sent": true` in a JSON response is NOT proof.
3. **DB row persisted** — run an actual `SELECT` against postgres/timescale and paste the row. In-memory state can lie.
4. **Service restarted after config change** — most common false-pass is hitting a service that's still running with the old in-memory config. Restart, then re-test.

**Tool:** `.claude/skills/verify-stack/SKILL.md` encodes this checklist. Invoke before any "shipped" / "deployed" / "working" claim.

## Low-Price Asset Rounding (regression to avoid)

**Never `round(price, 2)` on price-domain fields for sub-$1 assets.** ADAUSDT at ~$0.45 produced 30+ flip-flop losses when rounding to 2dp because adjacent ticks collapsed. Use `float(price)` — preserve full precision through the TA pipeline. Fixed in commit `487d1bd`. Regression tests on low-priced symbols (ADA, DOGE-class) should assert precision preservation.

---

*Testing analysis: 2026-05-12*
