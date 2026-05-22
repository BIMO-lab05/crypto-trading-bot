<!-- refreshed: 2026-05-22 -->
# Architecture

**Analysis Date:** 2026-05-22

## System Overview

```text
┌─────────────────────────────────────────────────────────────────┐
│                   React 18 Frontend (:3000)                     │
│            `frontend/src/App.jsx` — 7 routes                   │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP REST
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              api-gateway (:8000)                                │
│   `services/api-gateway/app/main.py`                           │
│   ServiceProxy (httpx) routes to all upstream services         │
└──┬──────────┬───────────┬───────────┬──────────────────────────┘
   │          │           │           │
   ▼          ▼           ▼           ▼
bybit-     market-    technical-  trading-
connector  data-svc   analysis   engine
(:8001)    (:8002)    (:8004)    (:8005)
   │          │           │           │
   │    TimescaleDB   indicators  auto-trader
   │    (candles)     (RSI,MACD…) loop
   │                              │
   └──────────────────────────────┘
   bybit-connector is sole Bybit gateway
   (Phase 13 BC-05/D-09, 2026-05-22)
```

## Services

| Service | Port | Entry Point | Purpose |
|---------|------|-------------|---------|
| api-gateway | 8000 | `services/api-gateway/app/main.py` | Frontend routing, auth, admin guard |
| bybit-connector | 8001 | `services/bybit-connector/app/main.py` | Sole Bybit REST gateway + circuit breaker |
| market-data-service | 8002 | `services/market-data-service/app/main.py` | Candle ingest → TimescaleDB |
| portfolio-manager | 8003 | `services/portfolio-manager/app/main.py` | Positions, balances, P&L |
| technical-analysis | 8004 | `services/technical-analysis/app/main.py` | TA indicators + GRU inference |
| trading-engine | 8005 | `services/trading-engine/app/main.py` | Strategy + risk + order execution + auto-trader |
| notification-service | 8006 | `services/notification-service/app/main.py` | Telegram + email alerts |
| ml-prediction-service | 8007 | `services/ml-prediction-service/app/main.py` | Standalone GRU inference endpoints |
| sentiment-analysis-service | 8008 | `services/sentiment-analysis-service/app/main.py` | News/social sentiment (idle) |
| risk-metrics-service | 8009 | `services/risk-metrics-service/app/main.py` | Risk dashboards |
| ml-retraining-service | — | `services/ml-retraining-service/app/main.py` | Cron-driven GRU retrain (no HTTP) |
| tournament-harness | internal | `services/tournament-harness/app/main.py` | Tournament leaderboard read (SQLite) + CLI |

**Note:** tournament-harness is a 12th service not in the CLAUDE.md service table. It exposes `GET /api/v1/tournaments` and `GET /api/v1/tournaments/{id}/runs` and has a CLI at `services/tournament-harness/app/cli.py`.

## Component Responsibilities

| Component | Responsibility | Key File |
|-----------|----------------|----------|
| api-gateway | Auth, routing, admin guard, preflight carry-ins | `services/api-gateway/app/main.py` |
| ServiceProxy | httpx-based reverse proxy to upstream services | `services/api-gateway/app/services/service_proxy.py` |
| bybit-connector | Bybit REST API wrapper, rate limiting, circuit breaker, tape replay | `services/bybit-connector/app/main.py` |
| BybitRestClient | Signs+sends Bybit REST requests | `services/bybit-connector/app/bybit_rest_client.py` |
| market-data-service fetcher | Fetches klines/ticker from bybit-connector, writes TimescaleDB | `services/market-data-service/app/fetcher.py` |
| signal_aggregator | Fetches 10 indicators concurrently (asyncio.gather), calls CoreAggregator | `services/trading-engine/app/signal_aggregator.py:707` |
| CoreAggregator | Gatekeeper → validator → voter orchestration | `services/trading-engine/app/aggregation/aggregator_core.py` |
| StrategyBase | ABC for all trading strategies | `services/trading-engine/app/strategies/base.py` |
| auto_trader | Main trading loop, paper/live branch, kill-switch checks | `services/trading-engine/app/auto_trader.py` |
| notification_client | aiohttp HTTP POSTs to notification-service | `services/trading-engine/app/services/notification_client.py` |
| tournament-harness CLI | `start tournament`, `export-snapshot` commands | `services/tournament-harness/app/cli.py` |

