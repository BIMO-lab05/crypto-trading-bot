"""
Regression: the screen must reproduce the committed H3-secondary aggregates.

Source: .planning/evidence/killtests/H3-secondary-verdict-20260806-table-per_trade_*.csv
        (12,297 trades from the deployed ensemble's own fired signals)

Targets verified 2026-08-07 by summing the CSVs; all match the published
verdict markdown exactly. fees_modelled = (notional_in + notional_out) * 0.001
and fees_bybit_est = (notional_in + notional_out) * 0.00055, so leg notional
derives as fees_modelled / 0.001 / 2.

If a figure here ever fails, the screen's arithmetic has drifted from
independently-produced evidence. Fix the screen, not the expectations.
"""

import csv
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from costs_loader import load_costs  # noqa: E402
from screen import adapt_row, screen_trades  # noqa: E402

costs = load_costs()

TABLES = {
    "1.5x": REPO
    / ".planning/evidence/killtests/H3-secondary-verdict-20260806-table-per_trade_1.5x.csv",
    "2.5x": REPO
    / ".planning/evidence/killtests/H3-secondary-verdict-20260806-table-per_trade_2.5x.csv",
}

SLIP = {
    "BTCUSDT": Decimal("5"),
    "ETHUSDT": Decimal("5"),
    "SOLUSDT": Decimal("5"),
    "BNBUSDT": Decimal("10"),
    "ADAUSDT": Decimal("10"),
}

EXPECTED = {
    "1.5x": {
        "n": 12297,
        "gross_total": Decimal("41.870782"),
        "expectancy": Decimal("0.0034049591"),
        "fees_bybit": Decimal("94.3604"),
        "fees_modelled": Decimal("171.5643"),
        "funding": Decimal("48.6160"),
        "mean_leg_notional": Decimal("6.975"),
        "edge_bps": Decimal("4.88"),
    },
    "2.5x": {
        "n": 12297,
        "gross_total": Decimal("10.974434"),
        "expectancy": Decimal("0.0008924481"),
        "fees_bybit": Decimal("94.3433"),
        "fees_modelled": Decimal("171.5332"),
        "funding": Decimal("50.8002"),
        "mean_leg_notional": Decimal("6.9746"),
        "edge_bps": Decimal("1.28"),
    },
}


def _load(path):
    rows = []
    with open(path) as fh:
        for r in csv.DictReader(fh):
            # Per-leg notional from the recorded modelled fee.
            leg = Decimal(r["fees_modelled"]) / Decimal("0.001") / 2
            rows.append(
                {
                    "symbol": r["symbol"],
                    "side": r["side"],
                    "gross_pnl": Decimal(r["gross_pnl"]),
                    "notional_in": leg,
                    "notional_out": leg,
                    "entry_ts_ms": 0,
                    "exit_ts_ms": 0,
                }
            )
    return rows


def _screen(rows):
    return screen_trades(
        rows,
        schedule=costs.FeeSchedule.bybit_linear_perp(),
        slippage_table=SLIP,
        slippage_fallback=Decimal("10"),
    )


@pytest.mark.parametrize("variant", sorted(TABLES))
def test_table_is_present_and_intact(variant):
    assert TABLES[variant].is_file(), (
        f"{TABLES[variant]} missing — coverage would be silent"
    )


@pytest.mark.parametrize("variant", sorted(TABLES))
def test_screen_reproduces_the_published_aggregates(variant):
    rows = _load(TABLES[variant])
    exp = EXPECTED[variant]

    assert len(rows) == exp["n"]

    result = _screen(rows)

    assert abs(result.gross_total - exp["gross_total"]) < Decimal("0.001")
    assert abs(result.gross_expectancy - exp["expectancy"]) < Decimal("0.0000001")
    assert abs(result.mean_leg_notional - exp["mean_leg_notional"]) < Decimal("0.01")
    assert abs(result.gross_edge_bps - exp["edge_bps"]) < Decimal("0.05")


@pytest.mark.parametrize("variant", sorted(TABLES))
def test_the_deployed_ensemble_is_killed_by_the_screen(variant):
    """The whole point. 4.88 bps of gross edge against 21-31 bps of cost."""
    result = _screen(_load(TABLES[variant]))
    assert result.verdict == "KILL"
    assert result.ratio_taker < Decimal("0.3"), (
        "the ensemble earns well under a third of its own cost"
    )


@pytest.mark.parametrize("variant", sorted(TABLES))
def test_recorded_fee_columns_match_the_schedule(variant):
    """fees_bybit_est was recorded at 0.00055/side. If costs.py's taker rate
    ever drifts from that, this catches it."""
    exp = EXPECTED[variant]
    schedule = costs.FeeSchedule.bybit_linear_perp()
    implied_notional = exp["fees_modelled"] / Decimal("0.001")
    assert abs(implied_notional * schedule.taker - exp["fees_bybit"]) < Decimal("0.01")


@pytest.mark.parametrize("variant", sorted(TABLES))
def test_the_cli_adapter_derives_the_same_notionals(variant):
    """`screen.py --trades <H3 table>` has no notional columns to read, so it
    derives them from fees_modelled. That derivation must land on exactly the
    same aggregates as the explicit path above — otherwise the CLI and the
    library disagree about what a strategy costs."""
    from screen import MODELLED_FEE_RATE_PER_PAIR

    with open(TABLES[variant]) as fh:
        adapted = [
            adapt_row(r, modelled_fee_rate=MODELLED_FEE_RATE_PER_PAIR)
            for r in csv.DictReader(fh)
        ]
    rows = [t for t, _ in adapted]
    provenance = {p for _, p in adapted}
    assert len(provenance) == 1
    assert "fees_modelled" in provenance.pop(), "provenance must name the derivation"

    derived = _screen(rows)
    explicit = _screen(_load(TABLES[variant]))
    assert derived.mean_leg_notional == explicit.mean_leg_notional
    assert derived.gross_edge_bps == explicit.gross_edge_bps
    assert derived.verdict == explicit.verdict == "KILL"


@pytest.mark.parametrize("variant", sorted(TABLES))
def test_the_verdict_declares_funding_unavailable(variant):
    """`backtesting/data/funding/` is empty, so these verdicts are funding-
    EXCLUSIVE. The screen must say so on the lines a reader quotes, or
    `funding total 0.000000` gets read as a measured zero."""
    result = _screen(_load(TABLES[variant]))
    assert result.funding_total == Decimal("0")
    assert result.funding_complete is False
    assert set(result.funding_symbols_missing) == set(SLIP)
    rendered = result.render()
    assert "UNAVAILABLE" in rendered
    assert rendered.count("EXCLUDES funding") == 2, "both net lines carry the marker"
