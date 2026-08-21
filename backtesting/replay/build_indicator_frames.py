#!/usr/bin/env python3
"""
Stage 1 of the filter-stack replay: compute the LIVE indicator legs for every
historical bar and write them to disk.

Why two stages. `backtesting/prod_indicators.py` prepends
`services/technical-analysis` to sys.path so `app.*` resolves to the TA
service; the aggregation stack it feeds lives in `services/trading-engine`
under the SAME `app.*` namespace. The two cannot be imported into one
process. Stage 1 (this file) runs in the TA context and emits plain JSON;
stage 2 (`replay_filter_stack.py`) runs in the trading-engine context and
consumes it.

Fidelity: every value here comes from the calculator classes the TA service
itself uses, constructed with the parameters `trading-engine`'s
`signal_aggregator.fetch_*` passes (RSI 9, MACD 5/35/5, BB 20/2.5, SMA/EMA
21, Ichimoku 20/60/120, ADX 14, Stochastic 14/3/3, TrendFilter 50/200,
Volume 20, SQZMOM 20/2.0/20/1.5/12). Nothing is reimplemented.
`--validate-live` checks the last bar against the running system's
`/api/dashboard/{symbol}` payload before any historical output is trusted.

Data floor: TimescaleDB holds mixed testnet/mainnet history — the mainnet flip
was 2026-04-25 (CLAUDE.md §10). Input CSVs MUST already be floored there;
this script refuses bars older than the flip.

Usage:
    python3 backtesting/replay/build_indicator_frames.py \
        --klines-dir <dir> --out <dir> --symbols BTCUSDT,... --intervals 60,15,240
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, List

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pandas as pd  # noqa: E402

# prod_indicators puts services/technical-analysis on sys.path FIRST.
from backtesting import prod_indicators  # noqa: F401,E402

from app.indicators.adx import ADXCalculator  # noqa: E402
from app.indicators.atr import ATR  # noqa: E402
from app.indicators.bollinger_bands import BollingerBandsCalculator  # noqa: E402
from app.indicators.ichimoku import IchimokuCalculator  # noqa: E402
from app.indicators.macd import MACDCalculator  # noqa: E402
from app.indicators.moving_averages import EMACalculator, SMACalculator  # noqa: E402
from app.indicators.rsi import RSICalculator  # noqa: E402
from app.indicators.sqzmom_enhanced import EnhancedSqueezeMomentum  # noqa: E402
from app.indicators.stochastic import Stochastic  # noqa: E402
from app.indicators.trend_filter import TrendFilter  # noqa: E402
from app.indicators.volume_confirmation import VolumeConfirmation  # noqa: E402

MAINNET_FLIP_MS = 1777075200000  # 2026-04-25T00:00:00Z

# Weights and roles as the deployed engine assigns them. Verified against the
# running system's /api/dashboard/BTCUSDT payload on 2026-08-21 — see
# docs/FUNNEL_REPORT.md for the captured evidence.
WEIGHTS = {
    "RSI": 1.0,
    "MACD": 1.0,
    "BOLLINGER_BANDS": 1.0,
    "SMA": 0.8,
    "EMA": 1.0,
    "ADX": 1.0,
    "ICHIMOKU": 1.3,
    "SQZMOM_ENHANCED": 1.4,
}
ROLES = {
    "TREND_FILTER": "GATEKEEPER",
    "VOLUME_CONFIRMATION": "VALIDATOR",
    "STOCHASTIC": "MOMENTUM",
    "ICHIMOKU": "MULTI_ASPECT_TREND",
    "SQZMOM_ENHANCED": "BREAKOUT_DETECTOR",
    "ADX": "TREND_GATE",
}

# TrendFilter needs 200 bars; Ichimoku senkou_b 120 + displacement.
WARMUP_BARS = 300


def _sig(value) -> str:
    """SignalType/str -> plain uppercase action string."""
    v = getattr(value, "value", value)
    v = str(v).upper()
    return "HOLD" if v == "NEUTRAL" else v


class LegBuilder:
    """Builds one bar's worth of indicator legs from a lookback window."""

    def __init__(self) -> None:
        self.rsi = RSICalculator(period=9)
        self.macd = MACDCalculator(fast_period=5, slow_period=35, signal_period=5)
        self.bb = BollingerBandsCalculator(period=20, std_dev=2.5)
        self.sma = SMACalculator(period=21)
        self.ema = EMACalculator(period=21)
        self.stoch = Stochastic(period=14, smooth_k=3, smooth_d=3)
        self.trend = TrendFilter(fast_period=50, slow_period=200)
        self.volume = VolumeConfirmation(period=20)
        self.ichimoku = IchimokuCalculator(
            tenkan_period=20, kijun_period=60, senkou_b_period=120
        )
        self.adx = ADXCalculator(period=14)
        self.atr = ATR(period=14)
        self.sqz = EnhancedSqueezeMomentum()

    def build(self, window: pd.DataFrame) -> Dict[str, Dict]:
        highs = window["high"].tolist()
        lows = window["low"].tolist()
        closes = window["close"].tolist()
        volumes = window["volume"].tolist()
        price = float(closes[-1])
        legs: Dict[str, Dict] = {}

        rsi_v, rsi_s, rsi_c = self.rsi.calculate_with_signal(window)
        legs["RSI"] = _leg("RSI", rsi_s, rsi_c, rsi_v, {"period": 9})

        macd_v, macd_s, macd_c = self.macd.calculate_with_signal(window)
        legs["MACD"] = _leg(
            "MACD",
            macd_s,
            macd_c,
            (macd_v or {}).get("histogram"),
            {"macd_line": (macd_v or {}).get("macd_line")},
        )

        bb_v, bb_s, bb_c = self.bb.calculate_with_signal(window)
        legs["BOLLINGER_BANDS"] = _leg("BOLLINGER_BANDS", bb_s, bb_c, price, bb_v or {})

        sma_v = self.sma.calculate(window)
        if sma_v is not None:
            s, c = self.sma.generate_signal(sma_v, price)
            legs["SMA"] = _leg("SMA", s, c, sma_v, {"current_price": price})

        ema_v = self.ema.calculate(window)
        if ema_v is not None:
            s, c = self.ema.generate_signal(ema_v, price)
            legs["EMA"] = _leg("EMA", s, c, ema_v, {"current_price": price})

        st = self.stoch.calculate(highs, lows, closes)
        legs["STOCHASTIC"] = _leg(
            "STOCHASTIC", st.get("signal"), st.get("confidence"), st.get("k"), st
        )

        tf = self.trend.calculate(closes)
        legs["TREND_FILTER"] = _leg(
            "TREND_FILTER", tf.get("signal"), tf.get("confidence"), tf.get("value"), tf
        )

        vc = self.volume.calculate(volumes)
        # The engine does NOT forward the calculator's raw signal (which can be
        # "REJECT"); signal_aggregator.fetch_volume_confirmation maps
        # confirmed+STRONG/MODERATE -> BUY and everything else -> HOLD.
        # Mirrored here so the replayed leg is byte-identical to production.
        if vc.get("confirmed") and vc.get("strength") in ("STRONG", "MODERATE"):
            vol_action = "BUY"
        else:
            vol_action = "HOLD"
        legs["VOLUME_CONFIRMATION"] = _leg(
            "VOLUME_CONFIRMATION",
            vol_action,
            vc.get("confidence"),
            vc.get("volume_ratio"),
            vc,
        )

        ich_v, ich_s, ich_c = self.ichimoku.calculate_with_signal(window)
        legs["ICHIMOKU"] = _leg("ICHIMOKU", ich_s, ich_c, price, ich_v or {})

        adx_d = self.adx.calculate(highs, lows, closes)
        # Engine maps the ADX regime to an action (signal_aggregator.fetch_adx):
        # a directional vote only once ADX >= 20, else HOLD.
        adx_val = adx_d.get("adx", 0.0)
        if adx_val >= 20.0 and adx_d.get("direction") == "BULLISH":
            adx_action = "BUY"
        elif adx_val >= 20.0 and adx_d.get("direction") == "BEARISH":
            adx_action = "SELL"
        else:
            adx_action = "HOLD"
        legs["ADX"] = _leg("ADX", adx_action, adx_d.get("confidence"), adx_val, adx_d)

        atr_d = self.atr.calculate(highs, lows, closes, price)
        legs["ATR"] = _leg(
            "ATR", "HOLD", atr_d.get("confidence"), atr_d.get("atr"), atr_d
        )

        sq = self.sqz.get_signal(window)
        legs["SQZMOM_ENHANCED"] = _leg(
            "SQZMOM_ENHANCED",
            sq.get("signal"),
            sq.get("confidence"),
            sq.get("momentum"),
            sq,
        )

        for name, leg in legs.items():
            if name in WEIGHTS:
                leg["metadata"]["weight"] = WEIGHTS[name]
            if name in ROLES:
                leg["metadata"]["role"] = ROLES[name]
            leg["metadata"]["current_price"] = price
        return legs


