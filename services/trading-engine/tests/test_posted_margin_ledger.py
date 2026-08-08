"""
Stage 0: posted margin is a per-position dollar amount, not a global ratio.

Defect being pinned: paper_trading.py:253 read settings.default_leverage at
CLOSE time and paper_trading.py:325 credited entry_price*close_qty/that value.
A position opened while DEFAULT_LEVERAGE=10 and closed after the compose flip
to 1.0 credited back 10x the margin it posted. Reconstructed against the live
DB, this fabricated ~$177 of cash on a $100 account.
"""

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.paper_trading as paper_trading_module
from app.models import OrderCreate, OrderSide, OrderType
from app.paper_trading import PaperTradingEngine
from app.position_manager import PositionManager


async def _drain_tasks():
    for _ in range(10):
        await asyncio.sleep(0)


class _IdentitySlippage:
    def fill_price(self, symbol, side, price):
        return price

    def describe(self):
        return "identity (test)"


def _mock_position_repo():
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.update_price = AsyncMock()
    repo.close = AsyncMock()
    repo.record_reduction = AsyncMock()
    repo.record_scale_in = AsyncMock()
    repo.get_open_positions = AsyncMock(return_value=[])
    return repo


def _mock_portfolio_repo():
    repo = MagicMock()
    repo.record_position_close = AsyncMock()
    repo.update_balance = AsyncMock()
    repo.get_or_create = AsyncMock()
    return repo


def _mock_risk_manager():
    rm = MagicMock()
    rm.calculate_stop_loss = MagicMock(return_value=Decimal("0.00000001"))
    rm.calculate_take_profit = MagicMock(return_value=Decimal("99999999"))
    rm.update_daily_pnl = MagicMock()
    return rm


@pytest.fixture
def stack():
    position_repo = _mock_position_repo()
    portfolio_repo = _mock_portfolio_repo()
    trade_repo = MagicMock()
    trade_repo.log_trade = AsyncMock()
    risk_manager = _mock_risk_manager()

    with (
        patch("app.position_manager.get_risk_manager", return_value=risk_manager),
        patch(
            "app.position_manager.get_position_repository", return_value=position_repo
        ),
        patch(
            "app.position_manager.get_portfolio_repository", return_value=portfolio_repo
        ),
    ):
        manager = PositionManager()

    with (
        patch("app.paper_trading.get_position_manager", return_value=manager),
        patch("app.paper_trading.get_risk_manager", return_value=risk_manager),
        patch("app.paper_trading.get_trade_repository", return_value=trade_repo),
        patch(
            "app.paper_trading.get_portfolio_repository", return_value=portfolio_repo
        ),
    ):
        engine = PaperTradingEngine()
    engine.slippage = _IdentitySlippage()

    saved = paper_trading_module._paper_engine
    paper_trading_module._paper_engine = engine
    # `engine.settings` IS the process-wide get_settings() singleton, so every
    # test below that assigns default_leverage / leverage_enabled mutates it for
    # the rest of the run. Capture and restore, or a whole-suite run inherits
    # 10x leverage from whichever test happened to go last.
    saved_leverage = engine.settings.default_leverage
    saved_leverage_enabled = engine.settings.leverage_enabled
    yield SimpleNamespace(
        engine=engine,
        manager=manager,
        position_repo=position_repo,
        portfolio_repo=portfolio_repo,
    )
    engine.settings.default_leverage = saved_leverage
    engine.settings.leverage_enabled = saved_leverage_enabled
    paper_trading_module._paper_engine = saved


def _order(symbol, side, qty, position_id=None, reduce_only=False):
    return OrderCreate(
        symbol=symbol,
        side=side,
        type=OrderType.MARKET,
        quantity=Decimal(str(qty)),
        strategy="test",
        position_id=position_id,
        reduce_only=reduce_only,
    )


async def test_open_stamps_posted_margin_equal_to_debited_margin(stack):
    """What leaves the cash ledger at open is exactly what the position records."""
    engine, manager = stack.engine, stack.manager
    # leverage_enabled MUST be set: config.py:614 defaults it to False, and the
    # Stage 0 fix gates paper_trading's leverage read on it (auto_trader always
    # did; paper_trading did not, which was an independent latent bug).
    engine.settings.leverage_enabled = True
    engine.settings.default_leverage = 10.0
    before = engine.balance

    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.BUY, "1"), Decimal("70")
    )
    await _drain_tasks()

    pos = manager.get_open_positions()[0]
    commission = engine.calculate_commission(Decimal("70"))
    debited = before - engine.balance

    assert pos.posted_margin == Decimal("7")  # 70 notional / 10x
    assert pos.leverage == Decimal("10")
    assert debited == pos.posted_margin + commission


