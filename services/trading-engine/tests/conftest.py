"""
Test Configuration and Fixtures
Purpose: Provide database fixtures and test utilities for trading-engine tests
Strategy: Mock database dependencies to avoid requiring actual database connections
"""

import os
import sys
import pytest
import asyncio
import logging
from decimal import Decimal
from uuid import uuid4
from typing import AsyncGenerator, Any, Dict
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

# Add shared directory to Python path so database module can be imported
SHARED_DIR = Path(__file__).parent.parent.parent.parent / "shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


# ==========================================
# PYTEST CONFIGURATION
# ==========================================

def pytest_configure(config):
    """Configure pytest with custom markers for trading-engine"""
    config.addinivalue_line(
        "markers", "integration: Integration tests requiring database"
    )
    config.addinivalue_line(
        "markers", "unit: Fast unit tests"
    )
    config.addinivalue_line(
        "markers", "slow: Slow-running tests"
    )
    config.addinivalue_line(
        "markers", "benchmark: Performance benchmark tests"
    )


# ==========================================
# MOCK DATABASE CONNECTION MODULE
# ==========================================

@pytest.fixture(autouse=True)
def mock_database_connection():
    """
    Automatically mock database.connection module for all tests
    Prevents database connection attempts during testing
    """
    # Create mock db_manager
    mock_db_manager = MagicMock()
    mock_db_manager.get_async_session = AsyncMock()

    # Mock async session generator
    async def mock_session_generator():
        yield MockAsyncSession()

    mock_db_manager.get_async_session.return_value = mock_session_generator()

    # Patch the database.connection module
    with patch.dict('sys.modules', {
        'database.connection': MagicMock(db_manager=mock_db_manager)
    }):
        logger.debug("Mocked database.connection module")
        yield mock_db_manager


# ==========================================
# MOCK DATABASE SESSION
# ==========================================

