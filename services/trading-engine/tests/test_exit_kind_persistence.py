"""
Stage 0: the structured close reason must reach positions.exit_kind.

Two traps this pins:
  * The field MUST live on OrderBase, not OrderCreate. paper_trading.py:255
    does Order(**order.model_dump(), ...) and Order inherits OrderBase;
    pydantic v2 extra='ignore' would silently drop an OrderCreate-only field
    with no ValidationError.
  * In PAPER mode the routed prose reason never reaches the DB at all - the
    persisted exit_reason is synthesized at paper_trading.py:343-345. The enum
    is a second, independent channel; exit_reason is left untouched.
"""

from decimal import Decimal


from app.models import OrderCreate, OrderSide, OrderType
from app.models.enums import ExitKind
from tests.test_posted_margin_ledger import (  # noqa: F401
    _drain_tasks,
    _order,
    stack,
)


def test_exit_kind_is_declared_on_orderbase_not_ordercreate():
    """If it lands on OrderCreate only, model_dump() drops it at the Order()
    construction and the whole feature is a silent no-op."""
    from app.models.order import Order, OrderBase

    assert "exit_kind" in OrderBase.model_fields
    assert "exit_kind" in Order.model_fields

    order = OrderCreate(
        symbol="SOLUSDT",
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        quantity=Decimal("1"),
        exit_kind=ExitKind.HARD_STOP,
    )
    assert order.exit_kind == ExitKind.HARD_STOP
    assert order.model_dump()["exit_kind"] == ExitKind.HARD_STOP

    # The actual construction paper_trading.py performs: Order(**model_dump()).
    # This is the line that would silently drop the field if it lived on
    # OrderCreate instead of OrderBase.
    assert Order(**order.model_dump()).exit_kind == ExitKind.HARD_STOP


def test_unknown_field_on_ordercreate_is_still_silently_dropped():
    """Documents WHY the field must be on OrderBase. If this ever starts
    raising, pydantic's extra policy changed and the reasoning should be
    revisited."""
    order = OrderCreate(
        symbol="SOLUSDT",
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        quantity=Decimal("1"),
        definitely_not_a_field=123,
    )
    assert "definitely_not_a_field" not in order.model_dump()


async def test_full_close_persists_exit_kind(stack):
    engine, manager, repo = stack.engine, stack.manager, stack.position_repo

    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.BUY, "1"), Decimal("70")
    )
    await _drain_tasks()
    pos = manager.get_open_positions()[0]

    close = OrderCreate(
        symbol="SOLUSDT",
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        quantity=Decimal("1"),
        strategy="stop_loss_limit",
        position_id=pos.id,
        reduce_only=True,
        exit_kind=ExitKind.HARD_STOP,
    )
    await engine.execute_market_order(close, Decimal("68.6"))
    await _drain_tasks()

    repo.close.assert_awaited_once()
    assert repo.close.await_args.kwargs["exit_kind"] == "HARD_STOP"


async def test_prose_exit_reason_is_left_untouched(stack):
    """exit_reason is API-visible via TradeHistoryResponse; the enum is
    additive, not a replacement."""
    engine, manager, repo = stack.engine, stack.manager, stack.position_repo

    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.BUY, "1"), Decimal("70")
    )
    await _drain_tasks()
    pos = manager.get_open_positions()[0]

    close = OrderCreate(
        symbol="SOLUSDT",
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        quantity=Decimal("1"),
        strategy="auto_close",
        position_id=pos.id,
        reduce_only=True,
        exit_kind=ExitKind.MAX_HOLD,
    )
    await engine.execute_market_order(close, Decimal("71"))
    await _drain_tasks()

    kwargs = repo.close.await_args.kwargs
    assert kwargs["exit_kind"] == "MAX_HOLD"
    assert kwargs["exit_reason"] == "Market sell order (LONG close) [auto_close]"


async def test_close_without_exit_kind_persists_none(stack):
    """The live path and every legacy caller must keep working."""
    engine, manager, repo = stack.engine, stack.manager, stack.position_repo

    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.BUY, "1"), Decimal("70")
    )
    await _drain_tasks()
    pos = manager.get_open_positions()[0]

    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.SELL, "1", position_id=pos.id, reduce_only=True),
        Decimal("70"),
    )
    await _drain_tasks()

    assert repo.close.await_args.kwargs["exit_kind"] is None
