"""
costs.py funding layer.

backtesting/backtest_engine.py:220 charges funding only when
`order_type == BUY and funding_long_pays` - a SHORT never receives it, so the
short side of every backtest is missing a real cash flow. It also hardcodes an
8-bar cadence and a constant 0.0001 rate, and funding_enabled defaults False,
so NO published figure in this repo has ever paid funding.

Measured live 2026-08-07 over 200 settlements/symbol, the mean per 8h is
0.00278% (BTC), 0.00191% (ETH), -0.00086% (SOL), 0.00319% (BNB), 0.00137%
(ADA). The 0.0100% ceiling on all five is the base-rate CLIP, so the
backtester's hardcoded 0.0001 is the worst case, not the norm - and it has
the wrong sign for a SOL long.
"""

from decimal import Decimal

import pytest

from app.costs import FundingSettlement, funding_cost


H8 = 8 * 60 * 60 * 1000

# Three settlements at the measured BTC mean.
POSITIVE = [
    FundingSettlement(ts_ms=1_000 + H8 * i, rate=Decimal("0.0000278")) for i in range(3)
]
# SOL's mean is negative - shorts pay, longs are paid.
NEGATIVE = [
    FundingSettlement(ts_ms=1_000 + H8 * i, rate=Decimal("-0.0000086"))
    for i in range(3)
]


def test_long_pays_positive_funding():
    cost = funding_cost(
        Decimal("100"), "LONG", POSITIVE, entry_ts_ms=0, exit_ts_ms=1_000 + H8 * 3
    )
    assert cost == Decimal("100") * Decimal("0.0000278") * 3
    assert cost > 0


def test_short_is_paid_positive_funding():
    cost = funding_cost(
        Decimal("100"), "SHORT", POSITIVE, entry_ts_ms=0, exit_ts_ms=1_000 + H8 * 3
    )
    assert cost == -(Decimal("100") * Decimal("0.0000278") * 3)
    assert cost < 0, (
        "a short RECEIVES positive funding - the backtester never modelled this"
    )


def test_long_is_paid_negative_funding():
    """SOL's mean rate is negative; a long there is paid, not charged."""
    cost = funding_cost(
        Decimal("100"), "LONG", NEGATIVE, entry_ts_ms=0, exit_ts_ms=1_000 + H8 * 3
    )
    assert cost < 0


def test_only_settlements_inside_the_holding_window_count():
    cost = funding_cost(
        Decimal("100"), "LONG", POSITIVE, entry_ts_ms=1_000, exit_ts_ms=1_000 + H8
    )
    # Settlements at t=1000 and t=1000+H8 are both inside [entry, exit].
    assert cost == Decimal("100") * Decimal("0.0000278") * 2


def test_a_position_closed_before_any_settlement_pays_nothing():
    assert (
        funding_cost(Decimal("100"), "LONG", POSITIVE, entry_ts_ms=0, exit_ts_ms=500)
        == 0
    )


def test_empty_series_is_zero_not_an_assumed_rate():
    """Silence must never become a hardcoded 0.0001 worst case."""
    assert (
        funding_cost(Decimal("100"), "LONG", [], entry_ts_ms=0, exit_ts_ms=H8 * 10) == 0
    )


def test_unknown_side_raises():
    with pytest.raises(ValueError):
        funding_cost(Decimal("100"), "FLAT", POSITIVE, entry_ts_ms=0, exit_ts_ms=H8)


def test_48h_hold_at_the_measured_mean_is_one_to_two_bps():
    """The design spec's claim, checked. Six settlements at the BTC mean is
    1.67 bps - NOT the 6 bps a hardcoded 0.01%/8h implies."""
    six = [FundingSettlement(ts_ms=H8 * i, rate=Decimal("0.0000278")) for i in range(6)]
    cost = funding_cost(Decimal("10000"), "LONG", six, entry_ts_ms=0, exit_ts_ms=H8 * 6)
    bps = cost / Decimal("10000") * Decimal("10000")
    assert Decimal("1.5") < bps < Decimal("2.0")


def test_48h_hold_at_the_base_rate_clip_is_six_bps():
    """0.0100%/8h is the CLIP seen on all five symbols, i.e. the worst case."""
    six = [FundingSettlement(ts_ms=H8 * i, rate=Decimal("0.0001")) for i in range(6)]
    cost = funding_cost(Decimal("10000"), "LONG", six, entry_ts_ms=0, exit_ts_ms=H8 * 6)
    assert cost / Decimal("10000") * Decimal("10000") == Decimal("6")
