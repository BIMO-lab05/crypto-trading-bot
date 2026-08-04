---
type: concept
status: blocked
tags: [concept, ml, gru]
created: 2026-05-05
updated: 2026-07-30
---

# ML Status

16 GRU price-prediction models. **Currently gated OFF** (`ENABLE_ML_PREDICTIONS=false`).

## Why off

V0 directional-accuracy metric had **look-ahead leakage**. After fix (commit `c56765c`), models score chance-level on log-returns and **lose to naive persistence**.

## Acceptance gate

Re-enable only after rebuild on returns target with **DSR > 0.95**.

## Lifecycle

- LSTM removal (ADR-001) is **incomplete**: `_archive_lstm/` does not exist anywhere in the tree; `ensemble_model.py:15` still imports LSTM; `ml-retraining-service/app/core/models/lstm.py` still present; footprint spans 10+ files. Full purge = v1.3 Phase 23 (`.planning/REQUIREMENTS.md` ML-PURGE-01/02). Also: `model_trainer.py:430,623` and `scripts/check_ml_training_status.py` still compute the forbidden price-level R².
- GRU last trained 2025-12-10 — stale (7+ months as of 2026-07)
- 2026-07-29: GRU NaN/inf-guard fixes landed; Phase 9 (2026-05-17) armed the ML auto-flip + leaderboard/DSR evidence machinery
- BTC training OOM-killed at default container limits — bump memory before retraining BTC

## Related

- [[../modules/ml-prediction-service|ml-prediction-service]]
- [[../modules/ml-retraining-service|ml-retraining-service]]
- [[../modules/technical-analysis|technical-analysis]]
- [[Feature-Flags]]
