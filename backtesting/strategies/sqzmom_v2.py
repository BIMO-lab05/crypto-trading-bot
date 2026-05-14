"""
sqzmom_v2 — Phase C canonical strategy (ADR-013).

ONE strategy aligned with 2026 crypto-bot research findings:
  TTM Squeeze (BB 20/2.0 + KC 20/1.5) on second consecutive momentum bar
  + 200-EMA trend filter
  + ADX>=20 with +DI/-DI directional agreement
  + volume>1.2*SMA(20) confirmation
  + 4h MTF squeeze-color alignment (1h+4h direction agree)
  + 1.5*ATR initial stop, 3*ATR take-profit (2:1 R/R)

Each filter is gated by `layer` so the walk-forward harness can isolate
which gate kills trade count. Layer 0 = pure squeeze release; layer 5 =
all filters stacked.

Indicator math is causal: precompute_features() emits per-row values
that depend ONLY on data[:idx+1]. The 4h MTF features are shifted by
one 4h period after resample so a 4h-bar's close is not visible to 1h
bars within that 4h window — avoids look-ahead.

USAGE
=====
    from strategies.sqzmom_v2 import precompute_features, make_sqzmom_v2

    enriched = precompute_features(raw_ohlcv_df)
    strategy = make_sqzmom_v2(layer=5)

    engine = BacktestEngine(...)
    engine.run_backtest(enriched, strategy, strategy_name="sqzmom_v2_L5")
"""

from __future__ import annotations

import os
import sys
from typing import Callable

import numpy as np
import pandas as pd

# Make sibling backtesting/ modules importable when this file is imported
# from another script (e.g. run_walk_forward).
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKTESTING_DIR = os.path.dirname(_HERE)
if _BACKTESTING_DIR not in sys.path:
    sys.path.insert(0, _BACKTESTING_DIR)

from prod_indicators import SqueezeMomentumIndicator  # noqa: E402

# ---------------------------------------------------------------------
# Hyperparameters (research-anchored defaults; tune via walk-forward only)
# ---------------------------------------------------------------------
BB_LENGTH = 20
BB_MULT = 2.0
KC_LENGTH = 20
KC_MULT = 1.5

EMA_FAST = 20
EMA_SLOW = 200

ATR_PERIOD = 14
ADX_PERIOD = 14
ADX_MIN = 20.0

VOL_WINDOW = 20
VOL_MIN_RATIO = 1.2

ATR_STOP_MULT = 1.5
ATR_TP_MULT = 3.0  # 2:1 reward-to-risk

WARMUP = 200  # need EMA200 to settle


# ---------------------------------------------------------------------
# Vectorized indicator helpers (causal — rolling-only, no shift backward)
# ---------------------------------------------------------------------


def _true_range(h: pd.Series, l: pd.Series, c: pd.Series) -> pd.Series:
    return pd.concat(
        [h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()],
        axis=1,
    ).max(axis=1)


def _wilder_smooth(series: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing — equivalent to EMA with alpha=1/period."""
    return series.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def _adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Returns DataFrame with adx, plus_di, minus_di columns. Causal."""
    h, l, c = df["high"], df["low"], df["close"]
    up_move = h - h.shift(1)
    down_move = l.shift(1) - l

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=df.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=df.index,
    )
    tr = _true_range(h, l, c)

    atr = _wilder_smooth(tr, period)
    plus_di = 100.0 * _wilder_smooth(plus_dm, period) / atr
    minus_di = 100.0 * _wilder_smooth(minus_dm, period) / atr

    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = _wilder_smooth(dx, period)

    return pd.DataFrame(
        {"adx": adx, "plus_di": plus_di, "minus_di": minus_di},
        index=df.index,
    )


# ---------------------------------------------------------------------
# precompute_features: enrich raw OHLCV in one pass
# ---------------------------------------------------------------------


