# Phase B walk-forward gate — LIVE ensemble strategy

**Date:** 2026-05-20
**Strategy:** `services/trading-engine/app/aggregation/aggregator_core.CoreAggregator` (the path the auto-trader actually runs when `STRATEGY_MODE=ensemble`)
**Harness:** `backtesting/run_walk_forward_ensemble.py`
**Verdict:** **GATE FAIL on 0 / 5 symbols.** Live ensemble does not meet ADR-013 promotion thresholds. Auto-trader remains paused (`safety/EMERGENCY_STOP` active since 2026-05-19 23:01 UTC).

## Why this run exists

Prior walk-forward harnesses measured strategies that the auto-trader does NOT run:

| Harness | What it tests | Status |
|---|---|---|
| `run_walk_forward.py::phase1_strategy_prod` | hardcoded RSI(9)<20 + EMA20 + ADX>=20 rule | dead legacy. 0 trades / 4 folds × 5 symbols on 2026-05-19. |
| `run_walk_forward_sqzmom_v2.py` | Phase C canonical strategy (planned replacement) | FAIL 0/5 on 2026-05-06 (docs/phase_c_results_2026-05-06.md). Not deployed. |
| **`run_walk_forward_ensemble.py` (this run)** | **live 10-indicator weighted vote + gatekeeper + validator + regime modifier** | **FAIL 0/5 on 2026-05-20** |

ADR-013 Phase B-2 required "Replace `backtesting/IndicatorCalculator` with imports from `services/technical-analysis/app/indicators/`" and a Phase B-3 walk-forward harness that drives the live aggregator. The TA shim landed in `prod_indicators.py` 2026-05-06; the aggregator-driven harness did not exist until today.

## Setup

- Symbols: SOLUSDT, BNBUSDT, ADAUSDT, BTCUSDT, ETHUSDT
- Window: 180 days hourly, fetched from market-data-service (`http://localhost:8002`)
- `is_mainnet=True` filter applied (ADR-013 testnet-taint guard)
- Folds: 4 anchored, IS fraction 0.75 — same layout as `run_walk_forward_sqzmom_v2.py`
- Aggregator constructor: `CoreAggregator(enable_market_regime=True)` — matches live config (min_confidence=0.30, min_consensus=3, min_category_consensus=2, aggregation_threshold=0.15)
- ATR exits: 1.5×ATR stop / 3.0×ATR TP (R/R 2:1)
- DSR: `n_trials=8` (honest count = phase1_prod + sqzmom_v2 L0..L5 + ensemble)
- Engine: legacy fixed-fee BacktestEngine. **Realistic slippage / funding / Bybit fee asymmetry NOT modeled** (ADR-013 Phase B-4 still open). Treat metrics as generous, not pessimistic.

## Architecture notes (harness construction)

Aggregator and TA indicators both ship their code under a package named `app`. Cannot have both on `sys.path` simultaneously. Harness uses a dual-import scheme:

1. Load TA indicator classes first under TA's `app` namespace.
2. Purge `sys.modules["app.*"]` and remove TA from `sys.path`.
3. Add TE to `sys.path` and pre-register stubs for `app.models` / `app.config` / `app.monitoring.metrics` so aggregator_core's heavy `from app.models import ...` (which would otherwise drag in stat_arb_models) and its config validation are bypassed.
4. Load each aggregation submodule (gatekeeper, validator, voter, signal_cache, market_regime, aggregator_core) via `importlib.util.spec_from_file_location` so the real `app/aggregation/__init__.py` (which eagerly loads EnhancedAggregator + MultiTimeframeAnalyzer) does not run.
5. Bridge TA's `SignalType` enum to TE's `SignalAction` enum by string value.

The aggregator instance and all submodules in this harness are the *live* code. No port, no reimplementation.

## Per-symbol results

