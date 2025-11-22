"""
Unit Tests for Position Models
Tests Position model methods and edge cases
"""

import pytest
from decimal import Decimal
from uuid import uuid4

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))

from app.models.position import Position, PositionSide, PositionStatus


class TestPositionModel:
    """Test suite for Position model"""

    def test_pnl_percentage_normal_case(self):
        """Test P&L percentage calculation with normal values"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            unrealized_pnl=Decimal("500.00")
        )

        # P&L % = (unrealized_pnl / (entry_price * quantity)) * 100
        # = (500 / (50000 * 0.1)) * 100 = (500 / 5000) * 100 = 10%
        assert position.pnl_percentage == pytest.approx(10.0, rel=1e-2)

    def test_pnl_percentage_zero_entry_price(self):
        """Test P&L percentage with zero entry price (edge case)"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("0"),
            quantity=Decimal("0.1"),
            unrealized_pnl=Decimal("100.00")
        )

        # Should return 0.0 to avoid division by zero
        assert position.pnl_percentage == 0.0

    def test_total_value_with_current_price(self):
        """Test total value calculation with current price"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            current_price=Decimal("51000.00"),
            quantity=Decimal("0.1")
        )

        # total_value = current_price * quantity = 51000 * 0.1 = 5100
        assert position.total_value == Decimal("5100.00")

    def test_total_value_without_current_price(self):
        """Test total value calculation without current price (fallback to entry)"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            current_price=None,
            quantity=Decimal("0.1")
        )

        # Should use entry_price when current_price is None
        # total_value = entry_price * quantity = 50000 * 0.1 = 5000
        assert position.total_value == Decimal("5000.00")

    def test_update_pnl_long_position(self):
        """Test P&L update for LONG position"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        position.update_pnl(Decimal("52000.00"))

        # unrealized_pnl = (current_price - entry_price) * quantity
        # = (52000 - 50000) * 0.1 = 200
        assert position.current_price == Decimal("52000.00")
        assert position.unrealized_pnl == Decimal("200.00")

    def test_update_pnl_short_position(self):
        """Test P&L update for SHORT position"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.SHORT,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        position.update_pnl(Decimal("48000.00"))

        # unrealized_pnl = (entry_price - current_price) * quantity
        # = (50000 - 48000) * 0.1 = 200
        assert position.current_price == Decimal("48000.00")
        assert position.unrealized_pnl == Decimal("200.00")

    def test_check_stop_loss_long_position_hit(self):
        """Test stop loss check for LONG position - hit"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            stop_loss=Decimal("49000.00")
        )

        # Price drops to or below stop loss
        assert position.check_stop_loss(Decimal("49000.00")) is True
        assert position.check_stop_loss(Decimal("48000.00")) is True

    def test_check_stop_loss_long_position_not_hit(self):
        """Test stop loss check for LONG position - not hit"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            stop_loss=Decimal("49000.00")
        )

        # Price above stop loss
        assert position.check_stop_loss(Decimal("49500.00")) is False

    def test_check_stop_loss_short_position_hit(self):
        """Test stop loss check for SHORT position - hit"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.SHORT,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            stop_loss=Decimal("51000.00")
        )

        # Price rises to or above stop loss
        assert position.check_stop_loss(Decimal("51000.00")) is True
        assert position.check_stop_loss(Decimal("52000.00")) is True

    def test_check_stop_loss_no_stop_loss_set(self):
        """Test stop loss check when no stop loss is set"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            stop_loss=None
        )

        # Should return False when no stop loss is set
        assert position.check_stop_loss(Decimal("40000.00")) is False

    def test_check_take_profit_long_position_hit(self):
        """Test take profit check for LONG position - hit"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            take_profit=Decimal("55000.00")
        )

        # Price rises to or above take profit
        assert position.check_take_profit(Decimal("55000.00")) is True
        assert position.check_take_profit(Decimal("56000.00")) is True

    def test_check_take_profit_long_position_not_hit(self):
        """Test take profit check for LONG position - not hit"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            take_profit=Decimal("55000.00")
        )

        # Price below take profit
        assert position.check_take_profit(Decimal("54000.00")) is False

    def test_check_take_profit_short_position_hit(self):
        """Test take profit check for SHORT position - hit"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.SHORT,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            take_profit=Decimal("48000.00")
        )

        # Price drops to or below take profit
        assert position.check_take_profit(Decimal("48000.00")) is True
        assert position.check_take_profit(Decimal("47000.00")) is True

    def test_check_take_profit_no_take_profit_set(self):
        """Test take profit check when no take profit is set"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            take_profit=None
        )

        # Should return False when no take profit is set
        assert position.check_take_profit(Decimal("60000.00")) is False


# Test configuration
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
