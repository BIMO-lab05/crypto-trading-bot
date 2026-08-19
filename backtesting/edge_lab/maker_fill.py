"""Maker fill realism for battery #3 re-gates (manifest 2026-08-19, frozen).

A limit entry at the signal price fills ONLY if the bar strictly
next-adjacent to entry_ts_ms (i.e. at entry_ts_ms + bar_interval_ms, no
gap) trades through the level (long: next low < limit; short: next high >
limit). Touch is not a fill — the gap audit documented touch-fill as a
phantom-profit source. A kline hole means no adjacent bar exists, so that
counts as a missed trade too — reaching across a gap to a later bar would
inflate fill_rate with fabricated edge (more elapsed time, more chances to
trade through). Unfilled = missed trade, counted and reported. Exit prices
are left untouched here; the fee treatment (maker entry / taker stop) is
applied at the screening layer.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from edge_lab.trades import Trade

MAKER_NOTE = (
    "maker-mode: entry fills only on strict next-adjacent-bar trade-through; "
    "gapped bars = missed; missed entries dropped and counted; "
    "slippage table unchanged"
)


@dataclass(frozen=True)
class MakerFillResult:
    filled: list[Trade]
    missed: int
    fill_rate: float


def _next_bar(df: pd.DataFrame, ts_ms: int):
    after = df[df["ts_ms"] > ts_ms]
    if after.empty:
        return None
    return after.nsmallest(1, "ts_ms").iloc[0]


def apply_maker_fill(
    trades: list[Trade], bars: dict[str, pd.DataFrame], bar_interval_ms: int
) -> MakerFillResult:
    filled: list[Trade] = []
    missed = 0
    for t in trades:
        df = bars.get(t.symbol)
        nxt = None if df is None else _next_bar(df, t.entry_ts_ms)
        adjacent = (
            nxt is not None and int(nxt["ts_ms"]) == t.entry_ts_ms + bar_interval_ms
        )
        if not adjacent:
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
