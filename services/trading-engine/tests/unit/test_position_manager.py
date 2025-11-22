"""
Unit Tests for Position Manager
Tests position lifecycle and P&L tracking without database
"""

import pytest
from decimal import Decimal
from datetime import datetime
from uuid import uuid4, UUID
from unittest.mock import Mock, AsyncMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "shared"))

from app.position_manager import PositionManager
from app.models import Position, PositionStatus, PositionSide


class TestPositionManager:
    """Test suite for PositionManager"""

    @pytest.fixture
    def mock_risk_manager(self):
        """Mock risk manager"""
        manager = Mock()
        manager.calculate_stop_loss.return_value = Decimal("49000.00")
        manager.calculate_take_profit.return_value = Decimal("52000.00")
        manager.should_close_position.return_value = (False, None)
        manager.update_daily_pnl.return_value = None
        return manager

    @pytest.fixture
    def mock_position_repo(self):
        """Mock position repository"""
        repo = Mock()
        repo.create = AsyncMock()
        repo.update_price = AsyncMock()
        repo.close = AsyncMock()
        return repo

    @pytest.fixture
    def position_manager(self, mock_risk_manager, mock_position_repo):
        """Create PositionManager with mocked dependencies"""
        with patch('app.position_manager.get_risk_manager', return_value=mock_risk_manager), \
             patch('app.position_manager.get_position_repository', return_value=mock_position_repo):

            manager = PositionManager()
            return manager

    def test_initialization(self, position_manager):
        """Test position manager initializes correctly"""
        assert isinstance(position_manager.positions, dict)
        assert len(position_manager.positions) == 0

    def test_create_position_with_stop_loss_and_take_profit(self, position_manager):
        """Test creating position with explicit SL/TP"""
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            stop_loss=Decimal("48000.00"),
            take_profit=Decimal("53000.00"),
            strategy="test"
        )

        assert position.symbol == "BTCUSDT"
        assert position.side == PositionSide.LONG
        assert position.entry_price == Decimal("50000.00")
        assert position.quantity == Decimal("0.1")
        assert position.stop_loss == Decimal("48000.00")
        assert position.take_profit == Decimal("53000.00")
        assert position.strategy == "test"
        assert position.status == PositionStatus.OPEN
        assert position.id in position_manager.positions

    def test_create_position_without_stop_loss_uses_risk_manager(self, position_manager, mock_risk_manager):
        """Test creating position without SL/TP uses risk manager defaults"""
        position = position_manager.create_position(
            symbol="ETHUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("3000.00"),
            quantity=Decimal("1.0")
        )

        # Verify risk manager was called to calculate SL/TP
        mock_risk_manager.calculate_stop_loss.assert_called_once_with(
            Decimal("3000.00"),
            PositionSide.LONG
        )
        mock_risk_manager.calculate_take_profit.assert_called_once_with(
            Decimal("3000.00"),
            PositionSide.LONG
        )

        # Verify defaults were used
        assert position.stop_loss == Decimal("49000.00")  # From mock
        assert position.take_profit == Decimal("52000.00")  # From mock

    def test_get_position_exists(self, position_manager):
        """Test getting position that exists"""
        # Create position
        created_position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        # Get position
        retrieved_position = position_manager.get_position(created_position.id)

        assert retrieved_position is not None
        assert retrieved_position.id == created_position.id
        assert retrieved_position.symbol == "BTCUSDT"

    def test_get_position_not_exists(self, position_manager):
        """Test getting position that doesn't exist"""
        fake_id = uuid4()
        position = position_manager.get_position(fake_id)

        assert position is None

    def test_get_all_positions(self, position_manager):
        """Test getting all positions"""
        # Create multiple positions
        pos1 = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        pos2 = position_manager.create_position(
            symbol="ETHUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("3000.00"),
            quantity=Decimal("1.0")
        )

        all_positions = position_manager.get_all_positions()

        assert len(all_positions) == 2
        assert pos1 in all_positions
        assert pos2 in all_positions

    def test_get_open_positions(self, position_manager):
        """Test filtering open positions"""
        # Create open position
        open_pos = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        # Create and close position
        closed_pos = position_manager.create_position(
            symbol="ETHUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("3000.00"),
            quantity=Decimal("1.0")
        )
        position_manager.close_position(closed_pos.id, Decimal("3100.00"))

        # Get open positions
        open_positions = position_manager.get_open_positions()

        assert len(open_positions) == 1
        assert open_positions[0].id == open_pos.id
        assert open_positions[0].status == PositionStatus.OPEN

    def test_get_closed_positions(self, position_manager):
        """Test filtering closed positions"""
        # Create and close position
        pos = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )
        position_manager.close_position(pos.id, Decimal("52000.00"))

        # Get closed positions
        closed_positions = position_manager.get_closed_positions()

        assert len(closed_positions) == 1
        assert closed_positions[0].id == pos.id
        assert closed_positions[0].status == PositionStatus.CLOSED

    def test_update_position_price_success(self, position_manager):
        """Test updating position price"""
        # Create position
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        # Update price
        updated_position = position_manager.update_position_price(
            position.id,
            Decimal("51000.00")
        )

        assert updated_position.current_price == Decimal("51000.00")
        # For LONG: (51000 - 50000) * 0.1 = 100
        assert updated_position.unrealized_pnl == Decimal("100.00")

    def test_update_position_price_not_found(self, position_manager):
        """Test updating non-existent position raises error"""
        fake_id = uuid4()

        with pytest.raises(ValueError, match="Position .* not found"):
            position_manager.update_position_price(fake_id, Decimal("50000.00"))

    def test_check_position_exit_should_not_close(self, position_manager, mock_risk_manager):
        """Test checking position that should not be closed"""
        # Create position
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        # Mock risk manager says don't close
        mock_risk_manager.should_close_position.return_value = (False, None)

        # Check exit
        should_close, reason = position_manager.check_position_exit(
            position.id,
            Decimal("50500.00")
        )

        assert should_close is False
        assert reason is None

    def test_check_position_exit_should_close_stop_loss(self, position_manager, mock_risk_manager):
        """Test checking position that hit stop loss"""
        # Create position
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            stop_loss=Decimal("49000.00")
        )

        # Mock risk manager says close (stop loss hit)
        mock_risk_manager.should_close_position.return_value = (True, "Stop loss hit")

        # Check exit
        should_close, reason = position_manager.check_position_exit(
            position.id,
            Decimal("48500.00")
        )

        assert should_close is True
        assert reason == "Stop loss hit"

    def test_close_position_success(self, position_manager, mock_risk_manager):
        """Test closing position successfully"""
        # Create position
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        # Close position at profit
        closed_position = position_manager.close_position(
            position.id,
            Decimal("52000.00"),
            reason="Take profit"
        )

        assert closed_position.status == PositionStatus.CLOSED
        assert closed_position.current_price == Decimal("52000.00")
        # For LONG: (52000 - 50000) * 0.1 = 200
        assert closed_position.realized_pnl == Decimal("200.00")
        assert closed_position.unrealized_pnl == Decimal("0.00")
        assert closed_position.closed_at is not None

        # Verify risk manager was updated
        mock_risk_manager.update_daily_pnl.assert_called_once_with(Decimal("200.00"))

    def test_close_position_not_found(self, position_manager):
        """Test closing non-existent position raises error"""
        fake_id = uuid4()

        with pytest.raises(ValueError, match="Position .* not found"):
            position_manager.close_position(fake_id, Decimal("50000.00"))

    def test_close_position_already_closed(self, position_manager):
        """Test closing already closed position raises error"""
        # Create and close position
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )
        position_manager.close_position(position.id, Decimal("51000.00"))

        # Try to close again
        with pytest.raises(ValueError, match="Position .* is not open"):
            position_manager.close_position(position.id, Decimal("52000.00"))

    def test_get_total_exposure(self, position_manager):
        """Test calculating total exposure from open positions"""
        # Create positions
        position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        position_manager.create_position(
            symbol="ETHUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("3000.00"),
            quantity=Decimal("1.0")
        )

        # Total exposure = (50000 * 0.1) + (3000 * 1.0) = 5000 + 3000 = 8000
        total_exposure = position_manager.get_total_exposure()

        assert total_exposure == Decimal("8000.00")

    def test_get_total_unrealized_pnl(self, position_manager):
        """Test calculating total unrealized P&L"""
        # Create position 1 with profit
        pos1 = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )
        position_manager.update_position_price(pos1.id, Decimal("51000.00"))  # +100

        # Create position 2 with loss
        pos2 = position_manager.create_position(
            symbol="ETHUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("3000.00"),
            quantity=Decimal("1.0")
        )
        position_manager.update_position_price(pos2.id, Decimal("2950.00"))  # -50

        # Total unrealized P&L = 100 - 50 = 50
        total_pnl = position_manager.get_total_unrealized_pnl()

        assert total_pnl == Decimal("50.00")

    def test_get_total_realized_pnl(self, position_manager):
        """Test calculating total realized P&L from closed positions"""
        # Create and close position 1 with profit
        pos1 = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )
        position_manager.close_position(pos1.id, Decimal("52000.00"))  # +200

        # Create and close position 2 with loss
        pos2 = position_manager.create_position(
            symbol="ETHUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("3000.00"),
            quantity=Decimal("1.0")
        )
        position_manager.close_position(pos2.id, Decimal("2900.00"))  # -100

        # Total realized P&L = 200 - 100 = 100
        total_pnl = position_manager.get_total_realized_pnl()

        assert total_pnl == Decimal("100.00")

    def test_get_position_count(self, position_manager):
        """Test getting position counts by status"""
        # Create open positions
        pos1 = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        pos2 = position_manager.create_position(
            symbol="ETHUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("3000.00"),
            quantity=Decimal("1.0")
        )

        # Close one position
        position_manager.close_position(pos2.id, Decimal("3100.00"))

        # Get counts
        counts = position_manager.get_position_count()

        assert counts["total"] == 2
        assert counts["open"] == 1
        assert counts["closed"] == 1


# Test configuration
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
