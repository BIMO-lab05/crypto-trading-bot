import numpy as np
import pandas as pd
import pytest


def _write_candles(tmp_path, symbol, interval, n, start):
    freq = {"15": "15min", "60": "60min", "240": "240min", "1440": "D"}[interval]
    ts = pd.date_range(start, periods=n, freq=freq)
    rng = np.random.default_rng(42)
    closes = 100 + np.cumsum(rng.normal(0, 0.5, n))
    df = pd.DataFrame(
        {
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": symbol,
            "interval": interval,
            "open": closes,
            "high": closes + 0.6,
            "low": closes - 0.6,
            "close": closes,
            "volume": 10.0,
            "turnover": 1000.0,
            "is_mainnet": True,
            "created_at": 1,
        }
    )
    df.to_csv(tmp_path / f"{symbol}_{interval}m_365d_bybit.csv", index=False)


@pytest.fixture
def write_candles():
    return _write_candles
