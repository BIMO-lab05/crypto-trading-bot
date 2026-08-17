"""Gate 2 — daily returns builder + CPCV/DSR, with a trials floor.

Two pieces:

`daily_returns_from_trades` turns a trade list into a calendar-daily net
return series (float), honest about capital utilization — flat days (no
open position) are included as 0.0 rather than dropped, so the resulting
Sharpe/DSR is not inflated by silently compressing the timeline down to
only the days a trade happened to be open.

`run_gate2` composes CPCV path returns into a Deflated Sharpe Ratio with a
`num_trials` floor, per the h4 kill-test precedent
(`killtests/h4_information.py:134-155`). It deliberately does NOT use
`cpcv.cpcv_to_dsr` — that helper hard-codes `num_trials=len(paths)` and
cannot honor a floor set by the battery's known search-space size
(CLAUDE.md §2: 8 candidate variants + 8 historical families = 16).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from edge_lab.config import (
    CPCV_EMBARGO_PCT,
    CPCV_K_TEST_GROUPS,
    CPCV_N_GROUPS,
    DSR_THRESHOLD,
    MIN_POSITIVE_PATH_FRAC,
    NUM_TRIALS_FLOOR,
)
from edge_lab.trades import Trade

# killtests/*.py do absolute `from killtests.xxx import ...` imports, which
# assume `backtesting/` (this file's parent) is on sys.path. Every existing
# entry point arranges that already; this bootstrap makes gate2.py
# self-sufficient too, so importing edge_lab.gate2 directly never depends
# on caller ordering.
_BACKTESTING = str(Path(__file__).resolve().parents[1])
if _BACKTESTING not in sys.path:
    sys.path.insert(0, _BACKTESTING)

from killtests.offline_ensemble import _load_kernels  # noqa: E402

DAY = 86_400_000


@dataclass
class Gate2Result:
    dsr: float
    pooled_pf: float
    positive_path_frac: float
    n_paths_valid: int
    n_samples: int
    sharpe_mean: float
    sharpe_std: float
    passed: bool
    reasons: list[str]


def _index_closes(
    daily_closes: Mapping[str, pd.DataFrame],
) -> dict[str, dict[int, float]]:
    """Per-symbol {day_number: close}, day_number = ts_ms // DAY."""
    return {
        symbol: {
            int(ts_ms) // DAY: float(close)
            for ts_ms, close in zip(df["ts_ms"], df["close"])
        }
        for symbol, df in daily_closes.items()
    }


def _close(indexed: dict[int, float], day: int, symbol: str) -> float:
    """Daily close for `day`, carrying the previous day's close over a hole.

    Gate 0 tolerates a single missing bar by design (`sanity.check_klines`
    flags a defect only above 2x the interval), so a one-bar hole reaches
    here on data the battery has already blessed. Raising on it would ERROR
    whole candidate files over data Gate 0 called clean.

    The carry is deliberately ONE day deep. Two or more consecutive missing
    bars is a gap Gate 0 would itself have flagged, so it stays loud rather
    than silently compounding a stale close across a widening hole.
    """
    if day in indexed:
        return indexed[day]
    carried = indexed.get(day - 1)
    if carried is not None:
        return carried
    raise KeyError(
        f"no daily close for {symbol} on day {day} OR day {day - 1} — two or "
        "more consecutive missing bars, which Gate 0 flags as a defect "
        "(sanity.check_klines: gap > 2x interval). Single-bar holes are "
        "carried; this is not one."
    )


