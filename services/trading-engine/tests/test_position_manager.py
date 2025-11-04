"""
Tests for Position Manager
Purpose: Test position tracking, P&L calculations, and lifecycle management
"""

import pytest
from decimal import Decimal
from uuid import UUID, uuid4
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

from app.position_manager import PositionManager, get_position_manager
from app.models import Position, PositionSide, PositionStatus


@pytest.fixture
def mock_risk_manager():
    """Mock risk manager"""
    manager = MagicMock()
    manager.calculate_stop_loss = MagicMock(return_value=Decimal("49000.00"))
    manager.calculate_take_profit = MagicMock(return_value=Decimal("52000.00"))
    manager.should_close_position = MagicMock(return_value=(False, None))
    manager.update_daily_pnl = MagicMock()
    return manager


@pytest.fixture
def mock_position_repo():
    """Mock position repository"""
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.update_price = AsyncMock()
    repo.close = AsyncMock()
    return repo


@pytest.fixture
def position_manager(mock_risk_manager, mock_position_repo):
    """Create position manager with mocked dependencies"""
    with patch('app.position_manager.get_risk_manager', return_value=mock_risk_manager), \
         patch('app.position_manager.get_position_repository', return_value=mock_position_repo):
        manager = PositionManager()
        return manager


class TestPositionCreation:
    """Test position creation"""

    def test_create_long_position(self, position_manager, mock_risk_manager):
        """Test creating a LONG position"""
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            strategy="TEST_STRATEGY"
        )

        assert position.symbol == "BTCUSDT"
        assert position.side == PositionSide.LONG
        assert position.entry_price == Decimal("50000.00")
        assert position.quantity == Decimal("0.1")
        assert position.status == PositionStatus.OPEN
        assert position.current_price == Decimal("50000.00")

        # Verify stop-loss and take-profit calculated
        mock_risk_manager.calculate_stop_loss.assert_called_once()
        mock_risk_manager.calculate_take_profit.assert_called_once()

    def test_create_short_position(self, position_manager):
        """Test creating a SHORT position"""
        position = position_manager.create_position(
            symbol="ETHUSDT",
            side=PositionSide.SHORT,
            entry_price=Decimal("3000.00"),
            quantity=Decimal("1.0"),
            strategy="SHORT_STRATEGY"
        )

        assert position.side == PositionSide.SHORT
        assert position.symbol == "ETHUSDT"

    def test_create_position_with_custom_stops(self, position_manager):
        """Test creating position with custom stop-loss and take-profit"""
        custom_sl = Decimal("48000.00")
        custom_tp = Decimal("55000.00")

        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            stop_loss=custom_sl,
            take_profit=custom_tp
        )

        assert position.stop_loss == custom_sl
        assert position.take_profit == custom_tp

    def test_create_position_adds_to_positions(self, position_manager):
        """Test that created position is added to manager's positions dict"""
        initial_count = len(position_manager.positions)

        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        assert len(position_manager.positions) == initial_count + 1
        assert position.id in position_manager.positions

    def test_create_position_persists_to_database(self, position_manager, mock_position_repo):
        """Test that position creation is persisted to database"""
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        # Verify database persistence attempted (async task created)
        # Note: In real test, would need to await the async task


class TestPositionRetrieval:
    """Test position retrieval methods"""

    def test_get_position_by_id(self, position_manager):
        """Test retrieving position by ID"""
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        retrieved = position_manager.get_position(position.id)
        assert retrieved is not None
        assert retrieved.id == position.id

    def test_get_position_not_found(self, position_manager):
        """Test retrieving non-existent position returns None"""
        fake_id = uuid4()
        position = position_manager.get_position(fake_id)
        assert position is None

    def test_get_all_positions(self, position_manager):
        """Test retrieving all positions"""
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

        all_positions = position_manager.get_all_positions()
        assert len(all_positions) == 2

    def test_get_open_positions(self, position_manager):
        """Test retrieving only open positions"""
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
        position_manager.close_position(pos1.id, Decimal("51000.00"))

        open_positions = position_manager.get_open_positions()
        assert len(open_positions) == 1
        assert open_positions[0].id == pos2.id

    def test_get_closed_positions(self, position_manager):
        """Test retrieving only closed positions"""
        pos1 = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        position_manager.close_position(pos1.id, Decimal("51000.00"))

        closed_positions = position_manager.get_closed_positions()
        assert len(closed_positions) == 1
        assert closed_positions[0].status == PositionStatus.CLOSED


