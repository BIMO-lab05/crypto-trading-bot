# Trading Engine Service

> Merged from `QUICK_CONFIG_REFERENCE.md`, `QUICK_REFERENCE.md`, `SQZMOM_DEPLOYMENT_GUIDE.md`, and `SQZMOM_QUICK_REFERENCE.md` on 2026-07-30.

## Overview

The Trading Engine is the core decision-making service of the crypto trading bot. It aggregates signals from the Technical Analysis Service, applies risk management rules, and executes trades in paper or live mode. All inter-service communication is **synchronous REST over HTTP** — there is no RabbitMQ event bus in the pipeline (see `wiki/concepts/HTTP-Service-Mesh.md`).

**Current operating state (2026-07-30):** paper trading (`TRADING_MODE=PAPER`), mainnet price feed (`BYBIT_TESTNET=false`), ML predictions gated off (`ENABLE_ML_PREDICTIONS=false`).

## Features

### Core Capabilities
- **Multi-Indicator Aggregation**: RSI, MACD, Bollinger Bands, SMA, EMA voters + trend-filter gatekeeper + volume-confirmation validator
- **Intelligent Signal Weighting**: confidence-based scoring; multi-timeframe blending and volume-profile enhancement (see `wiki/components/`)
- **Risk Management**: position sizing, stop-loss, take-profit, exposure limits, daily-loss circuit breaker
- **Paper Trading**: safe simulation with virtual balance (default $100 — see ADR-010)
- **Real-time Position Tracking**: live P&L calculation and monitoring
- **Performance Metrics**: win rate, ROI, Sharpe ratio, drawdown tracking

### Safety Features
- **Default Paper Mode**: starts in paper trading mode by default
- **Risk Limits** (current, per `wiki/concepts/Risk-Model.md`):
  - Per-trade cap: **10% in paper mode** (relaxed per ADR-010, 2026-05-06, to clear Bybit min-notional on a $100 balance) / **2% hard cap in LIVE** (non-negotiable; clamps, does not reject — fixed 2026-07-28)
  - **5% daily loss** circuit breaker (auto-rolls per UTC day)
  - Total exposure and per-position size caps (`config.py`; 80% / 5% as of 2026-07-29)
