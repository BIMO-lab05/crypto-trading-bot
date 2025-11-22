"""
API Handler Tests for Portfolio Manager Service
Tests HTTP endpoints via FastAPI TestClient

Target: Boost coverage from 51% to 65%+ by testing untested handlers.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal


class TestHealthHandler:
    """Unit tests for health handler functions"""

    @pytest.mark.asyncio
    async def test_health_check_all_healthy(self):
        """Test health_check when all services are healthy"""
        with patch('app.handlers.health.check_service_health', new_callable=AsyncMock) as mock_health, \
             patch('app.handlers.health.settings') as mock_settings:
            mock_health.return_value = True
            mock_settings.use_database = False
            mock_settings.trading_engine_url = "http://localhost:8001"
            mock_settings.market_data_url = "http://localhost:8005"

            from app.handlers.health import health_check
            result = await health_check()

            assert result.status == "healthy"
            assert result.trading_engine_connection is True
            assert result.market_data_connection is True

    @pytest.mark.asyncio
    async def test_health_check_services_down(self):
        """Test health_check when services are down"""
        with patch('app.handlers.health.check_service_health', new_callable=AsyncMock) as mock_health, \
             patch('app.handlers.health.settings') as mock_settings:
            mock_health.return_value = False
            mock_settings.use_database = False
            mock_settings.trading_engine_url = "http://localhost:8001"
            mock_settings.market_data_url = "http://localhost:8005"

            from app.handlers.health import health_check
            result = await health_check()

            assert result.status == "healthy"
            assert result.trading_engine_connection is False
            assert result.market_data_connection is False

    @pytest.mark.asyncio
    async def test_get_status_function(self):
        """Test get_status function directly"""
        with patch('app.handlers.health.get_portfolio_manager') as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.list_portfolios.return_value = [
                MagicMock(total_value=Decimal("10000"), assets=[]),
                MagicMock(total_value=Decimal("5000"), assets=["BTC"])
            ]
            mock_get_pm.return_value = mock_pm

            from app.handlers.health import get_status
            result = await get_status()

            assert result.status == "running"
            assert result.portfolio_count == 2
            assert result.active_positions == 1

    @pytest.mark.asyncio
    async def test_get_status_empty_portfolios(self):
        """Test get_status with no portfolios"""
        with patch('app.handlers.health.get_portfolio_manager') as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.list_portfolios.return_value = []
            mock_get_pm.return_value = mock_pm

            from app.handlers.health import get_status
            result = await get_status()

            assert result.status == "running"
            assert result.portfolio_count == 0


class TestPortfolioHandler:
    """Unit tests for portfolio handler functions"""

    @pytest.mark.asyncio
    async def test_get_portfolio_not_found(self):
        """Test get_portfolio raises 404 when not found"""
        from fastapi import HTTPException

        with patch('app.handlers.portfolio.get_portfolio_manager') as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.get_portfolio.return_value = None
            mock_get_pm.return_value = mock_pm

            from app.handlers.portfolio import get_portfolio

            with pytest.raises(HTTPException) as exc_info:
                await get_portfolio("nonexistent")

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_balance_success(self):
        """Test get_balance returns balance info"""
        with patch('app.handlers.portfolio.get_portfolio_manager') as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.get_portfolio.return_value = MagicMock(
                portfolio_id="default",
                cash_balance=Decimal("10000"),
                total_value=Decimal("15000"),
                unrealized_pnl=Decimal("500"),
                realized_pnl=Decimal("200"),
                total_pnl=Decimal("700"),
                total_return_pct=Decimal("7.0")
            )
            mock_pm.update_prices = AsyncMock()
            mock_get_pm.return_value = mock_pm

            from app.handlers.portfolio import get_balance
            result = await get_balance("default")

            assert result.success is True
            assert result.cash_balance == "10000"

    @pytest.mark.asyncio
    async def test_get_balance_not_found(self):
        """Test get_balance raises 404 when portfolio not found"""
        from fastapi import HTTPException

        with patch('app.handlers.portfolio.get_portfolio_manager') as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.get_portfolio.return_value = None
            mock_get_pm.return_value = mock_pm

            from app.handlers.portfolio import get_balance

            with pytest.raises(HTTPException) as exc_info:
                await get_balance("nonexistent")

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_holdings_not_found(self):
        """Test get_holdings raises 404 when portfolio not found"""
        from fastapi import HTTPException

        with patch('app.handlers.portfolio.get_portfolio_manager') as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.get_portfolio.return_value = None
            mock_get_pm.return_value = mock_pm

            from app.handlers.portfolio import get_holdings

            with pytest.raises(HTTPException) as exc_info:
                await get_holdings("nonexistent")

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_sync_with_trading_engine_success(self):
        """Test sync_with_trading_engine success"""
        with patch('app.handlers.portfolio.get_portfolio_manager') as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.get_portfolio.return_value = MagicMock(portfolio_id="default")
            mock_pm.sync_with_trading_engine = AsyncMock(return_value=True)
            mock_get_pm.return_value = mock_pm

            from app.handlers.portfolio import sync_with_trading_engine
            result = await sync_with_trading_engine("default")

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_sync_with_trading_engine_failure(self):
        """Test sync_with_trading_engine failure"""
        from fastapi import HTTPException

        with patch('app.handlers.portfolio.get_portfolio_manager') as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.get_portfolio.return_value = MagicMock(portfolio_id="default")
            mock_pm.sync_with_trading_engine = AsyncMock(return_value=False)
            mock_get_pm.return_value = mock_pm

            from app.handlers.portfolio import sync_with_trading_engine

            with pytest.raises(HTTPException) as exc_info:
                await sync_with_trading_engine("default")

            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_sync_not_found(self):
        """Test sync raises 404 when portfolio not found"""
        from fastapi import HTTPException

        with patch('app.handlers.portfolio.get_portfolio_manager') as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.get_portfolio.return_value = None
            mock_get_pm.return_value = mock_pm

            from app.handlers.portfolio import sync_with_trading_engine

            with pytest.raises(HTTPException) as exc_info:
                await sync_with_trading_engine("nonexistent")

            assert exc_info.value.status_code == 404


class TestPerformanceHandler:
    """Unit tests for performance handler functions"""

    @pytest.mark.asyncio
    async def test_get_asset_performance_success(self):
        """Test get_asset_performance returns asset metrics"""
        with patch('app.handlers.performance.get_portfolio_manager') as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.get_portfolio.return_value = MagicMock(portfolio_id="default")
            mock_pm.update_prices = AsyncMock()
            mock_pm.get_asset_performance.return_value = []
            mock_get_pm.return_value = mock_pm

            from app.handlers.performance import get_asset_performance
            result = await get_asset_performance("default")

            assert result.success is True
            assert result.portfolio_id == "default"

    @pytest.mark.asyncio
    async def test_get_asset_performance_not_found(self):
        """Test get_asset_performance raises 404"""
        from fastapi import HTTPException

        with patch('app.handlers.performance.get_portfolio_manager') as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.get_portfolio.return_value = None
            mock_get_pm.return_value = mock_pm

            from app.handlers.performance import get_asset_performance

            with pytest.raises(HTTPException) as exc_info:
                await get_asset_performance("nonexistent")

            assert exc_info.value.status_code == 404


class TestAllocationHandler:
    """Unit tests for allocation handler functions"""

    @pytest.mark.asyncio
    async def test_get_allocation_not_found(self):
        """Test get_allocation raises 404"""
        from fastapi import HTTPException

        with patch('app.handlers.allocation.get_portfolio_manager') as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.get_portfolio.return_value = None
            mock_get_pm.return_value = mock_pm

            from app.handlers.allocation import get_allocation

            with pytest.raises(HTTPException) as exc_info:
                await get_allocation("nonexistent")

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_rebalance_recommendations_not_found(self):
        """Test get_rebalance_recommendations raises 404"""
        from fastapi import HTTPException

        with patch('app.handlers.allocation.get_portfolio_manager') as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.get_portfolio.return_value = None
            mock_get_pm.return_value = mock_pm

            from app.handlers.allocation import get_rebalance_recommendations

            with pytest.raises(HTTPException) as exc_info:
                await get_rebalance_recommendations("nonexistent")

            assert exc_info.value.status_code == 404


class TestPortfolioManagerNotInitialized:
    """Test error handling when portfolio manager is not initialized"""

    @pytest.mark.asyncio
    async def test_health_handler_pm_not_initialized(self):
        """Test health handler when portfolio_manager is None"""
        from fastapi import HTTPException

        with patch('app.handlers.health.get_portfolio_manager') as mock_get_pm:
            mock_get_pm.side_effect = HTTPException(
                status_code=503, detail="Portfolio Manager not initialized"
            )

            from app.handlers.health import get_status

            with pytest.raises(HTTPException) as exc_info:
                await get_status()

            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_portfolio_handler_pm_not_initialized(self):
        """Test portfolio handler when portfolio_manager is None"""
        from fastapi import HTTPException

        with patch('app.handlers.portfolio.get_portfolio_manager') as mock_get_pm:
            mock_get_pm.side_effect = HTTPException(
                status_code=503, detail="Portfolio Manager not initialized"
            )

            from app.handlers.portfolio import get_portfolio

            with pytest.raises(HTTPException) as exc_info:
                await get_portfolio("default")

            assert exc_info.value.status_code == 503


class TestEdgeCases:
    """Edge case and boundary tests"""

    @pytest.mark.asyncio
    async def test_list_portfolios_with_none_snapshot(self):
        """Test list_portfolios handles None snapshots"""
        with patch('app.handlers.portfolio.get_portfolio_manager') as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.list_portfolios.return_value = [
                MagicMock(portfolio_id="default"),
                MagicMock(portfolio_id="test")
            ]
            mock_pm.get_snapshot.side_effect = [None, None]
            mock_get_pm.return_value = mock_pm

            from app.handlers.portfolio import list_portfolios
            result = await list_portfolios()

            assert result.success is True
            assert result.count == 0

    @pytest.mark.asyncio
    async def test_get_status_with_large_portfolio(self):
        """Test get_status with many assets"""
        with patch('app.handlers.health.get_portfolio_manager') as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.list_portfolios.return_value = [
                MagicMock(
                    total_value=Decimal("1000000"),
                    assets=["BTC", "ETH", "SOL", "XRP", "ADA"]
                )
            ]
            mock_get_pm.return_value = mock_pm

            from app.handlers.health import get_status
            result = await get_status()

            assert result.status == "running"
            assert result.active_positions == 5

    @pytest.mark.asyncio
    async def test_allocation_handler_pm_not_initialized(self):
        """Test allocation handler when portfolio_manager is None"""
        from fastapi import HTTPException

        with patch('app.handlers.allocation.get_portfolio_manager') as mock_get_pm:
            mock_get_pm.side_effect = HTTPException(
                status_code=503, detail="Portfolio Manager not initialized"
            )

            from app.handlers.allocation import get_allocation

            with pytest.raises(HTTPException) as exc_info:
                await get_allocation("default")

            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_performance_handler_pm_not_initialized(self):
        """Test performance handler when portfolio_manager is None"""
        from fastapi import HTTPException

        with patch('app.handlers.performance.get_portfolio_manager') as mock_get_pm:
            mock_get_pm.side_effect = HTTPException(
                status_code=503, detail="Portfolio Manager not initialized"
            )

            from app.handlers.performance import get_asset_performance

            with pytest.raises(HTTPException) as exc_info:
                await get_asset_performance("default")

            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_get_balance_with_zero_values(self):
        """Test get_balance with zero values"""
        with patch('app.handlers.portfolio.get_portfolio_manager') as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.get_portfolio.return_value = MagicMock(
                portfolio_id="default",
                cash_balance=Decimal("0"),
                total_value=Decimal("0"),
                unrealized_pnl=Decimal("0"),
                realized_pnl=Decimal("0"),
                total_pnl=Decimal("0"),
                total_return_pct=Decimal("0")
            )
            mock_pm.update_prices = AsyncMock()
            mock_get_pm.return_value = mock_pm

            from app.handlers.portfolio import get_balance
            result = await get_balance("default")

            assert result.success is True
            assert result.cash_balance == "0"

    @pytest.mark.asyncio
    async def test_get_balance_with_negative_pnl(self):
        """Test get_balance with negative P&L"""
        with patch('app.handlers.portfolio.get_portfolio_manager') as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.get_portfolio.return_value = MagicMock(
                portfolio_id="default",
                cash_balance=Decimal("5000"),
                total_value=Decimal("8000"),
                unrealized_pnl=Decimal("-2000"),
                realized_pnl=Decimal("-500"),
                total_pnl=Decimal("-2500"),
                total_return_pct=Decimal("-25.0")
            )
            mock_pm.update_prices = AsyncMock()
            mock_get_pm.return_value = mock_pm

            from app.handlers.portfolio import get_balance
            result = await get_balance("default")

            assert result.success is True
            assert result.unrealized_pnl == "-2000"

    @pytest.mark.asyncio
    async def test_get_status_single_portfolio(self):
        """Test get_status with single portfolio"""
        with patch('app.handlers.health.get_portfolio_manager') as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.list_portfolios.return_value = [
                MagicMock(total_value=Decimal("10000"), assets=["BTC", "ETH"])
            ]
            mock_get_pm.return_value = mock_pm

            from app.handlers.health import get_status
            result = await get_status()

            assert result.status == "running"
            assert result.portfolio_count == 1
            assert result.active_positions == 2

    @pytest.mark.asyncio
    async def test_health_check_partial_connectivity(self):
        """Test health_check with mixed service connectivity"""
        with patch('app.handlers.health.check_service_health', new_callable=AsyncMock) as mock_health, \
             patch('app.handlers.health.settings') as mock_settings:
            mock_health.side_effect = [True, False]
            mock_settings.use_database = False
            mock_settings.trading_engine_url = "http://localhost:8001"
            mock_settings.market_data_url = "http://localhost:8005"

            from app.handlers.health import health_check
            result = await health_check()

            assert result.status == "healthy"
            assert result.trading_engine_connection is True
            assert result.market_data_connection is False

    @pytest.mark.asyncio
    async def test_list_portfolios_empty(self):
        """Test list_portfolios with no portfolios"""
        with patch('app.handlers.portfolio.get_portfolio_manager') as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.list_portfolios.return_value = []
            mock_get_pm.return_value = mock_pm

            from app.handlers.portfolio import list_portfolios
            result = await list_portfolios()

            assert result.success is True
            assert result.count == 0
            assert result.portfolios == []
