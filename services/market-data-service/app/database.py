"""
Market Data Service - Database Connection
Purpose: Manage database connections and sessions
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from contextlib import asynccontextmanager
import logging

from app.config import get_settings
from app.models import Base

logger = logging.getLogger(__name__)

# Global engine and session maker
_engine = None
_async_session_maker = None


def get_engine():
    """Get or create database engine"""
    global _engine
    
    if _engine is None:
        settings = get_settings()

        # Use TimescaleDB for market data storage
        _engine = create_async_engine(
            settings.timescale_url,  # Changed from postgres_url to timescale_url
            echo=settings.debug,  # Log SQL queries in debug mode
            pool_size=settings.db_pool_min_size,
            max_overflow=settings.db_pool_max_size - settings.db_pool_min_size,
            pool_pre_ping=True,  # Verify connections before using
            pool_recycle=3600,  # Recycle connections after 1 hour
        )

        logger.info(f"Created database engine for TimescaleDB: {settings.timescale_host}:{settings.timescale_port}")
    
    return _engine


def get_session_maker():
    """Get or create session maker"""
    global _async_session_maker
    
    if _async_session_maker is None:
        engine = get_engine()
        _async_session_maker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False
        )
        logger.info("Created async session maker")
    
    return _async_session_maker


@asynccontextmanager
async def get_db_session():
    """
    Get database session context manager
    
    Usage:
        async with get_db_session() as session:
            # Use session
            result = await session.execute(...)
    """
    session_maker = get_session_maker()
    session = session_maker()
    
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"Database error, rolling back: {e}")
        raise
    finally:
        await session.close()


async def init_database(max_retries: int = 10, retry_delay: float = 2.0):
    """
    Initialize database (create tables) with retry logic

    Handles the case where database is still starting up by retrying
    the connection with exponential backoff.

    Args:
        max_retries: Maximum number of connection attempts
        retry_delay: Initial delay between retries (doubles each attempt)
    """
    import asyncio

    engine = get_engine()
    last_error = None

    for attempt in range(max_retries):
        try:
            async with engine.begin() as conn:
                # Create all tables
                await conn.run_sync(Base.metadata.create_all)
                logger.info("Database tables created")
                return  # Success - exit function

        except Exception as e:
            last_error = e
            wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
            logger.warning(
                f"Database connection attempt {attempt + 1}/{max_retries} failed: {e}. "
                f"Retrying in {wait_time:.1f}s..."
            )
            await asyncio.sleep(wait_time)

    # All retries exhausted
    logger.error(f"Failed to connect to database after {max_retries} attempts")
    raise last_error


async def create_hypertables():
    """
    Convert tables to TimescaleDB hypertables

    This should be run AFTER init_database() creates the tables.
    Safe to run multiple times (uses if_not_exists).
    """
    from sqlalchemy import text

    engine = get_engine()

    # Individual SQL statements for better error handling
    hypertable_statements = [
        # Convert klines to hypertable
        """SELECT create_hypertable('klines', 'timestamp',
            chunk_time_interval => 86400000,
            if_not_exists => TRUE,
            migrate_data => TRUE
        )""",
        # Convert tickers to hypertable
        """SELECT create_hypertable('tickers', 'timestamp',
            chunk_time_interval => 86400000,
            if_not_exists => TRUE,
            migrate_data => TRUE
        )""",
        # Convert orderbook_snapshots to hypertable
        """SELECT create_hypertable('orderbook_snapshots', 'timestamp',
            chunk_time_interval => 86400000,
            if_not_exists => TRUE,
            migrate_data => TRUE
        )""",
    ]

    retention_statements = [
        # Keep klines for 90 days
        "SELECT add_retention_policy('klines', INTERVAL '90 days', if_not_exists => TRUE)",
        # Keep tickers for 30 days
        "SELECT add_retention_policy('tickers', INTERVAL '30 days', if_not_exists => TRUE)",
        # Keep orderbook snapshots for 7 days
        "SELECT add_retention_policy('orderbook_snapshots', INTERVAL '7 days', if_not_exists => TRUE)",
    ]

    async with engine.begin() as conn:
        # Create hypertables
        for stmt in hypertable_statements:
            try:
                await conn.execute(text(stmt))
                logger.info(f"Hypertable created successfully")
            except Exception as e:
                # Log but continue - hypertable may already exist
                logger.warning(f"Hypertable creation: {e}")

        # Add retention policies
        for stmt in retention_statements:
            try:
                await conn.execute(text(stmt))
                logger.info(f"Retention policy added")
            except Exception as e:
                logger.warning(f"Retention policy: {e}")

        logger.info("TimescaleDB hypertables and policies configured")


async def close_database():
    """Close database connections"""
    global _engine, _async_session_maker
    
    if _engine:
        await _engine.dispose()
        logger.info("Database engine disposed")
    
    _engine = None
    _async_session_maker = None
