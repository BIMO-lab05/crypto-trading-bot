# Phase 1: Bootstrap & Recorded Tape - Pattern Map

**Mapped:** 2026-05-06
**Files analyzed:** 14 (1 NEW shell + 10 NEW JSONL fixtures + 1 NEW capture script + 1 NEW workflow + 1 NEW unit + 2 MOD)
**Analogs found:** 11 / 14 (3 fixtures have no direct in-repo analog — see "No Analog Found")

> Scope per CONTEXT.md / D-01..D-17. Quotes are file:line excerpts (≤30 lines each); planner copies these patterns directly into plan actions.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `bootstrap.sh` (NEW) | utility (operator script) | request-response + file-I/O | `health_check.sh` + `build-all.sh` | exact (shell-style) |
| `tests/fixtures/tape/klines/{BTC,ETH,SOL,BNB,ADA}USDT.jsonl` (NEW × 5) | test fixture | streaming (replayed JSONL) | none (see "No Analog Found") | none |
| `tests/fixtures/tape/ticker/{BTC,ETH,SOL,BNB,ADA}USDT.jsonl` (NEW × 5) | test fixture | streaming (replayed JSONL) | none (see "No Analog Found") | none |
| `scripts/tape/capture_bybit.py` (NEW) | utility (one-shot script) | request-response → file-I/O | `scripts/collect_bybit_direct_180days.py` | exact (role + flow) |
| `services/bybit-connector/app/main.py` (MOD) | controller/lifespan | request-response | self (existing routes preserved; lifespan branches) | self-extension |
| `services/bybit-connector/app/config.py` (MOD) | config | config | self (relax validator under tape) | self-extension |
| `services/bybit-connector/app/<NEW tape replay loader>` (NEW) | service (in-process replay) | streaming (file-I/O → in-memory) | `services/bybit-connector/app/bybit_rest_client.py` | role-match (mirror interface) |
| `.github/workflows/live-smoke.yml` (NEW) | CI workflow | event-driven (cron) | `.github/workflows/security-scan.yml` (cron) + `ci.yml` (compose-up) | role-match |
| `docker-compose.unified.yml` (MOD) | config | config | self (existing bybit-connector block + EMERGENCY_STOP bind-mount) | self-extension |
| `.env.example` (verify-only) | config | config | self (planner reads directly — see Landmines §1) | n/a |

---

## Pattern Assignments

### `bootstrap.sh` (utility, request-response + file-I/O)

**Analog:** `health_check.sh` (shell-script style + service port table + curl /health probe loop) and `build-all.sh` (CLI flag parse + colored output + summary block).

**Header / `set -e` / SCRIPT_DIR pattern** (`health_check.sh:1-15`):
```bash
#!/bin/bash
# ============================================================================
# Health Check Script for Crypto Trading Bot
# Purpose: Monitor health status of all microservices
# Usage: ./health_check.sh [--json] [--watch]
# ============================================================================

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
```

**Service port table** (`health_check.sh:17-29`):
```bash
declare -A SERVICES=(
    ["api-gateway"]=8000
    ["bybit-connector"]=8001
    ["market-data"]=8002
    ["portfolio"]=8003
    ["technical-analysis"]=8004
    ["trading-engine"]=8005
    ["notification"]=8006
    ["ml-prediction"]=8007
    ["sentiment"]=8008
    ["risk-metrics"]=8009
)
```

**Curl-based health probe with timeout + JSON status parse** (`health_check.sh:39-63`):
```bash
check_service_health() {
    local service=$1
    local port=$2
    local timeout=5

    local response=$(curl -s --max-time $timeout "http://localhost:$port/health" 2>/dev/null)
    local curl_exit=$?

    if [ $curl_exit -ne 0 ]; then
        echo "UNAVAILABLE"
        return 1
    fi

    local status=$(echo "$response" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data.get('status', 'unknown'))" 2>/dev/null || echo "error")

    if [ "$status" = "healthy" ] || [ "$status" = "ok" ]; then
        echo "HEALTHY"
        return 0
    fi
    echo "$status"
    return 1
}
```

**Infrastructure DB/cache probe (RabbitMQ via curl, postgres via pg_isready, redis via redis-cli)** (`health_check.sh:194-209`):
```bash
pg_status=$(docker exec crypto-bot-postgres pg_isready -U postgres 2>/dev/null && echo "READY" || echo "NOT_READY")
ts_status=$(docker exec crypto-bot-timescaledb pg_isready -U postgres 2>/dev/null && echo "READY" || echo "NOT_READY")
redis_status=$(docker exec crypto-bot-redis redis-cli ping 2>/dev/null | grep -q "PONG" && echo "READY" || echo "NOT_READY")
rabbit_status=$(curl -s "http://localhost:15672/api/health/checks/alarms" -u guest:guest 2>/dev/null | grep -q "ok" && echo "READY" || echo "NOT_READY")
```

