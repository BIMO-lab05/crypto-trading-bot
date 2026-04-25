"""
Database Connection and Session Management
Purpose: Handle database initialization and provide session factory
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.pool import NullPool

from app.config.settings import get_settings
from app.database.models import Base

logger = logging.getLogger(__name__)

# Global engine and session factory
_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db() -> None:
    """
    Initialize database connection and create tables

    Creates all tables defined in models.py if they don't exist
    """
    global _engine, _async_session_factory

    settings = get_settings()

    logger.info(f"Initializing database connection to {settings.postgres_host}:{settings.postgres_port}")

    try:
        # Create async engine
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,  # Log SQL queries in debug mode
            poolclass=NullPool,  # Use NullPool for better async performance
            pool_pre_ping=True,  # Verify connections before using
        )

        # Create session factory
        _async_session_factory = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

        # Create all tables
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("✅ Database initialized successfully")
        logger.info(f"Created tables: {', '.join(Base.metadata.tables.keys())}")

    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}", exc_info=True)
        raise


async def close_db() -> None:
    """Close database connection"""
    global _engine

    if _engine:
        logger.info("Closing database connection...")
        await _engine.dispose()
        logger.info("✅ Database connection closed")


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Get the async session factory

    Returns:
        async_sessionmaker: Factory for creating database sessions

    Raises:
        RuntimeError: If database not initialized
    """
    if _async_session_factory is None:
        raise RuntimeError(
            "Database not initialized. Call init_db() first."
        )
    return _async_session_factory


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database sessions

    Automatically commits on success, rolls back on error

    Usage:
        async with get_db_session() as session:
            result = await session.execute(query)
            await session.commit()

    Yields:
        AsyncSession: Database session
    """
    session_factory = get_session_factory()

    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}", exc_info=True)
            raise
        finally:
            await session.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI routes

    Usage:
        @app.get("/")
        async def route(db: AsyncSession = Depends(get_db)):
            result = await db.execute(query)
            return result

    Yields:
        AsyncSession: Database session
    """
    async with get_db_session() as session:
        yield session


async def check_db_connection() -> bool:
    """
    Check if database connection is healthy

    Returns:
        bool: True if connection is healthy, False otherwise
    """
    try:
        async with get_db_session() as session:
            await session.execute("SELECT 1")
            return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False


async def create_tables() -> None:
    """
    Manually create all database tables

    Useful for migrations or initial setup
    """
    global _engine

    if _engine is None:
        await init_db()

    logger.info("Creating database tables...")

    try:
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ All tables created successfully")
    except Exception as e:
        logger.error(f"❌ Failed to create tables: {e}", exc_info=True)
        raise


async def drop_tables() -> None:
    """
    Drop all database tables

    ⚠️ WARNING: This will delete all data!
    Use only in development/testing
    """
    global _engine

    if _engine is None:
        raise RuntimeError("Database not initialized")

    logger.warning("⚠️ Dropping all database tables...")

    try:
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.warning("All tables dropped")
    except Exception as e:
        logger.error(f"❌ Failed to drop tables: {e}", exc_info=True)
        raise
