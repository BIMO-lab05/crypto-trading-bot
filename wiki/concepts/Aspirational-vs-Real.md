---
type: concept
status: active
tags: [concept, fiction, debt]
created: 2026-05-05
updated: 2026-05-05
---

# Aspirational vs Real

Catalog of features described in docs / configured / imported but **not actually wired**. Discovered by Stage 1 code-mapping (2026-05-05).

## Libraries imported but never used

| Library | Service | What it claims | Reality |
|---|---|---|---|
| `pybit==5.6.2` | bybit-connector | Official Bybit Python SDK | Service rolls own REST + V5 HMAC over httpx; pybit never imported |
| `websockets==12.0` | bybit-connector | WS client for real-time data | Zero `websockets.connect`; no WS endpoint; "REST + WS wrapper" half-aspirational |
| `aio_pika`, `pika` | trading-engine, others | RabbitMQ async client | trading-engine has one optional health probe; no orchestration use |
| `asyncpg`, `sqlalchemy`, `aioredis`, `fastapi-cache2` | api-gateway | DB + cache | Never imported; user store = in-process `dict` |
| `redis` | technical-analysis | Indicator cache | Settings + TTL knobs, no client; recompute per request |

## Configured env / settings but unread

- **All 11 services**: `RABBITMQ_HOST`, `RABBITMQ_URL` injected by compose, unused
- **technical-analysis**: explicit audit comment in `app/config.py:105-115` admits unused
- **api-gateway**: `database_url`, `redis_url` (only slowapi consumes the latter)
- **bybit-connector**: circuit-breaker thresholds env vars dead (hardcoded in constructor)
- **risk-metrics-service**: `database_url`, `market_data_url` (never called)
- **ml-prediction-service**: `market_data_url` default points to wrong port (8003 instead of 8002)
- **sentiment-analysis-service**: `REDDIT_CLIENT_ID/_SECRET` declared, no `reddit_fetcher.py`
- **trading-engine**: `portfolio_manager_url` defaults to `:8006` — wrong port

## Files parked / unused

- `services/bybit-connector/app/config_vault.py` (485 lines) — Vault-backed Settings, never imported
- `services/risk-metrics-service/{backtesting,cpcv,sharpe_metrics,backtest_models}.py` — ~1260 LOC dead
- `services/ml-prediction-service/app/main.py.bak` — references deleted LSTMPricePredictor
- `services/notification-service/app/main.py.bak` — pre-cleanup snapshot
- `services/sentiment-analysis-service/app/main.py.bak` — pre-cleanup snapshot
- `services/ml-prediction-service/app/handlers/{orderbook,sentiment,regime}.py` — `APIRouter`s defined, imported, never `include_router`'d → ~16 endpoints unreachable

## Routes defined but never mounted

- ml-prediction-service: 3 router files (~16 endpoints) imported but not included
- trading-engine: 2 routers (orchestration, performance_dashboard) were unmounted dead code until April–May 2026 (handlers existed; `app.include_router(...)` line missing). Mounted in commits 2026-04-29 and 2026-05-01.

## Logic stubs

- `risk-metrics-service`: `historical_returns` never populated → every Sharpe/Sortino/Calmar/VaR call falls through to insufficient-data fallback. Frontend dashboards display fictional numbers.
- `risk-metrics-service`: `PUT /config/limits` returns 200 but doesn't persist
- `ml-prediction-service`: `/predict/volatility` is a pandas heuristic, not ML
- `trading-engine`: paper trading executes deterministically at the requested price — slippage manager exists in `trading_enhancements/slippage_manager.py` but **not invoked inside paper engine**
- `notification-service`: `dashboard` channel enum value stored but never delivered
- `ml-retraining-service`: acceptance-gate plumbing exists (`retrain_min_dsr`, `retrain_min_r2_returns`, `retrain_min_dir_acc`) but **all default `None`** → CLAUDE.md's `DSR > 0.95` gate is **not enforced**. Active gates = V0-era R²≥0.85 + loss<0.05.

## Infra fictions

- **ml-retraining-service is NOT in any docker-compose file** (unified, headless, prod, default). Scheduler never fires in canonical stack — explains 4-month staleness.
- GH Actions workflow `.github/workflows/ml-retrain.yml` references service that doesn't exist in `headless` and passes `--once` flag main.py never parses.
- Port 8009 collision: ml-retraining-service vs risk-metrics-service.

## Cosmetic LSTM residue (ADR-001 incomplete)

- `ml-prediction-service`: `/supported-models` lists LSTM in some doc paths
- Various endpoint docstrings reference LSTM
- `main.py.bak` references deleted `LSTMPricePredictor` class

## Related

- [[HTTP-Service-Mesh]]
- [[Message-Queue-Topics]]
- [[../decisions/ADR-001-LSTM-removed]]
- [[../decisions/ADR-012-http-not-events]]
