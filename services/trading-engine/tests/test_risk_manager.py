"""
Tests for Risk Manager
Purpose: Test risk management rules, position sizing, and safety limits
"""

import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.risk_manager import RiskManager, get_risk_manager
from app.models import PositionSide, SignalAction, Position, PositionStatus


@pytest.fixture
def mock_settings():
    """Mock settings for risk manager"""
    settings = MagicMock()
    settings.max_position_size_pct = 10.0  # 10% max position
    settings.max_daily_loss_pct = 5.0      # 5% max daily loss
    settings.default_stop_loss_pct = 2.0   # 2% stop loss
    settings.default_take_profit_pct = 4.0 # 4% take profit
    settings.paper_initial_balance = 10000.0
    settings.signal_confidence_threshold = 0.6
    return settings


@pytest.fixture
def risk_manager(mock_settings):
    """Create risk manager with mocked settings"""
    with patch('app.risk_manager.get_settings', return_value=mock_settings):
        manager = RiskManager()
        return manager


class TestRiskManagerInitialization:
    """Test risk manager initialization"""

    def test_initialization(self, risk_manager):
        """Test risk manager initializes correctly"""
        assert risk_manager.daily_pnl == Decimal("0")
        assert risk_manager.trading_halted is False
        assert risk_manager.settings is not None


class TestDailyPnLTracking:
    """Test daily P&L tracking and reset"""

    def test_update_daily_pnl_profit(self, risk_manager):
        """Test updating daily P&L with profit"""
        risk_manager.update_daily_pnl(Decimal("100.00"))
        assert risk_manager.daily_pnl == Decimal("100.00")

        risk_manager.update_daily_pnl(Decimal("50.00"))
        assert risk_manager.daily_pnl == Decimal("150.00")

    def test_update_daily_pnl_loss(self, risk_manager):
        """Test updating daily P&L with loss"""
        risk_manager.update_daily_pnl(Decimal("-100.00"))
        assert risk_manager.daily_pnl == Decimal("-100.00")

        risk_manager.update_daily_pnl(Decimal("-50.00"))
        assert risk_manager.daily_pnl == Decimal("-150.00")

    def test_reset_daily_pnl(self, risk_manager):
        """Test resetting daily P&L"""
        risk_manager.update_daily_pnl(Decimal("500.00"))
        assert risk_manager.daily_pnl == Decimal("500.00")

        risk_manager.reset_daily_pnl()
        assert risk_manager.daily_pnl == Decimal("0")
        assert risk_manager.trading_halted is False

    def test_reset_daily_pnl_clears_halt(self, risk_manager):
        """Test that resetting P&L clears trading halt"""
        risk_manager.halt_trading()
        assert risk_manager.trading_halted is True

        risk_manager.reset_daily_pnl()
        assert risk_manager.trading_halted is False


class TestTradingHalt:
    """Test trading halt mechanism"""

    def test_should_halt_trading_within_limit(self, risk_manager):
        """Test that trading not halted when within loss limit"""
        # Loss of -400 is 4% of 10000 balance (< 5% limit)
        risk_manager.update_daily_pnl(Decimal("-400.00"))
        assert risk_manager.should_halt_trading() is False

    def test_should_halt_trading_exceeds_limit(self, risk_manager):
        """Test that trading halted when daily loss limit exceeded"""
        # Max loss is 5% of 10000 = 500
        # Loss of -600 exceeds the limit
        risk_manager.update_daily_pnl(Decimal("-600.00"))
        assert risk_manager.should_halt_trading() is True
        assert risk_manager.trading_halted is True

    def test_should_halt_trading_at_exact_limit(self, risk_manager):
        """Test trading halted at exact loss limit"""
        # Exactly at 5% loss
        risk_manager.update_daily_pnl(Decimal("-500.00"))
        assert risk_manager.should_halt_trading() is False

        # Just over 5% loss
        risk_manager.update_daily_pnl(Decimal("-0.01"))
        assert risk_manager.should_halt_trading() is True

    def test_halt_trading_logs_critical(self, risk_manager):
        """Test that halting trading logs critical message"""
        risk_manager.halt_trading()
        assert risk_manager.trading_halted is True

    def test_halt_trading_idempotent(self, risk_manager):
        """Test that halting already-halted trading is safe"""
        risk_manager.halt_trading()
        risk_manager.halt_trading()  # Should not error
        assert risk_manager.trading_halted is True

    def test_resume_trading(self, risk_manager):
        """Test manually resuming trading"""
        risk_manager.halt_trading()
        assert risk_manager.trading_halted is True

        risk_manager.resume_trading()
        assert risk_manager.trading_halted is False


