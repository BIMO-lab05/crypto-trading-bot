"""
Unit Tests for Notification Service Main Application
Tests all notification endpoints and integration
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime


class TestHealthEndpoint:
    """Test health check endpoint"""

    def test_health_check_returns_healthy_status(self, test_client):
        """Test health check endpoint returns healthy status"""
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data
        assert "version" in data
        assert "timestamp" in data

    def test_health_check_includes_configuration(self, test_client):
        """Test health check includes notification configuration.

        Channel flags moved under data['channels'] when the health response
        was reshaped to group related fields.
        """
        response = test_client.get("/health")
        data = response.json()

        assert "channels" in data
        channels = data["channels"]
        assert "email_enabled" in channels
        assert "telegram_enabled" in channels
        assert isinstance(channels["email_enabled"], bool)
        assert isinstance(channels["telegram_enabled"], bool)


class TestConfigurationEndpoint:
    """Test configuration endpoint"""

    def test_get_config_returns_configuration(self, test_client):
        """Test configuration endpoint returns settings"""
        response = test_client.get("/api/v1/config")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "config" in data

    def test_get_config_includes_all_settings(self, test_client):
        """Test configuration includes all relevant settings"""
        response = test_client.get("/api/v1/config")
        data = response.json()
        config = data["config"]

        required_settings = [
            "email_enabled",
            "telegram_enabled",
            "alert_on_trade",
            "alert_on_profit",
            "alert_on_loss",
            "alert_on_daily_limit",
            "alert_on_error",
            "alert_on_startup"
        ]

        for setting in required_settings:
            assert setting in config


class TestTradeNotificationEndpoint:
    """Test trade notification endpoint"""

    @pytest.mark.asyncio
    async def test_notify_trade_success(
        self,
        test_client,
        sample_trade_notification,
        mock_email_notifier,
        mock_telegram_notifier
    ):
        """Test successful trade notification"""
        with patch('app.main.email_notifier', mock_email_notifier), \
             patch('app.main.telegram_notifier', mock_telegram_notifier), \
             patch('app.main.config') as mock_config:

            mock_config.email_enabled = True
            mock_config.telegram_enabled = True

            response = test_client.post(
                "/api/v1/notify/trade",
                json=sample_trade_notification
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "timestamp" in data

    def test_notify_trade_validates_required_fields(self, test_client):
        """Test trade notification validates required fields"""
        invalid_data = {
            "action": "BUY",
            # Missing required fields: symbol, quantity, price, timestamp
        }

        response = test_client.post(
            "/api/v1/notify/trade",
            json=invalid_data
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_notify_trade_handles_email_failure(
        self,
        test_client,
        sample_trade_notification,
        mock_email_notifier,
        mock_telegram_notifier
    ):
        """Partial-delivery failure now surfaces as 502 (false-success fix).

        Previously the endpoint returned 200 with `success=True` even when one
        channel failed. The PR replaced that pattern: any failed channel now
        raises 502 so callers can react instead of trusting HTTP 200.
        """
        mock_email_notifier.notify_trade_executed.return_value = False

        with patch('app.main.email_notifier', mock_email_notifier), \
             patch('app.main.telegram_notifier', mock_telegram_notifier), \
             patch('app.main.config') as mock_config:

            mock_config.email_enabled = True
            mock_config.telegram_enabled = True

            response = test_client.post(
                "/api/v1/notify/trade",
                json=sample_trade_notification
            )

        assert response.status_code == 502
        detail = response.json()["detail"]
        assert detail["success"] is False
        assert detail["email_sent"] is False
        assert "email" in detail["failed_channels"]

    def test_notify_trade_with_optional_confidence(self, test_client):
        """Endpoint accepts the optional confidence field; with no channels
        enabled it now returns 503 per the false-success fix."""
        notification_with_confidence = {
            "action": "BUY",
            "symbol": "BTCUSDT",
            "quantity": 1.0,
            "price": 45000.0,
            "timestamp": "2025-11-21T00:00:00",
            "signal_confidence": 0.95
        }

        with patch('app.main.config') as mock_config:
            mock_config.email_enabled = False
            mock_config.telegram_enabled = False

            response = test_client.post(
                "/api/v1/notify/trade",
                json=notification_with_confidence
            )

        assert response.status_code == 503


class TestProfitLossNotificationEndpoint:
    """Test profit/loss notification endpoint"""

    @pytest.mark.asyncio
    async def test_notify_pnl_success(
        self,
        test_client,
        sample_pnl_notification,
        mock_email_notifier,
        mock_telegram_notifier
    ):
        """Test successful P&L notification"""
        with patch('app.main.email_notifier', mock_email_notifier), \
             patch('app.main.telegram_notifier', mock_telegram_notifier), \
             patch('app.main.config') as mock_config:

            mock_config.email_enabled = True
            mock_config.telegram_enabled = True

            response = test_client.post(
                "/api/v1/notify/pnl",
                json=sample_pnl_notification
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_notify_pnl_positive(self, test_client):
        """Endpoint accepts positive P&L; no-channels-enabled now returns 503."""
        notification = {
            "trade": {
                "action": "SELL",
                "symbol": "BTCUSDT",
                "quantity": 1.0,
                "price": 46000.0,
                "timestamp": "2025-11-21T01:00:00"
            },
            "pnl": 1000.0  # Positive P&L
        }

        with patch('app.main.config') as mock_config:
            mock_config.email_enabled = False
            mock_config.telegram_enabled = False

            response = test_client.post("/api/v1/notify/pnl", json=notification)

        assert response.status_code == 503

    def test_notify_pnl_negative(self, test_client):
        """Endpoint accepts negative P&L; no-channels-enabled now returns 503."""
        notification = {
            "trade": {
                "action": "SELL",
                "symbol": "BTCUSDT",
                "quantity": 1.0,
                "price": 44000.0,
                "timestamp": "2025-11-21T01:00:00"
            },
            "pnl": -1000.0  # Negative P&L
        }

        with patch('app.main.config') as mock_config:
            mock_config.email_enabled = False
            mock_config.telegram_enabled = False

            response = test_client.post("/api/v1/notify/pnl", json=notification)

        assert response.status_code == 503


class TestDailyLimitNotificationEndpoint:
    """Test daily limit notification endpoint"""

    @pytest.mark.asyncio
    async def test_notify_daily_limit_success(
        self,
        test_client,
        mock_email_notifier,
        mock_telegram_notifier
    ):
        """Test daily limit notification"""
        with patch('app.main.email_notifier', mock_email_notifier), \
             patch('app.main.telegram_notifier', mock_telegram_notifier), \
             patch('app.main.config') as mock_config:

            mock_config.email_enabled = True
            mock_config.telegram_enabled = True

            response = test_client.post(
                "/api/v1/notify/daily-limit",
                params={"total_loss": 5000.0}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_notify_daily_limit_with_zero_loss(self, test_client):
        """Endpoint accepts zero loss; no-channels-enabled now returns 503."""
        with patch('app.main.config') as mock_config:
            mock_config.email_enabled = False
            mock_config.telegram_enabled = False

            response = test_client.post(
                "/api/v1/notify/daily-limit",
                params={"total_loss": 0.0}
            )

        assert response.status_code == 503


class TestErrorNotificationEndpoint:
    """Test error notification endpoint"""

    @pytest.mark.asyncio
    async def test_notify_error_success(
        self,
        test_client,
        sample_error_notification,
        mock_email_notifier,
        mock_telegram_notifier
    ):
        """Test error notification"""
        with patch('app.main.email_notifier', mock_email_notifier), \
             patch('app.main.telegram_notifier', mock_telegram_notifier), \
             patch('app.main.config') as mock_config:

            mock_config.email_enabled = True
            mock_config.telegram_enabled = True

            response = test_client.post(
                "/api/v1/notify/error",
                json=sample_error_notification
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_notify_error_without_context(self, test_client):
        """Endpoint accepts error without context; no-channels → 503."""
        notification = {
            "error_message": "Generic error occurred"
        }

        with patch('app.main.config') as mock_config:
            mock_config.email_enabled = False
            mock_config.telegram_enabled = False

            response = test_client.post("/api/v1/notify/error", json=notification)

        assert response.status_code == 503

    def test_notify_error_with_context(self, test_client):
        """Endpoint accepts error with context; no-channels → 503."""
        notification = {
            "error_message": "Order execution failed",
            "context": {
                "order_id": "123456",
                "symbol": "BTCUSDT",
                "error_code": "INSUFFICIENT_MARGIN",
                "timestamp": "2025-11-21T02:00:00"
            }
        }

        with patch('app.main.config') as mock_config:
            mock_config.email_enabled = False
            mock_config.telegram_enabled = False

            response = test_client.post("/api/v1/notify/error", json=notification)

        assert response.status_code == 503


class TestStartupNotificationEndpoint:
    """Test startup notification endpoint"""

    @pytest.mark.asyncio
    async def test_notify_startup_success(
        self,
        test_client,
        sample_startup_notification,
        mock_email_notifier,
        mock_telegram_notifier
    ):
        """Test startup notification"""
        with patch('app.main.email_notifier', mock_email_notifier), \
             patch('app.main.telegram_notifier', mock_telegram_notifier), \
             patch('app.main.config') as mock_config:

            mock_config.email_enabled = True
            mock_config.telegram_enabled = True

            response = test_client.post(
                "/api/v1/notify/startup",
                json=sample_startup_notification
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_notify_startup_paper_trading_mode(self, test_client):
        """Endpoint accepts paper-trading payload; no-channels → 503."""
        notification = {
            "mode": "PAPER_TRADING",
            "symbols": ["BTCUSDT"],
            "interval_minutes": 60,
            "capital": 100000.0,
            "max_position_pct": 20.0,
            "daily_loss_limit": 5.0,
            "stop_loss_pct": 2.0
        }

        with patch('app.main.config') as mock_config:
            mock_config.email_enabled = False
            mock_config.telegram_enabled = False

            response = test_client.post("/api/v1/notify/startup", json=notification)

        assert response.status_code == 503

    def test_notify_startup_live_trading_mode(self, test_client):
        """Endpoint accepts live-trading payload; no-channels → 503."""
        notification = {
            "mode": "LIVE_TRADING",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "interval_minutes": 60,
            "capital": 10000.0,
            "max_position_pct": 10.0,
            "daily_loss_limit": 2.0,
            "stop_loss_pct": 1.5
        }

        with patch('app.main.config') as mock_config:
            mock_config.email_enabled = False
            mock_config.telegram_enabled = False

            response = test_client.post("/api/v1/notify/startup", json=notification)

        assert response.status_code == 503


class TestDailySummaryNotificationEndpoint:
    """Test daily summary notification endpoint"""

    @pytest.mark.asyncio
    async def test_notify_daily_summary_success(
        self,
        test_client,
        sample_daily_summary,
        mock_telegram_notifier
    ):
        """Test daily summary notification"""
        with patch('app.main.telegram_notifier', mock_telegram_notifier), \
             patch('app.main.config') as mock_config:

            mock_config.telegram_enabled = True

            response = test_client.post(
                "/api/v1/notify/daily-summary",
                json=sample_daily_summary
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "telegram_sent" in data

    def test_notify_daily_summary_profitable_day(self, test_client):
        """Endpoint accepts profitable summary; no-channels → 503."""
        summary = {
            "total_pnl": 5000.0,
            "total_trades": 15,
            "win_rate": 80.0,
            "best_trade": 1200.0,
            "worst_trade": -200.0,
            "balance": 105000.0,
            "open_positions": 1
        }

        with patch('app.main.config') as mock_config:
            mock_config.telegram_enabled = False
            mock_config.email_enabled = False

            response = test_client.post(
                "/api/v1/notify/daily-summary",
                json=summary
            )

        assert response.status_code == 503

    def test_notify_daily_summary_losing_day(self, test_client):
        """Endpoint accepts losing summary; no-channels → 503."""
        summary = {
            "total_pnl": -2000.0,
            "total_trades": 10,
            "win_rate": 40.0,
            "best_trade": 500.0,
            "worst_trade": -800.0,
            "balance": 98000.0,
            "open_positions": 0
        }

        with patch('app.main.config') as mock_config:
            mock_config.telegram_enabled = False
            mock_config.email_enabled = False

            response = test_client.post(
                "/api/v1/notify/daily-summary",
                json=summary
            )

        assert response.status_code == 503


class TestNotificationTestEndpoint:
    """Test notification test endpoint"""

    @pytest.mark.asyncio
    async def test_test_notifications_success(
        self,
        test_client,
        mock_email_notifier,
        mock_telegram_notifier
    ):
        """Test notification test endpoint.

        slack/sms must be explicitly disabled — the endpoint's `attempted` list
        includes any channel where `enabled` is truthy, and a bare MagicMock
        attribute is truthy, which would otherwise make the honest-success
        check fail.
        """
        with patch('app.main.email_notifier', mock_email_notifier), \
             patch('app.main.telegram_notifier', mock_telegram_notifier), \
             patch('app.main.config') as mock_config:

            mock_config.email_enabled = True
            mock_config.telegram_enabled = True
            mock_config.slack_enabled = False
            mock_config.sms_enabled = False

            response = test_client.post("/api/v1/test")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "results" in data
        assert "email" in data["results"]
        assert "telegram" in data["results"]

    @pytest.mark.asyncio
    async def test_test_notifications_email_disabled(
        self,
        test_client,
        mock_telegram_notifier
    ):
        """Test notification test with email disabled"""
        with patch('app.main.telegram_notifier', mock_telegram_notifier), \
             patch('app.main.config') as mock_config:

            mock_config.email_enabled = False
            mock_config.telegram_enabled = True

            response = test_client.post("/api/v1/test")

        assert response.status_code == 200
        data = response.json()
        assert data["results"]["email"]["enabled"] is False

    @pytest.mark.asyncio
    async def test_test_notifications_telegram_disabled(
        self,
        test_client,
        mock_email_notifier
    ):
        """Test notification test with Telegram disabled"""
        with patch('app.main.email_notifier', mock_email_notifier), \
             patch('app.main.config') as mock_config:

            mock_config.email_enabled = True
            mock_config.telegram_enabled = False

            response = test_client.post("/api/v1/test")

        assert response.status_code == 200
        data = response.json()
        assert data["results"]["telegram"]["enabled"] is False


class TestCORSConfiguration:
    """Test CORS middleware configuration"""

    def test_cors_allows_all_origins(self, test_client):
        """Test CORS allows all origins"""
        response = test_client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET"
            }
        )

        assert response.status_code == 200

    def test_cors_allows_post_methods(self, test_client):
        """Test CORS allows POST methods"""
        response = test_client.options(
            "/api/v1/notify/trade",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST"
            }
        )

        assert response.status_code == 200


class TestErrorHandling:
    """Test error handling across the application"""

    @pytest.mark.asyncio
    async def test_invalid_json_returns_422(self, test_client):
        """Test invalid JSON returns 422 error"""
        response = test_client.post(
            "/api/v1/notify/trade",
            data="invalid json"
        )

        assert response.status_code == 422

    def test_missing_required_fields_returns_422(self, test_client):
        """Test missing required fields returns validation error"""
        incomplete_data = {
            "action": "BUY"
            # Missing other required fields
        }

        response = test_client.post(
            "/api/v1/notify/trade",
            json=incomplete_data
        )

        assert response.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
