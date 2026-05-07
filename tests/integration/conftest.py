"""
Integration Test Configuration
Shared fixtures and utilities for integration tests
"""

import asyncio
import os
from typing import AsyncGenerator, Dict

import httpx
import pytest


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def services_config() -> Dict[str, str]:
    """Service URLs configuration. Ports per crypto-trading-bot/CLAUDE.md and bootstrap.sh:67-78.
    Phase 2 fix: prior version inverted bybit_connector (8001) and trading_engine (8005).
    """
    return {
        "api_gateway": os.getenv("API_GATEWAY_URL", "http://localhost:8000"),
        "bybit_connector": os.getenv("BYBIT_CONNECTOR_URL", "http://localhost:8001"),
        "market_data": os.getenv("MARKET_DATA_URL", "http://localhost:8002"),
        "portfolio": os.getenv("PORTFOLIO_URL", "http://localhost:8003"),
        "technical_analysis": os.getenv("TA_URL", "http://localhost:8004"),
        "trading_engine": os.getenv("TRADING_ENGINE_URL", "http://localhost:8005"),
        "notification": os.getenv("NOTIFICATION_URL", "http://localhost:8006"),
        "ml_prediction": os.getenv("ML_PREDICTION_URL", "http://localhost:8007"),
        "sentiment": os.getenv("SENTIMENT_URL", "http://localhost:8008"),
        "risk_metrics": os.getenv("RISK_METRICS_URL", "http://localhost:8009"),
    }


@pytest.fixture(scope="session")
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """HTTP client for API calls"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


@pytest.fixture(scope="session")
def bootstrap_stack(services_config):
    """Stub session fixture — body replaced in Task 2 (bootstrap_stack + tmp_fresh_clone).
    Session-scoped per D-03: single boot shared across the whole pytest run.
    """
    # Placeholder: Task 2 replaces this body with subprocess.run(bootstrap.sh)
    pass


@pytest.fixture(scope="session")
def wait_for_services(bootstrap_stack):
    """Backward-compat alias. New tests should depend on bootstrap_stack directly."""
    return bootstrap_stack


@pytest.fixture(scope="function")
def test_symbol():
    """Test trading symbol"""
    return "BTCUSDT"


@pytest.fixture(scope="function")
def test_portfolio_id():
    """Test portfolio ID"""
    return "test_portfolio"
