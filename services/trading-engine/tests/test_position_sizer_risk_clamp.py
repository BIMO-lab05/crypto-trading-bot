"""
The loss-at-stop clamp must actually fire.

Two defects made it vacuous: auto_trader passes stop_loss_pct as a FRACTION
while the docstring declared percent, and get_position_sizer injected the
per-trade NOTIONAL cap (0.10 -> 10.0) into a parameter documented as the
loss-at-stop budget (2.0). max_position_by_risk = 10.0 / 0.02 = 500 against
a position_pct that never exceeds ~18.

Reference semantics: app/risk/kelly_position_sizing.py:366 computes
max_risk_pct / stop_loss_pct * 100. For a 2% budget and a 5% stop both
sizers must produce 40.0.

Balances here are arbitrary and deliberately not account-size literals - the
assertions are percentage math and balance-independent.
"""

from decimal import Decimal

import pytest

from app.position_sizing import (
    PositionSizer,
    SizingMethod,
    get_position_sizer,
    reset_position_sizer,
)


def _sizer(budget: float = 1.0) -> PositionSizer:
    return PositionSizer(
        min_position_pct=1.0,
        max_position_pct=50.0,
        default_position_pct=50.0,
        max_risk_per_trade_pct=budget,
    )


def _size(sizer: PositionSizer, stop):
    return sizer.calculate_position_size(
        method=SizingMethod.FIXED,
        current_balance=Decimal("200"),
        current_price=Decimal("50000"),
        signal_confidence=0.75,
        stop_loss_pct=stop,
    )


def test_clamp_fires_when_loss_at_stop_exceeds_budget():
    """1% budget, 5% stop -> at most a 20% position."""
    result = _size(_sizer(budget=1.0), 0.05)

    assert result.position_size_pct == pytest.approx(20.0), (
        f"clamp did not bind: got {result.position_size_pct}%, expected 20%"
    )
    assert result.position_size_pct * 0.05 <= 1.0 + 1e-9, (
        "loss at stop exceeds the budget after clamping"
    )
    assert "Risk-limited" in result.reasoning


def test_clamp_inert_at_the_exact_boundary():
    """The comparison is strict >; at equality nothing is clamped."""
    result = _size(_sizer(budget=1.0), 0.02)  # 1.0 / 0.02 == 50.0 == position

    assert result.position_size_pct == pytest.approx(50.0)
    assert "Risk-limited" not in result.reasoning


def test_percent_input_normalizes_to_the_same_answer():
    """0.05 and 5.0 must mean the same stop; the ranges are disjoint."""
    as_fraction = _size(_sizer(budget=1.0), 0.05)
    as_percent = _size(_sizer(budget=1.0), 5.0)

    assert as_percent.position_size_pct == pytest.approx(as_fraction.position_size_pct)


def test_reasoning_states_the_real_budget_not_a_hardcoded_two_percent():
    # 0.10 stays a FRACTION under the >= 0.5 normalization rule, so the cap is
    # 3.0 / 0.10 = 30 < the 50% FIXED position and the clamp binds. Do NOT use
    # 0.5 here: it lands exactly on the percent-normalization threshold, giving
    # a 600% cap that never binds, and the "fix" that makes it bind is the
    # factor-of-100 error the DO NOT DO THIS box above exists to prevent.
    result = _size(_sizer(budget=3.0), 0.10)

    assert "(2% max)" not in result.reasoning, (
        "the log hardcoded 2% while the injected budget was something else"
    )
    assert "3.0% max" in result.reasoning


def test_factory_injects_the_loss_at_stop_budget_not_the_notional_cap():
    """max_risk_per_trade is the NOTIONAL cap (config.py:349-359) - feeding it
    here as a loss-at-stop budget is what made the clamp structurally dead."""
    reset_position_sizer()
    try:
        sizer = get_position_sizer()
        assert sizer.max_risk_per_trade_pct == pytest.approx(2.0), (
            f"factory injected {sizer.max_risk_per_trade_pct} as the "
            "loss-at-stop budget; the notional cap belongs in max_position_pct"
        )
        assert sizer.max_position_pct == pytest.approx(10.0)
    finally:
        reset_position_sizer()
