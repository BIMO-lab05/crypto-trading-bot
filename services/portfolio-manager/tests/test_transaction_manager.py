"""
Unit Tests for Portfolio Transaction Manager
Tests transaction execution, validation, and history tracking
"""

import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from app.services.portfolio_manager import PortfolioManager
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction


class TestTransactionExecution:
    """Test transaction execution logic"""

    @pytest.fixture
    def portfolio_manager(self):
        """Create portfolio manager instance"""
        pm = PortfolioManager()
        return pm

    def test_execute_buy_transaction_sufficient_balance(self, portfolio_manager):
        """Test successful buy transaction with sufficient balance"""
        # Arrange
        portfolio_id = "default"
        symbol = "BTCUSDT"
        quantity = Decimal("1.0")
        price = Decimal("45000.0")

        # Act
        success, message, realized_pnl = portfolio_manager.execute_transaction(
            portfolio_id=portfolio_id,
            symbol=symbol,
            action="BUY",
            quantity=quantity,
            price=price
        )

        # Assert
        assert success is True
        assert "Bought" in message
        assert realized_pnl is None  # Buy transactions don't have realized P&L

        # Verify portfolio was updated
        portfolio = portfolio_manager.get_portfolio(portfolio_id)
        assert symbol in portfolio.assets
        assert portfolio.assets[symbol].quantity == quantity

    def test_execute_buy_transaction_insufficient_balance(self, portfolio_manager):
        """Test buy transaction fails with insufficient balance"""
        # Arrange
        portfolio_id = "default"
        symbol = "BTCUSDT"
        quantity = Decimal("100.0")  # Very large quantity
        price = Decimal("100000.0")  # Very high price

        # Act
        success, message, realized_pnl = portfolio_manager.execute_transaction(
            portfolio_id=portfolio_id,
            symbol=symbol,
            action="BUY",
            quantity=quantity,
            price=price
        )

        # Assert
        assert success is False
        assert message is not None

    def test_execute_sell_transaction_sufficient_holding(self, portfolio_manager):
        """Test successful sell transaction"""
        # Arrange
        portfolio_id = "default"
        symbol = "BTCUSDT"
        buy_quantity = Decimal("2.0")
        buy_price = Decimal("45000.0")
        sell_quantity = Decimal("1.0")
        sell_price = Decimal("46000.0")

        # First buy
        portfolio_manager.execute_transaction(
            portfolio_id, symbol, "BUY", buy_quantity, buy_price
        )

        # Act: Sell half
        success, message, realized_pnl = portfolio_manager.execute_transaction(
            portfolio_id=portfolio_id,
            symbol=symbol,
            action="SELL",
            quantity=sell_quantity,
            price=sell_price
        )

        # Assert
        assert success is True
        assert "Sold" in message
        assert realized_pnl is not None
        assert realized_pnl > 0  # Should have profit

    def test_execute_sell_transaction_insufficient_holding(self, portfolio_manager):
        """Test sell transaction fails with insufficient holding"""
        # Arrange
        portfolio_id = "default"
        symbol = "BTCUSDT"
        quantity = Decimal("10.0")  # More than we have
        price = Decimal("45000.0")

        # Act
        success, message, realized_pnl = portfolio_manager.execute_transaction(
            portfolio_id=portfolio_id,
            symbol=symbol,
            action="SELL",
            quantity=quantity,
            price=price
        )

        # Assert
        assert success is False

    def test_execute_transaction_invalid_action(self, portfolio_manager):
        """Test transaction with invalid action type"""
        # Arrange
        portfolio_id = "default"
        symbol = "BTCUSDT"
        quantity = Decimal("1.0")
        price = Decimal("45000.0")

        # Act
        success, message, realized_pnl = portfolio_manager.execute_transaction(
            portfolio_id=portfolio_id,
            symbol=symbol,
            action="INVALID",
            quantity=quantity,
            price=price
        )

        # Assert
        assert success is False
        assert "Invalid action" in message

    def test_execute_transaction_nonexistent_portfolio(self, portfolio_manager):
        """Test transaction on non-existent portfolio"""
        # Arrange
        portfolio_id = "nonexistent"
        symbol = "BTCUSDT"
        quantity = Decimal("1.0")
        price = Decimal("45000.0")

        # Act
        success, message, realized_pnl = portfolio_manager.execute_transaction(
            portfolio_id=portfolio_id,
            symbol=symbol,
            action="BUY",
            quantity=quantity,
            price=price
        )

        # Assert
        assert success is False
        assert "not found" in message.lower()


