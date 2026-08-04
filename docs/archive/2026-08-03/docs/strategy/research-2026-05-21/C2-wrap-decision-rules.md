# C2 Wrap Experiment — Pre-Commit Decision Rules

**Status:** LOCKED before any wrap-experiment training run.
**Date:** 2026-05-21
**Purpose:** Eliminate p-hacking. Pick ε + pass criteria deterministically. Honor verdict regardless of outcome.

## Hypothesis

A regression GRU trained on `log_returns` produces predictions whose *sign + magnitude* contain a tradeable signal when filtered by a flat-zone deadband (i.e. a 3-class classifier of {BUY, FLAT, SELL}).

If true: classification head retrain (full C2 surgery) is motivated.
If false: same noise floor → full surgery also fails. Both C2 paths killed.

## Inputs (fixed)

- Data: `/tmp/t01_4h_clean/{SOLUSDT,BNBUSDT,ADAUSDT}_1H_4hfresh.csv` (4519 4H bars per symbol, DB-resampled through 2026-05-20).
- Model: regression GRU[32], `target_mode=log_returns`, `feature_set=stationary`, prediction_horizon=5.
- Train/test split: same as T0.1 (80/20 sequential, no shuffle).

## Deterministic ε rule (PICKED BEFORE RUN)

After model trains, compute predictions on **training set only**: `train_preds = model.predict(X_train)` then inverse-scale to log-return space; take the LAST horizon step `train_preds[:, -1]`.

Set:

```
mu_train  = mean(train_preds)
sigma_train = std(train_preds)
epsilon = 1.0 * sigma_train          # locked: exactly 1 train-pred sigma
```

Test-set signal (per test sample `i`, using `test_pred = pred[i, -1]` inverse-scaled):

```
signal[i] = +1  if test_pred > mu_train + epsilon
signal[i] = -1  if test_pred < mu_train - epsilon
signal[i] =  0  otherwise (FLAT)
```

Realized actual returns (already inverse-scaled from `y_test[:, -1]`):

```
actual_log_return[i] = inverse_scale(y_test[i, -1])
strategy_return[i]   = signal[i] * actual_log_return[i]
```

No transaction cost, no slippage. (If pre-cost signal fails, post-cost is worse.)

## Pass criteria (LOCKED — both must clear)

Verdict per symbol:

| Gate | Threshold | Source metric |
|---|---|---|
| **Balanced accuracy** | ≥ 0.45 | mean of per-class recall over realised-direction-vs-signal contingency, including a FLAT bucket for `|actual_return| ≤ epsilon` |
| **DSR on strategy returns** | ≥ 0.95 | cpcv_to_dsr fed `strategy_return[i]` series (45 paths per CLAUDE.md DSR rule) |

Note on chance baseline: 3-class with balanced classes by construction gives 0.333 chance. The 0.45 bar is moderate — equivalent to ~4 standard errors above chance for n_test ≈ 887.

Overall verdict:
- **EDGE FOUND**: at least 2 of 3 symbols pass BOTH gates.
- **NO EDGE**: any other outcome.

EDGE FOUND → motivates full classification surgery (C2 proper).
NO EDGE → kills C2 path. Move to C3 (XGB baseline) or C4 (cross-sectional features).

## What this experiment does NOT test

- Classification-head OPTIMA: the loss landscape may have local minima a regression model can't reach. Wrap-first only tests whether *any* threshold structure on regression outputs has signal. If wrap fails, full surgery is a low-confidence escalation.
- Different ε values. Sweeping ε then reporting best = p-hacking. ONE ε rule, ONE run, ONE verdict.
- Hyperparameter tuning. Same GRU[32] / dropout 0.2 / Adam(0.001) as baseline.

## Sign convention sanity check

`actual_log_return[i] > 0` means price went up between bar `(i + seq_len + horizon - 1)` and bar `(i + seq_len + horizon)`. signal=+1 → long → strategy_return positive when prediction was right. signal=-1 → short → strategy_return positive when prediction (price down) was right.

If wrap result has *negative* mean strategy returns, model is anti-predictive — flip sign for a quick second-pass check, but do NOT do that to PASS the gate (that's a single-bit sign hack, not a real strategy).

## Output

- `docs/strategy/research-2026-05-21/C2-wrap/results.json` — per-symbol metrics + verdict
- `docs/strategy/research-2026-05-21/C2-wrap/report.md` — human-readable
- `docs/strategy/research-2026-05-21/C2-wrap/run.log` — training stdout

End of pre-commit rules. Anything beyond this point is post-hoc and must NOT modify the gates above.
