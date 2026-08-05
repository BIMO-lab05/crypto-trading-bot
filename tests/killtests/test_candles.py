import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from killtests.candles import CandleStore, CandleValidationError, INTERVAL_MS  # noqa: E402

COLS = [
    "timestamp",
    "symbol",
    "interval",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "turnover",
    "is_mainnet",
    "created_at",
]


def _write_csv(
    path,
    n=50,
    start="2026-05-01 00:00:00",
    interval="60",
    symbol="BTCUSDT",
    mainnet=True,
    drop_row=None,
):
    ts = pd.date_range(start, periods=n, freq="60min")
    df = pd.DataFrame(
        {
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": symbol,
            "interval": interval,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 10.0,
            "turnover": 1000.0,
            "is_mainnet": mainnet,
            "created_at": 1777161607163,
        }
    )
    if drop_row is not None:
        df = df.drop(index=drop_row)
    df.to_csv(path, index=False)


@pytest.fixture
def store_dir(tmp_path):
    _write_csv(tmp_path / "BTCUSDT_60m_365d_bybit.csv")
    return tmp_path


def test_loads_and_frames(store_dir):
    s = CandleStore(str(store_dir), ["BTCUSDT"], ["60"])
    f = s.frame("BTCUSDT", "60")
    assert len(f) == 50
    assert list(f.columns) == [
        "timestamp",
        "ts_ms",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]
    assert f["ts_ms"].is_monotonic_increasing


def test_rejects_non_mainnet(tmp_path):
    _write_csv(tmp_path / "BTCUSDT_60m_365d_bybit.csv", mainnet=False)
    with pytest.raises(CandleValidationError, match="is_mainnet"):
        CandleStore(str(tmp_path), ["BTCUSDT"], ["60"])


def test_rejects_gap(tmp_path):
    _write_csv(tmp_path / "BTCUSDT_60m_365d_bybit.csv", drop_row=10)
    with pytest.raises(CandleValidationError, match="gap"):
        CandleStore(str(tmp_path), ["BTCUSDT"], ["60"])


def test_rejects_missing_file(tmp_path):
    with pytest.raises(CandleValidationError, match="missing"):
        CandleStore(str(tmp_path), ["BTCUSDT"], ["60"])


def test_as_of_excludes_forming_and_future(store_dir):
    s = CandleStore(str(store_dir), ["BTCUSDT"], ["60"])
    f = s.frame("BTCUSDT", "60")
    # "now" = exactly the open of bar index 10 => bars 0..9 are closed
    now_ms = int(f["ts_ms"].iloc[10])
    rows = s.as_of("BTCUSDT", "60", now_ms, limit=200)
    assert len(rows) == 10
    assert rows[-1]["timestamp"] == int(f["ts_ms"].iloc[9])
    # one ms before bar 10 closes => bar 10 still forming, still 10 closed bars
    rows = s.as_of("BTCUSDT", "60", now_ms + INTERVAL_MS["60"] - 1, limit=200)
    assert rows[-1]["timestamp"] == int(f["ts_ms"].iloc[9])
    # exactly at close of bar 10 => it is included
    rows = s.as_of("BTCUSDT", "60", now_ms + INTERVAL_MS["60"], limit=200)
    assert rows[-1]["timestamp"] == int(f["ts_ms"].iloc[10])


def test_as_of_limit(store_dir):
    s = CandleStore(str(store_dir), ["BTCUSDT"], ["60"])
    f = s.frame("BTCUSDT", "60")
    end_ms = int(f["ts_ms"].iloc[-1]) + INTERVAL_MS["60"]
    rows = s.as_of("BTCUSDT", "60", end_ms, limit=7)
    assert len(rows) == 7


def test_daily_window_before(tmp_path):
    ts = pd.date_range("2026-05-01", periods=30, freq="D")
    df = pd.DataFrame(
        {
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": "BTCUSDT",
            "interval": "1440",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 10.0,
            "turnover": 1000.0,
            "is_mainnet": True,
            "created_at": 1,
        }
    )
    df.to_csv(tmp_path / "BTCUSDT_1440m_365d_bybit.csv", index=False)
    s = CandleStore(str(tmp_path), ["BTCUSDT"], ["1440"])
    cut = int(pd.Timestamp("2026-05-20 13:00:00").timestamp() * 1000)
    win = s.daily_window_before("BTCUSDT", cut, n=15)
    assert len(win) == 15
    # strictly before the cut DATE's bar: last bar must be 2026-05-19 (its close 05-20 00:00 <= cut)
    assert str(win["timestamp"].iloc[-1].date()) == "2026-05-19"
