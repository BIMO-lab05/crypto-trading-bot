"""
Unit Tests for Asset Model Money Handling
Tests critical financial calculations in asset valuation

Coverage Target: asset.py - Valuation, Cost Basis, P&L Calculations
Priority: CRITICAL - These calculations directly impact portfolio value reporting
"""

import pytest
from decimal import Decimal

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from app.models.asset import Asset
from app.models.enums import AssetType


class TestAssetValuation:
    """Test asset valuation calculations"""

    def test_update_valuation_basic(self):
        """Test basic valuation update"""
        asset = Asset(
            symbol="BTC",
            name="Bitcoin",
            quantity=Decimal("0.5"),
            average_entry_price=Decimal("50000.00"),
            total_cost=Decimal("25000.00")
        )

        asset.update_valuation(Decimal("60000.00"))

        assert asset.current_price == Decimal("60000.00")
        assert asset.current_value == Decimal("30000.00")  # 0.5 * 60000
        assert asset.unrealized_pnl == Decimal("5000.00")  # 30000 - 25000
        assert asset.unrealized_pnl_pct == Decimal("20")  # 5000/25000 * 100

    def test_update_valuation_with_loss(self):
        """Test valuation update when asset is at a loss"""
        asset = Asset(
            symbol="BTC",
            name="Bitcoin",
            quantity=Decimal("0.5"),
            average_entry_price=Decimal("50000.00"),
            total_cost=Decimal("25000.00")
        )

        asset.update_valuation(Decimal("40000.00"))

        assert asset.current_value == Decimal("20000.00")  # 0.5 * 40000
        assert asset.unrealized_pnl == Decimal("-5000.00")  # 20000 - 25000
        assert asset.unrealized_pnl_pct == Decimal("-20")  # -5000/25000 * 100

    def test_update_valuation_zero_cost(self):
        """Test valuation update when total cost is zero (edge case)"""
        asset = Asset(
            symbol="BTC",
            name="Bitcoin",
            quantity=Decimal("0"),
            average_entry_price=Decimal("0"),
            total_cost=Decimal("0")
        )

        asset.update_valuation(Decimal("50000.00"))

        assert asset.current_value == Decimal("0")
        assert asset.unrealized_pnl == Decimal("0")
        assert asset.unrealized_pnl_pct == Decimal("0")

    def test_update_valuation_precision(self):
        """Test valuation with high precision numbers"""
        asset = Asset(
            symbol="BTC",
            name="Bitcoin",
            quantity=Decimal("0.12345678"),
            average_entry_price=Decimal("50000.12345678"),
            total_cost=Decimal("6172.54012888877284")
        )

        asset.update_valuation(Decimal("52000.87654321"))

        expected_value = Decimal("0.12345678") * Decimal("52000.87654321")
        assert asset.current_value == expected_value


