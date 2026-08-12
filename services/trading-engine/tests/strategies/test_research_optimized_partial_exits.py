"""The hybrid path's partial-exit ladder must keep its ATR geometry at ADA scale.

Defect (2026-08-12, PRICE-01 site): ``calculate_partial_exits`` built every
``PartialExitLevel`` with ``price=round(price, 2)``. At ADA scale — entry
~$0.6042, ATR ~$0.0031 — the 2.5x / 4.0x / 6.0x ATR rungs span 1.1 cents in
total, so TP2 and TP3 round onto the SAME trigger and TP1 moves by a quarter of
its intended distance. A single ladder rung serving two levels means the 40%
runner leg force-closes at 4x ATR instead of 6x (``Position.check_partial_exit``
walks TP1 -> TP2 -> TP3 and TP3 exits the remainder).

The level is a trigger compared against market price and closes at market, so
no exchange tick precision belongs at this layer. ``auto_trader`` carries the
value on as ``Decimal(str(price))`` into ``take_profit_1/2/3``, which are
in-memory ``Decimal`` fields with no fixed scale, so nothing downstream
re-truncates it.
"""

from decimal import Decimal

import pytest

from app.models.enums import PositionSide
from app.models.position import Position
from app.strategies.research_optimized_strategy import ResearchOptimizedStrategy

# ADA/USDT at the scale the live hybrid path actually sees.
ADA_ENTRY = 0.6042
ADA_ATR = 0.0031

# BTC/USDT — same geometry, four orders of magnitude up.
BTC_ENTRY = 68450.5
BTC_ATR = 812.35


@pytest.fixture
def strategy():
    return ResearchOptimizedStrategy()


@pytest.mark.parametrize("is_long", [True, False], ids=["long", "short"])
def test_ada_ladder_rungs_are_distinct_prices(strategy, is_long):
    """Three exit percentages need three triggers; 2dp gave TP2 and TP3 one."""
    levels = strategy.calculate_partial_exits(ADA_ENTRY, ADA_ATR, is_long)

    assert len(levels) == 3
    prices = [lv.price for lv in levels]
    assert len(set(prices)) == 3, f"collapsed ladder: {prices}"


@pytest.mark.parametrize(
    "entry,atr",
    [(ADA_ENTRY, ADA_ATR), (BTC_ENTRY, BTC_ATR)],
    ids=["ada", "btc"],
)
@pytest.mark.parametrize("is_long", [True, False], ids=["long", "short"])
def test_ladder_preserves_atr_geometry_at_any_scale(strategy, entry, atr, is_long):
    """Each rung must sit exactly its own ``atr_multiple`` from entry."""
    levels = strategy.calculate_partial_exits(entry, atr, is_long)

    for level in levels:
        distance = (level.price - entry) if is_long else (entry - level.price)
        assert distance / atr == pytest.approx(level.atr_multiple, rel=1e-9), (
            f"{level.label} at {level.price} is {distance / atr:.3f}x ATR, "
            f"not {level.atr_multiple}x"
        )
        assert distance > 0, f"{level.label} sits on the wrong side of entry"


@pytest.mark.parametrize("is_long", [True, False], ids=["long", "short"])
def test_ada_ladder_is_monotone_in_the_trade_direction(strategy, is_long):
    prices = [
        lv.price for lv in strategy.calculate_partial_exits(ADA_ENTRY, ADA_ATR, is_long)
    ]
    assert prices == (sorted(prices) if is_long else sorted(prices, reverse=True))


@pytest.mark.parametrize(
    "is_long,side",
    [(True, PositionSide.LONG), (False, PositionSide.SHORT)],
    ids=["long", "short"],
)
def test_runner_leg_is_not_force_closed_at_the_tp2_trigger(strategy, is_long, side):
    """The money harm: a collapsed TP3 exits the remainder at TP2's price.

    The ladder is handed to the position exactly as ``auto_trader`` hands it —
    ``Decimal(str(level.price))`` into ``take_profit_1/2/3``.
    """
    levels = {
        lv.label: Decimal(str(lv.price))
        for lv in strategy.calculate_partial_exits(ADA_ENTRY, ADA_ATR, is_long)
    }

    position = Position(
        symbol="ADAUSDT",
        side=side,
        entry_price=Decimal(str(ADA_ENTRY)),
        quantity=Decimal("16"),
        take_profit_1=levels["TP1"],
        take_profit_2=levels["TP2"],
        take_profit_3=levels["TP3"],
        tp1_hit=True,
        tp2_hit=True,
    )

    assert position.check_partial_exit(levels["TP2"]) is None, (
        "TP3 fired at the TP2 trigger — the 40% runner leg closed at 4x ATR"
    )

    exit_info = position.check_partial_exit(levels["TP3"])
    assert exit_info is not None and exit_info["level"] == "TP3"
