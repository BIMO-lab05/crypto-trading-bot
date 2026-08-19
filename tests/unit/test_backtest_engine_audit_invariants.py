"""Promoted regression tests from the 2026-08-19 gap audit (audit/FINDINGS-GAP.md).

Three engine invariants that must hold regardless of strategy behavior:

1. Determinism — identical inputs give identical trades and equity curve
   (full trade-list compare, widened from the audit script's 8-field summary
   per final-review R5).
2. Equity reconciliation — final capital equals initial + Σ realized P&L
   − Σ entry fees − Σ funding, to the cent.
3. Random-walk — on drift-free GBM noise the engine must not show consistent
   positive expectancy (a persistent all-seeds-positive result is a
   look-ahead or accounting defect, never edge).

Runs on a 800-bar hourly BTCUSDT slice to keep suite runtime sane; the
full-year, fresh-process variants live in audit/run_all.py.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from audit._harness import (  # noqa: E402
    baseline_strategy,
    load_candles,
    make_engine,
)

N_BARS = 800


def _slice():
    return load_candles().iloc[:N_BARS].reset_index(drop=True)


def _trade_tuple(t):
    return (
        t.entry_time,
        t.exit_time,
        t.entry_price,
        t.exit_price,
        t.order_type.value,
        t.position_size,
        t.profit_loss,
        t.exit_reason,
    )


def test_determinism_full_trade_compare():
    data = _slice()
    r1 = make_engine().run_backtest(data, baseline_strategy, "det-1")
    r2 = make_engine().run_backtest(data, baseline_strategy, "det-2")
    assert [_trade_tuple(t) for t in r1.trades] == [_trade_tuple(t) for t in r2.trades]
    assert r1.equity_curve == r2.equity_curve
    assert r1.final_capital == r2.final_capital


def test_equity_reconciliation_to_the_cent():
    data = _slice()
    eng = make_engine()

    funding_deltas = []
    orig_apply = eng._apply_funding

    def logged_apply(price, time):
        before = eng.capital
        orig_apply(price, time)
        if eng.capital != before:
            funding_deltas.append(eng.capital - before)

    eng._apply_funding = logged_apply
    res = eng.run_backtest(data, baseline_strategy, "reconcile")

    entry_fees = sum(
        t.position_size * t.entry_price * eng._effective_fee_rate("MARKET")
        for t in res.trades
    )
    funding_total = -sum(funding_deltas)
    expected = (
        res.initial_capital
        + sum(t.profit_loss for t in res.trades)
        - entry_fees
        - funding_total
    )
    assert abs(res.final_capital - expected) <= 0.01


def test_no_profit_on_random_walk():
    real = _slice()
    log_ret = np.log(real["close"] / real["close"].shift(1)).dropna()
    sigma = float(log_ret.std())
    n = len(real)

    pnls = []
    for seed in range(5):
        rng = np.random.default_rng(seed)
        # Ito correction keeps the price-space expectation flat.
        steps = rng.normal(-0.5 * sigma**2, sigma, n)
        close = float(real["close"].iloc[0]) * np.exp(np.cumsum(steps))
        intrabar = np.abs(rng.normal(0.0, sigma, n))
        open_ = np.roll(close, 1)
        open_[0] = close[0]
        high = np.maximum(open_, close) * (1 + intrabar)
        low = np.minimum(open_, close) * (1 - intrabar)
        df = pd.DataFrame(
            {
                "timestamp": real["timestamp"].values,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": np.full(n, float(real["volume"].median())),
            }
        )
        res = make_engine().run_backtest(df, baseline_strategy, f"gbm-{seed}")
        pnls.append(res.total_profit_loss)

    positive = sum(1 for p in pnls if p > 0)
    # Consistent positive expectancy on noise = defect. With 5 seeds the
    # tripwire is every seed positive AND a positive mean.
    assert not (positive == 5 and float(np.mean(pnls)) > 0), (
        f"engine profits on random data: pnls={pnls}"
    )
