"""
Market Data Service - Cache Tests
Purpose: Test Redis caching functionality
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json

from app.cache import get_redis_client, cache_get, cache_set, close_redis


class TestRedisClient:
    """Test Redis client initialization and management"""

    @pytest.mark.asyncio
    async def test_get_redis_client_creates_new_client(self):
        """Test that get_redis_client creates a new client on first call"""
        # Reset global client
        import app.cache
        app.cache._redis_client = None

        with patch('app.cache.aioredis.from_url', new_callable=AsyncMock) as mock_from_url:
            mock_client = AsyncMock()
            mock_from_url.return_value = mock_client

            client = await get_redis_client()

            assert client is not None
            mock_from_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_redis_client_returns_existing_client(self):
        """Test that get_redis_client returns existing client on subsequent calls"""
        # Set up existing client
        import app.cache
        mock_existing_client = AsyncMock()
        app.cache._redis_client = mock_existing_client

        client = await get_redis_client()

        assert client is mock_existing_client

    @pytest.mark.asyncio
    async def test_close_redis_closes_client(self):
        """Test that close_redis properly closes the client"""
        import app.cache
        mock_client = AsyncMock()
        app.cache._redis_client = mock_client

        await close_redis()

        mock_client.close.assert_called_once()
        assert app.cache._redis_client is None

    @pytest.mark.asyncio
    async def test_close_redis_handles_no_client(self):
        """Test that close_redis handles case when client is None"""
        import app.cache
        app.cache._redis_client = None

        # Should not raise an exception
        await close_redis()

        assert app.cache._redis_client is None


class TestCacheGet:
    """Test cache retrieval functionality"""

    @pytest.mark.asyncio
    async def test_cache_get_returns_cached_value(self):
        """Test that cache_get returns and deserializes cached value"""
        mock_client = AsyncMock()
        cached_data = {"symbol": "BTCUSDT", "price": "50000"}
        mock_client.get.return_value = json.dumps(cached_data)

        with patch('app.cache.get_redis_client', return_value=mock_client):
            result = await cache_get("test_key")

            assert result == cached_data
            mock_client.get.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_cache_get_returns_none_for_missing_key(self):
        """Test that cache_get returns None when key doesn't exist"""
        mock_client = AsyncMock()
        mock_client.get.return_value = None

        with patch('app.cache.get_redis_client', return_value=mock_client):
            result = await cache_get("missing_key")

            assert result is None

    @pytest.mark.asyncio
    async def test_cache_get_handles_json_decode_error(self):
        """Test that cache_get handles invalid JSON gracefully"""
        mock_client = AsyncMock()
        mock_client.get.return_value = "invalid json {"

        with patch('app.cache.get_redis_client', return_value=mock_client):
            result = await cache_get("bad_json_key")

            # Should return None on JSON decode error
            assert result is None

    @pytest.mark.asyncio
    async def test_cache_get_handles_redis_connection_error(self):
        """Test that cache_get handles Redis connection errors"""
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("Redis connection failed")

        with patch('app.cache.get_redis_client', return_value=mock_client):
            result = await cache_get("test_key")

            # Should return None on error
            assert result is None


