# Trading-Bot Research-Driven Improvement Plan — 2026-04-29

> Distilled from 6 parallel research agents (crypto factors, indicator+ML hybrid, risk overlays, equity→crypto failure modes, retail practitioners, execution & sizing) plus an empirical V0 verification on the production GRU models.
>
> Win metric (default): OOS Sharpe ratio vs current indicator-vote baseline (NOT the GRU-augmented baseline — see Tier 0). Override with one word: "Sharpe", "Dir.Acc", "MaxDD", "Return".
>
> Symbol scope: SOL/BNB/ADA. Test gate: forward-paper-test ≥7 days. Backtest is contaminated and cannot serve as the gate today.

---

## Tier 0 — REBASELINE (the GRU has no edge; anything built on top of it overstates lift)

### T0.1 — Decommission or rebuild the GRU contribution
**Empirical finding (V0 persistence shootout, 3437 OOS samples per symbol):**

| Symbol | R² log-returns (GRU) | Dir.Acc corrected | Recorded (buggy) Dir.Acc |
|---|---:|---:|---:|
| SOLUSDT | −0.445 | 50.5% | 84.3% |
| BNBUSDT | −5.501 | 47.9% | 79.4% |
| ADAUSDT | −0.362 | 51.4% | 83.3% |

The production GRUs have **negative** R² on log-returns (worse than predicting the mean) and **coin-flip** directional accuracy. The 79–84% headline numbers were a look-ahead-leakage bug (fixed in commit `c56765c`).

**Quick path (recommended):** remove GRU contribution from the live confidence-weighted aggregator behind a feature flag. Forward-paper-test ≥7 days against indicator-vote-only. If returns / Sharpe don't degrade (likely improve, since GRU was diluting signal with noise), promote.

**Slow path (only if quick-path forward test shows GRU was helping):** rebuild GRU with target = log-returns, validation = CPCV + Deflated Sharpe, acceptance gate = `r2_returns > 0` AND `dir_acc_corrected > 0.55` AND isolated paper Sharpe > 0.5 net of Bybit fees.

**Effort**: quick-path ~1 day (feature flag + aggregator change + paper monitor). Slow-path ~2-3 weeks (training pipeline rework).
**Risk**: low for quick-path (paper-mode, feature-flagged). Medium for slow-path (heavy refactor of training pipeline).
**Status of current bot**: GAP-ANALYSIS-PENDING (need fork output to confirm where the GRU contribution is wired into the live aggregator).

### T0.2 — Adopt CPCV + Deflated Sharpe Ratio for evaluation
**Source:** Agent #2 (indicator+ML), Agent #5 (practitioners). López de Prado *Advances in Financial Machine Learning*; Bailey & López de Prado SSRN 2460551.

Replace the current single fixed train/test split with **Combinatorial Purged Cross-Validation**. Apply **Deflated Sharpe Ratio** to penalise reported numbers for the implicit number of trials. Required before any post-T0 lift estimate is trustworthy.

**Effort**: ~3-5 days (CV harness; the broken backtest needs work in parallel).
**Risk**: zero (evaluation only, no bot change).
**Status of current bot**: GAP-ANALYSIS-PENDING — need to confirm whether `model_validator.py` already does anything beyond fixed split.

---

## Tier 1 — Highest-evidence interventions (apply after Tier 0 rebaseline)

### T1.1 — Meta-labeling on top of the indicator-vote primary
**Source:** Agent #2 (indicator+ML), top recommendation.

Treat the existing indicator vote as the **primary** (emits side). Train a gradient-boosted **secondary** classifier on triple-barrier labels: did the primary's call hit the up-barrier, down-barrier, or time-out first? Secondary emits go/no-go and size.

Highest documented lift for systems with **high recall, low precision** primary — the diagnostic of a 9-indicator vote. Caveats from QuantConnect: fails when primary already near-optimal, classes too imbalanced, or secondary overfits. Use purged k-fold CV (= T0.2 prerequisite).

