#!/usr/bin/env python3
"""
Probe: count how often each phase1_strategy_prod gate trips across real bars.

Goal: identify which predicate is responsible for the 0-trade walk-forward
result of 2026-05-19. Walks the same data the WF run used (180d, 60m,
4320 bars/symbol) and tallies pass/fail at each stage.

No state mutation; pure read + count.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections import Counter


_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from backtesting.data_downloader import HistoricalDataDownloader  # noqa: E402
from backtesting.prod_indicators import (  # noqa: E402
    ADX,
    EMA,
    RSI,
    TrendFilter,
    VolumeConfirmation,
)


async def probe(symbol: str, days: int = 180, interval: str = "60") -> None:
    dl = HistoricalDataDownloader()
    data = await dl.download_historical_data(
        symbol=symbol, interval=interval, days=days
    )
    if data is None or data.empty:
        print(f"[{symbol}] NO DATA")
        return

    n = len(data)
    print(f"\n=== {symbol} — {n} bars ({interval}m, {days}d) ===")
    print(f"price min/max: {data['close'].min():.4f} / {data['close'].max():.4f}")

    counters: Counter[str] = Counter()
    counters["bars"] = n

    for idx in range(50, n):
        hist = data.iloc[: idx + 1]
        close_list = hist["close"].tolist()
        high_list = hist["high"].tolist()
        low_list = hist["low"].tolist()
        volume_list = hist["volume"].tolist()
        current_price = float(data.iloc[idx]["close"])

        counters["after_warmup"] += 1

        rsi_val = RSI(period=9).calculate(hist)
        if rsi_val is None:
            counters["rsi_none"] += 1
            continue
        ema_20 = EMA(period=20).calculate(hist)
        if ema_20 is None:
            counters["ema_none"] += 1
            continue
        counters["rsi_ema_ok"] += 1

        # Track raw distributions
        if rsi_val < 20:
            counters["rsi_lt20"] += 1
        if rsi_val > 80:
            counters["rsi_gt80"] += 1
        if current_price > ema_20:
            counters["above_ema20"] += 1
        else:
            counters["below_ema20"] += 1

        # ADX
        adx = ADX().calculate(high_list, low_list, close_list)
        adx_val = float(adx.get("adx", 0.0))
        direction = adx.get("direction", "NEUTRAL")
        if adx_val < 20.0:
            counters["adx_block"] += 1
            continue
        counters["adx_ok"] += 1

        trend = TrendFilter().calculate(close_list)
        if trend.get("trend") == "NEUTRAL" and len(close_list) < 200:
            counters["trend_warmup_block"] += 1

        volume = VolumeConfirmation().calculate(volume_list)
        if not volume.get("confirmed"):
            counters["volume_block"] += 1
            continue
        counters["volume_ok"] += 1

        # Mean-rev fixed polarity (2026-05-20): rsi<20 + price<ema20 = BUY,
        # rsi>80 + price>ema20 = SELL. TrendFilter + ADX still veto opposing
        # major trend.
        if rsi_val < 20:
            counters["buy_rsi_hit"] += 1
            if current_price < ema_20:
                counters["buy_rsi_and_below_ema"] += 1
                if trend.get("trend") != "BEARISH":
                    counters["buy_trend_ok"] += 1
                    if direction != "BEARISH":
                        counters["BUY_SIGNAL"] += 1
        if rsi_val > 80:
            counters["sell_rsi_hit"] += 1
            if current_price > ema_20:
                counters["sell_rsi_and_above_ema"] += 1
                if trend.get("trend") != "BULLISH":
                    counters["sell_trend_ok"] += 1
                    if direction != "BULLISH":
                        counters["SELL_SIGNAL"] += 1

    for k, v in sorted(counters.items(), key=lambda kv: -kv[1]):
        pct = v / n * 100 if n else 0.0
        print(f"  {k:30s} {v:7d}  ({pct:5.1f}%)")


async def main() -> None:
    symbols = sys.argv[1:] or ["BTCUSDT"]
    for s in symbols:
        await probe(s)


if __name__ == "__main__":
    asyncio.run(main())