| Symbol | OOS bars (fold 3) | OOS Sharpe | IS Sharpe | OOS/IS | DSR | PF mean | Max DD% | Verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| SOLUSDT | 650 | +0.84 | -2.35 | 0.00* | 0.00 | 1.32 | 0.18 | FAIL |
| BNBUSDT | 800 | +0.50 | +2.44 | 0.21 | 0.00 | 0.28 | 0.13 | FAIL |
| ADAUSDT | 150 | +0.00 | -3.10 | 0.00 | 0.00 | 0.00 | 0.00 | FAIL |
| BTCUSDT (smoke) | 1080 | -0.14 | +0.33 | -0.41 | 0.00 | 0.46 | 0.16 | FAIL |
| BTCUSDT (full) | n/a | n/a | n/a | n/a | n/a | n/a | n/a | data-fetch failed (downloader returned 0 rows in full sweep; smoke run an hour earlier returned 4320) |
| ETHUSDT | 350 | +0.17 | +0.19 | 0.92 | 0.00 | 0.00 | 0.06 | FAIL |

\* Ratio = 0 when IS Sharpe ≤ 0 (defended by divide-by-zero protection — reflects the strategy losing in the IS slice too, not noise).

ADR-013 gate thresholds (all must hold): **OOS Sharpe ≥ 1.0, OOS/IS ratio ≥ 0.6, DSR ≥ 0.95, max DD < 30%, PF mean ≥ 1.2.**

## Headline pattern

The same shape Phase C found, on the same window, with a different strategy:

- **Fold 1 (oldest OOS) is weakest**; fold 3 (most recent OOS) often shows positive Sharpe (SOL +2.98, BNB +4.35, ETH +4.07). But fold-1 / fold-2 underperformance drags the mean below the gate.
- **DSR = 0.00 for all symbols.** Bailey & Lopez de Prado's deflated Sharpe penalty for `n_trials=8` and the observed Sharpe / sample-size combinations puts every result inside the noise band.
- **PF mean wrecked by 0-trade and all-winner folds.** Several folds returned `profit_factor=0` (engine reports 0 when no losses), which math-averages down to <1.2 even when individual folds were profitable.
- **OOS Sharpe never exceeds 1.0** on any symbol's fold-mean. ETH comes closest at +0.17 (worst signal here is the strategy lacks edge, not that the test is noisy).

The aggregator's gatekeeper aggressively blocked counter-trend trades (BUY in extreme BEARISH appeared dozens of times in logs). That is the live behavior — same gate the auto-trader runs.

## Bar-count anomaly

Bar counts in the table are smaller than expected for 180d × 24h × is_mainnet filter. SOL got 2600 total, BNB 3200, ADA 600, ETH 1400. BTC oscillated between ~4320 (smoke, hour earlier) and 0 (full sweep). Two compounding causes:

1. `data_downloader` paginates from market-data-service and stops at the first empty page; BTC's pagination cursor may have hit a gap in TimescaleDB.
2. Per-symbol mainnet history differs because the testnet→mainnet flip (2026-04-25) wasn't atomic across all five symbols' ingestion paths.

ADA's 600 total bars × is_mainnet filter is roughly consistent with "only post-April-25 data exists for this symbol" (~24 days × 24 = ~576). ETH's 1400 bars and SOL's 2600 bars suggest the `is_mainnet` column is sometimes set on pre-flip rows for those symbols. Worth an audit, but does not change the verdict — even on SOL's larger sample, OOS Sharpe is +0.84 < 1.0.

BTC's intermittent fetch failure should be reproduced before re-running. A retry with `BTCUSDT` only is cheap.

## Diagnostic discriminators

1. **Harness is not the bug.** SOL fold 3 produced 5 trades, ETH fold 3 produced 2 trades, BNB fold 3 produced 1 trade — the aggregator is firing through every gate (gatekeeper, validator, regime, confidence floor 0.30, consensus 3, category diversity 2) and reaching `aggregate_signals → BUY/SELL` on real signal. Smoke BTC produced 15 trades across folds.
2. **Aggregator confidence floor is doing real work.** The 0.30 min_confidence tightening landed 2026-05-15 specifically to filter low-conviction whipsaw entries; it is observably filtering most signals in this run, leaving only the highest-conviction ones (1–9 trades per fold). That filter behaves correctly.
3. **Edge is the bug.** Same conclusion Phase C reached: the squeeze-momentum-derived edge is decaying on hourly crypto in late 2025 — Q2 2026. The aggregator's 10-leg vote does not recover the edge; if anything, the multi-leg cancellation makes signals scarcer.
4. **ETH OOS/IS ratio 0.92** (in-sample +0.19, out-of-sample +0.17) is the most stable result — strategy is consistently *bad* in both halves, not overfit. Honest negative.

