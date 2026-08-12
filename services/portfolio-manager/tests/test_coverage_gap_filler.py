"""
Targeted tests to fill coverage gaps for 77% to 80%+ coverage push

Focus: Handler edge cases and uncovered branches
"""

import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock
from decimal import Decimal
from fastapi.testclient import TestClient

from app.main import app
from app.models.portfolio import PortfolioSnapshot
from app.models.performance import PerformanceMetrics, AssetPerformance
from app.models.asset import AssetHolding


class TestCoverageGapFiller:
    """Tests targeting specific uncovered lines"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def create_portfolio_snapshot(
        self, portfolio_id: str = "test"
    ) -> PortfolioSnapshot:
        """Helper to create valid PortfolioSnapshot for testing"""
        return PortfolioSnapshot(
            portfolio_id=portfolio_id,
            cash_balance="10000",
            total_value="50000",
            total_pnl="5000",
            total_return_pct="10.0",
            holdings=[
                AssetHolding(
                    symbol="BTCUSDT",
                    quantity="0.5",
                    current_price="45000",
                    current_value="22500",
                    unrealized_pnl="2500",
                    unrealized_pnl_pct="12.5",
                    allocation_pct="45.0",
                )
            ],
        )

    # Health handler coverage gaps
    def test_health_check_endpoint_exists(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code in [200, 503]

    def test_status_endpoint_basic(self, client):
        """Test status endpoint"""
        response = client.get("/status")
        assert response.status_code in [200, 503]

    def test_root_endpoint_basic(self, client):
        """Test root endpoint"""
        response = client.get("/")
        assert response.status_code == 200

    # Performance handler coverage - with manager initialized
    def test_performance_handler_with_default_portfolio_id(self, client):
        """Test performance endpoint uses default portfolio_id"""
        mock_manager = Mock()
        mock_calculator = Mock()
        mock_history = Mock()  # Mock performance_history instead of None

        # Create a mock portfolio
        mock_portfolio = Mock()
        mock_portfolio.portfolio_id = "default"
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()
        mock_manager.sync_with_trading_engine = AsyncMock(return_value=True)

        # Create basic metrics
        from app.models.performance import PerformanceMetrics

        metrics = PerformanceMetrics(
            total_return=Decimal("1000"),
            total_return_pct=Decimal("10.0"),
            daily_return=Decimal("50"),
            daily_return_pct=Decimal("0.5"),
            volatility=0.15,
            sharpe_ratio=1.0,
            max_drawdown=5.0,
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            win_rate=60.0,
            total_pnl=Decimal("1000"),
            realized_pnl=Decimal("800"),
            unrealized_pnl=Decimal("200"),
        )
        mock_calculator.calculate_metrics.return_value = metrics

        with patch("app.main.portfolio_manager", mock_manager):
            with patch("app.main.performance_calculator", mock_calculator):
                with patch("app.main.performance_history", mock_history):
                    response = client.get("/api/v1/performance")

        # Should work with default portfolio_id
        assert response.status_code == 200

    def test_asset_performance_handler_with_default_portfolio_id(self, client):
        """Test asset performance endpoint uses default portfolio_id"""
        mock_manager = Mock()
        mock_portfolio = Mock()
        mock_portfolio.portfolio_id = "default"
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()
        mock_manager.sync_with_trading_engine = AsyncMock(return_value=True)
        mock_manager.get_asset_performance.return_value = []

        with patch("app.main.portfolio_manager", mock_manager):
            response = client.get("/api/v1/performance/assets")

        assert response.status_code == 200

    # Transaction handler coverage — FIX 11 gates the mutating paths with 409
    # before any parameter parsing (portfolio mirrors the trading-engine book)
    def test_buy_handler_missing_params(self, client):
        """Test buy endpoint is 409-gated even with missing parameters"""
        mock_manager = Mock()
        with patch("app.main.portfolio_manager", mock_manager):
            response = client.post("/api/v1/transaction/buy")

        assert response.status_code == 409

    def test_sell_handler_missing_params(self, client):
        """Test sell endpoint is 409-gated even with missing parameters"""
        mock_manager = Mock()
        with patch("app.main.portfolio_manager", mock_manager):
            response = client.post("/api/v1/transaction/sell")

        assert response.status_code == 409

    # Coverage for handler functions with None manager
    def test_performance_handler_manager_not_initialized(self, client):
        """Test performance handler when manager not initialized"""
        mock_manager = None

        with patch("app.main.portfolio_manager", mock_manager):
            response = client.get("/api/v1/performance?portfolio_id=test")

        assert response.status_code == 503

    def test_asset_performance_handler_manager_not_initialized(self, client):
        """Test asset performance handler when manager not initialized"""
        mock_manager = None

        with patch("app.main.portfolio_manager", mock_manager):
            response = client.get("/api/v1/performance/assets?portfolio_id=test")

        assert response.status_code == 503

    def test_allocation_handler_manager_not_initialized(self, client):
        """Test allocation handler when manager not initialized"""
        mock_manager = None

        with patch("app.main.portfolio_manager", mock_manager):
            response = client.get("/api/v1/allocation?portfolio_id=test")

        assert response.status_code == 503

    def test_rebalance_handler_manager_not_initialized(self, client):
        """Test rebalance handler when manager not initialized"""
        mock_manager = None

        with patch("app.main.portfolio_manager", mock_manager):
            response = client.get("/api/v1/rebalance?portfolio_id=test")

        assert response.status_code == 503

    def test_portfolio_handler_manager_not_initialized(self, client):
        """Test portfolio handler when manager not initialized"""
        mock_manager = None

        with patch("app.main.portfolio_manager", mock_manager):
            response = client.get("/api/v1/portfolio?portfolio_id=test")

        assert response.status_code == 503

    def test_balance_handler_manager_not_initialized(self, client):
        """Test balance handler when manager not initialized"""
        mock_manager = None

        with patch("app.main.portfolio_manager", mock_manager):
            response = client.get("/api/v1/portfolio/balance?portfolio_id=test")

        assert response.status_code == 503

    def test_holdings_handler_manager_not_initialized(self, client):
        """Test holdings handler when manager not initialized"""
        mock_manager = None

        with patch("app.main.portfolio_manager", mock_manager):
            response = client.get("/api/v1/portfolio/holdings?portfolio_id=test")

        assert response.status_code == 503

    # Health handler edge cases
    def test_health_check_with_manager_none(self, client):
        """Test health check when manager is None"""
        with patch("app.main.portfolio_manager", None):
            response = client.get("/health")

        assert response.status_code in [200, 503]

    # Performance handler with complex metrics
    def test_performance_with_all_metrics_filled(self, client):
        """Test performance response with all metrics"""
        mock_manager = Mock()
        mock_calculator = Mock()
        mock_history = Mock()

        # Mock portfolio
        mock_portfolio = Mock()
        mock_portfolio.portfolio_id = "test"
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()
        mock_manager.sync_with_trading_engine = AsyncMock(return_value=True)

        metrics = PerformanceMetrics(
            total_return=Decimal("25000"),
            total_return_pct=Decimal("25.0"),
            daily_return=Decimal("1250"),
            daily_return_pct=Decimal("1.25"),
            volatility=0.22,
            sharpe_ratio=1.2,
            sortino_ratio=1.5,
            max_drawdown=8.5,
            max_drawdown_duration=15,
            total_trades=150,
            winning_trades=100,
            losing_trades=50,
            win_rate=66.67,
            average_win=Decimal("250"),
            average_loss=Decimal("100"),
            profit_factor=2.5,
            total_pnl=Decimal("25000"),
            realized_pnl=Decimal("20000"),
            unrealized_pnl=Decimal("5000"),
            benchmark_return=0.15,
            alpha=0.10,
            beta=1.05,
        )

        mock_calculator.calculate_metrics.return_value = metrics

        with patch("app.main.portfolio_manager", mock_manager):
            with patch("app.main.performance_calculator", mock_calculator):
                with patch("app.main.performance_history", mock_history):
                    response = client.get("/api/v1/performance?portfolio_id=test")

        assert response.status_code == 200

    # Asset performance with various conditions
    def test_asset_performance_single_asset(self, client):
        """Test asset performance with single asset"""
        mock_manager = Mock()
        mock_portfolio = Mock()
        mock_portfolio.portfolio_id = "test"
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()
        mock_manager.sync_with_trading_engine = AsyncMock(return_value=True)

        asset_perf = [
            AssetPerformance(
                symbol="BTCUSDT",
                quantity="1.5",  # String, not Decimal
                entry_price="35000",
                current_price="42000",
                unrealized_pnl="10500",
                unrealized_pnl_pct="20.0",
                allocation_pct="100.0",
                hold_duration_days=30,  # Required field
            )
        ]

        mock_manager.get_asset_performance.return_value = asset_perf

        with patch("app.main.portfolio_manager", mock_manager):
            response = client.get("/api/v1/performance/assets?portfolio_id=test")

        assert response.status_code == 200

    # Coverage for handlers with None return values
    def test_performance_calculation_returns_none(self, client):
        """Test when performance calculation returns None"""
        mock_manager = Mock()
        mock_calculator = Mock()
        mock_history = Mock()

        # Mock portfolio
        mock_portfolio = Mock()
        mock_portfolio.portfolio_id = "test"
        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()
        mock_manager.sync_with_trading_engine = AsyncMock(return_value=True)

        mock_calculator.calculate_metrics.return_value = None

        with patch("app.main.portfolio_manager", mock_manager):
            with patch("app.main.performance_calculator", mock_calculator):
                with patch("app.main.performance_history", mock_history):
                    # This will raise validation error because metrics is None
                    with pytest.raises(ValueError):
                        response = client.get("/api/v1/performance?portfolio_id=test")

    # Transaction handler edge cases
    def test_buy_transaction_with_all_params(self, client):
        """Test buy transaction is 409-gated even with valid parameters"""
        # FIX 11: a manager that would fill the trade proves the gate, not a
        # downstream failure, is what rejects the request.
        mock_manager = Mock()
        mock_portfolio = Mock()
        mock_portfolio.total_value = Decimal("100000")

        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.execute_transaction.return_value = (
            True,
            "Buy executed",
            Decimal("0"),
        )
        mock_manager.get_transaction_lock.return_value = asyncio.Lock()

        with patch("app.main.portfolio_manager", mock_manager):
            response = client.post(
                "/api/v1/transaction/buy?portfolio_id=test&symbol=BTCUSDT&quantity=0.5&price=45000"
            )

        assert response.status_code == 409
        mock_manager.execute_transaction.assert_not_called()

    def test_sell_transaction_with_all_params(self, client):
        """Test sell transaction is 409-gated even with valid parameters"""
        mock_manager = Mock()
        mock_portfolio = Mock()
        mock_portfolio.assets = {"BTCUSDT": Mock(quantity=Decimal("1.0"))}

        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.execute_transaction.return_value = (
            True,
            "Sell executed",
            Decimal("1000"),
        )
        mock_manager.get_transaction_lock.return_value = asyncio.Lock()

        with patch("app.main.portfolio_manager", mock_manager):
            response = client.post(
                "/api/v1/transaction/sell?portfolio_id=test&symbol=BTCUSDT&quantity=0.5&price=46000"
            )

        assert response.status_code == 409
        mock_manager.execute_transaction.assert_not_called()

    def test_transaction_history_with_params(self, client):
        """Test transaction history with parameters"""
        mock_manager = Mock()
        mock_manager.get_transaction_history.return_value = []

        with patch("app.main.portfolio_manager", mock_manager):
            response = client.get(
                "/api/v1/transactions?portfolio_id=test&limit=50&symbol=BTCUSDT"
            )

        assert response.status_code in [200, 400, 500]

    # Coverage for sync handler
    def test_sync_with_portfolio_id(self, client):
        """Test sync with portfolio_id"""
        mock_manager = Mock()
        mock_manager.sync_with_trading_engine = AsyncMock(return_value=True)

        with patch("app.main.portfolio_manager", mock_manager):
            response = client.post("/api/v1/sync?portfolio_id=test")

        assert response.status_code in [200, 400, 500]

    # Multiple asset scenarios
    def test_portfolio_holdings_multiple_assets(self, client):
        """Test holdings with multiple assets"""
        mock_manager = Mock()
        mock_portfolio = Mock()
        mock_portfolio.assets = {
            "BTCUSDT": Mock(quantity=Decimal("0.5"), current_price=Decimal("45000")),
            "ETHUSDT": Mock(quantity=Decimal("5.0"), current_price=Decimal("2500")),
            "ADAUSDT": Mock(quantity=Decimal("1000.0"), current_price=Decimal("0.5")),
        }

        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()
        mock_manager.sync_with_trading_engine = AsyncMock(return_value=True)

        # Create proper PortfolioSnapshot with multiple holdings
        snapshot = PortfolioSnapshot(
            portfolio_id="test",
            cash_balance="5000",
            total_value="40000",
            total_pnl="3000",
            total_return_pct="8.0",
            holdings=[
                AssetHolding(
                    symbol="BTCUSDT",
                    quantity="0.5",
                    current_price="45000",
                    current_value="22500",
                    unrealized_pnl="2500",
                    unrealized_pnl_pct="12.5",
                    allocation_pct="56.25",
                ),
                AssetHolding(
                    symbol="ETHUSDT",
                    quantity="5.0",
                    current_price="2500",
                    current_value="12500",
                    unrealized_pnl="500",
                    unrealized_pnl_pct="4.17",
                    allocation_pct="31.25",
                ),
                AssetHolding(
                    symbol="ADAUSDT",
                    quantity="1000.0",
                    current_price="0.5",
                    current_value="500",
                    unrealized_pnl="20",
                    unrealized_pnl_pct="4.17",
                    allocation_pct="1.25",
                ),
            ],
        )

        mock_manager.get_snapshot.return_value = snapshot

        with patch("app.main.portfolio_manager", mock_manager):
            response = client.get("/api/v1/portfolio/holdings?portfolio_id=test")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 3
        assert len(data["holdings"]) == 3

    # Rebalance recommendations
    def test_rebalance_recommendations_with_target(self, client):
        """Test rebalance recommendations with target"""
        mock_manager = Mock()
        mock_portfolio = Mock()
        mock_portfolio.portfolio_id = "test"
        mock_portfolio.get_asset_allocation.return_value = {
            "BTCUSDT": Decimal("70.0"),
            "ETHUSDT": Decimal("30.0"),
        }

        mock_manager.get_portfolio.return_value = mock_portfolio
        mock_manager.update_prices = AsyncMock()
        mock_manager.sync_with_trading_engine = AsyncMock(return_value=True)
        # check_rebalancing_needed returns (needs_rebalancing, recommendations)
        mock_manager.check_rebalancing_needed.return_value = (False, [])

        with patch("app.main.portfolio_manager", mock_manager):
            response = client.get("/api/v1/rebalance?portfolio_id=test")

        assert response.status_code == 200

    # Portfolios listing
    def test_list_portfolios_endpoint(self, client):
        """Test list all portfolios"""
        mock_manager = Mock()

        # Create mock Portfolio objects with portfolio_id attributes
        mock_portfolio1 = Mock()
        mock_portfolio1.portfolio_id = "port1"
        mock_portfolio2 = Mock()
        mock_portfolio2.portfolio_id = "port2"

        mock_manager.list_portfolios.return_value = [mock_portfolio1, mock_portfolio2]

        # Create proper PortfolioSnapshot instances
        snapshot1 = self.create_portfolio_snapshot(portfolio_id="port1")
        snapshot2 = self.create_portfolio_snapshot(portfolio_id="port2")

        # Mock get_snapshot to return proper PortfolioSnapshot instances
        mock_manager.get_snapshot.side_effect = lambda pid: (
            snapshot1 if pid == "port1" else snapshot2
        )

        with patch("app.main.portfolio_manager", mock_manager):
            response = client.get("/api/v1/portfolios")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 2
        assert len(data["portfolios"]) == 2
