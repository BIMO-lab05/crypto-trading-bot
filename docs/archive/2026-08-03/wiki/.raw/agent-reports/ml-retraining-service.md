---
service: ml-retraining-service
path: services/ml-retraining-service/
generated: 2026-05-05
generator: agent (mapping)
---

# ml-retraining-service — raw agent report

## Entry point

`services/ml-retraining-service/app/main.py` — **a FastAPI app**, not a headless cron. Container `CMD` is `uvicorn app.main:app --host 0.0.0.0 --port 8009`. Long-lived HTTP service. Scheduling provided **internally** by APScheduler (`AsyncIOScheduler`) booted in the FastAPI lifespan when `RETRAIN_SCHEDULE_ENABLED=true`.

- `app/core/scheduler.py::RetrainingScheduler` — APScheduler with `MemoryJobStore`, `AsyncIOExecutor`, UTC timezone.
- One `CronTrigger` job per symbol, all firing on the same cron expression. Each job in turn calls back into the **same service's** `POST /api/v1/retrain/{symbol}` HTTP endpoint over `httpx.AsyncClient` (loopback to `service_host:service_port`). `_execute_scheduled_retrain` → `_trigger_retrain_api`.
- The `__main__` block at `app/main.py:1399` only calls `uvicorn.run(...)`. No `argparse`, no `--once` flag.

## Schedule cadence

- Default cron: `0 2 * * 1` — **Monday 02:00 UTC, weekly**, per `RetrainingSettings.retrain_schedule_cron` (`app/config/settings.py:42–45`).
- `coalesce=True`, `max_instances=1`, `misfire_grace_time=3600s`.
- Mirror schedule in GH Actions: `.github/workflows/ml-retrain.yml` cron `0 2 * * 1`. Workflow comment claims it "replaces" the in-cluster APScheduler — i.e. headless deploy on Oracle VM expects the always-on container to be dropped and the workflow to run a one-shot `docker compose run --rm --build ml-retraining python -m app.main --once` instead.

## Pipeline

`POST /api/v1/retrain/{symbol}` (`app/main.py:750–1013`) — four steps:

1. **Collect** — `core/data_collector.py::DataCollector.collect_training_data(symbol, interval)`. Fetches candles from market-data (`market_data_url` default `http://localhost:8002`).
2. **Train** — `core/model_trainer.py::ModelTrainer.train_model`. GRU keras model, configurable widths (`retrain_gru_units`, default `[128, 64]`; T0.1 rebuild uses `[32]`). Saves `model.keras + metadata.json + scalers.pkl + eval_arrays` under `models_versions_dir/<symbol>/<version>/`. Inserts `ModelVersion` row.
3. **Validate** — `core/model_validator.py::ModelValidator.validate_model`. Compares vs. current production `ModelVersion(status=DEPLOYED)` for the same symbol. Updates row status to `APPROVED`/`REJECTED`/`VALIDATION`.
4. **Deploy** — `core/model_deployer.py::ModelDeployer.deploy_model`. Backup → copy artifacts to production dir → POST `{ml_prediction_url}/api/v1/models/reload/{symbol}` (hot reload) → verify with `GET {ml_prediction_url}/api/v1/predict/{symbol}/gru`. Rollback on failure if `retrain_rollback_on_error=true`. Status → `DEPLOYED`.

## Models trained

- **Per-symbol, single-symbol models**, not multi-symbol. One `<SYMBOL>_60m_gru.keras` artifact per symbol per interval.
- Default symbols in retraining config: `["SOLUSDT", "BNBUSDT", "ADAUSDT"]` (`retrain_data_symbols`, `settings.py:62-65`).
- However `services/ml-prediction-service/models/` on disk contains **16 keras files** (ADA, APT, ARB, AVAX, BNB, BTC, DOGE, DOT, ETH, LINK, LTC, OP, POL, SOL, SUI, XRP — all `60m_gru.keras`). Matches the 16 figure in CLAUDE.md, but those models pre-date the current retraining-service default config. Retraining only auto-touches the 3 default symbols unless `RETRAIN_DATA_SYMBOLS` is overridden.

## Memory budget

