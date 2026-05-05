---
type: module
path: "services/bybit-connector/"
status: active
language: python
port: 8001
purpose: "Bybit REST wrapper (WS planned, not implemented)"
maintainer: ""
last_updated: 2026-05-05
linked_issues: []
depends_on: []
used_by: [api-gateway, market-data-service, trading-engine, portfolio-manager, technical-analysis, risk-metrics-service]
tags: [module, service, exchange, bybit]
created: 2026-05-05
updated: 2026-05-05
---

# bybit-connector

**Port:** `8001`
**Path:** `services/bybit-connector/`
**Purpose:** Thin async wrapper around the Bybit V5 REST API. Signs requests, applies a circuit breaker, exposes Prometheus metrics, and rate-limits its own clients.

## Overview

Leaf service — only outbound calls go to `https://api.bybit.com` (or `api-testnet.bybit.com`). Stateless: no DB, no Redis use, no RabbitMQ wiring. Mode-agnostic: it does not know about paper-trading vs. live; whatever order arrives at `POST /api/v1/order/place` gets signed and forwarded. The mode gate lives upstream in [[trading-engine]] (see [[../concepts/Trading-Mode-Flags|Trading mode flags]]).

Aligns with [[../decisions/ADR-006-mainnet-prices-paper-orders]]: default `BYBIT_TESTNET=false` produces real Bybit prices, while order *simulation* is enforced by `[[trading-engine]]`'s [[../concepts/Auto-Trader|paper-trading layer]] before any HTTP call reaches this service.

## Endpoints

All routes use the legacy `/api/v1/...` prefix — note this contradicts the gateway's [[../decisions/ADR-007-no-v1-api-prefix|no-v1 prefix decision]] for external API surface. Internal-only surface (proxied through gateway), so left in place.

**Account** (20/min)
- `GET /api/v1/account/balance` — wallet balance per `account_type` (default `UNIFIED`) and optional `coin`
- `GET /api/v1/account/positions` — open positions for `category` and optional `symbol`

**Trading**
- `POST /api/v1/order/place` — 10/min — signed order placement
- `POST /api/v1/order/cancel` — 10/min — cancel by `order_id` or `order_link_id`
- `GET /api/v1/order/open` — 20/min — list open orders
- `GET /api/v1/order/history` — 20/min — paginated history with `cursor`

**Market Data** (200/min unless noted)
- `GET /api/v1/market/ticker`
- `GET /api/v1/market/kline` — supports `start` / `end` ms timestamps; max 1000 candles per Bybit
- `GET /api/v1/market/orderbook`
- `GET /api/v1/market/funding-rate/history` — perp-only; T2.3 funding-rate awareness for entries
- `GET /api/v1/market/instruments-info` — 60/min — slow-changing reference data, callers should cache

**Monitoring**
- `GET /api/v1/status/circuit-breaker` — 20/min — current FSM state
- `POST /api/v1/status/circuit-breaker/reset` — 10/min — manual close

Plus `GET /health`, `GET /ready` (probes Bybit by fetching BTCUSDT ticker), and `GET /metrics` (Prometheus).

**Total non-health routes: 13.**

## REST client + signing

Custom-built, **`pybit` is in `requirements.txt` but never imported**.

- `app/bybit_rest_client.py` — `httpx.AsyncClient` with split timeouts (connect 5s, read 30s, write 10s, pool 10s). All requests pass through the [[../concepts/Risk-Model|circuit breaker]] (`circuit_breaker.call_async`) before hitting the wire.
- `app/auth.py` — `BybitAuthenticator` implements Bybit V5 HMAC-SHA256 manually: `HMAC(secret, timestamp + api_key + recv_window + (query_string|body))`.
- `tenacity` retry wraps `_request` but only triggers on `RateLimitException` — generic `httpx.HTTPError` is caught and re-raised as `BybitAPIException(ret_code=-1)` without retry.

## WebSocket — claimed, not implemented

CLAUDE.md and the services table label this service "REST **+ WebSocket** wrapper". In practice:

