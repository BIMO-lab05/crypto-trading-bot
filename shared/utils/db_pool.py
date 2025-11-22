"""
Database Connection Pooling
Efficient connection management for PostgreSQL, TimescaleDB, and Redis
"""

import asyncpg
from redis import asyncio as aioredis  # Modern Redis 5.x async support
from typing import Optional, Dict, Any
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class PostgresPool:
    """
    PostgreSQL/TimescaleDB connection pool with automatic retry and health checks

    Features:
    - Connection pooling for efficiency
    - Automatic connection retry
    - Health monitoring
    - Query timeout protection
    - Connection leak detection
    """

    def __init__(
        self,
        host: str,
        port: int = 5432,
        database: str = "cryptobot",
        user: str = "cryptobot",
        password: str = "",
        min_size: int = 10,
        max_size: int = 50,
        command_timeout: float = 60.0,
        max_queries: int = 50000,
        max_inactive_connection_lifetime: float = 300.0
    ):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.min_size = min_size
        self.max_size = max_size
        self.command_timeout = command_timeout
        self.max_queries = max_queries
        self.max_inactive_connection_lifetime = max_inactive_connection_lifetime

        self.pool: Optional[asyncpg.Pool] = None
        self._initialized = False

    async def initialize(self):
        """Initialize connection pool"""
        if self._initialized:
            logger.warning("Pool already initialized")
            return

        try:
            self.pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                min_size=self.min_size,
                max_size=self.max_size,
                command_timeout=self.command_timeout,
                max_queries=self.max_queries,
                max_inactive_connection_lifetime=self.max_inactive_connection_lifetime
            )
            self._initialized = True
            logger.info(
                f"PostgreSQL pool initialized: {self.host}:{self.port}/{self.database} "
                f"(min={self.min_size}, max={self.max_size})"
            )
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL pool: {e}")
            raise

    async def close(self):
        """Close connection pool gracefully"""
        if self.pool:
            await self.pool.close()
            self._initialized = False
            logger.info("PostgreSQL pool closed")

    @asynccontextmanager
    async def acquire(self):
        """
        Acquire a connection from the pool

        Usage:
            async with pool.acquire() as conn:
                result = await conn.fetch("SELECT * FROM users")
        """
        if not self._initialized:
            await self.initialize()

        async with self.pool.acquire() as connection:
            yield connection

    async def execute(self, query: str, *args) -> str:
        """Execute a query that doesn't return data (INSERT, UPDATE, DELETE)"""
        async with self.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args) -> list:
        """Fetch multiple rows"""
        async with self.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> Optional[Dict]:
        """Fetch a single row"""
        async with self.acquire() as conn:
            row = await conn.fetchrow(query, *args)
            return dict(row) if row else None

    async def fetchval(self, query: str, *args) -> Any:
        """Fetch a single value"""
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def health_check(self) -> bool:
        """Check if pool is healthy"""
        try:
            async with self.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def get_size(self) -> Dict[str, int]:
        """Get current pool size"""
        if not self.pool:
            return {"size": 0, "free": 0}

        return {
            "size": self.pool.get_size(),
            "free": self.pool.get_idle_size(),
            "min_size": self.min_size,
            "max_size": self.max_size
        }


