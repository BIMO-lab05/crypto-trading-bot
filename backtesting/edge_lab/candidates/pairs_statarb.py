"""Candidate — pairs / statistical arbitrage.

Prior art for the math shape only, never the imports:
``services/trading-engine/app/strategies/pairs_trading.py`` and
``app/utils/statistical/cointegration.py`` (OLS hedge ratio, spread
z-score entries/exits). Those pull in statsmodels + scipy, which the
battery stack does not require, and pairs_trading.py is on the
account-size offender list — this module is pure numpy.

`Trade` is single-symbol, single-leg. A pair position is emitted as
TWO `Trade` rows sharing entry/exit timestamps — one LONG, one SHORT —
so Gate 2's equal-weight divisor (open positions per day) halves each
leg's contribution the way a $50/$50 book naturally would.

Bundle input is daily candles only (`_CANDIDATE_SPECS` row uses
``("daily",)``), so the manifest's 4h/8h holding windows are
approximated in whole daily bars — the finest granularity available
here. This is a deliberate simplification of the pre-registered
manifest, not a silent deviation: documented, and the manifest's
intent (short mean-reversion holds, causal calibration, three
pair-selection philosophies) is preserved. `max_holding_days=2` (not
1) for every variant, specifically so the z-score reversion exit has a
bar in which to fire before the hold-time exit forces it: at
max_holding_days=1 the only bar visited after entry is also the
timeout bar, so `exit_z` can never trigger an earlier exit and is dead
code. Two bars is still far tighter than the manifest's daily-bar
floor would otherwise allow and keeps the reversion exit live.

Calibration is causal throughout: at each recalibration point the
hedge ratio (OLS slope via `np.polyfit`), spread mean/std, and a
half-life stationarity screen are estimated from the `lookback_days`
bars strictly before the calibration bar. Pair *selection* itself
(which symbol pairs are eligible to trade at all) also only ever looks
at the first `lookback_days` common bars — the warm-up window that
precedes the first possible trade — so nothing about which pairs get
traded depends on data the strategy could not have seen yet.

No ADF/statsmodels. Two numpy-only screens replace the manifest's ADF
p-value < 0.05 requirement:

1. A half-life bound on the AR(1) coefficient of the calibration-window
   spread — a pair whose spread does not mean-revert within a bounded
   number of bars is treated as uncointegrated for that window.
2. A cross-window hedge-ratio persistence check: the calibrated beta
   must agree in sign and magnitude (within a bounded ratio) with the
   *previous* calibration window's beta before the pair is trusted to
   trade. This one matters more than it looks: a plain t-distribution
   significance test on a single window's AR(1) coefficient does NOT
   discriminate a genuinely cointegrated pair from two independent
   random walks (verified empirically — both populations produce
   similarly "significant" within-window mean-reversion statistics,
   because OLS-on-I(1) spurious regression already builds
   locally-autocorrelated, near-zero-mean residuals by construction;
   that is exactly the failure mode ADF's MacKinnon critical values
   exist to correct for). A real cointegrating relationship's hedge
   ratio is stable window-to-window; a spurious single-window fit on
   unrelated series swings in magnitude and sign. The first
   calibration window for a pair is therefore never tradeable on its
   own — it only seeds the persistence baseline.

Trade *count* on a negative control is not itself a reliable signal —
a z-score built from a trailing spread crosses its entry threshold on
any moderately volatile series regardless of whether reversion is
real, so one admitted window can still emit a run of trades. What
should differ, and does, is realized P&L: a genuinely mean-reverting
spread recovers value on each round trip; a spread that merely looked
mean-reverting in-sample is a forward martingale and averages out near
zero. See `tests/edge_lab/test_edge_lab_pairs_statarb.py`'s negative
control, which checks mean gross P&L per position rather than count.
"""

from __future__ import annotations

import logging
from itertools import combinations

import numpy as np
import pandas as pd

from edge_lab.trades import Trade, Variant

logger = logging.getLogger(__name__)

# name -> (lookback_days, recalc_days, entry_z, exit_z, max_holding_days, pair_filter)
_VARIANT_PARAMS = {
    "pairs_sector_30d": dict(
        lookback_days=30,
        recalc_days=30,
        entry_z=2.0,
        exit_z=0.5,
        max_holding_days=2,
        pair_filter="all",
    ),
    "pairs_volume_top10_60d": dict(
        lookback_days=60,
        recalc_days=60,
        entry_z=1.5,
        exit_z=0.0,
        max_holding_days=2,
        pair_filter="top_volume10",
    ),
    "pairs_orthogonal_30d": dict(
        lookback_days=30,
        recalc_days=30,
        entry_z=1.0,
        exit_z=0.0,
        max_holding_days=2,
        pair_filter="low_corr",
    ),
}