## Pattern Overview

**Overall:** Event-driven microservices with synchronous HTTP transport

**Key Characteristics:**
- All inter-service communication is synchronous HTTP (httpx / aiohttp). RabbitMQ is configured in env/compose but NOT used in any production code path — only a connectivity health-check ping exists at `services/trading-engine/app/core/health.py:421`.
- Each service is an independent FastAPI app with its own `config.py`, `requirements.txt`, and `Dockerfile`.
- Async throughout: Python `asyncio` + `httpx.AsyncClient` / `aiohttp.ClientSession`.
- No AMQP publish/subscribe in production. The routing key `trade.events` appears only in a test fixture at `services/trading-engine/tests/integration/test_telegram_notifications.py`.

## Layers (within trading-engine)

**Entry / Lifespan:**
- Purpose: Boot sequence, dependency wiring, LIVE preflight
- Location: `services/trading-engine/app/main.py`, `services/trading-engine/app/lifespan/`
- Contains: 4 composed `@asynccontextmanager` phases (`data.py`, `ml.py`, `strategy.py`, `risk.py`)
- Depends on: config, all downstream modules

**Handlers / Routers:**
- Purpose: FastAPI route handlers, request/response mapping
- Location: `services/trading-engine/app/handlers/`
- Depends on: services layer

**Services:**
- Purpose: Business logic, orchestration of domain objects
- Location: `services/trading-engine/app/services/`
- Depends on: domain models, aggregation, risk

**Domain:**
- Purpose: Strategies, aggregation, risk, execution
- Location: `services/trading-engine/app/strategies/`, `app/aggregation/`, `app/risk/`, `app/execution/`

**External Clients:**
- Purpose: HTTP calls to bybit-connector, technical-analysis, notification-service
- Location: `services/trading-engine/app/services/notification_client.py`, signal_aggregator fetch functions

## Data Flow

### Primary Trading Signal Path

1. **bybit-connector** receives REST from Bybit mainnet (`GET /api/v1/market/kline`, `GET /api/v1/market/ticker`)
2. **market-data-service** fetcher (`services/market-data-service/app/fetcher.py:69`) polls bybit-connector every schedule tick → writes candles to TimescaleDB
3. **trading-engine auto_trader** loop fires (when `safety/EMERGENCY_STOP` absent, `AUTO_TRADING_ENABLED=true`)
4. `signal_aggregator.fetch_all_indicators()` (`services/trading-engine/app/signal_aggregator.py:707`) calls **technical-analysis** service concurrently via `asyncio.gather()` for 10 indicators
5. Results pass through `CoreAggregator` (`services/trading-engine/app/aggregation/aggregator_core.py`): gatekeeper → validator → voter
6. `StrategyBase.generate_signals()` (`services/trading-engine/app/strategies/base.py`) evaluates aggregated result
7. Risk caps checked (per-trade 10% paper / 2% LIVE, 5% daily-loss circuit-breaker)
8. Paper engine (`get_paper_engine()`) or live engine (`get_live_engine()`) called at `services/trading-engine/app/auto_trader.py:1836, 2412`
9. **notification_client** POSTs trade event to **notification-service** via `aiohttp.ClientSession`
10. **portfolio-manager** updated via HTTP

### Market Data Ingest Path (Phase 13, 2026-05-22)

- **market-data-service/app/fetcher.py:69**: `self.base_url = base_url or settings.bybit_connector_url`
- Default: `http://localhost:8001` (see `services/market-data-service/app/config.py:62`)
- Calls `GET /api/v1/market/kline` and `GET /api/v1/market/ticker` on bybit-connector
- Writes to TimescaleDB. market-data-service does NOT call Bybit directly.

