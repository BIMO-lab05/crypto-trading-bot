import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from conftest import DAY, T0, assert_shift_invariant  # noqa: E402
from edge_lab.candidates.lf_trend import VARIANTS, generate_trades  # noqa: E402

V = next(v for v in VARIANTS if v.name == "dc_20_10")


def _trending_up():
    """Flat 30 bars, a strong uptrend, then a reversal steep enough to breach
    the 10-day trailing low — one clean breakout entry, one clean exit, and a
    stop-and-reverse SHORT left open at data end (exercises the discard path).
    """
    rise = 100.0 * 1.01 ** np.arange(1, 61)
    fall = rise[-1] * 0.97 ** np.arange(1, 31)
    close = np.concatenate([np.full(30, 100.0), rise, fall])
    n = len(close)
    open_ = np.concatenate([[100.0], close[:-1]])
    return {
        "TUSDT": pd.DataFrame(
            {
                "ts_ms": [T0 + i * DAY for i in range(n)],
                "open": open_,
                "high": close * 1.002,
                "low": close * 0.998,
                "close": close,
                "volume": np.full(n, 1.0),
            }
        )
    }


def test_two_variants_declared():
    assert [v.name for v in VARIANTS] == ["dc_20_10", "dc_55_20"]


def test_uptrend_produces_long():
    trades = generate_trades(_trending_up(), V)
    assert trades and trades[0].side == "LONG"


def test_entry_is_next_bar_open():
    data = _trending_up()
    trades = generate_trades(data, V)
    t = trades[0]
    df = data["TUSDT"]
    idx = df.index[df["ts_ms"] == t.entry_ts_ms][0]
    assert t.entry_px == df["open"].iloc[idx]
    # the breakout close happened strictly before the entry bar
    assert df["close"].iloc[idx - 1] > df["high"].iloc[max(0, idx - 21) : idx - 1].max()


def test_open_position_at_end_not_emitted():
    data = _trending_up()  # reversal opens a SHORT that never closes by data end
    trades = generate_trades(data, V)
    for t in trades:
        assert t.exit_ts_ms <= data["TUSDT"]["ts_ms"].iloc[-1]


def test_few_trades_low_frequency(universe12):
    trades = generate_trades(universe12, V)
    # 12 symbols * 400 days of noise: Donchian should fire rarely
    assert len(trades) < 12 * 20


def test_shift_invariance(universe12):
    assert_shift_invariant(generate_trades, universe12, V, T0 + 250 * DAY)
