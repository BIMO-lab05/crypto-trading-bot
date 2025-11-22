"""
Pytest configuration and shared fixtures for Risk & Metrics Service tests
Provides reusable fixtures for API client, mock data, and test utilities
"""

import pytest
from fastapi.testclient import TestClient
from decimal import Decimal
from datetime import datetime
from typing import List, Dict
from unittest.mock import Mock, AsyncMock

from app.main import app
from app.risk_engine import RiskEngine
from app.models import (
    CapitalMetrics,
    ExposureMetrics,
    DrawdownMetrics,
    ValueAtRisk,
    PerformanceMetrics
)


@pytest.fixture
def test_client(monkeypatch):
    """
    FastAPI test client for making HTTP requests
    Automatically handles startup/shutdown events
    Mocks external HTTP calls to prevent timeouts
    """
    # Set test environment to use short timeout
    monkeypatch.setenv("HTTP_TIMEOUT", "0.1")

    # Mock httpx.AsyncClient to avoid real network calls
    import httpx

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def get(self, url, *args, **kwargs):
            """Mock GET request handler - instant response"""
            class MockResponse:
                status_code = 200
                def json(self):
                    return {"status": "healthy", "service": "mock-service"}
            return MockResponse()

        async def aclose(self):
            """Mock aclose method for proper cleanup"""
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    # Replace httpx.AsyncClient with our mock
    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    # Import app after patching to ensure it uses mocked client
    from app.main import app

    # Create test client
    with TestClient(app) as client:
        yield client


@pytest.fixture
def admin_headers():
    """
    Authentication headers for admin endpoints
    Uses the default dev API key from settings
    """
    return {"X-Admin-Key": "dev-admin-key-change-in-production"}


@pytest.fixture
def invalid_admin_headers():
    """
    Invalid authentication headers for testing unauthorized access
    """
    return {"X-Admin-Key": "invalid-key-12345"}


@pytest.fixture
def mock_portfolio_data():
    """
    Mock portfolio data matching the structure from portfolio-manager service
    Provides realistic test data for risk calculations
    FIXED: Changed 'market_value' to 'current_value' to match actual field names
    """
    return {
        "portfolio": {
            "total_value": 10000.0,
            "available_balance": 5000.0,
            "total_return_pct": 5.0,
            "holdings": [
                {
                    "symbol": "BTCUSDT",
                    "quantity": 0.5,
                    "current_price": 45000.0,
                    "current_value": 22500.0,  # FIXED: was 'market_value'
                    "unrealized_pnl": 2500.0,
                    "unrealized_pnl_pct": 12.5
                },
                {
                    "symbol": "ETHUSDT",
                    "quantity": 5.0,
                    "current_price": 3000.0,
                    "current_value": 15000.0,  # FIXED: was 'market_value'
                    "unrealized_pnl": 1000.0,
                    "unrealized_pnl_pct": 7.14
                }
            ]
        }
    }


@pytest.fixture
def mock_portfolio_data_concentrated():
    """
    Mock portfolio data with concentrated positions (>25% in single asset)
    Used for testing concentration risk alerts
    FIXED: Changed 'market_value' to 'current_value'
    """
    return {
        "portfolio": {
            "total_value": 10000.0,
            "available_balance": 2000.0,
            "total_return_pct": 3.0,
            "holdings": [
                {
                    "symbol": "BTCUSDT",
                    "quantity": 0.18,
                    "current_price": 45000.0,
                    "current_value": 8100.0,  # FIXED: was 'market_value', 81% of portfolio
                    "unrealized_pnl": 1000.0,
                    "unrealized_pnl_pct": 14.08
                }
            ]
        }
    }


@pytest.fixture
def mock_empty_portfolio():
    """
    Mock portfolio with no holdings
    Used for testing edge cases and zero-balance scenarios
    """
    return {
        "portfolio": {
            "total_value": 10000.0,
            "available_balance": 10000.0,
            "total_return_pct": 0.0,
            "holdings": []
        }
    }


@pytest.fixture
def sample_returns():
    """
    Sample historical returns for testing performance metrics
    Returns a list of daily returns (as percentages)
    """
    return [
        0.02, -0.01, 0.03, -0.02, 0.01,  # First week
        0.015, -0.005, 0.025, -0.015, 0.01,  # Second week
        0.02, -0.01, 0.03, -0.02, 0.01,  # Third week
        0.01, -0.02, 0.025, -0.01, 0.015  # Fourth week
    ]


@pytest.fixture
def sample_historical_values():
    """
    Sample historical portfolio values for drawdown calculations
    Returns list of (timestamp, value) tuples
    """
    base_value = Decimal("10000")
    values = []

    # Simulate 30 days of values with some drawdown
    multipliers = [
        1.0, 1.02, 1.04, 1.03, 1.05,  # Growth phase
        1.07, 1.06, 1.04, 1.02, 1.0,  # Peak and decline
        0.98, 0.96, 0.94, 0.93, 0.95,  # Drawdown phase
        0.97, 0.99, 1.01, 1.03, 1.05,  # Recovery phase
        1.06, 1.08, 1.09, 1.10, 1.11,  # New high
        1.10, 1.09, 1.11, 1.12, 1.13   # Continued growth
    ]

    for i, mult in enumerate(multipliers):
        timestamp = datetime(2024, 1, 1 + i)
        value = base_value * Decimal(str(mult))
        values.append((timestamp, value))

    return values