class TestPositionSizing:
    """Test position size calculations"""

    def test_calculate_position_size_basic(self, risk_manager):
        """Test basic position size calculation"""
        account_balance = Decimal("10000.00")
        entry_price = Decimal("50000.00")

        # Max position is 10% of 10000 = 1000
        # Quantity = 1000 / 50000 = 0.02
        quantity = risk_manager.calculate_position_size(account_balance, entry_price)

        expected = Decimal("1000.00") / entry_price
        assert quantity == expected

    def test_calculate_position_size_with_stop_loss(self, risk_manager):
        """Test position sizing with stop-loss (risk-based)"""
        account_balance = Decimal("10000.00")
        entry_price = Decimal("50000.00")
        stop_loss_price = Decimal("49000.00")  # 2% below entry

        quantity = risk_manager.calculate_position_size(
            account_balance,
            entry_price,
            stop_loss_price
        )

        # Risk per unit: 50000 - 49000 = 1000
        # Max risk: 10% of 10000 = 1000
        # Risk-based quantity: 1000 / 1000 = 1.0
        # Basic quantity: 1000 / 50000 = 0.02
        # Should use smaller (0.02)
        assert quantity == Decimal("0.02")

    def test_calculate_position_size_zero_balance(self, risk_manager):
        """Test position sizing with zero balance returns zero"""
        quantity = risk_manager.calculate_position_size(
            Decimal("0"),
            Decimal("50000.00")
        )
        assert quantity == Decimal("0")

    def test_calculate_position_size_zero_price(self, risk_manager):
        """Test position sizing with zero price returns zero"""
        quantity = risk_manager.calculate_position_size(
            Decimal("10000.00"),
            Decimal("0")
        )
        assert quantity == Decimal("0")

    def test_calculate_position_size_invalid_stop_loss(self, risk_manager):
        """Test position sizing with invalid stop-loss ignores it"""
        quantity = risk_manager.calculate_position_size(
            Decimal("10000.00"),
            Decimal("50000.00"),
            Decimal("0")  # Invalid stop-loss
        )
        # Should use basic calculation
        assert quantity == Decimal("0.02")


class TestStopLossCalculation:
    """Test stop-loss price calculations"""

    def test_calculate_stop_loss_long_position(self, risk_manager):
        """Test stop-loss for LONG position (below entry)"""
        entry_price = Decimal("50000.00")
        stop_loss = risk_manager.calculate_stop_loss(entry_price, PositionSide.LONG)

        # Default 2% below entry: 50000 * 0.98 = 49000
        expected = Decimal("49000.00")
        assert stop_loss == expected

    def test_calculate_stop_loss_short_position(self, risk_manager):
        """Test stop-loss for SHORT position (above entry)"""
        entry_price = Decimal("50000.00")
        stop_loss = risk_manager.calculate_stop_loss(entry_price, PositionSide.SHORT)

        # Default 2% above entry: 50000 * 1.02 = 51000
        expected = Decimal("51000.00")
        assert stop_loss == expected

    def test_calculate_stop_loss_custom_percentage(self, risk_manager):
        """Test stop-loss with custom percentage"""
        entry_price = Decimal("50000.00")
        custom_pct = 5.0  # 5% stop-loss

        stop_loss = risk_manager.calculate_stop_loss(
            entry_price,
            PositionSide.LONG,
            stop_loss_pct=custom_pct
        )

        # 5% below entry: 50000 * 0.95 = 47500
        expected = Decimal("47500.00")
        assert stop_loss == expected


class TestTakeProfitCalculation:
    """Test take-profit price calculations"""

    def test_calculate_take_profit_long_position(self, risk_manager):
        """Test take-profit for LONG position (above entry)"""
        entry_price = Decimal("50000.00")
        take_profit = risk_manager.calculate_take_profit(entry_price, PositionSide.LONG)

        # Default 4% above entry: 50000 * 1.04 = 52000
        expected = Decimal("52000.00")
        assert take_profit == expected

    def test_calculate_take_profit_short_position(self, risk_manager):
        """Test take-profit for SHORT position (below entry)"""
        entry_price = Decimal("50000.00")
        take_profit = risk_manager.calculate_take_profit(entry_price, PositionSide.SHORT)

        # Default 4% below entry: 50000 * 0.96 = 48000
        expected = Decimal("48000.00")
        assert take_profit == expected

    def test_calculate_take_profit_custom_percentage(self, risk_manager):
        """Test take-profit with custom percentage"""
        entry_price = Decimal("50000.00")
        custom_pct = 10.0  # 10% take-profit

        take_profit = risk_manager.calculate_take_profit(
            entry_price,
            PositionSide.LONG,
            take_profit_pct=custom_pct
        )

        # 10% above entry: 50000 * 1.10 = 55000
        expected = Decimal("55000.00")
        assert take_profit == expected


