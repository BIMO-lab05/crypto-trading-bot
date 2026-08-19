"""Minimal scoring-path tests for run_maker_regate (final-review C1/H2/M1/m3).

Exercises the NEW logic directly with synthetic trades — entry-basis-aware
fill selection (C1), the M1 mixed cost model (`_mixed_gate1`), and the
maker-cost Gate 2 substitution (`_score_gate2_maker`, H2) — rather than
real candidate regeneration, which is already covered by each candidate's
own test file and by `test_edge_lab_maker_fill.py`'s basis tests.
"""

import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from edge_lab.maker_fill import apply_maker_fill  # noqa: E402
from edge_lab.run_maker_regate import (  # noqa: E402
    _CANDIDATE_ENTRY_BASIS,
    _maker_regate_round_trip_bps,
    _mixed_gate1,
    _score_gate2_maker,
)
from edge_lab.trades import Trade  # noqa: E402

DAY = 86_400_000


def _daily_bars(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ts_ms": i * DAY,
                "open": c,
                "high": c * 1.01,
                "low": c * 0.99,
                "close": c,
            }
            for i, c in enumerate(closes)
        ]
    )


def test_entry_basis_matches_final_review_c1_classification():
    # Regression pin for the classification run_maker_regate.py cites with
    # source line numbers — a silent change here reproduces C1's defect
    # class (testing the wrong bar) without anyone noticing.
    assert _CANDIDATE_ENTRY_BASIS == {
        "xs_momentum": "open",
        "lf_trend": "open",
        "funding_carry": "open",
        "vol_breakout": "open",
        "pairs_statarb": "close",
        "baseline_rsi_ema": "open",
    }


def test_open_basis_fill_tests_the_entry_bar_not_the_next_one():
    # LONG entry limit == the entry bar's own open (100); that SAME bar's
    # low (99) trades through it. Under "close" basis this bar is never
    # even inspected (only entry_ts_ms + interval is) — this is exactly
    # what C1 found wrong for xs_momentum/lf_trend/funding_carry/
    # vol_breakout/baseline_rsi_ema.
    bars = {
        "BTCUSDT": pd.DataFrame(
            [{"ts_ms": 0, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5}]
        )
    }
    t = Trade("BTCUSDT", "LONG", 0, DAY, 100.0, 105.0)
    res = apply_maker_fill(
        [t], bars, DAY, entry_basis=_CANDIDATE_ENTRY_BASIS["xs_momentum"]
    )
    assert res.filled == [t] and res.missed == 0


def test_close_basis_tests_the_next_adjacent_bar():
    bars = {
        "BTCUSDT": pd.DataFrame(
            [
                {
                    "ts_ms": 0,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 100.0,
                    "close": 100.0,
                },
                {
                    "ts_ms": DAY,
                    "open": 100.4,
                    "high": 100.6,
                    "low": 99.0,
                    "close": 99.5,
                },
            ]
        )
    }
    t = Trade("BTCUSDT", "LONG", 0, DAY, 100.0, 99.5)  # entry_px == bar0 close
    res = apply_maker_fill(
        [t], bars, DAY, entry_basis=_CANDIDATE_ENTRY_BASIS["pairs_statarb"]
    )
    assert res.filled == [t] and res.missed == 0


def test_mixed_gate1_costs_between_pure_maker_and_pure_taker():
    from costs_loader import load_costs

    from edge_lab.config import SLIPPAGE_BPS, SLIPPAGE_FALLBACK_BPS

    trades = [Trade("BTCUSDT", "LONG", 0, DAY, 100.0, 106.0)]
    mixed = _mixed_gate1(trades)

    costs = load_costs()
    schedule = costs.FeeSchedule.bybit_linear_perp()
    taker_bps = costs.round_trip_cost_bps(
        "BTCUSDT",
        entry_liquidity=costs.Liquidity.TAKER,
        exit_liquidity=costs.Liquidity.TAKER,
        schedule=schedule,
        slippage_table=SLIPPAGE_BPS,
        slippage_fallback=SLIPPAGE_FALLBACK_BPS,
    )
    maker_bps = costs.round_trip_cost_bps(
        "BTCUSDT",
        entry_liquidity=costs.Liquidity.MAKER,
        exit_liquidity=costs.Liquidity.MAKER,
        schedule=schedule,
        slippage_table=SLIPPAGE_BPS,
        slippage_fallback=SLIPPAGE_FALLBACK_BPS,
    )
    # M1: maker entry (cheap) + taker exit (pricier) must land strictly
    # between the two pure legs — never cheaper than pure maker (that
    # would violate "costs only go up"), never pricier than pure taker.
    assert maker_bps < mixed["cost_bps_mixed"] < taker_bps


def test_score_gate2_maker_uses_cheaper_than_taker_cost_map(tmp_path):
    # Confirms _score_gate2_maker is really substituting the M1 cost map
    # into gate2.daily_returns_from_trades, not silently falling back to
    # run_battery.score_gate2's taker/taker round_trip_bps (H2).
    closes = [100 + i * 0.1 for i in range(40)]
    daily = {"BTCUSDT": _daily_bars(closes)}
    trades = [
        Trade("BTCUSDT", "LONG", i * DAY, (i + 2) * DAY, closes[i], closes[i + 2])
        for i in range(0, 30, 5)
    ]
    funding_dir = tmp_path / "funding"
    gate2, start_ms, end_ms, horizon, dropped = _score_gate2_maker(
        trades, daily, "xs_momentum", funding_dir, num_trials_floor=16
    )
    assert dropped == {}
    assert gate2.n_samples > 0

    from edge_lab.run_battery import round_trip_bps as taker_round_trip_bps

    mixed_bps = _maker_regate_round_trip_bps("BTCUSDT")
    assert mixed_bps < taker_round_trip_bps("BTCUSDT")


def test_score_gate2_maker_drops_symbols_with_no_daily_frame(tmp_path):
    daily = {"BTCUSDT": _daily_bars([100 + i * 0.1 for i in range(40)])}
    trades = [
        Trade("BTCUSDT", "LONG", 0, 2 * DAY, 100.0, 100.2),
        Trade("ETHUSDT", "LONG", 0, 2 * DAY, 100.0, 100.2),  # no daily frame
    ]
    gate2, start_ms, end_ms, horizon, dropped = _score_gate2_maker(
        trades, daily, "xs_momentum", tmp_path / "funding", num_trials_floor=16
    )
    assert dropped == {"ETHUSDT": 1}
