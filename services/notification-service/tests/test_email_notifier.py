"""
Unit Tests for Email Notifier Module
Tests all email notification functionality
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


class TestEmailNotifierInitialization:
    """Test EmailNotifier initialization"""

    def test_init_with_email_enabled(self):
        """Test initialization when email is enabled"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.smtp_host = "smtp.gmail.com"
            mock_config.smtp_port = 587
            mock_config.smtp_username = "test@example.com"
            mock_config.smtp_password = "password123"
            mock_config.email_from = "trading@bot.com"
            mock_config.email_to = "user1@test.com,user2@test.com"

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()

            assert notifier.enabled is True
            assert notifier.smtp_host == "smtp.gmail.com"
            assert notifier.smtp_port == 587
            assert len(notifier.to_emails) == 2

    def test_init_with_email_disabled(self):
        """Test initialization when email is disabled"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = False
            mock_config.email_to = ""

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()

            assert notifier.enabled is False

    def test_init_parses_multiple_recipients(self):
        """Test initialization correctly parses comma-separated recipients"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.email_to = "user1@test.com, user2@test.com ,  user3@test.com"
            mock_config.smtp_host = "smtp.test.com"
            mock_config.smtp_port = 587
            mock_config.smtp_username = "test"
            mock_config.smtp_password = "pass"
            mock_config.email_from = "bot@test.com"

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()

            assert len(notifier.to_emails) == 3
            assert "user1@test.com" in notifier.to_emails
            assert "user2@test.com" in notifier.to_emails
            assert "user3@test.com" in notifier.to_emails


class TestSendEmail:
    """Test send_email method"""

    @patch('app.email_notifier.smtplib.SMTP')
    def test_send_email_success(self, mock_smtp):
        """Test successful email sending"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.smtp_host = "smtp.test.com"
            mock_config.smtp_port = 587
            mock_config.smtp_username = "test@example.com"
            mock_config.smtp_password = "password"
            mock_config.email_from = "bot@test.com"
            mock_config.email_to = "user@test.com"

            # Setup mock SMTP
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()
            result = notifier.send_email("Test Subject", "Test Body")

            assert result is True
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("test@example.com", "password")
            mock_server.send_message.assert_called_once()

    @patch('app.email_notifier.smtplib.SMTP')
    def test_send_email_with_html_body(self, mock_smtp):
        """Test sending email with HTML body"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.smtp_host = "smtp.test.com"
            mock_config.smtp_port = 587
            mock_config.smtp_username = "test@example.com"
            mock_config.smtp_password = "password"
            mock_config.email_from = "bot@test.com"
            mock_config.email_to = "user@test.com"

            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()
            result = notifier.send_email("Test", "<h1>HTML Body</h1>", html=True)

            assert result is True
            mock_server.send_message.assert_called_once()

    def test_send_email_when_disabled(self):
        """Test send_email returns False when disabled"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = False
            mock_config.email_to = "user@test.com"

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()
            result = notifier.send_email("Test", "Body")

            assert result is False

    def test_send_email_with_no_recipients(self):
        """Test send_email returns False when no recipients configured"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.email_to = ""
            mock_config.smtp_host = "smtp.test.com"
            mock_config.smtp_port = 587

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()
            result = notifier.send_email("Test", "Body")

            assert result is False

    @patch('app.email_notifier.smtplib.SMTP')
    def test_send_email_handles_smtp_exception(self, mock_smtp):
        """Test send_email handles SMTP exceptions"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.smtp_host = "smtp.test.com"
            mock_config.smtp_port = 587
            mock_config.smtp_username = "test@example.com"
            mock_config.smtp_password = "password"
            mock_config.email_from = "bot@test.com"
            mock_config.email_to = "user@test.com"

            # Simulate SMTP error
            mock_smtp.return_value.__enter__.side_effect = smtplib.SMTPException("Connection failed")

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()
            result = notifier.send_email("Test", "Body")

            assert result is False

    @patch('app.email_notifier.smtplib.SMTP')
    def test_send_email_handles_authentication_error(self, mock_smtp):
        """Test send_email handles authentication errors"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.smtp_host = "smtp.test.com"
            mock_config.smtp_port = 587
            mock_config.smtp_username = "test@example.com"
            mock_config.smtp_password = "wrong_password"
            mock_config.email_from = "bot@test.com"
            mock_config.email_to = "user@test.com"

            mock_server = MagicMock()
            mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, "Authentication failed")
            mock_smtp.return_value.__enter__.return_value = mock_server

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()
            result = notifier.send_email("Test", "Body")

            assert result is False


