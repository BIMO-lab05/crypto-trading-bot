"""
Pytest Configuration and Fixtures
Provides common test utilities and mock services
"""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock
import httpx

from app.auth_middleware import get_current_active_user, get_current_admin_user
from app.auth_models import User
from app.main import app
from app.services.service_proxy import ServiceProxy


def _fake_admin() -> User:
    return User(
        user_id="test-admin",
        username="testadmin",
        email="admin@test.local",
        full_name="Test Admin",
        is_active=True,
        is_admin=True,
        created_at=datetime.utcnow(),
    )


@pytest.fixture
def admin_client():
    """TestClient with auth dependencies overridden to a fake admin user.

    Use for routes guarded by `get_current_admin_user`. Auth was added to
    several endpoints (e.g. /api/portfolio/emergency-stop) after the
    integration tests were written; this fixture lets those tests exercise
    the route logic without forging JWTs.
    """
    user = _fake_admin()
    app.dependency_overrides[get_current_admin_user] = lambda: user
    app.dependency_overrides[get_current_active_user] = lambda: user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_admin_user, None)
        app.dependency_overrides.pop(get_current_active_user, None)


@pytest.fixture
def mock_service_proxy():
    """Mock ServiceProxy for testing without real backend services"""
    proxy = Mock(spec=ServiceProxy)
    proxy.initialize = AsyncMock()
    proxy.cleanup = AsyncMock()
    proxy.proxy_request = AsyncMock()
    proxy.check_service_health = AsyncMock()
    proxy.aggregate_health_checks = AsyncMock()
    return proxy


@pytest.fixture
def test_client():
    """FastAPI test client"""
    return TestClient(app)


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient for testing HTTP requests"""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock()
    mock_client.post = AsyncMock()
    mock_client.put = AsyncMock()
    mock_client.delete = AsyncMock()
    mock_client.aclose = AsyncMock()
    return mock_client


@pytest.fixture
def sample_ticker_response():
    """Sample ticker response from market data service"""
    return {
        "success": True,
        "data": {
            "symbol": "BTCUSDT",
            "last_price": "45000.50",
            "price_change_24h": "2.5",
            "volume_24h": "1234567890",
            "high_24h": "46000.00",
            "low_24h": "44000.00",
            "timestamp": 1699200000000,
        },
    }


@pytest.fixture
def sample_portfolio_response():
    """Sample portfolio response"""
    return {
        "success": True,
        "data": {
            "portfolio_id": "default",
            "total_value": "100000.00",
            "cash_balance": "50000.00",
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "quantity": "1.0",
                    "avg_price": "44000.00",
                    "current_price": "45000.50",
                    "pnl": "1000.50",
                }
            ],
        },
    }


@pytest.fixture
def sample_health_checks():
    """Sample health check results"""
    return {
        "bybit": True,
        "market-data": True,
        "technical-analysis": True,
        "trading-engine": True,
        "portfolio-manager": True,
    }


@pytest.fixture
def mock_successful_response():
    """Mock successful HTTP response"""
    response = Mock(spec=httpx.Response)
    response.status_code = 200
    response.json.return_value = {"success": True, "data": {}}
    response.text = '{"success": true, "data": {}}'
    response.headers = {"content-type": "application/json"}
    return response


@pytest.fixture
def mock_error_response():
    """Mock error HTTP response"""
    response = Mock(spec=httpx.Response)
    response.status_code = 500
    response.json.return_value = {"success": False, "error": "Internal server error"}
    response.text = '{"success": false, "error": "Internal server error"}'
    response.headers = {"content-type": "application/json"}
    return response


@pytest.fixture
def mock_timeout_exception():
    """Mock httpx.TimeoutException"""
    return httpx.TimeoutException("Request timed out")


@pytest.fixture
def mock_request_error():
    """Mock httpx.RequestError"""
    return httpx.RequestError("Connection failed")