class MockAsyncSession:
    """
    Mock async database session for testing
    Simulates SQLAlchemy AsyncSession behavior without requiring database
    """

    def __init__(self):
        self._objects = []
        self._committed = False
        self._rolled_back = False

    def add(self, obj):
        """Add object to session"""
        self._objects.append(obj)
        logger.debug(f"Added object to session: {obj}")

    async def commit(self):
        """Commit transaction"""
        self._committed = True
        logger.debug("Session committed")

    async def rollback(self):
        """Rollback transaction"""
        self._rolled_back = True
        self._objects.clear()
        logger.debug("Session rolled back")

    async def refresh(self, obj):
        """Refresh object from database (mock)"""
        logger.debug(f"Refreshed object: {obj}")

    async def execute(self, query):
        """Execute query and return mock result"""
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        result.scalar_one_or_none.return_value = None
        result.scalar.return_value = 1  # For COUNT queries
        return result

    async def close(self):
        """Close session"""
        logger.debug("Session closed")

    async def __aenter__(self):
        """Context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if exc_type is not None:
            await self.rollback()
        await self.close()


class MockDBManager:
    """
    Mock database manager for testing
    Provides async session context manager
    """

    async def get_async_session(self):
        """Yield mock async session"""
        session = MockAsyncSession()
        try:
            yield session
        finally:
            await session.close()


# ==========================================
# DATABASE SESSION FIXTURES
# ==========================================

@pytest.fixture
async def db_session() -> AsyncGenerator[MockAsyncSession, None]:
    """
    Provide mock database session for tests
    No actual database connection required

    Usage:
        async def test_something(db_session):
            obj = SomeModel(...)
            db_session.add(obj)
            await db_session.commit()
    """
    session = MockAsyncSession()
    logger.debug("Created mock database session")

    yield session

    await session.close()
    logger.debug("Closed mock database session")


@pytest.fixture
async def async_db_session(db_session):
    """Alias for db_session for compatibility"""
    return db_session


@pytest.fixture
def mock_db_manager():
    """Provide mock database manager"""
    return MockDBManager()


# ==========================================
# REPOSITORY FIXTURES WITH MOCKS
# ==========================================

@pytest.fixture
def position_repository(db_session):
    """
    Provide PositionRepository with mocked database
    Returns repository configured to use mock session
    """
    from unittest.mock import MagicMock

    # Create mock repository
    repo = MagicMock()
    repo.db = MockDBManager()

    # Mock common methods
    async def mock_create(*args, **kwargs):
        return MagicMock(position_id=uuid4())

    async def mock_get(*args, **kwargs):
        return None

    async def mock_update(*args, **kwargs):
        return MagicMock()

    async def mock_delete(*args, **kwargs):
        return True

    async def mock_list(*args, **kwargs):
        return []

    repo.create = mock_create
    repo.get = mock_get
    repo.update = mock_update
    repo.delete = mock_delete
    repo.list_by_portfolio = mock_list

    logger.debug("Created mock position repository")
    return repo


@pytest.fixture
def trade_repository(db_session):
    """Provide TradeRepository with mocked database"""
    from unittest.mock import MagicMock

    repo = MagicMock()
    repo.db = MockDBManager()

    async def mock_create(*args, **kwargs):
        return MagicMock(trade_id=uuid4())

    async def mock_get(*args, **kwargs):
        return None

    async def mock_list(*args, **kwargs):
        return []

    repo.create = mock_create
    repo.get = mock_get
    repo.list_by_position = mock_list

    logger.debug("Created mock trade repository")
    return repo


@pytest.fixture
def portfolio_repository(db_session):
    """Provide PortfolioRepository with mocked database"""
    from unittest.mock import MagicMock

    repo = MagicMock()
    repo.db = MockDBManager()

    async def mock_get(*args, **kwargs):
        return MagicMock(
            portfolio_id="test_portfolio_001",
            name="Test Portfolio",
            cash_balance=Decimal("10000.00"),
            is_active=True
        )

    async def mock_update_balance(*args, **kwargs):
        return MagicMock(cash_balance=kwargs.get('new_balance', Decimal("10000.00")))

    repo.get = mock_get
    repo.update_balance = mock_update_balance

    logger.debug("Created mock portfolio repository")
    return repo


# ==========================================
# TEST DATA FIXTURES
# ==========================================

@pytest.fixture
def sample_portfolio_id():
    """Provide consistent portfolio ID for tests"""
    return "test_portfolio_001"


@pytest.fixture
def test_portfolio(sample_portfolio_id):
    """
    Provide mock portfolio object
    Returns MagicMock configured as Portfolio
    """
    portfolio = MagicMock()
    portfolio.portfolio_id = sample_portfolio_id
    portfolio.name = "Test Portfolio"
    portfolio.initial_balance = Decimal("10000.00")
    portfolio.cash_balance = Decimal("10000.00")
    portfolio.trading_mode = "PAPER"
    portfolio.is_active = True
    portfolio.created_at = datetime.now(timezone.utc)

    logger.debug(f"Created mock test portfolio: {portfolio.portfolio_id}")
    return portfolio


@pytest.fixture
def sample_position_data():
    """Provide sample position data for tests"""
    return {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "entry_price": Decimal("50000.00"),
        "quantity": Decimal("0.1"),
        "stop_loss": Decimal("49000.00"),
        "take_profit": Decimal("55000.00"),
        "strategy": "test_strategy",
    }


@pytest.fixture
def test_position(sample_portfolio_id, sample_position_data):
    """
    Provide mock position object
    Returns MagicMock configured as Position
    """
    position = MagicMock()
    position.position_id = uuid4()
    position.portfolio_id = sample_portfolio_id
    position.symbol = sample_position_data["symbol"]
    position.side = sample_position_data["side"]
    position.quantity = sample_position_data["quantity"]
    position.entry_price = sample_position_data["entry_price"]
    position.current_price = sample_position_data["entry_price"]
    position.cost_basis = sample_position_data["entry_price"] * sample_position_data["quantity"]
    position.stop_loss = sample_position_data["stop_loss"]
    position.take_profit = sample_position_data["take_profit"]
    position.status = "OPEN"
    position.strategy = sample_position_data["strategy"]
    position.opened_at = datetime.now(timezone.utc)
    position.closed_at = None
    position.realized_pnl = Decimal("0.00")
    position.unrealized_pnl = Decimal("0.00")

    logger.debug(f"Created mock test position: {position.position_id}")
    return position


@pytest.fixture
def create_app_position(sample_position_data):
    """Factory fixture to create position data dictionaries"""
    def _create_position(**overrides):
        data = {**sample_position_data, **overrides}
        return data

    return _create_position


# ==========================================
# MOCK FIXTURES FOR EXTERNAL DEPENDENCIES
# ==========================================

@pytest.fixture
def mock_bybit_connector():
    """Mock Bybit connector for tests that don't need real API calls"""
    mock = AsyncMock()

    # Mock successful order placement
    mock.place_order.return_value = {
        "order_id": "test_order_123",
        "status": "filled",
        "filled_price": "50000.00",
        "filled_qty": "0.1",
        "created_time": datetime.now(timezone.utc).isoformat(),
    }

    # Mock balance retrieval
    mock.get_balance.return_value = {
        "total_balance": "10000.00",
        "available_balance": "5000.00",
        "locked_balance": "5000.00",
    }

    # Mock position retrieval
    mock.get_positions.return_value = []

    # Mock order cancellation
    mock.cancel_order.return_value = {
        "order_id": "test_order_123",
        "status": "cancelled",
    }

    logger.debug("Created mock Bybit connector")
    return mock