class TestNotifyTradeExecuted:
    """Test notify_trade_executed method"""

    @patch('app.email_notifier.EmailNotifier.send_email')
    def test_notify_trade_buy_action(self, mock_send):
        """Test trade notification for BUY action"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.alert_on_trade = True
            mock_config.email_to = "user@test.com"
            mock_send.return_value = True

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()

            trade = {
                'action': 'BUY',
                'symbol': 'BTCUSDT',
                'quantity': 1.0,
                'price': 45000.0,
                'timestamp': '2025-11-23T12:00:00',
                'signal_confidence': 0.85
            }

            result = notifier.notify_trade_executed(trade)

            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert 'BUY' in call_args[0][0]  # Subject contains BUY
            assert 'BTCUSDT' in call_args[0][0]  # Subject contains symbol

    @patch('app.email_notifier.EmailNotifier.send_email')
    def test_notify_trade_sell_action(self, mock_send):
        """Test trade notification for SELL action"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.alert_on_trade = True
            mock_config.email_to = "user@test.com"
            mock_send.return_value = True

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()

            trade = {
                'action': 'SELL',
                'symbol': 'ETHUSDT',
                'quantity': 10.0,
                'price': 3000.0,
                'timestamp': '2025-11-23T12:00:00'
            }

            result = notifier.notify_trade_executed(trade)

            assert result is True
            mock_send.assert_called_once()

    def test_notify_trade_when_alerts_disabled(self):
        """Test notify_trade_executed returns False when alerts disabled"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.alert_on_trade = False
            mock_config.email_to = "user@test.com"

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()

            trade = {
                'action': 'BUY',
                'symbol': 'BTCUSDT',
                'quantity': 1.0,
                'price': 45000.0,
                'timestamp': '2025-11-23T12:00:00'
            }

            result = notifier.notify_trade_executed(trade)

            assert result is False


class TestNotifyProfitLoss:
    """Test notify_profit_loss method"""

    @patch('app.email_notifier.EmailNotifier.send_email')
    def test_notify_profit_above_threshold(self, mock_send):
        """Test profit notification when above threshold"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.alert_on_profit = True
            mock_config.min_profit_alert = 100.0
            mock_config.email_to = "user@test.com"
            mock_send.return_value = True

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()

            trade = {
                'action': 'SELL',
                'symbol': 'BTCUSDT',
                'quantity': 1.0,
                'price': 46000.0,
                'timestamp': '2025-11-23T12:00:00'
            }

            result = notifier.notify_profit_loss(trade, 1000.0)

            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args[0]
            assert 'Profit' in call_args[0] or '📈' in call_args[0]

    @patch('app.email_notifier.EmailNotifier.send_email')
    def test_notify_loss_above_threshold(self, mock_send):
        """Test loss notification when above threshold"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.alert_on_loss = True
            mock_config.min_loss_alert = 100.0
            mock_config.email_to = "user@test.com"
            mock_send.return_value = True

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()

            trade = {
                'action': 'SELL',
                'symbol': 'BTCUSDT',
                'quantity': 1.0,
                'price': 44000.0,
                'timestamp': '2025-11-23T12:00:00'
            }

            result = notifier.notify_profit_loss(trade, -500.0)

            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args[0]
            assert 'Loss' in call_args[0] or '📉' in call_args[0]

    def test_notify_profit_below_threshold(self):
        """Test profit notification skipped when below threshold"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.alert_on_profit = True
            mock_config.min_profit_alert = 1000.0
            mock_config.email_to = "user@test.com"

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()

            trade = {'action': 'SELL', 'symbol': 'BTCUSDT', 'quantity': 0.01, 'price': 45100.0, 'timestamp': '2025-11-23'}
            result = notifier.notify_profit_loss(trade, 50.0)  # Below 1000 threshold

            assert result is False

    def test_notify_loss_below_threshold(self):
        """Test loss notification skipped when below threshold"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.alert_on_loss = True
            mock_config.min_loss_alert = 500.0
            mock_config.email_to = "user@test.com"

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()

            trade = {'action': 'SELL', 'symbol': 'BTCUSDT', 'quantity': 0.01, 'price': 44900.0, 'timestamp': '2025-11-23'}
            result = notifier.notify_profit_loss(trade, -50.0)  # Below 500 threshold

            assert result is False

    def test_notify_profit_when_alerts_disabled(self):
        """Test profit notification skipped when alerts disabled"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.alert_on_profit = False
            mock_config.min_profit_alert = 0.0
            mock_config.email_to = "user@test.com"

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()

            trade = {'action': 'SELL', 'symbol': 'BTCUSDT', 'quantity': 1.0, 'price': 46000.0, 'timestamp': '2025-11-23'}
            result = notifier.notify_profit_loss(trade, 1000.0)

            assert result is False


