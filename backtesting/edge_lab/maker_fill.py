"""Maker fill realism for battery #3 re-gates (manifest 2026-08-19, frozen).

Two entry bases, because the candidates disagree about which bar a
resting limit order would sit on (final-review C1, 2026-08-19):

- **"close"** (spec §3 B3's literal shape): the signal fires on bar t's
  close and `entry_px` IS that same bar's close. The order rests from
  bar t onward, so the first bar it can trade through is the strict
  next-adjacent bar (`entry_ts_ms + bar_interval_ms`, no gap). This is
  the ORIGINAL (pre-fix) behavior, unchanged. `pairs_statarb` matches
  this shape (`entry_px` is read directly from a `closes[...]` dict).
- **"open"** (the shape 5 of the 6 re-gated candidates actually have):
  the signal fires on bar t's close but `entry_ts_ms`/`entry_px` are
  BOTH stamped from bar t+1 (the fill bar), with `entry_px` = that same
  bar's open. The order therefore rests ON bar t+1 itself — the bar
  named by `entry_ts_ms` — not on the bar after it. Testing the bar
  after `entry_ts_ms` (the pre-fix behavior) skips the only bar the
  order could actually have filled on.

  The limit price for "open" is read from the bars frame's own `open`
  column at `entry_ts_ms`, never from `t.entry_px` directly: at least one
  "open"-basis candidate (`baseline_rsi_ema`, via `backtest_engine.py`'s
  ATR-floor slippage) stores a SLIPPAGE-INFLATED `entry_px`, and testing
  `low < entry_px` against that inflated price for a LONG is true by
  construction (since `low <= open <= open*(1+slip)` always) — a vacuous
  fill rate of 1.000 that says nothing about fillability. Reading the raw
  bar open sidesteps that regardless of what a candidate happened to
  stamp into `entry_px`. The other four "open" candidates already store
  the unmodified bar open in `entry_px`, so this produces the identical
  number for them.

Both bases require STRICT trade-through (long: bar's low < limit; short:
bar's high > limit) — touch is not a fill, per the gap audit's
phantom-profit finding. A missing bar (the tested bar does not exist in
the frame — a gap for "close", or the entry bar itself absent for "open")
counts as a missed trade, never a fill: reaching past a hole would inflate
fill_rate with fabricated edge (more elapsed time/data, more chances to
trade through). Unfilled = missed trade, counted and reported.

Exit prices are left untouched here. Fee treatment (which leg pays maker
vs taker, and what slippage applies) is a screening-layer concern — see
`run_maker_regate.py`'s M1 conservative cost model (maker fee, no
slippage, on the entry leg; taker fee PLUS the same per-symbol slippage
table on the exit leg).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from edge_lab.trades import Trade

MAKER_NOTE = (
    "maker-mode: entry basis is per-candidate — 'open' tests the entry bar "
    "itself (limit = that bar's own open, read from the bars frame, never "
    "from a possibly slippage-adjusted entry_px); 'close' tests the strict "
    "next-adjacent bar (limit = entry_px, the signal bar's close). Both "
    "require strict trade-through, never touch; a missing tested bar = "
    "missed. Missed entries are dropped and counted, never filled. Cost "
    "model (applied at screening, not here): the entry leg pays the maker "
    "fee with NO slippage (a resting order fills at the price it posted); "
    "the exit leg pays the taker fee PLUS the same per-symbol slippage "
    "table used everywhere else in this battery — 'slippage table "
    "unchanged' describes that table, not a claim that the maker leg pays "
    "slippage."
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


def _bar_at(df: pd.DataFrame, ts_ms: int):
    """Exact-timestamp lookup — the bar the "open"-basis order rests on."""
    match = df[df["ts_ms"] == ts_ms]
    if match.empty:
        return None
    return match.iloc[0]


def apply_maker_fill(
    trades: list[Trade],
    bars: dict[str, pd.DataFrame],
    bar_interval_ms: int,
    entry_basis: Literal["open", "close"] = "close",
) -> MakerFillResult:
    filled: list[Trade] = []
    missed = 0
    for t in trades:
        df = bars.get(t.symbol)

        if entry_basis == "open":
            bar = None if df is None else _bar_at(df, t.entry_ts_ms)
            if bar is None:
                missed += 1
                continue
            limit_px = float(bar["open"])
            through = (
                float(bar["low"]) < limit_px
                if t.side == "LONG"
                else float(bar["high"]) > limit_px
            )
        else:
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