- **No compose entry exists for `ml-retraining-service`** in `docker-compose.unified.yml`, `docker-compose.headless.yml`, `docker-compose.yml`, or `docker-compose.prod.yml`. `grep -in "retrain" docker-compose*.yml` returns nothing relevant. Implies the service is *only* run as `docker compose run --rm --build ml-retraining ...` from the GH Actions workflow — but the compose files referenced (`docker-compose.headless.yml`) don't actually define an `ml-retraining` service either. So the GH workflow's `run --rm` would fail today.
- No `deploy.resources.limits` block to point at. CLAUDE.md says BTC training OOM-killed at default container limits and "bump memory in relevant compose `deploy.resources.limits` block before retraining BTC" — but **there is no block to bump**. Either the compose file was deleted or never committed.
- Dockerfile: no `ENV` for memory. `requirements.txt` pins `tensorflow==2.15.0` (CPU build path; `retrain_gpu_enabled` defaults False).

## Acceptance gate

- DSR (Deflated Sharpe Ratio) gate **is implemented but disabled by default**. `retrain_min_dsr: Optional[float] = None` (`settings.py:110`). When None, `ModelValidator._check_dsr_gate` records DSR informationally but does not gate.
- T0.1 pre-flight gates similarly off by default: `retrain_min_r2_returns=None`, `retrain_min_dir_acc=None` (settings.py:146–166).
- Active gates in `ModelValidator.validate_model` (`core/model_validator.py:146–397`):
  - `retrain_min_r2 >= 0.85` (default; new R² minimum)
  - `val_loss < 0.05` (hardcoded `max_loss = 0.05`)
  - `retrain_min_improvement = 0.02` (R² delta vs current)
  - `retrain_max_degradation = 0.10` (max MAE degradation)
- `should_deploy = is_valid AND (r2_improvement OR loss_reduction)` — so the V0 R² metric (which had look-ahead leakage per CLAUDE.md) is still the dominant deploy criterion.
- ADR-relevant: code carries the *plumbing* for the post-V0 fix (`retrain_min_dsr`, `retrain_min_r2_returns`, `retrain_min_dir_acc`, `retrain_target_mode="log_returns"`, `retrain_feature_set="stationary"`), but none are turned on in the defaults. CLAUDE.md asserts a "DSR > 0.95 acceptance gate" — that threshold lives nowhere as a hardcoded default; it's an *operational* ask not yet wired in.

## Internal deps

- **market-data-service** (port 8002) — candle source for training data via `DataCollector` and `market_data_url`.
- **ml-prediction-service** (port 8007) — receives hot-reload signal at `POST /api/v1/models/reload/{symbol}` and is hit for verification at `GET /api/v1/predict/{symbol}/gru` (deployer.py:296, 374).
- **notification-service** (port 8006) — `notification_service_url` for retrain success/failure alerts (`retrain_notify_success`, `retrain_notify_failure`, `retrain_telegram_enabled`).
- **PostgreSQL** — own DB `ml_retraining` on port `5433` (`postgres_*`). Tables created via `init_db()` (SQLAlchemy `Base.metadata.create_all`). No Alembic migration files used at boot.
- **Redis** — `redis_db=5`. Imported in requirements but no usage observed in `app/core/`.
- **File system / object store** — `models_production_dir`, `models_versions_dir`, `models_backups_dir`. Default relative paths `./models/...`. `ModelDeployer` hardcodes `/models/{staging,production,backups}` (note the leading slash — different from settings defaults). Likely a host-mount expected.

## Used by

- No other service calls ml-retraining-service. It is the *caller*: pulls from market-data, pushes to ml-prediction-service. Background to the system.

## DB tables

Defined in `app/database/models.py`:

- `model_versions` — id, version, symbol, interval, model_type, architecture (JSON), training_info (JSON), train_metrics (JSON), val_metrics (JSON), backtest_metrics (JSON), model_path, metadata_path, status (`ModelStatus` enum), deployed_at, deployed_by, replaced_version, is_better, improvement_pct, created_at, updated_at.
- `retraining_jobs` — id, job_id, trigger_type, triggered_by, config (JSON), status (`RetrainingStatus` enum), started_at, completed_at, duration_seconds, results (JSON), error_message, error_details (JSON), metrics_summary (JSON), created_at, updated_at.
- `model_performance_logs` — id, model_version, symbol, performance_metrics (JSON), pre_deployment_metrics (JSON), degradation_pct, alert_triggered, alert_reason, measured_at, created_at. **Defined but no code currently inserts into it** (no references in `app/core/`).

## Key files

