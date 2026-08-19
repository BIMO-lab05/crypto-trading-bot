import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

import pandas as pd

from edge_lab.maker_fill import apply_maker_fill
from edge_lab.trades import Trade


def _bars(prices):
    # (ts_ms, open, high, low, close) rows, 1h apart
    return pd.DataFrame(
        [
            {"ts_ms": 3_600_000 * i, "open": o, "high": h, "low": l, "close": c}
            for i, (o, h, l, c) in enumerate(prices)
        ]
    )


def test_long_fills_only_on_trade_through():
    bars = {
        "X": _bars(
            [
                (100, 101, 100, 100.5),  # t0: signal bar
                (100.4, 100.6, 99.0, 99.5),
            ]
        )
    }  # t1: low 99 < limit 100 → fills
    t = Trade("X", "LONG", 0, 3_600_000, 100.0, 99.5)
    res = apply_maker_fill([t], bars)
    assert res.missed == 0 and len(res.filled) == 1


def test_long_touch_only_is_missed():
    bars = {
        "X": _bars([(100, 101, 100, 100.5), (100.4, 100.6, 100.0, 100.5)])
    }  # low == limit: touch, no fill
    t = Trade("X", "LONG", 0, 3_600_000, 100.0, 100.5)
    res = apply_maker_fill([t], bars)
    assert res.missed == 1 and res.filled == []


def test_short_fills_on_upward_trade_through():
    bars = {
        "X": _bars([(100, 100.5, 99.5, 100), (100.1, 101.5, 100.0, 100.2)])
    }  # high 101.5 > limit 100 → fills
    t = Trade("X", "SHORT", 0, 3_600_000, 100.0, 100.2)
    res = apply_maker_fill([t], bars)
    assert res.missed == 0 and len(res.filled) == 1


def test_missing_next_bar_is_missed():
    bars = {"X": _bars([(100, 101, 100, 100.5)])}  # no bar after entry ts
    t = Trade("X", "LONG", 0, 3_600_000, 100.0, 100.5)
    assert apply_maker_fill([t], bars).missed == 1
