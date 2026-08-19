"""
Test Suite for Allocation Handler
Tests portfolio allocation and rebalancing functionality

Coverage Target: allocation.py (57% → 95%)

FIXED: Using proper test mocking with app.main module patching
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models import (
    Portfolio,
    RebalanceRecommendation,
)


class TestGetAllocation:
    """Test get_allocation endpoint handler"""

    def setup_method(self):
        """Setup test client"""
        self.client = TestClient(app)

    @pytest.mark.asyncio
    async def test_get_allocation_success(self):
        """Test successful allocation retrieval"""
        # Setup mock portfolio
        mock_portfolio = Mock(spec=Portfolio)
        mock_portfolio.get_asset_allocation.return_value = {
            "BTCUSDT": Decimal("60.0"),
            "ETHUSDT": Decimal("40.0"),
        }

        # Setup mock manager
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()
        mock_manager.sync_with_trading_engine = AsyncMock(return_value=True)
        mock_manager.check_rebalancing_needed.return_value = (False, [])

        # Patch the global instance in main
        with patch("app.main.portfolio_manager", mock_manager):
            response = self.client.get("/api/v1/allocation?portfolio_id=test_portfolio")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["portfolio_id"] == "test_portfolio"
        assert "BTCUSDT" in data["allocations"]
        assert "ETHUSDT" in data["allocations"]
        assert data["needs_rebalancing"] is False

    @pytest.mark.asyncio
    async def test_get_allocation_default_portfolio(self):
        """Test allocation with no portfolio_id (resolves to the canonical id)"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_portfolio.get_asset_allocation.return_value = {"BTCUSDT": Decimal("100.0")}

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()
        mock_manager.sync_with_trading_engine = AsyncMock(return_value=True)
        mock_manager.check_rebalancing_needed.return_value = (False, [])

        with patch("app.main.portfolio_manager", mock_manager):
            response = self.client.get("/api/v1/allocation")

        assert response.status_code == 200
        data = response.json()
        assert data["portfolio_id"] == settings.default_portfolio_id
        mock_manager.get_portfolio.assert_called_once_with(
            settings.default_portfolio_id
        )

    @pytest.mark.asyncio
    async def test_get_allocation_portfolio_not_found(self):
        """Test error when portfolio doesn't exist"""
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = None

        with patch("app.main.portfolio_manager", mock_manager):
            response = self.client.get("/api/v1/allocation?portfolio_id=nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_allocation_needs_rebalancing(self):
        """Test allocation when rebalancing needed"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_portfolio.get_asset_allocation.return_value = {
            "BTCUSDT": Decimal("70.0"),
            "ETHUSDT": Decimal("30.0"),
        }

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()
        mock_manager.sync_with_trading_engine = AsyncMock(return_value=True)
        mock_manager.check_rebalancing_needed.return_value = (True, [])

        with patch("app.main.portfolio_manager", mock_manager):
            response = self.client.get("/api/v1/allocation?portfolio_id=test")

        assert response.status_code == 200
        assert response.json()["needs_rebalancing"] is True

    @pytest.mark.asyncio
    async def test_get_allocation_updates_prices(self):
        """Test that prices fall back to a local update when engine sync fails"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_portfolio.get_asset_allocation.return_value = {}

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()
        mock_manager.sync_with_trading_engine = AsyncMock(return_value=False)
        mock_manager.check_rebalancing_needed.return_value = (False, [])

        with patch("app.main.portfolio_manager", mock_manager):
            response = self.client.get("/api/v1/allocation?portfolio_id=test")

        assert response.status_code == 200
        mock_manager.update_prices.assert_called_once_with("test")

    @pytest.mark.asyncio
    async def test_get_allocation_empty_portfolio(self):
        """Test allocation for portfolio with no assets"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_portfolio.get_asset_allocation.return_value = {}

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()
        mock_manager.sync_with_trading_engine = AsyncMock(return_value=True)
        mock_manager.check_rebalancing_needed.return_value = (False, [])

        with patch("app.main.portfolio_manager", mock_manager):
            response = self.client.get("/api/v1/allocation?portfolio_id=empty")

        assert response.status_code == 200
        data = response.json()
        assert data["allocations"] == {}
        assert data["needs_rebalancing"] is False

    @pytest.mark.asyncio
    async def test_get_allocation_decimal_conversion(self):
        """Test that decimal values are properly converted to strings"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_portfolio.get_asset_allocation.return_value = {
            "BTCUSDT": Decimal("33.333333"),
            "ETHUSDT": Decimal("66.666667"),
        }

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()
        mock_manager.sync_with_trading_engine = AsyncMock(return_value=True)
        mock_manager.check_rebalancing_needed.return_value = (False, [])

        with patch("app.main.portfolio_manager", mock_manager):
            response = self.client.get("/api/v1/allocation")

        assert response.status_code == 200
        data = response.json()
        # Verify all allocations are strings
        for value in data["allocations"].values():
            assert isinstance(value, str)

    @pytest.mark.asyncio
    async def test_get_allocation_manager_not_initialized(self):
        """Test error when portfolio manager not initialized"""
        with patch("app.main.portfolio_manager", None):
            response = self.client.get("/api/v1/allocation")

        assert response.status_code == 503
        assert "not initialized" in response.json()["detail"].lower()