**CLI flag parsing** (`build-all.sh:36-60`):
```bash
NO_CACHE=""
PARALLEL=false
PUSH=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --no-cache) NO_CACHE="--no-cache"; shift ;;
        --parallel) PARALLEL=true; shift ;;
        --push)     PUSH=true; shift ;;
        *) echo -e "${RED}Unknown option: $1${NC}"; exit 1 ;;
    esac
done
```

**Summary block + non-zero exit on failure** (`build-all.sh:172-193`):
```bash
echo "========================================="
echo "  Build Summary"
echo "========================================="
echo "Total services: ${#SERVICES[@]}"
echo "Failed builds: $result"
echo "Elapsed time: ${elapsed}s"

if [ $result -eq 0 ]; then
    echo -e "${GREEN}All images built successfully!${NC}"
    exit 0
else
    echo -e "${RED}Some builds failed. Check the output above for details.${NC}"
    exit 1
fi
```

**Health-loop timeout pattern (~120s, polling)** (cited from `start-system/SKILL.md:42-43` + `deploy/SKILL.md:30-33`):
```bash
until ! docker ps --format '{{.Status}}' | grep -q '(starting)'; do sleep 5; done
# OR (per-container variant):
until [ "$(docker inspect -f '{{.State.Health.Status}}' crypto-bot-<short> 2>/dev/null)" != "starting" ]; do sleep 2; done
```

**`bootstrap.sh`-specific landmine wiring (per CONTEXT.md D-11, D-12, D-13, CLAUDE.md gotchas):**
- Touch `EMERGENCY_STOP` at repo root before `docker compose up` (D-11). `./EMERGENCY_STOP` is bind-mounted RO into trading-engine and RW into api-gateway (`docker-compose.unified.yml:287` + `:543`).
- Default `DOCKER_BUILDKIT=0` on Linux/WSL2 to dodge known buildkit hangs (CLAUDE.md § Environment).
- Use `docker-compose.unified.yml` (not `docker-compose.yml` — incomplete; CLAUDE.md § Gotchas).
- On failure: print last 50 log lines per failed service, leave stack up, exit non-zero (D-13).

---

### `scripts/tape/capture_bybit.py` (utility, request-response → file-I/O)

**Analog:** `scripts/collect_bybit_direct_180days.py` — direct REST hit on Bybit mainnet, paginated kline collection, rate-limit pacing, repo-relative output dir. Same shape, different output format (CSV+DB → JSONL fixture).

**Header / repo-root resolution / logging setup** (`scripts/collect_bybit_direct_180days.py:1-38`):
```python
#!/usr/bin/env python3
"""
Direct Bybit Historical Data Collection
Purpose: Collect 180 days of historical kline data directly from Bybit API

This script bypasses the market-data-service and fetches data directly
from Bybit's public API to get the full 180 days of historical data.
"""

import os
from pathlib import Path as _Path
_REPO_ROOT = _Path(__file__).resolve().parent.parent
import sys
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
```

**Symbol list + endpoint + pacing constants** (`scripts/collect_bybit_direct_180days.py:41-71`):
```python
SYMBOLS = ['SOLUSDT', 'BNBUSDT', 'ADAUSDT', ...]
DAYS_TO_COLLECT = 180
INTERVAL = '60'  # 60 minutes
BYBIT_API_ENDPOINT = 'https://api.bybit.com'
MAX_LIMIT = 200
RATE_LIMIT_DELAY = 0.5
OUTPUT_DIR = str(_REPO_ROOT / 'data/historical')
```

**REST call shape (V5 kline)** (`scripts/collect_bybit_direct_180days.py:89-118`):
```python
def get_bybit_klines(symbol, interval, start_time, end_time, limit=200) -> List[Dict]:
    url = f"{BYBIT_API_ENDPOINT}/v5/market/kline"
    params = {
        'category': 'linear',
        'symbol': symbol,
        'interval': interval,
        'start': start_time,
        'end': end_time,
        'limit': limit,
    }
```

**Capture-script-specific deltas (per D-01, D-03, D-05, D-07):**
- Symbol scope: `BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, ADAUSDT` only (5 validated symbols, CLAUDE.md § Project rules + D-03).
- Interval = `5` (5-minute klines per D-03), window = 7 days (~2,016 candles per symbol).
- Two feeds per D-02: kline (`/v5/market/kline`) + ticker (`/v5/market/tickers`). Orderbook + funding deferred.
- Output = JSONL per `(feed, symbol)`: `tests/fixtures/tape/klines/SOLUSDT.jsonl`, `tests/fixtures/tape/ticker/SOLUSDT.jsonl` (D-04, D-01).
- First line of each JSONL is the schema header per D-07: `{"tape_version": 1, "captured_at": "...", "source": "bybit-mainnet", "symbol": "SOLUSDT", "feed": "klines"}`.
- Total tape size budget: <50 MB so it stays in git (D-04, no LFS in v1).