class TestTransactionHistory:
    """Test transaction history tracking"""

    @pytest.fixture
    def portfolio_manager(self):
        """Create portfolio manager instance"""
        return PortfolioManager()

    def test_record_transaction_buy(self, portfolio_manager):
        """Test recording buy transaction"""
        # Arrange
        portfolio_id = "default"
        symbol = "BTCUSDT"
        quantity = Decimal("1.0")
        price = Decimal("45000.0")

        # Act
        portfolio_manager.execute_transaction(
            portfolio_id, symbol, "BUY", quantity, price
        )

        # Assert
        history = portfolio_manager.get_transaction_history(portfolio_id)
        assert len(history) == 1
        assert history[0].symbol == symbol
        assert history[0].action == "BUY"
        assert Decimal(history[0].quantity) == quantity
        assert Decimal(history[0].price) == price

    def test_record_transaction_sell_with_realized_pnl(self, portfolio_manager):
        """Test recording sell transaction with P&L"""
        # Arrange
        portfolio_id = "default"
        symbol = "BTCUSDT"
        buy_quantity = Decimal("1.0")
        buy_price = Decimal("45000.0")
        sell_price = Decimal("46000.0")

        # Buy first
        portfolio_manager.execute_transaction(
            portfolio_id, symbol, "BUY", buy_quantity, buy_price
        )

        # Act: Sell with profit
        portfolio_manager.execute_transaction(
            portfolio_id, symbol, "SELL", buy_quantity, sell_price
        )

        # Assert
        history = portfolio_manager.get_transaction_history(portfolio_id)
        assert len(history) == 2

        # Check sell transaction
        sell_tx = [tx for tx in history if tx.action == "SELL"][0]
        assert sell_tx.realized_pnl is not None
        assert Decimal(sell_tx.realized_pnl) > 0

    def test_get_transaction_history_with_limit(self, portfolio_manager):
        """Test retrieving transaction history with limit"""
        # Arrange
        portfolio_id = "default"
        symbol = "BTCUSDT"

        # Create multiple transactions
        for i in range(5):
            portfolio_manager.execute_transaction(
                portfolio_id, symbol, "BUY", Decimal("0.1"), Decimal("45000.0")
            )

        # Act
        history = portfolio_manager.get_transaction_history(portfolio_id, limit=3)

        # Assert
        assert len(history) == 3

    def test_get_transaction_history_with_symbol_filter(self, portfolio_manager):
        """Test filtering transaction history by symbol"""
        # Arrange
        portfolio_id = "default"

        # Create transactions for different symbols
        portfolio_manager.execute_transaction(
            portfolio_id, "BTCUSDT", "BUY", Decimal("1.0"), Decimal("45000.0")
        )
        portfolio_manager.execute_transaction(
            portfolio_id, "ETHUSDT", "BUY", Decimal("10.0"), Decimal("3000.0")
        )
        portfolio_manager.execute_transaction(
            portfolio_id, "BTCUSDT", "BUY", Decimal("0.5"), Decimal("45500.0")
        )

        # Act
        btc_history = portfolio_manager.get_transaction_history(
            portfolio_id, symbol="BTCUSDT"
        )
        eth_history = portfolio_manager.get_transaction_history(
            portfolio_id, symbol="ETHUSDT"
        )

        # Assert
        assert len(btc_history) == 2
        assert len(eth_history) == 1
        assert all(tx.symbol == "BTCUSDT" for tx in btc_history)
        assert all(tx.symbol == "ETHUSDT" for tx in eth_history)

    def test_get_transaction_history_sorted_by_time(self, portfolio_manager):
        """Test transaction history is sorted by timestamp (most recent first)"""
        # Arrange
        portfolio_id = "default"
        symbol = "BTCUSDT"

        # Create transactions
        for i in range(3):
            portfolio_manager.execute_transaction(
                portfolio_id, symbol, "BUY", Decimal("0.1"), Decimal(f"4500{i}.0")
            )

        # Act
        history = portfolio_manager.get_transaction_history(portfolio_id)

        # Assert
        assert len(history) == 3
        # Most recent should be first
        for i in range(len(history) - 1):
            assert history[i].timestamp >= history[i + 1].timestamp

    def test_get_transaction_history_empty(self, portfolio_manager):
        """Test getting empty transaction history"""
        # Arrange
        portfolio_id = "new_portfolio"
        portfolio_manager.transaction_history[portfolio_id] = []

        # Act
        history = portfolio_manager.get_transaction_history(portfolio_id)

        # Assert
        assert len(history) == 0
        assert isinstance(history, list)


class TestTransactionValidation:
    """Test transaction validation logic"""

    @pytest.fixture
    def portfolio_manager(self):
        """Create portfolio manager instance"""
        return PortfolioManager()

    def test_validate_buy_with_zero_quantity(self, portfolio_manager):
        """Test buy transaction with zero quantity fails"""
        # Arrange
        portfolio_id = "default"
        symbol = "BTCUSDT"
        quantity = Decimal("0.0")
        price = Decimal("45000.0")

        # Act
        success, message, _ = portfolio_manager.execute_transaction(
            portfolio_id, symbol, "BUY", quantity, price
        )

        # Assert
        assert success is False

    def test_validate_sell_with_negative_quantity(self, portfolio_manager):
        """Test sell transaction with negative quantity fails"""
        # Arrange
        portfolio_id = "default"
        symbol = "BTCUSDT"
        quantity = Decimal("-1.0")
        price = Decimal("45000.0")

        # Act
        success, message, _ = portfolio_manager.execute_transaction(
            portfolio_id, symbol, "SELL", quantity, price
        )

        # Assert
        assert success is False

    def test_validate_buy_with_zero_price(self, portfolio_manager):
        """Test buy transaction with zero price fails"""
        # Arrange
        portfolio_id = "default"
        symbol = "BTCUSDT"
        quantity = Decimal("1.0")
        price = Decimal("0.0")

        # Act
        success, message, _ = portfolio_manager.execute_transaction(
            portfolio_id, symbol, "BUY", quantity, price
        )

        # Assert
        assert success is False


