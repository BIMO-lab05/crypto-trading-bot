# ml-prediction-service

Standalone ML inference service (FastAPI, port **8007**). Serves GRU price-prediction models trained by `ml-retraining-service`.

**Status: off by default.** The service sits behind the compose `ml` profile (`docker compose --profile ml up`) and `ENABLE_ML_PREDICTIONS=false` keeps its signal out of the aggregator. This is deliberate: after the V0 look-ahead-leakage fix (commit `c56765c`), GRU models score chance-level (~53%) on log-returns and lose to naive persistence. Re-enable requires a rebuild on a returns target passing the DSR > 0.95 gate — see `wiki/concepts/ML-Status.md` and `docs/strategy/research-2026-04-29/`.

## Endpoints (prefix `/api/v1`, service-internal — the gateway drops `/v1`)

- `GET /predict/{symbol}/gru`, `GET /predict/enhanced/{symbol}` — model inference
- `GET /predict/ensemble/{symbol}` — **legacy** TA/ML/sentiment/MTF blend; contradicts the current signal pipeline and imports LSTM code (deletion scheduled with the Phase 23 ML purge)
- `GET /models`, `GET /models/{symbol}`, `GET /models/loaded`, `POST /models/preload`, `POST /models/reload/{symbol}` — model management (reload is called by ml-retraining-service on deploy)
- `GET /models/compare/{symbol}`, `GET /supported-models`, `GET /cache/stats`
- `GET /health`, `GET /ready`, `GET /metrics`

## Model artifacts

16 GRU `*.keras` models under `models/` (+ metadata.json + scalers.pkl per version). **Last trained 2025-12-10 — stale.** Retrain before relying on predictions; BTC training OOM-kills at default container memory limits (bump `deploy.resources.limits` first).

## Known debt

- Historical experiment/coverage reports that used to live in this directory are archived under `docs/archive/services/ml-prediction-service/`. The hyperparameter guide there targets R² on price levels — the exact forbidden metric; kept only as an anti-pattern example.
- `ensemble_model.py` still imports LSTM (ML-PURGE footprint, `.planning/REQUIREMENTS.md`).

More: `wiki/modules/ml-prediction-service.md`.
