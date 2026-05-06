"""
Skeleton for a new technical-analysis indicator.

Drop into:
    services/technical-analysis/app/indicators/<your_name>.py

Module docstring MUST document:
    - period defaults and rationale
    - last optimization date
    - any deviation from crypto-tuned defaults

Pure function on an OHLCV DataFrame. No network, no DB, no in-place mutation
of the input frame.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# Crypto-tuned defaults documented at module level so callers can override
# explicitly. Re-optimize quarterly via walk-forward.
DEFAULT_PERIOD = 14
DEFAULT_THRESHOLD = 0.0


def compute(
    df: pd.DataFrame,
    period: int = DEFAULT_PERIOD,
    threshold: float = DEFAULT_THRESHOLD,
) -> pd.Series:
    """
    Return a Series aligned to df.index with the indicator value at each bar.

    Bar t output uses ONLY rows with index <= t. No centred rolling, no
    full-series fits. Validate via the prefix-stability test in
    references/leakage-tests.md.
    """
    if df.empty:
        return pd.Series(dtype="float64", index=df.index)

    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"OHLCV frame missing columns: {sorted(missing)}")

    # Example: rolling z-score of close (causal min_periods=period).
    close = df["close"].astype("float64")
    mean = close.rolling(window=period, min_periods=period).mean()
    std = close.rolling(window=period, min_periods=period).std(ddof=0)
    z = (close - mean) / std.replace(0, np.nan)

    return z


def signal(z: pd.Series, threshold: float = DEFAULT_THRESHOLD) -> pd.Series:
    """
    Map indicator -> {-1, 0, +1}. No look-ahead: pure elementwise.
    """
    out = pd.Series(0, index=z.index, dtype="int8")
    out[z > threshold] = 1
    out[z < -threshold] = -1
    return out
