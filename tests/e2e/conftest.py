#!/usr/bin/env python3
"""
Pytest Configuration for E2E Tests

Provides fixtures for service clients, test data, and test setup/teardown.
"""

import pytest
import pytest_asyncio
import asyncio
import httpx
from typing import AsyncGenerator, Dict
from decimal import Decimal

from tests.e2e.utils.wait_for_health import wait_for_service_health, wait_for_all_services
from tests.e2e.fixtures.mock_data import (
    generate_bullish_candles,
    generate_portfolio_data,
    generate_indicator_data,
)


# ============================================================================
# Service Client Fixtures
# ============================================================================

class ServiceClient:
    """Base class for service HTTP clients."""

    def __init__(self, client: httpx.AsyncClient, base_url: str):
        self.client = client
        self.base_url = base_url

    async def get(self, path: str, **kwargs):
        """GET request."""
        return await self.client.get(f"{self.base_url}{path}", **kwargs)

    async def post(self, path: str, **kwargs):
        """POST request."""
        return await self.client.post(f"{self.base_url}{path}", **kwargs)

    async def put(self, path: str, **kwargs):
        """PUT request."""
        return await self.client.put(f"{self.base_url}{path}", **kwargs)

    async def delete(self, path: str, **kwargs):
        """DELETE request."""
        return await self.client.delete(f"{self.base_url}{path}", **kwargs)


class MarketDataClient(ServiceClient):
    """Client for Market Data Service."""

    async def inject_candles(self, symbol: str, candles: list, interval: str = "60"):
        """Inject mock candle data for testing."""
        return await self.post(
            f"/api/v1/market-data/inject",
            json={
                "symbol": symbol,
                "interval": interval,
                "candles": candles
            }
        )

    async def get_latest_price(self, symbol: str):
        """Get latest price for symbol."""
        response = await self.get(f"/api/v1/market-data/{symbol}/latest")
        return response.json()

    async def get_candles(self, symbol: str, interval: str = "60", limit: int = 100):
        """Get historical candles."""
        response = await self.get(
            f"/api/v1/market-data/{symbol}/candles",
            params={"interval": interval, "limit": limit}
        )
        return response.json()


class TradingEngineClient(ServiceClient):
    """Client for Trading Engine."""

    async def get_aggregate_signal(self, symbol: str, interval: str = "60"):
        """Get aggregated trading signal."""
        response = await self.get(
            f"/api/v1/signals/aggregate",
            params={"symbol": symbol, "interval": interval}
        )
        return response.json() if response.status_code == 200 else None

    async def execute_trade(self, symbol: str, side: str, quantity: float):
        """Execute a trade."""
        response = await self.post(
            f"/api/v1/trading/execute",
            json={
                "symbol": symbol,
                "side": side,
                "quantity": quantity
            }
        )
        return response.json()

    async def get_positions(self):
        """Get all open positions."""
        response = await self.get("/api/v1/positions")
        return response.json() if response.status_code == 200 else []

    async def close_position(self, position_id: str):
        """Close a specific position."""
        response = await self.post(f"/api/v1/positions/{position_id}/close")
        return response.json()


class PortfolioClient(ServiceClient):
    """Client for Portfolio Manager."""

    async def get_balance(self):
        """Get current account balance."""
        response = await self.get("/api/v1/portfolio/balance")
        data = response.json() if response.status_code == 200 else {}
        return Decimal(str(data.get("balance", 0)))

    async def set_balance(self, amount: Decimal):
        """Set account balance (for testing)."""
        response = await self.post(
            "/api/v1/portfolio/balance",
            json={"balance": float(amount)}
        )
        return response.status_code == 200

    async def get_positions(self):
        """Get all positions."""
        response = await self.get("/api/v1/portfolio/positions")
        return response.json() if response.status_code == 200 else []

    async def get_trade_history(self, limit: int = 100):
        """Get trade history."""
        response = await self.get(
            "/api/v1/portfolio/trades",
            params={"limit": limit}
        )
        return response.json() if response.status_code == 200 else []

    async def get_pnl(self):
        """Get current P&L."""
        response = await self.get("/api/v1/portfolio/pnl")
        data = response.json() if response.status_code == 200 else {}
        return Decimal(str(data.get("total_pnl", 0)))

    async def close_position(self, position_id: str):
        """Close a specific position."""
        response = await self.post(f"/api/v1/portfolio/positions/{position_id}/close")
        return response.json()


class TechnicalAnalysisClient(ServiceClient):
    """Client for Technical Analysis Service."""

    async def get_indicators(self, symbol: str, interval: str = "60"):
        """Get technical indicators."""
        response = await self.get(
            f"/api/v1/indicators/{symbol}",
            params={"interval": interval}
        )
        return response.json() if response.status_code == 200 else {}

    async def get_signal(self, symbol: str, interval: str = "60"):
        """Get trading signal from TA."""
        response = await self.get(
            f"/api/v1/signals/{symbol}",
            params={"interval": interval}
        )
        return response.json() if response.status_code == 200 else None


