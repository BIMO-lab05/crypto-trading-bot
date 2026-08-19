"""Maker fill realism for battery #3 re-gates (manifest 2026-08-19, frozen).

A limit entry at the signal price fills ONLY if the bar immediately after
entry_ts_ms trades strictly through the level (long: next low < limit;
short: next high > limit). Touch is not a fill — the gap audit documented
touch-fill as a phantom-profit source. Unfilled after that one bar = missed
trade, counted and reported. Exit prices are left untouched here; the fee
treatment (maker entry / taker stop) is applied at the screening layer.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from edge_lab.trades import Trade

MAKER_NOTE = (
    "maker-mode: entry fills only on strict next-bar trade-through; "
    "missed entries dropped and counted; slippage table unchanged"
)


@dataclass(frozen=True)
class MakerFillResult:
    filled: list[Trade]
    missed: int
    fill_rate: float


def _next_bar(df: pd.DataFrame, ts_ms: int):
    after = df[df["ts_ms"] > ts_ms]
    return None if after.empty else after.iloc[0]


def apply_maker_fill(
    trades: list[Trade], bars: dict[str, pd.DataFrame]
) -> MakerFillResult:
    filled: list[Trade] = []
    missed = 0
    for t in trades:
        df = bars.get(t.symbol)
        nxt = None if df is None else _next_bar(df, t.entry_ts_ms)
        if nxt is None:
            missed += 1
            continue
        through = (
            float(nxt["low"]) < t.entry_px
            if t.side == "LONG"
            else float(nxt["high"]) > t.entry_px
        )
        if through:
            filled.append(t)
        else:
            missed += 1
    total = len(trades)
    return MakerFillResult(
        filled=filled,
        missed=missed,
        fill_rate=(len(filled) / total) if total else 0.0,
    )
