---
type: agent-report
service: bybit-connector
generated: 2026-05-05
source_path: services/bybit-connector/
---

# bybit-connector — raw audit

Service path: `services/bybit-connector/`
Port: 8001
Stated purpose (CLAUDE.md): "Bybit REST + WebSocket wrapper"

## Endpoints

All defined in `services/bybit-connector/app/main.py`. Decorators counted; `/health`, `/ready`, `/metrics` skipped per task. **All paths use the legacy `/api/v1/...` prefix** (contrast with gateway, which dropped the `v1` prefix per `[[../decisions/ADR-007-no-v1-api-prefix]]`).

| Method | Path | Tag | Rate limit | File:line |
|---|---|---|---|---|
| GET | `/api/v1/account/balance` | Account | 20/min | `app/main.py:424` |
| GET | `/api/v1/account/positions` | Account | 20/min | `app/main.py:449` |
| POST | `/api/v1/order/place` | Trading | 10/min | `app/main.py:479` |
| POST | `/api/v1/order/cancel` | Trading | 10/min | `app/main.py:525` |
| GET | `/api/v1/order/open` | Trading | 20/min | `app/main.py:564` |
| GET | `/api/v1/order/history` | Trading | 20/min | `app/main.py:590` |
| GET | `/api/v1/market/ticker` | Market Data | 200/min | `app/main.py:627` |
| GET | `/api/v1/market/kline` | Market Data | 200/min | `app/main.py:652` |
| GET | `/api/v1/market/orderbook` | Market Data | 200/min | `app/main.py:714` |
| GET | `/api/v1/market/funding-rate/history` | Market Data | 200/min | `app/main.py:740` |
| GET | `/api/v1/market/instruments-info` | Market Data | 60/min | `app/main.py:796` |
| GET | `/api/v1/status/circuit-breaker` | Monitoring | 20/min | `app/main.py:835` |
| POST | `/api/v1/status/circuit-breaker/reset` | Monitoring | 10/min | `app/main.py:860` |

**Total non-health routes: 13.**

## Bybit SDK / library

- `requirements.txt` pins `pybit==5.6.2` (official Bybit Python SDK).
- **Surprise: `pybit` is NOT imported anywhere in `app/`** (`grep -rn "pybit" services/bybit-connector/app/` returns no matches). The service rolls its own REST + signing.
- REST path: `httpx==0.27.0` `AsyncClient` configured in `app/bybit_rest_client.py:72-81` with split timeouts (connect=5s, read=30s, write=10s, pool=10s) hitting `https://api.bybit.com` (mainnet) or `https://api-testnet.bybit.com` (testnet).
- Auth: `app/auth.py` (`BybitAuthenticator`) implements HMAC-SHA256 V5 signature scheme manually (`generate_signature`, `get_headers`).
- Retries: `tenacity==8.2.3` `@retry(stop_after_attempt(3), wait_exponential(1..10), retry_if_exception_type(RateLimitException))` on `_request` (`app/bybit_rest_client.py:103-107`). Only retries on `RateLimitException` — other failures bubble up after first attempt.
- **WebSocket: not implemented in this service.** `requirements.txt` pulls `websockets==12.0` and `config.py` defines `bybit_ws_url_*` + `ws_ping_interval`/`ws_ping_timeout`/`ws_reconnect_delay`/`ws_max_reconnect_attempts` settings, but no WS client class, no `/ws/*` endpoint, no `websockets.connect(...)` in `app/`. Stub-level scaffolding only. Title in `main.py` advertises "REST API service for interfacing with Bybit exchange" — does not claim WS.

## Trading-mode handling

- Branches on `BYBIT_TESTNET` only. Computed in `app/config.py:142-149`:
  - `rest_api_url` → testnet URL if `bybit_testnet=True`, else mainnet.
  - `websocket_url` → same, but unused by this service (see above).
- **Default `bybit_testnet=False`** (`app/config.py:30`) — production prices unless explicitly overridden. Compose passes `BYBIT_TESTNET=${BYBIT_TESTNET:-false}` (`docker-compose.unified.yml:361`). Aligns with `[[../decisions/ADR-006-mainnet-prices-paper-orders]]`.
- Lifespan logs a loud, grep-able `BYBIT_PRICE_SOURCE: testnet=<bool> rest_url=<url> ws_url=<url>` warning at startup (`app/main.py:294-297`) for log audits — matches the project rule about verifying actual price source.
- `PAPER_TRADING_MODE`, `TRADING_MODE`, `LIVE_TRADING_ACK`: **no references in `services/bybit-connector/`**. This service is mode-agnostic — it only knows REST URL. Whether orders are simulated or sent live is decided upstream in `[[trading-engine]]`. If trading-engine ever calls `POST /api/v1/order/place`, this service signs and forwards to real Bybit unconditionally.