class TestAddQuantity:
    """Test add_quantity (buy) functionality with cost basis averaging"""

    def test_add_quantity_initial_purchase(self):
        """Test adding quantity to empty position"""
        asset = Asset(
            symbol="BTC",
            name="Bitcoin",
            quantity=Decimal("0"),
            average_entry_price=Decimal("0"),
            total_cost=Decimal("0")
        )

        asset.add_quantity(Decimal("0.1"), Decimal("50000.00"))

        assert asset.quantity == Decimal("0.1")
        assert asset.average_entry_price == Decimal("50000.00")
        assert asset.total_cost == Decimal("5000.00")

    def test_add_quantity_average_cost_calculation(self):
        """Test average cost basis calculation when adding to position"""
        asset = Asset(
            symbol="BTC",
            name="Bitcoin",
            quantity=Decimal("0.1"),
            average_entry_price=Decimal("50000.00"),
            total_cost=Decimal("5000.00")
        )

        # Buy 0.1 more at $60,000
        asset.add_quantity(Decimal("0.1"), Decimal("60000.00"))

        # New average = (0.1 * 50000 + 0.1 * 60000) / 0.2 = 55000
        assert asset.quantity == Decimal("0.2")
        assert asset.average_entry_price == Decimal("55000.00")
        assert asset.total_cost == Decimal("11000.00")

    def test_add_quantity_weighted_average(self):
        """Test weighted average cost with different quantities"""
        asset = Asset(
            symbol="BTC",
            name="Bitcoin",
            quantity=Decimal("0.3"),  # Already own 0.3 BTC
            average_entry_price=Decimal("50000.00"),  # Bought at $50k
            total_cost=Decimal("15000.00")  # 0.3 * 50000
        )

        # Buy 0.1 more at $70,000
        asset.add_quantity(Decimal("0.1"), Decimal("70000.00"))

        # New average = (0.3 * 50000 + 0.1 * 70000) / 0.4 = (15000 + 7000) / 0.4 = 55000
        assert asset.quantity == Decimal("0.4")
        assert asset.average_entry_price == Decimal("55000.00")
        assert asset.total_cost == Decimal("22000.00")

    def test_add_quantity_updates_valuation(self):
        """Test that add_quantity also updates current valuation"""
        asset = Asset(
            symbol="BTC",
            name="Bitcoin",
            quantity=Decimal("0.1"),
            average_entry_price=Decimal("50000.00"),
            total_cost=Decimal("5000.00")
        )

        # Buy at current price of $55,000
        asset.add_quantity(Decimal("0.1"), Decimal("55000.00"))

        # Current value should be updated to new quantity * buy price
        assert asset.current_price == Decimal("55000.00")
        assert asset.current_value == Decimal("11000.00")  # 0.2 * 55000

    def test_add_quantity_precision(self):
        """Test cost averaging with high precision numbers"""
        asset = Asset(
            symbol="BTC",
            name="Bitcoin",
            quantity=Decimal("0.12345678"),
            average_entry_price=Decimal("50000.12345678"),
            total_cost=Decimal("6172.54012888877284")
        )

        # Add more with precise numbers
        asset.add_quantity(Decimal("0.87654322"), Decimal("60000.87654321"))

        # Total quantity should be exactly 1
        assert asset.quantity == Decimal("1.00000000")
        # Verify total cost calculation
        expected_new_cost = Decimal("0.87654322") * Decimal("60000.87654321")
        expected_total = Decimal("6172.54012888877284") + expected_new_cost
        # Average should be total cost / quantity
        assert asset.average_entry_price == expected_total / Decimal("1.00000000")


