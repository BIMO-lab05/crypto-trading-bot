---
type: module
path: "services/ml-prediction-service/"
status: active
language: python
port: 8007
purpose: "Standalone GRU price-prediction + ensemble signal HTTP service"
maintainer: ""
linked_issues: []
depends_on: [market-data-service, technical-analysis, redis]
used_by: [api-gateway, trading-engine]
tags: [module, service, ml, gru, inference]
created: 2026-05-05
updated: 2026-07-29
---

# ml-prediction-service

**Port:** `8007`
**Path:** `services/ml-prediction-service/`
**Purpose:** GRU-only price prediction (16 symbols, 60m timeframe) + ensemble blended signal endpoint. HTTP request/response, no RabbitMQ, no SQL DB.

See raw audit: `wiki/.raw/agent-reports/ml-prediction-service.md`.

## Overview

FastAPI app. Loads 16 Keras `.keras` GRU models at startup (~20 MB resident) into an in-process `Dict[symbol_interval, GRUPricePredictor]`. Inference goes: market-data klines → feature filter (OHLCV only) → scaler → GRU `.predict()` → Redis cache (DB 2, TTL 300s) → JSON.

The `EnsemblePredictor` blends TA (47%) + ML (35%) + Multi-Timeframe (18%) — sentiment leg removed 2026-05-02 (see [[../decisions/ADR-001-LSTM-removed]] sibling decisions). Self-referential: ensemble calls back into `localhost:8007` for the ML leg.

LSTM removed late 2025 (ADR-001). Factory rejects LSTM. `POST /api/v1/models/train` returns HTTP 410. Some docstrings + `/api/v1/supported-models` still mention LSTM cosmetically — see Gotchas in raw report.

## Key endpoints

**Predictions**
- `GET /api/v1/predict/price/{symbol}` — N-step GRU price forecast
- `GET /api/v1/predict/trend/{symbol}` — BULLISH / BEARISH / NEUTRAL
- `GET /api/v1/predict/volatility/{symbol}` — heuristic rolling-std (not GARCH despite docstring)
- `GET /api/v1/predict/ensemble/{symbol}` — TA 47% + ML 35% + MultiTF 18% blended signal
- `GET /api/v1/predict/enhanced/{symbol}` — sklearn ensemble (RF/GB/LR), trains on the fly

**Model management**
- `GET /api/v1/models/loaded` — disk + memory inventory + preload stats
- `POST /api/v1/models/preload?symbols=&force=` — manual reload after retrain
- `POST /api/v1/models/train-gru/{symbol}` — synchronous GRU train
- `POST /api/v1/models/train` — **410 Gone** (LSTM training removed)
- `GET /api/v1/models/compare/{symbol}` — legacy LSTM-vs-GRU shape (LSTM slot now `None`)

**Cache**
- `GET /api/v1/cache/stats`, `DELETE /api/v1/cache/clear`, `DELETE /api/v1/cache/{symbol}`

Plus `/health`, `/ready`, `/metrics`. ~14 distinct non-health routes.

## Models served

16 GRU models (Keras v3 `.keras` + scalers `.pkl` + metadata `.json`), all `60m` timeframe:

```
ADAUSDT  APTUSDT  ARBUSDT  AVAXUSDT  BNBUSDT  BTCUSDT
DOGEUSDT DOTUSDT  ETHUSDT  LINKUSDT  LTCUSDT  OPUSDT
POLUSDT  SOLUSDT  SUIUSDT  XRPUSDT
```

Trained 2025-12-09/10. Stale by ~150 days as of 2026-05-05. Every model returns `needs_retraining=True` against the 7-day threshold.

## Feature flag gating

`ENABLE_ML_PREDICTIONS` is **not read by this service**. The flag lives on the [[trading-engine|trading-engine]] consumer side (compose default `false`). When false: signal-aggregator + auto-trader skip the ML leg, but `/api/ml/...` via [[api-gateway|gateway]] still returns predictions. See [[../concepts/Feature-Flags]].

