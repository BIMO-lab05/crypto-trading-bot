import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from killtests.entries import Entry  # noqa: E402
from killtests.h3_atr_replay import (  # noqa: E402
    headline_accept,
    load_entries_from_series,
    replay_entry,
)


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


def _series_csv(tmp_path, rows):
    path = tmp_path / "series.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return str(path)


def test_load_entries_from_series_filters_and_converts(tmp_path):
    from shared.account import PAPER_INITIAL_BALANCE

    path = _series_csv(
        tmp_path,
        [
            {
                "symbol": "BTCUSDT",
                "ts_ms": 1_700_000_000_000,
                "ens_action": "BUY",
                "ens_confidence": 0.75,
                "ens_position_size_pct": 0.10,
                "close": 50_000.0,
            },
            {
                "symbol": "ETHUSDT",
                "ts_ms": 1_700_003_600_000,
                "ens_action": "SELL",
                "ens_confidence": 0.5,
                "ens_position_size_pct": 0.05,
                "close": 3_000.0,
            },
            {  # HOLD row — must be dropped, not synthesized as an entry
                "symbol": "SOLUSDT",
                "ts_ms": 1_700_007_200_000,
                "ens_action": None,
                "ens_confidence": None,
                "ens_position_size_pct": None,
                "close": 150.0,
            },
        ],
    )
    entries = load_entries_from_series(path)
    assert len(entries) == 2
    buy, sell = entries
    assert buy.symbol == "BTCUSDT"
    assert buy.side == "LONG"
    assert buy.entry_price == 50_000.0
    assert buy.quantity == pytest.approx(0.10 * PAPER_INITIAL_BALANCE / 50_000.0)
    assert buy.signal_confidence == pytest.approx(0.75)
    assert sell.symbol == "ETHUSDT"
    assert sell.side == "SHORT"
    assert sell.quantity == pytest.approx(0.05 * PAPER_INITIAL_BALANCE / 3_000.0)


def test_load_entries_from_series_rejects_missing_size(tmp_path):
    path = _series_csv(
        tmp_path,
        [
            {
                "symbol": "BTCUSDT",
                "ts_ms": 1_700_000_000_000,
                "ens_action": "BUY",
                "ens_confidence": 0.75,
                "ens_position_size_pct": None,
                "close": 50_000.0,
            }
        ],
    )
    with pytest.raises(ValueError, match="ens_position_size_pct is missing"):
        load_entries_from_series(path)


def test_load_entries_from_series_rejects_nonpositive_close(tmp_path):
    path = _series_csv(
        tmp_path,
        [
            {
                "symbol": "BTCUSDT",
                "ts_ms": 1_700_000_000_000,
                "ens_action": "BUY",
                "ens_confidence": 0.75,
                "ens_position_size_pct": 0.10,
                "close": 0.0,
            }
        ],
    )
    with pytest.raises(ValueError, match="non-positive close"):
        load_entries_from_series(path)


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


def _write_interval_csv(tmp_path, iv, start, periods, freq):
    ts = pd.date_range(start, periods=periods, freq=freq)
    pd.DataFrame(
        {
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": "TESTUSDT",
            "interval": iv,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1.0,
            "turnover": 1.0,
            "is_mainnet": True,
            "created_at": 1,
        }
    ).to_csv(tmp_path / f"TESTUSDT_{iv}m_365d_bybit.csv", index=False)


def test_secondary_skips_entries_before_atr_warmup(tmp_path):
    """Series-sourced entries predating daily ATR(14) warmup are skipped and
    counted when skip_missing_atr=True (H3-secondary); primary semantics
    (hard abort) preserved when False."""
    from dataclasses import replace

    from killtests.candles import CandleValidationError
    from killtests.h3_atr_replay import run_h3

    _write_interval_csv(tmp_path, "1440", "2026-05-01", 22, "D")
    _write_interval_csv(tmp_path, "15", "2026-05-04", 18 * 96, "15min")
    _write_interval_csv(tmp_path, "60", "2026-05-04", 18 * 24, "h")

    def ts_ms(s):
        return int(pd.Timestamp(s).timestamp() * 1000)

    early = replace(_entry(ts=ts_ms("2026-05-05 12:00:00")), position_id="early")
    valid = replace(_entry(ts=ts_ms("2026-05-19 12:00:00")), position_id="valid")

    out = run_h3(
        str(tmp_path), 1.5, "15", entries=[early, valid], skip_missing_atr=True
    )
    assert out["n"] == 1
    assert out["atr_skipped"] == 1
    assert out["per_trade"][0]["position_id"] == "valid"

    with pytest.raises(CandleValidationError):
        run_h3(str(tmp_path), 1.5, "15", entries=[early, valid])


