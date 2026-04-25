"""
Basic Handler Coverage Tests
Purpose: Quick tests to boost handler coverage

UPDATED 2025-12-03: Tests simplified to check handler imports and basic functionality.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from app.models import HealthResponse, TradingControlResponse


@pytest.mark.asyncio
async def test_health_check_handler():
    """Test health check endpoint"""
    from app.handlers import health

    # Mock dependencies
    mock_health_monitor = Mock()
    mock_health = Mock()
    mock_health.status = Mock(value="healthy")
    mock_health.dependencies = {}
    mock_health.metrics = {}
    mock_health_monitor.get_cached_health = AsyncMock(return_value=mock_health)

    with patch('app.handlers.health.get_health_monitor', return_value=mock_health_monitor):
        result = await health.health_check()

    assert isinstance(result, HealthResponse)


@pytest.mark.asyncio
async def test_trading_control_start():
    """Test start trading

    UPDATED 2025-12-03: Check success field instead of status.
    """
    from app.handlers import trading_control

    mock_trader = Mock()
    mock_trader.is_running = False
    mock_trader.start = AsyncMock(return_value=True)

    with patch('app.handlers.trading_control.get_auto_trader', return_value=mock_trader):
        result = await trading_control.start_trading()

    assert isinstance(result, TradingControlResponse)
    assert result.success is True


@pytest.mark.asyncio
async def test_trading_control_stop():
    """Test stop trading

    UPDATED 2025-12-03: Check success field instead of status.
    """
    from app.handlers import trading_control

    mock_trader = Mock()
    mock_trader.is_running = True
    mock_trader.stop = AsyncMock()

    with patch('app.handlers.trading_control.get_auto_trader', return_value=mock_trader):
        result = await trading_control.stop_trading()

    assert isinstance(result, TradingControlResponse)
    assert result.success is True


@pytest.mark.asyncio
async def test_phase1_get_metrics():
    """Test get phase1 metrics endpoint"""
    from app.handlers import phase1

    # The phase1 metrics now comes from Phase1MetricsProvider
    result = await phase1.get_phase1_metrics_endpoint(hours=24)

    # Should return a dict with expected structure
    assert isinstance(result, dict)
    # Check for either 'data' wrapper or direct 'period_hours' key
    if "data" in result:
        assert "period_hours" in result["data"]
    else:
        assert "period_hours" in result
