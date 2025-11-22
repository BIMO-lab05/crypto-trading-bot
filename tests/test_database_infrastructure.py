"""
Test Database Infrastructure Verification
Purpose: Verify that test database setup works correctly
This is a standalone test that doesn't require service-specific code
"""

import pytest
import asyncio
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import text, create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Test database URLs
POSTGRES_URL = "postgresql+psycopg2://cryptobot_test:test_password_123@localhost:5434/cryptobot_test"
ASYNC_POSTGRES_URL = "postgresql+asyncpg://cryptobot_test:test_password_123@localhost:5434/cryptobot_test"


# ==========================================
# SYNCHRONOUS TESTS
# ==========================================

def test_sync_database_connection():
    """Test that we can connect to PostgreSQL synchronously"""
    engine = create_engine(POSTGRES_URL)

    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1 + 1 AS result"))
        value = result.scalar()

    assert value == 2
    engine.dispose()


def test_sync_database_version():
    """Test that PostgreSQL is the correct version"""
    engine = create_engine(POSTGRES_URL)

    with engine.connect() as conn:
        result = conn.execute(text("SELECT version()"))
        version = result.scalar()

    assert "PostgreSQL 15" in version
    engine.dispose()


def test_sync_create_table():
    """Test creating and querying a table"""
    engine = create_engine(POSTGRES_URL)

    with engine.begin() as conn:
        # Create test table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS test_infrastructure (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100),
                value DECIMAL(20,8),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))

        # Insert test data
        conn.execute(text("""
            INSERT INTO test_infrastructure (name, value)
            VALUES (:name, :value)
        """), {"name": "test_record", "value": Decimal("123.45")})

        # Query data
        result = conn.execute(text("""
            SELECT name, value FROM test_infrastructure
            WHERE name = :name
        """), {"name": "test_record"})

        row = result.first()

        # Clean up
        conn.execute(text("DROP TABLE test_infrastructure"))

    assert row is not None
    assert row[0] == "test_record"
    assert row[1] == Decimal("123.45")

    engine.dispose()


# ==========================================
# ASYNCHRONOUS TESTS
# ==========================================

@pytest.mark.asyncio
async def test_async_database_connection():
    """Test that we can connect to PostgreSQL asynchronously"""
    engine = create_async_engine(ASYNC_POSTGRES_URL)

    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 2 + 2 AS result"))
        value = result.scalar()

    assert value == 4
    await engine.dispose()


@pytest.mark.asyncio
async def test_async_database_transaction():
    """Test async database transactions"""
    engine = create_async_engine(ASYNC_POSTGRES_URL)

    async with engine.begin() as conn:
        # Create test table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS test_async_infrastructure (
                id SERIAL PRIMARY KEY,
                data TEXT
            )
        """))

        # Insert data
        await conn.execute(text("""
            INSERT INTO test_async_infrastructure (data)
            VALUES (:data)
        """), {"data": "async_test_data"})

        # Query data
        result = await conn.execute(text("""
            SELECT data FROM test_async_infrastructure
            WHERE data = :data
        """), {"data": "async_test_data"})

        row = result.first()

        # Clean up
        await conn.execute(text("DROP TABLE test_async_infrastructure"))

    assert row is not None
    assert row[0] == "async_test_data"

    await engine.dispose()


@pytest.mark.asyncio
async def test_async_session_rollback():
    """Test that transaction rollback works for test isolation"""
    engine = create_async_engine(ASYNC_POSTGRES_URL)

    # Create test table
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS test_rollback (
                id SERIAL PRIMARY KEY,
                data TEXT
            )
        """))

    # Test session with rollback
    async_session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_factory() as session:
        async with session.begin():
            # Insert data
            await session.execute(text("""
                INSERT INTO test_rollback (data) VALUES ('should_rollback')
            """))

            # Check data exists in transaction
            result = await session.execute(text("SELECT COUNT(*) FROM test_rollback"))
            count_in_transaction = result.scalar()

            # Rollback instead of commit
            await session.rollback()

    # Verify data was rolled back
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM test_rollback"))
        count_after_rollback = result.scalar()

        # Clean up
        await conn.execute(text("DROP TABLE test_rollback"))
        await conn.commit()

    assert count_in_transaction == 1, "Data should exist during transaction"
    assert count_after_rollback == 0, "Data should be rolled back after transaction"

    await engine.dispose()


# ==========================================
# PERFORMANCE TESTS
# ==========================================

@pytest.mark.slow
def test_bulk_insert_performance():
    """Test that bulk inserts are fast with tmpfs storage"""
    import time

    engine = create_engine(POSTGRES_URL)

    with engine.begin() as conn:
        # Create test table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS test_performance (
                id SERIAL PRIMARY KEY,
                value INTEGER
            )
        """))

        # Measure bulk insert time
        start_time = time.time()

        for i in range(1000):
            conn.execute(text("""
                INSERT INTO test_performance (value) VALUES (:value)
            """), {"value": i})

        elapsed_ms = (time.time() - start_time) * 1000

        # Clean up
        conn.execute(text("DROP TABLE test_performance"))

    # Assert bulk insert is reasonably fast (should be <2 seconds with tmpfs)
    assert elapsed_ms < 2000, f"Bulk insert took {elapsed_ms:.0f}ms, expected <2000ms"

    engine.dispose()


# ==========================================
# INTEGRATION TEST SUMMARY
# ==========================================

def test_database_infrastructure_summary():
    """Summary test to verify all components"""
    engine = create_engine(POSTGRES_URL)

    with engine.connect() as conn:
        # Check PostgreSQL features
        result = conn.execute(text("""
            SELECT
                current_database() as db_name,
                current_user as db_user,
                version() as db_version
        """))
        row = result.first()

    assert row[0] == "cryptobot_test", "Connected to correct test database"
    assert row[1] == "cryptobot_test", "Using correct test user"
    assert "PostgreSQL 15" in row[2], "Using PostgreSQL 15"

    engine.dispose()


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
