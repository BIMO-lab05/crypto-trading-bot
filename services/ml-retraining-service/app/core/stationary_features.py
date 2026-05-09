"""
Stationary-only feature set for the T0.1 GRU rebuild — chunk 2.

The legacy ``ModelTrainer.prepare_features`` mixes stationary features
(``returns``, ``log_returns``, ``rsi``, ``macd``, ``volatility_*``,
``momentum_*``) with non-stationary level features (``sma_*``, ``ema_*``,
``bb_middle/upper/lower``, ``volume_sma``). The V0 finding
(``V0-FINDINGS-gru-metric-bug.md``) showed the production GRU is fitting
price-level autocorrelation rather than skill on returns; level features
let the network do that. This module provides the alternative feature
pipeline that drops level inputs and keeps only stationary or
range-bounded indicators.

See ``docs/strategy/research-2026-04-29/T0.1-gru-rebuild-design.md`` §3
for the design discussion and the user's pick (Q2 → stationary-only).

The function is a pure pandas/numpy operation — no tensorflow — so it
can be unit-tested without TF and reused from offline rebuild scripts
(chunk 4).
"""

from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd


# Public, ordered. Trainer threads this list straight into
# ``create_sequences`` as the feature column set; pandas raises KeyError
# at trainer time if any column is missing, which is the loud failure
# we want.
STATIONARY_FEATURE_COLS: List[str] = [
    # Past returns — legitimate input, not a leak (input window is
    # t-59..t, target is t+1, so no temporal overlap).
    "returns",
    "log_returns",
    # Volatility (rolling std of returns) and vol-of-vol.
    "volatility_7",
    "volatility_14",
    "vol_of_vol_14",
    # Bounded oscillators / momentum-of-deviations.
    "rsi",
    "macd",
    "macd_signal",
    "macd_hist",
    "bb_width",  # (upper - lower) / middle — bands as a ratio
    # Volume features (ratio + log-change, both bounded around 0/1).
    "volume_ratio",
    "log_volume_change",
    # Range regime.
    "range_ratio_14",
    # Momentum (close/close.shift - 1) — bounded around 0 for hourly bars.
    "momentum_7",
    "momentum_14",
    # Time-of-day cyclical encoding — captures crypto's session structure
    # without treating "23 → 0" as a 23-unit jump.
    "hour_sin",
    "hour_cos",
]


def compute_stationary_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build the 17-column stationary feature set + ``timestamp`` + ``close``.

    Returns a DataFrame containing only ``timestamp``, ``close``, and
    the columns named in :data:`STATIONARY_FEATURE_COLS`. ``close`` is
    kept because the trainer needs it for ``last_close_*`` extraction
    when it routes through ``_calculate_returns_metrics`` /
    ``_calculate_cpcv_metrics``; the trainer's ``feature_cols`` list
    explicitly does **not** include ``close``, so the model never sees
    raw price level as input.

    Args:
        df: OHLCV with at least columns ``open, high, low, close, volume``
            and (optionally) a datetime ``timestamp``.

    Returns:
        DataFrame with no NaN rows. Output length is ``len(df) - K`` where
        ``K`` is the longest rolling window (volatility 14 + vol-of-vol 14
        plus a 1-bar diff for log_volume → 28 leading rows dropped in
        practice).
    """
    data = df.copy()

    # ── Returns ─────────────────────────────────────────────────────
    data["returns"] = data["close"].pct_change()
    data["log_returns"] = np.log(data["close"] / data["close"].shift(1))

    # ── Volatility (rolling std of returns) ─────────────────────────
    data["volatility_7"] = data["returns"].rolling(window=7).std()
    data["volatility_14"] = data["returns"].rolling(window=14).std()
    data["vol_of_vol_14"] = data["volatility_7"].rolling(window=14).std()

    # ── RSI(14) ─────────────────────────────────────────────────────
    delta = data["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    data["rsi"] = 100 - (100 / (1 + rs))

    # ── MACD ────────────────────────────────────────────────────────
    ema_12 = data["close"].ewm(span=12, adjust=False).mean()
    ema_26 = data["close"].ewm(span=26, adjust=False).mean()
    data["macd"] = ema_12 - ema_26
    data["macd_signal"] = data["macd"].ewm(span=9, adjust=False).mean()
    data["macd_hist"] = data["macd"] - data["macd_signal"]

    # ── Bollinger band width as a ratio ─────────────────────────────
    bb_middle = data["close"].rolling(window=20).mean()
    bb_std = data["close"].rolling(window=20).std()
    # (upper - lower) / middle = (4 * std) / middle
    data["bb_width"] = (4 * bb_std) / bb_middle

    # ── Volume features ─────────────────────────────────────────────
    volume_sma = data["volume"].rolling(window=20).mean()
    data["volume_ratio"] = data["volume"] / volume_sma
    data["log_volume_change"] = np.log(
        data["volume"] / data["volume"].shift(1)
    )

    # ── Bar range regime ───────────────────────────────────────────
    bar_range = data["high"] - data["low"]
    data["range_ratio_14"] = bar_range / bar_range.rolling(window=14).mean()

    # ── Momentum (bounded near 0 for hourly bars) ──────────────────
    data["momentum_7"] = data["close"] / data["close"].shift(7) - 1
    data["momentum_14"] = data["close"] / data["close"].shift(14) - 1

    # ── Time-of-day cyclical encoding ──────────────────────────────
    if (
        "timestamp" in data.columns
        and pd.api.types.is_datetime64_any_dtype(data["timestamp"])
    ):
        hours = data["timestamp"].dt.hour.astype(float)
    else:
        # Fallback: zero — no time-of-day signal available. Keeps
        # downstream shape stable.
        hours = pd.Series(0.0, index=data.index)
    angle = 2 * np.pi * hours / 24
    data["hour_sin"] = np.sin(angle)
    data["hour_cos"] = np.cos(angle)

    # ── Project down + drop NaN ────────────────────────────────────
    keep = [c for c in ("timestamp", "close") if c in data.columns]
    keep.extend(STATIONARY_FEATURE_COLS)
    out = data[keep].copy()

    # ``np.log(volume / volume.shift(1))`` produces +/-inf when a bar's
    # volume drops to zero. Replace with NaN before dropping so the
    # row is consistently treated as invalid.
    out = out.replace([np.inf, -np.inf], np.nan)

    return out.dropna().reset_index(drop=True)
