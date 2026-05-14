<!-- refreshed: 2026-05-12 -->
# Architecture

**Analysis Date:** 2026-05-12

## System Overview

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                       React 18 + Vite frontend (:3000)                   │
│                            `frontend/src/`                               │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ REST (JSON) + WebSocket
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    api-gateway (:8000) — routing + admin auth            │
│                       `services/api-gateway/app/`                        │
│  Proxies /api/<domain>/<resource> → downstream services. JWT + admin     │
│  guard via `auth_middleware.py` (`get_current_admin_user`).              │
└──┬───────┬───────┬───────┬───────┬───────┬───────┬───────┬──────────────┘
   │       │       │       │       │       │       │       │
   ▼       ▼       ▼       ▼       ▼       ▼       ▼       ▼
 ┌────┐ ┌────┐  ┌────┐  ┌────┐  ┌────┐  ┌────┐  ┌────┐  ┌────┐
 │bybit│ │mkt │  │port│  │TA  │  │eng │  │noti│  │ml  │  │risk│
 │ 8001│ │8002│  │8003│  │8004│  │8005│  │8006│  │8007│  │8009│
 └──┬─┘ └──┬─┘  └──┬─┘  └──┬─┘  └──┬─┘  └──┬─┘  └──┬─┘  └──┬─┘
    │      │       │       │       │       │       │       │
    └──────┴───────┴───────┴───────┴───────┴───────┴───────┘
                        Polling HTTP (sync, no pub/sub)
                                 │
   ┌─────────────────────────────┼─────────────────────────────────┐
   ▼                             ▼                                  ▼
┌────────────────────┐  ┌────────────────────┐         ┌────────────────────┐
│ TimescaleDB        │  │ PostgreSQL          │         │ Redis (cache)      │
│ `klines`, `tickers`│  │ portfolio.*,        │         │ Sparse use; mkt    │
│ owned by mkt-data  │  │ trades, alerts      │         │ data caches in DB  │
└────────────────────┘  └────────────────────┘         └────────────────────┘

ml-retraining-service — cron-driven, no HTTP. Writes GRU artifacts to
`services/ml-prediction-service/models/`.
sentiment-analysis-service (:8008) — runs in compose but idle since
`ENABLE_SENTIMENT_ANALYSIS=false` (commits c346483 / acae081 / fe941cf / c171bb0).
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| api-gateway | Single ingress, JWT auth, admin guard, route to downstreams, OpenAPI surface | `services/api-gateway/app/main.py` |
| bybit-connector | Bybit REST + WS client, rate-limit / circuit-breaker, vault auth | `services/bybit-connector/app/bybit_rest_client.py` |
| market-data-service | Pull candles + tickers from Bybit on schedule, persist to TimescaleDB | `services/market-data-service/app/scheduler.py`, `repository.py` |
| portfolio-manager | Positions, balances, P&L; writes `portfolio.*` tables | `services/portfolio-manager/app/services/performance_history.py` |
| technical-analysis | 9 indicators, GRU inference, signal aggregator + voter | `services/technical-analysis/app/services/indicator_service.py` |
| trading-engine | Strategy execution, risk caps, auto-trader loop, order placement | `services/trading-engine/app/auto_trader.py`, `aggregation/voter.py` |
| notification-service | Telegram + email alerts, DLQ, alert rules | `services/notification-service/app/alert_manager.py` |
| ml-prediction-service | Standalone GRU inference surface (parallel to in-TA inference) | `services/ml-prediction-service/app/inference/` |
| ml-retraining-service | Cron-driven GRU retrain, writes new model artifacts | `services/ml-retraining-service/` |
| risk-metrics-service | Drawdown / VaR / Sharpe dashboards | `services/risk-metrics-service/` |
| sentiment-analysis-service | (Idle, flag-gated off) | `services/sentiment-analysis-service/` |

## Pattern Overview

**Overall:** Polling microservices over HTTP — a service-oriented architecture, **not** event-driven despite RabbitMQ being deployed.

**Key Characteristics:**
- Synchronous HTTP between services. Each service has its own `app/` package, FastAPI app, lifespan, Dockerfile.
- Per-service config via Pydantic Settings in `app/config.py` (each service maintains its own).
- TimescaleDB doubles as cache (Redis present but underused — `redis-empty` is documented gotcha).
- RabbitMQ broker is **provisioned** (compose + `rabbitmq_url` in bybit-connector config) but **no producers/consumers exist in the Python code today** — `grep -rn aio_pika|pika\.` returns zero hits outside config. All inter-service flow is HTTP.
- Frontend talks to gateway only; never directly to downstream services.

## Layers (within trading-engine, the most layered service)