## Circuit breaker

Real, not just claimed.

- Implementation: `app/circuit_breaker.py` (252 lines). Three-state FSM (`CLOSED` → `OPEN` → `HALF_OPEN`) with `failure_threshold=5`, `recovery_timeout=60s`, `expected_exception=Exception`. `call_async` / `call` execute the wrapped function and flip state on threshold.
- Wired into REST client at `app/bybit_rest_client.py:84-88`; every `_request` goes through `circuit_breaker.call_async(self._make_request, ...)` (`bybit_rest_client.py:142-149`).
- Exposed via `GET /api/v1/status/circuit-breaker` (`main.py:835`) and resettable via `POST /api/v1/status/circuit-breaker/reset` (`main.py:860`). Prometheus gauge `circuit_breaker_state` (0/1/2 = closed/open/half_open) updates on status query.
- Settings exist for tuning (`circuit_breaker_failure_threshold`, `circuit_breaker_recovery_timeout`, `circuit_breaker_expected_exception` in `config.py:68-70`) **but the values are hard-coded at construction time** in `bybit_rest_client.py:84-88` — Settings are read but not threaded through. Minor gotcha: changing the env var has no effect.

## Internal deps

This service is a leaf — calls **only external Bybit REST API**, no other internal services.

Env vars (compose):
- `SERVICE_NAME=bybit-connector`, `SERVICE_PORT=8001`
- `BYBIT_API_KEY`, `BYBIT_API_SECRET` — testnet keys per project rule
- `BYBIT_TESTNET=${BYBIT_TESTNET:-false}` — selects mainnet/testnet REST URL
- `DEBUG`, `LOG_LEVEL`

Compose declares it as a healthcheck dependency for downstream services (market-data, trading-engine, etc.) but `bybit-connector` itself has no `depends_on` block — first to start.

`config.py` also declares Redis + RabbitMQ settings but neither is wired into runtime code (no aioredis or pika client instantiated). Dead config.

`config_vault.py` (485 lines) is an alternate Settings class pulling secrets from HashiCorp Vault. **Not imported by `main.py`** — `from app.config import get_settings, Settings` is the live path. Vault config is parked code.

## Used by

