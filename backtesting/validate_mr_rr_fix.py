#!/usr/bin/env python3
"""
Validation study for the 2026-07-28 mean-reversion R/R fix.

The live mean-reversion strategy (services/trading-engine/app/strategies/
mean_reversion_strategy.py) targets the SMA and used to place the stop at
1.5x the distance-to-mean (risking 1.5R for a 1.0R reward). The fix moves the
stop to 0.75x the distance.

This script replays both variants over the cached Bybit hourly data
(backtesting/data/*_90d_bybit.csv) with identical entries, so the ONLY
difference is the stop distance. Costs: 0.06% taker fee per side + 0.02%
slippage per side.

Run: python3 validate_mr_rr_fix.py
"""

import glob
import os
import pandas as pd

FEE = 0.0006
SLIP = 0.0002
COST_PER_SIDE = FEE + SLIP
SMA_PERIOD = 20
MIN_DEVIATION = 0.015  # enter when price is 1.5%+ below the SMA
MAX_HOLD_BARS = 48     # mirrors the live 48h max-hold on hourly bars


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder ADX — used to mirror the hybrid router's ADX<25 ranging filter."""
    high, low, close = df["high"], df["low"], df["close"]
    up = high.diff()
    down = -low.diff()
    plus_dm = ((up > down) & (up > 0)) * up
    minus_dm = ((down > up) & (down > 0)) * down
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return dx.ewm(alpha=1 / period, adjust=False).mean()


def run(df: pd.DataFrame, stop_mult: float, use_regime_filter: bool = True) -> dict:
    closes = df["close"].reset_index(drop=True)
    lows = df["low"].reset_index(drop=True)
    highs = df["high"].reset_index(drop=True)
    sma = closes.rolling(SMA_PERIOD).mean()
    adx_series = adx(df.reset_index(drop=True)) if use_regime_filter else None

    trades = []
    i = SMA_PERIOD
    n = len(closes)
    while i < n - 1:
        price = closes[i]
        mean = sma[i]
        if pd.isna(mean):
            i += 1
            continue
        deviation = (mean - price) / mean
        regime_ok = True
        if adx_series is not None:
            a = adx_series[i]
            regime_ok = pd.notna(a) and a < 25  # hybrid router: MR only when ranging
        if regime_ok and deviation >= MIN_DEVIATION:
            entry = price
            dist = mean - price
            target = mean
            stop = entry - dist * stop_mult
            # walk forward
            exit_px = None
            for j in range(i + 1, min(i + 1 + MAX_HOLD_BARS, n)):
                if lows[j] <= stop:
                    exit_px = stop
                    break
                if highs[j] >= target:
                    exit_px = target
                    break
            if exit_px is None:
                j = min(i + MAX_HOLD_BARS, n - 1)
                exit_px = closes[j]
            gross = (exit_px - entry) / entry
            net = gross - 2 * COST_PER_SIDE
            trades.append(net)
            i = j + 1  # no overlapping trades
        else:
            i += 1

    if not trades:
        return {"trades": 0}
    s = pd.Series(trades)
    wins = s[s > 0]
    losses = s[s <= 0]
    pf = wins.sum() / abs(losses.sum()) if len(losses) and losses.sum() != 0 else float("inf")
    return {
        "trades": len(s),
        "win_rate": len(wins) / len(s) * 100,
        "avg_net_ret_pct": s.mean() * 100,
        "total_net_ret_pct": s.sum() * 100,
        "profit_factor": pf,
    }


def main():
    files = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "data", "*_60m_90d_bybit.csv")))
    print(f"{'symbol':10s} {'variant':10s} {'trades':>6s} {'win%':>7s} {'avg%':>8s} {'total%':>8s} {'PF':>6s}")
    agg = {"old": [], "new": []}
    for f in files:
        symbol = os.path.basename(f).split("_")[0]
        df = pd.read_csv(f)
        cols = {c.lower(): c for c in df.columns}
        df = df.rename(columns={cols.get("close", "close"): "close",
                                cols.get("low", "low"): "low",
                                cols.get("high", "high"): "high"})
        for name, mult in (("old(1.5x)", 1.5), ("new(0.75x)", 0.75)):
            r = run(df, mult)
            key = "old" if mult == 1.5 else "new"
            if r["trades"]:
                agg[key].append(r["total_net_ret_pct"])
                print(f"{symbol:10s} {name:10s} {r['trades']:6d} {r['win_rate']:7.1f} "
                      f"{r['avg_net_ret_pct']:8.3f} {r['total_net_ret_pct']:8.2f} {r['profit_factor']:6.2f}")
            else:
                print(f"{symbol:10s} {name:10s} {0:6d}       -        -        -      -")
    print("-" * 60)
    print(f"SUM total net return: old(1.5x) = {sum(agg['old']):+.2f}%   new(0.75x) = {sum(agg['new']):+.2f}%")


if __name__ == "__main__":
    main()