**Effort**: ~1-2 weeks.
**Risk**: medium — affects signal aggregation. Behind feature flag, paper-only.
**Status of current bot**: GAP-ANALYSIS-PENDING.

### T1.2 — Portfolio-level realised-volatility targeting
**Source:** Agent #3 (risk), top "do this first" pick. Agent #5 (practitioners) consensus #1.

Compute rolling realised vol on hourly returns (7d or 30d window). Set annualised vol target (~30-40% conservative for SOL/BNB/ADA). Scale **gross exposure inversely to realised vol**. Sits *above* per-trade caps. When all symbols signal long together in a correlated regime, per-trade caps don't prevent portfolio blow-up; this does.

Crypto-specific replication (Wang et al. 2025 FRL): ~30% Sharpe uplift on weekly crypto momentum. Cederburg JFE 2020 hedge: factor-level vol targeting fails OOS, but **directional vol targeting on risk assets themselves** (which crypto qualifies for) survives.

**Effort**: ~3-5 days.
**Risk**: low — pure overlay; falls back to existing caps if vol estimator fails.
**Status of current bot**: GAP-ANALYSIS-PENDING — confirm risk module after commits `bef66cb` and `39352ba`.

### T1.3 — PostOnly maker on Bybit perps
**Source:** Agent #6 (execution).

Bybit perp taker = 0.055%, maker = 0.020%. Spot is flat 0.1%/0.1% — no benefit. ~7 bps round-trip savings on perp; at 200 round-trips/yr = **~140 bps/yr** flipping fee drag to neutral.

Use `timeInForce=PostOnly`. Add stale-quote timeout (re-quote after N seconds, or convert to taker if signal still valid) so bot doesn't silently miss fills.

**Effort**: ~2-3 days.
**Risk**: low — pure execution change. Worst case is a missed entry, recoverable.
**Status of current bot**: GAP-ANALYSIS-PENDING — confirm whether bot trades perps today and how orders are placed.

---

## Tier 2 — Lower-confidence or strategy-shaped interventions

### T2.1 — Carver-style continuous forecast combination (replace binary indicator vote)
**Source:** Agent #5 (practitioners). Carver, *Systematic Trading*; pysystemtrade.

Each indicator outputs a scaled forecast in [-20, +20], not just buy/sell/hold. Weighted-sum and cap. Carver shows ~doubles diversification multiplier vs binary voting. Current vote throws away signal magnitude.

**Effort**: ~1 week.
**Risk**: medium — replaces existing aggregator. Feature-flag and shadow-test.
**Status**: GAP-ANALYSIS-PENDING.

### T2.2 — Graduated drawdown de-risk
**Source:** Agent #3 (risk). Boyd et al., Stanford multi-period drawdown control.

Replace binary 20% kill-switch with continuous: 0.75x at 10% DD, 0.5x at 15%, flat at 20%. Same risk floor, smaller path discontinuity.

**Effort**: ~2 days.
**Risk**: low — strictly tighter than today's binary kill.
**Status**: GAP-ANALYSIS-PENDING — confirm exact DD trigger after commit `bef66cb`.

### T2.3 — Funding-rate awareness on perp entries
**Source:** Agent #6 (execution).

Pull `GET /v5/market/funding/history`. Gate perp entries on funding sign/magnitude. Skip-the-snapshot when |funding| > ~0.03%/8h on directional holds longer than one settlement. Worst-case ~55%/yr drag if persistently long into positive funding.

**Effort**: ~3 days.
**Risk**: low.
**Status**: GAP-ANALYSIS-PENDING.

### T2.4 — Half-Kelly sizing (only if Tier 0 rebaseline shows verified edge)
**Source:** Agent #3, Agent #6. MacLean/Ziemba/Blazenko Mgmt Sci 1992.

Replace fixed 2% per-trade cap with half-Kelly proportional to verified edge. Half-Kelly captures ~75% of optimal growth at ~50% of full-Kelly drawdown.

**Effort**: ~3-5 days.
**Risk**: high if edge estimate is wrong. **Hard-gated behind T0.1 + verified Sharpe** of the post-rebaseline strategy.
**Status**: blocked on T0.

