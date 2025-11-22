"""
Tests for Monitoring Alerts Module
Purpose: Test Slack, email, and trading-specific alerts
"""

import pytest
import os
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from app.monitoring.alerts import (
    AlertLevel,
    TradingAlert,
    send_slack_alert,
    send_email_alert,
    send_trading_alert,
    send_daily_loss_alert,
    send_position_size_alert,
    send_trade_error_alert,
    send_api_connection_alert,
    send_emergency_stop_alert,
    send_performance_alert,
    send_balance_alert
)


class TestAlertLevel:
    """Test AlertLevel enum"""

    def test_alert_levels_exist(self):
        """Test that all alert levels are defined"""
        assert AlertLevel.INFO == "info"
        assert AlertLevel.WARNING == "warning"
        assert AlertLevel.ERROR == "error"
        assert AlertLevel.CRITICAL == "critical"


class TestTradingAlertConstants:
    """Test TradingAlert constant values"""

    def test_alert_types_exist(self):
        """Test that all alert type constants are defined"""
        assert TradingAlert.DAILY_LOSS_LIMIT == "daily_loss_limit_reached"
        assert TradingAlert.POSITION_SIZE_LIMIT == "position_size_limit_exceeded"
        assert TradingAlert.TRADE_ERROR == "trade_execution_error"
        assert TradingAlert.API_CONNECTION_FAILED == "api_connection_failed"
        assert TradingAlert.DATABASE_ERROR == "database_error"
        assert TradingAlert.EMERGENCY_STOP == "emergency_stop_triggered"
        assert TradingAlert.UNUSUAL_ACTIVITY == "unusual_trading_activity"
        assert TradingAlert.BALANCE_LOW == "account_balance_low"
        assert TradingAlert.WINNING_STREAK == "winning_streak_detected"
        assert TradingAlert.LOSING_STREAK == "losing_streak_detected"


class TestSlackAlerts:
    """Test Slack alerting functionality"""

    @pytest.mark.asyncio
    async def test_send_slack_alert_no_webhook(self, monkeypatch):
        """Test Slack alert when webhook URL is not configured"""
        monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)

        result = await send_slack_alert("Test message")

        assert result is False

    @pytest.mark.asyncio
    async def test_send_slack_alert_success(self, monkeypatch):
        """Test successful Slack alert"""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

        # Mock httpx client
        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("app.monitoring.alerts.httpx.AsyncClient", return_value=mock_client):
            result = await send_slack_alert(
                message="Test alert",
                level=AlertLevel.WARNING,
                title="Test Title"
            )

        assert result is True
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_slack_alert_with_fields(self, monkeypatch):
        """Test Slack alert with additional fields"""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("app.monitoring.alerts.httpx.AsyncClient", return_value=mock_client):
            result = await send_slack_alert(
                message="Test alert",
                level=AlertLevel.ERROR,
                fields={"Symbol": "BTCUSDT", "Error": "Connection failed"}
            )

        assert result is True
        # Verify fields were included in payload
        call_args = mock_client.post.call_args
        payload = call_args.kwargs["json"]
        assert "attachments" in payload
        assert "fields" in payload["attachments"][0]

    @pytest.mark.asyncio
    async def test_send_slack_alert_http_error(self, monkeypatch):
        """Test Slack alert when HTTP request fails"""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

        # Mock the async context manager properly
        mock_post = AsyncMock(side_effect=Exception("Connection timeout"))
        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.monitoring.alerts.httpx.AsyncClient", return_value=mock_client):
            result = await send_slack_alert("Test message")

        assert result is False

    @pytest.mark.asyncio
    async def test_send_slack_alert_color_mapping(self, monkeypatch):
        """Test that correct colors are used for different alert levels"""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        color_tests = [
            (AlertLevel.INFO, "#36a64f"),
            (AlertLevel.WARNING, "#ff9900"),
            (AlertLevel.ERROR, "#ff0000"),
            (AlertLevel.CRITICAL, "#8b0000")
        ]

        for level, expected_color in color_tests:
            with patch("app.monitoring.alerts.httpx.AsyncClient", return_value=mock_client):
                await send_slack_alert("Test", level=level)

                call_args = mock_client.post.call_args
                payload = call_args.kwargs["json"]
                assert payload["attachments"][0]["color"] == expected_color