def daily_returns_from_trades(
    trades: Sequence[Trade],
    daily_closes: Mapping[str, pd.DataFrame],
    start_ms: int,
    end_ms: int,
    cost_bps_rt: Mapping[str, Decimal],
    funding: Mapping[str, list],
) -> pd.Series:
    """Calendar-daily net return series (float) over [start_ms, end_ms].

    Flat days (no trade open) are included at 0.0 — an honest capital
    utilization measure rather than a timeline that silently skips to only
    the days something happened.

    Per trade per day: fractional close-to-close return of its symbol,
    signed by side. Entry day uses entry_px -> that day's close; exit day
    uses the previous day's close -> exit_px; a trade opened and closed
    within the same calendar day uses entry_px -> exit_px directly. Half
    the round-trip cost (`cost_bps_rt / 2 / 10000`) is deducted on the
    entry day and half on the exit day (both halves land on the same day
    for a same-day trade, reconstituting the full round-trip cost).
    Funding settlements inside the trade's window are applied on their own
    day using `te_costs.funding_cost`'s sign convention: LONG pays a
    positive rate (a cost, i.e. a NEGATIVE return contribution); SHORT is
    paid a positive rate (a positive return contribution).

    Concurrent trades are equal-weighted: each day's summed contribution
    (price returns + costs + funding, across every trade touching that
    day) is divided by `max(1, n_open_that_day)`.

    Missing bars: a day with no close carries the PREVIOUS day's close
    forward, matching the single-bar hole Gate 0 tolerates
    (`sanity.check_klines` flags a defect only above 2x the interval). The
    gap day then contributes exactly 0.0 and the day after it is measured
    against the carried close, so the two-day move is booked whole rather
    than lost. Two or more consecutive missing bars still raise `KeyError`
    loudly — that is a Gate 0 defect, not a tolerance. One artifact of
    applying the carry uniformly: a trade whose ENTRY day is the hole books
    `close[day - 1] / entry_px - 1`, a backward price move read as a forward
    return. Unreachable for the daily candidates (no bar, no trade) and
    reachable only for a 4h candidate whose entry price has no daily bar
    behind it; it is left uniform rather than special-cased, because two
    behaviors for one hole is how the tolerance drifts.

    Caller contract: `daily_closes` must extend at least 1 day before
    `start_ms` whenever a trade is already open at `start_ms` (its first
    in-window day is then an intermediate holding day, which reads
    `close[day - 1]`). The carry does NOT weaken this — history that simply
    begins at `start_day` has neither `start_day - 1` nor `start_day - 2`,
    so the denominator lookup still raises.
    """
    start_day = start_ms // DAY
    end_day = end_ms // DAY
    n_days = end_day - start_day + 1
    ret_sum = np.zeros(n_days, dtype=float)
    n_open = np.zeros(n_days, dtype=np.int64)

    closes_by_symbol = _index_closes(daily_closes)

    for t in trades:
        closes = closes_by_symbol[t.symbol]
        entry_day = t.entry_ts_ms // DAY
        exit_day = t.exit_ts_ms // DAY
        sign = 1.0 if t.side == "LONG" else -1.0

        lo = max(entry_day, start_day)
        hi = min(exit_day, end_day)
        for day in range(lo, hi + 1):
            idx = day - start_day
            n_open[idx] += 1
            if day == entry_day and day == exit_day:
                price_ret = t.exit_px / t.entry_px - 1.0
            elif day == entry_day:
                price_ret = _close(closes, day, t.symbol) / t.entry_px - 1.0
            elif day == exit_day:
                price_ret = t.exit_px / _close(closes, day - 1, t.symbol) - 1.0
            else:
                price_ret = (
                    _close(closes, day, t.symbol) / _close(closes, day - 1, t.symbol)
                    - 1.0
                )
            ret_sum[idx] += sign * price_ret

        # Hard lookup, never `.get(..., 0)`: a symbol absent from the cost
        # table would otherwise be scored as free to trade, and a
        # zero-cost variant is exactly the one that clears Gate 2. The
        # caller builds this map from the trade list, so a miss is a caller
        # bug and must say so.
        cost_leg = float(cost_bps_rt[t.symbol]) / 2.0 / 10000.0
        if start_day <= entry_day <= end_day:
            ret_sum[entry_day - start_day] -= cost_leg
        if start_day <= exit_day <= end_day:
            ret_sum[exit_day - start_day] -= cost_leg

        for settlement in funding.get(t.symbol, []):
            if t.entry_ts_ms <= settlement.ts_ms <= t.exit_ts_ms:
                day = settlement.ts_ms // DAY
                if start_day <= day <= end_day:
                    rate = float(settlement.rate)
                    contrib = -rate if t.side == "LONG" else rate
                    ret_sum[day - start_day] += contrib

    net = ret_sum / np.maximum(1, n_open)
    index = [start_ms + i * DAY for i in range(n_days)]
    return pd.Series(net, index=index, dtype=float)