## Comparison: ensemble vs sqzmom_v2 (same gate, same data window)

| Symbol | Phase C sqzmom_v2 OOS Sharpe | Ensemble OOS Sharpe |
|---|---:|---:|
| SOL | +0.56 | +0.84 |
| BNB | +0.25 | +0.50 |
| ADA | +0.99 | +0.00 |
| BTC | -2.39 | -0.14 (smoke) |
| ETH | +2.88 | +0.17 |

Ensemble does NOT systematically outperform sqzmom_v2 — better on BNB/BTC/SOL, much worse on ADA and ETH. ETH's sqzmom_v2 outlier (+2.88) does not reappear under the ensemble, supporting the Phase C call that that result was cherry-pick risk.

## Decision

- **Auto-trader stays PAUSED.** Kill-switch `safety/EMERGENCY_STOP` remains in place. Don't restart on this evidence.
- **Existing positions stay open under their stops.** 3 SHORTs in flight as of pause (SOL, ADA, ETH per earlier session check). They will close on stop / TP / 48h time-stop. Not closing manually — risk-managed exits.
- **No "tune until gate passes."** ADR-013 line still holds: *"Don't tune to pass."* Every promotion to live trading must originate from a gate-passing walk-forward (Phase B) AND ≥30 days of forward paper trading (Phase D).
- **No strategy is gate-eligible right now**: phase1_prod is dead (0 trades), sqzmom_v2 is gate-fail, ensemble is gate-fail.

## Next-step options (NOT executed)

These are the live decisions. The data does not pick between them.

1. **Pivot strategy family.** Phase C closed on "consider mean-reversion or trend-pullback templates instead." Squeeze/breakout dead on 1h crypto in this regime. Build a mean-reversion or volatility-targeting template; run *this* harness on it.
2. **Drop frequency.** Move to 4h primary timeframe. Squeeze breakouts may need a slower clock post-2026. Cheap to test: re-run this harness with `INTERVAL="240"`.
3. **Realistic-sim retest.** Add Bybit perp fee asymmetry (maker -0.01% / taker +0.055%), 8h funding cost on perp longs, ATR-aware slippage. Probably makes results worse, not better — but rules out "fee fantasy" as a confound.
4. **Investigate bar-count anomaly.** Audit `is_mainnet` flag consistency in TimescaleDB across the 5 validated symbols. If pre-flip testnet rows are silently flagged mainnet, the SOL/BNB/ETH histories used here are partly tainted. Re-run after fix.
5. **Stop here, audit assumptions.** Three iterations (phase1, sqzmom_v2, ensemble) have failed on the same window. The research program may be wrong about crypto-momentum-on-1h having a tradable edge in this regime. Re-evaluate the whole milestone.

## Artifacts

- `backtesting/run_walk_forward_ensemble.py` — new harness, imports live aggregator.
- `backtesting/results/wf_ensemble_2026-05-20/*_summary.txt` — per-symbol fold tables.
- `backtesting/results/wf_ensemble_2026-05-20/_progress.log`, `_run.log` — raw run output.
- `.planning/quick/260520-0cc-build-aggregator-harness/260520-0cc-PLAN.md` — the plan for this work.

## Pre-promotion checklist (when any strategy eventually passes)

(unchanged from ADR-013 Phase D)

1. Walk-forward OOS Sharpe > 1.0 + DSR > 0.95 (this harness).
2. ≥30 days forward paper with positive Sharpe and live-vs-sim slippage Δ < 25%.
3. Restore per-trade cap to ≤ 2% (ADR-010 paper 10% reverted).
4. `safety/EMERGENCY_STOP` removed, kill-switch path verified.
5. `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY` set.
6. Mainnet Bybit keys with trade permissions.
7. `TRADING_MODE=LIVE` + `PAPER_TRADING_MODE=false` flipped together.

None of these are within reach today.
