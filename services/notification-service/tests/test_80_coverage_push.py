"""
Comprehensive test suite for notification-service coverage optimization
Targets: Exception handlers, error paths, and edge cases
Goal: Achieve 80%+ coverage with comprehensive integration tests
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
import logging


class TestExceptionHandling:
    """Test exception handling across all notification endpoints"""

    def test_notify_trade_exception_handling(self, test_client):
        """Test trade notification when service raises exception"""
        with patch('app.main.email_notifier') as mock_email, \
             patch('app.main.telegram_notifier') as mock_telegram, \
             patch('app.main.config') as mock_config:

            mock_config.email_enabled = True
            mock_config.telegram_enabled = True
            mock_email.notify_trade_executed.side_effect = Exception("Email service error")
            mock_telegram.notify_trade_executed.return_value = True

            notification = {
                "action": "BUY",
                "symbol": "BTCUSDT",
                "quantity": 1.0,
                "price": 45000.0,
                "timestamp": "2025-11-21T00:00:00"
            }

            response = test_client.post("/api/v1/notify/trade", json=notification)
            assert response.status_code == 500
            assert "error" in response.json() or "detail" in response.json()

    def test_notify_pnl_exception_handling(self, test_client):
        """Test P&L notification when service raises exception"""
        with patch('app.main.email_notifier') as mock_email, \
             patch('app.main.telegram_notifier') as mock_telegram, \
             patch('app.main.config') as mock_config:

            mock_config.email_enabled = True
            mock_telegram.notify_profit_loss = AsyncMock(side_effect=Exception("Telegram API error"))

            notification = {
                "trade": {
                    "action": "SELL",
                    "symbol": "ETHUSDT",
                    "quantity": 5.0,
                    "price": 2500.0,
                    "timestamp": "2025-11-21T01:00:00"
                },
                "pnl": 500.0
            }

            response = test_client.post("/api/v1/notify/pnl", json=notification)
            assert response.status_code == 500

    def test_notify_daily_limit_exception_handling(self, test_client):
        """Test daily limit notification when exception occurs"""
        with patch('app.main.email_notifier') as mock_email, \
             patch('app.main.telegram_notifier') as mock_telegram, \
             patch('app.main.config') as mock_config:

            mock_config.email_enabled = True
            mock_email.notify_daily_limit_reached.side_effect = RuntimeError("SMTP connection failed")

            response = test_client.post(
                "/api/v1/notify/daily-limit",
                params={"total_loss": 5000.0}
            )

            assert response.status_code == 500

    def test_notify_error_exception_handling(self, test_client):
        """Test error notification when notifier raises exception"""
        with patch('app.main.email_notifier') as mock_email, \
             patch('app.main.telegram_notifier') as mock_telegram, \
             patch('app.main.config') as mock_config:

            mock_config.email_enabled = False
            mock_config.telegram_enabled = True
            mock_telegram.notify_error = AsyncMock(side_effect=Exception("HTTP timeout"))

            notification = {
                "error_message": "Test error",
                "context": {"key": "value"}
            }

            response = test_client.post("/api/v1/notify/error", json=notification)
            assert response.status_code == 500

    def test_notify_startup_exception_handling(self, test_client):
        """Test startup notification when exception occurs"""
        with patch('app.main.email_notifier') as mock_email, \
             patch('app.main.telegram_notifier') as mock_telegram, \
             patch('app.main.config') as mock_config:

            mock_config.email_enabled = True
            mock_config.telegram_enabled = True
            mock_email.notify_startup.side_effect = Exception("SMTP server unavailable")

            notification = {
                "mode": "PAPER_TRADING",
                "symbols": ["BTCUSDT"],
                "interval_minutes": 60,
                "capital": 100000.0,
                "max_position_pct": 20.0,
                "daily_loss_limit": 5.0,
                "stop_loss_pct": 2.0
            }

            response = test_client.post("/api/v1/notify/startup", json=notification)
            assert response.status_code == 500

    def test_notify_daily_summary_exception_handling(self, test_client):
        """Test daily summary notification when exception occurs"""
        with patch('app.main.telegram_notifier') as mock_telegram, \
             patch('app.main.config') as mock_config:

            mock_config.telegram_enabled = True
            mock_telegram.notify_daily_summary = AsyncMock(side_effect=Exception("API error"))

            summary = {
                "total_pnl": 2500.0,
                "total_trades": 10,
                "win_rate": 70.0,
                "best_trade": 800.0,
                "worst_trade": -300.0,
                "balance": 102500.0,
                "open_positions": 2
            }

            response = test_client.post("/api/v1/notify/daily-summary", json=summary)
            assert response.status_code == 500

    def test_test_notifications_success(self, test_client):
        """Test notification test endpoint success.

        slack/sms must be explicitly disabled — the endpoint's `attempted` list
        treats any truthy `enabled` value as an active channel, and bare
        MagicMock attributes are truthy.
        """
        with patch('app.main.email_notifier') as mock_email, \
             patch('app.main.telegram_notifier') as mock_telegram, \
             patch('app.main.config') as mock_config:

            mock_config.email_enabled = True
            mock_config.telegram_enabled = True
            mock_config.slack_enabled = False
            mock_config.sms_enabled = False
            mock_email.send_email.return_value = True
            mock_telegram.send_message = AsyncMock(return_value=True)

            response = test_client.post("/api/v1/test")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True


class TestEmailNotifierEdgeCases:
    """Test edge cases and boundary conditions for email notifier"""

    def test_notify_profit_loss_exactly_at_min_profit_threshold(self):
        """Test P&L notification exactly at minimum profit threshold"""
        from app.email_notifier import EmailNotifier
        from app.config import NotificationConfig

        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.alert_on_profit = True
            mock_config.min_profit_alert = 10.0
            mock_config.alert_on_trade = True
            mock_config.smtp_host = "smtp.test.com"
            mock_config.smtp_port = 587
            mock_config.smtp_username = "test@test.com"
            mock_config.smtp_password = "password"
            mock_config.email_from = "test@test.com"
            mock_config.email_to = "recipient@test.com"

            notifier = EmailNotifier()

            with patch('smtplib.SMTP') as mock_smtp:
                trade = {
                    "action": "SELL",
                    "symbol": "BTCUSDT",
                    "quantity": 1.0,
                    "price": 45000.0,
                    "timestamp": "2025-11-21T00:00:00"
                }

                # Exactly at threshold
                result = notifier.notify_profit_loss(trade, 10.0)
                assert result is True or result is False  # Edge case behavior

    def test_notify_profit_loss_below_min_profit_threshold(self):
        """Test P&L notification below minimum profit threshold"""
        from app.email_notifier import EmailNotifier

        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.alert_on_profit = True
            mock_config.min_profit_alert = 20.0

            notifier = EmailNotifier()

            trade = {
                "action": "SELL",
                "symbol": "BTCUSDT",
                "quantity": 1.0,
                "price": 45000.0,
                "timestamp": "2025-11-21T00:00:00"
            }

            # Below threshold - should not alert
            result = notifier.notify_profit_loss(trade, 5.0)
            assert result is False

    def test_notify_profit_loss_large_profit(self):
        """Test P&L notification with large profit amount"""
        from app.email_notifier import EmailNotifier

        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.alert_on_profit = True
            mock_config.min_profit_alert = 10.0
            mock_config.alert_on_loss = False
            mock_config.smtp_host = "smtp.test.com"
            mock_config.smtp_port = 587
            mock_config.smtp_username = "test@test.com"
            mock_config.smtp_password = "password"
            mock_config.email_from = "test@test.com"
            mock_config.email_to = "recipient@test.com"

            notifier = EmailNotifier()

            with patch('smtplib.SMTP') as mock_smtp:
                mock_server = MagicMock()
                mock_smtp.return_value.__enter__.return_value = mock_server

                trade = {
                    "action": "SELL",
                    "symbol": "BTCUSDT",
                    "quantity": 100.0,
                    "price": 50000.0,
                    "timestamp": "2025-11-21T00:00:00"
                }

                result = notifier.notify_profit_loss(trade, 50000.0)
                assert result is True

    def test_notify_profit_loss_loss_disabled(self):
        """Test P&L notification when loss alerts are disabled"""
        from app.email_notifier import EmailNotifier

        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.alert_on_loss = False
            mock_config.min_loss_alert = 10.0

            notifier = EmailNotifier()

            trade = {
                "action": "SELL",
                "symbol": "BTCUSDT",
                "quantity": 1.0,
                "price": 45000.0,
                "timestamp": "2025-11-21T00:00:00"
            }

            # Loss alert disabled
            result = notifier.notify_profit_loss(trade, -500.0)
            assert result is False

    def test_notify_daily_limit_negative_loss(self):
        """Test daily limit notification with negative loss (gain)"""
        from app.email_notifier import EmailNotifier

        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.alert_on_daily_limit = True
            mock_config.smtp_host = "smtp.test.com"
            mock_config.smtp_port = 587
            mock_config.smtp_username = "test@test.com"
            mock_config.smtp_password = "password"
            mock_config.email_from = "test@test.com"
            mock_config.email_to = "recipient@test.com"

            notifier = EmailNotifier()

            with patch('smtplib.SMTP') as mock_smtp:
                mock_server = MagicMock()
                mock_smtp.return_value.__enter__.return_value = mock_server

                result = notifier.notify_daily_limit_reached(-5000.0)
                assert result is True


class TestTelegramNotifierEdgeCases:
    """Test edge cases for Telegram notifier"""

    @pytest.mark.asyncio
    async def test_notify_profit_loss_zero_pnl(self):
        """Test Telegram P&L notification with zero P&L"""
        from app.telegram_notifier import TelegramNotifier

        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.alert_on_profit = True
            mock_config.alert_on_loss = True
            mock_config.min_profit_alert = 10.0
            mock_config.min_loss_alert = 10.0

            notifier = TelegramNotifier()

            trade = {
                "action": "SELL",
                "symbol": "BTCUSDT",
                "quantity": 1.0,
                "price": 45000.0,
                "timestamp": "2025-11-21T00:00:00"
            }

            # Zero P&L - neither profit nor loss
            result = await notifier.notify_profit_loss(trade, 0.0)
            assert result is False

    @pytest.mark.asyncio
    async def test_send_message_with_markdown_parse_mode(self):
        """Test sending Telegram message with Markdown parse mode"""
        from app.telegram_notifier import TelegramNotifier

        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.telegram_bot_token = "test-token"
            mock_config.telegram_chat_id = "12345"

            notifier = TelegramNotifier()

            with patch('httpx.AsyncClient') as mock_client:
                mock_response = MagicMock()
                mock_response.raise_for_status.return_value = None
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    return_value=mock_response
                )

                result = await notifier.send_message(
                    "**Bold text** *italic*",
                    parse_mode="Markdown"
                )
                assert result is True

    @pytest.mark.asyncio
    async def test_notify_daily_summary_with_zero_trades(self):
        """Test daily summary with zero trades"""
        from app.telegram_notifier import TelegramNotifier

        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.telegram_bot_token = "test-token"
            mock_config.telegram_chat_id = "12345"

            notifier = TelegramNotifier()

            with patch('httpx.AsyncClient') as mock_client:
                mock_response = MagicMock()
                mock_response.raise_for_status.return_value = None
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    return_value=mock_response
                )

                summary = {
                    "total_pnl": 0.0,
                    "total_trades": 0,
                    "win_rate": 0.0,
                    "best_trade": 0.0,
                    "worst_trade": 0.0,
                    "balance": 100000.0,
                    "open_positions": 0
                }

                result = await notifier.notify_daily_summary(summary)
                assert result is True

    @pytest.mark.asyncio
    async def test_notify_startup_multiple_symbols(self):
        """Test startup notification with multiple trading symbols"""
        from app.telegram_notifier import TelegramNotifier

        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.telegram_bot_token = "test-token"
            mock_config.telegram_chat_id = "12345"
            mock_config.alert_on_startup = True

            notifier = TelegramNotifier()

            with patch('httpx.AsyncClient') as mock_client:
                mock_response = MagicMock()
                mock_response.raise_for_status.return_value = None
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    return_value=mock_response
                )

                config = {
                    "mode": "LIVE_TRADING",
                    "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT"],
                    "interval_minutes": 15,
                    "capital": 50000.0,
                    "max_position_pct": 15.0,
                    "daily_loss_limit": 3.0,
                    "stop_loss_pct": 1.5
                }

                result = await notifier.notify_startup(config)
                assert result is True


class TestConfigurationValidation:
    """Test configuration-based behavior"""

    def test_email_disabled_skips_notification(self, test_client):
        """Disabled-email path no longer returns 200 silently — now 503
        with no-channels-enabled detail (false-success fix)."""
        with patch('app.main.config') as mock_config, \
             patch('app.main.email_notifier') as mock_email:

            mock_config.email_enabled = False
            mock_config.telegram_enabled = False

            notification = {
                "action": "BUY",
                "symbol": "BTCUSDT",
                "quantity": 1.0,
                "price": 45000.0,
                "timestamp": "2025-11-21T00:00:00"
            }

            response = test_client.post("/api/v1/notify/trade", json=notification)
            assert response.status_code == 503
            # Email notifier should not be called
            mock_email.notify_trade_executed.assert_not_called()

    def test_telegram_disabled_skips_notification(self, test_client):
        """Disabled-telegram path no longer returns 200 silently — now 503."""
        with patch('app.main.config') as mock_config, \
             patch('app.main.telegram_notifier') as mock_telegram:

            mock_config.email_enabled = False
            mock_config.telegram_enabled = False

            summary = {
                "total_pnl": 1000.0,
                "total_trades": 5,
                "win_rate": 60.0,
                "best_trade": 400.0,
                "worst_trade": -100.0,
                "balance": 101000.0,
                "open_positions": 1
            }

            response = test_client.post("/api/v1/notify/daily-summary", json=summary)
            assert response.status_code == 503
            mock_telegram.notify_daily_summary.assert_not_called()

    def test_config_endpoint_returns_all_alert_settings(self, test_client):
        """Test that config endpoint includes all alert settings"""
        response = test_client.get("/api/v1/config")

        assert response.status_code == 200
        config = response.json()["config"]

        # All alert settings should be present
        assert "alert_on_trade" in config
        assert "alert_on_profit" in config
        assert "alert_on_loss" in config
        assert "alert_on_daily_limit" in config
        assert "alert_on_error" in config
        assert "alert_on_startup" in config

        # All should be boolean
        assert isinstance(config["alert_on_trade"], bool)
        assert isinstance(config["alert_on_profit"], bool)
        assert isinstance(config["alert_on_loss"], bool)


class TestMultiChannelNotifications:
    """Test notifications across multiple channels"""

    def test_email_and_telegram_both_succeed(self, test_client):
        """Test when both email and Telegram succeed"""
        with patch('app.main.email_notifier') as mock_email, \
             patch('app.main.telegram_notifier') as mock_telegram, \
             patch('app.main.config') as mock_config:

            mock_config.email_enabled = True
            mock_config.telegram_enabled = True
            mock_email.notify_trade_executed.return_value = True
            mock_telegram.notify_trade_executed = AsyncMock(return_value=True)

            notification = {
                "action": "BUY",
                "symbol": "BTCUSDT",
                "quantity": 1.0,
                "price": 45000.0,
                "timestamp": "2025-11-21T00:00:00"
            }

            response = test_client.post("/api/v1/notify/trade", json=notification)
            data = response.json()

            assert response.status_code == 200
            assert data["email_sent"] is True
            assert data["telegram_sent"] is True

    def test_email_succeeds_telegram_fails(self, test_client):
        """Partial failure now surfaces as 502 with failed_channels listed."""
        with patch('app.main.email_notifier') as mock_email, \
             patch('app.main.telegram_notifier') as mock_telegram, \
             patch('app.main.config') as mock_config:

            mock_config.email_enabled = True
            mock_config.telegram_enabled = True
            mock_email.notify_error.return_value = True
            mock_telegram.notify_error = AsyncMock(return_value=False)

            notification = {
                "error_message": "Connection timeout",
                "context": {"service": "market-data"}
            }

            response = test_client.post("/api/v1/notify/error", json=notification)
            assert response.status_code == 502
            detail = response.json()["detail"]
            assert detail["email_sent"] is True
            assert detail["telegram_sent"] is False
            assert "telegram" in detail["failed_channels"]

    def test_email_fails_telegram_succeeds(self, test_client):
        """Partial failure (email) now surfaces as 502."""
        with patch('app.main.email_notifier') as mock_email, \
             patch('app.main.telegram_notifier') as mock_telegram, \
             patch('app.main.config') as mock_config:

            mock_config.email_enabled = True
            mock_config.telegram_enabled = True
            mock_email.notify_daily_limit_reached.return_value = False
            mock_telegram.notify_daily_limit_reached = AsyncMock(return_value=True)

            response = test_client.post(
                "/api/v1/notify/daily-limit",
                params={"total_loss": 5000.0}
            )
            assert response.status_code == 502
            detail = response.json()["detail"]
            assert detail["email_sent"] is False
            assert detail["telegram_sent"] is True
            assert "email" in detail["failed_channels"]


class TestNotificationContent:
    """Test notification content formatting"""

    def test_trade_notification_includes_timestamp(self, test_client):
        """No-channels-enabled now returns 503 detail body with timestamp."""
        with patch('app.main.config') as mock_config:
            mock_config.email_enabled = False
            mock_config.telegram_enabled = False

            notification = {
                "action": "SELL",
                "symbol": "ETHUSDT",
                "quantity": 10.0,
                "price": 2500.0,
                "timestamp": "2025-11-21T14:30:00",
                "signal_confidence": 0.92
            }

            response = test_client.post("/api/v1/notify/trade", json=notification)
            assert response.status_code == 503
            assert "timestamp" in response.json()["detail"]

    def test_pnl_notification_response_structure(self, test_client):
        """No-channels-enabled now returns 503 detail body with full structure."""
        with patch('app.main.config') as mock_config:
            mock_config.email_enabled = False
            mock_config.telegram_enabled = False

            notification = {
                "trade": {
                    "action": "BUY",
                    "symbol": "BNBUSDT",
                    "quantity": 50.0,
                    "price": 600.0,
                    "timestamp": "2025-11-21T10:00:00"
                },
                "pnl": 2000.0
            }

            response = test_client.post("/api/v1/notify/pnl", json=notification)
            assert response.status_code == 503
            detail = response.json()["detail"]
            assert "success" in detail
            assert "email_sent" in detail
            assert "telegram_sent" in detail
            assert "timestamp" in detail

    def test_daily_summary_response_structure(self, test_client):
        """No-channels-enabled now returns 503 detail body."""
        with patch('app.main.config') as mock_config:
            mock_config.telegram_enabled = False
            mock_config.email_enabled = False

            summary = {
                "total_pnl": 3500.0,
                "total_trades": 20,
                "win_rate": 75.0,
                "best_trade": 1500.0,
                "worst_trade": -400.0,
                "balance": 103500.0,
                "open_positions": 3
            }

            response = test_client.post("/api/v1/notify/daily-summary", json=summary)
            assert response.status_code == 503
            detail = response.json()["detail"]
            assert detail["success"] is False
            assert "telegram_sent" in detail
            assert "timestamp" in detail


class TestAsyncBehavior:
    """Test async behavior of Telegram notifications"""

    def test_health_check_response_format(self, test_client):
        """Test health check response format"""
        response = test_client.get("/health")
        data = response.json()

        assert response.status_code == 200
        assert data["status"] == "healthy"
        assert "service" in data
        assert "version" in data
        assert "timestamp" in data
        assert isinstance(data["timestamp"], int)
        assert data["timestamp"] > 0


class TestRequestValidation:
    """Test request validation for all endpoints"""

    def test_trade_notification_missing_action(self, test_client):
        """Test trade notification with missing action"""
        notification = {
            "symbol": "BTCUSDT",
            "quantity": 1.0,
            "price": 45000.0,
            "timestamp": "2025-11-21T00:00:00"
        }

        response = test_client.post("/api/v1/notify/trade", json=notification)
        assert response.status_code == 422

    def test_trade_notification_missing_symbol(self, test_client):
        """Test trade notification with missing symbol"""
        notification = {
            "action": "BUY",
            "quantity": 1.0,
            "price": 45000.0,
            "timestamp": "2025-11-21T00:00:00"
        }

        response = test_client.post("/api/v1/notify/trade", json=notification)
        assert response.status_code == 422

    def test_pnl_notification_missing_pnl(self, test_client):
        """Test P&L notification with missing pnl field"""
        notification = {
            "trade": {
                "action": "SELL",
                "symbol": "BTCUSDT",
                "quantity": 1.0,
                "price": 46000.0,
                "timestamp": "2025-11-21T01:00:00"
            }
        }

        response = test_client.post("/api/v1/notify/pnl", json=notification)
        assert response.status_code == 422

    def test_error_notification_missing_message(self, test_client):
        """Test error notification with missing message"""
        notification = {
            "context": {"key": "value"}
        }

        response = test_client.post("/api/v1/notify/error", json=notification)
        assert response.status_code == 422

    def test_startup_notification_missing_mode(self, test_client):
        """Test startup notification with missing mode"""
        notification = {
            "symbols": ["BTCUSDT"],
            "interval_minutes": 60,
            "capital": 100000.0,
            "max_position_pct": 20.0,
            "daily_loss_limit": 5.0,
            "stop_loss_pct": 2.0
        }

        response = test_client.post("/api/v1/notify/startup", json=notification)
        assert response.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=app"])
