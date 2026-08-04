---
type: summary
status: complete
date: 2026-05-20
quick_id: 260520-0cc
description: build walk-forward harness driving live aggregator_core over historical OHLCV
---

# SUMMARY — build aggregator-driven walk-forward harness

## What was built

`backtesting/run_walk_forward_ensemble.py` — a walk-forward gate harness that imports the live `CoreAggregator` from `services/trading-engine/app/aggregation/aggregator_core.py` and drives it bar-by-bar across 180d hourly history per validated symbol. Closes the ADR-013 Phase B gap that prior harnesses (`run_walk_forward.py`, `run_walk_forward_sqzmom_v2.py`) left open: neither tested the strategy the auto-trader actually runs.

## Architecture

Dual-namespace import scheme. TA indicator classes and TE aggregator both register a package named `app`. Harness:
1. Loads TA indicators under TA's `app` namespace.
2. Purges `sys.modules["app.*"]`, removes TA from `sys.path`.
3. Pre-registers stubs for `app.models` / `app.config` / `app.monitoring.metrics` so aggregator_core's imports resolve without the heavy `models/__init__.py` stat_arb cascade or env-validated `Settings`.
4. Stubs `app.aggregation` as an empty package so the real `__init__.py` (which would eagerly load EnhancedAggregator + MultiTimeframeAnalyzer + httpx clients) does not run.
5. Loads aggregator submodules individually via `importlib.util.spec_from_file_location` in dependency order.

The aggregator instance is the live class. No port.

## Verdict

**FAIL on 0/5 symbols.** All gate criteria fail across SOL/BNB/ADA/ETH; BTC's full-sweep fetch returned 0 rows but smoke (run an hour earlier) returned 4320 rows and also FAIL'd. Same shape as Phase C: fold-1 weak, fold-3 strong, mean drags below the 1.0 OOS Sharpe gate. DSR=0.00 for every symbol. See `docs/phase_b_walkforward_ensemble_2026-05-20.md` for full table + diagnostics.

## Decisions captured

- Auto-trader stays PAUSED (`safety/EMERGENCY_STOP` active since 2026-05-19 23:01 UTC).
- Existing positions stay open under their stops; no manual closing.
- "Don't tune to pass" — no parameter tweaks against this dataset.
- Bar-count anomaly (`is_mainnet` filter inconsistency across symbols) flagged but does not change the verdict. Tracked as a follow-up.

## Files

- created: `backtesting/run_walk_forward_ensemble.py`
- created: `backtesting/results/wf_ensemble_2026-05-20/{BTCUSDT,SOLUSDT,BNBUSDT,ADAUSDT,ETHUSDT}_summary.txt`
- created: `backtesting/results/wf_ensemble_2026-05-20/_progress.log`
- created: `backtesting/results/wf_ensemble_2026-05-20/_run.log`
- created: `docs/phase_b_walkforward_ensemble_2026-05-20.md`
- created: `.planning/quick/260520-0cc-build-aggregator-harness/260520-0cc-PLAN.md`
- created: `.planning/quick/260520-0cc-build-aggregator-harness/260520-0cc-SUMMARY.md`
- created: `safety/EMERGENCY_STOP` (sentinel — kill-switch active; not technically part of this task but produced during it)

## Open follow-ups (NOT executed in this task)

- Audit `is_mainnet` flag consistency across 5 symbols in TimescaleDB. SOL/BNB/ETH bar counts suggest pre-flip rows leaking through the filter.
- Investigate intermittent BTC fetch returning 0 rows in `data_downloader`. Reproduce by re-running BTCUSDT alone.
- Realistic-sim layer (Bybit fee asymmetry + funding + ATR-aware slippage) is ADR-013 Phase B-4, still open. Current numbers are generous, not pessimistic.
- Strategic call: continue squeeze/momentum family vs. pivot to mean-reversion / trend-pullback. Three iterations failed; the research premise may be wrong.
