import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from killtests.entries import Entry  # noqa: E402
from killtests.h3_atr_replay import replay_entry  # noqa: E402


def _bars(prices, start_ms=1_700_000_000_000, step_ms=900_000, spread=0.5):
    """Bars where high=price+spread, low=price-spread, close=price."""
    return pd.DataFrame(
        {
            "ts_ms": [start_ms + i * step_ms for i in range(len(prices))],
            "open": prices,
            "high": [p + spread for p in prices],
            "low": [p - spread for p in prices],
            "close": prices,
        }
    )


def _entry(side="LONG", price=100.0, qty=1.0, ts=1_700_000_000_000):
    return Entry(
        position_id="t",
        symbol="TESTUSDT",
        side=side,
        quantity=qty,
        entry_price=price,
        entry_ts_ms=ts,
        exit_ts_ms=ts + 1,
        actual_exit_price=0.0,
        actual_realized_pnl=0.0,
        signal_confidence=None,
    )


def test_long_stop_hit():
    bars = _bars([100, 100, 97, 100])
    out = replay_entry(_entry(), bars, stop=98.0, tp=104.0, max_hold_bars=192)
    assert out.exit_reason == "stop_loss"
    assert out.exit_price == 98.0
    assert out.gross_pnl == pytest.approx(-2.0)


def test_long_tp_hit():
    bars = _bars([100, 100, 105, 100])
    out = replay_entry(_entry(), bars, stop=98.0, tp=104.0, max_hold_bars=192)
    assert out.exit_reason == "take_profit"
    assert out.gross_pnl == pytest.approx(4.0)


def test_ambiguous_bar_stop_wins():
    # bar 2 spans both stop (98) and tp (104): low=95.5, high=104.5
    bars = _bars([100, 100, 100, 100])
    bars.loc[2, "low"], bars.loc[2, "high"] = 95.5, 104.5
    out = replay_entry(_entry(), bars, stop=98.0, tp=104.0, max_hold_bars=192)
    assert out.exit_reason == "stop_loss"
    assert out.ambiguous_bars == 1


def test_short_stop_hit():
    bars = _bars([100, 100, 103, 100])
    out = replay_entry(
        _entry(side="SHORT"), bars, stop=102.0, tp=96.0, max_hold_bars=192
    )
    assert out.exit_reason == "stop_loss"
    assert out.gross_pnl == pytest.approx(-2.0)


def test_max_hold_exit_at_close():
    bars = _bars([100.0] * 10)
    out = replay_entry(_entry(), bars, stop=90.0, tp=110.0, max_hold_bars=4)
    assert out.exit_reason == "max_hold"
    assert out.bars_held == 4
    assert out.exit_price == 100.0


def test_walk_starts_after_entry_ts():
    # entry mid-bar-0: bar 0's crash to 90 must NOT trigger the stop.
    #
    # DEVIATION from task-6-brief.md (team-lead approved 2026-08-05): the
    # brief's own reference `replay_entry` (brief lines 214-218) decides
    # max_hold vs end_of_data via `len(walk) >= max_hold_bars`. With this
    # fixture walk has 3 bars (bar 0 excluded by the entry-ts filter) and
    # max_hold_bars=192, so that formula yields "end_of_data" — but the
    # brief's own test (lines 88-94) asserted "max_hold" for the exact same
    # inputs that `test_end_of_data` (lines 97-100) asserts "end_of_data"
    # for (walk len 3, max_hold_bars 192 in both). The reference
    # implementation fails its own Step-1 test as written.
    #
    # Resolution: walk exhaustion before max_hold_bars is always
    # "end_of_data" (matches test_end_of_data and test_max_hold_exit_at_close
    # consistently — real runs pass replay_entry the entry's ENTIRE
    # symbol/resolution frame, so running out of walk always means running
    # out of real history). This test's real intent, per its own comment, is
    # "never stopped" — asserted directly below instead of via a label that
    # was never rigorously derived for this edge case.
    bars = _bars([100, 100, 100, 100])
    bars.loc[0, "low"] = 90.0
    e = _entry(ts=bars["ts_ms"][0] + 1)  # 1ms after bar 0 opens
    out = replay_entry(e, bars, stop=95.0, tp=110.0, max_hold_bars=192)
    assert out.exit_reason != "stop_loss"  # never stopped
    assert out.exit_reason == "end_of_data"


def test_end_of_data():
    bars = _bars([100.0] * 3)
    out = replay_entry(_entry(), bars, stop=90.0, tp=110.0, max_hold_bars=192)
    assert out.exit_reason == "end_of_data"


def test_daily_atr_known_values(tmp_path):
    """ATR = SMA of last 14 true ranges; constant bars => TR = high-low = 2."""
    from killtests.candles import CandleStore

    ts = pd.date_range("2026-05-01", periods=20, freq="D")
    df = pd.DataFrame(
        {
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": "TESTUSDT",
            "interval": "1440",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1.0,
            "turnover": 1.0,
            "is_mainnet": True,
            "created_at": 1,
        }
    )
    df.to_csv(tmp_path / "TESTUSDT_1440m_365d_bybit.csv", index=False)
    from killtests.h3_atr_replay import daily_atr

    store = CandleStore(str(tmp_path), ["TESTUSDT"], ["1440"])
    cut = int(pd.Timestamp("2026-05-19 12:00:00").timestamp() * 1000)
    assert daily_atr(store, "TESTUSDT", cut) == pytest.approx(2.0)
