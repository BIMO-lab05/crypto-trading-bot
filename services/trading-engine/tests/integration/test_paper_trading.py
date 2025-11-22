"""
Integration Tests for Paper Trading Module
Tests end-to-end paper trading functionality with database persistence
"""

import pytest
import pytest_asyncio
import asyncio
from decimal import Decimal
from datetime import datetime
from uuid import uuid4

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))

from app.paper_trading import PaperTradingEngine
from app.models import OrderCreate, OrderSide, OrderType, OrderStatus
from app.position_manager import get_position_manager


@pytest.mark.integration
class TestPaperTradingIntegration:
    """Integration tests for paper trading engine"""

    @pytest_asyncio.fixture
    async def trading_engine(self):
        """Create paper trading engine instance"""
        # PaperTradingEngine gets config from settings, no constructor args needed
        engine = PaperTradingEngine()
        yield engine
        # Cleanup - reset state if needed
        # Note: No reset method exists, but balance persists across tests

    @pytest_asyncio.fixture
    async def position_manager(self):
        """Get position manager for verifying positions"""
        return get_position_manager()

    @pytest.mark.asyncio
    async def test_buy_order_creates_position(self, trading_engine, position_manager):
        """Test that BUY order creates a position"""
        initial_balance = trading_engine.get_balance()

        # Create BUY order
        order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.1"),
            type=OrderType.MARKET
        )

        # Execute BUY
        executed_order, error = await trading_engine.execute_market_order(
            order=order,
            current_price=Decimal("50000.00")
        )

        # Verify order executed successfully
        assert error is None, f"Order failed: {error}"
        assert executed_order.status == OrderStatus.FILLED
        assert executed_order.side == OrderSide.BUY
        assert executed_order.filled_quantity == Decimal("0.1")
        assert executed_order.filled_price == Decimal("50000.00")

        # Verify position created
        positions = position_manager.get_open_positions()
        btc_positions = [p for p in positions if p.symbol == "BTCUSDT"]
        assert len(btc_positions) > 0, "No BTC position found"
        position = btc_positions[0]
        assert position.quantity == Decimal("0.1")
        assert position.entry_price == Decimal("50000.00")

        # Verify balance decreased (price * quantity + commission)
        assert trading_engine.get_balance() < initial_balance

    @pytest.mark.asyncio
    async def test_sell_order_closes_position(self, trading_engine, position_manager):
        """Test that SELL order closes position"""
        # Setup: Create position with BUY
        buy_order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.1"),
            type=OrderType.MARKET
        )

        buy_executed, buy_error = await trading_engine.execute_market_order(
            order=buy_order,
            current_price=Decimal("50000.00")
        )
        assert buy_error is None

        initial_open_count = len(position_manager.get_open_positions())

        # Execute SELL to close
        sell_order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            quantity=Decimal("0.1"),
            type=OrderType.MARKET
        )

        sell_executed, sell_error = await trading_engine.execute_market_order(
            order=sell_order,
            current_price=Decimal("52000.00")
        )

        # Verify SELL executed
        assert sell_error is None, f"Sell order failed: {sell_error}"
        assert sell_executed.status == OrderStatus.FILLED

        # Verify position closed
        final_open_count = len(position_manager.get_open_positions())
        assert final_open_count < initial_open_count, "Position was not closed"

        # Verify P&L was realized (closed positions should have realized_pnl)
        closed_positions = position_manager.get_closed_positions()
        assert len(closed_positions) > 0, "No closed positions found"

        # Last closed position should be our trade
        last_closed = closed_positions[-1]
        assert last_closed.symbol == "BTCUSDT"
        assert last_closed.realized_pnl > Decimal("0"), "Expected profit from trade"

    @pytest.mark.asyncio
    async def test_commission_calculation(self, trading_engine):
        """Test commission is calculated correctly"""
        initial_balance = trading_engine.get_balance()

        # Execute trade
        order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.1"),
            type=OrderType.MARKET
        )

        executed_order, error = await trading_engine.execute_market_order(
            order=order,
            current_price=Decimal("50000.00")
        )

        assert error is None

        # Verify commission charged
        total_cost = Decimal("50000.00") * Decimal("0.1")  # 5000
        commission = trading_engine.calculate_commission(total_cost)  # Should be 5.00 (0.1%)
        expected_balance = initial_balance - total_cost - commission

        assert abs(trading_engine.get_balance() - expected_balance) < Decimal("0.01")

    @pytest.mark.asyncio
    async def test_insufficient_balance_rejection(self, trading_engine):
        """Test order rejected when insufficient balance"""
        # Try to buy more than balance allows
        order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("1.0"),  # Would cost 50,000 but may only have ~10,000
            type=OrderType.MARKET
        )

        executed_order, error = await trading_engine.execute_market_order(
            order=order,
            current_price=Decimal("50000.00")
        )

        # Verify order rejected
        assert error is not None, "Expected error for insufficient balance"
        assert "insufficient" in error.lower() or "balance" in error.lower()
        assert executed_order.status == OrderStatus.FAILED

    @pytest.mark.asyncio
    async def test_multiple_positions_tracking(self, trading_engine, position_manager):
        """Test tracking multiple positions simultaneously"""
        initial_positions = len(position_manager.get_open_positions())

        # Create BTC position
        btc_order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.01"),  # Smaller quantity to preserve balance
            type=OrderType.MARKET
        )

        btc_executed, btc_error = await trading_engine.execute_market_order(
            order=btc_order,
            current_price=Decimal("50000.00")
        )
        assert btc_error is None

        # Create ETH position
        eth_order = OrderCreate(
            symbol="ETHUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.5"),  # Smaller quantity
            type=OrderType.MARKET
        )

        eth_executed, eth_error = await trading_engine.execute_market_order(
            order=eth_order,
            current_price=Decimal("3000.00")
        )
        assert eth_error is None

        # Verify both positions exist
        open_positions = position_manager.get_open_positions()
        assert len(open_positions) >= initial_positions + 2, "Expected at least 2 new positions"

        symbols = [p.symbol for p in open_positions]
        assert "BTCUSDT" in symbols, "BTC position not found"
        assert "ETHUSDT" in symbols, "ETH position not found"

    @pytest.mark.asyncio
    async def test_position_pnl_updates(self, trading_engine, position_manager):
        """Test position P&L updates with price changes"""
        # Create position
        order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.1"),
            type=OrderType.MARKET
        )

        executed_order, error = await trading_engine.execute_market_order(
            order=order,
            current_price=Decimal("50000.00")
        )
        assert error is None

        # Get the created position
        positions = position_manager.get_open_positions()
        btc_positions = [p for p in positions if p.symbol == "BTCUSDT"]
        assert len(btc_positions) > 0
        position = btc_positions[0]

        # Update position with new price using position_manager
        position_manager.update_position_price(
            position.id,
            Decimal("52000.00")
        )

        # Get updated position and verify P&L
        updated_position = position_manager.get_position(position.id)
        expected_pnl = (Decimal("52000.00") - Decimal("50000.00")) * Decimal("0.1")
        assert abs(updated_position.unrealized_pnl - expected_pnl) < Decimal("0.01")

    @pytest.mark.asyncio
    async def test_trade_execution_tracking(self, trading_engine, position_manager):
        """Test that trades are tracked through position lifecycle"""
        initial_closed = len(position_manager.get_closed_positions())

        # Execute BUY
        buy_order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.1"),
            type=OrderType.MARKET
        )

        buy_executed, buy_error = await trading_engine.execute_market_order(
            order=buy_order,
            current_price=Decimal("50000.00")
        )
        assert buy_error is None

        # Execute SELL
        sell_order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            quantity=Decimal("0.1"),
            type=OrderType.MARKET
        )

        sell_executed, sell_error = await trading_engine.execute_market_order(
            order=sell_order,
            current_price=Decimal("52000.00")
        )
        assert sell_error is None

        # Verify trade completed (position closed)
        final_closed = len(position_manager.get_closed_positions())
        assert final_closed > initial_closed, "No new closed positions found"

    @pytest.mark.asyncio
    async def test_portfolio_value_calculation(self, trading_engine, position_manager):
        """Test total portfolio value calculation"""
        # Create position
        order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.1"),
            type=OrderType.MARKET
        )

        executed_order, error = await trading_engine.execute_market_order(
            order=order,
            current_price=Decimal("50000.00")
        )
        assert error is None

        # Record equity after purchase (balance decreased but we have position)
        equity_after_purchase = trading_engine.get_total_equity()

        # Get position and update with profitable price
        positions = position_manager.get_open_positions()
        btc_positions = [p for p in positions if p.symbol == "BTCUSDT"]
        assert len(btc_positions) > 0
        position = btc_positions[0]

        # Update to higher price (profit): $50k -> $55k = $500 profit on 0.1 BTC
        position_manager.update_position_price(
            position.id,
            Decimal("55000.00")
        )

        # Verify total equity increased (balance + unrealized P&L)
        # Should increase by approximately $500 (minus any rounding)
        current_equity = trading_engine.get_total_equity()
        expected_increase = (Decimal("55000.00") - Decimal("50000.00")) * Decimal("0.1")
        assert current_equity > equity_after_purchase, "Expected equity to increase with unrealized profit"
        assert abs(current_equity - equity_after_purchase - expected_increase) < Decimal("1.0"), "Equity increase should match price gain"


# Test configuration
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-m", "integration"])
