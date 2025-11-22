"""
Integration Test Configuration
Shared fixtures and utilities for integration tests
"""

import pytest
import asyncio
import httpx
from typing import AsyncGenerator, Dict
import os


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def services_config() -> Dict[str, str]:
    """Service URLs configuration"""
    return {
        "api_gateway": os.getenv("API_GATEWAY_URL", "http://localhost:8000"),
        "trading_engine": os.getenv("TRADING_ENGINE_URL", "http://localhost:8001"),
        "market_data": os.getenv("MARKET_DATA_URL", "http://localhost:8002"),
        "technical_analysis": os.getenv("TECHNICAL_ANALYSIS_URL", "http://localhost:8003"),
        "portfolio_manager": os.getenv("PORTFOLIO_MANAGER_URL", "http://localhost:8004"),
        "bybit_connector": os.getenv("BYBIT_CONNECTOR_URL", "http://localhost:8005"),
    }


@pytest.fixture(scope="session")
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """HTTP client for API calls"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


@pytest.fixture(scope="function")
async def wait_for_services(services_config, http_client):
    """Wait for all services to be healthy"""
    max_attempts = 30
    for service_name, url in services_config.items():
        for attempt in range(max_attempts):
            try:
                response = await http_client.get(f"{url}/health")
                if response.status_code == 200:
                    print(f"✅ {service_name} is healthy")
                    break
            except:
                if attempt == max_attempts - 1:
                    pytest.fail(f"Service {service_name} not available")
                await asyncio.sleep(2)


@pytest.fixture(scope="function")
def test_symbol():
    """Test trading symbol"""
    return "BTCUSDT"


@pytest.fixture(scope="function")
def test_portfolio_id():
    """Test portfolio ID"""
    return "test_portfolio"
