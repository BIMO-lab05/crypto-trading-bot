"""
Phase C-4: walk-forward gate validation for sqzmom_v2 across symbols.

For each symbol: download 180d, precompute features, split 4 folds (anchored,
IS-frac 0.75), run sqzmom_v2 layer L5 on OOS slice of each fold, report
fold metrics + DSR + ADR-013 gate verdict.

Run: python3 backtesting/run_walk_forward_sqzmom_v2.py
"""

import asyncio
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "strategies"))

import numpy as np
import pandas as pd

from data_downloader import HistoricalDataDownloader
from backtest_engine import BacktestEngine
from sqzmom_v2 import precompute_features, make_sqzmom_v2

# 2026-08-20: capital from the declaration of record (was a bare 10000.0
# hardcoded when the declared account was $100 — wrong then; ADR-029 has since
# set the declared size to $10,000 again, but shared/account.py stays
# authoritative — the routing is the fix, not the number).
from shared.account import PAPER_INITIAL_BALANCE  # noqa: E402,F401


SYMBOLS = ["SOLUSDT", "BNBUSDT", "ADAUSDT", "BTCUSDT", "ETHUSDT"]
DAYS = 180  # 6 months — needs to be post-2026-04-25 + walk-forward fold size
INTERVAL = "60"
FOLDS = 4
IS_FRAC = 0.75
LAYER = 5
N_TRIALS = 6  # honest number of variants explored: L0..L5


def calc_sharpe(equity_curve, periods_per_year=24 * 365):
    """ANNUALIZED Sharpe — display + OOS/IS ratio only, never DSR input
    (DSR takes raw per-bar returns). ddof=1 since 2026-08-20."""
    if len(equity_curve) < 2:
        return 0.0
    arr = np.asarray(equity_curve, dtype=float)
    rets = np.diff(arr) / arr[:-1]
    if rets.size < 2 or rets.std(ddof=1) == 0:
        return 0.0
    return float(rets.mean() / rets.std(ddof=1) * math.sqrt(periods_per_year))


def split_folds(data, n_folds, is_frac=0.75):
    n = len(data)
    folds = []
    for k in range(n_folds):
        split_end = round((k + 1) / n_folds * n)
        split_is = round(split_end * is_frac)
        if split_end - split_is < 1:
            continue
        folds.append((data.iloc[:split_is], data.iloc[split_is:split_end]))
    return folds


def per_bar_returns(equity_curve):
    """Per-bar fractional returns from an equity curve."""
    if len(equity_curve) < 2:
        return np.empty(0, dtype=float)
    arr = np.asarray(equity_curve, dtype=float)
    return np.diff(arr) / arr[:-1]


def per_bar_sharpe(rets):
    """Per-bar (NOT annualized) Sharpe, ddof=1. 0.0 for degenerate series."""
    rets = np.asarray(rets, dtype=float)
    if rets.size < 2:
        return 0.0
    sd = float(rets.std(ddof=1))
    if sd == 0.0:
        return 0.0
    return float(rets.mean() / sd)


def deflated_sharpe_per_bar(oos_returns, fold_bar_sharpes, num_trials):
    """DSR via the canonical Bailey & Lopez de Prado kernel
    (services/risk-metrics-service/app/sharpe_metrics.py), reached through
    killtests.offline_ensemble._load_kernels — the same spec-load mechanism
    edge_lab/gate2.py uses from host-run backtesting code.

    Feed RAW PER-BAR OOS returns. The kernel derives the per-bar Sharpe
    itself (mean/std, ddof=1) and applies the full machinery: sqrt(V)
    expected-max threshold plus the skew/kurtosis standard-error term.
    Never feed an ANNUALIZED Sharpe here — the pre-2026-08-20 local
    implementation paired an annualized SR with the per-bar sqrt(n-1)
    z-statistic, which made DSR a step function (0.000 or 1.000, nothing
    between).

    trial_sharpes_variance = variance (ddof=1) of the per-fold PER-BAR
    Sharpes of this one config. Honest limitation: Bailey/LdP want the
    Sharpe dispersion across the `num_trials` variants tried during
    selection, but per-trial return series were never logged for the
    historical variants, so fold-level dispersion of the surviving config
    is the only estimate available here. It understates deflation if the
    discarded variants dispersed more than the folds do.

    Returns NaN (gate-failing) with fewer than 2 folds or 2 return
    observations — never a silent zero-variance pass-through.
    """
    from killtests.offline_ensemble import _load_kernels

    rets = np.asarray(oos_returns, dtype=float)
    valid = [s for s in fold_bar_sharpes if np.isfinite(s)]
    if rets.size < 2 or len(valid) < 2:
        return float("nan")
    kernels = _load_kernels()
    return float(
        kernels["deflated_sharpe_ratio"](
            rets,
            num_trials=max(2, int(num_trials)),
            trial_sharpes_variance=float(np.var(valid, ddof=1)),
        )
    )