**Aggregation layer:**
- Purpose: Reduce N indicator + ML signals to single buy/sell/hold + confidence.
- Location: `services/trading-engine/app/aggregation/`
- Files: `voter.py`, `aggregator_core.py`, `enhanced_aggregator.py`, `confidence_guard.py`, `gatekeeper.py`, `market_regime.py`, `signal_cache.py`, `validator.py`.
- Depends on: technical-analysis HTTP responses.
- Used by: orchestration + auto-trader.

**Orchestration layer:**
- Purpose: Strategy registry, allocator, risk coordinator, conflict resolver.
- Location: `services/trading-engine/app/orchestration/`
- Files: `orchestrator.py`, `registry.py`, `allocation.py`, `risk_coordinator.py`, `conflict_resolver.py`, `signal_aggregator.py`, `performance_tracker.py`.

**Execution layer:**
- Purpose: Smart order routing, TWAP/VWAP slicing.
- Location: `services/trading-engine/app/execution/`
- Files: `smart_order_router.py`, `twap_vwap.py`, `execution_scheduler.py`, `orderbook_analyzer.py`.

**Exchange adapters:**
- Purpose: Multi-exchange abstraction. Bybit primary; binance/coinbase/kraken stubs.
- Location: `services/trading-engine/app/exchanges/`
- Files: `bybit_adapter.py`, `factory.py`, `router.py`, `manager.py`, `base.py`.

**Lifespan hooks:**
- Purpose: Startup wiring (data feeds, ML models, risk state, strategy registry).
- Location: `services/trading-engine/app/lifespan/` — `data.py`, `ml.py`, `risk.py`, `strategy.py`.

**Handlers (FastAPI routers):**
- Location: `services/trading-engine/app/handlers/` — `signals.py`, `trades.py`, `positions.py`, `risk_budget.py`, `trading_control.py`, `phase1.py`, `grid_trading.py`, `statistical_arbitrage.py`, etc.

## Data Flow

### Primary trading path (paper mode, current default)

1. `market-data-service` scheduler pulls candles from Bybit mainnet → upsert `klines` / `tickers` in TimescaleDB (`services/market-data-service/app/scheduler.py`, `repository.py:26`).
2. `trading-engine` auto-trader loop (`services/trading-engine/app/auto_trader.py:842`) wakes every cycle, checks `EMERGENCY_STOP` file and `settings.auto_trading_enabled`.
3. For each validated symbol, engine HTTP-calls `technical-analysis` (:8004) — TA pulls candles from market-data, runs 9 indicators in `app/indicators/` plus GRU inference in `app/services/indicator_service.py`, returns aggregated signal.
4. Engine routes signal through `aggregation/voter.py` → `aggregation/gatekeeper.py` → risk caps in `orchestration/risk_coordinator.py`.
5. If pass, engine calls `bybit-connector` (:8001) for order placement; paper mode short-circuits to `app/paper_trading.py`.
6. Filled order → engine HTTP-posts to `portfolio-manager` (:8003); portfolio writes `portfolio.performance_history` (`services/portfolio-manager/app/services/performance_history.py:106`).
7. Alerts emitted to `notification-service` (:8006) → Telegram / email.

### Standalone ML inference path

- `ml-prediction-service` (:8007) is a parallel inference surface (`app/inference/`, `app/predictor_factory.py`). Currently called by ad-hoc clients / dashboards, not by trading-engine — engine reads GRU output via technical-analysis service. Two inference paths exist; the in-TA one is the live one.

### Retraining path

- `ml-retraining-service` has no HTTP port. Cron in container retrains GRU on schedule and writes artifacts to `services/ml-prediction-service/models/` (which the LSTM archive sits inside as `_archive_lstm/`).

**State Management:**
- No in-memory shared state between services (each service is its own process).
- Within trading-engine, state is held in module-level singletons (auto-trader loop instance, exchange manager, strategy registry) wired up by `app/lifespan/*.py`.

## Key Abstractions

**Indicator:**
- Purpose: Stateless function `compute(df) -> Signal` over OHLCV DataFrame.
- Examples: `services/technical-analysis/app/indicators/rsi.py`, `macd.py`, `squeeze_momentum.py`.
- Pattern: One module per indicator; combined by `app/services/indicator_service.py`.

**Strategy:**
- Purpose: Bundle of indicators + entry/exit rules + risk overlay.
- Examples: `services/technical-analysis/app/strategies/squeeze_momentum_strategy.py`, `services/trading-engine/app/multi_symbol_trader.py`.
- Pattern: `StrategyBase` contract (per `.claude/skills/trading-strategy-dev/SKILL.md`).

