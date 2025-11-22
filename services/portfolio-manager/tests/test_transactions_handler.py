"""
Test Suite for Transactions Handler
Tests buy and sell transaction execution

Coverage Target: transactions.py (27% → 95%)

FIXED: Using proper test mocking with app.main module patching
"""

import pytest
import uuid
from decimal import Decimal
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.models import Portfolio, TransactionResponse


class MockRequest:
    """Mock FastAPI Request object for testing"""
    def __init__(self, client_host="127.0.0.1"):
        self.client = Mock()
        self.client.host = client_host


class TestBuyAsset:
    """Test buy_asset endpoint handler"""

    def setup_method(self):
        """Setup test client"""
        self.client = TestClient(app)

    @pytest.mark.asyncio
    async def test_buy_asset_success_with_provided_price(self):
        """Test successful buy with provided price"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.execute_transaction.return_value = (True, "Transaction successful", None)

        with patch('app.main.portfolio_manager', mock_manager):
            with patch('app.handlers.transactions.check_rate_limit'):
                with patch('app.handlers.transactions.parse_decimal', side_effect=lambda v, n: Decimal(v)):
                    response = self.client.post(
                        "/api/v1/transaction/buy",
                        params={
                            "portfolio_id": "test",
                            "symbol": "BTCUSDT",
                            "quantity": "1.0",
                            "price": "50000.00"
                        }
                    )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["symbol"] == "BTCUSDT"
        assert data["action"] == "BUY"
        assert data["quantity"] == "1.0"
        assert Decimal(data["price"]) == Decimal("50000.00")
        assert Decimal(data["total_cost"]) == Decimal("50000.00")

    @pytest.mark.asyncio
    async def test_buy_asset_success_without_price(self):
        """Test successful buy with fetched price"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager._fetch_current_price = AsyncMock(return_value=Decimal("50000.00"))
        mock_manager.execute_transaction.return_value = (True, "Transaction successful", None)

        with patch('app.main.portfolio_manager', mock_manager):
            with patch('app.handlers.transactions.check_rate_limit'):
                with patch('app.handlers.transactions.parse_decimal', return_value=Decimal("1.0")):
                    response = self.client.post(
                        "/api/v1/transaction/buy",
                        params={
                            "portfolio_id": "test",
                            "symbol": "BTCUSDT",
                            "quantity": "1.0"
                        }
                    )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert Decimal(data["total_cost"]) == Decimal("50000.00")
        mock_manager._fetch_current_price.assert_called_once_with("BTCUSDT")

    @pytest.mark.asyncio
    async def test_buy_asset_portfolio_not_found(self):
        """Test buy fails when portfolio doesn't exist"""
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = None

        with patch('app.main.portfolio_manager', mock_manager):
            with patch('app.handlers.transactions.check_rate_limit'):
                response = self.client.post(
                    "/api/v1/transaction/buy",
                    params={
                        "portfolio_id": "nonexistent",
                        "symbol": "BTCUSDT",
                        "quantity": "1.0"
                    }
                )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_buy_asset_price_fetch_failure(self):
        """Test buy fails when price cannot be fetched"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager._fetch_current_price = AsyncMock(return_value=Decimal("0"))

        with patch('app.main.portfolio_manager', mock_manager):
            with patch('app.handlers.transactions.check_rate_limit'):
                with patch('app.handlers.transactions.parse_decimal', return_value=Decimal("1.0")):
                    response = self.client.post(
                        "/api/v1/transaction/buy",
                        params={
                            "symbol": "INVALID",
                            "quantity": "1.0"
                        }
                    )

        assert response.status_code == 503
        assert "could not fetch" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_buy_asset_transaction_execution_failure(self):
        """Test buy fails when transaction execution fails"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.execute_transaction.return_value = (False, "Insufficient balance", None)

        with patch('app.main.portfolio_manager', mock_manager):
            with patch('app.handlers.transactions.check_rate_limit'):
                with patch('app.handlers.transactions.parse_decimal', side_effect=lambda v, n: Decimal(v)):
                    response = self.client.post(
                        "/api/v1/transaction/buy",
                        params={
                            "symbol": "BTCUSDT",
                            "quantity": "100.0",
                            "price": "50000.00"
                        }
                    )

        assert response.status_code == 400
        assert "Insufficient balance" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_buy_asset_rate_limiting_checked(self):
        """Test that rate limiting is checked"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.execute_transaction.return_value = (True, "Success", None)

        with patch('app.main.portfolio_manager', mock_manager):
            with patch('app.handlers.transactions.check_rate_limit') as mock_rate_limit:
                with patch('app.handlers.transactions.parse_decimal', side_effect=lambda v, n: Decimal(v)):
                    with patch('app.handlers.transactions.settings') as mock_settings:
                        mock_settings.rate_limit_transactions_per_minute = 30
                        response = self.client.post(
                            "/api/v1/transaction/buy",
                            params={
                                "symbol": "BTCUSDT",
                                "quantity": "1.0",
                                "price": "50000.00"
                            }
                        )

                        # Rate limit should be checked
                        assert mock_rate_limit.called

    @pytest.mark.asyncio
    async def test_buy_asset_default_portfolio(self):
        """Test buy with default portfolio ID"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.execute_transaction.return_value = (True, "Success", None)

        with patch('app.main.portfolio_manager', mock_manager):
            with patch('app.handlers.transactions.check_rate_limit'):
                with patch('app.handlers.transactions.parse_decimal', side_effect=lambda v, n: Decimal(v)):
                    response = self.client.post(
                        "/api/v1/transaction/buy",
                        params={
                            "symbol": "BTCUSDT",
                            "quantity": "1.0",
                            "price": "50000.00"
                        }
                    )

        assert response.status_code == 200
        mock_manager.get_portfolio.assert_called_once_with("default")

    @pytest.mark.asyncio
    async def test_buy_asset_total_cost_calculation(self):
        """Test accurate total cost calculation"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.execute_transaction.return_value = (True, "Success", None)

        with patch('app.main.portfolio_manager', mock_manager):
            with patch('app.handlers.transactions.check_rate_limit'):
                with patch('app.handlers.transactions.parse_decimal', side_effect=lambda v, n: Decimal(v)):
                    response = self.client.post(
                        "/api/v1/transaction/buy",
                        params={
                            "symbol": "ETHUSDT",
                            "quantity": "10.5",
                            "price": "3000.00"
                        }
                    )

        assert response.status_code == 200
        data = response.json()
        # 10.5 * 3000 = 31500
        assert Decimal(data["total_cost"]) == Decimal("31500.00")

    @pytest.mark.asyncio
    async def test_buy_asset_transaction_id_generated(self):
        """Test that transaction ID is generated"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.execute_transaction.return_value = (True, "Success", None)

        with patch('app.main.portfolio_manager', mock_manager):
            with patch('app.handlers.transactions.check_rate_limit'):
                with patch('app.handlers.transactions.parse_decimal', side_effect=lambda v, n: Decimal(v)):
                    response = self.client.post(
                        "/api/v1/transaction/buy",
                        params={
                            "symbol": "BTCUSDT",
                            "quantity": "1.0",
                            "price": "50000.00"
                        }
                    )

        assert response.status_code == 200
        data = response.json()
        # Verify transaction ID is valid UUID
        try:
            uuid.UUID(data["transaction_id"])
            is_valid_uuid = True
        except ValueError:
            is_valid_uuid = False

        assert is_valid_uuid

    @pytest.mark.asyncio
    async def test_buy_asset_manager_not_initialized(self):
        """Test error when portfolio manager not initialized"""
        with patch('app.main.portfolio_manager', None):
            response = self.client.post(
                "/api/v1/transaction/buy",
                params={
                    "symbol": "BTCUSDT",
                    "quantity": "1.0",
                    "price": "50000.00"
                }
            )

        assert response.status_code == 503
        assert "not initialized" in response.json()["detail"].lower()


