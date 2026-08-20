"""Shared helper for killtests, in a module with a unique basename (not
`conftest`) — a second top-level `conftest` module in tests/edge_lab
collides with this one under pytest's default `prepend` import mode, since
both files loaded as top-level modules named `conftest`. Imported directly
by test modules, so it must independently perform the sys.path side effect
(fixtures in conftest.py do not need to import this module, but keeping the
same side effect here makes this module safe to import standalone). See
2026-08-20 wait-window plan, task 14.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))


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
