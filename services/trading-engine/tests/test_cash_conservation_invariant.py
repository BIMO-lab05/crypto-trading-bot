"""
Standing cash-conservation invariant (Stage 0, 2026-08-07).

    cash
  + SUM(posted_margin on open)
  + SUM(unconsumed entry fee on open)
  == initial_balance + SUM(realized_pnl over ALL positions)

Both extra terms are load-bearing and the obvious two-term form is WRONG:

  * the cash ledger debits the whole entry fee at open, while
    position.realized_pnl nets only the CONSUMED portion, so an open position
    with a partial exit leaves the difference stranded;
  * realized P&L accrues onto OPEN positions via partial exits, so summing
    only closed ones under-counts. portfolios.realized_pnl has the same blind
    spot by construction - it is written only by record_position_close.

Asserted over an in-memory round trip rather than the live portfolios row,
because the live row carried a ~$177 break at the time this was written and a
test that fails on real data teaches nothing. The one-time repair is
database/migrations/one_time_repairs/2026-08-07-cash-ledger-repair.sql.
"""

from decimal import Decimal

from tests.test_posted_margin_ledger import (  # noqa: F401  - fixture reuse
    _drain_tasks,
    _order,
    stack,
)
from app.models import OrderSide


def _unconsumed_entry_fees(manager) -> Decimal:
    """Entry commission already out of cash but not yet charged to any leg's P&L.

    This term is NOT optional. The cash ledger debits the whole entry fee at
    open, while position.realized_pnl is net of only the CONSUMED portion
    (close_position/reduce_position call _consume_entry_fee per exit leg). Drop
    it and the identity holds only for positions with nothing open.
    """
    total = Decimal("0")
    for p in manager.get_open_positions():
        total += manager._entry_fees.get(
            p.id, Decimal("0")
        ) - manager._entry_fees_consumed.get(p.id, Decimal("0"))
    return total


def _identity_holds(engine, manager) -> bool:
    open_margin = sum(
        (p.posted_margin or Decimal("0")) for p in manager.get_open_positions()
    )
    # ALL positions, not just closed ones: a partial exit accrues realized P&L
    # onto a position that is still OPEN. Live proof that this matters -
    # portfolios.realized_pnl reads -0.41002416 while SUM over all positions is
    # -0.28337306, the gap being position 64's +0.1266511 partial exit.
    realized = sum(
        p.realized_pnl
        for p in list(manager.get_open_positions())
        + list(manager.get_closed_positions())
    )
    return (
        engine.balance + open_margin + _unconsumed_entry_fees(manager)
        == engine.initial_balance + realized
    )


async def test_identity_holds_after_open(stack):
    engine, manager = stack.engine, stack.manager
    engine.settings.leverage_enabled = True
    engine.settings.default_leverage = 10.0

    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.BUY, "1"), Decimal("70")
    )
    await _drain_tasks()

    assert _identity_holds(engine, manager)
    # And the fee term is genuinely load-bearing here, not decorative:
    assert _unconsumed_entry_fees(manager) == engine.calculate_commission(Decimal("70"))


async def test_identity_holds_after_full_round_trip(stack):
    engine, manager = stack.engine, stack.manager
    engine.settings.leverage_enabled = True
    engine.settings.default_leverage = 10.0

    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.BUY, "1"), Decimal("70")
    )
    await _drain_tasks()
    pos = manager.get_open_positions()[0]

    engine.settings.default_leverage = 1.0
    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.SELL, "1", position_id=pos.id, reduce_only=True),
        Decimal("77"),
    )
    await _drain_tasks()

    assert _identity_holds(engine, manager)


async def test_identity_survives_partial_exits(stack):
    engine, manager = stack.engine, stack.manager
    engine.settings.leverage_enabled = True
    engine.settings.default_leverage = 10.0

    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.BUY, "1"), Decimal("70")
    )
    await _drain_tasks()
    pos = manager.get_open_positions()[0]

    for qty, px in (("0.3", "72"), ("0.3", "74"), ("0.4", "76")):
        await engine.execute_market_order(
            _order(
                "SOLUSDT", OrderSide.SELL, qty, position_id=pos.id, reduce_only=True
            ),
            Decimal(px),
        )
        await _drain_tasks()

    assert _identity_holds(engine, manager)
