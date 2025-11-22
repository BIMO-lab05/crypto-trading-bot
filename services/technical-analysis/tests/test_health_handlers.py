"""
Tests for Health Check Handlers
Coverage target: health.py lines 19-22, 35-38
"""

import pytest
from unittest.mock import AsyncMock, patch
from app.handlers.health import health_check, readiness_check


class TestHealthCheck:
    """Test health check endpoint handler"""
    
    @pytest.mark.asyncio
    async def test_health_check_when_market_data_healthy(self):
        """Test health check returns healthy when market data service is up"""
        with patch('app.handlers.health.get_fetcher') as mock_get_fetcher:
            # Mock fetcher health check to return True
            mock_fetcher = AsyncMock()
            mock_fetcher.health_check = AsyncMock(return_value=True)
            mock_get_fetcher.return_value = mock_fetcher
            
            # Call health check
            result = await health_check()
            
            # Verify response
            assert result.status == "healthy"
            assert result.service == "technical-analysis"
            assert result.market_data_connection is True
            assert result.timestamp > 0
    
    @pytest.mark.asyncio
    async def test_health_check_when_market_data_unhealthy(self):
        """Test health check returns healthy even when market data is down"""
        with patch('app.handlers.health.get_fetcher') as mock_get_fetcher:
            # Mock fetcher health check to return False
            mock_fetcher = AsyncMock()
            mock_fetcher.health_check = AsyncMock(return_value=False)
            mock_get_fetcher.return_value = mock_fetcher
            
            # Call health check
            result = await health_check()
            
            # Verify response - service still reports healthy
            assert result.status == "healthy"
            assert result.service == "technical-analysis"
            assert result.market_data_connection is False
            assert result.timestamp > 0


class TestReadinessCheck:
    """Test readiness check endpoint handler"""
    
    @pytest.mark.asyncio
    async def test_readiness_check_when_dependencies_ready(self):
        """Test readiness check returns ready when all dependencies are healthy"""
        with patch('app.handlers.health.get_fetcher') as mock_get_fetcher:
            # Mock fetcher health check to return True
            mock_fetcher = AsyncMock()
            mock_fetcher.health_check = AsyncMock(return_value=True)
            mock_get_fetcher.return_value = mock_fetcher
            
            # Call readiness check
            result = await readiness_check()
            
            # Verify response
            assert result.status == "ready"
            assert result.service == "technical-analysis"
            assert result.dependencies["market_data_service"] is True
            assert result.timestamp > 0
    
    @pytest.mark.asyncio
    async def test_readiness_check_when_dependencies_not_ready(self):
        """Test readiness check returns not_ready when dependencies are down"""
        with patch('app.handlers.health.get_fetcher') as mock_get_fetcher:
            # Mock fetcher health check to return False
            mock_fetcher = AsyncMock()
            mock_fetcher.health_check = AsyncMock(return_value=False)
            mock_get_fetcher.return_value = mock_fetcher
            
            # Call readiness check
            result = await readiness_check()
            
            # Verify response
            assert result.status == "not_ready"
            assert result.service == "technical-analysis"
            assert result.dependencies["market_data_service"] is False
            assert result.timestamp > 0
