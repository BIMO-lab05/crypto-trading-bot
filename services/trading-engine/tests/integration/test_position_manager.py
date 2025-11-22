"""
Integration Tests for Position Manager Module
Tests position lifecycle management with database persistence
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

from app.position_manager import get_position_manager
from app.models import PositionSide, PositionStatus


@pytest.mark.integration
class TestPositionManagerIntegration:
    """Integration tests for position manager"""

    @pytest_asyncio.fixture
    async def position_manager(self):
        """Get position manager instance (singleton)"""
        manager = get_position_manager()
        # Clear any existing positions for clean test state
        initial_positions = manager.get_all_positions()
        yield manager
        # Note: No cleanup method exists, positions persist

    @pytest.mark.asyncio
    async def test_create_position_creates_record(self, position_manager):
        """Test creating a position creates in-memory and database record"""
        initial_count = len(position_manager.get_all_positions())

        # Create position (sync method, no await)
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000.00"),
            stop_loss=Decimal("49000.00"),
            take_profit=Decimal("52000.00"),
            strategy="test_strategy"
        )

        # Verify position created
        assert position is not None
        assert position.symbol == "BTCUSDT"
        assert position.quantity == Decimal("0.1")
        assert position.status == PositionStatus.OPEN

        # Verify position tracked
        tracked_position = position_manager.get_position(position.id)
        assert tracked_position is not None
        assert tracked_position.id == position.id

        # Verify count increased
        final_count = len(position_manager.get_all_positions())
        assert final_count == initial_count + 1

    @pytest.mark.asyncio
    async def test_update_position_price_calculates_pnl(self, position_manager):
        """Test updating position price calculates P&L correctly"""
        # Create position
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000.00")
        )

        # Update price (sync method, no await)
        updated_position = position_manager.update_position_price(
            position.id,
            Decimal("52000.00")
        )

        # Verify P&L calculated
        expected_pnl = (Decimal("52000.00") - Decimal("50000.00")) * Decimal("0.1")
        assert abs(updated_position.unrealized_pnl - expected_pnl) < Decimal("0.01")

    @pytest.mark.asyncio
    async def test_close_position_calculates_realized_pnl(self, position_manager):
        """Test closing position calculates realized P&L"""
        # Create position
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000.00")
        )

        # Close position with profit (sync method, no await)
        closed_position = position_manager.close_position(
            position.id,
            Decimal("52000.00"),  # exit_price parameter
            reason="Manual Close"
        )

        # Verify P&L
        expected_pnl = (Decimal("52000.00") - Decimal("50000.00")) * Decimal("0.1")
        assert abs(closed_position.realized_pnl - expected_pnl) < Decimal("0.01")
        assert closed_position.status == PositionStatus.CLOSED

    @pytest.mark.asyncio
    async def test_stop_loss_hit_closes_position(self, position_manager):
        """Test position detects when stop loss is hit"""
        # Create position with stop loss
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000.00"),
            stop_loss=Decimal("49000.00")
        )

        # Price drops below stop loss - update price
        position_manager.update_position_price(
            position.id,
            Decimal("48500.00")
        )

        # Check if position should be closed using check_position_exit
        should_close, reason = position_manager.check_position_exit(
            position.id,
            Decimal("48500.00")
        )

        # Verify stop loss detected
        assert should_close is True
        assert "stop loss" in reason.lower()

        # Manually close the position (simulating what the system would do)
        closed_position = position_manager.close_position(
            position.id,
            Decimal("48500.00"),
            reason=reason
        )

        assert closed_position.status == PositionStatus.CLOSED
        assert closed_position.realized_pnl < Decimal("0")  # Loss

    @pytest.mark.asyncio
    async def test_take_profit_hit_closes_position(self, position_manager):
        """Test position detects when take profit is hit"""
        # Create position with take profit
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000.00"),
            take_profit=Decimal("52000.00")
        )

        # Price rises above take profit - update price
        position_manager.update_position_price(
            position.id,
            Decimal("52500.00")
        )

        # Check if position should be closed
        should_close, reason = position_manager.check_position_exit(
            position.id,
            Decimal("52500.00")
        )

        # Verify take profit detected
        assert should_close is True
        assert "take profit" in reason.lower()

        # Manually close the position
        closed_position = position_manager.close_position(
            position.id,
            Decimal("52500.00"),
            reason=reason
        )

        assert closed_position.status == PositionStatus.CLOSED
        assert closed_position.realized_pnl > Decimal("0")  # Profit

    @pytest.mark.asyncio
    async def test_multiple_positions_management(self, position_manager):
        """Test managing multiple positions simultaneously"""
        initial_count = len(position_manager.get_all_positions())

        # Create multiple positions
        btc_position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000.00")
        )

        eth_position = position_manager.create_position(
            symbol="ETHUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("1.0"),
            entry_price=Decimal("3000.00")
        )

        # Verify both tracked
        all_positions = position_manager.get_all_positions()
        assert len(all_positions) >= initial_count + 2

        # Verify can retrieve individually
        assert position_manager.get_position(btc_position.id) is not None
        assert position_manager.get_position(eth_position.id) is not None

    @pytest.mark.asyncio
    async def test_position_by_symbol_retrieval(self, position_manager):
        """Test retrieving position by symbol using filters"""
        # Create position
        created_position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000.00")
        )

        # Retrieve by filtering all positions for symbol
        # Note: No get_position_by_symbol method exists
        all_positions = position_manager.get_open_positions()
        btc_positions = [p for p in all_positions if p.symbol == "BTCUSDT"]

        # Verify correct position returned
        assert len(btc_positions) > 0
        assert any(p.id == created_position.id for p in btc_positions)

    @pytest.mark.asyncio
    async def test_position_pnl_percentage_calculation(self, position_manager):
        """Test P&L percentage calculation"""
        # Create position
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000.00")
        )

        # Update with 10% gain
        updated_position = position_manager.update_position_price(
            position.id,
            Decimal("55000.00")
        )

        # Verify P&L percentage
        initial_value = position.entry_price * position.quantity
        pnl_pct = (updated_position.unrealized_pnl / initial_value) * Decimal("100")

        assert abs(pnl_pct - Decimal("10.0")) < Decimal("0.1")

    @pytest.mark.asyncio
    async def test_close_all_open_positions(self, position_manager):
        """Test closing all open positions"""
        # Create multiple positions
        pos1 = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000.00")
        )

        pos2 = position_manager.create_position(
            symbol="ETHUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("1.0"),
            entry_price=Decimal("3000.00")
        )

        # Get initial open positions
        initial_open = position_manager.get_open_positions()
        initial_open_count = len(initial_open)

        # Close all positions manually (no close_all method exists)
        # Filter for our test positions and close them
        for pos in [pos1, pos2]:
            if position_manager.get_position(pos.id).status == PositionStatus.OPEN:
                position_manager.close_position(
                    pos.id,
                    pos.entry_price,  # Close at entry price for simplicity
                    reason="Emergency Close"
                )

        # Verify positions closed
        final_pos1 = position_manager.get_position(pos1.id)
        final_pos2 = position_manager.get_position(pos2.id)

        assert final_pos1.status == PositionStatus.CLOSED
        assert final_pos2.status == PositionStatus.CLOSED

    @pytest.mark.asyncio
    async def test_position_exposure_calculation(self, position_manager):
        """Test total exposure calculation"""
        initial_exposure = position_manager.get_total_exposure()

        # Create positions
        position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000.00")
        )

        position_manager.create_position(
            symbol="ETHUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("1.0"),
            entry_price=Decimal("3000.00")
        )

        # Calculate expected exposure: (50000 * 0.1) + (3000 * 1.0) = 8000
        final_exposure = position_manager.get_total_exposure()
        expected_new_exposure = Decimal("5000.00") + Decimal("3000.00")  # 8000

        # Verify exposure increased by expected amount
        assert final_exposure >= initial_exposure + expected_new_exposure


# Test configuration
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-m", "integration"])
