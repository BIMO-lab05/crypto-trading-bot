"""
Market Data Service - Fetcher Tests
Purpose: Test data fetching from Bybit Connector
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from app.fetcher import BybitDataFetcher


class TestBybitDataFetcher:
    """Test Bybit data fetcher"""
    
    @pytest.mark.asyncio
    async def test_fetcher_initialization(self):
        """Test fetcher initializes correctly"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")
        assert fetcher.base_url == "http://test:8002"
        assert fetcher.client is not None
        await fetcher.close()
    
    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test health check returns True when service is healthy"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")
        
        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch.object(fetcher.client, 'get', return_value=mock_response):
            result = await fetcher.health_check()
            assert result is True
        
        await fetcher.close()
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test health check returns False on error"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")
        
        with patch.object(fetcher.client, 'get', side_effect=Exception("Connection error")):
            result = await fetcher.health_check()
            assert result is False
        
        await fetcher.close()
    
    @pytest.mark.asyncio
    async def test_get_kline_success(self):
        """Test fetching kline data successfully"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")
        
        # Mock response data
        mock_data = {
            "success": True,
            "data": {
                "list": [
                    ["1234567890000", "50000", "51000", "49000", "50500", "123.456", "6172800"],
                    ["1234567880000", "49500", "50000", "49000", "49800", "100.000", "4980000"]
                ]
            }
        }
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(fetcher.client, 'get', return_value=mock_response):
            klines = await fetcher.get_kline(symbol="BTCUSDT", interval="60", limit=2)
            
            assert len(klines) == 2
            assert klines[0]["timestamp"] == 1234567890000
            assert klines[0]["open"] == "50000"
            assert klines[0]["close"] == "50500"
            assert klines[0]["volume"] == "123.456"
        
        await fetcher.close()
    
    @pytest.mark.asyncio
    async def test_get_kline_empty_response(self):
        """Test handling empty kline response"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")
        
        mock_data = {"success": True, "data": {"list": []}}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(fetcher.client, 'get', return_value=mock_response):
            klines = await fetcher.get_kline(symbol="BTCUSDT", interval="60")
            assert klines == []
        
        await fetcher.close()
    
    @pytest.mark.asyncio
    async def test_get_ticker_success(self):
        """Test fetching ticker data successfully"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")
        
        mock_data = {
            "success": True,
            "data": {
                "list": [{
                    "symbol": "BTCUSDT",
                    "lastPrice": "50000.00",
                    "bid1Price": "49999.00",
                    "ask1Price": "50001.00",
                    "highPrice24h": "51000.00",
                    "lowPrice24h": "49000.00",
                    "volume24h": "1000.00",
                    "turnover24h": "50000000.00",
                    "price24hPcnt": "0.0200"
                }]
            }
        }
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(fetcher.client, 'get', return_value=mock_response):
            ticker = await fetcher.get_ticker(symbol="BTCUSDT")
            
            assert ticker is not None
            assert ticker["symbol"] == "BTCUSDT"
            assert ticker["last_price"] == "50000.00"
            assert ticker["volume_24h"] == "1000.00"
        
        await fetcher.close()
    
    @pytest.mark.asyncio
    async def test_get_ticker_not_found(self):
        """Test handling ticker not found"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")
        
        mock_data = {"success": True, "data": {"list": []}}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(fetcher.client, 'get', return_value=mock_response):
            ticker = await fetcher.get_ticker(symbol="INVALID")
            assert ticker is None
        
        await fetcher.close()


# Fixtures
@pytest.fixture
def sample_kline_data():
    """Sample kline data for testing"""
    return [
        {
            "timestamp": 1234567890000,
            "open": "50000.00",
            "high": "51000.00",
            "low": "49000.00",
            "close": "50500.00",
            "volume": "123.456",
            "turnover": "6172800.00"
        }
    ]


@pytest.fixture
def sample_ticker_data():
    """Sample ticker data for testing"""
    return {
        "symbol": "BTCUSDT",
        "last_price": "50000.00",
        "bid_price": "49999.00",
        "ask_price": "50001.00",
        "high_24h": "51000.00",
        "low_24h": "49000.00",
        "volume_24h": "1000.00",
        "turnover_24h": "50000000.00",
        "price_change_24h": "0.0200"
    }