class TestReduceQuantity:
    """Test reduce_quantity (sell) functionality with realized P&L"""

    def test_reduce_quantity_basic_profit(self):
        """Test selling for a profit"""
        asset = Asset(
            symbol="BTC",
            name="Bitcoin",
            quantity=Decimal("0.2"),
            average_entry_price=Decimal("50000.00"),
            total_cost=Decimal("10000.00")
        )

        # Sell 0.1 at $60,000
        realized_pnl = asset.reduce_quantity(Decimal("0.1"), Decimal("60000.00"))

        # Realized P&L = sale proceeds - cost basis
        # = (0.1 * 60000) - (0.1 * 50000) = 6000 - 5000 = 1000
        assert realized_pnl == Decimal("1000.00")
        assert asset.quantity == Decimal("0.1")
        assert asset.total_cost == Decimal("5000.00")

    def test_reduce_quantity_basic_loss(self):
        """Test selling for a loss"""
        asset = Asset(
            symbol="BTC",
            name="Bitcoin",
            quantity=Decimal("0.2"),
            average_entry_price=Decimal("50000.00"),
            total_cost=Decimal("10000.00")
        )

        # Sell 0.1 at $40,000 (loss)
        realized_pnl = asset.reduce_quantity(Decimal("0.1"), Decimal("40000.00"))

        # Realized P&L = (0.1 * 40000) - (0.1 * 50000) = 4000 - 5000 = -1000
        assert realized_pnl == Decimal("-1000.00")
        assert asset.quantity == Decimal("0.1")

    def test_reduce_quantity_sell_all(self):
        """Test selling entire position"""
        asset = Asset(
            symbol="BTC",
            name="Bitcoin",
            quantity=Decimal("0.5"),
            average_entry_price=Decimal("50000.00"),
            total_cost=Decimal("25000.00")
        )

        realized_pnl = asset.reduce_quantity(Decimal("0.5"), Decimal("55000.00"))

        # Full position sold: (0.5 * 55000) - (0.5 * 50000) = 27500 - 25000 = 2500
        assert realized_pnl == Decimal("2500.00")
        assert asset.quantity == Decimal("0")
        assert asset.total_cost == Decimal("0")

    def test_reduce_quantity_insufficient_balance(self):
        """Test error when trying to sell more than owned"""
        asset = Asset(
            symbol="BTC",
            name="Bitcoin",
            quantity=Decimal("0.1"),
            average_entry_price=Decimal("50000.00"),
            total_cost=Decimal("5000.00")
        )

        with pytest.raises(ValueError) as exc_info:
            asset.reduce_quantity(Decimal("0.2"), Decimal("50000.00"))

        assert "Cannot sell" in str(exc_info.value)
        assert "0.2" in str(exc_info.value)
        assert "0.1" in str(exc_info.value)

    def test_reduce_quantity_breakeven(self):
        """Test selling at breakeven (no profit or loss)"""
        asset = Asset(
            symbol="BTC",
            name="Bitcoin",
            quantity=Decimal("0.2"),
            average_entry_price=Decimal("50000.00"),
            total_cost=Decimal("10000.00")
        )

        realized_pnl = asset.reduce_quantity(Decimal("0.1"), Decimal("50000.00"))

        assert realized_pnl == Decimal("0")

    def test_reduce_quantity_precision(self):
        """Test realized P&L calculation with high precision"""
        asset = Asset(
            symbol="BTC",
            name="Bitcoin",
            quantity=Decimal("0.12345678"),
            average_entry_price=Decimal("50000.12345678"),
            total_cost=Decimal("6172.54012888877284")
        )

        # Sell half
        sell_quantity = Decimal("0.06172839")
        sell_price = Decimal("55000.87654321")

        realized_pnl = asset.reduce_quantity(sell_quantity, sell_price)

        # Expected: (sell_qty * sell_price) - (sell_qty * avg_entry)
        expected_proceeds = sell_quantity * sell_price
        expected_cost = sell_quantity * Decimal("50000.12345678")
        expected_pnl = expected_proceeds - expected_cost

        assert realized_pnl == expected_pnl

    def test_reduce_quantity_updates_valuation(self):
        """Test that reduce_quantity also updates current valuation"""
        asset = Asset(
            symbol="BTC",
            name="Bitcoin",
            quantity=Decimal("0.2"),
            average_entry_price=Decimal("50000.00"),
            total_cost=Decimal("10000.00")
        )

        asset.reduce_quantity(Decimal("0.1"), Decimal("55000.00"))

        assert asset.current_price == Decimal("55000.00")
        assert asset.current_value == Decimal("5500.00")  # 0.1 * 55000