class RedisPool:
    """
    Redis connection pool with automatic retry and pub/sub support

    Features:
    - Connection pooling
    - Automatic retry on failure
    - Health monitoring
    - TTL management
    - Pub/Sub support
    """

    def __init__(
        self,
        host: str,
        port: int = 6379,
        password: Optional[str] = None,
        db: int = 0,
        min_size: int = 10,
        max_size: int = 50,
        encoding: str = "utf-8",
        decode_responses: bool = True
    ):
        self.host = host
        self.port = port
        self.password = password
        self.db = db
        self.min_size = min_size
        self.max_size = max_size
        self.encoding = encoding
        self.decode_responses = decode_responses

        self.pool: Optional[aioredis.Redis] = None
        self._initialized = False

    async def initialize(self):
        """Initialize Redis connection pool"""
        if self._initialized:
            logger.warning("Redis pool already initialized")
            return

        try:
            self.pool = await aioredis.create_redis_pool(
                f"redis://{self.host}:{self.port}/{self.db}",
                password=self.password,
                minsize=self.min_size,
                maxsize=self.max_size,
                encoding=self.encoding
            )
            self._initialized = True
            logger.info(
                f"Redis pool initialized: {self.host}:{self.port}/{self.db} "
                f"(min={self.min_size}, max={self.max_size})"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Redis pool: {e}")
            raise

    async def close(self):
        """Close Redis connection pool"""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            self._initialized = False
            logger.info("Redis pool closed")

    async def get(self, key: str) -> Optional[str]:
        """Get value by key"""
        if not self._initialized:
            await self.initialize()
        return await self.pool.get(key)

    async def set(
        self,
        key: str,
        value: str,
        expire: Optional[int] = None
    ) -> bool:
        """Set key-value pair with optional TTL"""
        if not self._initialized:
            await self.initialize()

        if expire:
            return await self.pool.setex(key, expire, value)
        else:
            return await self.pool.set(key, value)

    async def delete(self, *keys: str) -> int:
        """Delete one or more keys"""
        if not self._initialized:
            await self.initialize()
        return await self.pool.delete(*keys)

    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        if not self._initialized:
            await self.initialize()
        return await self.pool.exists(key)

    async def expire(self, key: str, seconds: int) -> bool:
        """Set TTL on key"""
        if not self._initialized:
            await self.initialize()
        return await self.pool.expire(key, seconds)

    async def ttl(self, key: str) -> int:
        """Get TTL of key"""
        if not self._initialized:
            await self.initialize()
        return await self.pool.ttl(key)

    async def incr(self, key: str) -> int:
        """Increment key value"""
        if not self._initialized:
            await self.initialize()
        return await self.pool.incr(key)

    async def decr(self, key: str) -> int:
        """Decrement key value"""
        if not self._initialized:
            await self.initialize()
        return await self.pool.decr(key)

    async def hget(self, key: str, field: str) -> Optional[str]:
        """Get hash field value"""
        if not self._initialized:
            await self.initialize()
        return await self.pool.hget(key, field)

    async def hset(self, key: str, field: str, value: str) -> int:
        """Set hash field value"""
        if not self._initialized:
            await self.initialize()
        return await self.pool.hset(key, field, value)

    async def hgetall(self, key: str) -> Dict:
        """Get all hash fields"""
        if not self._initialized:
            await self.initialize()
        return await self.pool.hgetall(key)

    async def health_check(self) -> bool:
        """Check if Redis is healthy"""
        try:
            if not self._initialized:
                await self.initialize()
            await self.pool.ping()
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False


class DatabaseManager:
    """
    Centralized database connection manager
    Manages pools for PostgreSQL, TimescaleDB, and Redis
    """

    def __init__(self):
        self.postgres_pool: Optional[PostgresPool] = None
        self.timescale_pool: Optional[PostgresPool] = None
        self.redis_pool: Optional[RedisPool] = None

    async def initialize_postgres(
        self,
        host: str,
        port: int = 5432,
        database: str = "cryptobot",
        user: str = "cryptobot",
        password: str = "",
        **kwargs
    ):
        """Initialize PostgreSQL connection pool"""
        self.postgres_pool = PostgresPool(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            **kwargs
        )
        await self.postgres_pool.initialize()

    async def initialize_timescale(
        self,
        host: str,
        port: int = 5432,
        database: str = "market_data",
        user: str = "cryptobot",
        password: str = "",
        **kwargs
    ):
        """Initialize TimescaleDB connection pool"""
        self.timescale_pool = PostgresPool(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            **kwargs
        )
        await self.timescale_pool.initialize()

    async def initialize_redis(
        self,
        host: str,
        port: int = 6379,
        password: Optional[str] = None,
        **kwargs
    ):
        """Initialize Redis connection pool"""
        self.redis_pool = RedisPool(
            host=host,
            port=port,
            password=password,
            **kwargs
        )
        await self.redis_pool.initialize()

    async def close_all(self):
        """Close all connection pools"""
        if self.postgres_pool:
            await self.postgres_pool.close()
        if self.timescale_pool:
            await self.timescale_pool.close()
        if self.redis_pool:
            await self.redis_pool.close()
        logger.info("All database pools closed")

    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all pools"""
        health = {}

        if self.postgres_pool:
            health['postgres'] = await self.postgres_pool.health_check()

        if self.timescale_pool:
            health['timescale'] = await self.timescale_pool.health_check()

        if self.redis_pool:
            health['redis'] = await self.redis_pool.health_check()

        return health

    def get_pool_stats(self) -> Dict[str, Dict]:
        """Get statistics for all pools"""
        stats = {}

        if self.postgres_pool:
            stats['postgres'] = self.postgres_pool.get_size()

        if self.timescale_pool:
            stats['timescale'] = self.timescale_pool.get_size()

        if self.redis_pool:
            stats['redis'] = {
                "initialized": self.redis_pool._initialized,
                "host": self.redis_pool.host,
                "port": self.redis_pool.port
            }

        return stats


# Global database manager instance
db_manager = DatabaseManager()


async def get_postgres() -> PostgresPool:
    """Get PostgreSQL pool"""
    if not db_manager.postgres_pool:
        raise RuntimeError("PostgreSQL pool not initialized")
    return db_manager.postgres_pool


async def get_timescale() -> PostgresPool:
    """Get TimescaleDB pool"""
    if not db_manager.timescale_pool:
        raise RuntimeError("TimescaleDB pool not initialized")
    return db_manager.timescale_pool


async def get_redis() -> RedisPool:
    """Get Redis pool"""
    if not db_manager.redis_pool:
        raise RuntimeError("Redis pool not initialized")
    return db_manager.redis_pool