- `requirements.txt` pulls `websockets==12.0`.
- `config.py` defines `bybit_ws_url_testnet`, `bybit_ws_url_mainnet`, `ws_ping_interval`, `ws_ping_timeout`, `ws_reconnect_delay`, `ws_max_reconnect_attempts`.
- **No WS client class. No `/ws/...` endpoint. No `websockets.connect(...)` anywhere in `app/`.**

Treat the WS half of the description as scaffolding waiting for code.

## Trading-mode handling

Branches on `BYBIT_TESTNET` only.

| `BYBIT_TESTNET` | REST URL | WS URL (unused) |
|---|---|---|
| `false` (default) | `https://api.bybit.com` | `wss://stream.bybit.com/v5/public/linear` |
| `true` | `https://api-testnet.bybit.com` | `wss://stream-testnet.bybit.com/v5/public/linear` |

Computed via `Settings.rest_api_url` / `websocket_url` properties (`config.py:142-149`). On startup the lifespan emits a grep-able banner so log audits can confirm the actual price source:

```
BYBIT_PRICE_SOURCE: testnet=False rest_url=https://api.bybit.com ws_url=wss://stream.bybit.com/v5/public/linear
```

`PAPER_TRADING_MODE`, `TRADING_MODE`, and `LIVE_TRADING_ACK` **do not appear** anywhere in `services/bybit-connector/`. This service has no concept of "simulated order" — it will sign and forward whatever `[[trading-engine]]` sends it. The four-step LIVE gate documented in [[../concepts/Trading-Mode-Flags]] is enforced upstream, not here. Implication: any caller with network access to port 8001 and valid keys can place real orders, regardless of `PAPER_TRADING_MODE`.

## Circuit breaker

Real and load-bearing. `app/circuit_breaker.py` is a 3-state FSM (`CLOSED` → `OPEN` → `HALF_OPEN`) with `failure_threshold=5`, `recovery_timeout=60s`. Defaults are **hard-coded at `BybitRestClient.__init__`** (`bybit_rest_client.py:84-88`) — the `circuit_breaker_failure_threshold` / `circuit_breaker_recovery_timeout` env vars defined in `config.py` are not threaded through. Tuning via env is a no-op; edit the constructor.

Status surfaced through `GET /api/v1/status/circuit-breaker` and the Prometheus `circuit_breaker_state` gauge (0=closed, 1=open, 2=half-open).

## Internal deps

External only — calls `api.bybit.com` over httpx. No internal service is invoked.

Compose env (`docker-compose.unified.yml:346-377`):

- `BYBIT_API_KEY`, `BYBIT_API_SECRET` — required, validated non-empty at boot
- `BYBIT_TESTNET=${BYBIT_TESTNET:-false}` — default mainnet
- `SERVICE_NAME`, `SERVICE_PORT=8001`, `DEBUG`, `LOG_LEVEL`