### T2.5 — Time-series momentum standalone strategy (sleeve, not replacement)
**Source:** Agent #1 (factors). Moskowitz/Ooi/Pedersen JFE 2012; Grayscale 2024.

20-50d MA crossover or 28d-lookback / 5d-hold on per-asset price. 1.5-1.9 in-sample Sharpe; ~0.84 buy-and-hold benchmark. **Combine with T1.2 vol scaling** to mitigate momentum-crash regime turns.

**Effort**: ~1 week as a new strategy module.
**Risk**: medium — adds a new strategy that competes with existing aggregator. Run as a sleeve, not a replacement.
**Status**: GAP-ANALYSIS-PENDING — confirm whether a momentum sleeve already exists.

---

## DO NOT (literature-backed anti-patterns)

- **HMM / regime detection as alpha source.** Decorative. Fine as a filter label; never as the source of edge. (Quantopian 888-strategy study; FinRL crypto Sharpe collapse to 0.28.)
- **Full Kelly.** 33% probability of 50% drawdown before any doubling.
- **Markowitz / risk parity over 1/N** for SOL/BNB/ADA. (DeMiguel et al. RFS 2009; arXiv 2501.12841.) Pairwise correlations >0.7 — estimation error eats covariance optimisation.
- **Tight fixed-% stops (e.g. 1%).** (Kaminski & Lo JFE 2014.)
- **TWAP / VWAP / iceberg slicing at retail size.** Threshold is 3% of period volume; SOL/BNB/ADA hourly volume is in millions, retail orders are <0.1% of volume.
- **Spot maker rebate game.** Bybit spot is flat 0.1%/0.1% — no rebate to harvest.
- **Equity factor ports**: HML / value, BAB, equity pairs cointegration, short-interest, PEAD, calendar effects. Do not transfer to crypto.
- **Crypto carry as standalone strategy in 2026.** Basis compressed sharply post-spot-ETF launch. Treat as opportunistic, not core.
- **Mean-reversion as core engine.** Decay half-life is short. Use as a sleeve gated by regime, never as the engine.
- **Cross-sectional momentum at n=3.** Doesn't apply to a 3-asset book.

---

## Recommended sequencing

```
T0.1 (GRU rebaseline, ~1 day) ──┐
                                 ├── enables honest baseline
T0.2 (CPCV + DSR, 3-5 days) ─────┘
        │
        ├── T1.2 (vol target, 3-5 days) ─── parallelizable
        ├── T1.3 (PostOnly perps, 2-3 days) ─── parallelizable
        ├── T1.1 (meta-labeling, 1-2 weeks) ─── highest documented lift
        │
        ├── T2.1 — T2.5 — cherry-pick after T1.* show real lift
```

Each Ti gets its own forward-paper-test ≥7 days before promoting beyond paper mode.

---

## What this plan is NOT

- Not a green-light to start coding any Ti without explicit user pick.
- Not an audit of what's already implemented (gap-analysis fork output annotates that — sections are marked GAP-ANALYSIS-PENDING).
- Not a replacement for fixing the broken backtest (testnet contamination + signal-logic mismatch per audit memory) if the test gate ever needs to be backtest rather than forward-paper.

---

## Source files

Research reports — `docs/strategy/research-2026-04-29/`:
- `01-crypto-factors.md`
- `02-indicator-ml-hybrid.md`
- `03-risk-management-overlays.md`
- `04-equity-to-crypto-failure-modes.md`
- `05-retail-practitioners.md`
- `06-execution-sizing.md`

V0 empirical verification — same directory:
- `V0-FINDINGS-gru-metric-bug.md` — code archaeology proving the metric bugs
- `V0-RESULTS-no-edge.md` — persistence-baseline shootout results
- `V0-PERSISTENCE-results.json` — raw numbers
- `persistence_shootout.py` — reproducer script (run inside `crypto-bot-ml-prediction` container)

Patches landed:
- `c56765c` fix(ml-prediction): correct directional_accuracy metric (look-ahead + degenerate ref)
