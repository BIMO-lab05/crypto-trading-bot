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
    res = apply_maker_fill([t], bars, bar_interval_ms=3_600_000)
    assert res.missed == 0 and len(res.filled) == 1


def test_long_touch_only_is_missed():
    bars = {
        "X": _bars([(100, 101, 100, 100.5), (100.4, 100.6, 100.0, 100.5)])
    }  # low == limit: touch, no fill
    t = Trade("X", "LONG", 0, 3_600_000, 100.0, 100.5)
    res = apply_maker_fill([t], bars, bar_interval_ms=3_600_000)
    assert res.missed == 1 and res.filled == []


def test_short_fills_on_upward_trade_through():
    bars = {
        "X": _bars([(100, 100.5, 99.5, 100), (100.1, 101.5, 100.0, 100.2)])
    }  # high 101.5 > limit 100 → fills
    t = Trade("X", "SHORT", 0, 3_600_000, 100.0, 100.2)
    res = apply_maker_fill([t], bars, bar_interval_ms=3_600_000)
    assert res.missed == 0 and len(res.filled) == 1


def test_missing_next_bar_is_missed():
    bars = {"X": _bars([(100, 101, 100, 100.5)])}  # no bar after entry ts
    t = Trade("X", "LONG", 0, 3_600_000, 100.0, 100.5)
    assert apply_maker_fill([t], bars, bar_interval_ms=3_600_000).missed == 1


def test_gapped_bar_is_missed_not_filled():
    # Bar at t=0 (signal) then next available bar is 5h later — a kline
    # hole. The next-adjacent bar (t=1h) does not exist, so this must be
    # a miss even though the far bar (t=5h) trades through the limit.
    bars = {
        "X": pd.DataFrame(
            [
                {"ts_ms": 0, "open": 100, "high": 101, "low": 100, "close": 100.5},
                {
                    "ts_ms": 5 * 3_600_000,
                    "open": 100.4,
                    "high": 100.6,
                    "low": 99.0,
                    "close": 99.5,
                },
            ]
        )
    }
    t = Trade("X", "LONG", 0, 3_600_000, 100.0, 99.5)
    res = apply_maker_fill([t], bars, bar_interval_ms=3_600_000)
    assert res.missed == 1 and res.filled == []


def test_unsorted_frame_resolves_correct_adjacent_bar():
    # Rows out of ts_ms order: a later decoy bar appears before the true
    # next-adjacent bar. Adjacency selection must not depend on row order.
    bars = {
        "X": pd.DataFrame(
            [
                {
                    "ts_ms": 2 * 3_600_000,
                    "open": 200,
                    "high": 201,
                    "low": 200,
                    "close": 200.5,
                },  # decoy: a later bar, listed first
                {
                    "ts_ms": 3_600_000,
                    "open": 100.4,
                    "high": 100.6,
                    "low": 99.0,
                    "close": 99.5,
                },  # true next-adjacent bar: trades through
                {"ts_ms": 0, "open": 100, "high": 101, "low": 100, "close": 100.5},
            ]
        )
    }
    t = Trade("X", "LONG", 0, 3_600_000, 100.0, 99.5)
    res = apply_maker_fill([t], bars, bar_interval_ms=3_600_000)
    assert res.missed == 0 and len(res.filled) == 1