- **Signal Validation**: minimum confidence (0.6) and consensus (3 indicators). Since 2026-07-28 consensus counts **directional votes only** (a BUY's consensus = buy votes, HOLDs no longer count toward it)
- **Emergency Stop**: kill-switch file `safety/EMERGENCY_STOP` (container: `/app/safety/EMERGENCY_STOP`) + manual/automatic halt endpoints
- **LIVE boot guard**: refuses to boot in LIVE without `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`

## Architecture

```
┌─────────────────────────────────────────────┐
│         Trading Engine (Port 8005)          │
├─────────────────────────────────────────────┤
│  Signal Aggregator ── Risk Manager          │
│           │                │                │
│           ▼                ▼                │
│         Decision Engine                     │
│           │                                 │
│           ▼                                 │
│  Position Manager ── Paper Trading Engine   │
└─────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
  Technical Analysis    Bybit Connector
       (8004)               (8001)
```

> Note (2026-07-30): older trading-engine docs placed bybit-connector on 8002. Current port map: bybit-connector **8001**, market-data-service **8002**, portfolio-manager **8003** (root `CLAUDE.md` is authoritative).

## Service & Infrastructure Ports

| Service | Port | Purpose |
|---------|------|---------|
| Trading Engine | 8005 | This service |
| API Gateway | 8000 | Frontend routing (routes are `/api/<domain>/...` — **no `/v1` prefix** at the gateway) |
| Bybit Connector | 8001 | Exchange REST/WS wrapper (LIVE order routing) |
| Market Data Service | 8002 | Live price source |
| Portfolio Manager | 8003 | Position/balance reconciliation |
| Technical Analysis | 8004 | Signal generation (hard dependency) |
| PostgreSQL | 5433 (host) | Trade/position persistence (db `trading_engine`) |
| Redis | 6379, DB 2 | Signal cache (some legacy dev setups host-mapped Redis to 6380 — canonical compose uses 6379) |

Canonical stack bring-up uses **`docker-compose.unified.yml`** at repo root (`docker-compose.yml` is incomplete — missing databases).

## API Endpoints

Service-internal routes keep the `/api/v1` prefix. The api-gateway strips versioning: frontend-facing paths are `/api/<domain>/<resource>` with **no `/v1`**.

### Health & Status
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Quick health check (cached, ~5ms) with dependency status |
| `/health/detailed` | GET | Comprehensive metrics (dependencies + system metrics) |
| `/status` | GET | Trading mode, auto-trading state, balance, open positions |
| `/api/v1/trading/status` | GET | Auto-trading stats |

```bash
curl http://localhost:8005/health
curl http://localhost:8005/health/detailed | jq
curl http://localhost:8005/status
```

### Signals, Positions, Performance, Control
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/signals/{symbol}?interval=60` | GET | Aggregated trading signal |
| `/api/v1/signals/{symbol}/analyze?execute=true` | POST | Analyze and optionally execute |
| `/api/v1/positions?status=open` | GET | List positions |
| `/api/v1/positions/{position_id}` | GET | Position detail |
| `/api/v1/performance` | GET | Win rate, P&L, ROI, balances |
| `/api/v1/trading/start` | POST | Start automated trading |
| `/api/v1/trading/stop` | POST | Stop automated trading |

Signal response includes per-indicator `signal`/`confidence`/`value`, `aggregated_score` (−1..+1), `consensus_count`, and vote breakdown metadata.

## Configuration

### Environment Variables (current defaults, 2026-07-30)

| Variable | Default | Validated range | Notes |
|----------|---------|-----------------|-------|
| `SERVICE_NAME` | trading-engine | — | |
| `SERVICE_PORT` | 8005 | 1–65535 | |
| `TRADING_MODE` | PAPER | PAPER \| LIVE | LIVE additionally requires `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY` |
| `AUTO_TRADING_ENABLED` | false (compose) | bool | Operator `.env` override is `true` since 2026-05-05 |
| `TECHNICAL_ANALYSIS_URL` | http://localhost:8004 | — | |
| `BYBIT_CONNECTOR_URL` | http://bybit-connector:8001 | — | 8002 in pre-2026 docs is stale |
| `MAX_RISK_PER_TRADE` | 0.10 (paper) | ≤0.02 enforced in LIVE | ADR-010; restore ≤2% before LIVE (see `/RUNBOOK.md` Pre-LIVE checklist) |
| `MAX_POSITION_SIZE_PCT` | see `config.py` | 0.1–10.0 | older quick-refs cited 2.0 |
| `MAX_DAILY_LOSS_PCT` | 5.0 | 1.0–20.0 | circuit breaker, auto-rolls per UTC day |
| `MAX_TOTAL_EXPOSURE_PCT` | see `config.py` | 5.0–100.0 | older quick-refs cited 20.0; 80 as of 2026-07-29 |
| `DEFAULT_STOP_LOSS_PCT` | 3.0 | 0.5–10.0 | |
| `DEFAULT_TAKE_PROFIT_PCT` | 6.0 | 1.0–50.0 | |
| `MIN_SIGNAL_CONFIDENCE` | 0.6 | 0.0–1.0 | |
| `MIN_CONSENSUS_INDICATORS` | 3 | 1–10 | directional votes only since 2026-07-28 |
| `PAPER_INITIAL_BALANCE` | 100.0 | — | older README prose said $10,000 — stale |
| `PAPER_COMMISSION_PCT` | 0.1 | — | |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` | localhost / 6379 / 2 | — | |
| `LOG_LEVEL` | INFO | INFO/DEBUG/WARNING/ERROR/CRITICAL | pydantic-validated |

### Configuration File Locations

| File | Purpose |
|------|---------|
| `services/trading-engine/app/config.py` | Settings schema with pydantic validation (~635 lines) |
| `services/trading-engine/.env` | Current environment settings (never commit) |
| `services/trading-engine/.env.example` | Setup template |
| `services/trading-engine/.env.test` | Test database config |
| `services/bybit-connector/.env` | Bybit API configuration |

### Database Configuration

- **PostgreSQL** — host `localhost`, port `5433`, db `trading_engine`, user `cryptobot` (dev password in `.env` only). Persistent storage of trades, positions, portfolios.
- **Redis** — host `localhost`, port `6379`, DB `2`. High-speed signal caching.

## Redis Signal Cache & Health Monitor

> Merged from `QUICK_REFERENCE.md` on 2026-07-30.

### Cache key pattern

```
signal:{symbol}:{timeframe}[:{indicator}]

signal:BTCUSDT:60        # 1-hour aggregated signal
signal:BTCUSDT:240       # 4-hour aggregated signal
signal:BTCUSDT:60:rsi    # specific indicator
```

Default TTLs: real-time signals **60s**; aggregated signals **300s**; warmed cache **300s**.

### Usage

```python
from app.aggregation.signal_cache import get_signal_cache

cache = await get_signal_cache(redis_url="redis://localhost:6379/2", ttl_seconds=60)
await cache.set("signal:BTCUSDT:60", {"signal": "BUY", "confidence": 0.85}, ttl=60)
signal = await cache.get("signal:BTCUSDT:60")
await cache.invalidate_pattern("signal:BTCUSDT:*")
stats = await cache.get_stats()   # includes hit_rate
```

### Health monitor

```python
from app.monitoring import get_health_monitor, HealthStatus

monitor = get_health_monitor()
health = await monitor.perform_health_check(
    postgres_enabled=True,
    redis_url="redis://localhost:6379/2",
    external_apis={"technical_analysis": "http://localhost:8004/health"},
)
metrics = monitor.get_system_metrics()   # cpu / memory
```

Status levels: `HEALTHY` / `DEGRADED` (some issues, still functional) / `UNHEALTHY` (critical deps down) / `UNKNOWN`.

### Cache/health operations

```bash
# Cache stats + clear (adjust port if your dev setup maps Redis differently)
curl http://localhost:8005/api/internal/cache/stats
redis-cli -h localhost -p 6379 -n 2 ping
redis-cli -h localhost -p 6379 -n 2 FLUSHDB

# Health drill-down
curl http://localhost:8005/health/detailed | jq '.dependencies.postgres'
curl http://localhost:8005/status | jq '.system_metrics'
```

Prometheus: cache hit rate = `rate(cache_hits_total[5m]) / (rate(cache_hits_total[5m]) + rate(cache_misses_total[5m])) * 100`; alert on `cache_hit_rate < 50` for 5m and `health_status == "unhealthy"` for 1m.

Performance targets: cache hit rate >80%; cached health check <50ms; fresh health check <100ms; cache response <5ms. (Measured values in the 2025-era quick-ref met all targets; re-measure before citing.)

Key files: `app/aggregation/signal_cache.py`, `app/monitoring/health.py`, `app/monitoring/metrics.py`, `app/monitoring/alerts.py`, `app/handlers/health.py`; tests in `tests/test_signal_cache.py`, `tests/test_health_monitor.py`, `tests/test_cache_standalone.py`.

## SQZMOM Reference

> Merged from `SQZMOM_DEPLOYMENT_GUIDE.md` + `SQZMOM_QUICK_REFERENCE.md` on 2026-07-30. Phase 21 will bring SQZMOM into the aggregator vote — parameter values below are load-bearing.

### Indicator & strategy parameters (optimized 2025-11)

| Parameter | Value | Notes |
|-----------|-------|-------|
| `bb_length` | 20 | Bollinger Bands period |
| `kc_length` | 20 | Keltner Channel period |
| `min_momentum_threshold` | 0.3 | reduced from 0.5 for more signals |
| `stop_loss_pct` | 1.5% | tighter than default 2.0%; automatic, cannot be disabled |
| `take_profit_pct` | 3.0–3.5% | symbol-specific |
| `position_size_pct` | 1.5–2.5% | symbol-specific |
| `max_positions` | 3 | max exposure 7.5% (3 × 2.5%) |
| `require_squeeze_release` | False | more entry opportunities |
| `require_volume_confirmation` | False | avoid missing signals |

### Symbol whitelist (as configured)

| Symbol | Position size | Min confidence |
|--------|---------------|----------------|
| SOLUSDT | 2.5% | 65% |
| DOGEUSDT | 1.5% | 75% |
| BNBUSDT | 2.0% | 70% |

Explicitly disabled: BTCUSDT, ETHUSDT, XRPUSDT, ADAUSDT (whitelist enforced in code).

**Caveats (2026-07-30):**
- The 2025-11 backtest results that justified this whitelist (SOL +2,706%, DOGE +630%, BNB +330%; disabled symbols "lost >99%") are **history only, not evidence**: all pre-2026-07-28 P&L numbers are measurement-corrupted (broken paper accounting + testnet-polluted candles pre-2026-04-25). Re-backtest on `is_mainnet=true` data before relying on any of these figures.
- DOGEUSDT is in the SQZMOM whitelist but **not** in the validated trading symbols (BTC/ETH/SOL/BNB/ADA as of 2026-05-03) — engine-level position-taking restricts to the validated set; reconcile before Phase 21.

### Endpoints (service-internal)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/strategies/sqzmom/info` | GET | Strategy information |
| `/api/v1/strategies/sqzmom/config` | GET | Current configuration |
| `/api/v1/strategies/sqzmom/signals` | GET | Signals for all enabled symbols |
| `/api/v1/strategies/sqzmom/signal/{symbol}?interval=60` | GET | Single signal |
| `/api/v1/strategies/sqzmom/symbols/{symbol}/config` | GET | Symbol config |
| `/api/v1/strategies/sqzmom/enable[?auto_trading=true]` | POST | Enable (manual-approval or auto) |
| `/api/v1/strategies/sqzmom/disable` | POST | Disable |
| `/api/v1/strategies/sqzmom/trade/{symbol}?force=true` | POST | Manual trade execution |

Signal payload: `action`, `confidence`, `entry_price`, `stop_loss`, `take_profit`, `momentum`, `squeeze_state` (`ON|OFF|TRANSITIONAL`), `momentum_color`, `reason`.

### Files & tests

- Config: `app/strategies/sqzmom_config.py` (edit `symbol_config` dict, then restart service)
- Integration: `app/strategies/sqzmom_strategy_integration.py`
- Verification: `./verify_sqzmom_deployment.sh`
- Tests: `pytest tests/test_sqzmom_strategy.py -v`, `pytest tests/integration/test_sqzmom_integration.py -v`
- Indicator math lives in technical-analysis: `GET :8004/api/v1/indicators/sqzmom/{symbol}`

Adding new symbols: only after ≥6 months of clean-data backtesting (positive returns, Sharpe > 2.0) plus 2+ weeks of paper trading, and only via `enabled_symbols` + symbol-specific params — then manual-approval mode first.

## Installation

Prerequisites: Python 3.12+, Technical Analysis Service on 8004, Bybit Connector on 8001 (optional for paper trading).

```bash
pip install -r requirements.txt
PYTHONPATH=. python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8005 --reload
```

Or via the canonical compose file from repo root:

```bash
docker compose -f docker-compose.unified.yml up -d trading-engine
```

## How It Works

### Signal Aggregation

1. Parallel indicator fetches from Technical Analysis Service
2. Normalize BUY/SELL/HOLD to scores (−1 to +1), weight by confidence
3. Aggregated score: ≥ +0.3 → BUY; ≤ −0.3 → SELL; else HOLD
4. Validate: consensus ≥ `MIN_CONSENSUS_INDICATORS` **directional** votes and confidence ≥ 0.6, else override to HOLD

### Position Sizing & Stops

```python
max_value = account_balance * (per_trade_cap)          # 10% paper / 2% LIVE (clamped)
quantity  = max_value / entry_price
# risk-based sizing when stop-loss provided; the more conservative wins
stop_loss = entry_price * (1 ∓ DEFAULT_STOP_LOSS_PCT / 100)   # − LONG, + SHORT
```

Daily loss: trading halts automatically when `daily_pnl < −(initial_balance * MAX_DAILY_LOSS_PCT / 100)`; the counter rolls at UTC midnight.

### Paper Trading

Simulated fills at current mainnet market price with 0.1% commission, full P&L tracking, and the same performance metrics as live. Accounting was rewritten 2026-07-28 (correct SHORT P&L sign, `reduce_only` honored, partial closes, scale-in) — see `wiki/concepts/Paper-Trading-Internals.md`. **Do not compare P&L across the 2026-07-28 boundary.**

## Safety Protocols

### Before Going Live

Follow the **Pre-LIVE Operator Checklist in `/RUNBOOK.md`** (`python3 scripts/preflight_live.py --json`): per-trade cap restored to ≤2%, `PAPER_TRADING_MODE=false`, `TRADING_MODE=LIVE`, `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`, `EMERGENCY_STOP` absent, DSR evidence if ML enabled. Plus: 2+ weeks paper trading, performance review on post-2026-07-28 data only, small-capital first.

### Emergency Procedures

- **Daily loss limit hit**: trading halts automatically; positions remain open; manual review required.
- **Manual stop**: `touch safety/EMERGENCY_STOP` (halt within one auto-trader tick) or `POST /api/v1/trading/stop` (service) / `POST /api/portfolio/emergency-stop` (gateway, admin-guarded).
- **Resume after file-halt**: `rm safety/EMERGENCY_STOP` **then** `POST /api/v1/trading/start` — a file-triggered halt does not auto-restart.

## Testing

```bash
cd services/trading-engine
pytest tests/ -v --cov=app
bash test_all.sh
```

## Monitoring

Logs: `tail -f logs/service.log` (key messages: `✓ Position created`, `✓ Position closed`, `🛑 TRADING HALTED`, `Signal aggregated`). Full tooling (signal monitor, log analyzer, checklists): see `MONITORING_GUIDE.md`.

## Troubleshooting

| Problem | Check |
|---------|-------|
| Service won't start | `export PYTHONPATH=.`; deps installed; PostgreSQL (5433) + Redis (6379) up; `.env` complete; `tail logs/service.log` |
| TA connection failed | `curl http://localhost:8004/health`; `TECHNICAL_ANALYSIS_URL` in `.env` |
| Trades not recorded | DB connection established; paper portfolio exists (created at startup) |
| Signals never meet requirements | lower `MIN_SIGNAL_CONFIDENCE` / `MIN_CONSENSUS_INDICATORS`; market may be ranging |
| Bybit connection failing | connector health on 8001; API credentials; note current state is **mainnet prices** (`BYBIT_TESTNET=false` since 2026-04-25 — older docs saying "testnet only" are historical) |

## Support

1. Check logs: `logs/service.log`
2. Verify all services are running (`bash health_check.sh` at repo root)
3. Live API docs: http://localhost:8005/docs (service) / http://localhost:8000/openapi.json (gateway)
4. Deeper docs: `wiki/modules/trading-engine.md`, `/RUNBOOK.md` (failure triage), `MONITORING_GUIDE.md`