@pytest.fixture
def mock_risk_manager():
    """Mock risk manager for tests"""
    mock = MagicMock()

    # Mock validation
    mock.validate_order.return_value = True

    # Mock position size calculation
    mock.calculate_position_size.return_value = Decimal("0.1")

    # Mock risk check
    mock.check_risk_limits.return_value = {
        "allowed": True,
        "max_position_size": Decimal("0.5"),
        "current_exposure": Decimal("0.1"),
    }

    logger.debug("Created mock risk manager")
    return mock


@pytest.fixture
def mock_message_bus():
    """Mock message bus for event publishing"""
    mock = AsyncMock()

    mock.publish.return_value = True
    mock.subscribe.return_value = True

    logger.debug("Created mock message bus")
    return mock


# ==========================================
# ENVIRONMENT CONFIGURATION
# ==========================================

@pytest.fixture(autouse=True)
def test_environment():
    """
    Setup test environment variables
    Automatically applied to all tests
    """
    # Save original environment
    original_env = os.environ.copy()

    # Set test environment variables
    test_env = {
        'ENVIRONMENT': 'test',
        'DB_HOST': 'localhost',
        'DB_PORT': '5434',
        'DB_NAME': 'cryptobot_test',
        'DB_USER': 'cryptobot_test',
        'DB_PASSWORD': 'test_password_123',
        'REDIS_HOST': 'localhost',
        'REDIS_PORT': '6380',
        'LOG_LEVEL': 'DEBUG',
        'BYBIT_API_KEY': 'test_api_key',
        'BYBIT_API_SECRET': 'test_api_secret',
        'RABBITMQ_HOST': 'localhost',
        'RABBITMQ_PORT': '5672',
    }

    os.environ.update(test_env)
    logger.debug(f"Set test environment variables: {list(test_env.keys())}")

    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)
    logger.debug("Restored original environment variables")


# ==========================================
# HELPER FIXTURES
# ==========================================

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


@pytest.fixture
def mock_cache():
    """Mock Redis cache for testing"""
    mock = AsyncMock()

    # In-memory storage for cache
    _cache_storage = {}

    async def mock_get(key):
        return _cache_storage.get(key)

    async def mock_set(key, value, ttl=None):
        _cache_storage[key] = value
        return True

    async def mock_delete(key):
        _cache_storage.pop(key, None)
        return True

    mock.get = mock_get
    mock.set = mock_set
    mock.delete = mock_delete

    logger.debug("Created mock cache")
    return mock


# ==========================================
# TEST STATISTICS FIXTURES
# ==========================================

@pytest.fixture
def test_stats():
    """
    Collect test statistics
    Useful for tracking test performance over time
    """
    stats = {
        'queries_executed': 0,
        'rows_inserted': 0,
        'rows_updated': 0,
        'test_duration_ms': 0,
    }

    yield stats

    # Log statistics after test
    logger.info(f"Test statistics: {stats}")


# ==========================================
# PYTEST ASYNCIO CONFIGURATION
# ==========================================

@pytest.fixture(scope="session")
def event_loop():
    """
    Create event loop for async tests
    Required for pytest-asyncio
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
