"""
Pytest configuration and fixtures for notification service tests
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, patch

@pytest.fixture
def test_client():
    """Create test client for FastAPI app"""
    from app.main import app
    return TestClient(app)


@pytest.fixture
def mock_email_notifier():
    """Mock email notifier"""
    mock = Mock()
    mock.notify_trade_executed.return_value = True
    mock.notify_profit_loss.return_value = True
    mock.notify_daily_limit_reached.return_value = True
    mock.notify_error.return_value = True
    mock.notify_startup.return_value = True
    mock.send_email.return_value = True
    return mock


@pytest.fixture
def mock_telegram_notifier():
    """Mock Telegram notifier"""
    mock = AsyncMock()
    mock.notify_trade_executed.return_value = True
    mock.notify_profit_loss.return_value = True
    mock.notify_daily_limit_reached.return_value = True
    mock.notify_error.return_value = True
    mock.notify_startup.return_value = True
    mock.notify_daily_summary.return_value = True
    mock.send_message.return_value = True
    return mock


@pytest.fixture
def sample_trade_notification():
    """Sample trade notification data"""
    return {
        "action": "BUY",
        "symbol": "BTCUSDT",
        "quantity": 1.0,
        "price": 45000.0,
        "timestamp": "2025-11-21T00:00:00",
        "signal_confidence": 0.85
    }


@pytest.fixture
def sample_pnl_notification():
    """Sample P&L notification data"""
    return {
        "trade": {
            "action": "SELL",
            "symbol": "BTCUSDT",
            "quantity": 1.0,
            "price": 46000.0,
            "timestamp": "2025-11-21T01:00:00",
            "signal_confidence": 0.80
        },
        "pnl": 1000.0
    }


@pytest.fixture
def sample_error_notification():
    """Sample error notification data"""
    return {
        "error_message": "Failed to execute trade",
        "context": {
            "symbol": "BTCUSDT",
            "action": "BUY",
            "error_code": "INSUFFICIENT_BALANCE"
        }
    }


@pytest.fixture
def sample_startup_notification():
    """Sample startup notification data"""
    return {
        "mode": "PAPER_TRADING",
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "interval_minutes": 60,
        "capital": 100000.0,
        "max_position_pct": 20.0,
        "daily_loss_limit": 5.0,
        "stop_loss_pct": 2.0
    }


@pytest.fixture
def sample_daily_summary():
    """Sample daily summary data"""
    return {
        "total_pnl": 2500.0,
        "total_trades": 10,
        "win_rate": 70.0,
        "best_trade": 800.0,
        "worst_trade": -300.0,
        "balance": 102500.0,
        "open_positions": 2
    }