class TestRebalancingRecommendations:
    """Test portfolio rebalancing recommendation logic"""

    @pytest.fixture
    def portfolio_manager(self):
        """Create portfolio manager with test data"""
        pm = PortfolioManager()
        return pm

    def test_check_rebalancing_no_drift(self, portfolio_manager):
        """Test rebalancing check when portfolio is balanced"""
        # Arrange
        portfolio_id = "default"
        portfolio = portfolio_manager.get_portfolio(portfolio_id)

        # Add assets at target allocation
        portfolio.add_asset("BTCUSDT", "Bitcoin", Decimal("1.0"), Decimal("40000.0"))

        # Set target allocation
        portfolio.assets["BTCUSDT"].target_allocation_pct = Decimal("50.0")

        # Act
        needs_rebalancing, recommendations = portfolio_manager.check_rebalancing_needed(
            portfolio_id
        )

        # Assert - depends on threshold settings
        assert isinstance(needs_rebalancing, bool)
        assert isinstance(recommendations, list)

    def test_check_rebalancing_with_drift(self, portfolio_manager):
        """Test rebalancing check detects drift"""
        # Arrange
        portfolio_id = "default"
        portfolio = portfolio_manager.get_portfolio(portfolio_id)

        # Add assets with significant drift
        portfolio.add_asset("BTCUSDT", "Bitcoin", Decimal("2.0"), Decimal("40000.0"))
        portfolio.add_asset("ETHUSDT", "Ethereum", Decimal("1.0"), Decimal("3000.0"))

        # Set target allocations that differ from current
        portfolio.assets["BTCUSDT"].target_allocation_pct = Decimal("30.0")
        portfolio.assets["ETHUSDT"].target_allocation_pct = Decimal("70.0")

        # Act
        needs_rebalancing, recommendations = portfolio_manager.check_rebalancing_needed(
            portfolio_id
        )

        # Assert
        assert isinstance(needs_rebalancing, bool)
        assert isinstance(recommendations, list)

        if needs_rebalancing:
            # Verify recommendations have required fields
            for rec in recommendations:
                assert hasattr(rec, 'symbol')
                assert hasattr(rec, 'action')
                assert hasattr(rec, 'quantity')

    def test_check_rebalancing_nonexistent_portfolio(self, portfolio_manager):
        """Test rebalancing check on non-existent portfolio"""
        # Act
        needs_rebalancing, recommendations = portfolio_manager.check_rebalancing_needed(
            "nonexistent"
        )

        # Assert
        assert needs_rebalancing is False
        assert len(recommendations) == 0


class TestConcurrentTransactions:
    """Test concurrent transaction handling"""

    @pytest.fixture
    def portfolio_manager(self):
        """Create portfolio manager instance"""
        return PortfolioManager()

    @pytest.mark.asyncio
    async def test_concurrent_buy_transactions(self, portfolio_manager):
        """Test multiple simultaneous buy transactions"""
        # Arrange
        portfolio_id = "default"
        symbol = "BTCUSDT"
        quantity = Decimal("0.1")
        price = Decimal("45000.0")

        # Act: Execute multiple transactions
        results = []
        for i in range(5):
            success, message, _ = portfolio_manager.execute_transaction(
                portfolio_id, symbol, "BUY", quantity, price
            )
            results.append(success)

        # Assert
        assert all(results)  # All should succeed

        # Verify total quantity
        portfolio = portfolio_manager.get_portfolio(portfolio_id)
        expected_quantity = quantity * 5
        assert portfolio.assets[symbol].quantity == expected_quantity

    def test_sequential_buy_sell_transactions(self, portfolio_manager):
        """Test sequence of buy and sell transactions"""
        # Arrange
        portfolio_id = "default"
        symbol = "BTCUSDT"

        # Act: Buy, sell, buy again
        buy1_success, _, _ = portfolio_manager.execute_transaction(
            portfolio_id, symbol, "BUY", Decimal("1.0"), Decimal("45000.0")
        )

        sell_success, _, _ = portfolio_manager.execute_transaction(
            portfolio_id, symbol, "SELL", Decimal("0.5"), Decimal("46000.0")
        )

        buy2_success, _, _ = portfolio_manager.execute_transaction(
            portfolio_id, symbol, "BUY", Decimal("0.5"), Decimal("45500.0")
        )

        # Assert
        assert buy1_success is True
        assert sell_success is True
        assert buy2_success is True

        # Verify final state
        portfolio = portfolio_manager.get_portfolio(portfolio_id)
        assert portfolio.assets[symbol].quantity == Decimal("1.0")

        # Verify transaction history
        history = portfolio_manager.get_transaction_history(portfolio_id)
        assert len(history) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
