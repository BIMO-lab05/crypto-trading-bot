---
type: module
path: "services/technical-analysis/"
status: active
language: python
port: 8004
purpose: "TA indicators + signal aggregator (no ML inference here despite CLAUDE.md tagline)"
maintainer: ""
last_updated: 2026-05-05
linked_issues: []
depends_on: [market-data-service]
used_by: [trading-engine, api-gateway]
tags: [module, service, indicators, signals]
created: 2026-05-05
updated: 2026-05-05
---

# technical-analysis

**Port:** `8004`
**Path:** `services/technical-analysis/`
**Purpose:** Technical indicators (13) + multi-indicator signal aggregator + multi-timeframe consensus.

## Overview

FastAPI service that fetches OHLCV candles from [[market-data-service]] over HTTP, computes TA indicators on-demand with pandas/numpy, and exposes both raw indicator endpoints and a weighted aggregator. Stateless: no DB, no Redis client, no RabbitMQ publisher (RabbitMQ + Redis settings exist in `config.py` but are dead config knobs — see audit comment at `app/config.py:105-115`).

Despite the CLAUDE.md tagline ("TA indicators + GRU inference + signal aggregator"), **GRU inference does not run here** — it lives in [[ml-prediction-service]]. See [[../concepts/ML-Status]] and [[../concepts/Feature-Flags]].

## Endpoints

Routes use `/api/v1/` prefix (legacy; gateway proxies as-is). Health: `/health`, `/ready`. Prometheus: `/metrics`.

Indicators (`/api/v1/indicators/{name}/{symbol}`): `rsi`, `macd`, `bollinger`, `sma`, `ema`, `trend`, `volume`, `atr`, `adx`, `stochastic`, `rsi-divergence`, `ichimoku`, `sqzmom`, `sqzmom-enhanced`, `sqzmom/{symbol}/backtest`.

Strategy: `GET /api/v1/strategies/sqzmom/signal/{symbol}` — full BUY/SELL/HOLD with stop/take-profit.

Aggregation: `GET /api/v1/indicators/signal/{symbol}` (RSI + MACD + trend weighted vote), `GET /api/v1/analysis/multi-timeframe/{symbol}` (parallel analysis across `1,5,15,60,240,1440` min, alignment score, consensus).

## Signal aggregator

Pure TA: **RSI + MACD + trend filter only** (`app/handlers/analysis.py::get_aggregated_signal`). Each indicator's `generate_signal()` produces a `(label, confidence)` tuple; the aggregator does a weighted vote using each indicator's *own derived* confidence (fixed in commit `2d2c524`, MACD branch unwedged in `af7fdd9`).

No sentiment leg, no ML leg in this aggregator — by file evidence, never had one. The sentiment removal commits (`c346483`, `acae081`, `fe941cf`, `c171bb0`) referenced in [[../decisions/ADR-001-LSTM-removed]] applied to the [[trading-engine]] signal pipeline, not here. See [[../flows/Signal-Pipeline]].

## Indicators

13 indicators in `app/indicators/`: `rsi`, `macd`, `bollinger_bands`, `moving_averages` (SMA+EMA), `trend_filter`, `volume_confirmation`, `atr`, `adx`, `stochastic`, `rsi_divergence`, `ichimoku`, `squeeze_momentum`, `sqzmom_enhanced`. Strategy wrapper in `app/strategies/squeeze_momentum_strategy.py`.

## GRU integration

**None in this service.** `grep -rn "gru\|ml_predict\|ENABLE_ML" services/technical-analysis/app/` returns zero hits. ML inference is the responsibility of [[ml-prediction-service]]. ML feature gating (`ENABLE_ML_PREDICTIONS=false`) is read by consumers, not here.

## Dependencies

- **Outbound**: [[market-data-service]] only — HTTP `GET /api/v1/klines/{symbol}` via `app/fetcher.py::MarketDataFetcher`. URL from `MARKET_DATA_URL` env (default `http://localhost:8002` post commit `4d46e17`; was wrongly `8003`).
- **Configured-but-unused**: Redis (caching), RabbitMQ (signal publishing). See `app/config.py:105-115` audit note.

## Used by

- [[trading-engine]] — consumes ADX (market-regime classifier), ATR (dynamic stops), stochastic, multi-timeframe signal. References: `app/aggregation/market_regime.py`, `app/phase1_metrics.py`, `app/multi_timeframe.py`.
- [[api-gateway]] — proxies as `/api/analysis/*`.

## Messaging

**No RabbitMQ usage.** Despite RabbitMQ settings + `enable_signal_publishing` flag in config, no `aio_pika` import, no publisher, no exchange declaration. Downstream is HTTP-only. See [[../concepts/Message-Queue-Topics]] for what is and isn't on the bus.

## Persistence

**None.** No DB connection, no migrations, no cache. Every request recomputes from candles. Cache TTL knobs in config (`cache_ttl_indicator=300`, `cache_ttl_signal=60`) unused.

## Gotchas

- **Default mismatch**: `config.py` MACD defaults are 5/35/5 (Kang 2021), but route Query defaults are 8/17/9. Aggregator uses settings (5/35/5); raw `/macd/{symbol}` route uses 8/17/9. Same conflict on Bollinger std (config 2.5, route 2.0).
- **MACD signal key (`af7fdd9`)**: `MACDCalculator.calculate()` returns `{macd_line, signal_line, histogram}` — no `signal` key. Old code calling `macd.get('signal')` always returned `None`, silently dropping MACD votes. Use `MACDCalculator.generate_signal(macd)` instead.
- **Enhanced SQZMOM columns (`fc345e8`)**: indicator writes `sqz_*` columns; `indicator_service` was reading non-prefixed names → silent zero defaults across every response.
- **Port-default fix (`4d46e17`)**: `market_data_url` default was `8003`; broke local pytest, masked in compose by `MARKET_DATA_URL` override.
- **RabbitMQ + Redis dead config**: env-validated, never connected.

## Key files

- `app/main.py` — FastAPI app + Prometheus metrics + 18 routes
- `app/config.py` — settings, audit annotations
- `app/fetcher.py` — market-data-service HTTP client
- `app/handlers/analysis.py` — aggregator + multi-timeframe
- `app/handlers/sqzmom.py` — SQZMOM raw + strategy handlers
- `app/services/indicator_service.py` — shared compute layer
- `app/indicators/*.py` — 13 indicator implementations
- `app/strategies/squeeze_momentum_strategy.py` — SQZMOM entry/exit rules

## Related

- [[../flows/Signal-Pipeline]]
- [[../concepts/ML-Status]]
- [[../concepts/Feature-Flags]]
- [[../concepts/Message-Queue-Topics]]
- [[../decisions/ADR-001-LSTM-removed]]
- [[market-data-service]]
- [[ml-prediction-service]]
- [[trading-engine]]
- Raw report: `[[../.raw/agent-reports/technical-analysis|agent report 2026-05-05]]`
