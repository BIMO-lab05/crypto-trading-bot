# tests/edge_lab/test_edge_lab_vol_breakout.py
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from conftest import T0, assert_shift_invariant  # noqa: E402
from edge_lab.candidates.vol_breakout import VARIANTS, generate_trades  # noqa: E402

H4 = 4 * 3_600_000
V = VARIANTS[0]


def _squeeze_then_pop(n=200, pop_at=100, direction=1.0):
    """Tight flat range (BB inside KC) then an explosive move."""
    rng = np.random.default_rng(5)
    close = np.empty(n)
    close[:pop_at] = 100.0 + rng.normal(0, 0.05, pop_at)  # very tight
    steps = direction * np.abs(rng.normal(1.5, 0.3, n - pop_at))
    close[pop_at:] = close[pop_at - 1] + np.cumsum(steps)
    open_ = np.concatenate([[close[0]], close[:-1]])
    return {
        "VUSDT": pd.DataFrame(
            {
                "ts_ms": [T0 + i * H4 for i in range(n)],
                "open": open_,
                "high": np.maximum(open_, close) + 0.05,
                "low": np.minimum(open_, close) - 0.05,
                "close": close,
                "volume": np.full(n, 1.0),
            }
        )
    }


def test_single_variant_declared():
    assert len(VARIANTS) == 1 and VARIANTS[0].name == "sqz_default"


def test_upward_pop_goes_long():
    trades = generate_trades(_squeeze_then_pop(direction=1.0), V)
    assert trades and trades[0].side == "LONG"


def test_downward_pop_goes_short():
    trades = generate_trades(_squeeze_then_pop(direction=-1.0), V)
    assert trades and trades[0].side == "SHORT"


def test_time_exit_bounds_holding():
    data = _squeeze_then_pop()
    trades = generate_trades(data, V)
    for t in trades:
        assert (t.exit_ts_ms - t.entry_ts_ms) <= 31 * H4


def test_no_squeeze_no_trades():
    """Steady high-vol trend without a squeeze phase: no entries."""
    rng = np.random.default_rng(6)
    n = 200
    close = 100.0 * np.cumprod(1 + rng.normal(0, 0.03, n))
    open_ = np.concatenate([[100.0], close[:-1]])
    data = {
        "VUSDT": pd.DataFrame(
            {
                "ts_ms": [T0 + i * H4 for i in range(n)],
                "open": open_,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": np.full(n, 1.0),
            }
        )
    }
    trades = generate_trades(data, V)
    assert len(trades) <= 2  # noise may fake one squeeze; a stream means a bug


def test_shift_invariance():
    data = _squeeze_then_pop(n=300)
    assert_shift_invariant(generate_trades, data, V, T0 + 200 * H4)
