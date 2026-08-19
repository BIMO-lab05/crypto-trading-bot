"""intraday_seasonality candidate — causality and contract tests."""

import numpy as np
import pandas as pd
import pytest

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from edge_lab.candidates import intraday_seasonality as cand
from edge_lab.trades import Trade

CLEAN_EPOCH_MS = int(pd.Timestamp("2026-04-25").timestamp() * 1000)


def _h1_frame(days=120, seed=0):
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2026-03-01", periods=days * 24, freq="1h", tz="UTC")
    px = 100 * np.exp(np.cumsum(rng.normal(0, 0.005, len(ts))))
    # ts.view("int64") is pandas-3 datetime64[us] microseconds-since-epoch;
    # naively //10**6 yields SECONDS mislabeled as ms. Cast to datetime64[ms]
    # first, same trap run_battery.py:read_kline_csv documents and avoids.
    ts_ms = ts.astype("datetime64[ms, UTC]").astype("int64")
    return pd.DataFrame(
        {
            "ts_ms": ts_ms,
            "open": px,
            "high": px * 1.001,
            "low": px * 0.999,
            "close": px,
            "volume": 1000.0,
        }
    )


def test_variants_match_manifest():
    names = {v.name for v in cand.VARIANTS}
    assert names == {"funding_window_drift", "hour_of_day"}


@pytest.mark.parametrize("variant", cand.VARIANTS, ids=lambda v: v.name)
def test_no_trades_before_clean_epoch(variant):
    trades = cand.generate_trades({"BTCUSDT": _h1_frame()}, variant)
    assert len(trades) > 0  # non-vacuity: a passing "all()" over [] proves nothing
    assert all(t.entry_ts_ms >= CLEAN_EPOCH_MS for t in trades)


def test_funding_window_direction_is_causal():
    # Poison future bars: make every bar AFTER a chosen entry hugely positive.
    # Direction at that entry must not change (computed from strictly prior data).
    df = _h1_frame()
    variant = next(v for v in cand.VARIANTS if v.name == "funding_window_drift")
    base = cand.generate_trades({"BTCUSDT": df}, variant)
    poisoned = df.copy()
    cut = int(len(df) * 0.9)
    poisoned.loc[cut:, ["open", "high", "low", "close"]] *= 10
    after = cand.generate_trades({"BTCUSDT": poisoned}, variant)
    pre_cut_ts = df.iloc[cut]["ts_ms"]
    base_pre = [(t.entry_ts_ms, t.side) for t in base if t.entry_ts_ms < pre_cut_ts]
    after_pre = [(t.entry_ts_ms, t.side) for t in after if t.entry_ts_ms < pre_cut_ts]
    assert (
        len(base_pre) > 0
    )  # non-vacuity: [] == [] would pass without testing anything
    assert base_pre == after_pre  # future data changed nothing before the cut


def test_trades_satisfy_contract():
    for variant in cand.VARIANTS:
        trades = cand.generate_trades({"BTCUSDT": _h1_frame(seed=3)}, variant)
        assert len(trades) > 0  # non-vacuity: an empty loop asserts nothing
        for t in trades:
            assert isinstance(t, Trade)  # dataclass __post_init__ validates rest