class TestNotifyDailyLimitReached:
    """Test notify_daily_limit_reached method"""

    @patch('app.email_notifier.EmailNotifier.send_email')
    def test_notify_daily_limit_reached(self, mock_send):
        """Test daily limit notification"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.alert_on_daily_limit = True
            mock_config.email_to = "user@test.com"
            mock_send.return_value = True

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()

            result = notifier.notify_daily_limit_reached(5000.0)

            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args[0]
            assert 'CRITICAL' in call_args[0] or '🚨' in call_args[0]
            assert '5000' in call_args[1] or '5,000' in call_args[1]

    def test_notify_daily_limit_when_disabled(self):
        """Test daily limit notification when alerts disabled"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.alert_on_daily_limit = False
            mock_config.email_to = "user@test.com"

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()

            result = notifier.notify_daily_limit_reached(5000.0)

            assert result is False


class TestNotifyError:
    """Test notify_error method"""

    @patch('app.email_notifier.EmailNotifier.send_email')
    def test_notify_error_without_context(self, mock_send):
        """Test error notification without context"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.alert_on_error = True
            mock_config.email_to = "user@test.com"
            mock_send.return_value = True

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()

            result = notifier.notify_error("Connection timeout")

            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args[0]
            assert 'Error' in call_args[0] or '⚠️' in call_args[0]
            assert 'Connection timeout' in call_args[1]

    @patch('app.email_notifier.EmailNotifier.send_email')
    def test_notify_error_with_context(self, mock_send):
        """Test error notification with additional context"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.alert_on_error = True
            mock_config.email_to = "user@test.com"
            mock_send.return_value = True

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()

            context = {
                'symbol': 'BTCUSDT',
                'error_code': 'INSUFFICIENT_MARGIN',
                'order_id': '123456'
            }

            result = notifier.notify_error("Order failed", context)

            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args[0]
            assert 'Order failed' in call_args[1]
            assert 'BTCUSDT' in call_args[1]
            assert 'INSUFFICIENT_MARGIN' in call_args[1]

    def test_notify_error_when_disabled(self):
        """Test error notification when alerts disabled"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.alert_on_error = False
            mock_config.email_to = "user@test.com"

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()

            result = notifier.notify_error("Test error")

            assert result is False


class TestNotifyStartup:
    """Test notify_startup method"""

    @patch('app.email_notifier.EmailNotifier.send_email')
    def test_notify_startup_paper_trading(self, mock_send):
        """Test startup notification for paper trading mode"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.alert_on_startup = True
            mock_config.email_to = "user@test.com"
            mock_send.return_value = True

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()

            config_summary = {
                'mode': 'PAPER_TRADING',
                'symbols': ['BTCUSDT', 'ETHUSDT'],
                'interval_minutes': 60,
                'capital': 100000.0,
                'max_position_pct': 20.0,
                'daily_loss_limit': 5.0,
                'stop_loss_pct': 2.0
            }

            result = notifier.notify_startup(config_summary)

            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args[0]
            assert 'Started' in call_args[0] or '🚀' in call_args[0]
            assert 'PAPER_TRADING' in call_args[1]
            assert 'BTCUSDT' in call_args[1]

    @patch('app.email_notifier.EmailNotifier.send_email')
    def test_notify_startup_live_trading(self, mock_send):
        """Test startup notification for live trading mode"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.alert_on_startup = True
            mock_config.email_to = "user@test.com"
            mock_send.return_value = True

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()

            config_summary = {
                'mode': 'LIVE_TRADING',
                'symbols': ['BTCUSDT'],
                'interval_minutes': 30,
                'capital': 10000.0,
                'max_position_pct': 10.0,
                'daily_loss_limit': 2.0,
                'stop_loss_pct': 1.5
            }

            result = notifier.notify_startup(config_summary)

            assert result is True
            call_args = mock_send.call_args[0]
            assert 'LIVE_TRADING' in call_args[1]
            assert '10,000' in call_args[1] or '10000' in call_args[1]

    def test_notify_startup_when_disabled(self):
        """Test startup notification when alerts disabled"""
        with patch('app.email_notifier.config') as mock_config:
            mock_config.email_enabled = True
            mock_config.alert_on_startup = False
            mock_config.email_to = "user@test.com"

            from app.email_notifier import EmailNotifier
            notifier = EmailNotifier()

            config_summary = {'mode': 'PAPER_TRADING', 'symbols': ['BTCUSDT']}
            result = notifier.notify_startup(config_summary)

            assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
