# Backtest battery — first $10,000 baselines (ADR-029)

- **Date:** 2026-08-26 · **Branch:** `feature/account-10k` · **Capital:** $10,000 resolved from `shared/account.py` (no overrides passed anywhere)
- **Data:** offline Bybit-direct mainnet CSV exports (`backtesting/data/*_60m_365d_bybit.csv`, downloaded 2026-08-19 via REST — **not** the testnet-tainted TimescaleDB; the runner's taint guard was acknowledged with `--ack-mixed-data` on that provenance basis, and the runner stamps the output "NOT promotion-grade" accordingly)
- **Purpose:** replace the pre-2026-08-03 frictionless-$10k figures and the 2026-08-03→08-25 $100-floor-bound figures with the first cost-on, $10,000-scale measurements. Per ADR-029: this re-scale buys measurement fidelity, **not** edge — fees are bps of notional.

## Verdict

**No strategy shows edge at $10,000.** The deployed-ensemble analog fails every ADR-013 gate under the full realistic cost stack. The phase-1 filter stack suppresses essentially all trades. This matches the ADR-029 prediction and CLAUDE.md §2's standing table.

## 1. Phase-1 runner (`run_phase1_backtest.py`), 365d × 60m, per symbol

Cost model **legacy fixed**: 0.1%/side commission + 0.05% fixed slippage, no funding (engine logged `fee_mode=fixed, slippage_mode=fixed, funding_enabled=False`; the runner never engages `bybit_perp`/`atr_aware`).

| Symbol | Leg | Trades | Win % | PF | Net P&L | Final equity |
|---|---|---|---|---|---|---|
| BTCUSDT | Baseline (RSI+EMA) | 8 | 12.5 | 0.27 | −$32.35 | $9,966.05 |
| BTCUSDT | Phase 1 (filters) | 0 | — | — | $0.00 | $10,000.00 |
| ETHUSDT | Baseline | 14 | 35.7 | 1.03 | +$1.78* | $9,998.98 |
| ETHUSDT | Phase 1 | 0 | — | — | $0.00 | $10,000.00 |
| SOLUSDT | Baseline | 14 | 21.4 | 0.51 | −$34.14 | $9,963.07 |
| SOLUSDT | Phase 1 | 0 | — | — | $0.00 | $10,000.00 |
| BNBUSDT | Baseline | 11 | 45.5 | 1.48 | +$18.14 | $10,015.93 |
| BNBUSDT | Phase 1 | 1 | 100 | 0.00† | +$2.45 | $10,002.25 |
| ADAUSDT | Baseline | 12 | 25.0 | 0.62 | −$21.55 | $9,976.06 |
| ADAUSDT | Phase 1 | 1 | 0 | 0.00 | −$4.22 | $9,995.58 |

\* ETH runner's printed P&L (+$1.78) and final equity ($9,998.98) disagree by ~$2.80 — reported verbatim; runner-internal inconsistency, flagged.
† PF prints 0 when a leg has zero losses (known engine quirk — pool over trades, never average fold PFs).

Runner-printed Sharpe values (−29 to −46 on baselines, −221/−347 on 1-trade legs) are per-bar annualization artifacts at these trade counts — recorded in the raw outputs, not meaningful; use the walk-forward DSR instead.

**Reading:** the Phase-1 GATEKEEPER+VALIDATOR+ATR stack filters out 98–100 % of signals over a full year (0–1 trades per symbol). Its "improvement" lines (drawdown −100 %) reflect *never trading*, not skill. Baselines are flat-to-losing everywhere; BNB's +0.16 %/yr is noise at 11 trades.

## 2. Walk-forward, SOLUSDT 180d (4 folds, IS 75 %)

- **`phase1_strategy_prod` (`run_walk_forward.py`): 0 trades in all 4 OOS folds.** Gate FAIL (OOS Sharpe 0 < 1.0, OOS/IS 0 < 0.60, DSR nan < 0.95). The production phase-1 strategy simply does not fire on 2026 data.
  - Executed via a scratchpad driver that imports the runner's own functions verbatim and feeds the offline CSV (the runner hardcodes market-data-service `:8002`, which is down with TimescaleDB — zero repo edits made).
- **Deployed-ensemble analog (`run_walk_forward_ensemble.py --realistic-sim`)** — cost stack **fully realistic**: `fee_mode=bybit_perp` (taker 0.055 %/side), `slippage_mode=atr_aware` (5 % of ATR/price, 5 bp floor), `funding_enabled=True` (0.01 %/8h):

| Fold (OOS) | Bars | Trades | Win % | PF | Sharpe (ann.) | Max DD | PnL % |
|---|---|---|---|---|---|---|---|
| 0 | 275 | 4 | 50.0 | 1.95 | +3.10 | 0.08 % | +0.07 |
| 1 | 550 | 5 | 40.0 | 0.62 | −1.08 | 0.24 % | −0.07 |
| 2 | 825 | 11 | 27.3 | 0.53 | −2.86 | 0.44 % | −0.31 |
| 3 | 1100 | 16 | 25.0 | 0.73 | −1.46 | 0.49 % | −0.20 |
| **Aggregate** | — | **36** | ~30.6 pooled | **0.957** | **−0.576** | 0.49 % | — |

**Gates (ADR-013): ALL FAIL** — OOS Sharpe −0.58 < 1.0 · OOS/IS 0.00 < 0.60 · **DSR 0.002 < 0.95** · PF 0.957 < 1.20. New-run artifact preserved at `backtesting/results/wf_ensemble_2026-08-26_10k/SOLUSDT_summary.txt` (the runner's fixed output dir overwrote the 2026-05-21 historical summary; that file was restored from git).

## 3. Formerly blocked — cleared 2026-08-26 after the infra repair

The DB outage was repaired the same night (postgres/timescaledb recreated, market-data + api-gateway pools recycled, **52 h kline hole backfilled and verified complete** — 3,134/3,134 expected 1m bars per symbol across the outage window; the open 2026-08-22 232-min hole sat inside the verified window and is closed with it). Stack 14/14 healthy; trading-engine container untouched (isolation window preserved).

- **BNB walk-forward (`run_walk_forward.py --symbol BNBUSDT --days 180`): 0 trades in all 4 OOS folds — gate FAIL** (OOS Sharpe 0 < 1.0, DSR nan). Identical shape to SOL: `phase1_strategy_prod` does not fire on 2026 data.
- **Golden-parity killtest: PASSED (3/3)** after two repairs: the offline kernel loader had been broken since `42e2250` added the signal-funnel import to `aggregator_core` (fixed by loading the real stdlib-only module and deriving all stub gate values from the spec-loaded real `config.py` defaults), and the parity candle CSVs were refreshed through bybit-connector (20 files, 365d, mainnet-asserted; 1440m via the `D` interval). Stamp: `.planning/evidence/killtests/golden-parity-stamp.json` — offline replay ≡ live TA, non-HOLD action observed.
- Indicator/TA correctness thereby verified three ways: trading-engine suite (2,019 passed), killtests/replay stack, and live seam parity.

## Provenance note

These figures answer a **$10,000, cost-on** question. Phase-1 runner legs use the legacy fixed cost model (slightly pessimistic on fees vs Bybit taker: 0.1 % vs 0.055 %); the ensemble walk-forward uses the realistic Bybit-perp stack. Pre-2026-08-25 numbers elsewhere in the repo answer $100-era or frictionless questions — see CLAUDE.md §2's provenance rule.
