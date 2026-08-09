"""
The hurdle-first screen. It answers ONE question in seconds, before any
statistics run: does gross edge per trade clear twice the all-in cost?

Hurdle arithmetic (design spec section 5.1):
  taker fees + slippage  21 bps majors / 31 bps BNB-ADA  -> hurdle 0.45-0.65%
  maker fees only        4 bps                            -> hurdle 0.10%
  funding                signed, per-symbol, position-dependent - NOT a
                         constant adder, so it is applied per trade
The current ensemble delivers 0.0488%.
"""

import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backtesting"))

from costs_loader import load_costs  # noqa: E402
from screen import screen_trades  # noqa: E402

costs = load_costs()
SCHEDULE = costs.FeeSchedule.bybit_linear_perp()
SLIP = {"BTCUSDT": Decimal("5"), "SOLUSDT": Decimal("5"), "ADAUSDT": Decimal("10")}
FALLBACK = Decimal("10")


def _trade(symbol="SOLUSDT", side="LONG", gross=Decimal("0"), notional=Decimal("10")):
    return {
        "symbol": symbol,
        "side": side,
        "gross_pnl": gross,
        "notional_in": notional,
        "notional_out": notional,
        "entry_ts_ms": 0,
        "exit_ts_ms": 0,
    }


def _screen(trades, hurdle="2"):
    return screen_trades(
        trades,
        schedule=SCHEDULE,
        slippage_table=SLIP,
        slippage_fallback=FALLBACK,
        hurdle_multiple=Decimal(hurdle),
    )


def test_a_strategy_at_five_bps_of_edge_is_killed():
    """The current ensemble: 0.0488% gross against 21 bps of taker cost."""
    trades = [_trade(gross=Decimal("10") * Decimal("0.000488")) for _ in range(500)]
    r = _screen(trades)
    assert r.verdict == "KILL"
    assert Decimal("4") < r.gross_edge_bps < Decimal("6")
    assert r.cost_bps_taker == Decimal("21")
    assert r.ratio_taker < 1


def test_a_strategy_at_sixty_bps_of_edge_passes_the_taker_hurdle():
    trades = [_trade(gross=Decimal("10") * Decimal("0.0060")) for _ in range(500)]
    r = _screen(trades)
    assert r.verdict == "PASS"
    assert r.ratio_taker >= 2


def test_the_hurdle_multiple_is_configurable():
    trades = [_trade(gross=Decimal("10") * Decimal("0.0030")) for _ in range(500)]
    assert _screen(trades, hurdle="2").verdict == "KILL"  # 30 bps vs 2x21
    assert _screen(trades, hurdle="1").verdict == "PASS"  # 30 bps vs 1x21


def test_cost_is_per_symbol_not_averaged():
    """ADA carries 10 bps of slippage per side, BTC 5."""
    ada = _screen([_trade(symbol="ADAUSDT") for _ in range(10)])
    btc = _screen([_trade(symbol="BTCUSDT") for _ in range(10)])
    assert ada.cost_bps_taker == Decimal("31")
    assert btc.cost_bps_taker == Decimal("21")


def test_maker_hurdle_is_much_lower_but_still_reported_separately():
    trades = [_trade(gross=Decimal("10") * Decimal("0.0012")) for _ in range(500)]
    r = _screen(trades)
    assert r.cost_bps_maker == Decimal("4")
    assert r.ratio_maker >= 2  # 12 bps clears 2x4
    assert r.ratio_taker < 2  # but not 2x21
    assert r.verdict == "KILL", "the headline verdict is the TAKER verdict"


def test_an_empty_trade_list_raises_rather_than_passing_vacuously():
    with pytest.raises(ValueError):
        _screen([])


def test_negative_gross_is_killed_without_arithmetic_gymnastics():
    trades = [_trade(gross=Decimal("-0.05")) for _ in range(100)]
    r = _screen(trades)
    assert r.verdict == "KILL"
    assert r.gross_edge_bps < 0


# --- funding honesty -------------------------------------------------------
# `backtesting/data/funding/` is empty and nothing in this repo has ever
# stored funding rates. A screen that printed `funding total 0.000000` with no
# further comment would let a funding-EXCLUSIVE verdict be read as a
# funding-inclusive one. These pin the marker in place.


def test_missing_funding_is_reported_not_silently_zeroed():
    r = _screen([_trade(symbol="ADAUSDT") for _ in range(10)])
    assert r.funding_total == Decimal("0")
    assert r.funding_complete is False
    assert r.funding_symbols_missing == ("ADAUSDT",)
    rendered = r.render()
    assert "UNAVAILABLE" in rendered
    assert "EXCLUDES funding" in rendered


def test_supplied_funding_is_applied_and_the_marker_disappears():
    fs = costs.FundingSettlement(ts_ms=5, rate=Decimal("0.0001"))
    trades = [
        {
            "symbol": "SOLUSDT",
            "side": "LONG",
            "gross_pnl": Decimal("0"),
            "notional_in": Decimal("10"),
            "notional_out": Decimal("10"),
            "entry_ts_ms": 0,
            "exit_ts_ms": 10,
        }
    ]
    r = screen_trades(
        trades,
        schedule=SCHEDULE,
        slippage_table=SLIP,
        slippage_fallback=FALLBACK,
        funding_by_symbol={"SOLUSDT": [fs]},
        funding_source="test fixture",
    )
    assert r.funding_total == Decimal("10") * Decimal("0.0001")
    assert r.funding_complete is True
    assert r.funding_symbols_missing == ()
    assert "UNAVAILABLE" not in r.render()
    assert "EXCLUDES funding" not in r.render()
