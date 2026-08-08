"""
Stage 0: set_position_stops must persist, not just mutate memory.

Before this task: set_position_stops (position_manager.py:778-830) mutated the
in-memory Position and returned. PositionRepository had no update-stops method
at all, and stop_loss reached the DB at exactly one line repo-wide
(repositories.py:73, inside create()). So every post-fill refinement - the
ATR/regime stops at auto_trader.py:2383, the ATR trailing update at :2786, the
breakeven stop at :2841 - was discarded on restart and replaced by the flat
default_stop_loss_pct value written at INSERT time.
"""

import asyncio
from decimal import Decimal


from app.models.enums import PositionSide
from tests.test_posted_margin_ledger import _drain_tasks, stack  # noqa: F401


async def test_set_position_stops_persists(stack):
    manager, repo = stack.manager, stack.position_repo
    pos = manager.create_position(
        symbol="SOLUSDT",
        side=PositionSide.LONG,
        entry_price=Decimal("72.68"),
        quantity=Decimal("0.3"),
    )
    await _drain_tasks()

    manager.set_position_stops(
        position_id=pos.id,
        stop_loss=Decimal("70.10"),
        take_profit=Decimal("77.20"),
    )
    await _drain_tasks()

    repo.update_stops.assert_awaited_once()
    kwargs = repo.update_stops.await_args.kwargs
    assert kwargs["stop_loss"] == Decimal("70.10")
    assert kwargs["take_profit"] == Decimal("77.20")


async def test_set_position_stops_is_still_synchronous(stack):
    """Callers do not await it - auto_trader.py:2383 and :2786 call it bare."""
    manager = stack.manager
    pos = manager.create_position(
        symbol="SOLUSDT",
        side=PositionSide.LONG,
        entry_price=Decimal("72.68"),
        quantity=Decimal("0.3"),
    )
    result = manager.set_position_stops(position_id=pos.id, stop_loss=Decimal("70"))
    assert not asyncio.iscoroutine(result)
    assert result.stop_loss == Decimal("70")
    await _drain_tasks()


async def test_partial_update_does_not_null_the_other_side(stack):
    manager, repo = stack.manager, stack.position_repo
    pos = manager.create_position(
        symbol="SOLUSDT",
        side=PositionSide.LONG,
        entry_price=Decimal("72.68"),
        quantity=Decimal("0.3"),
        stop_loss=Decimal("71"),
        take_profit=Decimal("76"),
    )
    await _drain_tasks()

    manager.set_position_stops(position_id=pos.id, stop_loss=Decimal("73"))
    await _drain_tasks()

    kwargs = repo.update_stops.await_args.kwargs
    assert kwargs["stop_loss"] == Decimal("73")
    assert kwargs.get("take_profit") is None  # omitted, not overwritten
    assert manager.positions[pos.id].take_profit == Decimal("76")
