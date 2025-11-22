"""
Tests for Redis Signal Cache Module
Purpose: Verify cache functionality, TTL, metrics, and fallback behavior

Test Coverage:
- In-memory cache operations
- Redis cache operations
- TTL expiration
- Cache invalidation
- Pattern-based invalidation
- Metrics tracking
- Fallback behavior
- Health checks
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

from app.aggregation.signal_cache import (
    SignalCache,
    RedisSignalCache,
    get_signal_cache,
    close_signal_cache
)


class TestSignalCache:
    """Test in-memory signal cache"""

    def test_cache_initialization(self):
        """Test cache initialization with default settings"""
        cache = SignalCache(enabled=True, ttl_seconds=60)

        assert cache.enabled is True
        assert cache.ttl_seconds == 60
        assert len(cache._cache) == 0

    def test_cache_disabled_returns_none(self):
        """Test that disabled cache always returns None"""
        cache = SignalCache(enabled=False)

        cache.set("test_key", "test_value")
        result = cache.get("test_key")

        assert result is None

    def test_cache_set_and_get(self):
        """Test basic cache set and get operations"""
        cache = SignalCache(enabled=True, ttl_seconds=60)

        # Set value
        cache.set("test_key", {"signal": "BUY", "confidence": 0.8})

        # Get value
        result = cache.get("test_key")

        assert result is not None
        assert result["signal"] == "BUY"
        assert result["confidence"] == 0.8

    def test_cache_miss(self):
        """Test cache miss returns None"""
        cache = SignalCache(enabled=True)

        result = cache.get("nonexistent_key")

        assert result is None

    def test_cache_expiration(self):
        """Test cache entries expire after TTL"""
        cache = SignalCache(enabled=True, ttl_seconds=1)

        # Set value
        cache.set("test_key", "test_value")

        # Verify it exists
        assert cache.get("test_key") == "test_value"

        # Wait for expiration
        import time
        time.sleep(1.1)

        # Should be expired
        assert cache.get("test_key") is None

    def test_cache_invalidation(self):
        """Test cache invalidation removes specific key"""
        cache = SignalCache(enabled=True)

        cache.set("key1", "value1")
        cache.set("key2", "value2")

        # Invalidate one key
        cache.invalidate("key1")

        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"

    def test_cache_pattern_invalidation(self):
        """Test pattern-based cache invalidation"""
        cache = SignalCache(enabled=True)

        cache.set("signal:BTCUSDT:60", "signal1")
        cache.set("signal:BTCUSDT:240", "signal2")
        cache.set("signal:ETHUSDT:60", "signal3")

        # Invalidate all BTCUSDT signals
        cache.invalidate_pattern("signal:BTCUSDT:*")

        assert cache.get("signal:BTCUSDT:60") is None
        assert cache.get("signal:BTCUSDT:240") is None
        assert cache.get("signal:ETHUSDT:60") == "signal3"

    def test_cache_clear(self):
        """Test clearing all cache entries"""
        cache = SignalCache(enabled=True)

        cache.set("key1", "value1")
        cache.set("key2", "value2")

        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_cache_stats(self):
        """Test cache statistics tracking"""
        cache = SignalCache(enabled=True, ttl_seconds=60)

        # Set some values
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        # Generate hits and misses
        cache.get("key1")  # Hit
        cache.get("key1")  # Hit
        cache.get("nonexistent")  # Miss

        stats = cache.get_stats()

        assert stats["enabled"] is True
        assert stats["cache_type"] == "in_memory"
        assert stats["total_entries"] == 2
        assert stats["active_entries"] == 2
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 66.67  # 2/(2+1) * 100


class TestRedisSignalCache:
    """Test Redis-backed signal cache"""

    @pytest.mark.asyncio
    async def test_redis_cache_initialization(self):
        """Test Redis cache initialization"""
        cache = RedisSignalCache(
            redis_url="redis://localhost:6379/2",
            ttl_seconds=60,
            enabled=True
        )

        assert cache.redis_url == "redis://localhost:6379/2"
        assert cache.ttl_seconds == 60
        assert cache.enabled is True

    @pytest.mark.asyncio
    async def test_redis_connection_failure_uses_fallback(self):
        """Test that connection failure gracefully falls back to memory cache"""
        cache = RedisSignalCache(
            redis_url="redis://invalid:9999/0",
            ttl_seconds=60
        )

        # Try to connect (should fail)
        connected = await cache.connect()

        assert connected is False
        assert cache._connected is False

        # Should use fallback cache
        await cache.set("test_key", "test_value")
        result = await cache.get("test_key")

        # Fallback cache should work
        assert result == "test_value"

    @pytest.mark.asyncio
    @patch('redis.asyncio.from_url')
    async def test_redis_set_and_get(self, mock_redis_from_url):
        """Test Redis set and get operations"""
        # Mock Redis client
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_redis.get = AsyncMock(return_value='{"signal": "BUY"}')
        mock_redis_from_url.return_value = mock_redis

        cache = RedisSignalCache(redis_url="redis://localhost:6379/2")
        await cache.connect()

        # Set value
        await cache.set("test_key", {"signal": "BUY"})

        # Get value
        result = await cache.get("test_key")

        assert result == {"signal": "BUY"}
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    @patch('redis.asyncio.from_url')
    async def test_redis_cache_miss(self, mock_redis_from_url):
        """Test Redis cache miss"""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis_from_url.return_value = mock_redis

        cache = RedisSignalCache(redis_url="redis://localhost:6379/2")
        await cache.connect()

        result = await cache.get("nonexistent_key")

        assert result is None

    @pytest.mark.asyncio
    @patch('redis.asyncio.from_url')
    async def test_redis_invalidation(self, mock_redis_from_url):
        """Test Redis key invalidation"""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()
        mock_redis.delete = AsyncMock()
        mock_redis_from_url.return_value = mock_redis

        cache = RedisSignalCache(redis_url="redis://localhost:6379/2")
        await cache.connect()

        await cache.invalidate("test_key")

        mock_redis.delete.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    @patch('redis.asyncio.from_url')
    async def test_redis_pattern_invalidation(self, mock_redis_from_url):
        """Test Redis pattern-based invalidation"""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()
        mock_redis.scan = AsyncMock(side_effect=[
            (10, ["signal:BTCUSDT:60", "signal:BTCUSDT:240"]),
            (0, [])  # End of scan
        ])
        mock_redis.delete = AsyncMock()
        mock_redis_from_url.return_value = mock_redis

        cache = RedisSignalCache(redis_url="redis://localhost:6379/2")
        await cache.connect()

        await cache.invalidate_pattern("signal:BTCUSDT:*")

        # Should have called delete with the matched keys
        assert mock_redis.delete.call_count == 1

    @pytest.mark.asyncio
    @patch('redis.asyncio.from_url')
    async def test_redis_health_check(self, mock_redis_from_url):
        """Test Redis health check"""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()
        mock_redis.info = AsyncMock(return_value={
            "redis_version": "6.2.6",
            "used_memory_human": "1.5M",
            "connected_clients": 5,
            "uptime_in_days": 10
        })
        mock_redis_from_url.return_value = mock_redis

        cache = RedisSignalCache(redis_url="redis://localhost:6379/2")
        await cache.connect()

        health = await cache.health_check()

        assert health["healthy"] is True
        assert health["connected"] is True
        assert health["version"] == "6.2.6"

    @pytest.mark.asyncio
    @patch('redis.asyncio.from_url')
    async def test_redis_cache_stats(self, mock_redis_from_url):
        """Test Redis cache statistics"""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()
        mock_redis.scan = AsyncMock(side_effect=[
            (10, ["key1", "key2"]),
            (0, [])
        ])
        mock_redis.get = AsyncMock(return_value='{"value": 1}')
        mock_redis_from_url.return_value = mock_redis

        cache = RedisSignalCache(redis_url="redis://localhost:6379/2")
        await cache.connect()

        # Generate some hits
        await cache.get("test_key")
        await cache.get("test_key2")

        stats = await cache.get_stats()

        assert stats["enabled"] is True
        assert stats["cache_type"] == "redis"
        assert stats["connected"] is True
        assert stats["hits"] == 2

    @pytest.mark.asyncio
    @patch('redis.asyncio.from_url')
    async def test_redis_warm_cache(self, mock_redis_from_url):
        """Test cache warming functionality"""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_redis_from_url.return_value = mock_redis

        cache = RedisSignalCache(redis_url="redis://localhost:6379/2")
        await cache.connect()

        symbols = ["BTCUSDT", "ETHUSDT"]
        timeframes = ["60", "240"]

        await cache.warm_cache(symbols, timeframes)

        # Should have called setex for each symbol/timeframe combination
        assert mock_redis.setex.call_count == 4  # 2 symbols * 2 timeframes

    @pytest.mark.asyncio
    async def test_get_signal_cache_global_instance(self):
        """Test global cache instance management"""
        # Get cache instance
        cache1 = await get_signal_cache(redis_url="redis://localhost:6379/2")

        # Get again - should be same instance
        cache2 = await get_signal_cache()

        assert cache1 is cache2

        # Cleanup
        await close_signal_cache()

    @pytest.mark.asyncio
    async def test_close_signal_cache(self):
        """Test cache cleanup"""
        cache = await get_signal_cache(redis_url="redis://localhost:6379/2")

        await close_signal_cache()

        # After closing, getting cache again should create new instance
        new_cache = await get_signal_cache()
        assert new_cache is not cache


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