**Exchange adapter:**
- Purpose: Abstract Bybit / Binance / Coinbase / Kraken behind one interface.
- Pattern: `services/trading-engine/app/exchanges/base.py` defines contract; concrete adapters implement.

**Circuit breaker:**
- Purpose: Wrap downstream HTTP calls; trip on consecutive failures.
- Implementation: `services/trading-engine/app/core/circuit_breaker.py` (Prometheus-instrumented).

## Entry Points

**api-gateway HTTP:**
- Location: `services/api-gateway/app/main.py`
- Triggers: Frontend or external clients hitting `:8000/api/<domain>/<resource>`.
- Responsibilities: JWT verification, admin guard, proxy to downstream service.

**trading-engine auto-trader:**
- Location: `services/trading-engine/app/auto_trader.py`
- Triggers: Lifespan-startup task launched by `services/trading-engine/app/main.py:262`, gated on `settings.auto_trading_enabled` AND absence of `EMERGENCY_STOP` file.
- Responsibilities: Periodic signal poll → aggregate → execute.

**market-data scheduler:**
- Location: `services/market-data-service/app/scheduler.py`
- Triggers: Lifespan task; runs every N seconds (default 5 min for ticker refresh).
- Responsibilities: Pull from Bybit, upsert TimescaleDB.

**ml-retraining cron:**
- Location: `services/ml-retraining-service/`
- Triggers: Container-internal cron.
- Responsibilities: Pull historical klines, retrain GRU per symbol, write new artifacts.

## Risk Cap Enforcement

All caps live in `trading-engine`. Per-trade and daily-loss are non-negotiable per project rules.

**Per-trade cap:**
- Config: `services/trading-engine/app/config.py:321` — `max_risk_per_trade`.
- LIVE mode: 2% (hard requirement before flipping `TRADING_MODE=LIVE`).
- Paper mode: 10% (per ADR-010, filed 2026-05-06, to clear Bybit min-notional on $100 balance).
- Enforced in `services/trading-engine/app/orchestration/risk_coordinator.py` and position sizing in `app/position_sizing.py`.

**Daily-loss circuit breaker:**
- Config: `services/trading-engine/app/config.py:364` — `max_daily_loss_pct` (5%).
- Enforced in `services/trading-engine/app/core/circuit_breaker.py` + `app/orchestration/risk_coordinator.py`.
- Trips: halts new entries for the trading day.

**Other circuit-breaker thresholds** (`app/config.py` lines 501-522):
- `circuit_breaker_max_consecutive_losses`
- `circuit_breaker_max_drawdown_pct`
- `circuit_breaker_min_win_rate_pct`
- `circuit_breaker_evaluation_trades`

**Auto-trader gate (EMERGENCY_STOP):**
- File path config: `services/trading-engine/app/config.py:199` — `emergency_stop_file`, default `/app/EMERGENCY_STOP`.
- Host path: `EMERGENCY_STOP` at repo root (currently exists as a directory on disk).
- Compose bind-mount: **read-only** into trading-engine container.
- Check sites:
  - Boot: `services/trading-engine/app/main.py:284` — refuses to start auto-trader if file present.
  - Loop: `services/trading-engine/app/auto_trader.py:842,877` — checks every iteration; broken-bind-mount detection at `:857` (catches the WSL race where mount silently fails and `EMERGENCY_STOP` looks present-but-empty).
- Manual pause: `touch EMERGENCY_STOP` (host) OR `POST /api/portfolio/emergency-stop` (admin-guarded).

**LIVE-mode ack:**
- Trading-engine refuses to boot in `TRADING_MODE=LIVE` without `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`. Catches env drift on cloud hosts.

## Data Ownership

| Table / namespace | Owner service | DB |
|---|---|---|
| `klines`, `tickers` | market-data-service | TimescaleDB |
| `portfolio.performance_history`, `portfolio.positions`, `portfolio.balances` | portfolio-manager | PostgreSQL |
| `trades`, signal logs | trading-engine | PostgreSQL |
| Alert state, DLQ | notification-service | PostgreSQL |
| ML model artifacts | ml-retraining-service writes, ml-prediction + technical-analysis read | filesystem (`services/ml-prediction-service/models/`) |

No service writes outside its owned namespace. Cross-service reads happen over HTTP, not direct DB queries — except trading-engine reads `klines` from TimescaleDB directly during backtest mode (`app/backtesting/`).

## Event Flows (RabbitMQ status)

