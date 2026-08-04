---
service: technical-analysis
port: 8004
path: services/technical-analysis/
report_date: 2026-05-05
agent: claude-opus-4-7
---

# technical-analysis — raw agent report

## Endpoints

All routes carry the `/api/v1/` prefix despite the gateway-level convention being prefix-less; the gateway proxies these as-is. Defined in `services/technical-analysis/app/main.py`.

Indicator endpoints:
- `GET /api/v1/indicators/rsi/{symbol}` — period default `9` (crypto-tuned)
- `GET /api/v1/indicators/macd/{symbol}` — fast/slow/signal default `8/17/9` at the route, but `default_macd_*` in `config.py` is `5/35/5` (Kang 2021); discrepancy below
- `GET /api/v1/indicators/bollinger/{symbol}` — period 20, std 2.0 (config default 2.5)
- `GET /api/v1/indicators/sma/{symbol}` and `/ema/{symbol}` — period 20
- `GET /api/v1/indicators/trend/{symbol}` — dual-EMA 50/200 trend filter
- `GET /api/v1/indicators/volume/{symbol}` — volume vs N-period avg, `breakout` or `continuation` mode
- `GET /api/v1/indicators/atr/{symbol}` — ATR + auto stop/take-profit at 2x/4x
- `GET /api/v1/indicators/adx/{symbol}` — ADX + market regime classification
- `GET /api/v1/indicators/stochastic/{symbol}` — %K/%D
- `GET /api/v1/indicators/rsi-divergence/{symbol}` — bullish/bearish/hidden divergences
- `GET /api/v1/indicators/ichimoku/{symbol}` — 9/26/52 cloud
- `GET /api/v1/indicators/sqzmom-enhanced/{symbol}` — squeeze firing + LR momentum
- `GET /api/v1/indicators/sqzmom/{symbol}` — LazyBear SQZMOM
- `GET /api/v1/indicators/sqzmom/{symbol}/backtest` — historical SQZMOM data

Strategy:
- `GET /api/v1/strategies/sqzmom/signal/{symbol}` — full BUY/SELL/HOLD with entry, stop, TP, confidence

Analysis:
- `GET /api/v1/indicators/signal/{symbol}` — aggregated TA signal (RSI + MACD + trend)
- `GET /api/v1/analysis/multi-timeframe/{symbol}` — parallel analysis across `1,5,15,60,240,1440` minutes; returns alignment score and consensus

Other:
- `GET /metrics` — Prometheus
- `GET /` — service info

## Indicators implemented

Files in `services/technical-analysis/app/indicators/`:
- `rsi.py` — `RSICalculator`
- `macd.py` — `MACDCalculator` with `generate_signal()` returning `(SignalType, confidence)`
- `bollinger_bands.py`
- `moving_averages.py` — SMA + EMA
- `trend_filter.py` — EMA-50/EMA-200 dual filter
- `volume_confirmation.py`
- `atr.py`
- `adx.py`
- `stochastic.py`
- `rsi_divergence.py`
- `ichimoku.py`
- `squeeze_momentum.py` — LazyBear SQZMOM
- `sqzmom_enhanced.py` — `EnhancedSqueezeMomentum`, writes `sqz_momentum`, `sqz_color`, `sqz_signal`, `sqz_confidence` columns

Strategies in `app/strategies/`:
- `squeeze_momentum_strategy.py` — `SqueezeMomentumStrategy` (entry/exit rules wrapping SQZMOM)

## Signal aggregator

`app/handlers/analysis.py::get_aggregated_signal` is the only TA aggregator. Logic:
1. Fetches 200 klines via `MarketDataFetcher.get_klines_as_dataframe`.
2. Computes RSI, MACD, trend filter.
3. Calls `RSICalculator.generate_signal()` and `MACDCalculator.generate_signal()` to get both label and **derived confidence per indicator** (commit `2d2c524`, then `af7fdd9` rewired MACD which was previously dead code).
4. Builds list of `(signal, confidence)` tuples; weighted vote across BUY/SELL/HOLD; final = argmax of `signal_weights`, normalised confidence.

Three legs only: **RSI + MACD + trend**. No sentiment, no ML, no SQZMOM in the aggregator. Sentiment leg is *absent from this code* — there is no removal scar to clean up because it apparently never wired into the aggregator in the first place. CLAUDE.md commits (`c346483`, `acae081`, `fe941cf`, `c171bb0`) presumably touched the trading-engine signal pipeline, not this aggregator.

`get_multi_timeframe_analysis` is a parallel aggregator across timeframes; same three legs per timeframe, then majority vote → consensus.

## GRU integration

**None.** Zero references to GRU, ML, ml-prediction-service, or `ENABLE_ML_PREDICTIONS` anywhere under `services/technical-analysis/app/`. The CLAUDE.md description "TA indicators + GRU inference + signal aggregator" is wrong for this service: GRU inference lives in `ml-prediction-service` (port 8007). This service does pure pandas/numpy math, no model loading.

## Internal deps

- **Outbound**: `market-data-service` only (HTTP). `app/fetcher.py` reads `settings.market_data_url` (default `http://localhost:8002` after commit `4d46e17` — was wrongly `8003` before; Docker masked this via `MARKET_DATA_URL` env var). Hits `GET /api/v1/klines/{symbol}` and `/health`.
- **Inbound**: `trading-engine` (port 8005) consumes via `TECHNICAL_ANALYSIS_URL=http://technical-analysis:8004`. References:
  - `services/trading-engine/app/multi_timeframe.py:63`
  - `services/trading-engine/app/aggregation/market_regime.py` (fetches ADX)
  - `services/trading-engine/app/phase1_metrics.py` (fetches ATR/stochastic)