class TestSellAsset:
    """Test sell_asset endpoint handler"""

    def setup_method(self):
        """Setup test client"""
        self.client = TestClient(app)

    @pytest.mark.asyncio
    async def test_sell_asset_success_with_provided_price(self):
        """Test successful sell with provided price"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.execute_transaction.return_value = (True, "Sold successfully", Decimal("5000.00"))

        with patch('app.main.portfolio_manager', mock_manager):
            with patch('app.handlers.transactions.check_rate_limit'):
                with patch('app.handlers.transactions.parse_decimal', side_effect=lambda v, n: Decimal(v)):
                    response = self.client.post(
                        "/api/v1/transaction/sell",
                        params={
                            "portfolio_id": "test",
                            "symbol": "BTCUSDT",
                            "quantity": "1.0",
                            "price": "55000.00"
                        }
                    )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["action"] == "SELL"
        assert data["symbol"] == "BTCUSDT"
        assert data["quantity"] == "1.0"
        assert Decimal(data["price"]) == Decimal("55000.00")
        assert Decimal(data["total_cost"]) == Decimal("55000.00")  # Total proceeds
        assert data["realized_pnl"] == "5000.00"

    @pytest.mark.asyncio
    async def test_sell_asset_success_without_price(self):
        """Test successful sell with fetched price"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager._fetch_current_price = AsyncMock(return_value=Decimal("55000.00"))
        mock_manager.execute_transaction.return_value = (True, "Sold", Decimal("5000.00"))

        with patch('app.main.portfolio_manager', mock_manager):
            with patch('app.handlers.transactions.check_rate_limit'):
                with patch('app.handlers.transactions.parse_decimal', return_value=Decimal("1.0")):
                    response = self.client.post(
                        "/api/v1/transaction/sell",
                        params={
                            "symbol": "BTCUSDT",
                            "quantity": "1.0"
                        }
                    )

        assert response.status_code == 200
        data = response.json()
        assert Decimal(data["price"]) == Decimal("55000.00")
        mock_manager._fetch_current_price.assert_called_once_with("BTCUSDT")

    @pytest.mark.asyncio
    async def test_sell_asset_portfolio_not_found(self):
        """Test sell fails when portfolio doesn't exist"""
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = None

        with patch('app.main.portfolio_manager', mock_manager):
            with patch('app.handlers.transactions.check_rate_limit'):
                response = self.client.post(
                    "/api/v1/transaction/sell",
                    params={
                        "portfolio_id": "nonexistent",
                        "symbol": "BTCUSDT",
                        "quantity": "1.0"
                    }
                )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_sell_asset_insufficient_holdings(self):
        """Test sell fails with insufficient holdings"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.execute_transaction.return_value = (False, "Insufficient holdings", None)

        with patch('app.main.portfolio_manager', mock_manager):
            with patch('app.handlers.transactions.check_rate_limit'):
                with patch('app.handlers.transactions.parse_decimal', side_effect=lambda v, n: Decimal(v)):
                    response = self.client.post(
                        "/api/v1/transaction/sell",
                        params={
                            "symbol": "BTCUSDT",
                            "quantity": "100.0",
                            "price": "50000.00"
                        }
                    )

        assert response.status_code == 400
        assert "Insufficient holdings" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_sell_asset_price_fetch_failure(self):
        """Test sell fails when price cannot be fetched"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager._fetch_current_price = AsyncMock(return_value=Decimal("0"))

        with patch('app.main.portfolio_manager', mock_manager):
            with patch('app.handlers.transactions.check_rate_limit'):
                with patch('app.handlers.transactions.parse_decimal', return_value=Decimal("1.0")):
                    response = self.client.post(
                        "/api/v1/transaction/sell",
                        params={
                            "symbol": "INVALID",
                            "quantity": "1.0"
                        }
                    )

        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_sell_asset_with_loss(self):
        """Test sell transaction with realized loss"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.execute_transaction.return_value = (True, "Sold at loss", Decimal("-2000.00"))

        with patch('app.main.portfolio_manager', mock_manager):
            with patch('app.handlers.transactions.check_rate_limit'):
                with patch('app.handlers.transactions.parse_decimal', side_effect=lambda v, n: Decimal(v)):
                    response = self.client.post(
                        "/api/v1/transaction/sell",
                        params={
                            "symbol": "BTCUSDT",
                            "quantity": "1.0",
                            "price": "48000.00"
                        }
                    )

        assert response.status_code == 200
        assert response.json()["realized_pnl"] == "-2000.00"

    @pytest.mark.asyncio
    async def test_sell_asset_no_realized_pnl(self):
        """Test sell when no realized P&L is calculated"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.execute_transaction.return_value = (True, "Sold", None)

        with patch('app.main.portfolio_manager', mock_manager):
            with patch('app.handlers.transactions.check_rate_limit'):
                with patch('app.handlers.transactions.parse_decimal', side_effect=lambda v, n: Decimal(v)):
                    response = self.client.post(
                        "/api/v1/transaction/sell",
                        params={
                            "symbol": "BTCUSDT",
                            "quantity": "1.0",
                            "price": "50000.00"
                        }
                    )

        assert response.status_code == 200
        assert response.json()["realized_pnl"] is None

    @pytest.mark.asyncio
    async def test_sell_asset_rate_limiting_checked(self):
        """Test that rate limiting is checked"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.execute_transaction.return_value = (True, "Success", None)

        with patch('app.main.portfolio_manager', mock_manager):
            with patch('app.handlers.transactions.check_rate_limit') as mock_rate_limit:
                with patch('app.handlers.transactions.parse_decimal', side_effect=lambda v, n: Decimal(v)):
                    with patch('app.handlers.transactions.settings') as mock_settings:
                        mock_settings.rate_limit_transactions_per_minute = 30
                        response = self.client.post(
                            "/api/v1/transaction/sell",
                            params={
                                "symbol": "BTCUSDT",
                                "quantity": "1.0",
                                "price": "50000.00"
                            }
                        )

                        assert mock_rate_limit.called

    @pytest.mark.asyncio
    async def test_sell_asset_total_proceeds_calculation(self):
        """Test accurate total proceeds calculation"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.execute_transaction.return_value = (True, "Success", Decimal("1000.00"))

        with patch('app.main.portfolio_manager', mock_manager):
            with patch('app.handlers.transactions.check_rate_limit'):
                with patch('app.handlers.transactions.parse_decimal', side_effect=lambda v, n: Decimal(v)):
                    response = self.client.post(
                        "/api/v1/transaction/sell",
                        params={
                            "symbol": "ETHUSDT",
                            "quantity": "5.5",
                            "price": "3000.00"
                        }
                    )

        assert response.status_code == 200
        data = response.json()
        # 5.5 * 3000 = 16500
        assert Decimal(data["total_cost"]) == Decimal("16500.00")

    @pytest.mark.asyncio
    async def test_sell_asset_default_portfolio(self):
        """Test sell with default portfolio ID"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.execute_transaction.return_value = (True, "Success", None)

        with patch('app.main.portfolio_manager', mock_manager):
            with patch('app.handlers.transactions.check_rate_limit'):
                with patch('app.handlers.transactions.parse_decimal', side_effect=lambda v, n: Decimal(v)):
                    response = self.client.post(
                        "/api/v1/transaction/sell",
                        params={
                            "symbol": "BTCUSDT",
                            "quantity": "1.0",
                            "price": "50000.00"
                        }
                    )

        assert response.status_code == 200
        mock_manager.get_portfolio.assert_called_once_with("default")

    @pytest.mark.asyncio
    async def test_sell_asset_manager_not_initialized(self):
        """Test error when portfolio manager not initialized"""
        with patch('app.main.portfolio_manager', None):
            response = self.client.post(
                "/api/v1/transaction/sell",
                params={
                    "symbol": "BTCUSDT",
                    "quantity": "1.0",
                    "price": "50000.00"
                }
            )

        assert response.status_code == 503
        assert "not initialized" in response.json()["detail"].lower()