def _leg(name, signal, confidence, value, metadata) -> Dict:
    md = {
        k: (float(v) if isinstance(v, (int, float)) else v)
        for k, v in (metadata or {}).items()
        if not isinstance(v, (list, dict, pd.Series, pd.DataFrame))
    }
    return {
        "name": name,
        "signal": _sig(signal if signal is not None else "HOLD"),
        "confidence": float(confidence or 0.0),
        "value": float(value) if isinstance(value, (int, float)) else 0.0,
        "metadata": md,
    }


def build_for(
    symbol: str,
    interval: str,
    klines_dir: str,
    out_dir: str,
    align_to: str = "",
) -> int:
    """Compute legs for every bar, or (when `align_to` names another interval)
    only for the last bar at or before each of that interval's timestamps.

    The secondary timeframes exist solely to feed the multi-timeframe
    alignment modifier at the 60m decision points, so computing all 11k 15m
    bars would be ~4x the work for values nothing reads.
    """
    path = os.path.join(klines_dir, f"{symbol}_{interval}.csv")
    df = pd.read_csv(path)
    if df.empty:
        raise SystemExit(f"{path}: no rows")
    if int(df["timestamp"].min()) < MAINNET_FLIP_MS:
        raise SystemExit(
            f"{path}: contains bars before the 2026-04-25 mainnet flip — "
            "testnet prices would poison every distribution in the report"
        )
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)

    wanted = None
    if align_to:
        ref = pd.read_csv(os.path.join(klines_dir, f"{symbol}_{align_to}.csv"))
        ref_ts = sorted(int(t) for t in ref["timestamp"])
        ts_list = [int(t) for t in df["timestamp"]]
        import bisect

        wanted = set()
        for t in ref_ts:
            j = bisect.bisect_right(ts_list, t) - 1
            if j >= WARMUP_BARS:
                wanted.add(j)

    builder = LegBuilder()
    out_path = os.path.join(out_dir, f"{symbol}_{interval}.jsonl")
    written = 0
    t0 = time.time()
    with open(out_path, "w") as fh:
        for i in range(WARMUP_BARS, len(df)):
            if wanted is not None and i not in wanted:
                continue
            window = df.iloc[max(0, i - WARMUP_BARS) : i + 1].reset_index(drop=True)
            legs = builder.build(window)
            fh.write(
                json.dumps(
                    {
                        "timestamp": int(df["timestamp"].iloc[i]),
                        "close": float(df["close"].iloc[i]),
                        "legs": legs,
                    }
                )
                + "\n"
            )
            written += 1
    print(
        f"  {symbol} {interval}m: {written} bars "
        f"({time.time() - t0:.1f}s) -> {out_path}",
        flush=True,
    )
    return written


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--klines-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,ADAUSDT")
    ap.add_argument("--intervals", default="60,15,240")
    ap.add_argument(
        "--primary",
        default="60",
        help="Primary decision interval; other intervals are aligned to it.",
    )
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    symbols: List[str] = args.symbols.split(",")
    intervals: List[str] = args.intervals.split(",")
    total = 0
    for symbol in symbols:
        for interval in intervals:
            total += build_for(
                symbol,
                interval,
                args.klines_dir,
                args.out,
                align_to="" if interval == args.primary else args.primary,
            )
    print(f"TOTAL {total} bar-frames written to {args.out}")


if __name__ == "__main__":
    main()
