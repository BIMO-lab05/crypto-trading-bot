---
type: module
path: "services/ml-retraining-service/"
status: active
language: python
port: 8009
purpose: "Automated GRU model retraining (FastAPI + APScheduler, weekly cron)"
maintainer: ""
last_updated: 2026-05-05
linked_issues: []
depends_on: [market-data-service, ml-prediction-service, notification-service]
used_by: []
tags: [module, service, ml, cron, retraining]
created: 2026-05-05
updated: 2026-05-05
---

# ml-retraining-service

**Port:** `8009` (collides with `risk-metrics-service` in `docker-compose.unified.yml`)
**Path:** `services/ml-retraining-service/`
**Purpose:** Automated GRU retrain pipeline — collect → train → validate → deploy.

## Overview

Despite the CLAUDE.md description "no HTTP — cron-driven background", this is a **FastAPI service** running on `uvicorn` at port 8009. Scheduling is internal: `APScheduler` cron job (default `0 2 * * 1` — Monday 02:00 UTC) loops over each configured symbol and re-enters the same service over loopback HTTP at `POST /api/v1/retrain/{symbol}`.

Default symbols (`retrain_data_symbols`): `SOLUSDT`, `BNBUSDT`, `ADAUSDT`. The 16 GRU `*.keras` artifacts in `services/ml-prediction-service/models/` are a wider set; auto-retrain only covers symbols present in the env-config list.

## Pipeline

1. **Collect** — `DataCollector` fetches candles from [[market-data-service]] (8002).
2. **Train** — `ModelTrainer` builds a GRU (default widths `[128, 64]`; T0.1 rebuild swaps to `[32]`). Saves `model.keras + metadata.json + scalers.pkl + eval_arrays` to `models_versions_dir/<symbol>/<version>/`. Inserts `model_versions` row.
3. **Validate** — `ModelValidator` compares against the current `DEPLOYED` `ModelVersion`; gates on `min_r2`, `max_loss`, `min_improvement`, `max_degradation`. DSR / R²-on-returns / corrected directional-accuracy gates exist but default to disabled.
4. **Deploy** — `ModelDeployer` backs up the current production artifact, copies the new files, hits [[ml-prediction-service]] at `POST /api/v1/models/reload/{symbol}`, then verifies with `GET /api/v1/predict/{symbol}/gru`. Rollback on failure.

## DB tables (`ml_retraining` Postgres on :5433)

- `model_versions` — full per-train artifact metadata + status (`training`/`validation`/`approved`/`deployed`/`rejected`/`rolled_back`).
- `retraining_jobs` — one row per scheduled or manual run; status, duration, results JSON.
- `model_performance_logs` — post-deployment monitoring; **defined but no writer in code**.

## Acceptance gate (vs [[../concepts/ML-Status]])

CLAUDE.md states a `DSR > 0.95` re-enable gate. The code path is plumbed (`settings.retrain_min_dsr`, `_check_dsr_gate`) but **defaults to `None` (disabled)**. Likewise `retrain_min_r2_returns` and `retrain_min_dir_acc`. No committed env file sets them. The active deploy decision is still V0-style: `min_r2 >= 0.85` plus a `loss < 0.05` ceiling. Re-enabling ML predictions requires turning these env vars on, not just code changes.

## Gotchas

- **Not in any compose file.** `grep -in "retrain" docker-compose*.yml` — nothing. The "weekly cron" never fires in the canonical stack; APScheduler only runs if someone manually launches the container.
- **GH Actions workflow `.github/workflows/ml-retrain.yml`** runs `docker compose -f docker-compose.headless.yml run --rm --build ml-retraining python -m app.main --once`. Two problems: (a) no `ml-retraining` service in `docker-compose.headless.yml`; (b) `app.main` has no `--once` argparse — flag is silently ignored and uvicorn boots forever until GH Actions hits the 60-min timeout.
- **Models 4+ months stale** (last trained 2025-12-10) — consistent with the scheduler never running.
- **Port 8009 collision** with `risk-metrics-service` in unified compose.
- **Loopback HTTP scheduling** — APScheduler triggers re-enter via `httpx` to `service_host:service_port` instead of calling the coroutine in-process; needs uvicorn alive in same container.
- **Deployer hardcodes `/models/{staging,production,backups}` (absolute)** while settings default to `./models/...` (relative). Mismatch unless host bind-mount is at `/models`.
- **V0 leakage history** — default `retrain_target_mode="price"`, `retrain_feature_set="legacy"`. The post-`c56765c` log-returns + stationary-feature path exists in code but is opt-in.

## See also

- [[../concepts/ML-Status]] — V0 leakage findings, DSR acceptance criterion
- [[../decisions/ADR-001-LSTM-removed]] — why this service trains GRU only
- [[ml-prediction-service]] — receives hot-reload signals; serves the artifacts this service produces
- [[market-data-service]] — candle source for training data
- [[technical-analysis]] — runs the GRU artifacts inline for signal aggregation
- [[../flows/Signal-Pipeline|Signal Pipeline]]

## Raw

Full agent walkthrough: `wiki/.raw/agent-reports/ml-retraining-service.md`
