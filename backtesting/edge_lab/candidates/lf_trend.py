"""Candidate 3 — low-frequency Donchian breakout trend.

Per symbol independently, a single-position (flat/long/short) breakout
system driven by Task 2's `donchian()` channel (already causal — the
channel value at bar t is computed from bars strictly before t). A
signal read off bar t's close only ever fills at bar t+1's open, so a
signal never fills on the bar that produced it.

LONG entry: close[t] > dc_entry_high[t]. LONG exit: close[t] < dc_exit_low[t].
SHORT is the mirror: enter on close[t] < dc_entry_low[t], exit on
close[t] > dc_exit_high[t]. One position per symbol. An exit signal for
the open side plus an opposite-side entry signal on the same bar
stop-and-reverse: the old leg closes and the new leg opens at the same
t+1 open. A position still open when the data ends is discarded — only
completed round trips are emitted.
"""

from __future__ import annotations

import pandas as pd

from edge_lab.indicators import donchian
from edge_lab.trades import Trade, Variant

_CHANNELS = ((20, 10), (55, 20))

VARIANTS: list[Variant] = [
    Variant(
        candidate="lf_trend",
        name=f"dc_{entry_n}_{exit_n}",
        params=(("entry_n", entry_n), ("exit_n", exit_n)),
    )
    for entry_n, exit_n in _CHANNELS
]


def _symbol_trades(
    symbol: str, df: pd.DataFrame, entry_n: int, exit_n: int
) -> list[Trade]:
    ordered = df.sort_values("ts_ms").reset_index(drop=True)
    dc = donchian(ordered, entry_n, exit_n)

    ts = ordered["ts_ms"].tolist()
    open_ = ordered["open"].tolist()
    close = ordered["close"].tolist()
    entry_high = dc["dc_entry_high"].tolist()
    entry_low = dc["dc_entry_low"].tolist()
    exit_high = dc["dc_exit_high"].tolist()
    exit_low = dc["dc_exit_low"].tolist()

    trades: list[Trade] = []
    side: str | None = None  # None | "LONG" | "SHORT"
    entry_idx: int | None = None

    n = len(ordered)
    for t in range(n - 1):  # bar t+1 must exist to fill a signal from bar t
        c = close[t]
        long_entry = not pd.isna(entry_high[t]) and c > entry_high[t]
        long_exit = not pd.isna(exit_low[t]) and c < exit_low[t]
        short_entry = not pd.isna(entry_low[t]) and c < entry_low[t]
        short_exit = not pd.isna(exit_high[t]) and c > exit_high[t]

        fill_idx = t + 1

        if side is None:
            if long_entry:
                side, entry_idx = "LONG", fill_idx
            elif short_entry:
                side, entry_idx = "SHORT", fill_idx
        elif side == "LONG":
            if short_entry:  # exit + opposite entry same bar: stop-and-reverse
                trades.append(
                    Trade(
                        symbol=symbol,
                        side="LONG",
                        entry_ts_ms=ts[entry_idx],
                        exit_ts_ms=ts[fill_idx],
                        entry_px=open_[entry_idx],
                        exit_px=open_[fill_idx],
                    )
                )
                side, entry_idx = "SHORT", fill_idx
            elif long_exit:
                trades.append(
                    Trade(
                        symbol=symbol,
                        side="LONG",
                        entry_ts_ms=ts[entry_idx],
                        exit_ts_ms=ts[fill_idx],
                        entry_px=open_[entry_idx],
                        exit_px=open_[fill_idx],
                    )
                )
                side, entry_idx = None, None
        elif side == "SHORT":
            if long_entry:  # exit + opposite entry same bar: stop-and-reverse
                trades.append(
                    Trade(
                        symbol=symbol,
                        side="SHORT",
                        entry_ts_ms=ts[entry_idx],
                        exit_ts_ms=ts[fill_idx],
                        entry_px=open_[entry_idx],
                        exit_px=open_[fill_idx],
                    )
                )
                side, entry_idx = "LONG", fill_idx
            elif short_exit:
                trades.append(
                    Trade(
                        symbol=symbol,
                        side="SHORT",
                        entry_ts_ms=ts[entry_idx],
                        exit_ts_ms=ts[fill_idx],
                        entry_px=open_[entry_idx],
                        exit_px=open_[fill_idx],
                    )
                )
                side, entry_idx = None, None

    return trades


def generate_trades(daily: dict[str, pd.DataFrame], variant: Variant) -> list[Trade]:
    params = dict(variant.params)
    entry_n, exit_n = params["entry_n"], params["exit_n"]

    trades: list[Trade] = []
    for symbol, df in daily.items():
        trades.extend(_symbol_trades(symbol, df, entry_n, exit_n))
    return trades