### Notification Path

- trading-engine auto_trader → `notification_client._post(endpoint, data)` → `aiohttp.ClientSession.post(notification_service_url)` → notification-service → Telegram/email
- No AMQP involved. Config field: `notification_service_url` in `services/trading-engine/app/config.py:43`

## Voting Indicators

`signal_aggregator.fetch_all_indicators()` (`services/trading-engine/app/signal_aggregator.py:734-755`) fetches these concurrently:

| Indicator | Role | Source endpoint |
|-----------|------|-----------------|
| RSI | Voter | technical-analysis |
| MACD | Voter | technical-analysis |
| BOLLINGER_BANDS | Voter | technical-analysis |
| SMA | Voter | technical-analysis |
| EMA | Voter | technical-analysis |
| TREND_FILTER | Gatekeeper (blocks signal if fails) | technical-analysis |
| VOLUME_CONFIRMATION | Validator (reduces confidence if fails) | technical-analysis |
| STOCHASTIC | Voter | technical-analysis |
| ICHIMOKU | Voter | technical-analysis |
| ADX | Regime gate | technical-analysis |
| ATR | Non-voting (position sizing / stop-loss) | technical-analysis |

**Disabled (commented out in signal_aggregator.py):** RSI_DIVERGENCE, SQZMOM_ENHANCED.
**Do NOT exist:** OBV, VWAP — no files in `services/technical-analysis/app/indicators/` for these.

**Note:** technical-analysis also has a minimal internal aggregator at `services/technical-analysis/app/handlers/analysis.py` (RSI + MACD + trend_filter only) exposed at `/api/v1/analysis/aggregated/{symbol}`. This is NOT the canonical aggregator used by the auto-trader.

## Key Abstractions

**StrategyBase:**
- Purpose: Contract all trading strategies must implement
- File: `services/trading-engine/app/strategies/base.py`
- Required methods: `analyze()`, `generate_signals()`, `calculate_position_size()`
- Enums: `StrategyRiskLevel` (CONSERVATIVE/MODERATE/AGGRESSIVE/VERY_AGGRESSIVE), `StrategyCategory` (TREND_FOLLOWING/MEAN_REVERSION/MOMENTUM/BREAKOUT/ARBITRAGE/GRID/SCALPING/HYBRID)
- Strategies live in: `services/trading-engine/app/strategies/`

**CoreAggregator:**
- Purpose: Orchestrates gatekeeper → validator → voter pipeline
- File: `services/trading-engine/app/aggregation/aggregator_core.py`
- Sub-components: `gatekeeper.py`, `validator.py`, `voter.py`, `market_regime.py`, `confidence_guard.py`, `signal_cache.py`, `enhanced_aggregator.py`, `multi_timeframe.py`

**ServiceProxy (api-gateway):**
- Purpose: httpx-based reverse proxy with timeout=30s
- File: `services/api-gateway/app/services/service_proxy.py`
- Service URL map: bybit, market-data, technical-analysis, trading-engine, portfolio-manager, risk-metrics, ml-prediction, sentiment-analysis

**BybitRestClient (bybit-connector):**
- Purpose: Signs and sends Bybit API requests
- File: `services/bybit-connector/app/bybit_rest_client.py`
- Tape replay alternative: `services/bybit-connector/app/tape_replay_client.py` (test mode)

## Entry Points

**API Gateway:**
- Location: `services/api-gateway/app/main.py`
- Route domains: `/api/market/*`, `/api/analysis/*`, `/api/trading/*`, `/api/portfolio/*`, `/api/tournament/*`
- Auth routes: `/auth/register`, `/auth/login`, `/auth/me`, `/auth/logout`
- Includes `preflight_carry_ins_router`

