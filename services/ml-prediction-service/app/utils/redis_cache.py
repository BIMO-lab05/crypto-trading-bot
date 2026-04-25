"""
Redis Cache Utility for ML Predictions
Provides caching layer to reduce redundant ML inference calls
"""

import json
import logging
from typing import Optional, Any
from datetime import datetime, timedelta
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class PredictionCache:
    """
    Redis-based cache for ML predictions

    Features:
    - Automatic TTL (time-to-live) expiration
    - JSON serialization for complex objects
    - Connection pooling
    - Graceful degradation (works without Redis)
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 2,
        ttl_seconds: int = 300,
        key_prefix: str = "ml:prediction:",
        enabled: bool = True
    ):
        """
        Initialize prediction cache

        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            ttl_seconds: Time-to-live for cached predictions (default: 5 minutes)
            key_prefix: Prefix for all cache keys
            enabled: Whether caching is enabled
        """
        self.host = host
        self.port = port
        self.db = db
        self.ttl_seconds = ttl_seconds
        self.key_prefix = key_prefix
        self.enabled = enabled
        self.redis_client: Optional[redis.Redis] = None
        self._is_connected = False

    async def connect(self):
        """
        Connect to Redis server

        Gracefully handles connection failures - service continues without caching
        """
        if not self.enabled:
            logger.info("Redis caching disabled")
            return

        try:
            self.redis_client = await redis.from_url(
                f"redis://{self.host}:{self.port}/{self.db}",
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0
            )

            # Test connection
            await self.redis_client.ping()
            self._is_connected = True
            logger.info(f"✅ Connected to Redis at {self.host}:{self.port}/{self.db}")

        except Exception as e:
            logger.warning(f"⚠️ Redis connection failed: {e}. Caching disabled.")
            self._is_connected = False
            self.redis_client = None

    async def disconnect(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Redis connection closed")
            self._is_connected = False

    def _make_key(self, symbol: str, interval: str, model_type: str) -> str:
        """
        Generate cache key for prediction

        Format: ml:prediction:{symbol}:{interval}:{model_type}
        Example: ml:prediction:BTCUSDT:60:LSTM
        """
        return f"{self.key_prefix}{symbol}:{interval}:{model_type}"

    async def get_prediction(
        self,
        symbol: str,
        interval: str,
        model_type: str
    ) -> Optional[dict]:
        """
        Get cached prediction

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Timeframe in minutes
            model_type: Model type (LSTM or GRU)

        Returns:
            Cached prediction dict or None if not found/expired
        """
        if not self._is_connected or not self.redis_client:
            return None

        try:
            key = self._make_key(symbol, interval, model_type)
            cached_data = await self.redis_client.get(key)

            if cached_data:
                prediction = json.loads(cached_data)

                # Check if cache is still fresh
                cached_time = datetime.fromisoformat(prediction.get('cached_at', ''))
                age_seconds = (datetime.utcnow() - cached_time).total_seconds()

                logger.debug(
                    f"Cache HIT for {symbol} {interval}m {model_type} "
                    f"(age: {age_seconds:.1f}s)"
                )

                return prediction

            logger.debug(f"Cache MISS for {symbol} {interval}m {model_type}")
            return None

        except Exception as e:
            logger.error(f"Error reading from cache: {e}")
            return None

    async def set_prediction(
        self,
        symbol: str,
        interval: str,
        model_type: str,
        prediction: dict
    ) -> bool:
        """
        Cache a prediction

        Args:
            symbol: Trading pair
            interval: Timeframe in minutes
            model_type: Model type (LSTM or GRU)
            prediction: Prediction data to cache

        Returns:
            True if cached successfully, False otherwise
        """
        if not self._is_connected or not self.redis_client:
            return False

        try:
            key = self._make_key(symbol, interval, model_type)

            # Add caching metadata
            cache_data = {
                **prediction,
                'cached_at': datetime.utcnow().isoformat(),
                'ttl_seconds': self.ttl_seconds
            }

            # Store in Redis with TTL
            await self.redis_client.setex(
                key,
                self.ttl_seconds,
                json.dumps(cache_data, default=str)
            )

            logger.debug(
                f"Cached prediction for {symbol} {interval}m {model_type} "
                f"(TTL: {self.ttl_seconds}s)"
            )

            return True

        except Exception as e:
            logger.error(f"Error writing to cache: {e}")
            return False

    async def invalidate_prediction(
        self,
        symbol: str,
        interval: str,
        model_type: str
    ) -> bool:
        """
        Invalidate (delete) a cached prediction

        Use when:
        - Model is retrained
        - Fresh data is required
        - Manual cache clear

        Args:
            symbol: Trading pair
            interval: Timeframe in minutes
            model_type: Model type

        Returns:
            True if deleted, False otherwise
        """
        if not self._is_connected or not self.redis_client:
            return False

        try:
            key = self._make_key(symbol, interval, model_type)
            deleted = await self.redis_client.delete(key)

            if deleted:
                logger.info(f"Invalidated cache for {symbol} {interval}m {model_type}")
                return True
            else:
                logger.debug(f"No cache found to invalidate for {symbol} {interval}m {model_type}")
                return False

        except Exception as e:
            logger.error(f"Error invalidating cache: {e}")
            return False

    async def clear_all(self) -> int:
        """
        Clear all ML prediction caches

        Returns:
            Number of keys deleted
        """
        if not self._is_connected or not self.redis_client:
            return 0

        try:
            # Find all keys with our prefix
            pattern = f"{self.key_prefix}*"
            keys = []

            async for key in self.redis_client.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                deleted = await self.redis_client.delete(*keys)
                logger.info(f"Cleared {deleted} cached predictions")
                return deleted
            else:
                logger.info("No cached predictions to clear")
                return 0

        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return 0

    async def get_cache_stats(self) -> dict:
        """
        Get cache statistics

        Returns:
            Dict with cache metrics (keys count, memory usage, hit rate, etc.)
        """
        if not self._is_connected or not self.redis_client:
            return {
                'connected': False,
                'enabled': self.enabled,
                'error': 'Not connected to Redis'
            }

        try:
            # Count keys with our prefix
            pattern = f"{self.key_prefix}*"
            keys = []

            async for key in self.redis_client.scan_iter(match=pattern):
                keys.append(key)

            # Get Redis info
            info = await self.redis_client.info('memory')

            return {
                'connected': True,
                'enabled': self.enabled,
                'host': self.host,
                'port': self.port,
                'db': self.db,
                'total_cached_predictions': len(keys),
                'ttl_seconds': self.ttl_seconds,
                'memory_used_mb': round(info.get('used_memory', 0) / (1024 * 1024), 2),
                'cache_prefix': self.key_prefix
            }

        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {
                'connected': False,
                'enabled': self.enabled,
                'error': str(e)
            }

    @property
    def is_connected(self) -> bool:
        """Check if Redis is connected and healthy"""
        return self._is_connected and self.redis_client is not None
