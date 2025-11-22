"""
Database Test Fixtures
Purpose: Centralized database fixtures for all microservices
Strategy: Docker-based PostgreSQL for integration tests with transaction rollback for isolation

Usage:
    @pytest.mark.integration
    async def test_with_database(db_session):
        # Test code using db_session
        pass
"""

import os
import asyncio
import logging
from typing import AsyncGenerator, Generator
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text, event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
    AsyncEngine
)
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

# Import database models
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from database.connection import Base

logger = logging.getLogger(__name__)


# ==========================================
# CONFIGURATION
# ==========================================

def get_test_db_url(async_mode: bool = False) -> str:
    """
    Get test database URL from environment or use defaults

    Environment variables:
        TEST_DB_HOST: Database host (default: localhost)
        TEST_DB_PORT: Database port (default: 5434)
        TEST_DB_NAME: Database name (default: cryptobot_test)
        TEST_DB_USER: Database user (default: cryptobot_test)
        TEST_DB_PASSWORD: Database password (default: test_password_123)

    Returns:
        str: Database connection URL
    """
    config = {
        'host': os.getenv('TEST_DB_HOST', 'localhost'),
        'port': os.getenv('TEST_DB_PORT', '5434'),
        'name': os.getenv('TEST_DB_NAME', 'cryptobot_test'),
        'user': os.getenv('TEST_DB_USER', 'cryptobot_test'),
        'password': os.getenv('TEST_DB_PASSWORD', 'test_password_123'),
    }

    driver = 'postgresql+asyncpg' if async_mode else 'postgresql+psycopg2'
    url = f"{driver}://{config['user']}:{config['password']}@{config['host']}:{config['port']}/{config['name']}"

    logger.debug(f"Test database URL: {driver}://{config['user']}:***@{config['host']}:{config['port']}/{config['name']}")
    return url


def get_timescale_test_db_url(async_mode: bool = False) -> str:
    """Get TimescaleDB test database URL for market data tests"""
    config = {
        'host': os.getenv('TIMESCALE_TEST_DB_HOST', 'localhost'),
        'port': os.getenv('TIMESCALE_TEST_DB_PORT', '5435'),
        'name': os.getenv('TIMESCALE_TEST_DB_NAME', 'market_data_test'),
        'user': os.getenv('TIMESCALE_TEST_DB_USER', 'cryptobot_test'),
        'password': os.getenv('TIMESCALE_TEST_DB_PASSWORD', 'test_password_123'),
    }

    driver = 'postgresql+asyncpg' if async_mode else 'postgresql+psycopg2'
    url = f"{driver}://{config['user']}:{config['password']}@{config['host']}:{config['port']}/{config['name']}"

    logger.debug(f"TimescaleDB test URL: {driver}://{config['user']}:***@{config['host']}:{config['port']}/{config['name']}")
    return url


# ==========================================
# PYTEST MARKERS CONFIGURATION
# ==========================================

def pytest_configure(config):
    """Register custom pytest markers"""
    config.addinivalue_line(
        "markers", "integration: Integration tests requiring database (slower)"
    )
    config.addinivalue_line(
        "markers", "unit: Fast unit tests using SQLite or mocks"
    )
    config.addinivalue_line(
        "markers", "slow: Slow-running tests (benchmarks, load tests)"
    )
    config.addinivalue_line(
        "markers", "timescale: Tests requiring TimescaleDB features"
    )


# ==========================================
# ENGINE FIXTURES (SESSION-SCOPED)
# ==========================================

@pytest.fixture(scope="session")
def sync_test_engine():
    """
    Session-scoped synchronous database engine
    Used for setup/teardown operations
    """
    engine = create_engine(
        get_test_db_url(async_mode=False),
        poolclass=NullPool,  # Disable connection pooling for tests
        echo=False,  # Set to True for SQL debugging
        future=True,
    )

    logger.info("Created synchronous test database engine")
    yield engine

    engine.dispose()
    logger.info("Disposed synchronous test database engine")


