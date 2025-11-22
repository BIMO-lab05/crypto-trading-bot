"""
Standalone Tests for Signal Cache (No Database Required)
Tests the core caching logic without external dependencies
"""

import pytest
import time
from app.aggregation.signal_cache import SignalCache


class TestSignalCacheStandalone:
    """Test in-memory signal cache without database"""

    def test_cache_initialization(self):
        """Test cache initialization"""
        cache = SignalCache(enabled=True, ttl_seconds=60)
        assert cache.enabled is True
        assert cache.ttl_seconds == 60

    def test_cache_disabled(self):
        """Test disabled cache returns None"""
        cache = SignalCache(enabled=False)
        cache.set("key", "value")
        assert cache.get("key") is None

    def test_cache_set_get(self):
        """Test basic set/get operations"""
        cache = SignalCache(enabled=True)
        cache.set("test", {"data": "value"})
        result = cache.get("test")
        assert result == {"data": "value"}

    def test_cache_miss(self):
        """Test cache miss returns None"""
        cache = SignalCache(enabled=True)
        assert cache.get("nonexistent") is None

    def test_cache_expiration(self):
        """Test TTL expiration"""
        cache = SignalCache(enabled=True, ttl_seconds=1)
        cache.set("key", "value")
        assert cache.get("key") == "value"

        time.sleep(1.1)
        assert cache.get("key") is None

    def test_cache_stats(self):
        """Test statistics tracking"""
        cache = SignalCache(enabled=True)
        cache.set("k1", "v1")
        cache.get("k1")  # Hit
        cache.get("k2")  # Miss

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 50.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
