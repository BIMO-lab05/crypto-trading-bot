# tests/edge_lab/test_edge_lab_sanity.py
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from edge_lab.sanity import check_funding, check_klines, render_sanity_table  # noqa: E402

DAY = 86_400_000


def _clean(n=10, start=1_700_000_000_000):
    ts = [start + i * DAY for i in range(n)]
    return pd.DataFrame(
        {
            "ts_ms": ts,
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.5] * n,
            "volume": [1.0] * n,
        }
    )


def test_clean_data_passes():
    r = check_klines(_clean(), "BTCUSDT", "D")
    assert r.ok and r.defects == [] and r.n_bars == 10


def test_one_missing_bar_recorded_but_ok():
    df = _clean(10)
    df = df[df["ts_ms"] != df["ts_ms"].iloc[5]]  # one-bar hole = 2-interval gap
    r = check_klines(df, "BTCUSDT", "D")
    assert r.ok and len(r.gaps) == 1


def test_three_bar_hole_is_a_defect():
    df = _clean(10)
    df = df[~df["ts_ms"].isin(df["ts_ms"].iloc[4:7])]  # 3 missing bars
    r = check_klines(df, "BTCUSDT", "D")
    assert not r.ok and any("gap" in d for d in r.defects)


def test_negative_price_is_a_defect():
    df = _clean()
    df.loc[3, "low"] = -1.0
    r = check_klines(df, "BTCUSDT", "D")
    assert not r.ok


def test_funding_coverage():
    n_days = 30
    settlements = pd.DataFrame(
        {
            "ts_ms": [1_700_000_000_000 + i * 8 * 3_600_000 for i in range(90)],
            "funding_rate": ["0.0001"] * 90,
        }
    )
    ok, n = check_funding(settlements, n_days)
    assert ok and n == 90
    ok_empty, n_empty = check_funding(settlements.iloc[0:0], n_days)
    assert not ok_empty and n_empty == 0


def test_render_names_every_defect():
    bad = check_klines(_clean().assign(low=-5.0), "XUSDT", "D")
    out = render_sanity_table([bad])
    assert "XUSDT" in out and "FAIL" in out


def test_empty_dataframe_is_a_defect():
    r = check_klines(_clean(n=0), "BTCUSDT", "D")
    assert not r.ok and "no bars" in r.defects
    assert r.first_ts_ms == 0 and r.last_ts_ms == 0
    out = render_sanity_table([r])
    assert "FAIL" in out