No outbound to ml-prediction-service.

## Used by

- **trading-engine** — consumes `/api/v1/indicators/adx/{symbol}` for market regime, ATR for stop/take-profit, stochastic, multi-timeframe signal. Compose env: `TECHNICAL_ANALYSIS_URL=http://technical-analysis:8004`.
- **api-gateway** — proxies under `/api/analysis/*` domain.

## RabbitMQ

**Configured but unused.** `app/config.py` defines `rabbitmq_*` settings and `enable_signal_publishing: bool = Field(default=False)`. The author left an explicit comment (lines 105-115):

> NOT YET IMPLEMENTED — kept as a config knob so .env files don't fail validation, but no code path actually publishes signals to RabbitMQ today. Default flipped from `True` (which was a lie) to `False` on 2026-04-29 (audit finding).

`grep -rn "aio_pika\|publish" app/` returns zero hits in code (only the config comment). No `analysis.signal.{symbol}` topic published. Trading-engine consumes via HTTP only.

## DB tables

**None.** No SQLAlchemy, no asyncpg, no psycopg, no TimescaleDB writes. Indicators are computed on-demand from DataFrame fetched per request. Config defines `cache_ttl_indicator: 300` and `cache_ttl_signal: 60` — also unused (no Redis client constructed).

## Key files

1. `services/technical-analysis/app/main.py` — FastAPI app, 18 routes
2. `services/technical-analysis/app/config.py` — settings + audit comments
3. `services/technical-analysis/app/fetcher.py` — `MarketDataFetcher` (httpx)
4. `services/technical-analysis/app/handlers/analysis.py` — aggregator + multi-timeframe
5. `services/technical-analysis/app/handlers/sqzmom.py` — SQZMOM strategy handlers
6. `services/technical-analysis/app/handlers/indicators.py` — basic indicator handlers
7. `services/technical-analysis/app/handlers/advanced.py` — advanced indicator handlers
8. `services/technical-analysis/app/services/indicator_service.py` — shared compute layer
9. `services/technical-analysis/app/indicators/macd.py` — `MACDCalculator.generate_signal`
10. `services/technical-analysis/app/indicators/sqzmom_enhanced.py` — enhanced SQZMOM (sqz_* columns)

## Gotchas

- **Port-default fix (`4d46e17`)**: `market_data_url` default was `http://localhost:8003` (portfolio-manager port). Bites local pytest / `python -m app.main` runs without `.env`. Compose was unaffected via env override.
- **MACD signal wiring (`af7fdd9`)**: `MACDCalculator.calculate()` returns `{macd_line, signal_line, histogram}` — *no `signal` key*. Earlier code did `macd.get('signal')` which always returned `None`, silently dropping the MACD vote from both `get_aggregated_signal` and per-timeframe consensus. Fix: call `MACDCalculator.generate_signal(macd)` to derive label+confidence.
- **Enhanced SQZMOM column-name fix (`fc345e8`)**: `EnhancedSqueezeMomentum.calculate()` writes `sqz_momentum`, `sqz_color`, `sqz_signal`, `sqz_confidence`; `indicator_service` was reading `momentum`, `momentum_color`, `signal`, `confidence`. Every response defaulted to `momentum=0.0`, `color='gray'`, `signal='HOLD'`, `confidence=0.5`.
- **Confidence chain (`2d2c524`)**: aggregator previously discarded each indicator's derived confidence and used hardcoded weights (RSI 0.7, MACD 0.6, trend 0.8). Now propagates real confidence — Site 1 of a multi-site fix.
- **Default-parameter inconsistency**: `config.py` sets `default_macd_fast=5, default_macd_slow=35, default_macd_signal=5` (Kang 2021), but the FastAPI route `/macd/{symbol}` declares `fast=8, slow=17, signal=9` as Query defaults. The aggregator (`handlers/analysis.py`) uses `settings.default_macd_*` (so 5/35/5), the public MACD endpoint uses 8/17/9. Same disagreement on Bollinger std: config 2.5, route 2.0.
- **Config knobs that don't do anything yet**: Redis (host/port/db/url) and RabbitMQ (host/user/pass/vhost) are wired into `Settings` but no client is instantiated. Cache TTLs unused.
- **Two SQZMOM handler functions** in `main.py` route table — `sqzmom_endpoint` (raw) and `sqzmom_strategy_endpoint` (with stop/TP rules). Easy to confuse downstream.

## Contradictions vs CLAUDE.md

1. **CLAUDE.md says "TA indicators + GRU inference + signal aggregator"**. False for *this* service. GRU inference lives in `ml-prediction-service` (8007). technical-analysis has zero ML code paths.
2. **`ENABLE_ML_PREDICTIONS=false` gating**: CLAUDE.md says verify gating "in code". Cannot verify here — flag is not read by technical-analysis. Gating must live in trading-engine (consumer side) or ml-prediction-service.
3. **Sentiment leg removal commits** (`c346483`, `acae081`, `fe941cf`, `c171bb0`): no sentiment ever existed in this aggregator. Removal scar lives elsewhere (likely trading-engine signal pipeline). The aggregator here has always been TA-only by file evidence.
4. **RabbitMQ topic `analysis.signal.{symbol}`**: not published. Trading-engine consumes signals via HTTP, not message bus.
5. **Indicator cache in TimescaleDB**: not present. No DB writes, indicators computed on every request.
