"""
Test Fixtures
Shared test fixtures for all microservices
"""

from .database import (
    # Engine fixtures
    sync_test_engine,
    async_test_engine,
    timescale_async_engine,
    # Schema management
    setup_test_database_schema,
    # Session fixtures
    async_db_session,
    sync_db_session,
    clean_database,
    timescale_session,
    # Helper fixtures
    db_query_helper,
    assert_decimal_equal,
    benchmark_timer,
    configure_test_logging,
    # Configuration
    get_test_db_url,
    get_timescale_test_db_url,
)

__all__ = [
    # Engines
    'sync_test_engine',
    'async_test_engine',
    'timescale_async_engine',
    # Schema
    'setup_test_database_schema',
    # Sessions
    'async_db_session',
    'sync_db_session',
    'clean_database',
    'timescale_session',
    # Helpers
    'db_query_helper',
    'assert_decimal_equal',
    'benchmark_timer',
    'configure_test_logging',
    # Config
    'get_test_db_url',
    'get_timescale_test_db_url',
]