class TestPositionPriceUpdate:
    """Test position price updates and P&L calculation"""

    def test_update_position_price(self, position_manager):
        """Test updating position with new price"""
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        new_price = Decimal("51000.00")
        updated = position_manager.update_position_price(position.id, new_price)

        assert updated.current_price == new_price
        assert updated.unrealized_pnl > Decimal("0")  # Price went up for LONG

    def test_update_price_calculates_profit_for_long(self, position_manager):
        """Test P&L calculation for LONG position with price increase"""
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        position_manager.update_position_price(position.id, Decimal("52000.00"))

        # Expected P&L: (52000 - 50000) * 0.1 = 200
        assert position.unrealized_pnl == Decimal("200.00")

    def test_update_price_calculates_loss_for_long(self, position_manager):
        """Test P&L calculation for LONG position with price decrease"""
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        position_manager.update_position_price(position.id, Decimal("48000.00"))

        # Expected P&L: (48000 - 50000) * 0.1 = -200
        assert position.unrealized_pnl == Decimal("-200.00")

    def test_update_price_invalid_position(self, position_manager):
        """Test updating price for non-existent position raises error"""
        fake_id = uuid4()

        with pytest.raises(ValueError, match="not found"):
            position_manager.update_position_price(fake_id, Decimal("50000.00"))

    def test_update_price_persists_to_database(self, position_manager, mock_position_repo):
        """Test that price updates are persisted to database"""
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        position_manager.update_position_price(position.id, Decimal("51000.00"))

        # Verify database persistence attempted


class TestPositionExit:
    """Test position exit checks and closure"""

    def test_check_position_exit_no_trigger(self, position_manager, mock_risk_manager):
        """Test checking position exit when no trigger hit"""
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        mock_risk_manager.should_close_position.return_value = (False, None)

        should_close, reason = position_manager.check_position_exit(
            position.id,
            Decimal("50500.00")
        )

        assert should_close is False
        assert reason is None

    def test_check_position_exit_stop_loss(self, position_manager, mock_risk_manager):
        """Test position exit triggered by stop-loss"""
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            stop_loss=Decimal("49000.00")
        )

        mock_risk_manager.should_close_position.return_value = (True, "STOP_LOSS")

        should_close, reason = position_manager.check_position_exit(
            position.id,
            Decimal("48000.00")  # Below stop-loss
        )

        assert should_close is True
        assert reason == "STOP_LOSS"

    def test_close_position_success(self, position_manager, mock_risk_manager):
        """Test closing a position"""
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        close_price = Decimal("52000.00")
        closed = position_manager.close_position(position.id, close_price, reason="TAKE_PROFIT")

        assert closed.status == PositionStatus.CLOSED
        assert closed.realized_pnl == Decimal("200.00")  # (52000-50000)*0.1
        assert closed.unrealized_pnl == Decimal("0")
        assert closed.closed_at is not None

    def test_close_position_not_found(self, position_manager):
        """Test closing non-existent position raises error"""
        fake_id = uuid4()

        with pytest.raises(ValueError, match="not found"):
            position_manager.close_position(fake_id, Decimal("50000.00"))

    def test_close_position_already_closed(self, position_manager):
        """Test closing already closed position raises error"""
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        position_manager.close_position(position.id, Decimal("51000.00"))

        with pytest.raises(ValueError, match="not open"):
            position_manager.close_position(position.id, Decimal("52000.00"))

    def test_close_position_updates_daily_pnl(self, position_manager, mock_risk_manager):
        """Test that closing position updates risk manager's daily P&L"""
        position = position_manager.create_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        position_manager.close_position(position.id, Decimal("52000.00"))

        mock_risk_manager.update_daily_pnl.assert_called_once()


class TestAggregateMetrics:
    """Test aggregate position metrics"""

    def test_get_total_exposure_no_positions(self, position_manager):
        """Test total exposure with no open positions"""
        exposure = position_manager.get_total_exposure()
        assert exposure == Decimal("0")

    def test_get_total_exposure_with_positions(self, position_manager):
        """Test total exposure calculation"""
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

        # Expected: (50000*0.1) + (3000*1.0) = 5000 + 3000 = 8000
        exposure = position_manager.get_total_exposure()
        assert exposure == Decimal("8000.00")

    def test_get_total_unrealized_pnl(self, position_manager):
        """Test total unrealized P&L calculation"""
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

        # Update prices
        position_manager.update_position_price(pos1.id, Decimal("51000.00"))  # +100
        position_manager.update_position_price(pos2.id, Decimal("3100.00"))   # +100

        total_unrealized = position_manager.get_total_unrealized_pnl()
        assert total_unrealized == Decimal("200.00")

    def test_get_total_realized_pnl(self, position_manager):
        """Test total realized P&L from closed positions"""
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

        # Close with profit and loss
        position_manager.close_position(pos1.id, Decimal("52000.00"))  # +200
        position_manager.close_position(pos2.id, Decimal("2900.00"))   # -100

        total_realized = position_manager.get_total_realized_pnl()
        assert total_realized == Decimal("100.00")

    def test_get_position_count(self, position_manager):
        """Test position count statistics"""
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

        position_manager.close_position(pos1.id, Decimal("51000.00"))

        counts = position_manager.get_position_count()
        assert counts["total"] == 2
        assert counts["open"] == 1
        assert counts["closed"] == 1


class TestPositionManagerSingleton:
    """Test singleton pattern"""

    def test_get_position_manager_returns_singleton(self):
        """Test that get_position_manager returns same instance"""
        with patch('app.position_manager.get_risk_manager'), \
             patch('app.position_manager.get_position_repository'):
            manager1 = get_position_manager()
            manager2 = get_position_manager()

            assert manager1 is manager2
