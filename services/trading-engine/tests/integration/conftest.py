"""
Integration Test Fixtures
Purpose: Provide shared fixtures for integration tests

Fixtures include:
- Database setup/teardown
- Mock service responses
- Test data generators
- Trading system initialization
"""

import pytest
import asyncio
from decimal import Decimal
from datetime import datetime, timezone
from typing import AsyncGenerator, Dict, Any
from uuid import uuid4
import httpx
import respx

# Import application components
from app.config import get_settings, Settings
from app.paper_trading import PaperTradingEngine
from app.position_manager import PositionManager, get_position_manager
from app.risk_manager import RiskManager, get_risk_manager
from app.signal_aggregator import SignalAggregator
from app.repositories import (
    PositionRepository,
    TradeRepository,
    PortfolioRepository,
)
from app.models import (
    SignalAction,
    OrderSide,
    OrderType,
    OrderStatus,
    PositionSide,
    PositionStatus,
    TradingSignal,
    IndicatorSignal,
)

# Import database components
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "shared"))
from database.connection import db_manager


# ============================================================================
# PYTEST CONFIGURATION
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """
    Create event loop for async tests

    Scope: session - One loop for all tests
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# CONFIGURATION FIXTURES
# ============================================================================

@pytest.fixture
def test_settings() -> Settings:
    """
    Get test configuration settings

    Returns:
        Settings configured for testing
    """
    settings = get_settings()
    # Override settings for testing
    settings.trading_mode = "PAPER"
    settings.paper_initial_balance = 100.0
    settings.min_signal_confidence = 0.6
    settings.max_position_size_pct = 2.0
    settings.max_daily_loss_pct = 5.0
    return settings


# ============================================================================
# DATABASE FIXTURES
# ============================================================================

@pytest.fixture(scope="function")
async def db_session():
    """
    Provide database session for tests with automatic cleanup

    Yields:
        Async database session

    Note:
        - Initializes database connection
        - Creates test schema if needed
        - Rolls back changes after each test
    """
    # Initialize database
    db_manager.init_async_engine()

    # Get session
    async with db_manager.get_async_session() as session:
        yield session
        # Rollback any changes
        await session.rollback()


@pytest.fixture(scope="function")
async def clean_database(db_session):
    """
    Clean database before test

    Deletes all test data to ensure clean slate for each test.
    """
    # Delete test data from all tables
    try:
        # Note: Order matters due to foreign keys
        await db_session.execute("DELETE FROM trades WHERE portfolio_id = 'test_portfolio'")
        await db_session.execute("DELETE FROM positions WHERE portfolio_id = 'test_portfolio'")
        await db_session.execute("DELETE FROM portfolios WHERE portfolio_id = 'test_portfolio'")
        await db_session.commit()
    except Exception as e:
        await db_session.rollback()
        # Ignore errors if tables don't exist yet
        pass


# ============================================================================
# REPOSITORY FIXTURES
# ============================================================================

@pytest.fixture
def position_repo() -> PositionRepository:
    """Get position repository instance"""
    return PositionRepository()


@pytest.fixture
def trade_repo() -> TradeRepository:
    """Get trade repository instance"""
    return TradeRepository()


@pytest.fixture
def portfolio_repo() -> PortfolioRepository:
    """Get portfolio repository instance"""
    return PortfolioRepository()


# ============================================================================
# TRADING ENGINE FIXTURES
# ============================================================================

@pytest.fixture
async def paper_engine(test_settings, clean_database) -> PaperTradingEngine:
    """
    Get paper trading engine instance

    Returns:
        Fresh PaperTradingEngine with test configuration
    """
    # Reset singletons - Note: reset functions were removed during refactoring
    # The managers now use singleton pattern with get_* functions
    # reset_position_manager()  # Removed in refactoring
    # reset_risk_manager()      # Removed in refactoring

    # Create engine
    engine = PaperTradingEngine()

    # Ensure test portfolio exists
    portfolio_repo = PortfolioRepository()
    await portfolio_repo.get_or_create(
        portfolio_id="test_portfolio",
        name="Test Portfolio",
        initial_balance=Decimal("10000.00")
    )

    return engine


@pytest.fixture
def position_manager() -> PositionManager:
    """
    Get position manager instance

    Returns:
        Fresh PositionManager
    """
    # reset_position_manager()  # Removed in refactoring
    return PositionManager()


@pytest.fixture
def risk_manager(test_settings) -> RiskManager:
    """
    Get risk manager instance

    Returns:
        Fresh RiskManager with test settings
    """
    # reset_risk_manager()  # Removed in refactoring
    return RiskManager(
        max_position_size_pct=test_settings.max_position_size_pct,
        max_daily_loss_pct=test_settings.max_daily_loss_pct,
        max_total_exposure_pct=test_settings.max_total_exposure_pct,
        min_signal_confidence=test_settings.min_signal_confidence,
    )


# ============================================================================
# MOCK SERVICE FIXTURES
# ============================================================================

@pytest.fixture
def mock_technical_analysis_responses():
    """
    Mock Technical Analysis Service HTTP responses

    Returns:
        respx router with mocked endpoints
    """
    router = respx.mock(assert_all_called=False)

    # Mock health check
    router.get("http://localhost:8004/health").mock(
        return_value=httpx.Response(200, json={"status": "healthy"})
    )

    # Mock RSI endpoint
    router.get(url__regex=r"http://localhost:8004/api/v1/indicators/rsi.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "value": 45.5,
                    "signal": "BUY",
                    "confidence": 0.65,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
        )
    )

    # Mock MACD endpoint
    router.get(url__regex=r"http://localhost:8004/api/v1/indicators/macd.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "macd": 15.5,
                    "signal": 12.3,
                    "histogram": 3.2,
                    "signal_type": "BUY",
                    "confidence": 0.70,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
        )
    )

    # Mock Bollinger Bands endpoint
    router.get(url__regex=r"http://localhost:8004/api/v1/indicators/bollinger.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "upper": 52000.0,
                    "middle": 50000.0,
                    "lower": 48000.0,
                    "signal": "BUY",
                    "confidence": 0.60,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
        )
    )

    # Mock EMA endpoint
    router.get(url__regex=r"http://localhost:8004/api/v1/indicators/ema.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "ema_9": 49500.0,
                    "ema_21": 49000.0,
                    "signal": "BUY",
                    "confidence": 0.68,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
        )
    )

    # Mock Volume endpoint
    router.get(url__regex=r"http://localhost:8004/api/v1/indicators/volume.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "volume": 1500000.0,
                    "average_volume": 1200000.0,
                    "signal": "BUY",
                    "confidence": 0.55,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
        )
    )

    return router


@pytest.fixture
def mock_bybit_connector_responses():
    """
    Mock Bybit Connector Service HTTP responses

    Returns:
        respx router with mocked endpoints
    """
    router = respx.mock(assert_all_called=False)

    # Mock order placement
    router.post(url__regex=r"http://localhost:8001/api/v1/orders.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "order_id": str(uuid4()),
                "status": "FILLED",
                "filled_price": 50000.0,
                "filled_quantity": 0.02,
            },
        )
    )

    # Mock balance check
    router.get(url__regex=r"http://localhost:8001/api/v1/account/balance.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "balance": {"USDT": 10000.0},
            },
        )
    )

    return router


# ============================================================================
# TEST DATA FIXTURES
# ============================================================================

@pytest.fixture
def sample_buy_signal() -> TradingSignal:
    """
    Generate sample BUY trading signal

    Returns:
        TradingSignal with BUY action and high confidence
    """
    return TradingSignal(
        symbol="BTCUSDT",
        action=SignalAction.BUY,
        confidence=0.75,
        aggregated_score=0.75,
        consensus_strength=0.80,
        indicators={
            "rsi": IndicatorSignal(
                name="RSI",
                value=45.5,
                signal=SignalAction.BUY,
                confidence=0.65,
                weight=1.0,
                metadata={"current_price": 50000.0},
            ),
            "macd": IndicatorSignal(
                name="MACD",
                value=15.5,
                signal=SignalAction.BUY,
                confidence=0.70,
                weight=1.0,
                metadata={"current_price": 50000.0},
            ),
            "bollinger": IndicatorSignal(
                name="Bollinger Bands",
                value=48000.0,
                signal=SignalAction.BUY,
                confidence=0.60,
                weight=0.8,
                metadata={"current_price": 50000.0},
            ),
        },
        timeframe="60",
        metadata={
            "meets_requirements": True,
            "required_indicators": 3,
            "aligned_indicators": 3,
        },
    )


@pytest.fixture
def sample_sell_signal() -> TradingSignal:
    """
    Generate sample SELL trading signal

    Returns:
        TradingSignal with SELL action and high confidence
    """
    return TradingSignal(
        symbol="BTCUSDT",
        action=SignalAction.SELL,
        confidence=0.72,
        aggregated_score=0.72,
        consensus_strength=0.78,
        indicators={
            "rsi": IndicatorSignal(
                name="RSI",
                value=75.5,
                signal=SignalAction.SELL,
                confidence=0.70,
                weight=1.0,
                metadata={"current_price": 51000.0},
            ),
            "macd": IndicatorSignal(
                name="MACD",
                value=-12.5,
                signal=SignalAction.SELL,
                confidence=0.68,
                weight=1.0,
                metadata={"current_price": 51000.0},
            ),
            "bollinger": IndicatorSignal(
                name="Bollinger Bands",
                value=52000.0,
                signal=SignalAction.SELL,
                confidence=0.65,
                weight=0.8,
                metadata={"current_price": 51000.0},
            ),
        },
        timeframe="60",
        metadata={
            "meets_requirements": True,
            "required_indicators": 3,
            "aligned_indicators": 3,
        },
    )


@pytest.fixture
def sample_hold_signal() -> TradingSignal:
    """
    Generate sample HOLD trading signal

    Returns:
        TradingSignal with HOLD action and low confidence
    """
    return TradingSignal(
        symbol="BTCUSDT",
        action=SignalAction.HOLD,
        confidence=0.45,
        aggregated_score=0.45,
        consensus_strength=0.30,
        indicators={
            "rsi": IndicatorSignal(
                name="RSI",
                value=55.0,
                signal=SignalAction.HOLD,
                confidence=0.40,
                weight=1.0,
                metadata={"current_price": 50500.0},
            ),
            "macd": IndicatorSignal(
                name="MACD",
                value=2.5,
                signal=SignalAction.BUY,
                confidence=0.50,
                weight=1.0,
                metadata={"current_price": 50500.0},
            ),
        },
        timeframe="60",
        metadata={
            "meets_requirements": False,
            "required_indicators": 3,
            "aligned_indicators": 1,
        },
    )


@pytest.fixture
def test_portfolio_data() -> Dict[str, Any]:
    """
    Generate test portfolio data

    Returns:
        Dictionary with portfolio configuration
    """
    return {
        "portfolio_id": "test_portfolio",
        "name": "Test Trading Portfolio",
        "initial_balance": Decimal("10000.00"),
        "current_balance": Decimal("10000.00"),
        "trading_mode": "PAPER",
    }


@pytest.fixture
def test_market_prices() -> Dict[str, Decimal]:
    """
    Generate test market prices for various symbols

    Returns:
        Dictionary mapping symbols to current prices
    """
    return {
        "BTCUSDT": Decimal("50000.00"),
        "ETHUSDT": Decimal("3000.00"),
        "BNBUSDT": Decimal("400.00"),
        "SOLUSDT": Decimal("100.00"),
    }


# ============================================================================
# INTEGRATION TEST SYSTEM FIXTURE
# ============================================================================

@pytest.fixture
async def trading_system(
    paper_engine,
    position_manager,
    risk_manager,
    mock_technical_analysis_responses,
    test_settings,
    clean_database,
):
    """
    Complete trading system for integration tests

    Provides:
        - Paper trading engine
        - Position manager
        - Risk manager
        - Mocked external services
        - Clean database

    Returns:
        Dictionary with all trading system components
    """
    # Start mock routers
    mock_technical_analysis_responses.start()

    # Reset signal aggregator to use mocked services
    # reset_aggregator()  # Removed in refactoring, aggregator uses singleton pattern

    system = {
        "engine": paper_engine,
        "position_manager": position_manager,
        "risk_manager": risk_manager,
        "settings": test_settings,
        "initial_balance": Decimal("10000.00"),
    }

    yield system

    # Cleanup
    mock_technical_analysis_responses.stop()
    mock_technical_analysis_responses.reset()


# ============================================================================
# UTILITY FIXTURES
# ============================================================================

@pytest.fixture
def assert_decimal_equal():
    """
    Utility fixture for comparing Decimal values

    Returns:
        Function that asserts two Decimals are equal within tolerance
    """
    def _assert_equal(actual: Decimal, expected: Decimal, tolerance: Decimal = Decimal("0.01")):
        """Assert Decimal values are equal within tolerance"""
        diff = abs(actual - expected)
        assert diff <= tolerance, f"Expected {expected}, got {actual} (diff: {diff})"

    return _assert_equal


@pytest.fixture
def wait_for_async(event_loop):
    """
    Utility to wait for async operations

    Returns:
        Function to run async code in sync context
    """
    def _wait(coro, timeout=5.0):
        """Run coroutine with timeout"""
        return asyncio.wait_for(coro, timeout=timeout)

    return _wait