class TestCacheSet:
    """Test cache storage functionality"""

    @pytest.mark.asyncio
    async def test_cache_set_stores_value_with_ttl(self):
        """Test that cache_set stores and serializes value with TTL"""
        mock_client = AsyncMock()
        data_to_cache = {"symbol": "ETHUSDT", "price": "3000"}
        ttl = 300

        with patch('app.cache.get_redis_client', return_value=mock_client):
            await cache_set("test_key", data_to_cache, ttl)

            mock_client.setex.assert_called_once_with(
                "test_key",
                ttl,
                json.dumps(data_to_cache)
            )

    @pytest.mark.asyncio
    async def test_cache_set_handles_dict_data(self):
        """Test that cache_set properly handles dictionary data"""
        mock_client = AsyncMock()
        dict_data = {
            "timestamp": 1234567890,
            "values": [1, 2, 3],
            "nested": {"key": "value"}
        }

        with patch('app.cache.get_redis_client', return_value=mock_client):
            await cache_set("complex_key", dict_data, 600)

            # Verify JSON serialization was called
            called_json = mock_client.setex.call_args[0][2]
            assert json.loads(called_json) == dict_data

    @pytest.mark.asyncio
    async def test_cache_set_handles_list_data(self):
        """Test that cache_set properly handles list data"""
        mock_client = AsyncMock()
        list_data = [{"price": "100"}, {"price": "200"}]

        with patch('app.cache.get_redis_client', return_value=mock_client):
            await cache_set("list_key", list_data, 60)

            called_json = mock_client.setex.call_args[0][2]
            assert json.loads(called_json) == list_data

    @pytest.mark.asyncio
    async def test_cache_set_handles_redis_connection_error(self):
        """Test that cache_set handles Redis connection errors gracefully"""
        mock_client = AsyncMock()
        mock_client.setex.side_effect = Exception("Redis connection failed")

        with patch('app.cache.get_redis_client', return_value=mock_client):
            # Should not raise exception
            await cache_set("test_key", {"data": "value"}, 300)

    @pytest.mark.asyncio
    async def test_cache_set_with_string_value(self):
        """Test that cache_set handles string values"""
        mock_client = AsyncMock()
        string_value = "simple_string"

        with patch('app.cache.get_redis_client', return_value=mock_client):
            await cache_set("string_key", string_value, 120)

            called_json = mock_client.setex.call_args[0][2]
            assert json.loads(called_json) == string_value

    @pytest.mark.asyncio
    async def test_cache_set_with_numeric_value(self):
        """Test that cache_set handles numeric values"""
        mock_client = AsyncMock()
        numeric_value = 12345

        with patch('app.cache.get_redis_client', return_value=mock_client):
            await cache_set("number_key", numeric_value, 180)

            called_json = mock_client.setex.call_args[0][2]
            assert json.loads(called_json) == numeric_value


class TestCacheIntegration:
    """Test cache get/set integration"""

    @pytest.mark.asyncio
    async def test_cache_round_trip(self):
        """Test that data can be set and retrieved correctly"""
        mock_client = AsyncMock()
        test_data = {"symbol": "SOLUSDT", "volume": "1000000"}

        # Setup mock to return the data we set
        stored_data = None

        async def mock_setex(key, ttl, value):
            nonlocal stored_data
            stored_data = value

        async def mock_get(key):
            return stored_data

        mock_client.setex.side_effect = mock_setex
        mock_client.get.side_effect = mock_get

        with patch('app.cache.get_redis_client', return_value=mock_client):
            # Set the cache
            await cache_set("round_trip_key", test_data, 300)

            # Get from cache
            result = await cache_get("round_trip_key")

            assert result == test_data

    @pytest.mark.asyncio
    async def test_cache_different_ttls(self):
        """Test that cache_set can handle different TTL values"""
        mock_client = AsyncMock()

        with patch('app.cache.get_redis_client', return_value=mock_client):
            # Test various TTL values
            await cache_set("ttl_60", {"data": "1min"}, 60)
            await cache_set("ttl_300", {"data": "5min"}, 300)
            await cache_set("ttl_3600", {"data": "1hour"}, 3600)

            # Verify all were called with correct TTLs
            calls = mock_client.setex.call_args_list
            assert calls[0][0][1] == 60
            assert calls[1][0][1] == 300
            assert calls[2][0][1] == 3600


class TestCacheKeyPatterns:
    """Test common cache key patterns used in the service"""

    @pytest.mark.asyncio
    async def test_kline_cache_key_pattern(self):
        """Test caching kline data with proper key structure"""
        mock_client = AsyncMock()

        symbol = "BTCUSDT"
        interval = "60"
        cache_key = f"kline:{symbol}:{interval}"

        kline_data = [
            {"timestamp": 123, "open": "50000", "close": "50500"}
        ]

        with patch('app.cache.get_redis_client', return_value=mock_client):
            await cache_set(cache_key, kline_data, 300)

            mock_client.setex.assert_called_once()
            assert mock_client.setex.call_args[0][0] == cache_key

    @pytest.mark.asyncio
    async def test_ticker_cache_key_pattern(self):
        """Test caching ticker data with proper key structure"""
        mock_client = AsyncMock()

        symbol = "ETHUSDT"
        cache_key = f"ticker:{symbol}"

        ticker_data = {"last_price": "3000", "volume_24h": "100000"}

        with patch('app.cache.get_redis_client', return_value=mock_client):
            await cache_set(cache_key, ticker_data, 60)

            assert mock_client.setex.call_args[0][0] == cache_key