async def test_close_credits_what_was_posted_not_the_current_global(stack):
    """THE REGRESSION. Open at 10x, flip the global to 1x, close: cash must
    return 7, not 70."""
    engine, manager = stack.engine, stack.manager
    engine.settings.leverage_enabled = True
    engine.settings.default_leverage = 10.0
    start = engine.balance

    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.BUY, "1"), Decimal("70")
    )
    await _drain_tasks()
    pos = manager.get_open_positions()[0]

    engine.settings.default_leverage = 1.0  # the 2026-08-04 compose flip

    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.SELL, "1", position_id=pos.id, reduce_only=True),
        Decimal("70"),
    )
    await _drain_tasks()

    fees = engine.calculate_commission(Decimal("70")) * 2
    assert engine.balance == start - fees
    assert manager.positions[pos.id].posted_margin == Decimal("0")


async def test_partial_close_returns_proportional_margin(stack):
    engine, manager = stack.engine, stack.manager
    engine.settings.leverage_enabled = True
    engine.settings.default_leverage = 10.0

    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.BUY, "1"), Decimal("70")
    )
    await _drain_tasks()
    pos = manager.get_open_positions()[0]
    assert pos.posted_margin == Decimal("7")

    mid = engine.balance
    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.SELL, "0.4", position_id=pos.id, reduce_only=True),
        Decimal("70"),
    )
    await _drain_tasks()

    exit_fee = engine.calculate_commission(Decimal("28"))
    assert manager.positions[pos.id].posted_margin == Decimal("4.2")
    assert engine.balance == mid + Decimal("2.8") - exit_fee


async def test_scale_in_accumulates_margin_across_different_leverage(stack):
    """A stored leverage RATIO cannot express this; a dollar ledger can.
    scale_in also rewrites entry_price to a weighted average."""
    engine, manager = stack.engine, stack.manager
    engine.settings.leverage_enabled = True
    engine.settings.default_leverage = 10.0

    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.BUY, "1"), Decimal("70")
    )
    await _drain_tasks()
    pos = manager.get_open_positions()[0]

    engine.settings.default_leverage = 2.0
    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.BUY, "1", position_id=pos.id), Decimal("80")
    )
    await _drain_tasks()

    # 70/10 + 80/2 = 7 + 40
    assert manager.positions[pos.id].posted_margin == Decimal("47")


async def test_margin_conservation_over_a_full_round_trip(stack):
    """Cash returns to its start less fees, whatever leverage did in between."""
    engine, manager = stack.engine, stack.manager
    engine.settings.leverage_enabled = True
    engine.settings.default_leverage = 10.0
    start = engine.balance

    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.BUY, "1"), Decimal("70")
    )
    await _drain_tasks()
    pos = manager.get_open_positions()[0]

    for qty in ("0.3", "0.3"):
        engine.settings.default_leverage = 1.0
        await engine.execute_market_order(
            _order(
                "SOLUSDT", OrderSide.SELL, qty, position_id=pos.id, reduce_only=True
            ),
            Decimal("70"),
        )
        await _drain_tasks()

    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.SELL, "0.4", position_id=pos.id, reduce_only=True),
        Decimal("70"),
    )
    await _drain_tasks()

    total_fees = engine.calculate_commission(Decimal("70")) * 2
    assert engine.balance == start - total_fees
    assert manager.positions[pos.id].posted_margin == Decimal("0")


def test_consume_posted_margin_hands_the_exact_residual(stack):
    """Mirrors _consume_entry_fee: a whole-remainder leg gets the residual,
    not a computed share, so Decimal division cannot leak a fraction of a cent."""
    from app.models.enums import PositionSide

    manager = stack.manager
    pos = manager.create_position(
        symbol="ADAUSDT",
        side=PositionSide.LONG,
        entry_price=Decimal("0.2023"),
        quantity=Decimal("3"),
        posted_margin=Decimal("1"),
        leverage=Decimal("1"),
    )
    first = manager.consume_posted_margin(pos.id, Decimal("1"))
    pos.remaining_quantity = Decimal("2")
    second = manager.consume_posted_margin(pos.id, Decimal("2"))

    assert first + second == Decimal("1")
    assert pos.posted_margin == Decimal("0")