VARIANTS: list[Variant] = [
    Variant(candidate="pairs_statarb", name=name, params=tuple(params.items()))
    for name, params in _VARIANT_PARAMS.items()
]

_MIN_HALF_LIFE_BARS = 1
_MAX_HALF_LIFE_FACTOR = 4  # half-life must be <= max_holding_days * this factor
_MIN_BETA_RATIO = 0.4  # consecutive-window hedge ratio must agree within [0.4x, 2.5x]
_MAX_BETA_RATIO = 2.5


def _series_maps(daily: dict[str, pd.DataFrame]):
    closes: dict[str, dict[int, float]] = {}
    volumes: dict[str, dict[int, float]] = {}
    ts_sorted: dict[str, list[int]] = {}
    for sym, df in daily.items():
        ordered = df.sort_values("ts_ms")
        ts_list = ordered["ts_ms"].tolist()
        ts_sorted[sym] = ts_list
        closes[sym] = dict(zip(ts_list, ordered["close"].tolist()))
        volumes[sym] = dict(zip(ts_list, ordered["volume"].tolist()))
    return closes, volumes, ts_sorted


def _select_pairs(
    symbols: list[str],
    closes: dict[str, dict[int, float]],
    volumes: dict[str, dict[int, float]],
    ts_sorted: dict[str, list[int]],
    pair_filter: str,
    lookback_days: int,
) -> list[tuple[str, str]]:
    if len(symbols) < 2:
        return []

    common_ts = sorted(set.intersection(*(set(ts_sorted[s]) for s in symbols)))
    if len(common_ts) <= lookback_days:
        return []
    warmup_ts = common_ts[:lookback_days]

    universe = symbols
    if pair_filter == "top_volume10":
        avg_vol = {
            s: float(np.mean([volumes[s][t] for t in warmup_ts])) for s in symbols
        }
        ranked = sorted(symbols, key=lambda s: (-avg_vol[s], s))
        # exclude the two highest-volume symbols (BTC/ETH-analog "too liquid"
        # exclusion in the manifest), then take the next-highest 10.
        universe = ranked[2:12]
        return list(combinations(sorted(universe), 2))

    if pair_filter == "low_corr":
        rets = {}
        for s in symbols:
            px = np.array([closes[s][t] for t in warmup_ts])
            rets[s] = np.diff(px) / px[:-1]
        pairs = []
        for a, b in combinations(sorted(symbols), 2):
            ra, rb = rets[a], rets[b]
            if np.std(ra) == 0 or np.std(rb) == 0:
                continue
            corr = float(np.corrcoef(ra, rb)[0, 1])
            if abs(corr) < 0.5:
                pairs.append((a, b))
        return pairs

    # "all"
    return list(combinations(sorted(symbols), 2))


def _calibrate(
    sym_i: str,
    sym_j: str,
    closes: dict[str, dict[int, float]],
    window_ts: list[int],
    max_holding_days: int,
    prev_beta: float | None,
):
    x = np.array([closes[sym_j][t] for t in window_ts])
    y = np.array([closes[sym_i][t] for t in window_ts])
    if len(x) < 5 or np.std(x) == 0:
        return None, None

    beta, alpha = np.polyfit(x, y, 1)
    beta = float(beta)

    # Cointegration-persistence screen — see the module docstring for why a
    # single-window t-stat was rejected in favor of this. First window has
    # no prior beta and is never itself tradeable; it only seeds `prev_beta`.
    if prev_beta is None:
        return None, beta
    if beta == 0 or prev_beta == 0 or (beta > 0) != (prev_beta > 0):
        return None, beta
    ratio = abs(beta) / abs(prev_beta)
    if not (_MIN_BETA_RATIO <= ratio <= _MAX_BETA_RATIO):
        return None, beta

    spread = y - (beta * x + alpha)
    mu = float(spread.mean())
    sigma = float(spread.std(ddof=1))
    if sigma <= 0 or not np.isfinite(sigma):
        return None, beta

    s_t = spread[1:]
    s_tm1 = spread[:-1]
    if len(s_t) < 4 or np.std(s_tm1) == 0:
        return None, beta
    phi = float(np.polyfit(s_tm1, s_t, 1)[0])
    if not (0.0 < phi < 1.0):
        return None, beta
    half_life = -np.log(2) / np.log(phi)
    if not (
        _MIN_HALF_LIFE_BARS <= half_life <= max_holding_days * _MAX_HALF_LIFE_FACTOR
    ):
        return None, beta

    return {"beta": beta, "alpha": float(alpha), "mu": mu, "sigma": sigma}, beta


