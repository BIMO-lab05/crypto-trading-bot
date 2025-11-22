"""
Redis Cache Manager for Risk Metrics Service
Implements intelligent caching for expensive risk calculations
"""

import json
import logging
import hashlib
from typing import Optional, Any, Dict
from datetime import datetime, timedelta
from decimal import Decimal

try:
    import redis.asyncio as redis
except ImportError:
    redis = None

logger = logging.getLogger(__name__)


class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder for Decimal types"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class RiskMetricsCache:
    """
    High-performance cache for risk calculations
    Features:
    - Automatic TTL management
    - Symbol-based cache keys
    - Hit rate tracking
    - Graceful fallback when Redis unavailable
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        ttl_seconds: int = 30,
        enabled: bool = True
    ):
        """
        Initialize cache manager

        Args:
            redis_url: Redis connection URL
            ttl_seconds: Time-to-live for cached entries (default: 30s)
            enabled: Enable/disable caching globally
        """
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self.enabled = enabled and redis is not None
        self.client: Optional[redis.Redis] = None

        # Performance tracking
        self.hits = 0
        self.misses = 0
        self.errors = 0

        if not redis:
            logger.warning("Redis library not installed - caching disabled")
            self.enabled = False

    async def connect(self):
        """Establish Redis connection"""
        if not self.enabled:
            return

        try:
            self.client = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2
            )
            # Test connection
            await self.client.ping()
            logger.info(f"✅ Redis cache connected: {self.redis_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.enabled = False
            self.client = None

    async def disconnect(self):
        """Close Redis connection gracefully"""
        if self.client:
            try:
                await self.client.close()
                logger.info("Redis connection closed")
            except Exception as e:
                logger.error(f"Error closing Redis connection: {e}")

    def _generate_key(self, operation: str, **params) -> str:
        """
        Generate cache key from operation and parameters

        Args:
            operation: Operation type (e.g., 'risk_scorecard', 'capital_metrics')
            **params: Key-value parameters for cache key

        Returns:
            Hash-based cache key
        """
        # Sort params for consistent key generation
        sorted_params = sorted(params.items())
        key_data = f"{operation}:{json.dumps(sorted_params, sort_keys=True)}"

        # Generate hash for compact key
        key_hash = hashlib.md5(key_data.encode()).hexdigest()
        return f"risk_metrics:{operation}:{key_hash}"

    async def get(self, operation: str, **params) -> Optional[Dict[str, Any]]:
        """
        Get cached value if available

        Args:
            operation: Operation type
            **params: Parameters identifying the cached value

        Returns:
            Cached data or None if not found/expired
        """
        if not self.enabled or not self.client:
            self.misses += 1
            return None

        try:
            key = self._generate_key(operation, **params)
            value = await self.client.get(key)

            if value:
                self.hits += 1
                logger.debug(f"Cache HIT: {key}")
                return json.loads(value)
            else:
                self.misses += 1
                logger.debug(f"Cache MISS: {key}")
                return None

        except Exception as e:
            self.errors += 1
            logger.error(f"Cache get error: {e}")
            return None

    async def set(
        self,
        operation: str,
        data: Dict[str, Any],
        ttl: Optional[int] = None,
        **params
    ) -> bool:
        """
        Store value in cache with TTL

        Args:
            operation: Operation type
            data: Data to cache
            ttl: Custom TTL in seconds (uses default if None)
            **params: Parameters identifying the cached value

        Returns:
            True if successfully cached, False otherwise
        """
        if not self.enabled or not self.client:
            return False

        try:
            key = self._generate_key(operation, **params)
            ttl = ttl or self.ttl_seconds

            # Serialize with custom encoder for Decimal support
            value = json.dumps(data, cls=DecimalEncoder)

            await self.client.setex(key, ttl, value)
            logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
            return True

        except Exception as e:
            self.errors += 1
            logger.error(f"Cache set error: {e}")
            return False

    async def delete(self, operation: str, **params) -> bool:
        """
        Delete cached value

        Args:
            operation: Operation type
            **params: Parameters identifying the cached value

        Returns:
            True if deleted, False otherwise
        """
        if not self.enabled or not self.client:
            return False

        try:
            key = self._generate_key(operation, **params)
            result = await self.client.delete(key)
            logger.debug(f"Cache DELETE: {key}")
            return result > 0

        except Exception as e:
            self.errors += 1
            logger.error(f"Cache delete error: {e}")
            return False

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all keys matching pattern

        Args:
            pattern: Redis key pattern (e.g., 'risk_metrics:*')

        Returns:
            Number of keys deleted
        """
        if not self.enabled or not self.client:
            return 0

        try:
            keys = []
            async for key in self.client.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                deleted = await self.client.delete(*keys)
                logger.info(f"Invalidated {deleted} keys matching '{pattern}'")
                return deleted
            return 0

        except Exception as e:
            self.errors += 1
            logger.error(f"Cache invalidation error: {e}")
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache performance statistics

        Returns:
            Dict with hit rate, total requests, errors
        """
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0.0

        return {
            "enabled": self.enabled,
            "hits": self.hits,
            "misses": self.misses,
            "errors": self.errors,
            "total_requests": total_requests,
            "hit_rate_pct": round(hit_rate, 2),
            "ttl_seconds": self.ttl_seconds
        }

    def reset_stats(self):
        """Reset performance counters"""
        self.hits = 0
        self.misses = 0
        self.errors = 0
        logger.info("Cache statistics reset")


# Global cache instance (initialized in main.py)
cache: Optional[RiskMetricsCache] = None


def get_cache() -> Optional[RiskMetricsCache]:
    """Get global cache instance"""
    return cache
