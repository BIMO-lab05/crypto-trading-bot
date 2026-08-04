# V0 Persistence Shootout — Results

> 2026-04-29. Empirical confirmation of the V0 verification on the three production GRU models (SOL/BNB/ADA at 60m).

## Headline

**The production GRUs have no measurable predictive edge on returns.**
- On price-level R² (the metric the bot has been reporting), GRU ≈ persistence: ~0.99 each. Confirms the recorded R²=0.99 is autocorrelation noise.
- On log-return R², the GRUs are **negative** (-0.36 to -5.5). A negative R² means the GRU is **worse than predicting the mean return** — actively destructive on returns prediction.
- On corrected directional accuracy (with last-input-bar reference), the GRUs sit at **47.9% – 51.4%** — coin-flip.

The metadata-recorded "Dir.Acc 79–84%" was entirely the look-ahead-leakage bug fixed in commit `c56765c`. The same data run through the corrected metric gives 50%.

## Numbers

| Metric | SOLUSDT | BNBUSDT | ADAUSDT |
|---|---|---|---|
| OOS samples | 3,437 | 3,437 | 3,437 |
| R² price (GRU) | 0.9967 | 0.9809 | 0.9980 |
| R² price (persistence) | 0.9975 | 0.9974 | 0.9984 |
| **R² log-returns (GRU)** | **−0.445** | **−5.501** | **−0.362** |
| R² log-returns (persistence) | ≈0 | ≈0 | ≈0 |
| **Dir.Acc corrected (GRU)** | **0.505** | **0.479** | **0.514** |
| Dir.Acc BUGGY (GRU, reference only) | 0.816 | 0.666 | 0.815 |
| Metadata recorded R² | 0.993 | 0.997 | 0.995 |
| Metadata recorded Dir.Acc | 0.843 | 0.794 | 0.833 |

## What this means

1. **Every "lift vs GRU baseline" estimate in the synthesis is anchored on phantom skill.** The baseline GRU has no edge to beat — any naive momentum / mean-reversion / random strategy could match its return prediction (which is "nothing").

2. **Architecture should be inverted.** The synthesis already had this as recommendation T2.2: "if isolated GRU Sharpe < 0.5 OOS net of fees, the indicator vote is doing the real work and the architecture should be inverted (GRU as meta-filter, not primary)." We now have the empirical answer: invert it. Or remove the GRU from the live decision path entirely until it has been retrained with:
   - Target: log-returns (not raw price)
   - Validation: CPCV + Deflated Sharpe (not single fixed split)
   - Acceptance gate: `r2_returns > 0` AND corrected `dir_acc > 0.55` AND isolated paper-trade Sharpe > 0.5 OOS net of Bybit fees.

3. **The aggregator's "confidence-weighted" ensemble of indicator-vote + GRU-prediction is downweighting noise.** If GRU contribution is ~50% directionally accurate and unrelated to returns, it's diluting whatever signal the indicators carry. Removing the GRU from the aggregator will not lose alpha; it will likely improve it slightly (by removing dilution).

4. **All Tier-1 / Tier-2 / Tier-3 recommendations in the synthesis remain valid as ranked**, but their expected lift estimates are now relative to a simpler baseline (the indicator vote alone, NOT the indicator-vote + GRU combination). The relative ordering doesn't change. The absolute numbers are slightly larger because the baseline is weaker than we thought.

## Why R² log-returns is so bad on BNBUSDT (-5.5)

A negative R² means the model's predictions are worse than just predicting the mean. -5.5 on BNB suggests the GRU's *direction* of error is systematic — when the actual return is small-positive, the GRU predicts large-negative or vice versa. This is consistent with a model that learned the opposite of the right signal (or, more likely, learned to mimic price autocorrelation in a way that doesn't translate to returns).

## Caveats

- CSV data used for evaluation is from December 2025 (`*_24months_20251208.csv`). The models were retrained 2026-04-26 — they were exposed to data through that date. The evaluation is on the chronologically last 20% of the *CSV*, which extends into late 2025. So the evaluation window overlaps with what was in the model's training set. **This biases the test results toward the model**, not against it. Even on data the model has seen, it has no return-level skill. On unseen data the picture cannot be better.
- The ideal evaluation is on data the models genuinely never saw. That requires either reconstructing the exact training cutoff or running forward-paper-test for ≥30 days. Given that the in-sample-flavoured shootout already shows zero edge, true OOS is unlikely to rescue these models.

## Action items

The V0-fix task (#14) is now done in two of three steps:
- ✅ Step 1: patch metric — committed `c56765c`.
- ✅ Step 2: persistence shootout — this report.
- ⏸ Step 3: isolated GRU paper backtest — superseded; the empirical finding above is sufficient. No need to run a paper backtest of a model with negative R² on returns.

## Implications for the ranked plan

Insert as new Tier-0 above existing T1.*:

**T0.1 — Decommission or rebuild the GRU layer.**
- Quick path: remove the GRU contribution from the live aggregator behind a feature flag; run forward-paper-test ≥7 days against the indicator-vote-only baseline. Document with commit message + ADR.
- Slow path: rebuild GRU with returns target, CPCV evaluation, and pre-flight gates (r2_returns > 0, dir_acc_corrected > 0.55, Sharpe > 0.5 OOS net of fees) before any live use.

**T0.2 — Re-baseline.**
The indicator-vote-only configuration becomes the new baseline against which T1.1 / T1.2 / T1.3 are measured.

Both are gated on user pick from the (revised) ranked list.
