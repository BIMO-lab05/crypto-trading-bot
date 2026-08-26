"""
TradeMetrics must record NET P&L, because Kelly sizes on these numbers.

add_trade recomputed (exit - entry) * position.quantity: gross of fees and
slippage, on the ORIGINAL quantity. For a scaled-out position the final leg
was computed as if the full size rode to the final price, and the partial
legs' own P&L was discarded.

It cannot be fixed by recomputing on remaining_quantity: close_position zeroes
that before add_trade runs. The net figure already exists on the object -
realized_pnl, which close_position computes net of entry and exit commissions
and accumulates across partial legs.

The headline case: a trade whose gross P&L is positive but whose realized P&L
is negative once fees are paid must count as a LOSS.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models import PositionSide, PositionStatus
from app.performance_tracker import PerformanceTracker


def _closed_position(gross_positive: bool, realized: str):
    """A CLOSED position whose gross recompute disagrees with realized_pnl."""
    from unittest.mock import MagicMock

    p = MagicMock()
    p.symbol = "ADAUSDT"
    p.strategy = "test"
    p.side = PositionSide.LONG
    p.status = PositionStatus.CLOSED
    p.entry_price = Decimal("0.6000")
    p.quantity = Decimal("16")
    p.remaining_quantity = Decimal("0")  # close_position zeroes this
    p.realized_pnl = Decimal(realized)
    p.opened_at = datetime(2026, 8, 17, tzinfo=timezone.utc)
    p.closed_at = datetime(2026, 8, 17, 4, tzinfo=timezone.utc)
    p.exit_price = Decimal("0.6010") if gross_positive else Decimal("0.5990")
    return p


def test_fee_eaten_winner_is_recorded_as_a_loss():
    """Gross +0.16%, realized negative after fees. Kelly must see a LOSS."""
    tracker = PerformanceTracker()
    position = _closed_position(gross_positive=True, realized="-0.004")

    trade = tracker.add_trade(
        position, Decimal("0.6010"), datetime(2026, 8, 17, 4, tzinfo=timezone.utc)
    )

    assert trade.pnl == Decimal("-0.004"), (
        f"recorded {trade.pnl}; gross recompute would give +0.016 and count a "
        "fee-eaten scratch as a win"
    )
    assert trade.is_winner is False


def test_scaled_out_position_uses_accumulated_realized_pnl():
    """realized_pnl spans all legs; a gross recompute on original quantity
    would price the whole size at the final leg's exit."""
    tracker = PerformanceTracker()
    position = _closed_position(gross_positive=True, realized="0.25")

    trade = tracker.add_trade(
        position, Decimal("0.6010"), datetime(2026, 8, 17, 4, tzinfo=timezone.utc)
    )

    assert trade.pnl == Decimal("0.25")
    assert trade.is_winner is True


def test_open_position_falls_back_to_remaining_quantity_gross():
    """Non-CLOSED callers have no realized figure; gross on REMAINING is the
    best available estimate - never on the original quantity."""
    from unittest.mock import MagicMock

    tracker = PerformanceTracker()
    p = MagicMock()
    p.symbol = "ADAUSDT"
    p.strategy = "test"
    p.side = PositionSide.LONG
    p.status = PositionStatus.OPEN
    p.entry_price = Decimal("0.6000")
    p.quantity = Decimal("16")
    p.remaining_quantity = Decimal("8")  # half already scaled out
    p.realized_pnl = Decimal("0")
    p.opened_at = datetime(2026, 8, 17, tzinfo=timezone.utc)
    p.closed_at = None
    p.exit_price = None

    trade = tracker.add_trade(
        p, Decimal("0.6100"), datetime(2026, 8, 17, 4, tzinfo=timezone.utc)
    )

    assert trade.pnl == pytest.approx(Decimal("0.08")), (
        f"expected gross on the remaining 8 units (0.01 * 8), got {trade.pnl}"
    )