@pytest.fixture
def risk_engine():
    """
    Fresh RiskEngine instance for unit testing
    Provides clean state for each test
    """
    return RiskEngine()


@pytest.fixture
def risk_engine_with_history(risk_engine, sample_returns):
    """
    RiskEngine instance pre-populated with historical returns
    Used for testing metrics that require historical data
    """
    risk_engine.historical_returns = sample_returns
    return risk_engine


@pytest.fixture
def mock_httpx_client(monkeypatch):
    """
    Mock httpx AsyncClient for testing external API calls
    Prevents actual network requests during tests
    """
    async def mock_get(url, *args, **kwargs):
        """Mock GET request handler"""
        response = Mock()
        response.status_code = 200
        response.json = Mock(return_value={
            "status": "healthy",
            "service": "portfolio-manager"
        })
        return response

    mock_client = AsyncMock()
    mock_client.get = mock_get

    # Monkeypatch the httpx.AsyncClient context manager
    async def mock_context_manager(*args, **kwargs):
        return mock_client

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return mock_client

        async def __aexit__(self, *args):
            pass

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    return mock_client


@pytest.fixture
def sample_trades():
    """
    Sample trade data for testing performance metrics
    Returns list of trade dictionaries
    """
    return [
        {
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": 0.1,
            "entry_price": 40000.0,
            "exit_price": 42000.0,
            "pnl": 200.0,
            "return_pct": 5.0,
            "timestamp": datetime(2024, 1, 1)
        },
        {
            "symbol": "ETHUSDT",
            "side": "buy",
            "quantity": 2.0,
            "entry_price": 2500.0,
            "exit_price": 2600.0,
            "pnl": 200.0,
            "return_pct": 4.0,
            "timestamp": datetime(2024, 1, 2)
        },
        {
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": 0.05,
            "entry_price": 43000.0,
            "exit_price": 42000.0,
            "pnl": -50.0,
            "return_pct": -2.33,
            "timestamp": datetime(2024, 1, 3)
        }
    ]


@pytest.fixture
def capital_metrics_sample():
    """
    Sample CapitalMetrics for testing
    Pre-calculated metrics matching typical portfolio state
    FIXED: Added max_position_size and recommended_position_size fields
    """
    return CapitalMetrics(
        total_capital=Decimal("10000"),
        allocated_capital=Decimal("5000"),
        available_capital=Decimal("4500"),  # After reserved capital
        reserved_capital=Decimal("500"),  # 5% of total
        capital_utilization=0.50,
        max_position_size=Decimal("200"),  # 2% of capital
        recommended_position_size=Decimal("100")  # 1% of capital
    )


@pytest.fixture
def exposure_metrics_sample():
    """
    Sample ExposureMetrics for testing - NO VIOLATIONS
    FIXED: Removed concentrated_positions to allow "no violations" tests to pass
    This represents a well-diversified portfolio with no concentration risk
    """
    return ExposureMetrics(
        total_exposure=Decimal("3750"),
        exposure_ratio=0.15,  # Well below 20% max
        long_exposure=Decimal("3750"),
        short_exposure=Decimal("0"),
        net_exposure=Decimal("3750"),
        gross_exposure=Decimal("3750"),
        leverage=0.375,
        concentrated_positions=[]  # No concentration issues
    )


@pytest.fixture
def drawdown_metrics_sample():
    """
    Sample DrawdownMetrics for testing
    FIXED: Added underwater_periods and avg_drawdown fields
    """
    return DrawdownMetrics(
        current_drawdown=0.05,
        max_drawdown=0.08,
        max_drawdown_date=datetime(2024, 1, 15),
        underwater_period_days=5,
        recovery_factor=2.5,
        underwater_periods=3,
        avg_drawdown=0.03
    )


@pytest.fixture
def performance_metrics_sample():
    """
    Sample PerformanceMetrics for testing
    FIXED: Added largest_win, largest_loss, and total_trades fields
    """
    return PerformanceMetrics(
        total_return=0.15,
        annualized_return=0.60,
        volatility=0.15,
        sharpe_ratio=2.5,
        sortino_ratio=3.2,
        calmar_ratio=7.5,
        max_drawdown=0.08,
        win_rate=0.65,
        profit_factor=1.8,
        average_win=0.03,
        average_loss=-0.02,
        largest_win=0.08,
        largest_loss=-0.05,
        total_trades=50
    )


@pytest.fixture
def var_metrics_sample():
    """
    Sample ValueAtRisk metrics for testing
    FIXED: Added cvar_99 field and changed 'method' to 'calculation_method'
    """
    return ValueAtRisk(
        var_95=Decimal("250"),
        var_99=Decimal("350"),
        cvar_95=Decimal("300"),
        cvar_99=Decimal("400"),
        confidence_level=0.95,
        time_horizon_days=1,
        calculation_method="historical"
    )


# Pytest markers explanation
pytestmark = pytest.mark.unit
