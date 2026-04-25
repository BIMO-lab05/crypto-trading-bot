"""
Unit Tests for Paper Trading Engine
Tests trading simulation logic without real money or database
"""

import pytest
import asyncio
from decimal import Decimal
from datetime import datetime
from uuid import uuid4
from unittest.mock import Mock, AsyncMock, patch, MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "shared"))

from app.paper_trading import PaperTradingEngine
from app.models import (
    Order, OrderCreate, OrderStatus, OrderSide, OrderType,
    Position, PositionSide, PositionStatus
)


class TestPaperTradingEngine:
    """Test suite for PaperTradingEngine"""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings configuration"""
        settings = Mock()
        settings.paper_initial_balance = 100.0
        settings.paper_commission_pct = 0.1  # 0.1%
        return settings

    @pytest.fixture
    def mock_position_manager(self):
        """Mock position manager"""
        manager = Mock()
        manager.get_total_unrealized_pnl.return_value = Decimal("0")
        manager.get_open_positions.return_value = []
        manager.get_closed_positions.return_value = []
        return manager

    @pytest.fixture
    def mock_risk_manager(self):
        """Mock risk manager"""
        manager = Mock()
        manager.check_position_limits.return_value = (True, None)
        return manager

    @pytest.fixture
    def mock_trade_repo(self):
        """Mock trade repository"""
        repo = Mock()
        repo.log_trade = AsyncMock()
        return repo

    @pytest.fixture
    def mock_portfolio_repo(self):
        """Mock portfolio repository"""
        return Mock()

    @pytest.fixture
    def trading_engine(self, mock_settings, mock_position_manager, mock_risk_manager,
                      mock_trade_repo, mock_portfolio_repo):
        """Create PaperTradingEngine with mocked dependencies"""
        with patch('app.paper_trading.get_settings', return_value=mock_settings), \
             patch('app.paper_trading.get_position_manager', return_value=mock_position_manager), \
             patch('app.paper_trading.get_risk_manager', return_value=mock_risk_manager), \
             patch('app.paper_trading.get_trade_repository', return_value=mock_trade_repo), \
             patch('app.paper_trading.get_portfolio_repository', return_value=mock_portfolio_repo):

            engine = PaperTradingEngine()
            return engine

    def test_initialization(self, trading_engine, mock_settings):
        """Test engine initializes with correct settings"""
        assert trading_engine.balance == Decimal("100.0")
        assert trading_engine.initial_balance == Decimal("100.0")
        assert trading_engine.commission_pct == Decimal("0.001")  # 0.1% as decimal

    def test_get_balance(self, trading_engine):
        """Test getting current balance"""
        balance = trading_engine.get_balance()
        assert balance == Decimal("100.0")
        assert isinstance(balance, Decimal)

    def test_get_total_equity_no_positions(self, trading_engine, mock_position_manager):
        """Test total equity with no open positions"""
        mock_position_manager.get_total_unrealized_pnl.return_value = Decimal("0")

        equity = trading_engine.get_total_equity()

        assert equity == Decimal("100.0")
        mock_position_manager.get_total_unrealized_pnl.assert_called_once()

    def test_get_total_equity_with_unrealized_pnl(self, trading_engine, mock_position_manager):
        """Test total equity includes unrealized P&L"""
        mock_position_manager.get_total_unrealized_pnl.return_value = Decimal("500.50")

        equity = trading_engine.get_total_equity()

        assert equity == Decimal("10500.50")

    def test_calculate_commission(self, trading_engine):
        """Test commission calculation"""
        # 0.1% commission on $5000 order = $5
        commission = trading_engine.calculate_commission(Decimal("5000.00"))

        assert commission == Decimal("5.00")

    def test_calculate_commission_small_order(self, trading_engine):
        """Test commission on small order"""
        # 0.1% commission on $100 order = $0.10
        commission = trading_engine.calculate_commission(Decimal("100.00"))

        assert commission == Decimal("0.10")

    @pytest.mark.asyncio
    async def test_execute_buy_order_success(self, trading_engine, mock_position_manager):
        """Test successful BUY order execution"""
        # Create mock position
        mock_position = Mock()
        mock_position.id = uuid4()
        mock_position_manager.create_position.return_value = mock_position

        # Create BUY order
        order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.1"),
            type=OrderType.MARKET,  # Fixed: 'type' not 'order_type'
            strategy="test"
        )

        # Execute order at $50,000
        executed_order, error = await trading_engine.execute_market_order(
            order=order,
            current_price=Decimal("50000.00")
        )

        # Verify success
        assert error is None
        assert executed_order.status == OrderStatus.FILLED
        assert executed_order.filled_price == Decimal("50000.00")
        assert executed_order.filled_quantity == Decimal("0.1")

        # Verify balance deducted (50000 * 0.1 = 5000 + 5 commission = 5005)
        assert trading_engine.balance == Decimal("4995.00")

        # Verify position created
        mock_position_manager.create_position.assert_called_once_with(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            strategy="test"
        )

    @pytest.mark.asyncio
    async def test_execute_buy_order_insufficient_balance(self, trading_engine):
        """Test BUY order fails with insufficient balance"""
        # Create BUY order that exceeds balance
        order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("1.0"),  # $50,000 + commission
            type=OrderType.MARKET  # Fixed: 'type' not 'order_type'
        )

        # Execute order
        executed_order, error = await trading_engine.execute_market_order(
            order=order,
            current_price=Decimal("50000.00")
        )

        # Verify failure
        assert error is not None
        assert "Insufficient balance" in error
        assert executed_order.status == OrderStatus.FAILED

        # Verify balance unchanged
        assert trading_engine.balance == Decimal("100.00")

    @pytest.mark.asyncio
    async def test_execute_sell_order_success(self, trading_engine, mock_position_manager):
        """Test successful SELL order execution"""
        # First execute BUY to create position
        trading_engine.balance = Decimal("100.00")
        mock_buy_position = Mock()
        mock_buy_position.id = uuid4()
        mock_position_manager.create_position.return_value = mock_buy_position

        buy_order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.1"),
            type=OrderType.MARKET  # Fixed: 'type' not 'order_type'
        )

        await trading_engine.execute_market_order(buy_order, Decimal("50000.00"))

        # Now mock the position as open
        mock_open_position = Mock()
        mock_open_position.id = mock_buy_position.id
        mock_open_position.symbol = "BTCUSDT"
        mock_open_position.side = PositionSide.LONG
        mock_open_position.quantity = Decimal("0.1")
        mock_position_manager.get_open_positions.return_value = [mock_open_position]

        # Mock closed position with profit
        mock_closed_position = Mock()
        mock_closed_position.id = mock_buy_position.id
        mock_closed_position.realized_pnl = Decimal("200.00")
        mock_position_manager.close_position.return_value = mock_closed_position

        # Create SELL order
        sell_order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            quantity=Decimal("0.1"),
            type=OrderType.MARKET  # Fixed: 'type' not 'order_type'
        )

        # Execute SELL at higher price ($52,000)
        initial_balance = trading_engine.balance
        executed_order, error = await trading_engine.execute_market_order(
            sell_order,
            Decimal("52000.00")
        )

        # Verify success
        assert error is None
        assert executed_order.status == OrderStatus.FILLED

        # Verify balance increased (52000 * 0.1 = 5200 - 5.20 commission = 5194.80)
        expected_balance = initial_balance + Decimal("5194.80")
        assert trading_engine.balance == expected_balance

        # Verify position closed
        mock_position_manager.close_position.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_sell_order_no_position(self, trading_engine, mock_position_manager):
        """Test SELL order fails when no position exists"""
        # No open positions
        mock_position_manager.get_open_positions.return_value = []

        # Create SELL order
        order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            quantity=Decimal("0.1"),
            type=OrderType.MARKET  # Fixed: 'type' not 'order_type'
        )

        # Execute order
        executed_order, error = await trading_engine.execute_market_order(
            order=order,
            current_price=Decimal("50000.00")
        )

        # Verify failure
        assert error is not None
        assert "No open LONG position" in error
        assert executed_order.status == OrderStatus.FAILED

    def test_can_open_position_success(self, trading_engine, mock_risk_manager):
        """Test can open position with sufficient balance"""
        can_open, reason = trading_engine.can_open_position(
            symbol="BTCUSDT",
            quantity=Decimal("0.1"),
            price=Decimal("50000.00")
        )

        assert can_open is True
        assert reason is None

    def test_can_open_position_insufficient_balance(self, trading_engine):
        """Test cannot open position with insufficient balance"""
        can_open, reason = trading_engine.can_open_position(
            symbol="BTCUSDT",
            quantity=Decimal("10.0"),  # Too large
            price=Decimal("50000.00")
        )

        assert can_open is False
        assert "Insufficient balance" in reason

    def test_can_open_position_risk_limit(self, trading_engine, mock_risk_manager):
        """Test cannot open position when risk manager blocks"""
        # Mock risk manager rejection
        mock_risk_manager.check_position_limits.return_value = (False, "Too many positions")

        can_open, reason = trading_engine.can_open_position(
            symbol="BTCUSDT",
            quantity=Decimal("0.1"),
            price=Decimal("50000.00")
        )

        assert can_open is False
        assert reason == "Too many positions"

    def test_get_performance_summary_no_trades(self, trading_engine, mock_position_manager):
        """Test performance summary with no trades"""
        summary = trading_engine.get_performance_summary()

        assert summary["initial_balance"] == 100.0
        assert summary["current_balance"] == 100.0
        assert summary["total_equity"] == 100.0
        assert summary["total_pnl"] == 0.0
        assert summary["roi"] == 0.0
        assert summary["total_trades"] == 0
        assert summary["winning_trades"] == 0
        assert summary["losing_trades"] == 0
        assert summary["win_rate"] == 0.0

    def test_get_performance_summary_with_trades(self, trading_engine, mock_position_manager):
        """Test performance summary with completed trades"""
        # Mock closed positions with wins and losses
        winning_pos = Mock()
        winning_pos.realized_pnl = Decimal("200.00")

        losing_pos = Mock()
        losing_pos.realized_pnl = Decimal("-100.00")

        another_win = Mock()
        another_win.realized_pnl = Decimal("150.00")

        mock_position_manager.get_closed_positions.return_value = [
            winning_pos, losing_pos, another_win
        ]

        # Simulate balance change (started at 100, now at 125)
        trading_engine.balance = Decimal("125.00")

        summary = trading_engine.get_performance_summary()

        assert summary["initial_balance"] == 100.0
        assert summary["current_balance"] == 125.0
        assert summary["total_pnl"] == 25.0
        assert summary["roi"] == 25.0  # 25/100 * 100
        assert summary["total_trades"] == 3
        assert summary["winning_trades"] == 2
        assert summary["losing_trades"] == 1
        assert summary["win_rate"] == 66.67  # 2/3 * 100


# Test configuration
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
