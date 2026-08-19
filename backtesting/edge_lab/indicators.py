"""Causal indicator math for edge_lab candidates.

Formulas match the TA service (cited per function); implemented locally
because the service classes are latest-value-shaped, slow, and claim the
`app` package. Float math only — no money here.
"""

from __future__ import annotations

import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    # Wilder smoothing — same as backtesting/strategies/sqzmom_v2.py:79-88
    return true_range(df).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def bollinger(close: pd.Series, n: int = 20, mult: float = 2.0) -> pd.DataFrame:
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std()
    return pd.DataFrame(
        {"bb_upper": mid + mult * sd, "bb_mid": mid, "bb_lower": mid - mult * sd}
    )


def keltner(df: pd.DataFrame, n: int = 20, mult: float = 1.5) -> pd.DataFrame:
    # KC = SMA(close) ± mult * SMA(TR) — squeeze_momentum.py:151-192
    mid = sma(df["close"], n)
    rng = sma(true_range(df), n)
    return pd.DataFrame(
        {"kc_upper": mid + mult * rng, "kc_mid": mid, "kc_lower": mid - mult * rng}
    )


def donchian(df: pd.DataFrame, entry_n: int, exit_n: int) -> pd.DataFrame:
    # shift(1): channel of bars t-n..t-1 — the current bar never sees itself.
    return pd.DataFrame(
        {
            "dc_entry_high": df["high"]
            .rolling(entry_n, min_periods=entry_n)
            .max()
            .shift(1),
            "dc_entry_low": df["low"]
            .rolling(entry_n, min_periods=entry_n)
            .min()
            .shift(1),
            "dc_exit_high": df["high"]
            .rolling(exit_n, min_periods=exit_n)
            .max()
            .shift(1),
            "dc_exit_low": df["low"].rolling(exit_n, min_periods=exit_n).min().shift(1),
        }
    )


def squeeze_on(
    df: pd.DataFrame,
    bb_n: int = 20,
    bb_mult: float = 2.0,
    kc_n: int = 20,
    kc_mult: float = 1.5,
) -> pd.Series:
    # (bb_lower > kc_lower) & (bb_upper < kc_upper) — squeeze_momentum.py:351-361
    bb = bollinger(df["close"], bb_n, bb_mult)
    kc = keltner(df, kc_n, kc_mult)
    return (
        ((bb["bb_lower"] > kc["kc_lower"]) & (bb["bb_upper"] < kc["kc_upper"]))
        .fillna(False)
        .astype(bool)
    )