`config.py` also declares Redis + RabbitMQ settings, but no client is instantiated for either. Dead config (likely a copy-paste from another service's settings template). `app/config_vault.py` is a parallel Vault-backed Settings class, also unused — `main.py` imports `from app.config import get_settings`.

No `depends_on` of its own; first service to start in the compose graph.

## Used by

| Caller | Usage |
|---|---|
| [[api-gateway]] | Aggregates health + reverse-proxies via `bybit_connector_url` (`services/api-gateway/app/services/service_proxy.py`). |
| [[market-data-service]] | Heaviest consumer. `app/fetcher.py:69` pulls klines via `bybit_connector_url`, retries via local `bybit_connector_retry`, counts in `bybit_connector_calls_total`. **Caveat: `market-data-service/app/config.py:58` defaults `bybit_connector_url` to `http://localhost:8002`** — its own port. Compose env override fixes it; running market-data outside compose without setting `BYBIT_CONNECTOR_URL` self-loops. |
| [[trading-engine]] | Compose-declared dep + env, but order-flow path goes through this service for signed REST calls. |
| [[portfolio-manager]] | Compose-declared dep + env. |
| [[technical-analysis]] | Compose-declared dep + env. |
| [[risk-metrics-service]] | Compose-declared dep + env. |

## RabbitMQ — NOT wired

[[../concepts/Message-Queue-Topics]] documents:

- `trade.execute` — [[trading-engine]] → bybit-connector
- `trade.result` — bybit-connector → [[portfolio-manager]]

Neither topic is implemented in `app/`. There is no AMQP consumer, no publisher, no queue declaration, no listener task in lifespan. Order execution is **synchronous HTTP only**: caller `POST`s to `/api/v1/order/place`, the Bybit response is returned in the HTTP body. If `trade.result` events ever appear on the bus, they are produced by `[[trading-engine]]` directly, not this service.

The topics doc is aspirational. Either the queues need to be implemented here, or the doc should be revised.

## DB tables

None. Stateless wrapper.

## Key files

- `app/main.py` — FastAPI app, all 13 routes, JSON logging with secret masking, Prometheus middleware (903 lines)
- `app/bybit_rest_client.py` — `BybitRestClient` over httpx with circuit breaker + tenacity retry (640 lines)
- `app/auth.py` — `BybitAuthenticator` HMAC-SHA256 V5 signer (331 lines)
- `app/circuit_breaker.py` — 3-state FSM, sync + async call wrappers (252 lines)
- `app/config.py` — pydantic-settings, validators, computed `rest_api_url` / `websocket_url` (224 lines)
- `app/exceptions.py` — typed exception hierarchy + Bybit `retCode` → exception map (273 lines)
- `app/models.py` — `PlaceOrderRequest`, `CancelOrderRequest` Pydantic models (149 lines)
- `app/config_vault.py` — alternate Vault-backed Settings, **not wired** (485 lines)
- `requirements.txt` — fastapi 0.109, httpx 0.27, pybit 5.6.2 (unused), websockets 12 (unused), tenacity 8.2.3
- `Dockerfile` — container build

## Gotchas

- **`pybit==5.6.2` declared, never imported** — image weight + supply-chain surface for nothing.
- **WebSocket scaffolding without code** — `websockets` lib + WS settings present, no client.
- **Retry only fires on `RateLimitException`** — `httpx.HTTPError` is wrapped to `BybitAPIException(ret_code=-1)` and not retried.
- **Circuit-breaker thresholds hard-coded**, not pulled from Settings even though Settings has the fields.
- **`market-data-service`'s default `bybit_connector_url` points at `localhost:8002`** (its own port). Compose saves this; bare runs do not.
- **No API-key rotation** — keys read once at startup; rotate = restart.
- **`/api/v1/...` prefix** kept here, against [[../decisions/ADR-007-no-v1-api-prefix]] (gateway uses bare `/api/...`).
- **CORS: `allow_origins=["*"]` with `allow_credentials=True`** — browsers ignore credentials when origin is `*`, harmless but smells unfinished.
- **No mode flag here** — direct calls to port 8001 with mainnet keys = real orders, regardless of `PAPER_TRADING_MODE`. The four-step gate to live trading lives in [[trading-engine]] only. See [[../decisions/ADR-004-paper-trading-default]].

## Contradictions vs CLAUDE.md

1. **"REST + WebSocket wrapper"** — WS is not implemented. Either ship the WS client or relabel as "REST wrapper".
2. **`trade.execute` / `trade.result` pub-sub** ([[../concepts/Message-Queue-Topics]]) — no AMQP code in this service. Order flow is synchronous HTTP.
3. The **`PAPER_TRADING_MODE` / `TRADING_MODE` / `LIVE_TRADING_ACK`** mode gate documented in CLAUDE.md is **not** enforced here. This service is the live-fire conduit, gated only by upstream callers — worth flagging to anyone reasoning about how the four-step LIVE switch protects the system.

## Related

- [[../flows/Order-Lifecycle|Order lifecycle]] — where this service sits in the order-execution path
- [[../flows/Signal-Pipeline|Signal pipeline]] — upstream signal source feeding orders
- [[../concepts/Trading-Mode-Flags|Trading mode flags]]
- [[../concepts/Message-Queue-Topics|Message queue topics]] (aspirational vs. real)
- [[../decisions/ADR-004-paper-trading-default]]
- [[../decisions/ADR-006-mainnet-prices-paper-orders]]
- [[../decisions/ADR-007-no-v1-api-prefix]]
- Sibling services: [[trading-engine]], [[market-data-service]], [[api-gateway]], [[portfolio-manager]]