**Container gated off by default (verified 2026-07-29).** The `ml-prediction` service IS defined in `docker-compose.unified.yml` (line ~733) but sits behind an opt-in Compose **`ml` profile** (`profiles:` at line ~773), so a plain `docker compose up` does not start it — the RAM-constrained default runs the core trading flow without it. `trading-engine.depends_on` excludes it; runtime fan-out calls get connection-refused and the aggregator downgrades to non-ML signals. Bring it up with `docker compose --profile ml up -d`. (The audit's "8/9 services HTTP 200, ml-prediction intentionally absent" reflects this profile gating.)

## Internal deps

- [[market-data-service]] — historical klines for inference + training (`MARKET_DATA_URL`); default in config wrongly points at port 8003 (portfolio), env override required
- [[technical-analysis]] — TA signals for ensemble TA leg (`TECHNICAL_ANALYSIS_URL`)
- Redis DB 2 — prediction cache (TTL 300s, prefix `ml:prediction:`)
- Disk model store: `MODELS_DIR` or `services/ml-prediction-service/models/`. Sibling `trained_models/` is a stale duplicate — runtime ignores it.
- [[ml-retraining-service]] — writes new `.keras` artefacts into shared `models/` volume; this service does **not** auto-reload, must be restarted or hit `POST /api/v1/models/preload?force=true`

## Used by

- [[api-gateway]] — proxies `/api/ml/predict/{price,trend,volatility,signal}/{symbol}`, `/api/ml/models*`, `/api/ml/models/compare/{symbol}` to `ml_prediction_url`
- [[trading-engine]] (signal-aggregator + auto-trader) — consumes ML leg when `enable_ml_predictions=true`

## RabbitMQ

None. Pure HTTP request/response.

## DB tables

None. Service does not connect to PostgreSQL or TimescaleDB. Only state is Redis cache (DB 2) + on-disk Keras artefacts. Predictions are not persisted; metrics live in Prometheus.

## Status / quality

- Models 5 months stale; predictions chance-level on log-returns post-leakage fix (commit `c56765c`).
- Re-enable blocked on rebuild + DSR > 0.95 acceptance gate.
- **NaN/inf guards added (2026-07-29, `ml_models/gru_model.py:594–623`):** inference is refused on non-finite scaled input and non-finite model output (no more poisoned predictions), and the `price_change_pct` divisor (`current_price`) is guarded against divide-by-zero.
- **`/ready` now reflects real model availability** (`main.py:512`): `models_loaded = any(p.model is not None ...)`. A missing model file leaves `predictor.model = None`, so the old bare `len(gru_predictors)` overreported "models loaded" even when nothing usable was resident.
- Three handler routers (`orderbook`, `sentiment`, `regime`) defined but never `include_router`'d — ~16 endpoints of dead code.
- `app/main.py.bak` retains references to deleted `LSTMPricePredictor`.

See [[../concepts/ML-Status]] for full lifecycle context.

## Related

- [[../concepts/ML-Status]]
- [[../concepts/Feature-Flags]]
- [[../decisions/ADR-001-LSTM-removed]]
- [[../flows/Signal-Pipeline]]
- [[technical-analysis]]
- [[ml-retraining-service]]
- [[market-data-service]]
- [[api-gateway]]

## Corrections 2026-07-29

Reflects the 2026-07-29 production audit (verified in source):

- **NaN/inf guards** on ML predict path (`ml_models/gru_model.py:594–623`) — rejects non-finite input/output, guards the `current_price` divisor.
- **`/ready` reflects real model availability** (`main.py:512`) — was overreporting when model files were missing.
- **Container gated off by default**: defined in `docker-compose.unified.yml` but behind an opt-in `ml` Compose profile; not started by a plain `docker compose up`. See *Feature flag gating*.
