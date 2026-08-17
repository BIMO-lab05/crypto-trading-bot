"""Candidate 4 — squeeze-release volatility breakout on 240m bars.

A squeeze (BB inside KC) that has held for >= min_squeeze_bars consecutive
bars and releases (squeeze_on flips False) on a close outside the Keltner
channel signals a breakout in the direction of the break. Entry at the
next bar's open. Exit on an adverse close through a stop frozen at the
signal bar's ATR14, filled at the following bar's open (no intrabar stop
fills — conservative simplification), or a 30-bar time exit at that bar's
open, whichever comes first. One position per symbol at a time.
"""

from __future__ import annotations

import pandas as pd

from edge_lab.indicators import atr, keltner, squeeze_on
from edge_lab.trades import Trade, Variant

VARIANTS: list[Variant] = [
    Variant(
        "vol_breakout",
        "sqz_default",
        (
            ("bb_n", 20),
            ("bb_mult", "2.0"),
            ("kc_n", 20),
            ("kc_mult", "1.5"),
            ("atr_n", 14),
            ("stop_atr_mult", "2.0"),
            ("max_hold_bars", 30),
            ("min_squeeze_bars", 6),
        ),
    )
]


def _generate_symbol_trades(df: pd.DataFrame, symbol: str, p: dict) -> list[Trade]:
    ordered = df.sort_values("ts_ms").reset_index(drop=True)
    n = len(ordered)

    sqz = squeeze_on(ordered, p["bb_n"], p["bb_mult"], p["kc_n"], p["kc_mult"])
    kc = keltner(ordered, p["kc_n"], p["kc_mult"])
    atr14 = atr(ordered, p["atr_n"])

    ts = ordered["ts_ms"].tolist()
    open_ = ordered["open"].tolist()
    close = ordered["close"].tolist()
    kc_upper = kc["kc_upper"].tolist()
    kc_lower = kc["kc_lower"].tolist()
    atr_vals = atr14.tolist()
    sqz_on = sqz.tolist()

    min_squeeze_bars = p["min_squeeze_bars"]
    stop_atr_mult = p["stop_atr_mult"]
    max_hold_bars = p["max_hold_bars"]

    trades: list[Trade] = []
    in_position = False
    pos_side = None
    pos_entry_idx = None
    pos_entry_px = None
    pos_stop = None
    pos_deadline_idx = None

    for t in range(1, n):
        if in_position:
            if t == pos_deadline_idx:
                # Time exit: the deadline is known at entry, so the
                # position is already flat as of this bar's own open —
                # no stop check runs against this bar's close.
                trades.append(
                    Trade(
                        symbol=symbol,
                        side=pos_side,
                        entry_ts_ms=ts[pos_entry_idx],
                        exit_ts_ms=ts[t],
                        entry_px=pos_entry_px,
                        exit_px=open_[t],
                    )
                )
                in_position = False
                pos_side = None
                pos_entry_idx = None
                pos_entry_px = None
                pos_stop = None
                pos_deadline_idx = None
            else:
                # Adverse-stop breach on this bar's close (only checked
                # while strictly before the deadline bar).
                breached = (pos_side == "LONG" and close[t] <= pos_stop) or (
                    pos_side == "SHORT" and close[t] >= pos_stop
                )
                if not breached:
                    continue

                exit_idx = t + 1
                if exit_idx < n:
                    trades.append(
                        Trade(
                            symbol=symbol,
                            side=pos_side,
                            entry_ts_ms=ts[pos_entry_idx],
                            exit_ts_ms=ts[exit_idx],
                            entry_px=pos_entry_px,
                            exit_px=open_[exit_idx],
                        )
                    )
                # Open position at data end (no exit bar available) is
                # discarded either way.
                in_position = False
                pos_side = None
                pos_entry_idx = None
                pos_entry_px = None
                pos_stop = None
                pos_deadline_idx = None
            # Flat as of this bar either way — fall through to look for
            # a fresh signal below (release + entry needs bar t+1 anyway,
            # so re-checking the same bar t is safe).

        # Squeeze-release signal: sqz_on True for >= min_squeeze_bars bars
        # ending at t-1, and False at t.
        if sqz_on[t]:
            continue
        run_start = t - min_squeeze_bars
        if run_start < 0:
            continue
        if not all(sqz_on[j] for j in range(run_start, t)):
            continue

        if pd.isna(kc_upper[t]) or pd.isna(kc_lower[t]):
            continue

        if close[t] > kc_upper[t]:
            side = "LONG"
        elif close[t] < kc_lower[t]:
            side = "SHORT"
        else:
            continue

        entry_idx = t + 1
        if entry_idx >= n:
            continue
        signal_atr = atr_vals[t]
        if pd.isna(signal_atr):
            continue

        entry_px = open_[entry_idx]
        stop = (
            entry_px - stop_atr_mult * signal_atr
            if side == "LONG"
            else entry_px + stop_atr_mult * signal_atr
        )

        in_position = True
        pos_side = side
        pos_entry_idx = entry_idx
        pos_entry_px = entry_px
        pos_stop = stop
        pos_deadline_idx = entry_idx + max_hold_bars

    return trades


def generate_trades(h4: dict[str, pd.DataFrame], variant: Variant) -> list[Trade]:
    p = dict(variant.params)
    params = {
        "bb_n": int(p["bb_n"]),
        "bb_mult": float(p["bb_mult"]),
        "kc_n": int(p["kc_n"]),
        "kc_mult": float(p["kc_mult"]),
        "atr_n": int(p["atr_n"]),
        "stop_atr_mult": float(p["stop_atr_mult"]),
        "max_hold_bars": int(p["max_hold_bars"]),
        "min_squeeze_bars": int(p["min_squeeze_bars"]),
    }

    trades: list[Trade] = []
    for symbol, df in h4.items():
        trades.extend(_generate_symbol_trades(df, symbol, params))
    trades.sort(key=lambda t: t.entry_ts_ms)
    return trades