class TestGetRebalanceRecommendations:
    """Test get_rebalance_recommendations endpoint handler"""

    def setup_method(self):
        """Setup test client"""
        self.client = TestClient(app)

    @pytest.mark.asyncio
    async def test_get_rebalance_recommendations_success(self):
        """Test successful rebalance recommendations retrieval"""
        # Create mock recommendations with all required fields
        mock_recommendations = [
            RebalanceRecommendation(
                symbol="BTCUSDT",
                current_allocation_pct="50.0",
                target_allocation_pct="60.0",
                drift_pct="10.0",
                action="BUY",
                quantity="0.5",
                estimated_cost="25000.00",
            ),
            RebalanceRecommendation(
                symbol="ETHUSDT",
                current_allocation_pct="50.0",
                target_allocation_pct="40.0",
                drift_pct="-10.0",
                action="SELL",
                quantity="10.0",
                estimated_cost="15000.00",
            ),
        ]

        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()
        mock_manager.sync_with_trading_engine = AsyncMock(return_value=True)
        mock_manager.check_rebalancing_needed.return_value = (
            True,
            mock_recommendations,
        )

        with patch("app.main.portfolio_manager", mock_manager):
            response = self.client.get("/api/v1/rebalance?portfolio_id=test")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["needs_rebalancing"] is True
        assert data["total_transactions"] == 2
        assert len(data["recommendations"]) == 2
        # Total cost should be sum of individual costs
        assert float(data["estimated_total_cost"]) == 40000.00

    @pytest.mark.asyncio
    async def test_get_rebalance_recommendations_no_rebalancing_needed(self):
        """Test when portfolio doesn't need rebalancing"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()
        mock_manager.sync_with_trading_engine = AsyncMock(return_value=True)
        mock_manager.check_rebalancing_needed.return_value = (False, [])

        with patch("app.main.portfolio_manager", mock_manager):
            response = self.client.get("/api/v1/rebalance")

        assert response.status_code == 200
        data = response.json()
        assert data["needs_rebalancing"] is False
        assert data["total_transactions"] == 0
        assert data["estimated_total_cost"] == "0"

    @pytest.mark.asyncio
    async def test_get_rebalance_recommendations_portfolio_not_found(self):
        """Test error when portfolio doesn't exist"""
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = None

        with patch("app.main.portfolio_manager", mock_manager):
            response = self.client.get("/api/v1/rebalance?portfolio_id=nonexistent")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_rebalance_recommendations_updates_prices(self):
        """Test that prices fall back to a local update when engine sync fails"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()
        mock_manager.sync_with_trading_engine = AsyncMock(return_value=False)
        mock_manager.check_rebalancing_needed.return_value = (False, [])

        with patch("app.main.portfolio_manager", mock_manager):
            response = self.client.get("/api/v1/rebalance?portfolio_id=test")

        assert response.status_code == 200
        mock_manager.update_prices.assert_called_once_with("test")

    @pytest.mark.asyncio
    async def test_get_rebalance_recommendations_cost_calculation(self):
        """Test accurate total cost calculation"""
        mock_recommendations = [
            RebalanceRecommendation(
                symbol="BTC",
                current_allocation_pct="20.0",
                target_allocation_pct="30.0",
                drift_pct="10.0",
                action="BUY",
                quantity="1.0",
                estimated_cost="50000.50",
            ),
            RebalanceRecommendation(
                symbol="ETH",
                current_allocation_pct="40.0",
                target_allocation_pct="50.0",
                drift_pct="10.0",
                action="BUY",
                quantity="10.0",
                estimated_cost="25000.25",
            ),
            RebalanceRecommendation(
                symbol="SOL",
                current_allocation_pct="40.0",
                target_allocation_pct="20.0",
                drift_pct="-20.0",
                action="SELL",
                quantity="100.0",
                estimated_cost="5000.15",
            ),
        ]

        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()
        mock_manager.sync_with_trading_engine = AsyncMock(return_value=True)
        mock_manager.check_rebalancing_needed.return_value = (
            True,
            mock_recommendations,
        )

        with patch("app.main.portfolio_manager", mock_manager):
            response = self.client.get("/api/v1/rebalance")

        assert response.status_code == 200
        data = response.json()
        # Total should be 50000.50 + 25000.25 + 5000.15 = 80000.90
        assert Decimal(data["estimated_total_cost"]) == Decimal("80000.90")

    @pytest.mark.asyncio
    async def test_get_rebalance_recommendations_default_portfolio(self):
        """Test recommendations with no portfolio_id (resolves to the canonical id)"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()
        mock_manager.sync_with_trading_engine = AsyncMock(return_value=True)
        mock_manager.check_rebalancing_needed.return_value = (False, [])

        with patch("app.main.portfolio_manager", mock_manager):
            response = self.client.get("/api/v1/rebalance")

        assert response.status_code == 200
        data = response.json()
        assert data["portfolio_id"] == settings.default_portfolio_id
        mock_manager.get_portfolio.assert_called_once_with(
            settings.default_portfolio_id
        )

    @pytest.mark.asyncio
    async def test_get_rebalance_recommendations_single_recommendation(self):
        """Test with single rebalancing recommendation"""
        mock_recommendations = [
            RebalanceRecommendation(
                symbol="BTCUSDT",
                current_allocation_pct="90.0",
                target_allocation_pct="100.0",
                drift_pct="10.0",
                action="BUY",
                quantity="0.1",
                estimated_cost="5000.00",
            )
        ]

        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()
        mock_manager.sync_with_trading_engine = AsyncMock(return_value=True)
        mock_manager.check_rebalancing_needed.return_value = (
            True,
            mock_recommendations,
        )

        with patch("app.main.portfolio_manager", mock_manager):
            response = self.client.get("/api/v1/rebalance")

        assert response.status_code == 200
        data = response.json()
        assert data["total_transactions"] == 1
        assert data["estimated_total_cost"] == "5000.00"

    @pytest.mark.asyncio
    async def test_get_rebalance_recommendations_preserves_recommendation_data(self):
        """Test that recommendation data is preserved correctly"""
        mock_recommendations = [
            RebalanceRecommendation(
                symbol="BTCUSDT",
                current_allocation_pct="75.0",
                target_allocation_pct="50.0",
                drift_pct="-25.0",
                action="SELL",
                quantity="2.5",
                estimated_cost="125000.00",
            )
        ]

        mock_portfolio = Mock(spec=Portfolio)
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()
        mock_manager.sync_with_trading_engine = AsyncMock(return_value=True)
        mock_manager.check_rebalancing_needed.return_value = (
            True,
            mock_recommendations,
        )

        with patch("app.main.portfolio_manager", mock_manager):
            response = self.client.get("/api/v1/rebalance")

        assert response.status_code == 200
        data = response.json()
        rec = data["recommendations"][0]
        assert rec["symbol"] == "BTCUSDT"
        assert rec["action"] == "SELL"
        assert rec["quantity"] == "2.5"
        assert rec["estimated_cost"] == "125000.00"

    @pytest.mark.asyncio
    async def test_get_rebalance_recommendations_manager_not_initialized(self):
        """Test error when portfolio manager not initialized"""
        with patch("app.main.portfolio_manager", None):
            response = self.client.get("/api/v1/rebalance")

        assert response.status_code == 503
        assert "not initialized" in response.json()["detail"].lower()
