"""Candidate 2 — funding carry.

Position against the crowded side of funding: when the last 3
settlements (the trailing 24h at 8h cadence) are all the same sign and
their mean, annualized over a 3-day minimum hold, clears a cost-scaled
threshold, take the side that COLLECTS funding rather than pays it —
positive funding means longs pay, so we SHORT; negative means we LONG.
Evaluated daily. Entry executes immediately at bar t's open (the
signal only uses settlements strictly before t, so there is no
look-ahead). Exit is evaluated the same way every day; when persistence
breaks for the currently-held side, the position exits at the NEXT
day's open. One position per symbol at a time.

Persistence-breaks conditions, in order: fewer than 3 settlements are
available yet; the newest of the 3 is stale (>= 1 day old relative to
the bar), meaning there has been no new settlement in over 24h and "the
last 3 settlements (24h)" the design doc's persistence definition names
can no longer be verified as current; the oldest-to-newest span of the
3 exceeds 24h (a collector gap can otherwise let 2 pre-gap + 1
post-gap settlement slip past the newest-only freshness check while
spanning several days — this is a second, narrower freshness guard,
not a new failure mode); the 3 available are not all the same sign; or
the sign matches but the annualized mean has dropped below threshold.

The freshness/staleness checks (newest-must-be-recent, span-must-be-
bounded) are not spelled out verbatim in the pinned rule text
(spec/task-9-brief only name sign-flip and below-threshold as
failures), but they are required for the "hold while funding pays"
semantics to ever produce a CLOSED trade at all: Trade is a frozen
dataclass with a required exit, nothing here force-closes an open
position at the end of the data, and a truly unchanging funding series
would otherwise never fail the sign/threshold checks and would hold
forever. Considered and rejected: chaining daily 1-day round trips
(re-entering every bar the signal holds) instead of a freshness check
— that reading also satisfies every test in this task, but it pays the
round-trip cost daily against a threshold built on a 3-day minimum
hold (`_SETTLEMENTS_PER_HOLD = 9`) and contradicts "hold while funding
pays" in the design doc's candidate table. Both freshness checks are
fixed thresholds pinned here, not swept parameters — they do not add
to the battery's 8-variant trial count. Reviewed and pinned as an
amendment to design doc §4 candidate 2 (task 9 fix round 1).

A symbol present in `daily` with no funding data (or an empty funding
frame) is dropped and named in a warning, never silently — matching
the design doc's "dropped AND named" rule and xs_momentum's precedent.

Funding P&L is intentionally NOT added to gross_pnl here — screen.py's
screen_trades accounts funding separately via funding_by_symbol, so
Trade carries price-only P&L.
"""

from __future__ import annotations

import logging
from bisect import bisect_left
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import pandas as pd
from costs_loader import load_costs

from edge_lab.config import SLIPPAGE_BPS, SLIPPAGE_FALLBACK_BPS
from edge_lab.trades import Trade, Variant

logger = logging.getLogger(__name__)

_costs = load_costs()

_DAY_MS = 86_400_000
_SETTLEMENTS_PER_HOLD = Decimal("9")  # 3-day min hold x 3 settlements/day @ 8h cadence
_BPS = Decimal("10000")

VARIANTS: list[Variant] = [
    Variant(
        candidate="funding_carry",
        name="thresh_1.5x",
        params=(("threshold_mult", "1.5"),),
    ),
    Variant(
        candidate="funding_carry",
        name="thresh_2x",
        params=(("threshold_mult", "2"),),
    ),
]


@dataclass(frozen=True)
class _Settlement:
    ts_ms: int
    rate: Decimal


def _load_settlements(df: pd.DataFrame) -> list[_Settlement]:
    ordered = df.sort_values("ts_ms", kind="mergesort")
    return [
        _Settlement(ts_ms=int(ts), rate=Decimal(str(rate)))
        for ts, rate in zip(ordered["ts_ms"], ordered["funding_rate"])
    ]


def _signal(
    settlements: list[_Settlement],
    ts_arr: list[int],
    t_open: int,
    rt_cost_bps: Decimal,
    threshold_mult: Decimal,
) -> Optional[Decimal]:
    """Signed mean funding rate over the trailing 3 settlements strictly
    before `t_open`, or None when persistence cannot be confirmed.

    `settlements`/`ts_arr` are ascending and parallel (`ts_arr[i] ==
    settlements[i].ts_ms`); `bisect_left` finds the count strictly before
    `t_open` in O(log n) rather than rescanning the whole series per bar.
    """
    idx = bisect_left(ts_arr, t_open)
    if idx < 3:
        return None
    last3 = settlements[idx - 3 : idx]
    if t_open - last3[-1].ts_ms >= _DAY_MS:
        return None
    if last3[-1].ts_ms - last3[0].ts_ms > _DAY_MS:
        return None
    rates = [s.rate for s in last3]
    if not (all(r > 0 for r in rates) or all(r < 0 for r in rates)):
        return None
    mean_rate = sum(rates) / Decimal("3")
    if abs(mean_rate) * _SETTLEMENTS_PER_HOLD < threshold_mult * rt_cost_bps / _BPS:
        return None
    return mean_rate


def generate_trades(
    daily: dict[str, pd.DataFrame],
    funding: dict[str, pd.DataFrame],
    variant: Variant,
) -> list[Trade]:
    threshold_mult = Decimal(dict(variant.params)["threshold_mult"])

    trades: list[Trade] = []
    skipped: list[str] = []

    for symbol, df in daily.items():
        fdf = funding.get(symbol)
        if fdf is None or fdf.empty:
            skipped.append(symbol)
            continue

        settlements = _load_settlements(fdf)
        ts_arr = [s.ts_ms for s in settlements]
        rt_cost_bps = _costs.round_trip_cost_bps(
            symbol,
            entry_liquidity=_costs.Liquidity.TAKER,
            exit_liquidity=_costs.Liquidity.TAKER,
            schedule=_costs.FeeSchedule.bybit_linear_perp(),
            slippage_table=SLIPPAGE_BPS,
            slippage_fallback=SLIPPAGE_FALLBACK_BPS,
        )

        ordered = df.sort_values("ts_ms", kind="mergesort")
        ts_list = [int(ts) for ts in ordered["ts_ms"].tolist()]
        open_list = ordered["open"].tolist()

        position: Optional[tuple[str, int, float]] = None  # side, entry_ts, entry_px
        pending_exit = False

        for t, o in zip(ts_list, open_list):
            if pending_exit and position is not None:
                side, entry_ts, entry_px = position
                trades.append(
                    Trade(
                        symbol=symbol,
                        side=side,
                        entry_ts_ms=entry_ts,
                        exit_ts_ms=t,
                        entry_px=entry_px,
                        exit_px=o,
                    )
                )
                position = None
                pending_exit = False

            signal = _signal(settlements, ts_arr, t, rt_cost_bps, threshold_mult)

            if position is None:
                if signal is not None:
                    side = "SHORT" if signal > 0 else "LONG"
                    position = (side, t, o)
            else:
                side, _entry_ts, _entry_px = position
                persists = signal is not None and (
                    (side == "SHORT" and signal > 0) or (side == "LONG" and signal < 0)
                )
                if not persists:
                    pending_exit = True

    if skipped:
        logger.warning(
            "funding_carry: skipped %d symbol(s) lacking funding data: %s",
            len(skipped),
            sorted(skipped),
        )

    return trades