---

### `services/bybit-connector/app/main.py` (MOD — controller/lifespan, request-response)

**Analog:** itself. Existing lifespan + DI seam are the surface to extend; downstream HTTP contract on port 8001 must remain identical (D-15).

**Imports + lifespan signature (extend, don't replace)** (`services/bybit-connector/app/main.py:288-313`):
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle (startup/shutdown)"""
    # Startup
    settings = get_settings()

    logger.info(
        f"Starting Bybit Connector Service",
        extra={
            "testnet": settings.bybit_testnet,
            "service_version": "1.0.0",
            "environment": "development" if settings.debug else "production"
        }
    )
    # Loud, grep-able startup line so log audits can confirm the actual price source.
    logger.warning(
        "BYBIT_PRICE_SOURCE: testnet=%s rest_url=%s ws_url=%s",
        settings.bybit_testnet, settings.rest_api_url, settings.websocket_url,
    )
```

**Live-mode REST client construction + clock sync (the path tape mode must skip)** (`services/bybit-connector/app/main.py:315-336`):
```python
    try:
        # Initialize REST client and store in app state.
        app.state.rest_client = create_rest_client(
            settings,
            on_breaker_state_change=_update_breaker_gauge,
        )
        _update_breaker_gauge(CircuitState.CLOSED)
        logger.info("Bybit REST client initialized successfully")

        # Sync local clock against Bybit server time
        try:
            await app.state.rest_client.authenticator.sync_clock(
                app.state.rest_client.client, app.state.rest_client.base_url
            )
        except Exception as exc:
            logger.warning(f"Clock sync against Bybit server skipped: {exc}")

        yield
```

**DI seam — single injection point for both modes** (`services/bybit-connector/app/main.py:385-393`):
```python
def get_rest_client(request: Request) -> BybitRestClient:
    """Dependency to get REST client from app state"""
    if not hasattr(request.app.state, 'rest_client') or request.app.state.rest_client is None:
        logger.error("Bybit client not initialized in app state")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bybit client not initialized"
        )
    return request.app.state.rest_client
```

**Health + readiness pattern (must keep working in tape mode — see Landmines §3)** (`services/bybit-connector/app/main.py:421-451`):
```python
@app.get("/health", tags=["Health"])
@limiter.limit("60/minute")
async def health_check(request: Request):
    return {"status": "healthy", "service": "bybit-connector"}


@app.get("/ready", tags=["Health"])
@limiter.limit("60/minute")
async def readiness_check(request: Request, client: BybitRestClient = Depends(get_rest_client)):
    """
    Readiness check - verifies service can connect to Bybit
    """
    try:
        # Probe a public endpoint with one of the validated trading symbols
        await client.get_ticker(category="linear", symbol="SOLUSDT")
        logger.info("Readiness check passed - Bybit connection OK")
        return {"status": "ready", "bybit_connection": "ok"}
    except Exception as e:
        logger.error(f"Readiness check failed: {str(e)}", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Bybit connection failed: {str(e)}"
        )
```

**One market-data route to mirror (`get_kline`) — same response shape required in tape mode** (`services/bybit-connector/app/main.py:692-751`):
```python
@app.get("/api/v1/market/kline", tags=["Market Data"])
@limiter.limit("200/minute")
async def get_kline(
    request: Request,
    category: str = "linear",
    symbol: str = "BTCUSDT",
    interval: str = "60",
    limit: int = 200,
    start: Optional[int] = None,
    end: Optional[int] = None,
    client: BybitRestClient = Depends(get_rest_client)
):
    try:
        result = await client.get_kline(
            category=category, symbol=symbol, interval=interval,
            limit=limit, start_time=start, end_time=end,
        )
        return {"success": True, "data": result}
    except BybitConnectorException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
```

**Patch shape per D-15:** add a `MARKET_DATA_SOURCE`-aware branch *inside lifespan* that selects `BybitRestClient` (live) vs `TapeReplayClient` (tape) and assigns it to `app.state.rest_client`. Routes / DI seam stay byte-identical. Skip `sync_clock()` in tape mode. The `BYBIT_PRICE_SOURCE:` log line at `main.py:310-313` must also gain a `mode=tape|live` field so log audits can grep for the active source.

---

### `services/bybit-connector/app/<NEW tape replay loader>` (service, streaming)

**Analog:** `services/bybit-connector/app/bybit_rest_client.py` — must mirror the public coroutine surface (`get_ticker`, `get_kline`, `get_orderbook`, `get_recent_trades`, `get_funding_rate_history`, `get_instruments_info`, `close`) so callers can't tell the difference.

**Class signature + `close()` to mirror** (`services/bybit-connector/app/bybit_rest_client.py:26-99`):
```python
class BybitRestClient:
    """
    Bybit REST API client with authentication, retry logic, and circuit breaker

    Supports all major API endpoints:
    - Account: balance, positions
    - Trading: place order, cancel order, modify order
    - Market Data: tickers, klines, orderbook
    """
    def __init__(self, api_key, api_secret, testnet=True, base_url=None,
                 timeout=30.0, on_breaker_state_change=None):
        ...
        logger.info(f"Initialized Bybit REST client (testnet={testnet}, base_url={self.base_url})")

    async def close(self):
        await self.client.aclose()
        logger.info("Closed Bybit REST client")
```

**Coroutine signatures the tape replay client must implement byte-identically** (`services/bybit-connector/app/bybit_rest_client.py:509-563`):
```python
    async def get_ticker(self, category: str = "linear", symbol: Optional[str] = None) -> Dict[str, Any]:
        """Get latest ticker data"""
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        result = await self._request("GET", "/v5/market/tickers", params=params, auth_required=False)
        return result

    async def get_kline(
        self,
        category: str,
        symbol: str,
        interval: str,
        limit: int = 200,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None
    ) -> List[List[str]]:
        """
        Get kline/candlestick data
        Returns: List of kline data [timestamp, open, high, low, close, volume, turnover]
        """
        ...
        result = await self._request("GET", "/v5/market/kline", params=params, auth_required=False)
        return result.get("list", [])
```

**Downstream consumer expects this exact return shape** (`services/market-data-service/app/fetcher.py:159-188`):
```python
            response = await self.client.get("/api/v1/market/kline", params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("success"):
                raw_data = data.get("data", [])
                if isinstance(raw_data, dict):
                    raw_klines = raw_data.get("list", [])
                else:
                    raw_klines = raw_data
                klines = []
                for k in raw_klines:
                    klines.append({
                        "timestamp": int(k[0]),
                        "open": k[1], "high": k[2], "low": k[3], "close": k[4],
                        "volume": k[5],
                        "turnover": k[6] if len(k) > 6 else "0"
                    })
```
**Implication:** the tape client's `get_kline` must return `List[List[str]]` of `[timestamp, open, high, low, close, volume, turnover]` strings — not the structured dict that `fetcher.py` produces *after* parsing. Mirror the upstream Bybit V5 wire format, not the downstream shape.

**Out-of-scope methods (D-02 — orderbook + funding deferred to Phase 5):** the tape client should still expose `get_orderbook`, `get_funding_rate_history`, `get_instruments_info` as stubs that return empty lists (not raise) so existing routes in `main.py:784-897` don't 500. Default-off consumers (`PREFER_MAKER_ORDERS`, `ENABLE_FUNDING_GATE`) won't read them; Phase 5 will populate them.

---

### `services/bybit-connector/app/config.py` (MOD — config)

**Analog:** itself. Single change: relax credential validator under `MARKET_DATA_SOURCE=tape`.

**Current validator that *must* become conditional** (`services/bybit-connector/app/config.py:121-127`):
```python
    @field_validator("bybit_api_key", "bybit_api_secret")
    @classmethod
    def validate_api_credentials(cls, v, info):
        """Validate API credentials are not empty"""
        if not v or v == f"your_{info.field_name}_here":
            raise ValueError(f"{info.field_name} must be set with valid credentials")
        return v
```

**Existing testnet-vs-mainnet selector pattern (the model to follow)** (`services/bybit-connector/app/config.py:140-149`):
```python
    @property
    def rest_api_url(self) -> str:
        """Get appropriate REST API URL based on testnet setting"""
        return self.bybit_rest_url_testnet if self.bybit_testnet else self.bybit_rest_url_mainnet

    @property
    def websocket_url(self) -> str:
        """Get appropriate WebSocket URL based on testnet setting"""
        return self.bybit_ws_url_testnet if self.bybit_testnet else self.bybit_ws_url_mainnet
```

**Required additions per D-14, D-17:**
- New field: `market_data_source: Literal["tape", "live"] = Field(default="tape", description="...")`. Default `tape` so a fresh `.env` with no creds boots successfully.
- New field: `tape_fixtures_path: Path = Field(default=Path("/app/tests/fixtures/tape"), description="In-container path to tape fixtures (bind-mounted RO)")` — matches D-15 bind-mount target.
- Convert `validate_api_credentials` from a `@field_validator` (per-field) into a `@model_validator(mode="after")` that *only* enforces non-empty creds when `market_data_source == "live"`. Pydantic field_validators don't see other fields; model_validator is required.
- Provide a property `is_tape_mode -> bool` (mirrors the `is_testnet` property style at line 169-171).

---

### `docker-compose.unified.yml` (MOD — config)

**Analog:** itself. Existing `bybit-connector` block is the patch site.

**Existing block — env vars to extend + volume to add** (`docker-compose.unified.yml:342-368`):
```yaml
  bybit-connector:
    build:
      context: ./services/bybit-connector
      dockerfile: Dockerfile
    container_name: crypto-bot-bybit
    hostname: bybit-connector
    ports:
      - "${BYBIT_PORT:-8001}:8001"
    environment:
      - SERVICE_NAME=bybit-connector
      - SERVICE_PORT=8001
      - DEBUG=${DEBUG:-false}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - BYBIT_API_KEY=${BYBIT_API_KEY:-}
      - BYBIT_API_SECRET=${BYBIT_API_SECRET:-}
      - BYBIT_TESTNET=${BYBIT_TESTNET:-false}
    volumes:
      - ./services/bybit-connector/logs:/app/logs
    networks:
      - crypto-bot-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped
```

**Existing read-only bind-mount pattern to copy (EMERGENCY_STOP)** (`docker-compose.unified.yml:282-287`):
```yaml
      - EMERGENCY_STOP_FILE=${EMERGENCY_STOP_FILE:-/app/EMERGENCY_STOP}
    volumes:
      - ./services/api-gateway/logs:/app/logs
      # RW for the gateway: it creates/overwrites the EMERGENCY_STOP file.
      # trading-engine mounts the same host file read-only.
      - ./EMERGENCY_STOP:/app/EMERGENCY_STOP
```

**Patch shape per CONTEXT.md § Integration Points + D-15:**
- Add `MARKET_DATA_SOURCE=${MARKET_DATA_SOURCE:-tape}` to the `environment:` block (default tape so fresh bootstrap works without keys; D-14).
- Add `TAPE_FIXTURES_PATH=/app/tests/fixtures/tape` (matches the bind-mount target).
- Add a read-only bind-mount under `volumes:`:
  ```yaml
      - ./tests/fixtures/tape:/app/tests/fixtures/tape:ro
  ```
- Change `BYBIT_API_KEY`/`BYBIT_API_SECRET` defaults to empty (already `${VAR:-}`) — config validator change in `config.py` makes empty creds acceptable in tape mode (D-17).

---

### `.github/workflows/live-smoke.yml` (NEW — CI workflow, event-driven cron)

**Analogs:**
- Cron schedule + workflow_dispatch shape: `.github/workflows/security-scan.yml` (lines 1-19).
- `docker compose up` + health-loop + log capture: `.github/workflows/ci.yml` Job 4 (`integration-tests`, lines 332-388).

**Cron + manual trigger header** (`.github/workflows/security-scan.yml:1-22`):
```yaml
# Security Scanning Pipeline
# Triggers on: Schedule (daily), Manual, Push to main/develop
name: Security Scanning

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]
  workflow_dispatch:

env:
  PYTHON_VERSION: '3.12'
```

**Compose-up + health-loop + log dump + cleanup pattern** (`.github/workflows/ci.yml:358-388`):
```yaml
      - name: Start services with Docker Compose
        run: |
          docker compose -f infrastructure/docker-compose.test.yml up -d
          sleep 30  # Wait for services to be ready

      - name: Wait for services health checks
        run: |
          timeout 120 bash -c 'until docker compose -f infrastructure/docker-compose.test.yml ps | grep -q "healthy"; do sleep 5; done' || true

      - name: Run integration tests
        run: |
          docker compose -f infrastructure/docker-compose.test.yml exec -T api-gateway pytest tests/integration/ -v

      - name: Collect service logs
        if: always()
        run: |
          docker compose -f infrastructure/docker-compose.test.yml logs > integration-test-logs.txt

      - name: Upload integration test logs
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: integration-test-logs
          path: integration-test-logs.txt
          retention-days: 7

      - name: Cleanup
        if: always()
        run: |
          docker compose -f infrastructure/docker-compose.test.yml down -v
```

**`live-smoke.yml`-specific shape per D-16:**
- Schedule: nightly only (`cron: '0 3 * * *'` or similar). NO push/PR triggers — must not block deterministic CI lane.
- `workflow_dispatch:` enabled for manual re-run.
- Runs `bash bootstrap.sh` with `MARKET_DATA_SOURCE=live` exported, plus mainnet `BYBIT_API_KEY`/`BYBIT_API_SECRET` from `secrets.*` (read-only keys; no trading permissions).
- After bootstrap idle, runs a minimal probe (e.g. `curl /api/v1/market/kline?symbol=SOLUSDT` against bybit-connector and asserts non-empty `data.list`).
- `continue-on-error: true` on the probe step — failures notify (open Issue / Slack via existing patterns) but **do not** mark the workflow as failed for the deterministic lane (D-16: "allowed to be flaky").
- Reuse the `actions/upload-artifact@v4` log-dump + `down -v` cleanup pattern verbatim from ci.yml.

---

## Shared Patterns

### Validated symbol set
**Source:** `crypto-trading-bot/CLAUDE.md` § "Project rules → Validated symbols" + `services/bybit-connector/app/main.py:443` (readiness probe uses `SOLUSDT`).
**Apply to:** `scripts/tape/capture_bybit.py` symbol list, JSONL fixture filenames, capture-script README.
```
BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, ADAUSDT
```
Per D-03, **only** these 5 symbols. Do NOT extend to XRP/DOGE in v1 tape (Phase 5 may add when validation layer permits — see Landmines §4).

### Loud, grep-able startup log line (price-source attestation)
**Source:** `services/bybit-connector/app/main.py:310-313`.
```python
logger.warning(
    "BYBIT_PRICE_SOURCE: testnet=%s rest_url=%s ws_url=%s",
    settings.bybit_testnet, settings.rest_api_url, settings.websocket_url,
)
```
**Apply to:** the new tape-mode lifespan branch must add an equivalent line containing `mode=tape source_dir=/app/tests/fixtures/tape tape_version=1` so the verify-stack skill (`/verify-stack` check #1: "Live prices, not testnet") can grep the active mode without ambiguity.

### Two-flag trading-mode safety (do not regress)
**Source:** `crypto-trading-bot/CLAUDE.md` § "Project rules → Trading-mode flags" + `docker-compose.unified.yml:544, :569, :575`.
- `BYBIT_TESTNET` selects price source (testnet vs mainnet).
- `PAPER_TRADING_MODE` / `TRADING_MODE` selects whether orders simulated.
- `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY` required to boot in LIVE mode.
**Apply to:** `bootstrap.sh` `.env` template generation must set:
- `BYBIT_TESTNET=false` (mainnet prices via tape replay still represent mainnet captures)
- `PAPER_TRADING_MODE=true`, `TRADING_MODE=PAPER`
- `AUTO_TRADING_ENABLED=true` (operator override per CLAUDE.md; auto-trader still gated by EMERGENCY_STOP file, D-11)
- `ENABLE_ML_PREDICTIONS=false` (V0 finding — chance-level on log-returns)
- `ENABLE_SENTIMENT_ANALYSIS=false`
- `MARKET_DATA_SOURCE=tape` (D-14 default)

### Idempotent / safe-rerun ethos
**Source:** `.claude/skills/start-system/SKILL.md:8-9` ("Idempotent — safe to run when partially up") + `deploy/SKILL.md:25` (`up -d --build --no-deps --force-recreate`).
**Apply to:** `bootstrap.sh` must be safe to re-run: `touch EMERGENCY_STOP` is already idempotent; `cp -n .env.example .env` (no-clobber) preserves operator-edited `.env`; `docker compose up -d` is idempotent on already-running services.

### "Trust no docs" verification floor
**Source:** `.claude/skills/verify-stack/SKILL.md` (whole file — 4 PASS/FAIL checks) + CLAUDE.md § "Verification standards".
**Apply to:** Phase 1 success criteria — bootstrap.sh's exit-zero is *not* sufficient evidence of a healthy idle. The verify-stack checklist (live-source-URL grep, no testnet drift, EMERGENCY_STOP state, container restart-after-config) is the floor for any "Phase 1 done" claim.

---

## Landmines (planner must surface in plans)

### §1 `.env.example` not retrievable in this pass
The pattern-mapper's read of `/mnt/d/Bimo_max/crypto-trading-bot/.env.example` was rejected by the sandbox's directory permissions. Planner **must** read it directly during planning and verify:
- It already documents `BYBIT_API_KEY`, `BYBIT_API_SECRET`, `BYBIT_TESTNET`, `PAPER_TRADING_MODE`, `TRADING_MODE`, `AUTO_TRADING_ENABLED`, `ENABLE_ML_PREDICTIONS`, `ENABLE_SENTIMENT_ANALYSIS`.
- It needs new entries for `MARKET_DATA_SOURCE=tape` and `LIVE_TRADING_ACK` (per CLAUDE.md § Trading-mode flags).
- Per CONTEXT.md, "verify template baseline" — only edit if a key is missing; do not regenerate.

### §2 Credential validator currently raises on empty key/secret (D-17 conflict)
`services/bybit-connector/app/config.py:121-127` unconditionally rejects empty `bybit_api_key`/`bybit_api_secret`. D-17 says tape mode bypasses auth. Plan **must** convert this to a model-level validator that gates on `market_data_source == "live"` — otherwise a fresh-clone bootstrap with empty `.env` (the explicit success criterion) will crash the bybit-connector at startup with `ValueError: bybit_api_key must be set with valid credentials`.

### §3 `/ready` endpoint hits `client.get_ticker(SOLUSDT)` (live-only assumption)
`services/bybit-connector/app/main.py:432-451` does an actual ticker call against `app.state.rest_client`. In tape mode this still works **only if** `TapeReplayClient.get_ticker(category, symbol)` returns the same shape as `BybitRestClient.get_ticker` (`Dict[str, Any]` with `list` key). Plan must include a unit test asserting the tape replay client's `get_ticker("linear", "SOLUSDT")` returns a non-empty result so `/ready` reports 200 in tape mode. If it doesn't, `bootstrap.sh`'s health probe will time out and D-09 ("all 15 services /health=200") fails.

### §4 Symbol-set drift between connector tape and downstream scheduler
`services/market-data-service/app/scheduler.py:25-33` hardcodes 7 trading pairs (`BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT, ADAUSDT, DOGEUSDT`). v1 tape only covers 5 (D-03; XRP and DOGE excluded). The connector's `TapeReplayClient.get_ticker("XRPUSDT")` / `get_kline("XRPUSDT", ...)` will be called by scheduler.py.
**Required behavior:** return an empty list (not 500, not raise). Plan must add a graceful-fallback test — `get_kline` for an unknown symbol returns `[]` and logs a WARN. **Do not edit `scheduler.py`** in this phase (CONTEXT.md § "Out of scope" implies stack lock; only changes are in connector + bootstrap + fixtures + workflow).

### §5 WSL2 BuildKit hang
`crypto-trading-bot/CLAUDE.md` § "Environment" — BuildKit hangs are common on WSL2. `bootstrap.sh` should default to `export DOCKER_BUILDKIT=0` on Linux/WSL2 unless the operator overrides via env var. CONTEXT.md § "Specifics" calls this out. Confirm the script does this **before** the first `docker compose up`, otherwise on fresh-clone WSL2 boxes the initial build of sentiment-analysis hangs indefinitely.

### §6 WSL bind-mount race
CLAUDE.md § "Environment" — `docker inspect` can show a `bind` mount succeeded while the path inside the container is empty + root-owned. Symptom for tape mode: connector starts in tape mode, can't enumerate fixture files, returns empty `data.list` for everything → downstream scheduler logs "no kline data returned" silently → `/ready` still 200. Plan must include a sanity check inside the connector's tape lifespan path: enumerate fixtures, log fixture count per symbol, refuse to come `ready` if any expected JSONL file is missing or unreadable.

### §7 Two compose files
`docker-compose.unified.yml` is canonical (15+1 services incl DBs). `docker-compose.yml` is incomplete (missing postgres/timescaledb/redis/rabbitmq). `bootstrap.sh` and `live-smoke.yml` must reference `-f docker-compose.unified.yml` explicitly. CLAUDE.md § "Gotchas" + start-system/SKILL.md:30.

### §8 EMERGENCY_STOP file already present at repo root
A file named `EMERGENCY_STOP` is already in the repo root (visible in repo listing). D-11 says bootstrap.sh "touches" it by default — `touch` on an existing file is idempotent (just bumps mtime), so this is fine. But the auto-trader-arming flow (CLAUDE.md § "Project rules → Auto-trader") starts up *halted* until the operator removes it. This is **intended behavior** for Phase 1: bootstrap should leave EMERGENCY_STOP in place so the trading loop holds at STEP-0 even though `AUTO_TRADING_ENABLED=true`.

### §9 Sentiment-analysis pip flakiness
CLAUDE.md § "Gotchas" — sentiment-analysis-service image historically fails pip build (PyPI read timeouts). Bootstrap's first `docker compose up -d` may stall or fail on this one image. Plan should:
- Document the workaround inline in `bootstrap.sh` comments (`DOCKER_BUILDKIT=0 docker compose ... build sentiment-analysis` retry, or `--no-deps` skip).
- Cross-reference a future RUNBOOK.md (Phase 2 INFRA-05) for the full triage flow.
- Per D-13, on failure leave the stack up and exit non-zero — do not auto-retry.

---

## No Analog Found

Files with no close analog in the codebase. Planner should reference D-01 / D-07 schema + RESEARCH.md (if it exists) for the contract.

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `tests/fixtures/tape/klines/{BTC,ETH,SOL,BNB,ADA}USDT.jsonl` (× 5) | test fixture | streaming | Existing fixture machinery is `tests/e2e/fixtures/mock_data.py` (Python functions returning generated dicts) and `shared/tests/fixtures/database.py` (SQL setup helpers). Neither is a static data file. The JSONL-with-tape-version-header schema (D-07) is new to the repo. Format: line 1 = `{"tape_version": 1, "captured_at": "...", "source": "bybit-mainnet", "symbol": "BTCUSDT", "feed": "klines"}`; lines 2..N = raw Bybit V5 kline list-of-strings `[ts, o, h, l, c, v, turnover]`. |
| `tests/fixtures/tape/ticker/{BTC,ETH,SOL,BNB,ADA}USDT.jsonl` (× 5) | test fixture | streaming | Same — no static-JSONL-fixture analog in repo. Header line 1 same shape with `"feed": "ticker"`; lines 2..N = ticker dict per Bybit V5 `/v5/market/tickers` shape. |
| `services/bybit-connector/app/<NEW tape replay loader module>` | service | streaming/file-I/O | While `bybit_rest_client.py` provides the *coroutine surface* to mirror, the in-process JSONL streaming + timestamp pinning logic (D-08: replay timestamps as-is, no clock mock) is not implemented anywhere in the repo. Closest reference is `scripts/collect_bybit_direct_180days.py` for the wire-format mapping, plus `fetcher.py:159-188` for the consumer's expected shape. Planner should treat this as a fresh module — under `services/bybit-connector/app/tape_replay_client.py` or similar — implementing the same `BybitRestClient` public method signatures over a JSONL reader instead of `httpx.AsyncClient`. |

---

## Metadata

**Analog search scope:**
- Repo root shell scripts (`health_check.sh`, `build-all.sh`, `check_services.sh`, `monitor_paper_trading.sh`)
- `services/bybit-connector/app/` (full module)
- `services/market-data-service/app/` (downstream consumer contract — fetcher, scheduler)
- `tests/e2e/fixtures/`, `shared/tests/fixtures/` (existing fixture conventions)
- `.github/workflows/` (CI pattern library — ci.yml, security-scan.yml)
- `scripts/` (one-shot Python collectors — `collect_bybit_direct_180days.py`)
- `.claude/skills/{start-system,verify-stack,deploy}/SKILL.md` (operational analogs)
- `docker-compose.unified.yml` (existing bybit-connector block, EMERGENCY_STOP bind-mount pattern)
- `crypto-trading-bot/CLAUDE.md` (project rules, gotchas, environment)

**Files scanned:** ~15 (read in full or targeted ranges per role spec).

**Pattern extraction date:** 2026-05-06.

---

## PATTERN MAPPING COMPLETE

**Phase:** 1 - Bootstrap & Recorded Tape
**Files classified:** 14 (10 NEW JSONL × symbol-feed pair + 1 NEW capture script + 1 NEW shell + 1 NEW workflow + 1 NEW connector module + 2 MOD)
**Analogs found:** 11 / 14

### Coverage
- Files with exact analog: 4 (`bootstrap.sh`, `capture_bybit.py`, `live-smoke.yml`, both connector MODs as self-extension)
- Files with role-match analog: 1 (NEW tape replay loader → mirror `BybitRestClient`)
- Files with no analog: 3 categories (10 JSONL fixtures × 5 symbols × 2 feeds = 10 files + the new tape replay module's JSONL streaming logic)

### Key Patterns Identified
- All operator scripts in repo follow the bash header / `set -e` / `SCRIPT_DIR` / `declare -A SERVICES` / colored-output / summary-block style — `bootstrap.sh` should match exactly.
- `BybitRestClient` exposes a stable async coroutine surface (`get_ticker`, `get_kline`, `get_orderbook`, etc.) — the tape-mode loader must mirror that surface byte-identically so the DI seam at `main.py:385-393` and downstream consumer at `fetcher.py:159-188` need zero changes.
- CI workflows split into "block PR" (ci.yml — push + PR triggers, fail-fast) vs "advisory" (security-scan.yml — cron + workflow_dispatch, `continue-on-error: true` shape) — `live-smoke.yml` belongs to the second class per D-16.
- Trading-mode safety relies on multiple orthogonal flags + an EMERGENCY_STOP file at repo root — `bootstrap.sh` must align all of them and not leak ambiguity into the .env it generates.

### Landmines Surfaced
9 landmines listed (config validator conflict, `/ready` mode-blindness, symbol-set drift, BuildKit/bind-mount races, two-compose-files, EMERGENCY_STOP semantics, sentiment-analysis pip flake, .env.example sandboxed read).

### File Created
`/mnt/d/Bimo_max/crypto-trading-bot/.planning/phases/01-bootstrap-recorded-tape/01-PATTERNS.md`

### Ready for Planning
Pattern mapping complete. Planner can now reference analog patterns in PLAN.md files.
