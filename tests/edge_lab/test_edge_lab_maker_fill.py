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


def test_close_basis_is_the_default():
    # entry_basis defaults to "close" — the pre-fix behavior — so an
    # existing call site that never passes the new kwarg is unaffected.
    bars = {
        "X": _bars(
            [
                (100, 101, 100, 100.5),
                (100.4, 100.6, 99.0, 99.5),
            ]
        )
    }
    t = Trade("X", "LONG", 0, 3_600_000, 100.0, 99.5)
    default_res = apply_maker_fill([t], bars, bar_interval_ms=3_600_000)
    explicit_res = apply_maker_fill(
        [t], bars, bar_interval_ms=3_600_000, entry_basis="close"
    )
    assert default_res == explicit_res
    assert default_res.filled == [t]


def test_open_basis_fills_on_the_entry_bar_itself():
    # LONG entry limit == that bar's own open (100). The SAME bar's low
    # (99) trades through it — under "close" basis this bar would never
    # even be tested (only the NEXT bar is), which is exactly C1.
    bars = {"X": _bars([(100, 101, 99, 100.5)])}
    t = Trade("X", "LONG", 0, 3_600_000, 100.0, 100.5)
    res = apply_maker_fill([t], bars, bar_interval_ms=3_600_000, entry_basis="open")
    assert res.missed == 0 and res.filled == [t]


def test_open_basis_short_fills_on_the_entry_bar_itself():
    bars = {"X": _bars([(100, 101, 99.5, 100.5)])}  # high 101 > limit 100
    t = Trade("X", "SHORT", 0, 3_600_000, 100.0, 100.5)
    res = apply_maker_fill([t], bars, bar_interval_ms=3_600_000, entry_basis="open")
    assert res.missed == 0 and res.filled == [t]


def test_open_basis_touch_only_is_missed():
    # low == open (100): touch, not trade-through.
    bars = {"X": _bars([(100, 101, 100, 100.5)])}
    t = Trade("X", "LONG", 0, 3_600_000, 100.0, 100.5)
    res = apply_maker_fill([t], bars, bar_interval_ms=3_600_000, entry_basis="open")
    assert res.missed == 1 and res.filled == []


def test_open_basis_missing_entry_bar_is_missed():
    # No bar at ts==0 at all (data starts at the next interval) — the
    # entry bar itself is absent, so there is nothing for the order to
    # rest on.
    df = _bars([(100.4, 100.6, 99.0, 99.5)])
    df["ts_ms"] = df["ts_ms"] + 3_600_000
    bars = {"X": df}
    t = Trade("X", "LONG", 0, 3_600_000, 100.0, 100.5)
    res = apply_maker_fill([t], bars, bar_interval_ms=3_600_000, entry_basis="open")
    assert res.missed == 1 and res.filled == []


def test_open_basis_ignores_slippage_inflated_entry_px():
    # Regression for the vacuous-fill bug: entry_px carries a +5bps
    # slippage markup over the bar's true open (100 -> 100.05), as
    # baseline_rsi_ema's engine-derived trades do. Testing against
    # entry_px directly would make `low < entry_px` true by construction
    # whenever low <= open (i.e. always). The limit must come from the
    # bar's own open (100), not entry_px (100.05) — low=100 does NOT
    # trade through open=100 (touch only), so this must be a miss.
    bars = {"X": _bars([(100, 100.5, 100, 100.3)])}
    t = Trade("X", "LONG", 0, 3_600_000, 100.05, 100.3)  # inflated entry_px
    res = apply_maker_fill([t], bars, bar_interval_ms=3_600_000, entry_basis="open")
    assert res.missed == 1 and res.filled == []
    # Documents the trap: low(100) < entry_px(100.05) is True, so testing
    # against entry_px directly (the bug) would have produced a spurious
    # fill here. The correct test is against the bar's own open (100),
    # where low(100) < open(100) is False (touch, not trade-through).
    assert 100.0 < t.entry_px


def test_open_basis_gapped_next_bar_does_not_matter():
    # A hole at t+1 is irrelevant to "open" basis — only the entry bar
    # itself (t) is ever tested. Confirms "open" and "close" are
    # independent code paths, not "close" with an extra check.
    bars = {
        "X": pd.DataFrame(
            [
                {"ts_ms": 0, "open": 100, "high": 101, "low": 99, "close": 100.5},
                {  # gap: next bar is 5h later, not the adjacent 1h bar
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
    res = apply_maker_fill([t], bars, bar_interval_ms=3_600_000, entry_basis="open")
    assert res.missed == 0 and res.filled == [t]


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