def run_gate2(
    returns: pd.Series,
    label_horizon_days: int,
    num_trials_floor: int = NUM_TRIALS_FLOOR,
) -> Gate2Result:
    """CPCV path construction -> pooled PF + DSR (with a trials floor).

    `cv.split` raises ValueError when there are too few samples for the
    configured groups/embargo/horizon; that is reported as a failed gate,
    never allowed to crash the battery.
    """
    n_samples = len(returns)
    k = _load_kernels()
    rets = returns.to_numpy(dtype=float)
    cv = k["CombinatorialPurgedCV"](
        n_groups=CPCV_N_GROUPS,
        k_test_groups=CPCV_K_TEST_GROUPS,
        embargo_pct=CPCV_EMBARGO_PCT,
    )

    try:
        paths: dict[int, list[np.ndarray]] = {}
        for split in cv.split(n_samples=len(rets), label_horizon=label_horizon_days):
            paths.setdefault(split.path_id, []).append(rets[split.test_idx])
    except ValueError as exc:
        return Gate2Result(
            dsr=float("nan"),
            pooled_pf=float("nan"),
            positive_path_frac=float("nan"),
            n_paths_valid=0,
            n_samples=n_samples,
            sharpe_mean=float("nan"),
            sharpe_std=float("nan"),
            passed=False,
            reasons=[f"insufficient samples / invalid split params: {exc}"],
        )

    returns_per_path = [np.concatenate(chunks) for chunks in paths.values()]
    dist = k["cpcv_sharpe_distribution"](returns_per_path)
    # h4-precedent parity (h4_information.py:145-153): DSR needs >= 2 valid
    # path-Sharpes to have a variance to deflate against. At the pinned
    # CPCV_K_TEST_GROUPS=2 this is unreachable in practice (45 paths), but
    # the guard documents the dependence and matches h4's fallback instead
    # of silently handing deflated_sharpe_ratio a variance of 0 (== plain
    # undeflated PSR, not a deflated ratio at all).
    if int(dist["n_paths"]) < 2:
        dsr = float("nan")
    else:
        dsr = float(
            k["deflated_sharpe_ratio"](
                rets,
                num_trials=max(num_trials_floor, int(dist["n_paths"])),
                trial_sharpes_variance=float(dist["std"]) ** 2,
            )
        )

    all_path_rets = np.concatenate(returns_per_path)
    wins = float(all_path_rets[all_path_rets > 0].sum())
    losses = abs(float(all_path_rets[all_path_rets < 0].sum()))
    pooled_pf = wins / losses if losses else float("inf")

    # Denominator: ALL C(CPCV_N_GROUPS, CPCV_K_TEST_GROUPS) combination-paths
    # (45 at the pinned 10/2), not just the variance-valid subset dist keeps
    # for Sharpe. These paths overlap — each sample lands in every
    # combination that doesn't hold its group out, so at k=2 of 10 a sample
    # appears in 9 of the 45 paths — they are correlated ~20%-of-timeline
    # windows, not 45 independent trials.
    per_path_means = np.array(
        [float(p.mean()) if p.size else 0.0 for p in returns_per_path]
    )
    positive_path_frac = float(np.mean(per_path_means > 0))

    reasons: list[str] = []
    if not (dsr >= DSR_THRESHOLD):
        reasons.append(f"dsr {dsr:.4f} below threshold {DSR_THRESHOLD}")
    if not (pooled_pf > 1.0):
        reasons.append(f"pooled_pf {pooled_pf:.4f} not > 1.0")
    if not (positive_path_frac >= MIN_POSITIVE_PATH_FRAC):
        reasons.append(
            f"positive_path_frac {positive_path_frac:.4f} below "
            f"{MIN_POSITIVE_PATH_FRAC}"
        )
    passed = not reasons

    return Gate2Result(
        dsr=dsr,
        pooled_pf=pooled_pf,
        positive_path_frac=positive_path_frac,
        # Denominator: only the variance-valid paths cpcv_sharpe_distribution
        # kept (non-degenerate std) — a strict subset of the 45 total
        # combination-paths used above for positive_path_frac. Two adjacent
        # fields, two different denominators — don't average or compare them
        # directly.
        n_paths_valid=int(dist["n_paths"]),
        n_samples=n_samples,
        sharpe_mean=float(dist["mean"]),
        sharpe_std=float(dist["std"]),
        passed=passed,
        reasons=reasons,
    )