@pytest.fixture(scope="session")
async def async_test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """
    Session-scoped asynchronous database engine
    Used for async test operations
    """
    engine = create_async_engine(
        get_test_db_url(async_mode=True),
        poolclass=NullPool,  # Disable connection pooling for tests
        echo=False,  # Set to True for SQL debugging
        future=True,
    )

    logger.info("Created asynchronous test database engine")
    yield engine

    await engine.dispose()
    logger.info("Disposed asynchronous test database engine")


# ==========================================
# SCHEMA MANAGEMENT FIXTURES
# ==========================================

@pytest.fixture(scope="session", autouse=True)
def setup_test_database_schema(sync_test_engine):
    """
    Setup and teardown test database schema
    Runs once per test session

    This fixture:
    1. Drops all existing tables (clean slate)
    2. Creates all tables from SQLAlchemy models
    3. Tears down schema after all tests complete
    """
    logger.info("="*60)
    logger.info("Setting up test database schema...")

    try:
        # Drop all existing tables
        Base.metadata.drop_all(bind=sync_test_engine)
        logger.info("Dropped existing tables")

        # Create all tables from models
        Base.metadata.create_all(bind=sync_test_engine)
        logger.info("Created all database tables")

        # Verify table creation
        with sync_test_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """))
            tables = [row[0] for row in result]
            logger.info(f"Created tables: {', '.join(tables)}")

        logger.info("Test database schema setup complete")
        logger.info("="*60)

    except Exception as e:
        logger.error(f"Failed to setup test database: {e}", exc_info=True)
        raise

    yield  # Run all tests

    # Teardown: Clean up after all tests
    logger.info("="*60)
    logger.info("Tearing down test database schema...")
    try:
        Base.metadata.drop_all(bind=sync_test_engine)
        logger.info("Test database cleanup complete")
    except Exception as e:
        logger.error(f"Failed to cleanup test database: {e}", exc_info=True)
    logger.info("="*60)


# ==========================================
# SESSION FIXTURES (FUNCTION-SCOPED)
# ==========================================

@pytest.fixture
async def async_db_session(async_test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Async database session with transaction rollback
    Creates a new session for each test and rolls back changes after test

    Benefits:
    - Test isolation (each test has clean database state)
    - Fast (rollback is faster than truncating tables)
    - Safe (tests can't pollute each other)

    Usage:
        async def test_create_position(async_db_session):
            position = Position(...)
            async_db_session.add(position)
            await async_db_session.commit()
            # Automatically rolled back after test
    """
    # Create session factory
    async_session_factory = async_sessionmaker(
        bind=async_test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    # Create session and start transaction
    async with async_session_factory() as session:
        async with session.begin():
            logger.debug("Started database transaction for test")

            # Provide session to test
            yield session

            # Rollback transaction after test (automatic cleanup)
            await session.rollback()
            logger.debug("Rolled back database transaction")


@pytest.fixture
def sync_db_session(sync_test_engine) -> Generator[Session, None, None]:
    """
    Synchronous database session with transaction rollback
    For tests that don't require async operations

    Usage:
        def test_sync_operation(sync_db_session):
            result = sync_db_session.execute(text("SELECT 1"))
            # Automatically rolled back after test
    """
    # Create session factory
    SessionFactory = sessionmaker(
        bind=sync_test_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    # Create session and start transaction
    session = SessionFactory()
    transaction = session.begin()

    logger.debug("Started synchronous database transaction for test")

    # Provide session to test
    yield session

    # Rollback transaction after test
    transaction.rollback()
    session.close()
    logger.debug("Rolled back synchronous database transaction")


# ==========================================
# DATABASE CLEANUP FIXTURES
# ==========================================

@pytest.fixture
async def clean_database(async_db_session: AsyncSession):
    """
    Explicitly clean database tables before test
    Use this when you need guaranteed empty tables

    Note: Usually not needed due to transaction rollback,
    but useful for debugging or specific test scenarios

    Usage:
        async def test_with_clean_db(clean_database):
            # Database tables are empty
            pass
    """
    # Truncate all tables in correct order (respect foreign keys)
    tables_to_truncate = [
        'trades',
        'positions',
        'portfolio_snapshots',
        'portfolios',
        'market_data',
        'candles',
    ]

    for table in tables_to_truncate:
        try:
            await async_db_session.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
        except Exception as e:
            # Table might not exist, that's okay
            logger.debug(f"Could not truncate {table}: {e}")

    await async_db_session.commit()
    logger.debug(f"Truncated tables: {', '.join(tables_to_truncate)}")

    yield async_db_session


# ==========================================
# TIMESCALEDB FIXTURES
# ==========================================

@pytest.fixture(scope="session")
async def timescale_async_engine() -> AsyncGenerator[AsyncEngine, None]:
    """
    TimescaleDB test engine for market data tests
    """
    engine = create_async_engine(
        get_timescale_test_db_url(async_mode=True),
        poolclass=NullPool,
        echo=False,
        future=True,
    )

    logger.info("Created TimescaleDB test engine")
    yield engine

    await engine.dispose()
    logger.info("Disposed TimescaleDB test engine")


@pytest.fixture
async def timescale_session(timescale_async_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    TimescaleDB session for market data tests
    """
    async_session_factory = async_sessionmaker(
        bind=timescale_async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_factory() as session:
        async with session.begin():
            yield session
            await session.rollback()


# ==========================================
# HELPER FIXTURES
# ==========================================

@pytest.fixture
def db_query_helper(async_db_session: AsyncSession):
    """
    Helper to execute raw SQL queries in tests
    Useful for setup, verification, or debugging

    Usage:
        async def test_something(db_query_helper):
            result = await db_query_helper("SELECT COUNT(*) FROM positions")
            assert result.scalar() == 5
    """
    async def execute_query(query: str, params: dict = None):
        """Execute raw SQL query and return result"""
        if params:
            result = await async_db_session.execute(text(query), params)
        else:
            result = await async_db_session.execute(text(query))
        return result

    return execute_query


@pytest.fixture
def assert_decimal_equal():
    """
    Helper to assert Decimal equality with tolerance

    Usage:
        def test_calculation(assert_decimal_equal):
            result = calculate_pnl()
            assert_decimal_equal(result, Decimal("123.45"), tolerance=Decimal("0.01"))
    """
    def _assert_equal(
        actual: Decimal,
        expected: Decimal,
        tolerance: Decimal = Decimal("0.00000001")
    ):
        """Assert two Decimals are equal within tolerance"""
        diff = abs(actual - expected)
        assert diff <= tolerance, (
            f"Expected {expected}, got {actual} "
            f"(difference: {diff}, tolerance: {tolerance})"
        )

    return _assert_equal


# ==========================================
# PERFORMANCE TESTING FIXTURES
# ==========================================

@pytest.fixture
def benchmark_timer():
    """
    Simple timer for performance testing

    Usage:
        def test_performance(benchmark_timer):
            with benchmark_timer() as timer:
                # Code to benchmark
                pass
            timer.assert_faster_than(100)  # Assert < 100ms
    """
    import time

    class Timer:
        def __init__(self):
            self.start_time = None
            self.elapsed_ms = None

        def __enter__(self):
            self.start_time = time.time()
            return self

        def __exit__(self, *args):
            self.elapsed_ms = (time.time() - self.start_time) * 1000

        def assert_faster_than(self, max_ms: float, message: str = None):
            """Assert operation completed faster than threshold"""
            assert self.elapsed_ms < max_ms, (
                message or f"Operation took {self.elapsed_ms:.2f}ms, expected < {max_ms}ms"
            )

        def assert_slower_than(self, min_ms: float, message: str = None):
            """Assert operation took at least minimum time"""
            assert self.elapsed_ms >= min_ms, (
                message or f"Operation took {self.elapsed_ms:.2f}ms, expected >= {min_ms}ms"
            )

    return Timer


# ==========================================
# LOGGING CONFIGURATION
# ==========================================

@pytest.fixture(autouse=True)
def configure_test_logging(caplog):
    """Configure logging for tests"""
    caplog.set_level(logging.DEBUG)

    # Configure root logger
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True
    )

    yield
