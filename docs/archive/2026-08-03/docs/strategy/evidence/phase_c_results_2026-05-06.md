# Phase C-4 walk-forward gate — sqzmom_v2 results

**Date:** 2026-05-06
**Strategy:** `backtesting/strategies/sqzmom_v2.py` (LazyBear TTM Squeeze + 200-EMA + ADX(>=20)+DI agreement + volume>1.2× + 4h MTF + 1.5×ATR stop / 3×ATR TP)
**Harness:** `backtesting/run_walk_forward_sqzmom_v2.py`
**Verdict:** **GATE FAIL on 0 / 5 symbols.** Strategy does NOT advance to Phase D paper validation.

## Setup

- Symbols: SOLUSDT, BNBUSDT, ADAUSDT, BTCUSDT, ETHUSDT (validated set)
- Window: 180 days (post-2026-04-25 testnet flip)
- Interval: 1h candles, downloaded from market-data-service
- Folds: 4 anchored, IS fraction 0.75
- Engine: legacy fixed-fee mode (no realistic-sim flag) — pre-TX-cost results
- Filter layer: L5 (all stacked: squeeze release + 200-EMA + ADX + volume + 4h-MTF + ATR stops)
- DSR: `n_trials=6` (honest count of L0..L5 explored)

## Layer sweep (SOL 90d hourly)

Verifies each filter narrows trades but doesn't kill the strategy outright:

| Layer | Trades | Win % | P&L % | Max DD % | PF |
|-------|--------|-------|-------|----------|----|
| L0 (squeeze + mom-2bar) | 109 | 26.6 | -0.94 | 1.10 | 0.79 |
| L1 (+ 200-EMA) | 97 | 26.8 | -0.76 | 1.03 | 0.81 |
| L2 (+ ADX≥20) | 84 | 23.8 | -1.01 | 1.29 | 0.69 |
| L3 (+ volume) | 65 | 26.2 | -0.58 | 0.86 | 0.78 |
| L4 (+ 4h MTF) | 46 | 26.1 | -0.42 | 0.73 | 0.77 |
| L5 (+ ATR stops) | 42 | 38.1 | -0.20 | 0.60 | 0.91 |

Win-rate climbs L4→L5 (26→38%) on the ATR-stop transition; the fixed 2/5% stops at L4 close winners early. PF stays below 1.0 across all layers — **strategy is making bets, not winning them**. Filter stack is not the problem; the entry signal lacks edge.

## Walk-forward per symbol

Single-fold trade counts low (3–25). Stitching all OOS folds:

| Symbol | OOS Sharpe | IS Sharpe | OOS/IS | DSR | PF mean | Max DD% | Verdict |
|--------|------------|-----------|--------|-----|---------|---------|---------|
| SOL | 0.56 | -0.80 | 0.00* | 0.00 | 1.08 | 0.22 | FAIL |
| BNB | 0.25 | -2.07 | 0.00* | 0.00 | 1.17 | 0.18 | FAIL |
| ADA | 0.99 | 0.75 | 1.32 | 0.00 | 1.20 | 0.25 | FAIL |
| BTC | -2.39 | -2.32 | 0.00* | 0.00 | 0.89 | 0.22 | FAIL |
| **ETH** | **2.88** | **2.33** | **1.23** | **1.00** | 1.00 | 0.15 | FAIL (PF only) |

*Ratio = 0 when IS Sharpe ≤ 0 (defended by the gate's divide-by-zero protection). Reflects the strategy losing in the IS slice too; not noise.

ADR-013 gate thresholds: OOS Sharpe ≥ 1.0, max DD < 30%, PF mean ≥ 1.2, OOS/IS ratio ≥ 0.6, DSR ≥ 0.95. **All five must hold.**

## Per-fold structure

Repeats across symbols: fold 1 (oldest OOS) outperforms fold 3 (newest OOS). E.g. SOL fold 1 Sharpe 3.14, fold 3 -1.83. Suggests **regime drift in late 2026** — momentum-breakout strategies that worked October–January don't work April–May. ETH is the only symbol where the trend persists across folds (fold 1 Sharpe 9.19, fold 3 0.18).

## ETH-only outlier

ETH passes 4 of 5 gate criteria (OOS Sharpe 2.88, IS Sharpe 2.33, ratio 1.23, DSR 1.00, max DD 0.15%). Trips only on PF mean = 1.00, dragged by fold 0 having 2 trades both winning (PF undefined → engine emits 0).

**Caution:** one symbol passing 4/5 gate criteria out of five attempted is exactly the kind of result selection bias produces. With `n_trials=6` already in the DSR formula, ADR-013's 0.95 threshold is the right place to stop. Promoting ETH alone would be cherry-picking the only chart that fits — declining.

## Diagnostic discriminators

1. **Harness is not the bug.** The permissive RSI 50/50 strategy yields 29 trades in 240 SOL bars at the expected ~50% rate. Pipeline plumbing verified.
2. **Filter stack is not the bug.** L0 (no filters) yields 109 trades on SOL 90d but PF 0.79. Stacking filters narrows count and lifts win-rate (26→38%) without flipping PF above 1.
3. **Leakage is not the bug.** Prefix-stability test passed for all 14 features (squeeze_off, sqz_momentum, sqz_color, mom_pos_2, mom_neg_2, ema_*, vol_ratio, atr_14, adx_14, plus_di, minus_di, mtf4h_sqz_color, mtf4h_sqz_momentum). Causal precompute confirmed.
4. **Edge is the bug.** The squeeze + 2-bar momentum + ADX + volume + 4h MTF + ATR stop combination, on hourly crypto data over the validated symbol set, has no exploitable post-cost edge in the 2025-Q4 → 2026-Q2 window. Reading the per-fold structure: the strategy may have worked early-period and decayed.

## Decision per skill rules

> "Strategies are alpha-claims, not type-checks. Backtest + paper-trade evidence required."
> "Don't tune to pass."

Strategy does NOT advance to Phase D. Phase C synthesis is **complete-with-negative-result**: the canonical sqzmom + ADX + volume + MTF + ATR stack is shippable code (causal, tested, integrated) but **not shippable alpha** as currently parameterized.

## Next-step options (NOT executed)

- **Drop frequency.** Move to 4h primary, 1d MTF — squeeze breakouts may need slower clock on crypto post-2026.
- **Replace momentum trigger.** sqz_color "second consecutive lime/green" may chase entries; explore `momentum > 0 AND momentum_growth_decelerating` as the entry instead.
- **Test with realistic-sim ON.** Current run uses fixed 0.1% commission, no funding. ETH PF=1.00 may go below 1.0 once Bybit-perp asymmetric fees + funding are applied — that's a stronger reject, not a weaker one. (i.e., result is generous, not pessimistic.)
- **Per-symbol regime gating.** Strategy works ETH but not BTC despite similar squeeze dynamics — investigate if BTC's lower vol breaks the ATR stop assumptions.
- **Stop here, audit assumptions.** If three iterations don't pass the gate, the entire research program may be wrong (squeeze-breakout dead in current crypto regime). Consider mean-reversion or trend-pullback templates instead.

## Files committed

- `backtesting/prod_indicators.py` — added `SqueezeMomentumIndicator` re-export
- `backtesting/strategies/sqzmom_v2.py` — strategy + `precompute_features` + `make_sqzmom_v2(layer)`
- `backtesting/sqzmom_v2_layer_sweep.py` — L0..L5 sweep driver
- `backtesting/run_walk_forward_sqzmom_v2.py` — walk-forward + DSR + gate per symbol
- `docs/phase_c_results_2026-05-06.md` — this report
