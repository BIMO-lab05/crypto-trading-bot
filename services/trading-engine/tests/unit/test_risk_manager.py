"""
Unit Tests for Risk Manager
Tests risk management and position sizing logic
"""

import pytest

# Un-skipped 2026-07-31. This module carried a blanket
# `pytestmark = pytest.mark.skip(...)` from a PR #86 CI fix-up, disabling all
# 32 tests. On investigation only 4 of them actually failed, and all 4 were
# stale expectations left behind by the $10,000 -> $100 paper-account
# migration -- not drift in the risk manager, which was correct throughout.
# The other 28 had been passing the whole time.
#
# The risk manager enforces the per-trade and daily-loss caps that the project
# depends on, so running these is the point.

from decimal import Decimal
from unittest.mock import Mock, patch

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))

from app.config import get_settings
from app.risk_manager import RiskManager
from app.models import Position, PositionSide, PositionStatus, SignalAction

#: The declared paper equity, routed through Settings (never a bare literal).
#: Every dollar figure below is DERIVED from this so the suite re-scales with
#: the declared account size automatically.
EQUITY = Decimal(str(get_settings().paper_initial_balance))


class TestRiskManager:
    """Test suite for RiskManager"""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings configuration.

        The risk knobs are explicit SCENARIO parameters (e.g. the 5% daily
        breaker predates ADR-028's production 12%), but the balance tracks the
        declared account size via ``EQUITY``.
        """
        settings = Mock()
        settings.paper_initial_balance = float(EQUITY)
        settings.max_position_size_pct = 10.0  # 10% of capital
        settings.max_daily_loss_pct = 5.0  # 5% max daily loss
        settings.default_stop_loss_pct = 2.0  # 2% stop loss
        settings.short_stop_loss_pct = 1.5  # SHORT stop, tighter than LONG
        settings.default_take_profit_pct = 4.0  # 4% take profit
        settings.max_total_exposure_pct = 80.0  # 80% max exposure
        settings.min_signal_confidence = 0.7  # 70% minimum confidence
        return settings

    @pytest.fixture
    def risk_manager(self, mock_settings):
        """Create RiskManager with mocked settings"""
        with patch("app.risk_manager.get_settings", return_value=mock_settings):
            manager = RiskManager()
            return manager

    def test_initialization(self, risk_manager):
        """Test risk manager initializes correctly"""
        assert risk_manager.daily_pnl == Decimal("0")
        assert risk_manager.trading_halted is False

    def test_reset_daily_pnl(self, risk_manager):
        """Test resetting daily P&L"""
        # Set some P&L and halt trading
        risk_manager.daily_pnl = Decimal("-500.00")
        risk_manager.trading_halted = True

        # Reset
        risk_manager.reset_daily_pnl()

        assert risk_manager.daily_pnl == Decimal("0")
        assert risk_manager.trading_halted is False

    def test_update_daily_pnl_profit(self, risk_manager):
        """Test updating daily P&L with profit"""
        risk_manager.update_daily_pnl(Decimal("100.00"))

        assert risk_manager.daily_pnl == Decimal("100.00")
        assert risk_manager.trading_halted is False

    def test_update_daily_pnl_small_loss(self, risk_manager):
        """Test updating daily P&L with small loss"""
        # Loss of 2% of the declared account - below the 5% scenario breaker.
        small_loss = -(EQUITY * Decimal("0.02"))
        risk_manager.update_daily_pnl(small_loss)

        assert risk_manager.daily_pnl == small_loss
        assert risk_manager.trading_halted is False

    def test_update_daily_pnl_exceeds_limit(self, risk_manager):
        """Test updating daily P&L exceeds limit halts trading"""
        # Loss of 6% of the declared account - exceeds the 5% scenario limit
        big_loss = -(EQUITY * Decimal("0.06"))
        risk_manager.update_daily_pnl(big_loss)

        assert risk_manager.daily_pnl == big_loss
        assert risk_manager.trading_halted is True

    def test_should_halt_trading_below_limit(self, risk_manager):
        """Test should not halt when below loss limit"""
        # 4% of the declared account, just under the 5% scenario breaker.
        risk_manager.daily_pnl = -(EQUITY * Decimal("0.04"))

        should_halt = risk_manager.should_halt_trading()

        assert should_halt is False

    def test_should_halt_trading_at_limit(self, risk_manager):
        """Test should halt when at loss limit"""
        risk_manager.daily_pnl = -(EQUITY * Decimal("0.05"))  # 5% loss

        should_halt = risk_manager.should_halt_trading()

        assert should_halt is True

    def test_should_halt_trading_already_halted(self, risk_manager):
        """Test returns True if already halted"""
        risk_manager.trading_halted = True

        should_halt = risk_manager.should_halt_trading()

        assert should_halt is True

    def test_halt_trading(self, risk_manager):
        """Test halting trading"""
        risk_manager.halt_trading()

        assert risk_manager.trading_halted is True

    def test_halt_trading_already_halted(self, risk_manager):
        """Test halting when already halted doesn't crash"""
        risk_manager.halt_trading()
        risk_manager.halt_trading()  # Second call

        assert risk_manager.trading_halted is True

    def test_resume_trading(self, risk_manager):
        """Test resuming trading"""
        risk_manager.trading_halted = True

        risk_manager.resume_trading()

        assert risk_manager.trading_halted is False

    def test_calculate_position_size_basic(self, risk_manager):
        """Test basic position size calculation"""
        # 10% of the declared equity, as notional, divided by the entry price.
        # Mirrors the manager's own Decimal arithmetic so it re-scales with
        # the declared account size.
        quantity = risk_manager.calculate_position_size(
            account_balance=EQUITY, entry_price=Decimal("50000.00")
        )

        expected = EQUITY * Decimal("0.1") / Decimal("50000.00")
        assert quantity == expected

    def test_calculate_position_size_with_stop_loss(self, risk_manager):
        """Test position size with stop loss risk calculation"""
        # Entry: $50,000, SL: $49,000 -> risk per unit $1,000.
        # Max risk: 10% of equity -> risk-based qty = 0.10*E/1000
        # Notional cap:             0.10*E/50000
        # The notional cap is always the smaller of the two, so the min is
        # the notional-capped quantity at any account scale.
        quantity = risk_manager.calculate_position_size(
            account_balance=EQUITY,
            entry_price=Decimal("50000.00"),
            stop_loss_price=Decimal("49000.00"),
        )

        assert quantity == EQUITY * Decimal("0.1") / Decimal("50000.00")

    def test_calculate_position_size_invalid_balance(self, risk_manager):
        """Test position size with invalid balance returns zero"""
        quantity = risk_manager.calculate_position_size(
            account_balance=Decimal("0"), entry_price=Decimal("50000.00")
        )

        assert quantity == Decimal("0")

    def test_calculate_position_size_invalid_price(self, risk_manager):
        """Test position size with invalid price returns zero"""
        quantity = risk_manager.calculate_position_size(
            account_balance=EQUITY, entry_price=Decimal("0")
        )

        assert quantity == Decimal("0")

    def test_calculate_stop_loss_long(self, risk_manager):
        """Test stop loss calculation for LONG position"""
        # LONG at $50,000 with 2% SL = $49,000
        stop_loss = risk_manager.calculate_stop_loss(
            entry_price=Decimal("50000.00"), side=PositionSide.LONG
        )

        expected = Decimal("50000.00") * Decimal("0.98")  # 1 - 0.02
        assert stop_loss == expected

    def test_calculate_stop_loss_short(self, risk_manager, mock_settings):
        """Test stop loss calculation for SHORT position"""
        # SHORT falls back to short_stop_loss_pct, not the LONG default
        # (2026-08-12: the field was declared 2026-01-19 and read by nothing).
        stop_loss = risk_manager.calculate_stop_loss(
            entry_price=Decimal("50000.00"), side=PositionSide.SHORT
        )

        expected = Decimal("50000.00") * (
            Decimal("1") + Decimal(str(mock_settings.short_stop_loss_pct / 100))
        )
        assert stop_loss == expected

    def test_calculate_stop_loss_custom_percent(self, risk_manager):
        """Test stop loss with custom percentage"""
        # LONG at $50,000 with 5% SL = $47,500
        stop_loss = risk_manager.calculate_stop_loss(
            entry_price=Decimal("50000.00"), side=PositionSide.LONG, stop_loss_pct=5.0
        )

        expected = Decimal("50000.00") * Decimal("0.95")  # 1 - 0.05
        assert stop_loss == expected

    def test_calculate_take_profit_long(self, risk_manager):
        """Test take profit calculation for LONG position"""
        # LONG at $50,000 with 4% TP = $52,000
        take_profit = risk_manager.calculate_take_profit(
            entry_price=Decimal("50000.00"), side=PositionSide.LONG
        )

        expected = Decimal("50000.00") * Decimal("1.04")  # 1 + 0.04
        assert take_profit == expected

    def test_calculate_take_profit_short(self, risk_manager):
        """Test take profit calculation for SHORT position"""
        # SHORT at $50,000 with 4% TP = $48,000
        take_profit = risk_manager.calculate_take_profit(
            entry_price=Decimal("50000.00"), side=PositionSide.SHORT
        )

        expected = Decimal("50000.00") * Decimal("0.96")  # 1 - 0.04
        assert take_profit == expected

    def test_calculate_take_profit_custom_percent(self, risk_manager):
        """Test take profit with custom percentage"""
        # LONG at $50,000 with 10% TP = $55,000
        take_profit = risk_manager.calculate_take_profit(
            entry_price=Decimal("50000.00"),
            side=PositionSide.LONG,
            take_profit_pct=10.0,
        )

        expected = Decimal("50000.00") * Decimal("1.10")  # 1 + 0.10
        assert take_profit == expected

    def test_check_position_limits_within_limits(self, risk_manager):
        """Test position limits check passes"""
        # Single position worth 50% of equity - within the 80% exposure limit
        open_position = Mock()
        open_position.entry_price = Decimal("50000.00")
        open_position.quantity = EQUITY * Decimal("0.5") / Decimal("50000.00")
        open_position.remaining_quantity = open_position.quantity
        open_position.status = Mock(value="OPEN")

        allowed, reason = risk_manager.check_position_limits(
            current_positions=[open_position], account_balance=EQUITY
        )

        assert allowed is True
        assert reason is None

    def test_check_position_limits_exceeds_exposure(self, risk_manager):
        """Test position limits check fails on exposure"""
        # Position worth 90% of equity - exceeds the 80% exposure limit
        open_position = Mock()
        open_position.entry_price = Decimal("50000.00")
        open_position.quantity = EQUITY * Decimal("0.9") / Decimal("50000.00")
        open_position.remaining_quantity = open_position.quantity
        open_position.status = Mock(value="OPEN")

        allowed, reason = risk_manager.check_position_limits(
            current_positions=[open_position], account_balance=EQUITY
        )

        assert allowed is False
        assert "Total exposure" in reason

    def test_check_position_limits_trading_halted(self, risk_manager):
        """Test position limits check fails when trading halted"""
        risk_manager.trading_halted = True

        allowed, reason = risk_manager.check_position_limits(
            current_positions=[], account_balance=EQUITY
        )

        assert allowed is False
        assert "Trading halted" in reason

    def test_should_close_position_no_exit(self, risk_manager):
        """Test should not close position when no SL/TP hit"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            stop_loss=Decimal("49000.00"),
            take_profit=Decimal("52000.00"),
            status=PositionStatus.OPEN,
        )

        # Current price between SL and TP
        should_close, reason = risk_manager.should_close_position(position, Decimal("50500.00"))

        assert should_close is False
        assert reason is None

    def test_should_close_position_stop_loss_hit(self, risk_manager):
        """Test should close position when stop loss hit"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            stop_loss=Decimal("49000.00"),
            take_profit=Decimal("52000.00"),
            status=PositionStatus.OPEN,
        )

        # Current price below stop loss
        should_close, reason = risk_manager.should_close_position(position, Decimal("48500.00"))

        assert should_close is True
        assert "Stop loss hit" in reason

    def test_should_close_position_take_profit_hit(self, risk_manager):
        """Test should close position when take profit hit"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            stop_loss=Decimal("49000.00"),
            take_profit=Decimal("52000.00"),
            status=PositionStatus.OPEN,
        )

        # Current price above take profit
        should_close, reason = risk_manager.should_close_position(position, Decimal("52500.00"))

        assert should_close is True
        assert "Take profit hit" in reason

    def test_validate_signal_valid_buy(self, risk_manager):
        """Test valid BUY signal passes validation"""
        is_valid, reason = risk_manager.validate_signal(
            signal_action=SignalAction.BUY, signal_confidence=0.85
        )

        assert is_valid is True
        assert reason is None

    def test_validate_signal_valid_sell(self, risk_manager):
        """Test valid SELL signal passes validation"""
        is_valid, reason = risk_manager.validate_signal(
            signal_action=SignalAction.SELL, signal_confidence=0.75
        )

        assert is_valid is True
        assert reason is None

    def test_validate_signal_hold_action(self, risk_manager):
        """Test HOLD signal fails validation"""
        is_valid, reason = risk_manager.validate_signal(
            signal_action=SignalAction.HOLD, signal_confidence=0.85
        )

        assert is_valid is False
        assert "not BUY/SELL" in reason

    def test_validate_signal_low_confidence(self, risk_manager):
        """Test signal with low confidence fails validation"""
        is_valid, reason = risk_manager.validate_signal(
            signal_action=SignalAction.BUY,
            signal_confidence=0.5,  # Below 0.7 threshold
        )

        assert is_valid is False
        assert "confidence" in reason
        assert "below threshold" in reason

    def test_validate_signal_trading_halted(self, risk_manager):
        """Test signal validation fails when trading halted"""
        risk_manager.trading_halted = True

        is_valid, reason = risk_manager.validate_signal(
            signal_action=SignalAction.BUY, signal_confidence=0.85
        )

        assert is_valid is False
        assert "Trading halted" in reason


# Test configuration
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
