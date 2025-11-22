#!/usr/bin/env python3
"""
Test Database Verification Script
Purpose: Verify test databases are accessible and working
Usage: python3 scripts/test-db-verify.py
"""

import sys
import asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine

# Test database configuration
TEST_DATABASES = {
    'PostgreSQL': {
        'sync_url': 'postgresql+psycopg2://cryptobot_test:test_password_123@localhost:5434/cryptobot_test',
        'async_url': 'postgresql+asyncpg://cryptobot_test:test_password_123@localhost:5434/cryptobot_test',
    },
    'TimescaleDB': {
        'sync_url': 'postgresql+psycopg2://cryptobot_test:test_password_123@localhost:5435/market_data_test',
        'async_url': 'postgresql+asyncpg://cryptobot_test:test_password_123@localhost:5435/market_data_test',
    }
}


def test_sync_connection(db_name: str, url: str) -> bool:
    """Test synchronous database connection"""
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"  ✓ {db_name} (sync): Connected")
            print(f"    Version: {version[:60]}...")
            return True
    except Exception as e:
        print(f"  ✗ {db_name} (sync): Failed - {e}")
        return False
    finally:
        engine.dispose()


async def test_async_connection(db_name: str, url: str) -> bool:
    """Test asynchronous database connection"""
    try:
        engine = create_async_engine(url, pool_pre_ping=True)
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT current_database()"))
            db = result.scalar()
            print(f"  ✓ {db_name} (async): Connected to '{db}'")
            return True
    except Exception as e:
        print(f"  ✗ {db_name} (async): Failed - {e}")
        return False
    finally:
        await engine.dispose()


async def main():
    """Main verification routine"""
    print("="*60)
    print("Test Database Verification")
    print("="*60)
    print()

    all_passed = True

    # Test synchronous connections
    print("Testing Synchronous Connections:")
    for db_name, config in TEST_DATABASES.items():
        passed = test_sync_connection(db_name, config['sync_url'])
        all_passed = all_passed and passed
    print()

    # Test asynchronous connections
    print("Testing Asynchronous Connections:")
    for db_name, config in TEST_DATABASES.items():
        passed = await test_async_connection(db_name, config['async_url'])
        all_passed = all_passed and passed
    print()

    # Summary
    print("="*60)
    if all_passed:
        print("✓ All test databases are accessible and working")
        print()
        print("Ready to run tests:")
        print("  cd services/trading-engine")
        print("  pytest tests/ -v")
        return 0
    else:
        print("✗ Some test databases are not accessible")
        print()
        print("Make sure test databases are running:")
        print("  ./scripts/test-db-start.sh")
        return 1
    print("="*60)


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
