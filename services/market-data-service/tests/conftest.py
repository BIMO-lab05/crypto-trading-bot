"""
Market Data Service - pytest Configuration
Purpose: Shared fixtures and configuration for all tests
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(autouse=True)
def setup_app_state():
    """
    Setup app.state for tests
    This fixture runs automatically before every test to mock the fetcher
    """
    # Create a mock fetcher with all necessary methods
    mock_fetcher = AsyncMock()
    mock_fetcher.get_kline_data = AsyncMock(return_value=[])
    mock_fetcher.get_ticker_data = AsyncMock(return_value={})
    mock_fetcher.close = AsyncMock()

    # Attach to app.state
    app.state.fetcher = mock_fetcher

    yield mock_fetcher

    # Cleanup after test
    if hasattr(app.state, 'fetcher'):
        delattr(app.state, 'fetcher')


@pytest.fixture(autouse=True)
def disable_api_key_verification():
    """
    Disable API key verification for tests
    This allows tests to run without needing valid API keys
    """
    from app.auth import verify_api_key

    # Mock the verify_api_key dependency to always pass
    async def mock_verify_api_key(api_key: str = None):
        return True

    # Override the dependency in the app
    app.dependency_overrides[verify_api_key] = mock_verify_api_key

    yield

    # Clean up after test
    app.dependency_overrides.clear()


@pytest.fixture
def mock_fetcher():
    """
    Provides a mock fetcher for tests that need to customize behavior
    """
    fetcher = AsyncMock()
    fetcher.get_kline_data = AsyncMock(return_value=[])
    fetcher.get_ticker_data = AsyncMock(return_value={})
    fetcher.close = AsyncMock()
    return fetcher


@pytest.fixture(autouse=True)
def disable_rate_limiting():
    """
    Disable rate limiting for tests globally
    This prevents tests from failing due to rate limits
    """
    from app.main import limiter

    # Store original enabled state
    original_enabled = limiter.enabled

    # Disable rate limiting for tests
    limiter.enabled = False

    yield

    # Re-enable after test
    limiter.enabled = original_enabled
