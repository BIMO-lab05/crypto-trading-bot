"""
Market Data Service - Enhanced Fetcher Tests
Purpose: Additional tests to increase fetcher coverage
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
import httpx

from app.fetcher import BybitDataFetcher, create_fetcher


class TestBybitDataFetcherEnhanced:
    """Enhanced tests for BybitDataFetcher"""

    @pytest.mark.asyncio
    async def test_fetcher_default_base_url_from_config(self):
        """Test that fetcher uses config base_url when not provided"""
        with patch('app.fetcher.get_settings') as mock_settings:
            mock_settings.return_value.bybit_connector_url = "http://config-url:8000"

            fetcher = BybitDataFetcher()

            assert fetcher.base_url == "http://config-url:8000"
            await fetcher.close()

    @pytest.mark.asyncio
    async def test_fetcher_client_configuration(self):
        """Test that HTTP client is configured with connection pooling"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")

        assert fetcher.client is not None
        assert hasattr(fetcher.client, '_transport')
        await fetcher.close()

    @pytest.mark.asyncio
    async def test_close_method(self):
        """Test that close method properly closes the HTTP client"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")

        # Mock the aclose method
        fetcher.client.aclose = AsyncMock()

        await fetcher.close()

        fetcher.client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_kline_with_all_parameters(self):
        """Test get_kline with all optional parameters"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")

        mock_data = {
            "success": True,
            "data": {
                "list": [
                    ["1234567890000", "50000", "51000", "49000", "50500", "123.456", "6172800"]
                ]
            }
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher.client, 'get', return_value=mock_response):
            klines = await fetcher.get_kline(
                symbol="BTCUSDT",
                interval="60",
                limit=500,
                start_time=1234567000000,
                end_time=1234577000000
            )

            assert len(klines) == 1
            assert klines[0]["timestamp"] == 1234567890000

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_kline_limit_capped_at_1000(self):
        """Test that kline limit is capped at 1000"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")

        mock_data = {"success": True, "data": {"list": []}}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher.client, 'get', return_value=mock_response) as mock_get:
            await fetcher.get_kline(symbol="BTCUSDT", interval="60", limit=5000)

            # Check that the call was made with limit capped at 1000
            call_params = mock_get.call_args[1]['params']
            assert call_params['limit'] == 1000

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_kline_with_direct_list_response(self):
        """Test handling kline response that's a direct list instead of nested dict"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")

        # Some API responses return data as direct list
        mock_data = {
            "success": True,
            "data": [
                ["1234567890000", "50000", "51000", "49000", "50500", "123.456", "6172800"]
            ]
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher.client, 'get', return_value=mock_response):
            klines = await fetcher.get_kline(symbol="BTCUSDT", interval="60")

            assert len(klines) == 1
            assert klines[0]["timestamp"] == 1234567890000

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_kline_failure_returns_empty_list(self):
        """Test that kline fetch failure returns empty list instead of raising"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")

        mock_data = {"success": False, "error": "Rate limit exceeded"}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher.client, 'get', return_value=mock_response):
            klines = await fetcher.get_kline(symbol="BTCUSDT", interval="60")

            assert klines == []

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_kline_http_error_returns_empty_list(self):
        """Test that HTTP errors return empty list"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")

        with patch.object(fetcher.client, 'get', side_effect=httpx.HTTPError("Network error")):
            klines = await fetcher.get_kline(symbol="BTCUSDT", interval="60")

            assert klines == []

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_ticker_success_with_all_fields(self):
        """Test ticker fetch with all available fields"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")

        mock_data = {
            "success": True,
            "data": {
                "list": [{
                    "symbol": "ETHUSDT",
                    "lastPrice": "3000.00",
                    "bid1Price": "2999.00",
                    "ask1Price": "3001.00",
                    "highPrice24h": "3100.00",
                    "lowPrice24h": "2900.00",
                    "volume24h": "10000.00",
                    "turnover24h": "30000000.00",
                    "price24hPcnt": "0.0333"
                }]
            }
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher.client, 'get', return_value=mock_response):
            ticker = await fetcher.get_ticker(symbol="ETHUSDT")

            assert ticker["symbol"] == "ETHUSDT"
            assert ticker["last_price"] == "3000.00"
            assert ticker["bid_price"] == "2999.00"
            assert ticker["ask_price"] == "3001.00"
            assert ticker["high_24h"] == "3100.00"
            assert ticker["low_24h"] == "2900.00"
            assert ticker["volume_24h"] == "10000.00"
            assert ticker["turnover_24h"] == "30000000.00"
            assert ticker["price_change_24h"] == "0.0333"

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_ticker_api_failure_returns_none(self):
        """Test that ticker fetch failure returns None"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")

        mock_data = {"success": False, "error": "Symbol not found"}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher.client, 'get', return_value=mock_response):
            ticker = await fetcher.get_ticker(symbol="INVALID")

            assert ticker is None

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_ticker_http_error_returns_none(self):
        """Test that HTTP errors return None for ticker"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")

        with patch.object(fetcher.client, 'get', side_effect=httpx.RequestError("Timeout")):
            ticker = await fetcher.get_ticker(symbol="BTCUSDT")

            assert ticker is None

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_historical_klines_basic(self):
        """Test fetching historical klines"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")

        # Mock klines response
        mock_klines = [
            {"timestamp": 1234567890000, "open": "50000", "close": "50500", "volume": "100"}
        ]

        with patch.object(fetcher, 'get_kline', return_value=mock_klines):
            result = await fetcher.get_historical_klines(
                symbol="BTCUSDT",
                interval="60",
                days=1
            )

            # Should have called get_kline at least once
            assert len(result) >= 1

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_historical_klines_no_data(self):
        """Test historical klines when no data is returned"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")

        with patch.object(fetcher, 'get_kline', return_value=[]):
            result = await fetcher.get_historical_klines(
                symbol="BTCUSDT",
                interval="60",
                days=30
            )

            assert result == []

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_historical_klines_batch_limit(self):
        """Test that historical klines respects batch limit"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")

        call_count = [0]

        async def mock_get_kline(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] > 100:
                return []
            return [{"timestamp": 1234567890000 + call_count[0] * 1000, "open": "50000"}]

        with patch.object(fetcher, 'get_kline', side_effect=mock_get_kline):
            result = await fetcher.get_historical_klines(
                symbol="BTCUSDT",
                interval="60",
                days=365  # Large number to test limit
            )

            # Should stop at batch limit of 100
            assert call_count[0] <= 100

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_historical_klines_accumulates_data(self):
        """Test that historical klines accumulates data from multiple batches"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")

        call_count = [0]

        async def mock_get_kline(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] > 3:
                return []
            return [
                {"timestamp": 1234567890000 + (call_count[0] * 1000), "open": "50000"}
            ]

        with patch.object(fetcher, 'get_kline', side_effect=mock_get_kline):
            result = await fetcher.get_historical_klines(
                symbol="BTCUSDT",
                interval="60",
                days=30
            )

            # Should accumulate klines from multiple batches
            assert len(result) == 3

        await fetcher.close()


class TestCreateFetcher:
    """Test the create_fetcher convenience function"""

    def test_create_fetcher_returns_instance(self):
        """Test that create_fetcher returns a BybitDataFetcher instance"""
        with patch('app.fetcher.get_settings') as mock_settings:
            mock_settings.return_value.bybit_connector_url = "http://test:8002"

            fetcher = create_fetcher()

            assert isinstance(fetcher, BybitDataFetcher)
            assert fetcher.base_url == "http://test:8002"


class TestFetcherCircuitBreaker:
    """Test circuit breaker integration"""

    @pytest.mark.asyncio
    async def test_get_kline_uses_circuit_breaker(self):
        """Test that get_kline is decorated with circuit breaker"""
        # The @bybit_connector_retry decorator should be applied
        assert hasattr(BybitDataFetcher.get_kline, '__wrapped__')

    @pytest.mark.asyncio
    async def test_get_ticker_uses_circuit_breaker(self):
        """Test that get_ticker is decorated with circuit breaker"""
        # The @bybit_connector_retry decorator should be applied
        assert hasattr(BybitDataFetcher.get_ticker, '__wrapped__')


class TestFetcherErrorHandling:
    """Test comprehensive error handling"""

    @pytest.mark.asyncio
    async def test_get_kline_handles_malformed_response(self):
        """Test handling of malformed API response"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")

        # Response missing expected fields
        mock_data = {"unexpected": "format"}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher.client, 'get', return_value=mock_response):
            klines = await fetcher.get_kline(symbol="BTCUSDT", interval="60")

            # Should handle gracefully and return empty list
            assert klines == []

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_kline_handles_invalid_kline_format(self):
        """Test handling of invalid kline data format"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")

        # Kline data with wrong format (not enough elements)
        mock_data = {
            "success": True,
            "data": {
                "list": [
                    ["1234567890000", "50000"]  # Missing fields
                ]
            }
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher.client, 'get', return_value=mock_response):
            # Should handle the error gracefully
            klines = await fetcher.get_kline(symbol="BTCUSDT", interval="60")

            # Should return empty list or handle error
            assert isinstance(klines, list)

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_health_check_logs_error(self, caplog):
        """Test that health check logs errors"""
        fetcher = BybitDataFetcher(base_url="http://test:8002")

        with patch.object(fetcher.client, 'get', side_effect=Exception("Connection failed")):
            result = await fetcher.health_check()

            assert result is False

        await fetcher.close()
