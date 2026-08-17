"""Candidate 1 — weekly cross-sectional momentum.

Rebalance at each Monday 00:00 UTC bar's open. Rank symbols by trailing
L-day close-over-close return using only closes strictly before the
rebalance bar (the Monday bar itself never contributes to its own signal).
Long the top 6, short the bottom 6, equal weight. Full close/reopen each
week — membership continuity is not netted, which is conservative on
costs. Positions exit at the next rebalance's open.
"""

from __future__ import annotations

import logging
import math

import pandas as pd

from edge_lab.trades import Trade, Variant

logger = logging.getLogger(__name__)

_LOOKBACKS = (7, 30, 90)

VARIANTS: list[Variant] = [
    Variant(
        candidate="xs_momentum",
        name=f"lookback_{L}d",
        params=(("lookback_days", L),),
    )
    for L in _LOOKBACKS
]


def _is_monday(ts_ms: int) -> bool:
    return pd.Timestamp(ts_ms, unit="ms", tz="UTC").dayofweek == 0


def generate_trades(daily: dict[str, pd.DataFrame], variant: Variant) -> list[Trade]:
    lookback_days = dict(variant.params)["lookback_days"]

    all_ts = sorted({ts for df in daily.values() for ts in df["ts_ms"]})
    mondays = [ts for ts in all_ts if _is_monday(ts)]
    if len(mondays) < 2:
        return []

    # Per-symbol close lookup by ts_ms and sorted ts_ms array for indexing.
    closes: dict[str, dict[int, float]] = {}
    opens: dict[str, dict[int, float]] = {}
    ts_sorted: dict[str, list[int]] = {}
    for sym, df in daily.items():
        ordered = df.sort_values("ts_ms")
        ts_list = ordered["ts_ms"].tolist()
        ts_sorted[sym] = ts_list
        closes[sym] = dict(zip(ts_list, ordered["close"].tolist()))
        opens[sym] = dict(zip(ts_list, ordered["open"].tolist()))

    trades: list[Trade] = []

    for i in range(len(mondays) - 1):
        m = mondays[i]
        m_next = mondays[i + 1]

        momentum: dict[str, float] = {}
        skipped: list[str] = []
        for sym, ts_list in ts_sorted.items():
            if m not in opens[sym] or m_next not in opens[sym]:
                skipped.append(sym)
                continue

            # bars strictly before m, in ascending order
            prior = [t for t in ts_list if t < m]
            if len(prior) < lookback_days + 1:
                skipped.append(sym)
                continue

            last_close_ts = prior[-1]
            lookback_ts = prior[-(lookback_days + 1)]
            c_recent = closes[sym][last_close_ts]
            c_past = closes[sym][lookback_ts]
            if not (math.isfinite(c_recent) and math.isfinite(c_past)) or c_past <= 0:
                skipped.append(sym)
                continue
            momentum[sym] = c_recent / c_past - 1

        if skipped:
            logger.warning(
                "xs_momentum rebalance %s: skipped %d symbol(s) lacking data: %s",
                m,
                len(skipped),
                sorted(skipped),
            )

        n_eligible = len(momentum)
        if n_eligible == 0:
            continue

        quintile = 6 if n_eligible >= 12 else max(1, n_eligible // 5)
        if 2 * quintile > n_eligible:
            # no cross-section wide enough to hold non-overlapping long/short
            # books; a 1-name book would be a directional bet, not xs momentum
            continue

        ranked = sorted(momentum.items(), key=lambda kv: kv[1], reverse=True)
        long_syms = [sym for sym, _ in ranked[:quintile]]
        short_syms = [sym for sym, _ in ranked[-quintile:]]

        for sym in sorted(long_syms):
            trades.append(
                Trade(
                    symbol=sym,
                    side="LONG",
                    entry_ts_ms=m,
                    exit_ts_ms=m_next,
                    entry_px=opens[sym][m],
                    exit_px=opens[sym][m_next],
                )
            )
        for sym in sorted(short_syms):
            trades.append(
                Trade(
                    symbol=sym,
                    side="SHORT",
                    entry_ts_ms=m,
                    exit_ts_ms=m_next,
                    entry_px=opens[sym][m],
                    exit_px=opens[sym][m_next],
                )
            )

    return trades