def test_mixed_variant_result_is_reject():
    """The audit criterion has no any-variant clause: one bracket geometry
    clearing while the other fails is not "the exit design passed".

    Pinned because the code said `any(...)` until 2026-08-07 while the
    committed verdict's caveat claimed both variants had to clear — true of
    that data, false of the code, and nothing would have caught the drift.
    """
    mixed = {1.5: {"accept": True}, 2.5: {"accept": False}}
    d = headline_accept(mixed)
    assert d["accept"] is False
    assert d["accept_all"] is False
    assert d["accept_any"] is True  # recorded, deliberately not used
    assert d["per_variant"] == {1.5: True, 2.5: False}


def test_all_variants_passing_accepts():
    d = headline_accept({1.5: {"accept": True}, 2.5: {"accept": True}})
    assert d["accept"] is True and d["accept_all"] is True


def test_no_variant_passing_rejects():
    d = headline_accept({1.5: {"accept": False}, 2.5: {"accept": False}})
    assert d["accept"] is False and d["accept_any"] is False


def _warmup_frames(tmp_path):
    _write_interval_csv(tmp_path, "1440", "2026-05-01", 22, "D")
    _write_interval_csv(tmp_path, "15", "2026-05-04", 18 * 96, "15min")
    _write_interval_csv(tmp_path, "60", "2026-05-04", 18 * 24, "h")


def test_truncated_trades_are_split_out_of_the_headline(tmp_path):
    """A trade whose walk runs off the end of the CSV got no exit decision
    from these rules — its outcome is a fact about backfill length, not about
    bracket design — so it must not sit inside the headline expectancy. It is
    reported separately, never dropped."""
    from dataclasses import replace

    from killtests.h3_atr_replay import run_h3

    _warmup_frames(tmp_path)

    def ts_ms(s):
        return int(pd.Timestamp(s).timestamp() * 1000)

    decided = replace(_entry(ts=ts_ms("2026-05-19 12:00:00")), position_id="decided")
    runs_out = replace(_entry(ts=ts_ms("2026-05-21 00:00:00")), position_id="runs_out")

    out = run_h3(str(tmp_path), 1.5, "15", entries=[decided, runs_out])
    assert out["n_replayed"] == 2
    assert out["n"] == 1  # headline denominator excludes the truncated one
    assert out["truncated_n"] == 1
    reasons = {r["position_id"]: r["exit_reason"] for r in out["per_trade"]}
    assert reasons == {"decided": "max_hold", "runs_out": "end_of_data"}
    assert len(out["per_trade"]) == 2  # reported, not dropped


def test_max_hold_exits_stay_in_the_headline(tmp_path):
    """The 48h cutoff IS part of the exit design under test — unlike
    end_of_data, it must not be split out."""
    from dataclasses import replace

    from killtests.h3_atr_replay import run_h3

    _warmup_frames(tmp_path)
    e = replace(
        _entry(ts=int(pd.Timestamp("2026-05-19 12:00:00").timestamp() * 1000)),
        position_id="held",
    )
    out = run_h3(str(tmp_path), 1.5, "15", entries=[e])
    assert out["per_trade"][0]["exit_reason"] == "max_hold"
    assert out["n"] == 1 and out["truncated_n"] == 0


def test_all_entries_skipped_raises_a_readable_error(tmp_path):
    """Previously a KeyError out of pandas on an empty frame."""
    from dataclasses import replace

    from killtests.h3_atr_replay import run_h3

    _warmup_frames(tmp_path)
    early = replace(
        _entry(ts=int(pd.Timestamp("2026-05-05 12:00:00").timestamp() * 1000)),
        position_id="early",
    )
    with pytest.raises(ValueError, match="no entries survived setup"):
        run_h3(str(tmp_path), 1.5, "15", entries=[early], skip_missing_atr=True)
