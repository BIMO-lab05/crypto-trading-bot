"""
Test Suite for Transaction History Handler
Tests transaction history endpoint

Coverage Target: transaction_history.py (29% → 95%+)

Tests:
- get_transaction_history: Transaction history retrieval with filters
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from datetime import datetime, timedelta

from app.main import app
from app.models.transaction import Transaction


class TestGetTransactionHistory:
    """Test get_transaction_history endpoint handler"""

    def setup_method(self):
        """Setup test client"""
        self.client = TestClient(app)

    @pytest.mark.asyncio
    async def test_get_transaction_history_success(self):
        """Test successful transaction history retrieval"""
        # Setup mock portfolio
        mock_portfolio = Mock()
        mock_portfolio.portfolio_id = "test_portfolio"

        # Setup mock manager
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio

        # Create mock transactions
        transactions = [
            Transaction(
                timestamp=datetime.now(),
                symbol="BTCUSDT",
                action="BUY",
                quantity=Decimal("0.5"),
                price=Decimal("40000"),
                total_amount=Decimal("20000"),
                realized_pnl=None
            ),
            Transaction(
                timestamp=datetime.now() - timedelta(hours=1),
                symbol="ETHUSDT",
                action="BUY",
                quantity=Decimal("5.0"),
                price=Decimal("2500"),
                total_amount=Decimal("12500"),
                realized_pnl=None
            ),
            Transaction(
                timestamp=datetime.now() - timedelta(hours=2),
                symbol="BTCUSDT",
                action="SELL",
                quantity=Decimal("0.2"),
                price=Decimal("42000"),
                total_amount=Decimal("8400"),
                realized_pnl=Decimal("400")
            )
        ]

        mock_manager.get_transaction_history.return_value = transactions

        with patch('app.main.portfolio_manager', mock_manager):
            response = self.client.get("/api/v1/transactions?portfolio_id=test_portfolio")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["portfolio_id"] == "test_portfolio"
        assert data["total_count"] == 3
        assert len(data["transactions"]) == 3

        # Verify summary statistics
        assert data["total_buy_volume"] == "32500"  # 20000 + 12500
        assert data["total_sell_volume"] == "8400"
        assert data["total_realized_pnl"] == "400"

    @pytest.mark.asyncio
    async def test_get_transaction_history_default_portfolio(self):
        """Test transaction history with default portfolio"""
        mock_portfolio = Mock()
        mock_portfolio.portfolio_id = "default"

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.get_transaction_history.return_value = []

        with patch('app.main.portfolio_manager', mock_manager):
            response = self.client.get("/api/v1/transactions")

        assert response.status_code == 200
        data = response.json()
        assert data["portfolio_id"] == "default"
        mock_manager.get_portfolio.assert_called_once_with("default")

    @pytest.mark.asyncio
    async def test_get_transaction_history_with_limit(self):
        """Test transaction history with limit parameter"""
        mock_portfolio = Mock()

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio

        # Create 5 transactions
        transactions = [
            Transaction(
                timestamp=datetime.now() - timedelta(hours=i),
                symbol="BTCUSDT",
                action="BUY",
                quantity=Decimal("0.1"),
                price=Decimal("40000"),
                total_amount=Decimal("4000"),
                realized_pnl=None
            )
            for i in range(5)
        ]

        # Only return first 3 when limit=3
        mock_manager.get_transaction_history.return_value = transactions[:3]

        with patch('app.main.portfolio_manager', mock_manager):
            response = self.client.get("/api/v1/transactions?portfolio_id=test&limit=3")

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 3

        # Verify limit was passed to manager
        mock_manager.get_transaction_history.assert_called_once_with(
            portfolio_id="test",
            limit=3,
            symbol=None
        )

    @pytest.mark.asyncio
    async def test_get_transaction_history_with_symbol_filter(self):
        """Test transaction history filtered by symbol"""
        mock_portfolio = Mock()

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio

        # Only BTC transactions
        btc_transactions = [
            Transaction(
                timestamp=datetime.now(),
                symbol="BTCUSDT",
                action="BUY",
                quantity=Decimal("0.5"),
                price=Decimal("40000"),
                total_amount=Decimal("20000"),
                realized_pnl=None
            ),
            Transaction(
                timestamp=datetime.now() - timedelta(hours=1),
                symbol="BTCUSDT",
                action="SELL",
                quantity=Decimal("0.2"),
                price=Decimal("42000"),
                total_amount=Decimal("8400"),
                realized_pnl=Decimal("400")
            )
        ]

        mock_manager.get_transaction_history.return_value = btc_transactions

        with patch('app.main.portfolio_manager', mock_manager):
            response = self.client.get("/api/v1/transactions?portfolio_id=test&symbol=BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 2

        # Verify all transactions are for BTCUSDT
        for txn in data["transactions"]:
            assert txn["symbol"] == "BTCUSDT"

        # Verify symbol filter was passed to manager
        mock_manager.get_transaction_history.assert_called_once_with(
            portfolio_id="test",
            limit=None,
            symbol="BTCUSDT"
        )

    @pytest.mark.asyncio
    async def test_get_transaction_history_with_limit_and_symbol(self):
        """Test transaction history with both limit and symbol filters"""
        mock_portfolio = Mock()

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio

        transactions = [
            Transaction(
                timestamp=datetime.now(),
                symbol="ETHUSDT",
                action="BUY",
                quantity=Decimal("1.0"),
                price=Decimal("2500"),
                total_amount=Decimal("2500"),
                realized_pnl=None
            )
        ]

        mock_manager.get_transaction_history.return_value = transactions

        with patch('app.main.portfolio_manager', mock_manager):
            response = self.client.get(
                "/api/v1/transactions?portfolio_id=test&limit=10&symbol=ETHUSDT"
            )

        assert response.status_code == 200

        # Verify both parameters were passed
        mock_manager.get_transaction_history.assert_called_once_with(
            portfolio_id="test",
            limit=10,
            symbol="ETHUSDT"
        )

    @pytest.mark.asyncio
    async def test_get_transaction_history_empty(self):
        """Test transaction history with no transactions"""
        mock_portfolio = Mock()

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.get_transaction_history.return_value = []

        with patch('app.main.portfolio_manager', mock_manager):
            response = self.client.get("/api/v1/transactions?portfolio_id=test")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total_count"] == 0
        assert len(data["transactions"]) == 0
        assert data["total_buy_volume"] == "0"
        assert data["total_sell_volume"] == "0"
        assert data["total_realized_pnl"] == "0"

    @pytest.mark.asyncio
    async def test_get_transaction_history_only_buy_transactions(self):
        """Test transaction history with only buy transactions"""
        mock_portfolio = Mock()

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio

        buy_transactions = [
            Transaction(
                timestamp=datetime.now(),
                symbol="BTCUSDT",
                action="BUY",
                quantity=Decimal("0.5"),
                price=Decimal("40000"),
                total_amount=Decimal("20000"),
                realized_pnl=None
            ),
            Transaction(
                timestamp=datetime.now() - timedelta(hours=1),
                symbol="ETHUSDT",
                action="BUY",
                quantity=Decimal("5.0"),
                price=Decimal("2500"),
                total_amount=Decimal("12500"),
                realized_pnl=None
            )
        ]

        mock_manager.get_transaction_history.return_value = buy_transactions

        with patch('app.main.portfolio_manager', mock_manager):
            response = self.client.get("/api/v1/transactions?portfolio_id=test")

        assert response.status_code == 200
        data = response.json()
        assert data["total_buy_volume"] == "32500"
        assert data["total_sell_volume"] == "0"
        assert data["total_realized_pnl"] == "0"

    @pytest.mark.asyncio
    async def test_get_transaction_history_only_sell_transactions(self):
        """Test transaction history with only sell transactions"""
        mock_portfolio = Mock()

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio

        sell_transactions = [
            Transaction(
                timestamp=datetime.now(),
                symbol="BTCUSDT",
                action="SELL",
                quantity=Decimal("0.5"),
                price=Decimal("42000"),
                total_amount=Decimal("21000"),
                realized_pnl=Decimal("1000")
            ),
            Transaction(
                timestamp=datetime.now() - timedelta(hours=1),
                symbol="ETHUSDT",
                action="SELL",
                quantity=Decimal("5.0"),
                price=Decimal("2600"),
                total_amount=Decimal("13000"),
                realized_pnl=Decimal("500")
            )
        ]

        mock_manager.get_transaction_history.return_value = sell_transactions

        with patch('app.main.portfolio_manager', mock_manager):
            response = self.client.get("/api/v1/transactions?portfolio_id=test")

        assert response.status_code == 200
        data = response.json()
        assert data["total_buy_volume"] == "0"
        assert data["total_sell_volume"] == "34000"
        assert data["total_realized_pnl"] == "1500"

    @pytest.mark.asyncio
    async def test_get_transaction_history_mixed_pnl(self):
        """Test transaction history with positive and negative P&L"""
        mock_portfolio = Mock()

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio

        transactions = [
            Transaction(
                timestamp=datetime.now(),
                symbol="BTCUSDT",
                action="SELL",
                quantity=Decimal("0.5"),
                price=Decimal("45000"),
                total_amount=Decimal("22500"),
                realized_pnl=Decimal("2500")  # Profit
            ),
            Transaction(
                timestamp=datetime.now() - timedelta(hours=1),
                symbol="ETHUSDT",
                action="SELL",
                quantity=Decimal("5.0"),
                price=Decimal("2400"),
                total_amount=Decimal("12000"),
                realized_pnl=Decimal("-500")  # Loss
            )
        ]

        mock_manager.get_transaction_history.return_value = transactions

        with patch('app.main.portfolio_manager', mock_manager):
            response = self.client.get("/api/v1/transactions?portfolio_id=test")

        assert response.status_code == 200
        data = response.json()
        assert data["total_realized_pnl"] == "2000"  # 2500 - 500

    @pytest.mark.asyncio
    async def test_get_transaction_history_sell_without_pnl(self):
        """Test sell transaction without realized P&L"""
        mock_portfolio = Mock()

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio

        transactions = [
            Transaction(
                timestamp=datetime.now(),
                symbol="BTCUSDT",
                action="SELL",
                quantity=Decimal("0.5"),
                price=Decimal("42000"),
                total_amount=Decimal("21000"),
                realized_pnl=None  # No P&L recorded
            )
        ]

        mock_manager.get_transaction_history.return_value = transactions

        with patch('app.main.portfolio_manager', mock_manager):
            response = self.client.get("/api/v1/transactions?portfolio_id=test")

        assert response.status_code == 200
        data = response.json()
        assert data["total_sell_volume"] == "21000"
        assert data["total_realized_pnl"] == "0"  # P&L not counted if None

    @pytest.mark.asyncio
    async def test_get_transaction_history_portfolio_not_found(self):
        """Test error when portfolio doesn't exist"""
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = None

        with patch('app.main.portfolio_manager', mock_manager):
            response = self.client.get("/api/v1/transactions?portfolio_id=nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_transaction_history_manager_not_initialized(self):
        """Test error when portfolio manager not initialized"""
        with patch('app.main.portfolio_manager', None):
            response = self.client.get("/api/v1/transactions")

        assert response.status_code == 503
        assert "not initialized" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_transaction_history_large_dataset(self):
        """Test transaction history with large number of transactions"""
        mock_portfolio = Mock()

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio

        # Create 100 transactions
        transactions = [
            Transaction(
                timestamp=datetime.now() - timedelta(hours=i),
                symbol="BTCUSDT",
                action="BUY" if i % 2 == 0 else "SELL",
                quantity=Decimal("0.1"),
                price=Decimal("40000") + Decimal(i * 100),
                total_amount=Decimal("4000") + Decimal(i * 10),
                realized_pnl=Decimal("10") if i % 2 == 1 else None
            )
            for i in range(100)
        ]

        mock_manager.get_transaction_history.return_value = transactions

        with patch('app.main.portfolio_manager', mock_manager):
            response = self.client.get("/api/v1/transactions?portfolio_id=test")

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 100

    @pytest.mark.asyncio
    async def test_get_transaction_history_decimal_precision(self):
        """Test that decimal precision is preserved in response"""
        mock_portfolio = Mock()

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio

        transactions = [
            Transaction(
                timestamp=datetime.now(),
                symbol="BTCUSDT",
                action="BUY",
                quantity=Decimal("0.12345678"),
                price=Decimal("40123.456789"),
                total_amount=Decimal("4953.24691975"),
                realized_pnl=None
            )
        ]

        mock_manager.get_transaction_history.return_value = transactions

        with patch('app.main.portfolio_manager', mock_manager):
            response = self.client.get("/api/v1/transactions?portfolio_id=test")

        assert response.status_code == 200
        data = response.json()

        # Verify precision is maintained
        txn = data["transactions"][0]
        assert txn["quantity"] == "0.12345678"
        assert txn["price"] == "40123.456789"

    @pytest.mark.asyncio
    async def test_get_transaction_history_chronological_order(self):
        """Test that transactions are returned in chronological order"""
        mock_portfolio = Mock()

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio

        # Create transactions at different times
        now = datetime.now()
        transactions = [
            Transaction(
                timestamp=now,
                symbol="BTCUSDT",
                action="BUY",
                quantity=Decimal("0.5"),
                price=Decimal("40000"),
                total_amount=Decimal("20000"),
                realized_pnl=None
            ),
            Transaction(
                timestamp=now - timedelta(hours=2),
                symbol="ETHUSDT",
                action="BUY",
                quantity=Decimal("5.0"),
                price=Decimal("2500"),
                total_amount=Decimal("12500"),
                realized_pnl=None
            ),
            Transaction(
                timestamp=now - timedelta(hours=1),
                symbol="BNBUSDT",
                action="BUY",
                quantity=Decimal("10.0"),
                price=Decimal("400"),
                total_amount=Decimal("4000"),
                realized_pnl=None
            )
        ]

        mock_manager.get_transaction_history.return_value = transactions

        with patch('app.main.portfolio_manager', mock_manager):
            response = self.client.get("/api/v1/transactions?portfolio_id=test")

        assert response.status_code == 200
        data = response.json()

        # Transactions should be in the order returned by manager
        assert len(data["transactions"]) == 3
        assert data["transactions"][0]["symbol"] == "BTCUSDT"
        assert data["transactions"][1]["symbol"] == "ETHUSDT"
        assert data["transactions"][2]["symbol"] == "BNBUSDT"