**bybit-connector boot:**
- Live mode: `create_rest_client(settings, on_breaker_state_change=_update_breaker_gauge)` (`services/bybit-connector/app/main.py`)
- Tape-replay mode: `if settings.market_data_source == "tape": app.state.rest_client = TapeReplayClient(...)`
- Rate limits: market data 200/min, orders 10/min, account 20/min

**trading-engine lifespan:**
- Location: `services/trading-engine/app/main.py`
- 4 composed `@asynccontextmanager` phases in `services/trading-engine/app/lifespan/`: `data.py`, `ml.py`, `strategy.py`, `risk.py`
- LIVE preflight at `services/trading-engine/app/main.py:263-290`
- Auto-trader boot (with EMERGENCY_STOP gate) at `services/trading-engine/app/main.py:296-338`

**trading-engine routers:**
- Mounted at `services/trading-engine/app/main.py:440-494`
- Auto-stripped imports re-annotated `# noqa: F401` at `services/trading-engine/app/main.py:63-174` to survive autoflake

**Frontend:**
- Location: `frontend/src/main.jsx` (Vite entry) → `frontend/src/App.jsx` (React Router v6)
- Routes: `/` (Dashboard), `/phase1` (Phase1Dashboard), `/phase3` (Phase3Dashboard), `/performance` (PerformanceDashboard), `/tournament` (TournamentDashboard), `/portfolio` (Portfolio), `/settings` (Settings)

**Migrations:**
- SQL migrations: `infrastructure/migrations/001–005_*.sql` (applied by `start-system` skill)

## Kill-Switch Flow

Kill-switch is **file-based** using `safety/EMERGENCY_STOP` (host) / `/app/safety/EMERGENCY_STOP` (container).

**Boot gate** (`services/trading-engine/app/main.py:314`):
```
if stop_file.is_file():
    logger.critical("EMERGENCY_STOP file present — auto-trader NOT started")
    # auto_trader.start() is skipped
```

**Loop gate** (`services/trading-engine/app/auto_trader.py:886`):
```
if self.emergency_stop_file.is_file():
    # pause trading, wait for file removal
```

**Broken bind-mount detection** (`services/trading-engine/app/auto_trader.py:859`): checks if safety dir is accessible; symptoms differ from missing file — important distinction.

**Activate:** `touch safety/EMERGENCY_STOP` or `POST /api/portfolio/emergency-stop` (admin-guarded).
**Deactivate:** `rm safety/EMERGENCY_STOP` — auto-trader auto-restarts on next loop tick. If halted at boot, requires manual `POST /api/trading/start`.
**Full stop:** `POST /api/trading/auto/stop`

## Paper vs Live Decision Tree

```
trading-engine boot
    │
    ├─ TRADING_MODE == "LIVE"? (services/trading-engine/app/main.py:263-290)
    │       ├─ LIVE_TRADING_ACK == "I_UNDERSTAND_REAL_MONEY"? → NO → RuntimeError, refuse boot
    │       └─ max_risk_per_trade > 0.02? → YES → RuntimeError, refuse boot
    │
    └─ auto_trader loop (app/auto_trader.py:1836, 2412)
            ├─ trading_mode == "LIVE" → get_live_engine() → real orders via bybit-connector
            └─ trading_mode == "PAPER" → get_paper_engine() → simulated orders internally
```

**Current defaults:**
- `trading_mode: "PAPER"` (`services/trading-engine/app/config.py:193`)
- `max_risk_per_trade: 0.10` (10% — paper default per ADR-010, `services/trading-engine/app/config.py:321-332`)
- `max_daily_loss_pct: 5.0` (`services/trading-engine/app/config.py:364-365`)
- `BYBIT_TESTNET=false` — uses mainnet prices but simulated orders
- `AUTO_TRADING_ENABLED=true` in `.env` (operator override; loop fires only if EMERGENCY_STOP absent)

## Architectural Constraints

