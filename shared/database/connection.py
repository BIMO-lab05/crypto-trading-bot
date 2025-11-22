"""
Database Connection Management
Handles PostgreSQL connections using SQLAlchemy with async support
"""

import os
import logging
from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy import create_engine, event, pool, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

# Base class for ORM models
Base = declarative_base()


class DatabaseConfig:
    """Database configuration from environment variables"""

    def __init__(self):
        self.host = os.getenv('DB_HOST', 'localhost')
        self.port = int(os.getenv('DB_PORT', '5432'))
        self.name = os.getenv('DB_NAME', 'crypto_trading_bot')
        self.user = os.getenv('DB_USER', 'postgres')
        self.password = os.getenv('DB_PASSWORD', '')

        # Connection pool settings
        self.pool_size = int(os.getenv('DB_POOL_SIZE', '20'))
        self.max_overflow = int(os.getenv('DB_MAX_OVERFLOW', '40'))
        self.pool_timeout = int(os.getenv('DB_POOL_TIMEOUT', '30'))
        self.pool_recycle = int(os.getenv('DB_POOL_RECYCLE', '3600'))

    @property
    def sync_url(self) -> str:
        """Synchronous connection URL"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    @property
    def async_url(self) -> str:
        """Asynchronous connection URL (using asyncpg)"""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class DatabaseManager:
    """
    Singleton database manager for connection pooling
    Provides both sync and async database access
    """

    _instance: Optional['DatabaseManager'] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.config = DatabaseConfig()
            self._sync_engine = None
            self._async_engine = None
            self._sync_session_factory = None
            self._async_session_factory = None
            self._initialized = True

    def init_sync_engine(self):
        """Initialize synchronous database engine"""
        if self._sync_engine is None:
            logger.info(f"Initializing sync database engine: {self.config.host}:{self.config.port}/{self.config.name}")

            self._sync_engine = create_engine(
                self.config.sync_url,
                pool_size=self.config.pool_size,
                max_overflow=self.config.max_overflow,
                pool_timeout=self.config.pool_timeout,
                pool_recycle=self.config.pool_recycle,
                pool_pre_ping=True,  # Verify connections before using
                echo=os.getenv('DB_ECHO', 'false').lower() == 'true',  # SQL logging
            )

            # Event listeners for connection lifecycle
            @event.listens_for(self._sync_engine, "connect")
            def receive_connect(dbapi_conn, connection_record):
                logger.debug("Database connection established")

            @event.listens_for(self._sync_engine, "checkout")
            def receive_checkout(dbapi_conn, connection_record, connection_proxy):
                logger.debug("Connection checked out from pool")

            self._sync_session_factory = sessionmaker(
                bind=self._sync_engine,
                autocommit=False,
                autoflush=False,
            )

            logger.info("Sync database engine initialized successfully")

    def init_async_engine(self):
        """Initialize asynchronous database engine"""
        if self._async_engine is None:
            logger.info(f"Initializing async database engine: {self.config.host}:{self.config.port}/{self.config.name}")

            self._async_engine = create_async_engine(
                self.config.async_url,
                pool_size=self.config.pool_size,
                max_overflow=self.config.max_overflow,
                pool_timeout=self.config.pool_timeout,
                pool_recycle=self.config.pool_recycle,
                pool_pre_ping=True,
                echo=os.getenv('DB_ECHO', 'false').lower() == 'true',
            )

            self._async_session_factory = async_sessionmaker(
                bind=self._async_engine,
                class_=AsyncSession,
                autocommit=False,
                autoflush=False,
                expire_on_commit=False,
            )

            logger.info("Async database engine initialized successfully")

    @contextmanager
    def get_sync_session(self) -> Session:
        """
        Get synchronous database session (context manager)

        Usage:
            with db_manager.get_sync_session() as session:
                portfolio = session.query(Portfolio).first()
        """
        if self._sync_session_factory is None:
            self.init_sync_engine()

        session = self._sync_session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()

    @asynccontextmanager
    async def get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get asynchronous database session (async context manager)

        Usage:
            async with db_manager.get_async_session() as session:
                result = await session.execute(select(Portfolio))
                portfolio = result.scalar_one_or_none()
        """
        if self._async_session_factory is None:
            self.init_async_engine()

        async with self._async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Async database session error: {e}")
                raise

    async def close(self):
        """Close all database connections"""
        logger.info("Closing database connections...")

        if self._async_engine:
            await self._async_engine.dispose()
            logger.info("Async engine disposed")

        if self._sync_engine:
            self._sync_engine.dispose()
            logger.info("Sync engine disposed")

        self._sync_engine = None
        self._async_engine = None
        self._sync_session_factory = None
        self._async_session_factory = None

    def health_check(self) -> bool:
        """Check if database connection is healthy"""
        try:
            if self._sync_engine is None:
                self.init_sync_engine()

            with self._sync_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False


# Global instance
db_manager = DatabaseManager()


# Convenience functions
def init_db(use_async: bool = True):
    """Initialize database connections"""
    if use_async:
        db_manager.init_async_engine()
    db_manager.init_sync_engine()


def get_db_session() -> Session:
    """Get sync database session (deprecated - use context manager)"""
    return db_manager.get_sync_session()


async def get_async_db_session() -> AsyncSession:
    """Get async database session (deprecated - use context manager)"""
    async with db_manager.get_async_session() as session:
        yield session


async def close_db():
    """Close all database connections"""
    await db_manager.close()


# Dependency injection for FastAPI
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database session

    Usage in FastAPI:
        @app.get("/api/portfolio")
        async def get_portfolio(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Portfolio))
            return result.scalar_one_or_none()
    """
    async with db_manager.get_async_session() as session:
        yield session


if __name__ == "__main__":
    # Test database connection
    logging.basicConfig(level=logging.INFO)

    # Load .env file for testing
    from pathlib import Path
    env_file = Path(__file__).parent.parent.parent / "database" / ".env"

    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)

    # Test sync connection
    manager = DatabaseManager()
    if manager.health_check():
        print("✅ Database connection successful!")
    else:
        print("❌ Database connection failed!")