- `app/main.py` — 1407 lines, FastAPI surface (health, data collection, models, jobs, status, train, validate, retrain, deploy, deploy/rollback, deploy/backups, scheduler/{status,trigger,pause,resume,next-runs}).
- `app/core/scheduler.py` — APScheduler wrapper, in-process loopback HTTP triggers.
- `app/core/data_collector.py` — pull candles from market-data.
- `app/core/model_trainer.py` — GRU build + train + save.
- `app/core/model_validator.py` — R²/loss/MAE/DSR gates.
- `app/core/model_deployer.py` — copy artifacts, reload prediction service, verify, rollback.
- `app/core/cpcv_evaluation.py` + `app/cpcv.py` + `app/sharpe_metrics.py` — CPCV-based out-of-sample eval feeding DSR.
- `app/core/stationary_features.py` — T0.1 17-feature stationary-only set (alternative to legacy 22-indicator pile).
- `app/core/returns_metrics.py` — log-return R² / corrected directional accuracy.
- `app/config/settings.py` — pydantic-settings, ~50 fields.
- `app/database/models.py` — three SQLAlchemy tables.
- `Dockerfile` — python:3.11-slim, EXPOSE 8009.
- `.github/workflows/ml-retrain.yml` — weekly Mon 02:00 UTC GH Actions trigger over SSH.

## Gotchas

- **Compose orphan.** Service is not in any compose file. The "stack up" path doesn't include it; the GH workflow that "replaces" the in-cluster scheduler refers to a `docker-compose.headless.yml` service named `ml-retraining` that does not exist. Either dead workflow or unfinished migration.
- **`--once` not implemented.** Workflow runs `python -m app.main --once`; main.py has no argparse. Will start uvicorn ignoring the flag, hold the SSH session forever, then GH Actions kills it at the 60-min timeout. Workflow is a no-op (or worse, partial run).
- **Port 8009 collision.** `ml-retraining-service` defaults to 8009 (`settings.py:19`, Dockerfile EXPOSE 8009). `risk-metrics-service` already binds host port 8009 in `docker-compose.unified.yml` (`${RISK_PORT:-8009}:8009`). Co-resident deploy needs override.
- **Models 4+ months stale** — last trained 2025-12-10 per CLAUDE.md. Consistent with "service not in compose, scheduler never running."
- **V0 leakage history.** Default `retrain_target_mode="price"` keeps the V0 path that produced look-ahead-contaminated R² (commit `c56765c`). T0.1 fix exists in code (`log_returns` target, stationary feature set, returns-based metrics) but is gated behind env vars that aren't set anywhere in the repo's default configs.
- **Acceptance gate not enforced.** CLAUDE.md claims DSR > 0.95 is the re-enable gate. Code gates are off by default (`retrain_min_dsr=None`). Setting them to 0.95 requires env-var configuration that does not appear in any committed compose/env file.
- **LSTM cleanup (ADR-001).** Service trains GRU only (`model_type="GRU"`, `model_trainer` only builds GRU). Consistent with LSTM removal.
- **Hardcoded deployer paths.** `ModelDeployer.__init__` uses `/models/staging`, `/models/production`, `/models/backups` (absolute), but `settings.models_*_dir` defaults are relative `./models/...`. Mismatch — actual deploy target depends on whichever path the trainer wrote to vs what the deployer reads from.
- **Loopback HTTP scheduler.** `RetrainingScheduler._trigger_retrain_api` calls *its own* HTTP API rather than invoking the retrain coroutine in-process. Adds an unnecessary network hop and depends on uvicorn being healthy from inside the same container.
- **No `ModelPerformanceLog` writers.** The post-deployment monitoring table is defined but unused.

## Contradictions vs CLAUDE.md

| CLAUDE.md claim | Repo reality |
|---|---|
| "Cron-driven GRU retrain (no HTTP)" | FastAPI service exposing 30+ endpoints on 8009; APScheduler internally |
| "ml-retraining-service — no HTTP" (table) | Dockerfile `EXPOSE 8009`, `CMD uvicorn`, healthcheck pings `http://localhost:8009/health` |
| "16 GRU price-prediction models" | Default `retrain_data_symbols` is 3 (SOL, BNB, ADA). The 16 keras files on disk in `ml-prediction-service/models/` are a superset retrained service does *not* automatically cover |
| "Bump memory in relevant compose `deploy.resources.limits` block before retraining BTC" | No compose entry, no resources block exists to bump |
| "DSR > 0.95 acceptance gate" | Gate plumbed (`retrain_min_dsr`) but defaults to `None` (disabled). No committed env sets it |
| "Re-enable only after rebuild on returns target" | `retrain_target_mode="log_returns"` and `retrain_feature_set="stationary"` exist; defaults are still `price`/`legacy` |