- **Threading:** Single-threaded asyncio event loop per service. `asyncio.gather()` used for concurrent HTTP in signal aggregator. CPU-heavy ML inference offloaded to thread pools in ml-prediction-service.
- **Global state:** Each service has module-level singletons (settings, DB pool, HTTP clients) initialized in lifespan. See `services/trading-engine/app/lifespan/` for trading-engine's 4-phase approach.
- **Circular imports / autoflake:** `services/trading-engine/app/main.py:63-174` imports annotated `# noqa: F401` — autoflake strips these on refactor but they are required for test patching via `app.main.<symbol>`. Do NOT remove them without re-adding `# noqa: F401`.
- **RabbitMQ:** Configured in compose / env but idle. Only use: AMQP health-check ping (`services/trading-engine/app/core/health.py:421`). Do not assume queue-based messaging without adding publisher/subscriber code.
- **TimescaleDB as cache:** market-data-service writes candles to TimescaleDB (not Redis). Redis is configured but empty in practice. If prices look stale, hit `POST /api/v1/collect/ticker/{symbol}` on port 8002.
- **Testnet/mainnet DB contamination:** TimescaleDB has mixed testnet/mainnet history before 2026-04-25. Filter `is_mainnet=true` for backtests.

## Anti-Patterns

### Bypassing StrategyBase for new strategies

**What happens:** Defining a standalone strategy function without extending `StrategyBase`.
**Why it's wrong:** auto_trader loop and strategy registry expect the full `analyze()` / `generate_signals()` / `calculate_position_size()` interface.
**Do this instead:** Extend `StrategyBase` in `services/trading-engine/app/strategies/base.py` and register in the strategy registry.

### Calling Bybit directly from services other than bybit-connector

**What happens:** A service opens its own HTTP session to Bybit APIs.
**Why it's wrong:** Bypasses bybit-connector's circuit breaker, rate limiting, tape-replay mode, and centralized auth. Phase 13 explicitly centralized all Bybit access through bybit-connector.
**Do this instead:** Call bybit-connector at `http://bybit-connector:8001/api/v1/market/*` (or via api-gateway).

### Assuming RabbitMQ is the event bus

**What happens:** Code published to AMQP queue expecting downstream subscribers.
**Why it's wrong:** No consumers exist in production code. All live inter-service messaging is synchronous HTTP.
**Do this instead:** POST directly to the target service's HTTP API (e.g., notification_client pattern).

### Removing `# noqa: F401` imports in trading-engine/app/main.py

**What happens:** Autoflake or a linter removes "unused" imports at `services/trading-engine/app/main.py:63-174`.
**Why it's wrong:** Those imports register symbols under `app.main.*` that test mocks rely on for `monkeypatch` patching.
**Do this instead:** Keep `# noqa: F401` annotation on all such imports.

## Error Handling

**Strategy:** Exceptions in the auto-trader loop are caught, logged, and the loop continues with backoff. Unrecoverable startup errors raise `RuntimeError` and abort boot.

**Patterns:**
- LIVE preflight: `raise RuntimeError(...)` on missing ACK or over-cap risk — intentional hard abort.
- Circuit breaker in bybit-connector (`services/bybit-connector/app/circuit_breaker.py`) — auto-opens on repeated Bybit failures; state reported via Prometheus gauge.
- HTTP 4xx/5xx from upstream services handled per-call in signal_aggregator; missing indicator falls back to neutral rather than crashing the loop.

## Cross-Cutting Concerns

**Logging:** `shared/utils/structured_logging.py` — JSON structured logging, imported by most services.
**Validation:** Input validation via `shared/utils/input_validation.py`; Pydantic models per service.
**Authentication:** JWT-based auth in api-gateway (`services/api-gateway/app/auth.py`). Admin routes require `admin_client` fixture with `get_current_admin_user` override in tests.
**Secrets:** Vault integration via `shared/vault_client.py`, `shared/vault_config.py`. Bybit keys in `.env` (gitignored).
**Monitoring:** Prometheus metrics exposed at `/metrics` on each service. Grafana at `:3001`. Alert rules in `infrastructure/monitoring/prometheus/alerts/`.

---

*Architecture analysis: 2026-05-22*