def precompute_features(data: pd.DataFrame) -> pd.DataFrame:
    """
    Add all sqzmom_v2 feature columns to `data`. Returns a NEW DataFrame.

    `data` must have columns: open, high, low, close, volume.
    `data.index` should be a DatetimeIndex for 4h MTF features to work; if
    not, the mtf4h_* columns will be NaN and layer >= 4 entries will skip.

    All emitted column values at row i depend only on data[:i+1] (causal).
    The 4h MTF features are shifted by one 4h period to ensure the 4h
    bar's close isn't readable from 1h bars within that 4h window.
    """
    out = data.copy()

    # SQZMOM (BB + KC + linreg momentum + color + signal columns)
    sqz = SqueezeMomentumIndicator(
        bb_length=BB_LENGTH,
        bb_mult=BB_MULT,
        kc_length=KC_LENGTH,
        kc_mult=KC_MULT,
    )
    sqz_df = sqz.calculate(out[["open", "high", "low", "close", "volume"]])
    if sqz_df is None:
        raise RuntimeError("SqueezeMomentumIndicator.calculate returned None")
    for col in ("squeeze_on", "squeeze_off", "no_squeeze", "sqz_momentum", "sqz_color"):
        out[col] = sqz_df[col].values

    # 2-bar consecutive-direction momentum confirmation
    mom = out["sqz_momentum"]
    out["mom_pos"] = mom > 0
    out["mom_neg"] = mom < 0
    out["mom_pos_2"] = out["mom_pos"] & out["mom_pos"].shift(1).fillna(False)
    out["mom_neg_2"] = out["mom_neg"] & out["mom_neg"].shift(1).fillna(False)

    # EMAs
    out["ema_20"] = (
        out["close"].ewm(span=EMA_FAST, adjust=False, min_periods=EMA_FAST).mean()
    )
    out["ema_200"] = (
        out["close"].ewm(span=EMA_SLOW, adjust=False, min_periods=EMA_SLOW).mean()
    )

    # Volume confirmation
    out["vol_sma_20"] = out["volume"].rolling(VOL_WINDOW, min_periods=VOL_WINDOW).mean()
    out["vol_ratio"] = out["volume"] / out["vol_sma_20"]

    # ATR + ADX (vectorized, causal)
    out["atr_14"] = _wilder_smooth(
        _true_range(out["high"], out["low"], out["close"]), ATR_PERIOD
    )
    adx_frame = _adx(out, period=ADX_PERIOD)
    out["adx_14"] = adx_frame["adx"]
    out["plus_di"] = adx_frame["plus_di"]
    out["minus_di"] = adx_frame["minus_di"]

    # 4h MTF squeeze color (causal: shift(1) so close isn't visible mid-bar)
    if isinstance(out.index, pd.DatetimeIndex) and len(out) >= 22 * 4:
        agg = {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
        # Right-labeled 4h bar => label is the END of the 4h window
        h4 = (
            out[["open", "high", "low", "close", "volume"]]
            .resample("4h", label="right", closed="right")
            .agg(agg)
            .dropna()
        )
        if len(h4) >= 22:
            sqz4_df = sqz.calculate(h4)
            if sqz4_df is not None:
                # shift(1) — 4h bar at t emits its features only at t+1 4h boundary
                mtf = sqz4_df[
                    ["squeeze_on", "squeeze_off", "sqz_momentum", "sqz_color"]
                ].shift(1)
                mtf.columns = [f"mtf4h_{c}" for c in mtf.columns]
                out = out.merge(mtf, left_index=True, right_index=True, how="left")
                for col in mtf.columns:
                    out[col] = out[col].ffill()

    # Fill any missing mtf4h_* columns with safe defaults so strategy gate
    # can be evaluated uniformly (no leakage; just no signal).
    for col in (
        "mtf4h_squeeze_on",
        "mtf4h_squeeze_off",
        "mtf4h_sqz_momentum",
        "mtf4h_sqz_color",
    ):
        if col not in out.columns:
            out[col] = np.nan

    return out


# ---------------------------------------------------------------------
# Strategy factory
# ---------------------------------------------------------------------


def make_sqzmom_v2(layer: int = 5) -> Callable:
    """
    Return a backtest strategy function with `layer` filters active.

    layer 0: squeeze release + 2-bar consecutive momentum (no other gates)
    layer 1: + 200-EMA trend
    layer 2: + ADX>=20 with DI agreement
    layer 3: + volume>1.2*SMA(20)
    layer 4: + 4h MTF color alignment
    layer 5: + ATR-based stops (1.5*ATR / 3*ATR)

    Stops at layer < 5 fall back to fixed 2% / 5%.
    """
    assert 0 <= layer <= 5, f"layer must be 0..5, got {layer}"

    def sqzmom_v2(row, position, idx, data):
        if idx < WARMUP:
            return None
        if position is not None:
            return None  # position open — engine handles SL/TP

        # L0: squeeze release + 2-bar consecutive momentum
        sqz_off = bool(row.get("squeeze_off", False))
        no_sqz = bool(row.get("no_squeeze", False))
        if not (sqz_off or no_sqz):
            return None  # still inside squeeze, wait for release

        color = row.get("sqz_color", "gray")
        mom_pos_2 = bool(row.get("mom_pos_2", False))
        mom_neg_2 = bool(row.get("mom_neg_2", False))

        if mom_pos_2 and color in ("lime", "green"):
            direction = "BUY"
        elif mom_neg_2 and color in ("red", "maroon"):
            direction = "SELL"
        else:
            return None

        current_price = float(row["close"])

        # L1: 200-EMA trend filter
        if layer >= 1:
            ema_200 = row.get("ema_200", np.nan)
            if pd.isna(ema_200):
                return None
            if direction == "BUY" and current_price < ema_200:
                return None
            if direction == "SELL" and current_price > ema_200:
                return None

        # L2: ADX strength + DI directional agreement
        if layer >= 2:
            adx = row.get("adx_14", np.nan)
            plus_di = row.get("plus_di", np.nan)
            minus_di = row.get("minus_di", np.nan)
            if pd.isna(adx) or adx < ADX_MIN:
                return None
            if pd.isna(plus_di) or pd.isna(minus_di):
                return None
            if direction == "BUY" and not (plus_di > minus_di):
                return None
            if direction == "SELL" and not (minus_di > plus_di):
                return None

        # L3: volume confirmation
        if layer >= 3:
            vol_ratio = row.get("vol_ratio", np.nan)
            if pd.isna(vol_ratio) or vol_ratio < VOL_MIN_RATIO:
                return None

        # L4: 4h MTF color alignment
        if layer >= 4:
            mtf_color = row.get("mtf4h_sqz_color", None)
            if mtf_color is None or (
                isinstance(mtf_color, float) and np.isnan(mtf_color)
            ):
                return None
            if direction == "BUY" and mtf_color not in ("lime", "green"):
                return None
            if direction == "SELL" and mtf_color not in ("red", "maroon"):
                return None

        # L5: ATR-based stops; otherwise fixed 2% / 5%
        if layer >= 5:
            atr_val = row.get("atr_14", np.nan)
            if pd.isna(atr_val) or atr_val <= 0:
                return None
            if direction == "BUY":
                stop = current_price - ATR_STOP_MULT * atr_val
                tp = current_price + ATR_TP_MULT * atr_val
            else:
                stop = current_price + ATR_STOP_MULT * atr_val
                tp = current_price - ATR_TP_MULT * atr_val
        else:
            if direction == "BUY":
                stop = current_price * 0.98
                tp = current_price * 1.05
            else:
                stop = current_price * 1.02
                tp = current_price * 0.95

        return {
            "action": direction,
            "stop_loss": float(stop),
            "take_profit": float(tp),
            "metadata": {
                "layer": layer,
                "sqz_color": color,
                "momentum": float(row.get("sqz_momentum", 0.0)),
                "adx": float(row.get("adx_14", 0.0))
                if not pd.isna(row.get("adx_14", np.nan))
                else None,
                "vol_ratio": float(row.get("vol_ratio", 0.0))
                if not pd.isna(row.get("vol_ratio", np.nan))
                else None,
                "strategy": f"sqzmom_v2_L{layer}",
            },
        }

    sqzmom_v2.__name__ = f"sqzmom_v2_L{layer}"
    return sqzmom_v2