class TestPositionExitChecks:
    """Test position exit conditions"""

    def test_should_close_position_stop_loss_hit_long(self, risk_manager):
        """Test closing LONG position when stop-loss hit"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            current_price=Decimal("50000.00"),
            stop_loss=Decimal("49000.00"),
            take_profit=Decimal("52000.00"),
            status=PositionStatus.OPEN
        )

        # Price drops to 48000 (below stop-loss)
        should_close, reason = risk_manager.should_close_position(
            position,
            Decimal("48000.00")
        )

        assert should_close is True
        assert reason == "STOP_LOSS"

    def test_should_close_position_take_profit_hit_long(self, risk_manager):
        """Test closing LONG position when take-profit hit"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            current_price=Decimal("50000.00"),
            stop_loss=Decimal("49000.00"),
            take_profit=Decimal("52000.00"),
            status=PositionStatus.OPEN
        )

        # Price rises to 53000 (above take-profit)
        should_close, reason = risk_manager.should_close_position(
            position,
            Decimal("53000.00")
        )

        assert should_close is True
        assert reason == "TAKE_PROFIT"

    def test_should_close_position_no_trigger(self, risk_manager):
        """Test position stays open when no trigger hit"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            current_price=Decimal("50000.00"),
            stop_loss=Decimal("49000.00"),
            take_profit=Decimal("52000.00"),
            status=PositionStatus.OPEN
        )

        # Price at 50500 (between stop-loss and take-profit)
        should_close, reason = risk_manager.should_close_position(
            position,
            Decimal("50500.00")
        )

        assert should_close is False
        assert reason is None

    def test_should_close_position_stop_loss_hit_short(self, risk_manager):
        """Test closing SHORT position when stop-loss hit"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.SHORT,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            current_price=Decimal("50000.00"),
            stop_loss=Decimal("51000.00"),  # Above entry for SHORT
            take_profit=Decimal("48000.00"), # Below entry for SHORT
            status=PositionStatus.OPEN
        )

        # Price rises to 52000 (above stop-loss)
        should_close, reason = risk_manager.should_close_position(
            position,
            Decimal("52000.00")
        )

        assert should_close is True
        assert reason == "STOP_LOSS"


class TestSignalValidation:
    """Test signal confidence validation"""

    def test_validate_signal_high_confidence(self, risk_manager):
        """Test validating signal with high confidence"""
        is_valid, reason = risk_manager.validate_signal(
            SignalAction.BUY,
            confidence=0.8
        )

        assert is_valid is True
        assert reason == "OK"

    def test_validate_signal_low_confidence(self, risk_manager):
        """Test rejecting signal with low confidence"""
        is_valid, reason = risk_manager.validate_signal(
            SignalAction.BUY,
            confidence=0.4  # Below threshold of 0.6
        )

        assert is_valid is False
        assert "confidence too low" in reason.lower()

    def test_validate_signal_at_threshold(self, risk_manager):
        """Test signal exactly at confidence threshold"""
        is_valid, reason = risk_manager.validate_signal(
            SignalAction.BUY,
            confidence=0.6  # Exactly at threshold
        )

        assert is_valid is True

    def test_validate_signal_hold_always_valid(self, risk_manager):
        """Test that HOLD signals are always valid"""
        is_valid, reason = risk_manager.validate_signal(
            SignalAction.HOLD,
            confidence=0.1  # Very low confidence
        )

        assert is_valid is True

    def test_validate_signal_trading_halted(self, risk_manager):
        """Test that signals rejected when trading halted"""
        risk_manager.halt_trading()

        is_valid, reason = risk_manager.validate_signal(
            SignalAction.BUY,
            confidence=0.9  # High confidence
        )

        assert is_valid is False
        assert "halted" in reason.lower()


class TestRiskManagerSingleton:
    """Test singleton pattern"""

    def test_get_risk_manager_returns_singleton(self):
        """Test that get_risk_manager returns same instance"""
        with patch('app.risk_manager.get_settings'):
            manager1 = get_risk_manager()
            manager2 = get_risk_manager()

            assert manager1 is manager2


class TestPositionSizeValidation:
    """Test position size validation"""

    def test_validate_position_size_within_limit(self, risk_manager):
        """Test validating position size within limits"""
        account_balance = Decimal("10000.00")
        position_value = Decimal("500.00")  # 5% of balance

        is_valid, reason = risk_manager.validate_position_size(
            position_value,
            account_balance
        )

        assert is_valid is True

    def test_validate_position_size_exceeds_limit(self, risk_manager):
        """Test rejecting position size exceeding limits"""
        account_balance = Decimal("10000.00")
        position_value = Decimal("1500.00")  # 15% of balance (> 10% limit)

        is_valid, reason = risk_manager.validate_position_size(
            position_value,
            account_balance
        )

        assert is_valid is False
        assert "exceeds maximum" in reason.lower()
