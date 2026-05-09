---
type: concept
status: blocked
tags: [concept, ml, gru]
created: 2026-05-05
updated: 2026-05-05
---

# ML Status

16 GRU price-prediction models. **Currently gated OFF** (`ENABLE_ML_PREDICTIONS=false`).

## Why off

V0 directional-accuracy metric had **look-ahead leakage**. After fix (commit `c56765c`), models score chance-level on log-returns and **lose to naive persistence**.

## Acceptance gate

Re-enable only after rebuild on returns target with **DSR > 0.95**.

## Lifecycle

- LSTM models deleted 2026-05; archived under `_archive_lstm/`
- GRU last trained 2025-12-10 — stale (4+ months as of 2026-05)
- BTC training OOM-killed at default container limits — bump memory before retraining BTC

## Related

- [[../modules/ml-prediction-service|ml-prediction-service]]
- [[../modules/ml-retraining-service|ml-retraining-service]]
- [[../modules/technical-analysis|technical-analysis]]
- [[Feature-Flags]]