class TestEmailAlerts:
    """Test email alerting functionality"""

    def test_send_email_alert_disabled(self, monkeypatch):
        """Test email alert when email is disabled"""
        monkeypatch.setenv("EMAIL_ALERT_ENABLED", "false")

        result = send_email_alert("Test Subject", "Test Message")

        assert result is False

    def test_send_email_alert_incomplete_config(self, monkeypatch):
        """Test email alert with incomplete configuration"""
        monkeypatch.setenv("EMAIL_ALERT_ENABLED", "true")
        monkeypatch.setenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
        # Missing other required fields
        monkeypatch.delenv("EMAIL_FROM", raising=False)

        result = send_email_alert("Test Subject", "Test Message")

        assert result is False

    def test_send_email_alert_success(self, monkeypatch):
        """Test successful email alert"""
        monkeypatch.setenv("EMAIL_ALERT_ENABLED", "true")
        monkeypatch.setenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
        monkeypatch.setenv("EMAIL_SMTP_PORT", "587")
        monkeypatch.setenv("EMAIL_FROM", "bot@example.com")
        monkeypatch.setenv("EMAIL_TO", "admin@example.com")
        monkeypatch.setenv("EMAIL_PASSWORD", "password123")

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = Mock(return_value=mock_smtp)
        mock_smtp.__exit__ = Mock()
        mock_smtp.starttls = Mock()
        mock_smtp.login = Mock()
        mock_smtp.send_message = Mock()

        with patch("app.monitoring.alerts.smtplib.SMTP", return_value=mock_smtp):
            result = send_email_alert(
                subject="Test Alert",
                message="This is a test",
                level=AlertLevel.WARNING
            )

        assert result is True
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once()
        mock_smtp.send_message.assert_called_once()

    def test_send_email_alert_with_html(self, monkeypatch):
        """Test email alert with HTML content"""
        monkeypatch.setenv("EMAIL_ALERT_ENABLED", "true")
        monkeypatch.setenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
        monkeypatch.setenv("EMAIL_SMTP_PORT", "587")
        monkeypatch.setenv("EMAIL_FROM", "bot@example.com")
        monkeypatch.setenv("EMAIL_TO", "admin@example.com")
        monkeypatch.setenv("EMAIL_PASSWORD", "password123")

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = Mock(return_value=mock_smtp)
        mock_smtp.__exit__ = Mock()
        mock_smtp.starttls = Mock()
        mock_smtp.login = Mock()
        mock_smtp.send_message = Mock()

        with patch("app.monitoring.alerts.smtplib.SMTP", return_value=mock_smtp):
            result = send_email_alert(
                subject="Test Alert",
                message="Plain text",
                html_message="<h1>HTML content</h1>"
            )

        assert result is True

    def test_send_email_alert_smtp_error(self, monkeypatch):
        """Test email alert when SMTP fails"""
        monkeypatch.setenv("EMAIL_ALERT_ENABLED", "true")
        monkeypatch.setenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
        monkeypatch.setenv("EMAIL_SMTP_PORT", "587")
        monkeypatch.setenv("EMAIL_FROM", "bot@example.com")
        monkeypatch.setenv("EMAIL_TO", "admin@example.com")
        monkeypatch.setenv("EMAIL_PASSWORD", "password123")

        with patch("app.monitoring.alerts.smtplib.SMTP", side_effect=Exception("SMTP error")):
            result = send_email_alert("Subject", "Message")

        assert result is False