class APIGatewayClient(ServiceClient):
    """Client for API Gateway."""

    async def health_check(self):
        """Check API Gateway health."""
        response = await self.get("/health")
        return response.json() if response.status_code == 200 else {}

    async def proxy_request(self, service: str, path: str, **kwargs):
        """Make a request through the API Gateway."""
        full_path = f"/{service}{path}"
        return await self.get(full_path, **kwargs)


# ============================================================================
# Pytest Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def ensure_services_healthy():
    """Ensure all required services are healthy before running tests."""
    print("\n" + "="*60)
    print("CHECKING SERVICE HEALTH BEFORE E2E TESTS")
    print("="*60 + "\n")

    # Only check critical services for E2E tests
    critical_services = [
        "trading-engine",
        "market-data",
        "portfolio-manager",
        "technical-analysis",
    ]

    results = await wait_for_all_services(
        services=critical_services,
        timeout=60,
        fail_fast=True
    )

    # Check if all services are healthy
    all_healthy = all(results.values())

    if not all_healthy:
        unhealthy = [name for name, status in results.items() if not status]
        pytest.fail(f"Services not healthy: {unhealthy}")

    print("✅ All critical services are healthy\n")
    yield results


@pytest_asyncio.fixture
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provide an async HTTP client."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


@pytest_asyncio.fixture
async def market_data_client(http_client, ensure_services_healthy) -> MarketDataClient:
    """Provide Market Data Service client."""
    return MarketDataClient(http_client, "http://localhost:8003")


@pytest_asyncio.fixture
async def trading_engine_client(http_client, ensure_services_healthy) -> TradingEngineClient:
    """Provide Trading Engine client."""
    return TradingEngineClient(http_client, "http://localhost:8005")


@pytest_asyncio.fixture
async def portfolio_client(http_client, ensure_services_healthy) -> PortfolioClient:
    """Provide Portfolio Manager client."""
    return PortfolioClient(http_client, "http://localhost:8006")


@pytest_asyncio.fixture
async def technical_analysis_client(http_client, ensure_services_healthy) -> TechnicalAnalysisClient:
    """Provide Technical Analysis Service client."""
    return TechnicalAnalysisClient(http_client, "http://localhost:8004")


@pytest_asyncio.fixture
async def api_gateway_client(http_client) -> APIGatewayClient:
    """Provide API Gateway client."""
    return APIGatewayClient(http_client, "http://localhost:8000")


# ============================================================================
# Test Data Fixtures
# ============================================================================

@pytest.fixture
def bullish_market_data():
    """Generate bullish market data."""
    return generate_bullish_candles(start_price=100.0, num_candles=50, price_increase_pct=10.0)


@pytest.fixture
def bearish_market_data():
    """Generate bearish market data."""
    from tests.e2e.fixtures.mock_data import generate_bearish_candles
    return generate_bearish_candles(start_price=100.0, num_candles=50, price_decrease_pct=10.0)


@pytest.fixture
def initial_portfolio():
    """Generate initial portfolio state."""
    return generate_portfolio_data(balance=10000.0, positions=[])


@pytest.fixture
def bullish_indicators():
    """Generate bullish technical indicators."""
    return generate_indicator_data(
        rsi=25.0,  # Oversold
        macd=1.5,  # Positive
        bb_position=15.0,  # Near lower band
        trend_filter="BULLISH"
    )


@pytest.fixture
def bearish_indicators():
    """Generate bearish technical indicators."""
    return generate_indicator_data(
        rsi=75.0,  # Overbought
        macd=-1.5,  # Negative
        bb_position=85.0,  # Near upper band
        trend_filter="BEARISH"
    )


# ============================================================================
# Setup/Teardown Fixtures
# ============================================================================

@pytest_asyncio.fixture(autouse=True)
async def cleanup_between_tests(portfolio_client):
    """
    Cleanup state between tests.

    This fixture runs automatically before each test to ensure clean state.
    """
    # Setup: Nothing to do before test
    yield

    # Teardown: Clean up after test
    try:
        # Close all open positions
        positions = await portfolio_client.get_positions()
        for position in positions:
            try:
                await portfolio_client.close_position(position.get("id"))
            except Exception as e:
                print(f"Warning: Failed to close position {position.get('id')}: {e}")

        # Reset balance to default (optional)
        # await portfolio_client.set_balance(Decimal("10000.00"))

    except Exception as e:
        print(f"Warning: Cleanup failed: {e}")


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_environment():
    """
    Setup test environment once before all tests.

    This runs once at the start of the test session.
    """
    print("\n" + "="*60)
    print("SETTING UP E2E TEST ENVIRONMENT")
    print("="*60 + "\n")

    # Setup tasks
    # - Initialize test database
    # - Clear Redis cache
    # - Reset RabbitMQ queues
    # etc.

    yield

    # Teardown: Clean up after all tests
    print("\n" + "="*60)
    print("TEARING DOWN E2E TEST ENVIRONMENT")
    print("="*60 + "\n")


# ============================================================================
# Pytest Configuration
# ============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "smoke: mark test as smoke test (critical path)"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically."""
    for item in items:
        # Auto-mark tests in e2e directory
        if "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