- **`api-gateway`**: proxies via `bybit_connector_url` (`services/api-gateway/app/config.py:24` default `http://localhost:8001`; compose overrides to `http://bybit-connector:8001`). Used in `service_proxy.py` and exposed in gateway's `/api/health/services` aggregator (`main.py:508`).
- **`market-data-service`**: heaviest internal consumer. `services/market-data-service/app/fetcher.py:69` uses `bybit_connector_url` as the kline data source (default in `config.py:58` is `http://localhost:8002` — likely a copy-paste bug from market-data's own port; compose overrides to `8001` correctly via `BYBIT_CONNECTOR_URL=http://bybit-connector:8001` at `docker-compose.unified.yml:411`). Wraps every call in `bybit_connector_retry` (`market-data-service/app/circuit_breaker.py:18`) and counts in `bybit_connector_calls_total` Prometheus counter.
- **`trading-engine`**, **`portfolio-manager`**, **`technical-analysis`**, **`risk-metrics-service`**: receive `BYBIT_CONNECTOR_URL=http://bybit-connector:8001` env (`docker-compose.unified.yml:275, 460, 506, 566`) and `depends_on: bybit-connector: { condition: service_healthy }` (lines 419, 472, 513, 598). Whether they actively call it is per-service.

## RabbitMQ

**Claim is wrong.** Project topics doc (`wiki/concepts/Message-Queue-Topics.md:19-20`) says:
- `trade.execute` — trading-engine → bybit-connector
- `trade.result` — bybit-connector → portfolio-manager

**Reality:** zero RabbitMQ consumer or publisher code in `services/bybit-connector/app/`. `grep -rn "aio_pika\|pika\|publish\|consume\|trade.result\|trade.execute" services/bybit-connector/app/` returns only the dead `rabbitmq_*` settings in `config.py` and `config_vault.py`. No queue declarations, no listener task spawned in lifespan, no publisher invoked from the order endpoints. Order execution is purely **synchronous HTTP** — caller posts to `/api/v1/order/place`, gets the Bybit response back in the HTTP body. `trade.result` events would have to be published by the caller (`trading-engine`), not this service.

## DB tables

None. Stateless wrapper. No SQLAlchemy / asyncpg / TimescaleDB code. Confirmed.

## Key files

1. `services/bybit-connector/app/main.py` — FastAPI app, all 13 routes, middleware (903 lines)
2. `services/bybit-connector/app/bybit_rest_client.py` — REST client wrapping httpx + circuit breaker (640 lines)
3. `services/bybit-connector/app/auth.py` — HMAC-SHA256 V5 signing (331 lines)
4. `services/bybit-connector/app/circuit_breaker.py` — 3-state FSM (252 lines)
5. `services/bybit-connector/app/config.py` — pydantic-settings (224 lines)
6. `services/bybit-connector/app/exceptions.py` — typed exception hierarchy + Bybit error-code mapping (273 lines)
7. `services/bybit-connector/app/models.py` — `PlaceOrderRequest`, `CancelOrderRequest` Pydantic models (149 lines)
8. `services/bybit-connector/app/config_vault.py` — alternate Vault-backed Settings, not wired (485 lines)
9. `services/bybit-connector/requirements.txt` — pybit 5.6.2, httpx 0.27, websockets 12, fastapi 0.109
10. `services/bybit-connector/Dockerfile` — container build

## Gotchas

- **No retry on transient HTTP errors** — `_request`'s `tenacity` retry only triggers on `RateLimitException`. `httpx.HTTPError` is caught and re-raised as `BybitAPIException(ret_code=-1)` with no retry (`bybit_rest_client.py:153-159`).
- **Circuit breaker uses hard-coded thresholds**, not the configurable Settings values (`bybit_rest_client.py:84-88` vs `config.py:68-70`). Tuning via env var is a no-op.
- **`market-data-service` config default for `bybit_connector_url` is `http://localhost:8002`** (`services/market-data-service/app/config.py:58`) — that's market-data's own port, not bybit-connector's. Compose env override saves it; running market-data outside compose without setting `BYBIT_CONNECTOR_URL` will hit itself in a loop.
- **No key rotation logic.** API key/secret read once at startup from env into `BybitAuthenticator`; rotating keys requires service restart.
- **Secret masking is regex-based** in `SecretMaskingFormatter` (`main.py:54-62`) — masks `api_key`, `api_secret`, `password`, `token`, `secret`, `authorization`, `bearer`. Misses `BYBIT_API_KEY` (env-style upper-case key=value pair without quotes), but covers the JSON-log shape.
- **`pybit==5.6.2` in requirements pulled but unused** — adds image weight + supply-chain surface for nothing.
- **WebSocket settings + `websockets` lib pulled in requirements but no WS client implemented** — scaffolding without code.
- **Loud startup banner** (`main.py:294-297`) intentionally emits price source — useful for the project's "verify exchange URL in logs" rule.
- **`/api/v1/...` paths** kept here even though gateway uses bare `/api/...` (`[[../decisions/ADR-007-no-v1-api-prefix]]`). Internal-only surface, so probably fine, but inconsistent.
- **CORS `allow_origins=["*"]` with `allow_credentials=True`** (`main.py:332-338`) — browsers ignore credentials with `*` so harmless, but signals an unfinished CORS policy.

## Contradictions vs CLAUDE.md

1. **CLAUDE.md** (Services table): describes the service as "Bybit REST **+ WebSocket** wrapper". Reality: no WebSocket client implementation in `app/`. WS deps + config exist as scaffolding. **Either docs need a `(REST only — WS planned)` clarifier, or someone needs to implement WS.**
2. **`wiki/concepts/Message-Queue-Topics.md`** lists `trade.execute` as consumed by bybit-connector and `trade.result` as published by it. Reality: no AMQP code in this service. The order endpoints are synchronous HTTP only. Topics doc is aspirational, or those topics are produced by `trading-engine` directly.
3. CLAUDE.md trading-mode rule mentions `BYBIT_TESTNET` selecting price source; bybit-connector respects this correctly via `rest_api_url` computed property. **No contradiction here** — this service is faithful.
4. CLAUDE.md says `PAPER_TRADING_MODE` / `TRADING_MODE` / `LIVE_TRADING_ACK` gate live order placement. bybit-connector has **none of these flags** — it is mode-agnostic and will sign+forward any order it receives. The mode gate is enforced upstream in `trading-engine`. Not a contradiction, but worth documenting: this service is the live-fire conduit; if a caller bypasses trading-engine and calls `POST /api/v1/order/place` directly with mainnet keys, no flag stops it.
