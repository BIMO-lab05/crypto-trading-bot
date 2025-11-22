"""
Unit Tests for Order Models
Tests Order model properties
"""

import pytest
from decimal import Decimal

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))

from app.models.order import Order, OrderSide, OrderType, OrderStatus


class TestOrderModel:
    """Test suite for Order model"""

    def test_is_filled_property_true(self):
        """Test is_filled property when order is filled"""
        order = Order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal("0.1"),
            status=OrderStatus.FILLED
        )

        assert order.is_filled is True

    def test_is_filled_property_false(self):
        """Test is_filled property when order is not filled"""
        order = Order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal("0.1"),
            status=OrderStatus.PENDING
        )

        assert order.is_filled is False

    def test_is_pending_property_true(self):
        """Test is_pending property when order is pending"""
        order = Order(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            price=Decimal("50000.00"),
            status=OrderStatus.PENDING
        )

        assert order.is_pending is True

    def test_is_pending_property_false(self):
        """Test is_pending property when order is not pending"""
        order = Order(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            price=Decimal("50000.00"),
            status=OrderStatus.FILLED
        )

        assert order.is_pending is False

    def test_is_pending_cancelled_order(self):
        """Test is_pending property for cancelled order"""
        order = Order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal("0.1"),
            status=OrderStatus.CANCELLED
        )

        assert order.is_pending is False
        assert order.is_filled is False


# Test configuration
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
