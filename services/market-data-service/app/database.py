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
        
        _engine = create_async_engine(
            settings.timescale_url,
            echo=settings.debug,  # Log SQL queries in debug mode
            pool_size=settings.db_pool_min_size,
            max_overflow=settings.db_pool_max_size - settings.db_pool_min_size,
            pool_pre_ping=True,  # Verify connections before using
            pool_recycle=3600,  # Recycle connections after 1 hour
        )
        
        logger.info(f"Created database engine: {settings.timescale_host}:{settings.timescale_port}")
    
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


async def init_database():
    """Initialize database (create tables)"""
    engine = get_engine()
    
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")
        
        # Note: TimescaleDB hypertable conversion should be done manually
        # or via migration script, not here
        logger.info("Run TimescaleDB hypertable creation separately")


async def close_database():
    """Close database connections"""
    global _engine, _async_session_maker
    
    if _engine:
        await _engine.dispose()
        logger.info("Database engine disposed")
    
    _engine = None
    _async_session_maker = None
