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


class TestTrailingStop:
    """Test trailing stop functionality (Research-backed 2025-11-29)"""

    def test_update_price_extremes_initial(self):
        """Test initial price extreme tracking"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        position.update_price_extremes(Decimal("52000.00"))
        assert position.highest_price == Decimal("52000.00")
        assert position.lowest_price == Decimal("52000.00")

    def test_update_price_extremes_tracks_highest(self):
        """Test that highest price is tracked correctly"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        position.update_price_extremes(Decimal("52000.00"))
        position.update_price_extremes(Decimal("54000.00"))
        position.update_price_extremes(Decimal("53000.00"))

        assert position.highest_price == Decimal("54000.00")
        assert position.lowest_price == Decimal("52000.00")

    def test_update_trailing_stop_long_position(self):
        """Test trailing stop update for LONG position"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            trailing_stop_enabled=True
        )

        trail_distance = Decimal("1000.00")

        # Initial trailing stop
        updated = position.update_trailing_stop(Decimal("52000.00"), trail_distance)
        assert updated is True
        assert position.trailing_stop == Decimal("51000.00")  # 52000 - 1000

        # Price goes higher, trailing stop should move up
        updated = position.update_trailing_stop(Decimal("54000.00"), trail_distance)
        assert updated is True
        assert position.trailing_stop == Decimal("53000.00")  # 54000 - 1000

        # Price goes down, trailing stop should NOT move
        updated = position.update_trailing_stop(Decimal("53000.00"), trail_distance)
        assert updated is False
        assert position.trailing_stop == Decimal("53000.00")  # Unchanged

    def test_update_trailing_stop_short_position(self):
        """Test trailing stop update for SHORT position"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.SHORT,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            trailing_stop_enabled=True
        )

        trail_distance = Decimal("1000.00")

        # Initial trailing stop
        updated = position.update_trailing_stop(Decimal("48000.00"), trail_distance)
        assert updated is True
        assert position.trailing_stop == Decimal("49000.00")  # 48000 + 1000

        # Price goes lower, trailing stop should move down
        updated = position.update_trailing_stop(Decimal("46000.00"), trail_distance)
        assert updated is True
        assert position.trailing_stop == Decimal("47000.00")  # 46000 + 1000

        # Price goes up, trailing stop should NOT move
        updated = position.update_trailing_stop(Decimal("48000.00"), trail_distance)
        assert updated is False
        assert position.trailing_stop == Decimal("47000.00")  # Unchanged

    def test_update_trailing_stop_disabled(self):
        """Test trailing stop does nothing when disabled"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            trailing_stop_enabled=False
        )

        updated = position.update_trailing_stop(Decimal("52000.00"), Decimal("1000.00"))
        assert updated is False
        assert position.trailing_stop is None

    def test_check_trailing_stop_long_hit(self):
        """Test trailing stop hit for LONG position"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            trailing_stop=Decimal("51000.00"),
            trailing_stop_enabled=True
        )

        assert position.check_trailing_stop(Decimal("51000.00")) is True
        assert position.check_trailing_stop(Decimal("50000.00")) is True
        assert position.check_trailing_stop(Decimal("52000.00")) is False

    def test_check_trailing_stop_short_hit(self):
        """Test trailing stop hit for SHORT position"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.SHORT,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            trailing_stop=Decimal("49000.00"),
            trailing_stop_enabled=True
        )

        assert position.check_trailing_stop(Decimal("49000.00")) is True
        assert position.check_trailing_stop(Decimal("50000.00")) is True
        assert position.check_trailing_stop(Decimal("48000.00")) is False

    def test_get_effective_stop_loss_trailing_better(self):
        """Test effective stop loss when trailing is more favorable"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            stop_loss=Decimal("48000.00"),
            trailing_stop=Decimal("51000.00"),  # Better than original
            trailing_stop_enabled=True
        )

        # For LONG, higher stop is better
        assert position.get_effective_stop_loss() == Decimal("51000.00")

    def test_get_effective_stop_loss_original_better(self):
        """Test effective stop loss when original is more favorable"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            stop_loss=Decimal("48000.00"),
            trailing_stop=Decimal("47000.00"),  # Worse than original
            trailing_stop_enabled=True
        )

        # For LONG, higher stop is better
        assert position.get_effective_stop_loss() == Decimal("48000.00")


class TestPartialExit:
    """Test partial exit functionality (Research-backed 2025-11-29)"""

    def test_check_partial_exit_tp1_long(self):
        """Test TP1 partial exit for LONG position"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.3"),
            take_profit_1=Decimal("51000.00"),
            take_profit_2=Decimal("52000.00"),
            take_profit_3=Decimal("53000.00")
        )

        exit_info = position.check_partial_exit(Decimal("51000.00"))
        assert exit_info is not None
        assert exit_info["level"] == "TP1"
        assert exit_info["exit_percentage"] == 33.0
        assert exit_info["enable_trailing"] is True
        # 0.3 * 0.33 = 0.099
        assert exit_info["exit_quantity"] == Decimal("0.099")

    def test_check_partial_exit_tp2_long(self):
        """Test TP2 partial exit after TP1 hit"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.3"),
            remaining_quantity=Decimal("0.201"),  # After TP1
            take_profit_1=Decimal("51000.00"),
            take_profit_2=Decimal("52000.00"),
            take_profit_3=Decimal("53000.00"),
            tp1_hit=True
        )

        exit_info = position.check_partial_exit(Decimal("52000.00"))
        assert exit_info is not None
        assert exit_info["level"] == "TP2"
        assert exit_info["enable_trailing"] is False

    def test_check_partial_exit_short_position(self):
        """Test partial exit for SHORT position (price goes down)"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.SHORT,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.3"),
            take_profit_1=Decimal("49000.00"),  # Price goes DOWN for SHORT
            take_profit_2=Decimal("48000.00"),
            take_profit_3=Decimal("47000.00")
        )

        exit_info = position.check_partial_exit(Decimal("49000.00"))
        assert exit_info is not None
        assert exit_info["level"] == "TP1"

    def test_check_partial_exit_no_tp_set(self):
        """Test no partial exit when TP levels not set"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.3")
        )

        exit_info = position.check_partial_exit(Decimal("60000.00"))
        assert exit_info is None

    def test_apply_partial_exit_tp1(self):
        """Test applying TP1 partial exit"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.3")
        )

        exit_info = {
            "level": "TP1",
            "exit_quantity": Decimal("0.099"),
            "remaining_quantity": Decimal("0.201"),
            "enable_trailing": True
        }

        position.apply_partial_exit(exit_info, Decimal("100.00"))

        assert position.remaining_quantity == Decimal("0.201")
        assert position.realized_pnl == Decimal("100.00")
        assert position.tp1_hit is True
        assert position.trailing_stop_enabled is True
        assert position.status == PositionStatus.OPEN

    def test_apply_partial_exit_tp3_closes_position(self):
        """Test that TP3 closes the position"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.3"),
            remaining_quantity=Decimal("0.102"),
            tp1_hit=True,
            tp2_hit=True
        )

        exit_info = {
            "level": "TP3",
            "exit_quantity": Decimal("0.102"),
            "remaining_quantity": Decimal("0"),
            "enable_trailing": False
        }

        position.apply_partial_exit(exit_info, Decimal("200.00"))

        assert position.remaining_quantity == Decimal("0")
        assert position.tp3_hit is True
        assert position.status == PositionStatus.CLOSED
        assert position.closed_at is not None


class TestMoneyCalculations:
    """Test critical money calculations for precision and edge cases"""

    def test_pnl_calculation_precision_long(self):
        """Test P&L calculation precision for LONG position"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.12345678"),
            quantity=Decimal("0.12345678")
        )

        position.update_pnl(Decimal("52000.87654321"))

        # Expected: (52000.87654321 - 50000.12345678) * 0.12345678
        expected = (Decimal("52000.87654321") - Decimal("50000.12345678")) * Decimal("0.12345678")
        assert position.unrealized_pnl == expected

    def test_pnl_calculation_precision_short(self):
        """Test P&L calculation precision for SHORT position"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.SHORT,
            entry_price=Decimal("50000.12345678"),
            quantity=Decimal("0.12345678")
        )

        position.update_pnl(Decimal("48000.87654321"))

        # Expected: (50000.12345678 - 48000.87654321) * 0.12345678
        expected = (Decimal("50000.12345678") - Decimal("48000.87654321")) * Decimal("0.12345678")
        assert position.unrealized_pnl == expected

    def test_loss_scenario_long(self):
        """Test P&L is negative when LONG position loses"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        position.update_pnl(Decimal("45000.00"))

        # LONG loses when price goes down
        assert position.unrealized_pnl == Decimal("-500.00")
        assert position.pnl_percentage == pytest.approx(-10.0, rel=1e-2)

    def test_loss_scenario_short(self):
        """Test P&L is negative when SHORT position loses"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.SHORT,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        position.update_pnl(Decimal("55000.00"))

        # SHORT loses when price goes up
        assert position.unrealized_pnl == Decimal("-500.00")

    def test_breakeven_pnl(self):
        """Test P&L is zero at entry price"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )

        position.update_pnl(Decimal("50000.00"))

        assert position.unrealized_pnl == Decimal("0")
        assert position.pnl_percentage == 0.0

    def test_large_position_pnl(self):
        """Test P&L calculation with large numbers"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("100.0")  # $5 million position
        )

        position.update_pnl(Decimal("51000.00"))

        # 2% gain on $5M = $100K
        assert position.unrealized_pnl == Decimal("100000.00")

    def test_small_quantity_pnl(self):
        """Test P&L calculation with very small quantities"""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.00001")  # Very small position
        )

        position.update_pnl(Decimal("60000.00"))

        # 20% gain on 0.00001 BTC
        expected = Decimal("10000.00") * Decimal("0.00001")
        assert position.unrealized_pnl == expected


# Test configuration
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
