import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from conftest import DAY, T0, assert_shift_invariant  # noqa: E402
from edge_lab.candidates.xs_momentum import VARIANTS, generate_trades  # noqa: E402

V30 = next(v for v in VARIANTS if v.name == "lookback_30d")


def test_three_variants_declared():
    assert [v.name for v in VARIANTS] == ["lookback_7d", "lookback_30d", "lookback_90d"]
    assert all(v.candidate == "xs_momentum" for v in VARIANTS)


def test_ranks_longs_high_drift_shorts_low_drift(universe12):
    trades = generate_trades(universe12, V30)
    assert trades, "no trades generated"
    longs = {t.symbol for t in trades if t.side == "LONG"}
    shorts = {t.symbol for t in trades if t.side == "SHORT"}
    # drifted +0.4%/day symbols should dominate the long book
    assert {"S00USDT", "S01USDT", "S02USDT"} & longs
    assert {"S09USDT", "S10USDT", "S11USDT"} & shorts


def test_entries_only_on_mondays(universe12):
    trades = generate_trades(universe12, V30)
    for t in trades:
        dow = pd.Timestamp(t.entry_ts_ms, unit="ms", tz="UTC").dayofweek
        assert dow == 0, f"entry on non-Monday: {t}"


def test_entry_price_is_monday_open(universe12):
    trades = generate_trades(universe12, V30)
    t = trades[0]
    df = universe12[t.symbol]
    row = df[df["ts_ms"] == t.entry_ts_ms].iloc[0]
    assert t.entry_px == row["open"]


def test_holding_is_one_week(universe12):
    trades = generate_trades(universe12, V30)
    complete = [t for t in trades if t.exit_ts_ms - t.entry_ts_ms == 7 * DAY]
    assert len(complete) >= 0.9 * len(trades)  # tail week may truncate


def test_shift_invariance(universe12):
    cut = T0 + 200 * DAY
    assert_shift_invariant(generate_trades, universe12, V30, cut)