- **Provisioned but unused.** Compose runs `rabbitmq:3-management`. `bybit-connector/app/config.py:88-94` and `config_vault.py:138-153` expose `rabbitmq_*` settings and a `rabbitmq_url` property — but no `aio_pika` / `pika` import exists in any service's runtime code. Only config and tests reference RabbitMQ.
- **Live topics:** none. The originally-planned `signals.*`, `orders.*`, `portfolio.*` exchanges are not declared at runtime.
- **Sentiment removal impact:** since sentiment was the original consumer of any planned event flow, post-removal (`c346483`, `acae081`, `fe941cf`, `c171bb0`) there is no producer/consumer pair left to migrate. Treat RabbitMQ as dead infrastructure until a real pub/sub need re-emerges.

## Architectural Constraints

- **Threading:** Each service is single-event-loop asyncio. Workers (uvicorn `--workers`) are 1 in compose defaults. Heavy CPU (TA, ML inference) runs in the same loop — no thread-pool offload today.
- **Global state:** Module-level singletons inside trading-engine for auto-trader, exchange manager, strategy registry — wired at lifespan startup. Tests must override via `app.dependency_overrides` (see `services/api-gateway/tests/conftest.py` `admin_client` fixture pattern).
- **Circular imports:** None known after May 2026 refactor (`main.py` was shrunk; logic moved into `handlers/`, `lifespan/`, `aggregation/`).
- **Two compose files:** `docker-compose.unified.yml` is **canonical** (16 services incl. DBs). `docker-compose.yml` is incomplete (missing postgres/timescaledb/redis/rabbitmq) — do not use.
- **Mainnet/testnet split:** `BYBIT_TESTNET` controls price source only; `PAPER_TRADING_MODE` / `TRADING_MODE` control execution. Four-step LIVE flip required: `PAPER_TRADING_MODE=false`, `TRADING_MODE=LIVE`, mainnet keys with trade perms, `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`.

## Anti-Patterns

### Treating `docker-compose.yml` as canonical

**What happens:** Some legacy docs reference `docker-compose.yml`. It boots services but omits DBs and broker, leading to silent connect-refused loops.
**Why it's wrong:** Services fail health checks; you waste time debugging fake outages.
**Do this instead:** Always `docker compose -f docker-compose.unified.yml up -d`.

### Patching `builtins.open` for emergency-stop routes

**What happens:** Tests mock `builtins.open` to assert `EMERGENCY_STOP` write, but the actual code uses `pathlib.Path.write_text`.
**Why it's wrong:** `Path.write_text` goes through `_io.open` (C-level), bypassing the mock. Test passes vacuously.
**Do this instead:** `mock.patch("pathlib.Path.write_text")` directly. See `services/api-gateway/tests/conftest.py`.

### Rounding sub-$1 prices to 2dp

**What happens:** Historical bug — TA service applied `round(price, 2)` to ADAUSDT-class assets, collapsing $0.4523 → $0.45 and producing flip-flop signal noise.
**Why it's wrong:** 30+ losing trades attributable to it (commit `487d1bd`).
**Do this instead:** `float(price)` on any price-domain field; preserve full precision.

### Re-adding symbols without data-presence check

**What happens:** XRP / DOGE were silently re-added during dev; market-data hadn't been backfilled.
**Why it's wrong:** Engine quoted stale or empty candles.
**Do this instead:** Validated symbol list is BTC, ETH, SOL, BNB, ADA. Confirm `klines` rows exist before adding a new one.

## Error Handling

**Strategy:** Per-service circuit breakers wrap downstream HTTP calls.

**Patterns:**
- `services/trading-engine/app/core/circuit_breaker.py` — three-state (closed / open / half-open) with Prometheus metrics on `circuit_breaker_state`, `circuit_breaker_calls_total`, `circuit_breaker_state_transitions_total`.
- `services/bybit-connector/app/circuit_breaker.py` — wraps Bybit REST.
- `services/market-data-service/app/circuit_breaker.py` — wraps upstream fetch.
- Notification DLQ for failed Telegram/email: `services/notification-service/app/dlq.py`.

## Cross-Cutting Concerns

**Logging:** Structured logs per service; trading-engine logs to `/app/logs` (bind-mount race in WSL: if `PermissionError`, `docker compose up -d --force-recreate trading-engine`).
**Validation:** Pydantic models per service in `app/models.py` or `app/models/`.
**Authentication:** JWT at api-gateway. Downstream services trust gateway-set headers; admin routes go through `get_current_admin_user` dependency in `services/api-gateway/app/auth_middleware.py`. Plain `test_client` returns 403 on admin routes — tests must use `admin_client` fixture.
**Secrets:** `.env` (gitignored) or HashiCorp Vault via `bybit-connector/app/config_vault.py`. Never commit `.env`.
**Metrics:** Prometheus :9090 scrapes each service's `/metrics`. Grafana :3001 dashboards.
**Health:** Every service exposes `GET /health` (liveness) and `GET /ready` (readiness).

---

*Architecture analysis: 2026-05-12*
