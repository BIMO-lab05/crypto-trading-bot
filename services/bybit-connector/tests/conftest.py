"""
Pytest Configuration and Fixtures
Purpose: Shared test fixtures and configuration for all tests
"""

import pytest
import os
from typing import AsyncGenerator, Generator
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, patch
import httpx

# Set test environment variables before importing app
os.environ["BYBIT_API_KEY"] = "test_api_key_12345"
os.environ["BYBIT_API_SECRET"] = "test_api_secret_67890"
os.environ["BYBIT_TESTNET"] = "true"
os.environ["ENVIRONMENT"] = "development"
os.environ["DEBUG"] = "true"
# Force live mode so existing tests use the live branch (BybitRestClient patched via conftest).
# New tape-mode tests use TapeReplayClient directly with tmp_path fixtures — no env needed.
os.environ["MARKET_DATA_SOURCE"] = "live"

from app.main import app
from app.config import Settings, get_settings
from app.bybit_rest_client import BybitRestClient
from app.auth import BybitAuthenticator


# ============================================================================
# CONFIGURATION FIXTURES
# ============================================================================

@pytest.fixture
def test_settings() -> Settings:
    """Provide test settings instance"""
    return Settings(
        bybit_api_key="test_api_key_12345",
        bybit_api_secret="test_api_secret_67890",
        bybit_testnet=True,
        environment="development",
        debug=True,
        allowed_origins="http://localhost:3000,http://testapp.com"
    )


# ============================================================================
# AUTHENTICATION FIXTURES
# ============================================================================

@pytest.fixture
def auth_client(test_settings) -> BybitAuthenticator:
    """Provide Bybit authenticator instance"""
    return BybitAuthenticator(
        api_key=test_settings.bybit_api_key,
        api_secret=test_settings.bybit_api_secret,
        recv_window=test_settings.bybit_recv_window
    )


# ============================================================================
# REST CLIENT FIXTURES
# ============================================================================

@pytest.fixture
async def mock_rest_client(test_settings) -> AsyncGenerator[Mock, None]:
    """Provide mocked REST client"""
    mock_client = Mock(spec=BybitRestClient)

    # Mock async methods
    mock_client.close = AsyncMock()
    mock_client.get_ticker = AsyncMock(return_value={
        "retCode": 0,
        "retMsg": "OK",
        "result": {"list": [{"symbol": "BTCUSDT", "lastPrice": "50000"}]}
    })
    mock_client.place_order = AsyncMock(return_value={
        "retCode": 0,
        "retMsg": "OK",
        "result": {"orderId": "test-order-123", "orderLinkId": ""}
    })

    yield mock_client


# ============================================================================
# FASTAPI TEST CLIENT FIXTURES
# ============================================================================

@pytest.fixture
def client(mock_rest_client) -> Generator[TestClient, None, None]:
    """
    Provide FastAPI test client with mocked dependencies
    """
    with patch('app.main.create_rest_client', return_value=mock_rest_client):
        with TestClient(app) as test_client:
            # Inject mocked client into app state
            test_client.app.state.rest_client = mock_rest_client
            yield test_client


# ============================================================================
# MOCK HTTP RESPONSE FIXTURES
# ============================================================================

@pytest.fixture
def mock_http_response_success():
    """Mock successful HTTP response"""
    response = Mock(spec=httpx.Response)
    response.status_code = 200
    response.json.return_value = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {"data": "test"}
    }
    response.text = '{"retCode": 0, "retMsg": "OK", "result": {"data": "test"}}'
    return response


@pytest.fixture
def mock_http_response_error():
    """Mock error HTTP response"""
    response = Mock(spec=httpx.Response)
    response.status_code = 400
    response.json.return_value = {
        "retCode": 10001,
        "retMsg": "Invalid parameter"
    }
    response.text = '{"retCode": 10001, "retMsg": "Invalid parameter"}'
    return response


# ============================================================================
# ORDER DATA FIXTURES
# ============================================================================

@pytest.fixture
def valid_order_data():
    """Provide valid order request data"""
    return {
        "category": "linear",
        "symbol": "BTCUSDT",
        "side": "Buy",
        "order_type": "Limit",
        "qty": "0.01",
        "price": "50000",
        "time_in_force": "GTC"
    }


@pytest.fixture
def invalid_order_data():
    """Provide invalid order request data"""
    return {
        "category": "linear",
        "symbol": "BTCUSDT",
        "side": "InvalidSide",  # Invalid
        "order_type": "Limit",
        "qty": "-0.01",  # Negative quantity
        "price": "50000"
    }
