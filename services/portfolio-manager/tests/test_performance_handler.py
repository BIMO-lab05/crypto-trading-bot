"""
Test Suite for Performance Handler
Tests performance metrics endpoints

Coverage Target: performance.py (27% → 95%+)

Tests all performance endpoints:
- get_performance: Portfolio performance metrics
- get_asset_performance: Per-asset performance breakdown
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient
from datetime import datetime, timedelta

from app.main import app
from app.models import (
    Portfolio,
    Asset,
    PerformanceMetrics,
    AssetPerformance,
)


class TestGetPerformance:
    """Test get_performance endpoint handler"""

    def setup_method(self):
        """Setup test client"""
        self.client = TestClient(app)

    @pytest.mark.asyncio
    async def test_get_performance_basic_success(self):
        """Test successful basic performance retrieval"""
        # Setup mock portfolio
        mock_portfolio = Mock(spec=Portfolio)
        mock_portfolio.portfolio_id = "test_portfolio"

        # Setup mock manager
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()

        # Setup mock calculator with performance metrics
        mock_metrics = PerformanceMetrics(
            total_return=Decimal("1500.00"),
            total_unrealized_pnl_pct=Decimal("15.00"),
            realized_pnl=Decimal("500.00"),
            unrealized_pnl=Decimal("1000.00"),
            sharpe_ratio=Decimal("1.25"),
            win_rate=Decimal("0.60"),
            avg_win=Decimal("150.00"),
            avg_loss=Decimal("75.00"),
            max_drawdown=Decimal("0.12")
        )

        mock_calculator = Mock()
        mock_calculator.calculate_metrics.return_value = mock_metrics

        with patch('app.main.portfolio_manager', mock_manager), \
             patch('app.main.performance_calculator', mock_calculator):
            response = self.client.get("/api/v1/performance?portfolio_id=test_portfolio")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["portfolio_id"] == "test_portfolio"
        assert data["metrics"]["total_return"] == "1500.00"
        assert data["metrics"]["sharpe_ratio"] == "1.25"
        assert data["daily_performance"] is None
        assert data["period_performance"] is None

        # Verify update_prices was called
        mock_manager.update_prices.assert_called_once_with("test_portfolio")

    @pytest.mark.asyncio
    async def test_get_performance_default_portfolio(self):
        """Test performance retrieval with default portfolio"""
        mock_portfolio = Mock(spec=Portfolio)
        mock_portfolio.portfolio_id = "default"

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()

        mock_metrics = PerformanceMetrics(
            total_return=Decimal("0"),
            total_unrealized_pnl_pct=Decimal("0"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            sharpe_ratio=Decimal("0"),
            win_rate=Decimal("0"),
            avg_win=Decimal("0"),
            avg_loss=Decimal("0"),
            max_drawdown=Decimal("0")
        )

        mock_calculator = Mock()
        mock_calculator.calculate_metrics.return_value = mock_metrics

        with patch('app.main.portfolio_manager', mock_manager), \
             patch('app.main.performance_calculator', mock_calculator):
            response = self.client.get("/api/v1/performance")

        assert response.status_code == 200
        data = response.json()
        assert data["portfolio_id"] == "default"
        mock_manager.get_portfolio.assert_called_once_with("default")

    @pytest.mark.asyncio
    async def test_get_performance_with_daily_history(self):
        """Test performance retrieval with daily history"""
        mock_portfolio = Mock(spec=Portfolio)

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()

        mock_metrics = PerformanceMetrics(
            total_return=Decimal("1000"),
            total_unrealized_pnl_pct=Decimal("10"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("1000"),
            sharpe_ratio=Decimal("1.0"),
            win_rate=Decimal("0.5"),
            avg_win=Decimal("100"),
            avg_loss=Decimal("50"),
            max_drawdown=Decimal("0.1")
        )

        mock_calculator = Mock()
        mock_calculator.calculate_metrics.return_value = mock_metrics

        # Setup daily performance history
        daily_records = [
            dict(
                date=datetime.now().date(),
                total_value=Decimal("11000"),
                total_unrealized_pnl_pct=Decimal("10"),
                realized_pnl=Decimal("0"),
                unrealized_pnl=Decimal("1000"),
                num_positions=5
            ),
            dict(
                date=(datetime.now() - timedelta(days=1)).date(),
                total_value=Decimal("10500"),
                total_unrealized_pnl_pct=Decimal("5"),
                realized_pnl=Decimal("0"),
                unrealized_pnl=Decimal("500"),
                num_positions=5
            )
        ]

        mock_history = Mock()
        mock_history.get_daily_performance = AsyncMock(return_value=daily_records)

        with patch('app.main.portfolio_manager', mock_manager), \
             patch('app.main.performance_calculator', mock_calculator), \
             patch('app.main.performance_history', mock_history):
            response = self.client.get(
                "/api/v1/performance?portfolio_id=test&include_daily=true"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["daily_performance"] is not None
        assert len(data["daily_performance"]) == 2
        assert data["daily_performance"][0]["total_value"] == "11000"

        # Verify get_daily_performance was called with correct params
        mock_history.get_daily_performance.assert_called_once_with("test", days=30)

    @pytest.mark.asyncio
    async def test_get_performance_with_period_stats(self):
        """Test performance retrieval with period statistics"""
        mock_portfolio = Mock(spec=Portfolio)

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()

        mock_metrics = PerformanceMetrics(
            total_return=Decimal("1000"),
            total_unrealized_pnl_pct=Decimal("10"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("1000"),
            sharpe_ratio=Decimal("1.0"),
            win_rate=Decimal("0.5"),
            avg_win=Decimal("100"),
            avg_loss=Decimal("50"),
            max_drawdown=Decimal("0.1")
        )

        mock_calculator = Mock()
        mock_calculator.calculate_metrics.return_value = mock_metrics

        # Setup period performance stats
        week_stats = dict(
            period="week",
            start_date=datetime.now().date() - timedelta(days=7),
            end_date=datetime.now().date(),
            total_unrealized_pnl_pct=Decimal("2.5"),
            avg_daily_unrealized_pnl_pct=Decimal("0.35"),
            volatility=Decimal("1.2"),
            sharpe_ratio=Decimal("0.8"),
            max_drawdown=Decimal("0.05")
        )

        month_stats = dict(
            period="month",
            start_date=datetime.now().date() - timedelta(days=30),
            end_date=datetime.now().date(),
            total_unrealized_pnl_pct=Decimal("8.0"),
            avg_daily_unrealized_pnl_pct=Decimal("0.27"),
            volatility=Decimal("1.5"),
            sharpe_ratio=Decimal("1.2"),
            max_drawdown=Decimal("0.08")
        )

        mock_history = Mock()
        mock_history.calculate_period_performance = AsyncMock(
            side_effect=[week_stats, month_stats, None, None]
        )

        with patch('app.main.portfolio_manager', mock_manager), \
             patch('app.main.performance_calculator', mock_calculator), \
             patch('app.main.performance_history', mock_history):
            response = self.client.get(
                "/api/v1/performance?portfolio_id=test&include_periods=true"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["period_performance"] is not None
        assert "week" in data["period_performance"]
        assert "month" in data["period_performance"]
        assert data["period_performance"]["week"]["total_return_pct"] == "2.5"
        assert data["period_performance"]["month"]["sharpe_ratio"] == "1.2"

    @pytest.mark.asyncio
    async def test_get_performance_with_both_daily_and_periods(self):
        """Test performance with both daily and period data"""
        mock_portfolio = Mock(spec=Portfolio)

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()

        mock_metrics = PerformanceMetrics(
            total_return=Decimal("1000"),
            total_unrealized_pnl_pct=Decimal("10"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("1000"),
            sharpe_ratio=Decimal("1.0"),
            win_rate=Decimal("0.5"),
            avg_win=Decimal("100"),
            avg_loss=Decimal("50"),
            max_drawdown=Decimal("0.1")
        )

        mock_calculator = Mock()
        mock_calculator.calculate_metrics.return_value = mock_metrics

        daily_records = [
            dict(
                date=datetime.now().date(),
                total_value=Decimal("11000"),
                total_unrealized_pnl_pct=Decimal("10"),
                realized_pnl=Decimal("0"),
                unrealized_pnl=Decimal("1000"),
                num_positions=5
            )
        ]

        week_stats = dict(
            period="week",
            start_date=datetime.now().date() - timedelta(days=7),
            end_date=datetime.now().date(),
            total_unrealized_pnl_pct=Decimal("2.5"),
            avg_daily_unrealized_pnl_pct=Decimal("0.35"),
            volatility=Decimal("1.2"),
            sharpe_ratio=Decimal("0.8"),
            max_drawdown=Decimal("0.05")
        )

        mock_history = Mock()
        mock_history.get_daily_performance = AsyncMock(return_value=daily_records)
        mock_history.calculate_period_performance = AsyncMock(
            side_effect=[week_stats, None, None, None]
        )

        with patch('app.main.portfolio_manager', mock_manager), \
             patch('app.main.performance_calculator', mock_calculator), \
             patch('app.main.performance_history', mock_history):
            response = self.client.get(
                "/api/v1/performance?portfolio_id=test&include_daily=true&include_periods=true"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["daily_performance"] is not None
        assert data["period_performance"] is not None

    @pytest.mark.asyncio
    async def test_get_performance_portfolio_not_found(self):
        """Test error when portfolio doesn't exist"""
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = None

        with patch('app.main.portfolio_manager', mock_manager):
            response = self.client.get("/api/v1/performance?portfolio_id=nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_performance_history_service_not_initialized(self):
        """Test handling when history service not initialized"""
        mock_portfolio = Mock(spec=Portfolio)

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()

        mock_metrics = PerformanceMetrics(
            total_return=Decimal("1000"),
            total_unrealized_pnl_pct=Decimal("10"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("1000"),
            sharpe_ratio=Decimal("1.0"),
            win_rate=Decimal("0.5"),
            avg_win=Decimal("100"),
            avg_loss=Decimal("50"),
            max_drawdown=Decimal("0.1")
        )

        mock_calculator = Mock()
        mock_calculator.calculate_metrics.return_value = mock_metrics

        # History service not initialized
        with patch('app.main.portfolio_manager', mock_manager), \
             patch('app.main.performance_calculator', mock_calculator), \
             patch('app.main.performance_history', None):
            response = self.client.get(
                "/api/v1/performance?portfolio_id=test&include_daily=true"
            )

        assert response.status_code == 503
        assert "not initialized" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_performance_history_error_handling(self):
        """Test graceful error handling when history retrieval fails"""
        mock_portfolio = Mock(spec=Portfolio)

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()

        mock_metrics = PerformanceMetrics(
            total_return=Decimal("1000"),
            total_unrealized_pnl_pct=Decimal("10"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("1000"),
            sharpe_ratio=Decimal("1.0"),
            win_rate=Decimal("0.5"),
            avg_win=Decimal("100"),
            avg_loss=Decimal("50"),
            max_drawdown=Decimal("0.1")
        )

        mock_calculator = Mock()
        mock_calculator.calculate_metrics.return_value = mock_metrics

        mock_history = Mock()
        # Simulate error during history retrieval
        mock_history.get_daily_performance = AsyncMock(
            side_effect=Exception("Database error")
        )

        with patch('app.main.portfolio_manager', mock_manager), \
             patch('app.main.performance_calculator', mock_calculator), \
             patch('app.main.performance_history', mock_history):
            response = self.client.get(
                "/api/v1/performance?portfolio_id=test&include_daily=true"
            )

        # Should succeed with empty historical data
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["daily_performance"] == []

    @pytest.mark.asyncio
    async def test_get_performance_manager_not_initialized(self):
        """Test error when portfolio manager not initialized"""
        with patch('app.main.portfolio_manager', None):
            response = self.client.get("/api/v1/performance")

        assert response.status_code == 503
        assert "not initialized" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_performance_calculator_not_initialized(self):
        """Test error when performance calculator not initialized"""
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = Mock()
        mock_manager.update_prices = AsyncMock()

        with patch('app.main.portfolio_manager', mock_manager), \
             patch('app.main.performance_calculator', None):
            response = self.client.get("/api/v1/performance")

        assert response.status_code == 503
        assert "calculator" in response.json()["detail"].lower()


class TestGetAssetPerformance:
    """Test get_asset_performance endpoint handler"""

    def setup_method(self):
        """Setup test client"""
        self.client = TestClient(app)

    @pytest.mark.asyncio
    async def test_get_asset_performance_success(self):
        """Test successful asset performance retrieval"""
        mock_portfolio = Mock(spec=Portfolio)

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()

        # Mock asset performance data
        asset_performances = [
            AssetPerformance(
                symbol="BTCUSDT",
                quantity=Decimal("0.5"),
                entry_price=Decimal("40000"),
                current_price=Decimal("45000"),
                current_price=Decimal("22500"),
                unrealized_pnl=Decimal("2500"),
                unrealized_pnl_pct=Decimal("12.5"),
                allocation_pct=Decimal("60.0")
            ),
            AssetPerformance(
                symbol="ETHUSDT",
                quantity=Decimal("5.0"),
                entry_price=Decimal("2500"),
                current_price=Decimal("3000"),
                current_price=Decimal("15000"),
                unrealized_pnl=Decimal("2500"),
                unrealized_pnl_pct=Decimal("20.0"),
                allocation_pct=Decimal("40.0")
            )
        ]

        mock_manager.get_asset_performance.return_value = asset_performances

        with patch('app.main.portfolio_manager', mock_manager):
            response = self.client.get("/api/v1/performance/assets?portfolio_id=test")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["portfolio_id"] == "test"
        assert len(data["assets"]) == 2

        # Verify first asset
        btc_asset = data["assets"][0]
        assert btc_asset["symbol"] == "BTCUSDT"
        assert btc_asset["quantity"] == "0.5"
        assert btc_asset["unrealized_pnl"] == "2500"
        assert btc_asset["return_pct"] == "12.5"

        # Verify prices were updated
        mock_manager.update_prices.assert_called_once_with("test")

    @pytest.mark.asyncio
    async def test_get_asset_performance_default_portfolio(self):
        """Test asset performance with default portfolio"""
        mock_portfolio = Mock(spec=Portfolio)

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()
        mock_manager.get_asset_performance.return_value = []

        with patch('app.main.portfolio_manager', mock_manager):
            response = self.client.get("/api/v1/performance/assets")

        assert response.status_code == 200
        data = response.json()
        assert data["portfolio_id"] == "default"
        mock_manager.get_portfolio.assert_called_once_with("default")

    @pytest.mark.asyncio
    async def test_get_asset_performance_empty_portfolio(self):
        """Test asset performance with no assets"""
        mock_portfolio = Mock(spec=Portfolio)

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()
        mock_manager.get_asset_performance.return_value = []

        with patch('app.main.portfolio_manager', mock_manager):
            response = self.client.get("/api/v1/performance/assets?portfolio_id=test")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["assets"]) == 0

    @pytest.mark.asyncio
    async def test_get_asset_performance_portfolio_not_found(self):
        """Test error when portfolio doesn't exist"""
        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = None

        with patch('app.main.portfolio_manager', mock_manager):
            response = self.client.get("/api/v1/performance/assets?portfolio_id=nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_asset_performance_single_asset(self):
        """Test asset performance with single asset"""
        mock_portfolio = Mock(spec=Portfolio)

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()

        asset_performance = [
            AssetPerformance(
                symbol="BTCUSDT",
                quantity=Decimal("1.0"),
                entry_price=Decimal("40000"),
                current_price=Decimal("42000"),
                current_price=Decimal("42000"),
                unrealized_pnl=Decimal("2000"),
                unrealized_pnl_pct=Decimal("5.0"),
                allocation_pct=Decimal("100.0")
            )
        ]

        mock_manager.get_asset_performance.return_value = asset_performance

        with patch('app.main.portfolio_manager', mock_manager):
            response = self.client.get("/api/v1/performance/assets?portfolio_id=test")

        assert response.status_code == 200
        data = response.json()
        assert len(data["assets"]) == 1
        assert data["assets"][0]["allocation_pct"] == "100.0"

    @pytest.mark.asyncio
    async def test_get_asset_performance_negative_returns(self):
        """Test asset performance with negative returns"""
        mock_portfolio = Mock(spec=Portfolio)

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()

        asset_performance = [
            AssetPerformance(
                symbol="BTCUSDT",
                quantity=Decimal("1.0"),
                entry_price=Decimal("50000"),
                current_price=Decimal("45000"),
                current_price=Decimal("45000"),
                unrealized_pnl=Decimal("-5000"),
                unrealized_pnl_pct=Decimal("-10.0"),
                allocation_pct=Decimal("100.0")
            )
        ]

        mock_manager.get_asset_performance.return_value = asset_performance

        with patch('app.main.portfolio_manager', mock_manager):
            response = self.client.get("/api/v1/performance/assets?portfolio_id=test")

        assert response.status_code == 200
        data = response.json()
        assert data["assets"][0]["unrealized_pnl"] == "-5000"
        assert data["assets"][0]["return_pct"] == "-10.0"

    @pytest.mark.asyncio
    async def test_get_asset_performance_manager_not_initialized(self):
        """Test error when portfolio manager not initialized"""
        with patch('app.main.portfolio_manager', None):
            response = self.client.get("/api/v1/performance/assets")

        assert response.status_code == 503
        assert "not initialized" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_asset_performance_multiple_assets_sorted(self):
        """Test asset performance with multiple assets in order"""
        mock_portfolio = Mock(spec=Portfolio)

        mock_manager = Mock()
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()

        asset_performances = [
            AssetPerformance(
                symbol="BTCUSDT",
                quantity=Decimal("0.5"),
                entry_price=Decimal("40000"),
                current_price=Decimal("45000"),
                current_price=Decimal("22500"),
                unrealized_pnl=Decimal("2500"),
                unrealized_pnl_pct=Decimal("12.5"),
                allocation_pct=Decimal("45.0")
            ),
            AssetPerformance(
                symbol="ETHUSDT",
                quantity=Decimal("5.0"),
                entry_price=Decimal("2500"),
                current_price=Decimal("3000"),
                current_price=Decimal("15000"),
                unrealized_pnl=Decimal("2500"),
                unrealized_pnl_pct=Decimal("20.0"),
                allocation_pct=Decimal("30.0")
            ),
            AssetPerformance(
                symbol="BNBUSDT",
                quantity=Decimal("25.0"),
                entry_price=Decimal("400"),
                current_price=Decimal("500"),
                current_price=Decimal("12500"),
                unrealized_pnl=Decimal("2500"),
                unrealized_pnl_pct=Decimal("25.0"),
                allocation_pct=Decimal("25.0")
            )
        ]

        mock_manager.get_asset_performance.return_value = asset_performances

        with patch('app.main.portfolio_manager', mock_manager):
            response = self.client.get("/api/v1/performance/assets?portfolio_id=test")

        assert response.status_code == 200
        data = response.json()
        assert len(data["assets"]) == 3

        # Verify all symbols are present
        symbols = [asset["symbol"] for asset in data["assets"]]
        assert "BTCUSDT" in symbols
        assert "ETHUSDT" in symbols
        assert "BNBUSDT" in symbols