def _trade_pair(
    sym_i: str,
    sym_j: str,
    closes: dict[str, dict[int, float]],
    ts_sorted: dict[str, list[int]],
    lookback_days: int,
    recalc_days: int,
    entry_z: float,
    exit_z: float,
    max_holding_days: int,
) -> list[Trade]:
    common = sorted(set(ts_sorted[sym_i]) & set(ts_sorted[sym_j]))
    if len(common) <= lookback_days:
        return []

    trades: list[Trade] = []
    position = None  # dict: entry_idx, entry_ts, side_i, side_j, entry_px_i, entry_px_j
    calib = None
    prev_beta: float | None = None
    next_calib_idx = lookback_days
    n = len(common)

    for idx in range(lookback_days, n):
        if idx >= next_calib_idx:
            window_ts = common[idx - lookback_days : idx]
            calib, raw_beta = _calibrate(
                sym_i, sym_j, closes, window_ts, max_holding_days, prev_beta
            )
            if raw_beta is not None:
                prev_beta = raw_beta
            next_calib_idx = idx + recalc_days

        ts = common[idx]
        price_i = closes[sym_i][ts]
        price_j = closes[sym_j][ts]

        if calib is None:
            continue

        spread_t = price_i - (calib["beta"] * price_j + calib["alpha"])
        z = (spread_t - calib["mu"]) / calib["sigma"]

        if position is None:
            if z >= entry_z:
                # spread too high vs. fair value -> short the spread
                position = {
                    "entry_idx": idx,
                    "entry_ts": ts,
                    "side_i": "SHORT",
                    "side_j": "LONG",
                    "entry_px_i": price_i,
                    "entry_px_j": price_j,
                }
            elif z <= -entry_z:
                position = {
                    "entry_idx": idx,
                    "entry_ts": ts,
                    "side_i": "LONG",
                    "side_j": "SHORT",
                    "entry_px_i": price_i,
                    "entry_px_j": price_j,
                }
            continue

        held = idx - position["entry_idx"]
        reverted = abs(z) <= exit_z
        timed_out = held >= max_holding_days
        if reverted or timed_out:
            trades.extend(_close_position(sym_i, sym_j, position, ts, price_i, price_j))
            position = None

    # A position still open at the data end is discarded rather than
    # force-closed: force-closing at an arbitrary data boundary would make
    # the boundary itself change which trades close (shift-variant), since
    # a truncated run's "end" is exactly the truncation cut.
    return trades


def _close_position(
    sym_i, sym_j, position, exit_ts, exit_px_i, exit_px_j
) -> list[Trade]:
    entry_ts = position["entry_ts"]
    if exit_ts <= entry_ts:
        # never closes same-bar as entry; guards Trade's exit>entry invariant
        return []
    return [
        Trade(
            symbol=sym_i,
            side=position["side_i"],
            entry_ts_ms=entry_ts,
            exit_ts_ms=exit_ts,
            entry_px=position["entry_px_i"],
            exit_px=exit_px_i,
        ),
        Trade(
            symbol=sym_j,
            side=position["side_j"],
            entry_ts_ms=entry_ts,
            exit_ts_ms=exit_ts,
            entry_px=position["entry_px_j"],
            exit_px=exit_px_j,
        ),
    ]


def generate_trades(daily: dict[str, pd.DataFrame], variant: Variant) -> list[Trade]:
    params = dict(variant.params)
    lookback_days = params["lookback_days"]
    recalc_days = params["recalc_days"]
    entry_z = params["entry_z"]
    exit_z = params["exit_z"]
    max_holding_days = params["max_holding_days"]
    pair_filter = params["pair_filter"]

    symbols = sorted(daily.keys())
    closes, volumes, ts_sorted = _series_maps(daily)

    pairs = _select_pairs(
        symbols, closes, volumes, ts_sorted, pair_filter, lookback_days
    )
    if not pairs:
        return []

    trades: list[Trade] = []
    for sym_i, sym_j in pairs:
        trades.extend(
            _trade_pair(
                sym_i,
                sym_j,
                closes,
                ts_sorted,
                lookback_days,
                recalc_days,
                entry_z,
                exit_z,
                max_holding_days,
            )
        )
    return trades
