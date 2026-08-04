---
type: agent-report
service: ml-prediction-service
generated: 2026-05-05
source: services/ml-prediction-service/app/main.py + handlers/* + config.py + models/
---

# ml-prediction-service — raw report

Port `8007`. FastAPI app, lifespan-managed, GRU-only inference + ensemble aggregator. Houses ML training endpoints (GRU only), Redis prediction cache (DB 2), and Prometheus metrics.

## Endpoints

All defined in `app/main.py` directly via `@app.get/@app.post/@app.delete`. The handler routers in `app/handlers/__init__.py` (orderbook, sentiment, regime) are **imported but never `include_router`'d** — those code paths are dead at HTTP level (see Gotchas).

Excluding `/health`, `/ready`, `/metrics`:

**Predictions**
- `GET /api/v1/predict/price/{symbol}` — N-step GRU price forecast; cache-aware
- `GET /api/v1/predict/trend/{symbol}` — BULLISH/BEARISH/NEUTRAL classifier (derived from price pred)
- `GET /api/v1/predict/volatility/{symbol}` — heuristic 1h/4h/24h vol forecast (rolling std, **not** GARCH despite docstring)
- `GET /api/v1/predict/ensemble/{symbol}` — TA(47%)+ML(35%)+MultiTF(18%) blend via `EnsemblePredictor`
- `GET /api/v1/predict/enhanced/{symbol}` — `EnhancedEnsemblePredictor` (sklearn ensemble RF/GB/LR), trains on the fly if no serialized model present

**Model management**
- `GET /api/v1/models` — list loaded GRU models in memory
- `GET /api/v1/models/{symbol}` — `ModelInfo` (R^2, MAE, RMSE, last_trained, needs_retraining)
- `GET /api/v1/models/loaded` — comprehensive: available on disk, loaded in memory, preload stats, configured symbols
- `POST /api/v1/models/preload` — manually load symbols (`?symbols=...&force=true`)
- `POST /api/v1/models/train` — **HTTP 410 gone** (LSTM training removed; redirect to GRU endpoint)
- `POST /api/v1/models/train-gru/{symbol}` — synchronous GRU train
- `GET /api/v1/models/compare/{symbol}` — legacy LSTM-vs-GRU compare; `lstm_predictor` is now `None` so always returns GRU-only
- `GET /api/v1/supported-models` — descriptive list (still advertises both LSTM + GRU types)

**Cache**
- `GET /api/v1/cache/stats`
- `DELETE /api/v1/cache/clear`
- `DELETE /api/v1/cache/{symbol}`

Total non-health routes: **~14 distinct paths**.

## Models served

CLAUDE.md asserts 16 GRU models. Verified: `services/ml-prediction-service/models/` contains exactly **16** files matching `*_60m_gru.keras`:

```
ADAUSDT, APTUSDT, ARBUSDT, AVAXUSDT, BNBUSDT, BTCUSDT,
DOGEUSDT, DOTUSDT, ETHUSDT, LINKUSDT, LTCUSDT, OPUSDT,
POLUSDT, SOLUSDT, SUIUSDT, XRPUSDT
```

This matches `ALL_GRU_SYMBOLS` in `app/config.py` exactly. Format = Keras v3 native (`.keras` zip), with sidecars `*_60m_gru_metadata.json` + `*_60m_gru_scalers` (sklearn StandardScaler, joblib-style serialization). No SavedModel / no ONNX. No LSTM `.keras` files present (`ls models/ | grep -i lstm` empty).

A duplicate copy exists under `services/ml-prediction-service/trained_models/` (subset, ~legacy staging). The service reads from `models_dir` = `MODELS_DIR` env or `<service_root>/models/`.

`PRIORITY_SYMBOLS` (BNB, SOL, ADA, ARB, OP, POL, SUI) — used when `PRELOAD_PRIORITY_ONLY=true`.

## Inference path

- `GRUPricePredictor(symbol, interval)` instantiated lazily via `get_gru_predictor()`; cached in module-level `gru_predictors: Dict[key, GRUPricePredictor]`. Constructor loads model + scalers from disk by filename convention.
- Single-symbol inference: `await predictor.predict(df)` where `df` is OHLCV from market-data (cols filtered to `[timestamp,open,high,low,close,volume]` to avoid feature mismatch — explicit fix in `fetch_historical_data`).
- Lifespan startup calls `preload_gru_models()` if `PRELOAD_MODELS=true` (default): iterates `get_symbols_to_preload()`, loads each, records stats. ~16 models * ~1.2 MB = ~20 MB resident.
- No batching across symbols — each request takes its own `predictor.predict()`.
- Redis cache (`PredictionCache`, DB 2, prefix `ml:prediction:`, TTL 300s) keyed by `(symbol, interval, model_type)`; checked before inference when `use_cache=true`.

## Feature flag gating

CLAUDE.md says default `ENABLE_ML_PREDICTIONS=false`. Verification:

- `ENABLE_ML_PREDICTIONS` is set on **trading-engine** in `docker-compose.unified.yml` (line 579), defaulting `false`. Comment explicitly: ml-prediction is gated behind `--profile ml`.
- `ml-prediction-service` itself **does not read** `ENABLE_ML_PREDICTIONS`. Service runs unconditionally if its container is up; flag is consumer-side only.
- Trading-engine `signal_aggregator.py:994` checks `self.settings.enable_ml_predictions` before invoking ML leg; auto-trader honors same flag (`auto_trader.py:245`).
- API gateway proxies `/api/ml/*` straight through (no flag check); calls fail with connection error if container not running.

So: if container is up but flag false, the ML leg is silently skipped in the trading loop. Direct `GET /api/ml/predict/...` via gateway still returns predictions. No 503 on the service when "disabled" — the flag means "consumer ignores".

## LSTM cleanup status

ADR-001 (LSTM removed) is mostly enforced:

- `app/_archive_lstm/` exists (archive folder). `app/predictor.py` (LSTM module) gone — `from app.predictor import LSTMPricePredictor` only appears in `app/main.py.bak` (stale backup).
- `PredictorFactory.create_predictor("LSTM", ...)` raises `ValueError`. `get_predictor()` in main rejects non-GRU.
- `POST /api/v1/models/train` returns **HTTP 410 Gone**.
- `ModelComparator.lstm_predictor` is hard-coded `None`; `compare_models` endpoint still exposed but returns GRU-only payload.
- No `*_lstm.keras` artefacts in `models/`. progress.md line 654 confirms "ml-prediction-service factory 5 pass" (`tests/test_predictor_factory.py`).

**Residual LSTM surface (cosmetic):**
- Endpoint param descriptions on `predict_price`, `predict_trend`, `predict_ensemble`, `get_model_info`, `invalidate_cache` still say `"GRU (default) or LSTM"` (`main.py:680, 787, 928, 1341, 1641`).
- `enhanced_ml_prediction` advertises `"ENSEMBLE, LSTM, RF, GB, LR"` (line 996) — LSTM here referenced inside `EnhancedEnsemblePredictor` (sklearn-based, not Keras LSTM; the doc string is misleading).
- `/api/v1/supported-models` still lists LSTM as a "supported" type (lines 1571-1577).
- `app/main.py.bak` retained (stale; uses old `LSTMPricePredictor`).

## Internal deps

- **market-data-service** (port 8002, env `MARKET_DATA_URL`): historical klines via `GET /api/v1/klines/{symbol}` for inference + training data. Default in config is `localhost:8003` which is **wrong** (port 8003 is portfolio-manager); env override expected.
- **technical-analysis** (port 8004, env `TECHNICAL_ANALYSIS_URL`): used by `EnsemblePredictor` (`app/inference/ensemble.py`) to fetch TA signals for the 47% TA leg.
- **redis** (env `REDIS_HOST/PORT/DB`, default DB 2): prediction cache.
- **disk model store**: `MODELS_DIR` env or `services/ml-prediction-service/models/`. Sibling `trained_models/` exists but unused by runtime config.
- Self-reference in ensemble: `ml_service_url=http://localhost:{service_port}` — the ensemble predictor calls itself to get GRU output (`main.py:378`).
- Bybit price source flag (`BYBIT_TESTNET`) carried for training scripts that pull klines directly (no runtime use in main.py).

## Used by

- **api-gateway** (`services/api-gateway/app/main.py:1577-1750+`): proxies `/api/ml/predict/{price,trend,volatility,signal}/{symbol}`, `/api/ml/models`, `/api/ml/models/{symbol}`, `/api/ml/models/train`, `/api/ml/models/compare/{symbol}` to `ml_prediction_url`. Health check key `ml-prediction` in `/api/dashboard`.
- **trading-engine signal-aggregator** (`signal_aggregator.py:994`, `auto_trader.py:211-245`): consumes ML leg for blended signal when `enable_ml_predictions=true`.
- **technical-analysis service**: no direct call (TA itself is *upstream* of ml-prediction's ensemble — ml-prediction calls TA, not the other way around). Search `8007|ml-prediction` in technical-analysis returns nothing relevant.
- **ml-retraining-service**: writes new `.keras` artefacts into shared `models/` volume; ml-prediction must be restarted (or `POST /api/v1/models/preload?force=true`) to pick them up — there is no inotify reload.

## RabbitMQ

None. No `aio_pika`, `pika`, or `aiormq` imports in `app/`. Pure request/response over HTTP. (CLAUDE.md hypothesis confirmed.)

## DB tables

No SQL DB used. No `psycopg`, `asyncpg`, or `sqlalchemy` imports in `app/`. The only "DB" references are:
- Redis DB 2 (cache).
- Redis DB 3 (orderbook features cache, `app/features/orderbook_features.py:183`) — but this code path is unreachable since orderbook router not registered.
- TimescaleDB is read **transitively** via market-data-service HTTP, never directly.

No predictions table, no metrics table. All metrics live in Prometheus (`/metrics`).

## Key files

1. `app/main.py` — 1666 lines, all live HTTP routes + lifespan + Prometheus middleware
2. `app/config.py` — `Settings`, `ALL_GRU_SYMBOLS` (16), `PRIORITY_SYMBOLS` (7), `get_available_gru_models()` (filesystem scan)
3. `app/predictor_factory.py` — `PredictorFactory` (GRU-only), `ModelComparator` (LSTM-stubbed legacy)
4. `app/ml_models/gru_model.py` — `GRUPricePredictor` (Keras model + scalers + train/predict)
5. `app/ml_models/gru_predictor.py` — alternate predictor variant
6. `app/inference/ensemble.py` — `EnsemblePredictor` (TA 47% + ML 35% + MultiTF 18%, `EnsembleSignal`)
7. `app/models/ensemble_model.py` — `EnhancedEnsemblePredictor` (sklearn RF/GB/LR ensemble for `/predict/enhanced`)
8. `app/utils/redis_cache.py` — `PredictionCache` (DB 2, JSON serialize, TTL 300s)
9. `app/handlers/{orderbook,sentiment,regime}.py` — defined routers, **not registered** (dead code)
10. `tests/test_predictor_factory.py` — 5 passing tests (per progress.md line 654)

## Gotchas

- **Models stale 5 months**: trained 2025-12-09/10 (per CLAUDE.md, progress.md line 587, training reports). 2026-05-05 = ~150 days. Outside 7-day retrain threshold (`model_retrain_days=7`); every model returns `needs_retraining=True`.
- **V0 directional-accuracy leakage**: pre-`c56765c`, the metric had look-ahead bias; corrected metric shows chance-level performance on log-returns. Models lose to naive persistence baseline. CLAUDE.md mandates re-enable only after rebuild on returns target with **DSR > 0.95** acceptance gate.
- **BTC training OOM-killed at default container limits**: bump `deploy.resources.limits.memory` for ml-retraining-service before BTC retrain.
- **Default `market_data_url` wrong**: `app/config.py:57` defaults `http://localhost:8003` (portfolio-manager port). Production relies on `MARKET_DATA_URL` env; without it, training scripts hit the wrong service silently.
- **Handler routers unwired**: `app/handlers/{orderbook.py, sentiment.py, regime.py}` define `APIRouter` instances and are imported in `__init__.py`, but `main.py` never calls `app.include_router(...)`. So `/api/v1/orderbook/*`, `/api/v1/sentiment/*`, `/api/v1/regime/*` return 404. ~16 endpoints worth of dead code.
- **`/api/v1/supported-models` lies**: still lists LSTM with description "Long Short-Term Memory" as a supported type, contradicting the 410 on `/models/train` and the factory's `ValueError`.
- **`app/main.py.bak`** retained: imports the deleted `LSTMPricePredictor`. Confusing diff target; should be deleted.
- **Ensemble self-loop**: ensemble lifespan uses `localhost:{service_port}` to call itself for ML leg. Inside docker, `localhost` is the container — fine. If ever run behind a reverse-proxy with non-loopback bind, this breaks.
- **Cache TTL 300s vs 60m candle horizon**: `cache_ttl_seconds=300` for 60-minute candles -> cache evicts 12x per candle bar. Either intentional (latest data wins) or wasteful re-inference; not documented either way.
- **`GET /api/v1/predict/volatility/` is not ML**: pure pandas rolling-std heuristic with `predicted = recent * 1.1/1.2/1.3`. Documented as "in production, would use GARCH" but never replaced.
- **Two model directories** (`models/` and `trained_models/`): runtime reads `models/` only; `trained_models/` is divergent stale copy. Risk of operator copying into wrong path.

## Contradictions vs CLAUDE.md

| CLAUDE.md claim | Reality |
|---|---|
| "Standalone ML inference endpoints" | Accurate. Plus an unused ensemble predictor that calls back into the same service for the ML leg. |
| "16 GRU price-prediction models" | Confirmed: 16 `*_60m_gru.keras` files; symbols match `ALL_GRU_SYMBOLS`. |
| "LSTM deleted May 2026, archived under `_archive_lstm/`" | Mostly true. `app/_archive_lstm/` exists, no LSTM model files, factory rejects LSTM. **But** docstrings, `/supported-models`, `/predict/enhanced` model_type docs still mention LSTM; `app/main.py.bak` references deleted `LSTMPricePredictor`. |
| "Models currently gated off by default (`ENABLE_ML_PREDICTIONS=false`)" | The flag exists on **trading-engine**, not on ml-prediction-service. The ML service runs and serves predictions regardless. Gating is consumer-side — auto-trader / signal-aggregator skip ML leg. Direct `/api/ml/...` via gateway returns predictions even with flag false. |
| "V0 directional-accuracy metric had look-ahead leakage; after fix (commit `c56765c`) models score chance-level" | Code reflects this: predictions still return `directional_accuracy` from training stats, but no acceptance gate enforced in inference path — service will happily serve a chance-level model. |
| Validated symbols "BTC, ETH, SOL, BNB, ADA (5 active as of 2026-05-03). XRP / DOGE excluded by paper-trading data" | ml-prediction has trained models for **all 16** including XRP and DOGE; the active-symbol decision lives elsewhere (market-data + trading-engine). Not a contradiction here, just a scope difference: ML can predict symbols nobody trades. |
| "ml-prediction-service standalone" | True; no DB, no RabbitMQ. HTTP-only. |
