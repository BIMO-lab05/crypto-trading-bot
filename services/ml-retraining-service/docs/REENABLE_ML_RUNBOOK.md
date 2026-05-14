# Re-enabling ML predictions after T0.1 GRU rebuild — operator runbook

**Audience.** Operator with shell on the docker host. Paper-trading mode
assumed (CLAUDE.md covers live separately).

**Why this exists.** ML predictions are gated off
(`ENABLE_ML_PREDICTIONS=false`) because V0 GRU models score chance-level
on log-returns post-fix (commit `c56765c`). CLAUDE.md gates re-enable on
a T0.1 rebuild whose **DSR ≥ 0.95** and which beats naive persistence.
This runbook covers only the post-rebuild flip path.

## Contents

1. [Prerequisites](#1-prerequisites)
2. [T0.1 retrain — env vars + invocation](#2-t01-retrain--env-vars--invocation)
3. [Reading the validation report](#3-reading-the-validation-report)
4. [Flipping `ENABLE_ML_PREDICTIONS=true`](#4-flipping-enable_ml_predictionstrue)
5. [Verification](#5-verification)
6. [Rollback](#6-rollback)
7. [KPIs — first 48h](#7-kpis--first-48h)
8. [Known gaps](#8-known-gaps)

---

## 1. Prerequisites

Run from repo root (`crypto-trading-bot/`).

```bash
# Stack health.
docker compose -f docker-compose.unified.yml ps && ./health_check.sh

# Candle freshness — must be current to within ~1h.
docker compose -f docker-compose.unified.yml exec timescaledb \
    psql -U cryptobot -d market_data \
    -c "SELECT symbol, MAX(timestamp) FROM klines GROUP BY symbol;"

# Disk (~200MB per symbol per retrain).
df -h ./services/ml-retraining-service/models ./services/ml-prediction-service/models

# Current model age — anything > 60 days is stale.
ls -la ./services/ml-prediction-service/models/*.keras 2>/dev/null

# ml-retraining is not in default profile — start it.
docker compose -f docker-compose.unified.yml up -d ml-retraining
```

Any candle row before **2026-04-25** may be testnet — wipe before
retraining (CLAUDE.md gotcha).

## 2. T0.1 retrain — env vars + invocation

T0.1 = log-returns target + stationary feature set + single-layer GRU [32].
Pre-flight gates: `R²-returns ≥ 0`, `dir-acc ≥ 0.55`, `DSR ≥ 0.95`.

### 2.1 Env vars (paste-ready)

```bash
RETRAIN_TARGET_MODE=log_returns
RETRAIN_FEATURE_SET=stationary
RETRAIN_GRU_UNITS='[32]'
RETRAIN_MIN_DSR=0.95
RETRAIN_MIN_R2_RETURNS=0.0
RETRAIN_MIN_DIR_ACC=0.55
```

Add to `.env` at repo root, then:

```bash
docker compose -f docker-compose.unified.yml up -d --force-recreate ml-retraining
```

`retrain_min_*` defaults are `None` (gate off). Only this retrain has
gates armed; defaults stay safe for normal operation.

### 2.2 Option A — research script (first rebuild, recommended)

Runs all symbols, writes a markdown report, never publishes. Reuses the
real `ModelTrainer` codepath.

```bash
docker compose -f docker-compose.unified.yml exec ml-retraining \
    python docs/strategy/research-2026-04-29/T0_1_rebuild.py \
        --data-dir /tmp/rebuild/data \
        --output-dir docs/strategy/research-2026-04-29
```

CSV inputs: `{SYMBOL}_1H_*.csv` with `timestamp, open, high, low, close, volume`.
Outputs: `T0.1-rebuild-results.{json,md}`.

### 2.3 Option B — production retrain endpoint (per-symbol)

Use after the script confirms gates clear. Goes through validator +
deployer.

```bash
for sym in SOLUSDT BNBUSDT ADAUSDT; do
  curl -X POST "http://localhost:8009/api/v1/retrain/${sym}?interval=60&auto_validate=true&auto_deploy=true"
done
```

Returns include `validation.should_deploy` and `deployment.success`.

## 3. Reading the validation report

Each gate appears in `validation_checks[<key>].passed` as `True|False|None`.
`None` = informational (gate disabled or value missing/NaN).

| Gate | Setting | Metric key | Pass |
|---|---|---|---|
| Min R² (legacy) | `RETRAIN_MIN_R2` | `val_r2` | `≥ 0.85` |
| Max loss (legacy) | hardcoded | `val_loss` | `< 0.05` |
| **DSR** | `RETRAIN_MIN_DSR` | `test_dsr` | `≥ 0.95` |
| **R²-returns** | `RETRAIN_MIN_R2_RETURNS` | `test_r2_returns` | `≥ 0.0` |
| **Dir-acc** | `RETRAIN_MIN_DIR_ACC` | `test_dir_acc_corrected` | `≥ 0.55` |

**Pass:**
```json
"validation": {"should_deploy": true, "is_valid": true, "reason": "...; DSR=0.97 clears gate (0.95); ✅ APPROVED FOR DEPLOYMENT"}
```

**Failure modes:**
- `DSR (0.42) below gate (0.95)` — most common GRU failure on crypto
  returns. Do **not** flip; iterate features or accept "no edge found".
- `R²(returns) (-0.03) below gate (0.0)` — loses to naive persistence.
- `Dir.Acc (0.51) below gate (0.55)` — coin-flip after V0 metric fix.
- `unavailable (missing or NaN)` — degenerate test set; investigate.
  Does NOT block deployment.

## 4. Flipping `ENABLE_ML_PREDICTIONS=true`

Only after at least one symbol shows `should_deploy: true` AND
`deployment.success: true`.

**Only `trading-engine` reads this flag** (line 579 of
`docker-compose.unified.yml`). ml-prediction itself doesn't gate on it.

```bash
# Edit .env at repo root.
echo "ENABLE_ML_PREDICTIONS=true" >> .env

# Restart trading-engine to pick up the change.
docker compose -f docker-compose.unified.yml up -d --force-recreate trading-engine

# Confirm.
docker compose -f docker-compose.unified.yml exec trading-engine \
    printenv ENABLE_ML_PREDICTIONS   # → true
```

ml-prediction is gated behind `--profile ml`; bring it up explicitly:

```bash
docker compose -f docker-compose.unified.yml --profile ml up -d ml-prediction
```

## 5. Verification

CLAUDE.md verification standards: HTTP 200 alone ≠ shipped. All four:

```bash
# 5.1 ml-prediction serves and loaded the new artifact.
curl -s http://localhost:8007/api/v1/predict/SOLUSDT/gru | jq .
docker compose -f docker-compose.unified.yml logs --tail=200 ml-prediction \
    | grep -E "Loaded GRU model|Stale GRU model"

# 5.2 trading-engine is consuming ML signals.
docker compose -f docker-compose.unified.yml logs --tail=500 trading-engine \
    | grep -iE "ml_prediction|signal_aggregator|gru"

# 5.3 DB shows DEPLOYED row with recent deployed_at.
docker compose -f docker-compose.unified.yml exec postgres \
    psql -U cryptobot -d ml_retraining \
    -c "SELECT id, symbol, version, status, deployed_at FROM model_versions \
        WHERE status = 'DEPLOYED' ORDER BY deployed_at DESC LIMIT 5;"

# 5.4 Notification arrived in Telegram (actual message, not 'sent: True').
```

## 6. Rollback

### 6.1 Flag flip (instant, do this first)

```bash
# .env: ENABLE_ML_PREDICTIONS=false
docker compose -f docker-compose.unified.yml up -d --force-recreate trading-engine
```

Pre-ML signal pipeline resumes. Paper-trading state unaffected.

### 6.2 Model rollback (only if bad artifact is live)

```bash
curl -X POST http://localhost:8009/api/v1/deploy/rollback/SOLUSDT
ls -la ./services/ml-prediction-service/models/SOLUSDT_60m_*.keras
```

Restores from `/models/backups/{symbol}_{timestamp}/`. Reload via
mtime-based stale check on next prediction request.

### 6.3 Halt trading entirely

```bash
touch EMERGENCY_STOP        # repo root, read-only bind into trading-engine
# OR
curl -X POST http://localhost:8000/api/portfolio/emergency-stop \
    -H "Authorization: Bearer ${ADMIN_TOKEN}"
```

## 7. KPIs — first 48h

| KPI | Target | Where |
|---|---|---|
| Live directional accuracy (24h) | within 5pp of test-set | `risk-metrics-service /api/risk/ml-directional-accuracy` |
| Latency p95 of `/predict/{symbol}/gru` | < 100 ms | Grafana / ml-prediction logs |
| Win-rate of ML-influenced trades | not below pre-ML baseline | portfolio-manager + Grafana |
| Daily-loss circuit-breaker hits | 0 | trading-engine logs (`5% daily-loss`) |
| Model-reload events | only on retrain | ml-prediction logs (`Stale GRU model ... reloading`) |
| Open positions vs cap | within 2% per-trade | `portfolio-manager /api/portfolio/positions` |

If live directional accuracy drops > 5pp below test-set DSR for 12+
consecutive hours, **roll back (§6.1)**. DSR is OOS but still
pre-deployment; live regime drift can still break it.

## 8. Known gaps

P1 items — don't block the flip but file before calling the rebuild done.

1. **ml-prediction has no max-age refusal.** `gru_model.py` reloads on
   newer mtime but does not refuse to serve a stale artifact. Add
   `MAX_MODEL_AGE_DAYS` env + `/health/detailed` surface.
2. **Manual deploy override.** `POST /api/v1/deploy/{version_id}` on
   ml-retraining is the operator override. As of 2026-05-06:
   `REJECTED` is hard-blocked (no `force`), `VALIDATION` requires
   `?force=true`, `APPROVED`/`DEPLOYED` proceed normally. Treat
   `force=true` as production-impacting.
3. **Stale-reload uses container-local mtime.** Clock skew between
   ml-retraining and ml-prediction containers can wedge the reload
   check. Verify NTP before relying on hot reloads in production.

---

**Last reviewed:** 2026-05-06. Update if validator thresholds change,
the deploy endpoint contract changes, or `T0_1_rebuild.py` moves.
