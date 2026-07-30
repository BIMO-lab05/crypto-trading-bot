# ml-retraining-service

Automated GRU retraining pipeline: collect → train → validate → deploy. FastAPI + APScheduler (default cron `0 2 * * 1`, Monday 02:00 UTC), re-entering itself over loopback HTTP at `POST /api/v1/retrain/{symbol}`.

**Status: effectively dormant.** The service is **not in any compose file**, so the weekly cron never fires in the canonical stack; models have been stale since **2025-12-10**. The GH Actions workflow `ml-retrain.yml` is also broken (targets a service missing from `docker-compose.headless.yml`; passes a `--once` flag `app.main` doesn't parse).

## Pipeline

1. **Collect** — candles from market-data-service (`:8002`)
2. **Train** — GRU (`ModelTrainer`); artifacts to `models_versions_dir/<symbol>/<version>/`; row in `model_versions`
3. **Validate** — against the deployed version; active gates are still V0-style (`min_r2 >= 0.85`, loss ceiling). The honest gates (`retrain_min_dsr`, `retrain_min_r2_returns`, `retrain_min_dir_acc`) are plumbed but **default to disabled** — turn them on before trusting any retrain
4. **Deploy** — backup, copy, `POST /models/reload/{symbol}` on ml-prediction-service, verify, rollback on failure

## Warnings

- `model_trainer.py` still computes **R² on price levels** (forbidden V0 metric; Phase 23 ML-PURGE-01 removes it). Persisted model metadata carries the bad number — do not quote it.
- Default `retrain_target_mode="price"` reproduces the leakage-era setup; the log-returns + stationary-features path is opt-in.
- Port 8009 in its config collides with risk-metrics-service in unified compose.
- BTC training OOM-kills at default container memory limits.
- Container runs as `appuser` since 2026-07-29 (de-rooted).

## DB (`ml_retraining` Postgres, :5433)

`model_versions`, `retraining_jobs`, `model_performance_logs` (defined; no writer in code).

More: `wiki/modules/ml-retraining-service.md`. Design + evidence for the returns-target rebuild: `docs/strategy/research-2026-04-29/`.
