# V0 Verification — GRU R²=0.995 / Dir.Acc=79–84% are bogus

> 2026-04-29. Resolution of the convergent flag from research agents #2 and #5. Status: **bug confirmed in production training code**.

## TL;DR

Both marquee ML metrics for the production GRU models are methodologically broken:

1. **R² is computed on raw close-price levels.** A persistence baseline (`next_price = last_price`) achieves the same R² ≈ 0.99 on hourly crypto. This metric measures autocorrelation of price levels, not predictive skill.
2. **Directional accuracy uses look-ahead leakage AND is degenerate.** It uses bar 5 of the future prediction horizon as its reference point — data not visible at inference time. The formula collapses such that any prediction tracking price closely will score ~80%+, regardless of edge.

Production metadata (`services/ml-prediction-service/models/SOLUSDT_60m_gru_metadata.json`) records `r2_score: 0.9925` and `directional_accuracy: 0.8430` — both produced by the broken code path.

## Code references

### Bug 1 — R² on raw price level

`services/ml-retraining-service/app/core/model_trainer.py:125`
```python
def create_sequences(self, data, target_col: str = 'close'):
```

Line 146:
```python
target = data[target_col].values  # raw close price
```

Line 414-421:
```python
y_actual = self.scaler_y.inverse_transform(y)
y_pred_actual = self.scaler_y.inverse_transform(y_pred)
...
r2 = r2_score(y_actual.flatten(), y_pred_actual.flatten())
```

R² is computed on inverse-transformed price (back to dollar values). For a series with strong serial correlation in *level* (i.e. crypto), `var(residuals) / var(prices)` is dominated by between-day price variation, not by prediction skill on returns.

**Fix**: target log-returns, or compute R² on the residual relative to a persistence baseline.

### Bug 2 — Directional accuracy with look-ahead + degenerate reference

`services/ml-prediction-service/app/ml_models/gru_model.py:442-444`
```python
y_test_direction = np.sign(y_test[:, 0] - y_test[:, -1])
y_pred_direction = np.sign(y_pred[:, 0] - y_test[:, -1])
directional_accuracy = np.mean(y_test_direction == y_pred_direction)
```

Same bug at `services/ml-prediction-service/hyperparameter_optimizer.py:846`.

`y_test` shape is `(N, prediction_horizon=5)`:
- `y_test[:, 0]` = bar 1 of the future window (the actual next bar)
- `y_test[:, -1]` = bar 5 of the future window (4 bars further out)

The "actual direction" reference is a future bar, not a past bar. **Information that does not exist at prediction time is used in the metric.**

Worse, both `y_test_direction` and `y_pred_direction` subtract the same `y_test[:, -1]`. Whenever `y_pred[:, 0]` and `y_test[:, 0]` fall on the same side of `y_test[:, -1]`, the prediction is scored "correct." Given R²=0.99 (predictions track price closely), they almost always do — regardless of whether the predicted *change* matches the actual *change*.

**Correct form** would compare the predicted change against the actual change, both anchored on the last known bar (i.e. `X_test[:, -1, close_feature_idx]`):
```python
last_known = unscaled_close_at_end_of_input_sequence
true_dir = np.sign(actual_y_test[:, 0] - last_known)
pred_dir = np.sign(actual_y_pred[:, 0] - last_known)
directional_accuracy = np.mean(true_dir == pred_dir)
```

But this requires inverse-transforming through scaler_X for the close feature, or carrying the raw close alongside, which the current code doesn't do.

## Train/test split — clean

Verified `services/ml-retraining-service/app/core/model_trainer.py:266`:
```python
X_train, X_test, y_train, y_test = train_test_split(
    X, y,
    test_size=test_size,
    shuffle=False  # Don't shuffle time series data
)
```

Chronological split, no shuffling. So the bug is **not** about leaking future data into train; it's about the *reported metrics* being meaningless.

## Implication for the synthesis

This invalidates every "lift over current GRU baseline" estimate in the ranked plan. The current baseline is:

- A model trained on raw price (target highly autocorrelated)
- With both reported metrics decorative

We do not know the GRU's actual edge. Until V0 is fully resolved (metric fix + persistence-baseline comparison + isolated GRU paper backtest), **forward-paper-test of any new strategy can only be measured against itself, not "vs GRU baseline."**

## Recommended follow-up

1. **Patch the metric code** (low-risk, doesn't affect trading): fix `directional_accuracy` to use last-input-bar reference; add a `r2_returns` field computing R² on log-returns alongside the existing `r2_score`.
2. **Recompute metrics on existing production models without retraining** (one-shot script): load each production model, reload its training data via stored timestamps, run the corrected metric. Compare to recorded numbers. The delta is the bullshit factor.
3. **Run a persistence-baseline shootout** on the same OOS window: if GRU's `r2_returns` ≤ persistence's `r2_returns`, the GRU has zero predictive skill on returns and the architecture should be inverted (indicator vote primary, GRU as meta-filter at most).
4. **If GRU's `r2_returns` > persistence**: compute Deflated Sharpe Ratio on the GRU-only paper-trading PnL with realistic Bybit fees + slippage. Only then is the lift estimate from any T1.* intervention trustworthy.

## Risk note

Steps 1-2 modify *measurement code only*; do not touch the trading-engine or the live signal aggregation. Safe under auto mode.
Step 3 is a read-only computation against historical data.
Step 4 requires forward-paper-test infrastructure, which the synthesis already says is the bot's only trustworthy gate today.