async def run_symbol(symbol):
    print(f"\n=== {symbol} ===")
    downloader = HistoricalDataDownloader(market_data_url="http://localhost:8002")
    raw = await downloader.download_historical_data(symbol=symbol, interval=INTERVAL, days=DAYS)
    await downloader.close()

    if raw is None or len(raw) == 0:
        print(f"  FAIL: no data for {symbol}")
        return None

    if "timestamp" in raw.columns:
        ts = pd.to_datetime(raw["timestamp"], utc=True, errors="coerce")
        raw = raw.assign(timestamp=ts).set_index("timestamp")

    enriched = precompute_features(raw)
    folds = split_folds(enriched, FOLDS, IS_FRAC)

    is_sharpes = []
    oos_sharpes = []
    oos_bar_rets = []
    oos_fold_bar_sharpes = []
    fold_rows = []
    for k, (is_slice, oos_slice) in enumerate(folds):
        # IS run
        is_engine = BacktestEngine(initial_capital=PAPER_INITIAL_BALANCE)
        strategy = make_sqzmom_v2(layer=LAYER)
        is_engine.run_backtest(is_slice, strategy, strategy_name=f"is_{k}")
        is_sharpe = calc_sharpe(is_engine.equity_curve)
        is_sharpes.append(is_sharpe)

        # OOS run
        oos_engine = BacktestEngine(initial_capital=PAPER_INITIAL_BALANCE)
        oos_result = oos_engine.run_backtest(oos_slice, strategy, strategy_name=f"oos_{k}")
        oos_sharpe = calc_sharpe(oos_engine.equity_curve)
        oos_sharpes.append(oos_sharpe)
        oos_bar_rets.append(per_bar_returns(oos_engine.equity_curve))
        oos_fold_bar_sharpes.append(per_bar_sharpe(oos_bar_rets[-1]))

        fold_rows.append(
            (
                k,
                len(oos_slice),
                len(oos_engine.trades),
                getattr(oos_result, "win_rate", 0.0),
                oos_sharpe,
                getattr(oos_result, "max_drawdown_pct", 0.0),
                getattr(oos_result, "profit_factor", 0.0),
                getattr(oos_result, "total_profit_loss_pct", 0.0),
            )
        )

    print(
        f"  {'Fold':<6} {'Bars':<7} {'Trades':<8} {'WR%':<7} "
        f"{'Sharpe':<8} {'DD%':<8} {'PF':<6} {'PnL%':<7}"
    )
    for r in fold_rows:
        k, b, t, wr, s, dd, pf, pl = r
        print(f"  {k:<6} {b:<7} {t:<8} {wr:<7.1f} {s:<8.2f} {dd:<8.2f} {pf:<6.2f} {pl:<7.2f}")

    is_mean = float(np.mean(is_sharpes)) if is_sharpes else 0.0
    oos_mean = float(np.mean(oos_sharpes)) if oos_sharpes else 0.0
    is_oos_ratio = (oos_mean / is_mean) if is_mean > 0 else 0.0
    # Disjoint OOS windows at FOLDS=4 / IS_FRAC=0.75 — the concatenation
    # is the stitched per-bar OOS return series for the canonical kernel.
    all_oos_rets = np.concatenate(oos_bar_rets) if oos_bar_rets else np.empty(0, dtype=float)
    dsr = deflated_sharpe_per_bar(all_oos_rets, oos_fold_bar_sharpes, N_TRIALS)
    print(
        f"  IS Sharpe mean (ann): {is_mean:.2f}  "
        f"OOS Sharpe mean (ann): {oos_mean:.2f}  "
        f"OOS/IS ratio: {is_oos_ratio:.2f}  "
        f"DSR (per-bar kernel, n_trials={N_TRIALS}): {dsr:.2f}"
    )

    # Gate
    fail = []
    if oos_mean < 1.0:
        fail.append(f"OOS Sharpe {oos_mean:.2f} < 1.00")
    max_dd = max((abs(r[5]) for r in fold_rows), default=0.0)
    if max_dd > 30.0:
        fail.append(f"max DD {max_dd:.1f}% > 30%")
    pfs = [r[6] for r in fold_rows if r[2] > 0]
    if pfs and float(np.mean(pfs)) < 1.2:
        fail.append(f"PF mean {float(np.mean(pfs)):.2f} < 1.2")
    if is_oos_ratio < 0.6:
        fail.append(f"OOS/IS ratio {is_oos_ratio:.2f} < 0.60")
    # Real gate as of 2026-08-20 (canonical per-bar kernel; NaN fails via
    # the `not >=` form). Pre-2026-08-20 results through this gate are VOID
    # — the old local DSR fed an annualized Sharpe into a per-bar
    # sqrt(n-1) z-statistic (step function) AND dropped the sqrt(V)
    # multiplier and skew/kurtosis term.
    if not (dsr >= 0.95):
        fail.append(f"DSR {dsr:.2f} < 0.95")

    if fail:
        print(f"  GATE FAIL: {', '.join(fail)}")
    else:
        print("  GATE PASS")
    return {"symbol": symbol, "fail": fail}


async def main():
    print(f"=== Phase C-4 walk-forward gate: sqzmom_v2 L{LAYER} ===")
    print(f"days={DAYS}  folds={FOLDS}  is_frac={IS_FRAC}  layer={LAYER}  n_trials={N_TRIALS}")

    results = []
    for symbol in SYMBOLS:
        r = await run_symbol(symbol)
        if r:
            results.append(r)

    print("\n=== Summary ===")
    pass_count = sum(1 for r in results if not r["fail"])
    fail_count = len(results) - pass_count
    print(f"  PASS: {pass_count} / {len(results)}")
    print(f"  FAIL: {fail_count} / {len(results)}")
    for r in results:
        verdict = "PASS" if not r["fail"] else "FAIL"
        print(f"  {r['symbol']}: {verdict}  {' | '.join(r['fail'])}")


if __name__ == "__main__":
    asyncio.run(main())