class TestTradingAlerts:
    """Test trading-specific alert functions"""

    @pytest.mark.asyncio
    async def test_send_daily_loss_alert(self, monkeypatch):
        """Test daily loss limit alert"""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

        with patch("app.monitoring.alerts.send_slack_alert", new_callable=AsyncMock) as mock_slack:
            mock_slack.return_value = True

            await send_daily_loss_alert(
                current_loss=500.0,
                max_loss=1000.0,
                percentage=5.0
            )

            mock_slack.assert_called_once()
            call_args = mock_slack.call_args
            assert "daily loss limit" in call_args.kwargs["message"].lower()
            assert call_args.kwargs["level"] == AlertLevel.CRITICAL
            assert call_args.kwargs["fields"] is not None
            assert "Current Loss" in call_args.kwargs["fields"]

    @pytest.mark.asyncio
    async def test_send_position_size_alert(self, monkeypatch):
        """Test position size limit alert"""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

        with patch("app.monitoring.alerts.send_slack_alert", new_callable=AsyncMock) as mock_slack:
            mock_slack.return_value = True

            await send_position_size_alert(
                symbol="BTCUSDT",
                position_size=10000.0,
                max_size=5000.0
            )

            mock_slack.assert_called_once()
            call_args = mock_slack.call_args
            assert "BTCUSDT" in call_args.kwargs["message"]
            assert call_args.kwargs["level"] == AlertLevel.WARNING

    @pytest.mark.asyncio
    async def test_send_trade_error_alert(self, monkeypatch):
        """Test trade error alert"""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

        with patch("app.monitoring.alerts.send_slack_alert", new_callable=AsyncMock) as mock_slack:
            mock_slack.return_value = True

            await send_trade_error_alert(
                symbol="ETHUSDT",
                error="Insufficient funds",
                order_details={"side": "BUY", "quantity": 0.5}
            )

            mock_slack.assert_called_once()
            call_args = mock_slack.call_args
            assert call_args.kwargs["level"] == AlertLevel.ERROR
            assert call_args.kwargs["fields"] is not None
            assert "Symbol" in call_args.kwargs["fields"]

    @pytest.mark.asyncio
    async def test_send_api_connection_alert(self, monkeypatch):
        """Test API connection failure alert"""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

        with patch("app.monitoring.alerts.send_slack_alert", new_callable=AsyncMock) as mock_slack:
            mock_slack.return_value = True

            await send_api_connection_alert(
                service="Bybit",
                error="Connection timeout"
            )

            mock_slack.assert_called_once()
            call_args = mock_slack.call_args
            assert "Bybit" in call_args.kwargs["message"]
            assert call_args.kwargs["level"] == AlertLevel.ERROR

    @pytest.mark.asyncio
    async def test_send_emergency_stop_alert(self, monkeypatch):
        """Test emergency stop alert"""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

        with patch("app.monitoring.alerts.send_slack_alert", new_callable=AsyncMock) as mock_slack:
            mock_slack.return_value = True

            await send_emergency_stop_alert(
                reason="Multiple consecutive losses"
            )

            mock_slack.assert_called_once()
            call_args = mock_slack.call_args
            assert "EMERGENCY STOP" in call_args.kwargs["message"]
            assert call_args.kwargs["level"] == AlertLevel.CRITICAL

    @pytest.mark.asyncio
    async def test_send_performance_alert_winning_streak(self, monkeypatch):
        """Test performance alert for winning streak"""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

        with patch("app.monitoring.alerts.send_slack_alert", new_callable=AsyncMock) as mock_slack:
            mock_slack.return_value = True

            await send_performance_alert(
                alert_type=TradingAlert.WINNING_STREAK,
                streak_count=5,
                total_pnl=1500.0
            )

            mock_slack.assert_called_once()
            call_args = mock_slack.call_args
            assert call_args.kwargs["level"] == AlertLevel.INFO

    @pytest.mark.asyncio
    async def test_send_performance_alert_losing_streak(self, monkeypatch):
        """Test performance alert for losing streak"""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

        with patch("app.monitoring.alerts.send_slack_alert", new_callable=AsyncMock) as mock_slack:
            mock_slack.return_value = True

            await send_performance_alert(
                alert_type=TradingAlert.LOSING_STREAK,
                streak_count=3,
                total_pnl=-500.0
            )

            mock_slack.assert_called_once()
            call_args = mock_slack.call_args
            assert call_args.kwargs["level"] == AlertLevel.WARNING

    @pytest.mark.asyncio
    async def test_send_balance_alert(self, monkeypatch):
        """Test low balance alert"""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

        with patch("app.monitoring.alerts.send_slack_alert", new_callable=AsyncMock) as mock_slack:
            mock_slack.return_value = True

            await send_balance_alert(
                current_balance=500.0,
                threshold=1000.0
            )

            mock_slack.assert_called_once()
            call_args = mock_slack.call_args
            assert "balance below threshold" in call_args.kwargs["message"].lower()
            assert call_args.kwargs["level"] == AlertLevel.WARNING


class TestSendTradingAlert:
    """Test generic send_trading_alert function"""

    @pytest.mark.asyncio
    async def test_send_trading_alert_slack_only(self, monkeypatch):
        """Test trading alert sends to Slack for INFO level"""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

        with patch("app.monitoring.alerts.send_slack_alert", new_callable=AsyncMock) as mock_slack, \
             patch("app.monitoring.alerts.send_email_alert") as mock_email:

            mock_slack.return_value = True

            await send_trading_alert(
                alert_type="test_alert",
                message="Test message",
                level=AlertLevel.INFO
            )

            mock_slack.assert_called_once()
            mock_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_trading_alert_with_email(self, monkeypatch):
        """Test trading alert sends to both Slack and email for ERROR level"""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
        monkeypatch.setenv("EMAIL_ALERT_ENABLED", "true")

        with patch("app.monitoring.alerts.send_slack_alert", new_callable=AsyncMock) as mock_slack, \
             patch("app.monitoring.alerts.send_email_alert") as mock_email:

            mock_slack.return_value = True
            mock_email.return_value = True

            await send_trading_alert(
                alert_type="critical_alert",
                message="Critical error",
                details={"Error": "Database down"},
                level=AlertLevel.ERROR
            )

            mock_slack.assert_called_once()
            mock_email.assert_called_once()

            # Verify email was called with HTML message
            email_call_args = mock_email.call_args
            assert email_call_args.kwargs["html_message"] is not None
            assert "Critical error" in email_call_args.kwargs["html_message"]

    @pytest.mark.asyncio
    async def test_send_trading_alert_critical_with_details(self, monkeypatch):
        """Test trading alert sends email for CRITICAL level with details"""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
        monkeypatch.setenv("EMAIL_ALERT_ENABLED", "true")

        with patch("app.monitoring.alerts.send_slack_alert", new_callable=AsyncMock) as mock_slack, \
             patch("app.monitoring.alerts.send_email_alert") as mock_email:

            mock_slack.return_value = True
            mock_email.return_value = True

            await send_trading_alert(
                alert_type="emergency",
                message="System failure",
                details={"Reason": "Out of memory", "Action": "Restart required"},
                level=AlertLevel.CRITICAL
            )

            mock_slack.assert_called_once()
            mock_email.assert_called_once()

            # Verify details are in HTML
            email_call_args = mock_email.call_args
            html_message = email_call_args.kwargs["html_message"]
            assert "Out of memory" in html_message
            assert "Restart required" in html_message