class TestMultipleTransactions:
    """Test sequences of buys and sells"""

    def test_buy_sell_buy_sequence(self):
        """Test buying, selling, then buying again"""
        asset = Asset(
            symbol="BTC",
            name="Bitcoin"
        )

        # Buy 0.2 at $50,000
        asset.add_quantity(Decimal("0.2"), Decimal("50000.00"))
        assert asset.quantity == Decimal("0.2")
        assert asset.average_entry_price == Decimal("50000.00")

        # Sell 0.1 at $55,000 (profit)
        pnl1 = asset.reduce_quantity(Decimal("0.1"), Decimal("55000.00"))
        assert pnl1 == Decimal("500.00")  # (55k-50k) * 0.1
        assert asset.quantity == Decimal("0.1")
        assert asset.average_entry_price == Decimal("50000.00")  # Unchanged

        # Buy 0.1 at $60,000
        asset.add_quantity(Decimal("0.1"), Decimal("60000.00"))
        assert asset.quantity == Decimal("0.2")
        # New average: (0.1 * 50000 + 0.1 * 60000) / 0.2 = 55000
        assert asset.average_entry_price == Decimal("55000.00")

    def test_dollar_cost_averaging(self):
        """Test dollar cost averaging over multiple purchases"""
        asset = Asset(
            symbol="BTC",
            name="Bitcoin"
        )

        # DCA: Buy same amount at different prices
        prices = [
            Decimal("50000.00"),
            Decimal("45000.00"),
            Decimal("55000.00"),
            Decimal("48000.00")
        ]
        quantity_per_buy = Decimal("0.1")

        for price in prices:
            asset.add_quantity(quantity_per_buy, price)

        # Total quantity: 0.4 BTC
        assert asset.quantity == Decimal("0.4")

        # Average price: (50k + 45k + 55k + 48k) / 4 = 49500
        expected_avg = sum(prices) / 4
        assert asset.average_entry_price == expected_avg

        # Total cost: 0.4 * 49500 = 19800
        assert asset.total_cost == Decimal("0.4") * expected_avg


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_very_small_quantity(self):
        """Test with very small quantities (satoshis)"""
        asset = Asset(
            symbol="BTC",
            name="Bitcoin"
        )

        # Buy 1 satoshi worth at $100k
        asset.add_quantity(Decimal("0.00000001"), Decimal("100000.00"))

        assert asset.quantity == Decimal("0.00000001")
        assert asset.total_cost == Decimal("0.001")  # 0.00000001 * 100000

    def test_very_large_quantity(self):
        """Test with very large quantities"""
        asset = Asset(
            symbol="BTC",
            name="Bitcoin"
        )

        # Buy 1000 BTC at $50k = $50M position
        asset.add_quantity(Decimal("1000"), Decimal("50000.00"))
        asset.update_valuation(Decimal("51000.00"))

        assert asset.quantity == Decimal("1000")
        assert asset.current_value == Decimal("51000000.00")
        assert asset.unrealized_pnl == Decimal("1000000.00")  # $1M profit

    def test_zero_quantity_operations(self):
        """Test operations with zero quantity"""
        asset = Asset(
            symbol="BTC",
            name="Bitcoin",
            quantity=Decimal("0"),
            total_cost=Decimal("0")
        )

        # Adding zero should work
        asset.add_quantity(Decimal("0"), Decimal("50000.00"))
        assert asset.quantity == Decimal("0")

    def test_allocation_tracking(self):
        """Test allocation percentage tracking"""
        asset = Asset(
            symbol="BTC",
            name="Bitcoin",
            quantity=Decimal("0.1"),
            average_entry_price=Decimal("50000.00"),
            total_cost=Decimal("5000.00"),
            target_allocation_pct=Decimal("60.00"),
            current_allocation_pct=Decimal("45.00")
        )

        assert asset.target_allocation_pct == Decimal("60.00")
        assert asset.current_allocation_pct == Decimal("45.00")


class TestRealWorldScenarios:
    """Test real-world trading scenarios"""

    def test_crypto_swing_trade(self):
        """Simulate a swing trade with multiple entries and one exit"""
        asset = Asset(symbol="ETH", name="Ethereum")

        # Scale in: Buy at dips
        asset.add_quantity(Decimal("1.0"), Decimal("3000.00"))  # Initial
        asset.add_quantity(Decimal("1.0"), Decimal("2800.00"))  # Dip buy 1
        asset.add_quantity(Decimal("1.0"), Decimal("2600.00"))  # Dip buy 2

        # Average: (3000 + 2800 + 2600) / 3 = 2800
        assert asset.quantity == Decimal("3.0")
        assert asset.average_entry_price == Decimal("2800.00")
        assert asset.total_cost == Decimal("8400.00")

        # Price recovers to $3500, sell all
        realized_pnl = asset.reduce_quantity(Decimal("3.0"), Decimal("3500.00"))

        # Profit: (3.0 * 3500) - 8400 = 10500 - 8400 = 2100
        assert realized_pnl == Decimal("2100.00")
        assert asset.quantity == Decimal("0")

    def test_partial_profit_taking(self):
        """Test taking partial profits while holding core position"""
        asset = Asset(symbol="BTC", name="Bitcoin")

        # Buy 1 BTC at $50k
        asset.add_quantity(Decimal("1.0"), Decimal("50000.00"))

        # Price goes to $60k, sell 50% (take profit)
        pnl1 = asset.reduce_quantity(Decimal("0.5"), Decimal("60000.00"))
        assert pnl1 == Decimal("5000.00")  # 50% of 20% gain

        # Price goes to $70k, sell remaining
        pnl2 = asset.reduce_quantity(Decimal("0.5"), Decimal("70000.00"))
        assert pnl2 == Decimal("10000.00")  # 50% of 40% gain

        # Total realized: $15k profit on $50k investment = 30%
        total_pnl = pnl1 + pnl2
        assert total_pnl == Decimal("15000.00")


# Test configuration
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
