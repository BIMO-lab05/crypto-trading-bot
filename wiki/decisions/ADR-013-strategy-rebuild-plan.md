---
type: decision
status: proposed
date: 2026-05-06
context: "audit shows zero edge; 25 strategy files mostly orphaned; backtest validates a different strategy than what runs live; sqzmom claims unreproducible"
deciders: [operator]
tags: [decision, adr, strategy, research]
created: 2026-05-06
updated: 2026-05-06
---

# ADR-013: Strategy rebuild plan grounded in 2026 crypto-bot research

## Context

Audit on 2026-05-06 revealed several load-bearing defects in the trading stack that compound into "no edge in production":

1. **HybridStrategyRouter never picked TRENDING** — `detect_regime` looked for ADX in `atr_signal.metadata['adx']`, which never existed because the aggregator never fetched ADX. Router defaulted to RANGING regardless of market state. Live SOL was ADX=38.89 (STRONG_TREND BULLISH); router saw nothing.
2. **`trades` table empty in 2026 paper-trading** — ORM `Trade(Base)` model drifted from live DB schema (`action`/`order_type`/`total_cost`/`position_id` columns don't exist; live has `side`/`total_value`/`metadata`-jsonb). Every `log_trade` ORM insert raised silently into a swallowing except. Performance Analytics had zero input data, hence "Analytics so bad" — GIGO not query bug.
3. **Backtest tests a different strategy than what runs live** — `backtesting/run_phase1_backtest.py` has its own `IndicatorCalculator` class with stock-tuned RSI 14/30/70, while `services/technical-analysis/app/indicators/rsi.py` uses crypto-tuned 9/80/20. Aligned 2026-05-06 in the runner; deeper alignment (importing prod indicator code) is pending.
4. **Phase 1 backtest produces 0–6 trades over 90 days × 3 symbols, 1 win out of 6.** RSI extremes + EMA + GATEKEEPER + VALIDATOR + ATR cascade rejects nearly everything — bare RSI extremes are not edge in crypto, and crypto-tuned 80/20 makes the trigger even rarer than 70/30.
5. **25 strategy files in `services/trading-engine/app/strategies/` and the live orchestrator has 0 registrations.** Production goes through `multi_strategy_ensemble` + `aggregator_core` + `signal_aggregator`. The other 24 files are decorative.
6. **Sqzmom info-endpoint marketed metrics ("+2706% Sharpe 4.76 SOL")** are not reproducible via the project's own backtest runner. Either tuned-on-train-set or computed via different code path.
7. **Live ensemble HOLD-locked** at score 0.16 / conf 0.16 against floor 0.20. Math is correct; with 7 voting legs at typical conf 0.16–0.50, mixed BUY/SELL/HOLD splits cap aggregate at ~0.27. Indicator confidence calibration, not the floor, is the structural ceiling.

Parallel research (web-search-researcher + general-purpose agents, 2026-05-06) surveyed Freqtrade/Hummingbot/NautilusTrader edge sources and the Squeeze Momentum literature. Headline:

- **No peer-reviewed walk-forward study with ≥6mo OOS, Sharpe>1, MaxDD<30% on SOL/BNB/ADA on 1h candles was found.** Influencer-tier "+2700%" claims excluded. Treat any 1h SOL/BNB/ADA Sharpe>1 claim as unverified until generated in-house with proper walk-forward.
- **Working sqzmom stacks** universally add: 200-EMA trend filter, ADX>20–25 rising, volume>1.2× SMA(20) on release, multi-timeframe (4h confirms 1h), entry at second consecutive momentum bar (not release bar). Failure modes: choppy mean-reverting, post-news whipsaw, prolonged consolidation where BB never re-exits KC.
- **Empirical 1h crypto indicator defaults** (≥2 sources agree): RSI 14 (period unchanged) but 80/20 thresholds, EMA fast/slow 9/21 with 50-EMA trend filter, ATR(14), Bollinger 20/2σ, Keltner 20/1.5×ATR, MACD 12/26/9, StochRSI 14/14/3/3.
- **Killer backtest→live defects** in crypto: signal-on-current-close-fill-same-bar (look-ahead), HTF resamples including partial bars (repaint), slippage modeled at zero, fee asymmetry (Bybit maker -0.01% / taker +0.055%), funding cost ignored on perp longs (8h compounding), live-only data (Freqtrade orderbook/funding accessors) leaking into backtest.

## Decision

Three-phase rebuild rather than continued tuning of the existing tangle.

### Phase A — Stabilize (2026-05-06 to 2026-05-13, mostly done)

Fixes already landed in this audit cycle:

- ADR-010: documented paper `max_risk_per_trade` 0.10 vs live 0.02 contract.
- Concurrent-open dedup with 60s cooldown in `auto_trader._claim_open_slot`.
- Sqzmom stops ATR-derived via `/api/v1/indicators/atr/{symbol}` with fail-open to fixed-pct.
- `/ready` endpoint added (handlers/health.py + main.py).
- EMERGENCY_STOP broken-mount detector at loop start (operator follow-up: rmdir + force-recreate).
- ADX leg in signal_aggregator + hybrid router reads `indicators['ADX'].value` directly.
- log_trade rewritten to bypass broken ORM and INSERT raw SQL against live schema.
- Backtest data_downloader paginates with end_time cursor; runner aligned to crypto-tuned RSI 9/80/20.
- Sqzmom integration ADX gate (>=20, direction agreement) + volume gate (ratio>=1.2).

### Phase B — Honest backtesting (target 2026-05-13 to 2026-05-27)

1. **Kill 22 of the 25 strategy files.** Keep only: `multi_strategy_ensemble.py` (live path), `sqzmom_strategy_integration.py` (active leg), and one of `mean_reversion.py` / `mean_reversion_strategy.py` (whichever the hybrid router actually uses). Move the rest to `_archive_strategies/`.
2. **Replace `backtesting/IndicatorCalculator` with imports from `services/technical-analysis/app/indicators/`.** Either Python imports if shape is compatible, or hit a local copy of the TA service via httpx in test runs. Anything else means the backtest is decorative — it's been validating a parallel strategy for at least 6 months of file history.
3. **Walk-forward harness**: add `backtesting/run_walk_forward.py` that does anchored or rolling walk-forward (in-sample 75% / out-of-sample 25%, ≥4 folds, fold size ≥30 days each), reports per-fold Sharpe / max DD / profit factor + DSR. Acceptance gate: OOS Sharpe / IS Sharpe ratio > 0.6, OOS Sharpe > 1.0, OOS max DD < 30%, DSR > 0.95.
4. **Realistic simulator**: model slippage as ATR-aware (≥0.05% in low vol, scale with spread), fee asymmetry (maker rebate / taker cost from current Bybit perp schedule), funding cost on perp longs at 8h cadence (use Bybit funding-rate history), partial fills based on per-bar volume.
5. **Pre-2026-04-25 candle taint**: enforce in code — refuse to backtest spans crossing the testnet→mainnet flip date unless the operator passes `--ack-mixed-data`.

### Phase C — Strategy synthesis (target 2026-05-27 to 2026-06-15)

Build ONE strategy aligned with the research findings, not 25 alternates. Specification:

- **Entry**: Squeeze Momentum (BB 20/2.0, KC 20/1.5–2.0, momentum lookback 12) release on second consecutive momentum bar in the breakout direction.
- **Filters (all must pass)**:
  - 200-EMA trend filter (long only above, short only below).
  - ADX(14) ≥ 20 with +DI > -DI for long, -DI > +DI for short.
  - Volume on the trigger bar > 1.2 × SMA(20) of volume.
  - 4h timeframe sqzmom direction agrees with 1h trigger.
- **Sizing**: 2% per-trade cap (live; paper retains ADR-010 10% only for sizing experiments). ATR(14)-based.
- **Stops**: 1.5×ATR initial. Partial 50% off at 1R, move stop to breakeven, trail remainder by 2×ATR. Hard 48h time-stop (already enforced).
- **Skip-when**: Bollinger Bandwidth in bottom 20th percentile and not yet expanding (low-vol fizzle); ADX falling and < 20 (regime exit).
- **Continuous-strength signal score**: replace any binary "released yes/no" with `clip(|momentum| / rolling_stdev(momentum, 50), 0, 3) / 3 * sign_agreement(momentum, ema50_slope) * volume_ratio_clipped`. Boosts trade rate without sacrificing win-rate per the agent research.

### Phase D — Forward paper validation (rolling, indefinite)

- Deploy the Phase C strategy to paper-trading live alongside any incumbent.
- Daily log of signals, fills, P&L, slippage realized vs simulated, DSR rolling 30/60/90.
- Promotion to LIVE gated by:
  1. Walk-forward OOS Sharpe > 1.0 + DSR > 0.95 (Phase B harness).
  2. ≥30 days forward paper with positive Sharpe and live-vs-sim slippage Δ < 25%.
  3. Pre-live ADR documenting the per-capital `max_risk_per_trade` (must restore ≤ 2% per ADR-010).
  4. Operator explicit `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY` (already enforced in trading-engine boot).

## Consequences

- 22 strategy files deleted; CLAUDE.md gotcha about "25 strategy files, only ensemble fires" no longer applicable.
- Backtest harness becomes truthful — running it actually validates the live strategy.
- One strategy under one config; everything else is research, isolated to `_archive_strategies/`.
- Profitability is **not** promised by this ADR. The plan is to build the apparatus that can answer the profitability question honestly, not to declare a result. Skill rule: "profitability is empirical, evidenced by walk-forward and forward-paper, not edicts."
- Limitation surfaced: no symbol-specific published walk-forward exists for SOL/BNB/ADA on 1h. The first honest in-house backtest on the rebuilt harness IS the first credible answer.

## Related

- `wiki/decisions/ADR-001-LSTM-removed.md` (V0 directional-accuracy leakage incident — same lesson)
- `wiki/decisions/ADR-010-max-risk-per-trade-paper-bump.md`
- `wiki/decisions/ADR-011-paper-deterministic-execution.md`
- `wiki/decisions/ADR-016-http-not-events.md`
- `.claude/skills/trading-strategy-dev/references/leakage-tests.md`
- `.claude/skills/trading-strategy-dev/references/acceptance-gates.md`
- 2026-05-06 research synthesis (web-search-researcher + general-purpose agents) — sources cited in respective audit comments

## Phase C update — 2026-05-06 (gate FAIL, do NOT advance)

Phase C synthesis built and validated:

- `backtesting/strategies/sqzmom_v2.py` — TTM Squeeze + 200-EMA + ADX(>=20)+DI agreement + volume>1.2× + 4h-MTF + 1.5×ATR stop / 3×ATR TP. Causal precompute, prefix-stability leakage test PASSED.
- `backtesting/sqzmom_v2_layer_sweep.py` — L0..L5 isolation sweep (SOL 90d): all layers produce trades, PF stays < 1.0 across stack; rising win-rate (26→38%) on L4→L5 ATR-stop transition.
- `backtesting/run_walk_forward_sqzmom_v2.py` — walk-forward gate (4 folds, IS-frac 0.75) on validated 5 symbols, 180d hourly.

**Result: GATE FAIL on 0 / 5 symbols.**

| Symbol | OOS Sharpe | DSR | Gate |
|--------|------------|-----|------|
| SOL | 0.56 | 0.00 | FAIL |
| BNB | 0.25 | 0.00 | FAIL |
| ADA | 0.99 | 0.00 | FAIL |
| BTC | -2.39 | 0.00 | FAIL |
| ETH | 2.88 | 1.00 | FAIL (PF mean only) |

Strategy does **not** advance to Phase D paper validation. ETH outlier (4 of 5 gate criteria pass) is rejected as cherry-pick risk per skill rule "Don't tune to pass."

Per-fold structure shows fold 1 (oldest OOS) consistently outperforms fold 3 (newest OOS) → suggests regime drift in early 2026. Squeeze-breakout templates may be decaying on hourly crypto.

Detailed report: `docs/phase_c_results_2026-05-06.md`.

**Phase C status:** complete-with-negative-result. Code, harness, and gate are all working as designed; the proposed alpha is not present at the proposed time-frame. Rebuild iteration required before Phase D — see "Next-step options" in the results doc. No Phase D promotion.
