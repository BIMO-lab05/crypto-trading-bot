"""
Restart cash reconstruction must see partial exits and scale-ins.

sync_balance_with_positions rebuilds cash as `portfolios.cash_balance -
cost(positions opened after portfolios.updated_at)`. The only writer of
cash_balance was record_position_close, so a partial exit's credit and a
scale-in's debit never reached the row: the position carrying them was opened
BEFORE the last write, so the reconstruction classified it as already
reflected and the cash flow vanished on every restart. Every intermediate
snapshot is globally correct at write time -- engine.balance already nets
every open leg -- so the write must land wherever the ledger moves.

portfolios.realized_pnl is NOT touched here: update_balance OVERWRITES it,
and the eventual close accumulates the position's total net P&L (partial legs
included) via record_position_close.
"""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from tests.test_posted_margin_ledger import (  # noqa: F401  - fixture reuse
    _drain_tasks,
    _order,
    stack,
)
from app.models import OrderSide


def _ledger_after(portfolio_repo, cash: Decimal):
    """The persisted portfolios row, and a mock that keeps it current.

    Seeded as of NOW with the balance passed in, i.e. a row an earlier close
    wrote after the position under test was opened -- the exact state in which
    that position counts as "already reflected" and its later cash flows are
    dropped unless something writes them.
    """
    row = SimpleNamespace(cash_balance=cash, updated_at=datetime.now(timezone.utc))

    async def _write(portfolio_id, cash_balance, realized_pnl=None):
        row.cash_balance = cash_balance
        row.updated_at = datetime.now(timezone.utc)

    portfolio_repo.update_balance.side_effect = _write
    portfolio_repo.get_or_create.return_value = row
    return row


async def test_partial_exit_persists_cash_snapshot(stack):
    """The reduce branch writes the post-reduce cash figure to the ledger."""
    engine = stack.engine

    order, err = await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.BUY, "0.1"), Decimal("70")
    )
    assert err is None

    _, err = await engine.execute_market_order(
        _order(
            "SOLUSDT",
            OrderSide.SELL,
            "0.04",
            position_id=order.position_id,
            reduce_only=True,
        ),
        Decimal("71"),
    )
    assert err is None
    await _drain_tasks()

    stack.portfolio_repo.update_balance.assert_awaited_once()
    kwargs = stack.portfolio_repo.update_balance.await_args.kwargs
    assert kwargs["portfolio_id"] == "paper_trading"
    assert kwargs["cash_balance"] == engine.balance
    # realized_pnl on this writer OVERWRITES the accumulated ledger figure.
    assert kwargs.get("realized_pnl") is None
    # The position is still open: the close-path writer stays untouched.
    stack.portfolio_repo.record_position_close.assert_not_awaited()


async def test_partial_exit_cash_survives_restart(stack):
    """Restart reconstruction lands on the post-reduce balance, not pre-reduce."""
    engine = stack.engine

    order, err = await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.BUY, "0.1"), Decimal("70")
    )
    assert err is None
    row = _ledger_after(stack.portfolio_repo, engine.balance)
    pre_reduce = row.cash_balance

    _, err = await engine.execute_market_order(
        _order(
            "SOLUSDT",
            OrderSide.SELL,
            "0.04",
            position_id=order.position_id,
            reduce_only=True,
        ),
        Decimal("71"),
    )
    assert err is None
    await _drain_tasks()

    post_reduce = engine.balance
    assert post_reduce > pre_reduce  # margin + P&L returned, net of the exit fee

    engine.balance = Decimal("0")  # restart: in-memory ledger is gone
    await engine.sync_balance_with_positions()

    assert engine.balance == post_reduce


async def test_scale_in_persists_cash_snapshot(stack):
    """The scale-in branch writes the post-debit cash figure to the ledger."""
    engine = stack.engine

    order, err = await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.BUY, "0.1"), Decimal("70")
    )
    assert err is None

    _, err = await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.BUY, "0.05", position_id=order.position_id),
        Decimal("72"),
    )
    assert err is None
    await _drain_tasks()

    stack.portfolio_repo.update_balance.assert_awaited_once()
    kwargs = stack.portfolio_repo.update_balance.await_args.kwargs
    assert kwargs["portfolio_id"] == "paper_trading"
    assert kwargs["cash_balance"] == engine.balance
    assert kwargs.get("realized_pnl") is None


async def test_scale_in_cash_survives_restart(stack):
    """A scale-in's margin + commission debit is not refunded by a restart."""
    engine = stack.engine

    order, err = await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.BUY, "0.1"), Decimal("70")
    )
    assert err is None
    row = _ledger_after(stack.portfolio_repo, engine.balance)
    pre_scale_in = row.cash_balance

    _, err = await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.BUY, "0.05", position_id=order.position_id),
        Decimal("72"),
    )
    assert err is None
    await _drain_tasks()

    post_scale_in = engine.balance
    assert post_scale_in < pre_scale_in

    engine.balance = Decimal("0")  # restart: in-memory ledger is gone
    await engine.sync_balance_with_positions()

    assert engine.balance == post_scale_in
