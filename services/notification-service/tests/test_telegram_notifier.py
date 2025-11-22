"""
Unit Tests for Telegram Notifier Module
Tests all Telegram notification functionality
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
import httpx


class TestTelegramNotifierInitialization:
    """Test TelegramNotifier initialization"""

    def test_init_with_telegram_enabled(self):
        """Test initialization when Telegram is enabled"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.telegram_bot_token = "123456:ABC-DEF"
            mock_config.telegram_chat_id = "987654321"

            from app.telegram_notifier import TelegramNotifier
            notifier = TelegramNotifier()

            assert notifier.enabled is True
            assert notifier.bot_token == "123456:ABC-DEF"
            assert notifier.chat_id == "987654321"
            assert "123456:ABC-DEF" in notifier.base_url

    def test_init_with_telegram_disabled(self):
        """Test initialization when Telegram is disabled"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = False
            mock_config.telegram_bot_token = ""
            mock_config.telegram_chat_id = ""

            from app.telegram_notifier import TelegramNotifier
            notifier = TelegramNotifier()

            assert notifier.enabled is False


class TestSendMessage:
    """Test send_message method"""

    @pytest.mark.asyncio
    async def test_send_message_success(self):
        """Test successful message sending"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.telegram_bot_token = "123456:ABC-DEF"
            mock_config.telegram_chat_id = "987654321"

            with patch('app.telegram_notifier.httpx.AsyncClient') as mock_client:
                # Setup mock response
                mock_response = AsyncMock()
                mock_response.raise_for_status = Mock()
                mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

                from app.telegram_notifier import TelegramNotifier
                notifier = TelegramNotifier()
                result = await notifier.send_message("Test message")

                assert result is True

    @pytest.mark.asyncio
    async def test_send_message_with_markdown(self):
        """Test sending message with Markdown formatting"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.telegram_bot_token = "123456:ABC-DEF"
            mock_config.telegram_chat_id = "987654321"

            with patch('app.telegram_notifier.httpx.AsyncClient') as mock_client:
                mock_response = AsyncMock()
                mock_response.raise_for_status = Mock()
                mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

                from app.telegram_notifier import TelegramNotifier
                notifier = TelegramNotifier()
                result = await notifier.send_message("**Bold** text", parse_mode="Markdown")

                assert result is True

    @pytest.mark.asyncio
    async def test_send_message_when_disabled(self):
        """Test send_message returns False when disabled"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = False

            from app.telegram_notifier import TelegramNotifier
            notifier = TelegramNotifier()
            result = await notifier.send_message("Test")

            assert result is False

    @pytest.mark.asyncio
    async def test_send_message_with_empty_token(self):
        """Test send_message returns False when token not configured"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.telegram_bot_token = ""
            mock_config.telegram_chat_id = "123"

            from app.telegram_notifier import TelegramNotifier
            notifier = TelegramNotifier()
            result = await notifier.send_message("Test")

            assert result is False

    @pytest.mark.asyncio
    async def test_send_message_with_empty_chat_id(self):
        """Test send_message returns False when chat ID not configured"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.telegram_bot_token = "123456:ABC"
            mock_config.telegram_chat_id = ""

            from app.telegram_notifier import TelegramNotifier
            notifier = TelegramNotifier()
            result = await notifier.send_message("Test")

            assert result is False

    @pytest.mark.asyncio
    async def test_send_message_handles_http_error(self):
        """Test send_message handles HTTP errors"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.telegram_bot_token = "123456:ABC-DEF"
            mock_config.telegram_chat_id = "987654321"

            with patch('app.telegram_notifier.httpx.AsyncClient') as mock_client:
                mock_response = Mock()
                # Make raise_for_status raise an exception
                mock_response.raise_for_status = Mock(side_effect=httpx.HTTPStatusError(
                    "Bad request", request=Mock(), response=Mock()
                ))
                mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

                from app.telegram_notifier import TelegramNotifier
                notifier = TelegramNotifier()
                result = await notifier.send_message("Test")

                assert result is False

    @pytest.mark.asyncio
    async def test_send_message_handles_network_error(self):
        """Test send_message handles network errors"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.telegram_bot_token = "123456:ABC-DEF"
            mock_config.telegram_chat_id = "987654321"

            with patch('app.telegram_notifier.httpx.AsyncClient') as mock_client:
                mock_client.return_value.__aenter__.return_value.post.side_effect = httpx.RequestError(
                    "Network error"
                )

                from app.telegram_notifier import TelegramNotifier
                notifier = TelegramNotifier()
                result = await notifier.send_message("Test")

                assert result is False

    @pytest.mark.asyncio
    async def test_send_message_handles_timeout(self):
        """Test send_message handles timeout errors"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.telegram_bot_token = "123456:ABC-DEF"
            mock_config.telegram_chat_id = "987654321"

            with patch('app.telegram_notifier.httpx.AsyncClient') as mock_client:
                mock_client.return_value.__aenter__.return_value.post.side_effect = httpx.TimeoutException(
                    "Request timeout"
                )

                from app.telegram_notifier import TelegramNotifier
                notifier = TelegramNotifier()
                result = await notifier.send_message("Test")

                assert result is False


class TestNotifyTradeExecuted:
    """Test notify_trade_executed method"""

    @pytest.mark.asyncio
    async def test_notify_trade_buy_action(self):
        """Test trade notification for BUY action"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.alert_on_trade = True
            mock_config.telegram_bot_token = "123456:ABC"
            mock_config.telegram_chat_id = "123"

            with patch('app.telegram_notifier.TelegramNotifier.send_message', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = True

                from app.telegram_notifier import TelegramNotifier
                notifier = TelegramNotifier()

                trade = {
                    'action': 'BUY',
                    'symbol': 'BTCUSDT',
                    'quantity': 1.0,
                    'price': 45000.0,
                    'timestamp': '2025-11-23T12:00:00',
                    'signal_confidence': 0.85
                }

                result = await notifier.notify_trade_executed(trade)

                assert result is True
                mock_send.assert_called_once()
                call_args = mock_send.call_args[0][0]
                assert 'BUY' in call_args
                assert 'BTCUSDT' in call_args
                assert '🟢' in call_args or 'Buy' in call_args

    @pytest.mark.asyncio
    async def test_notify_trade_sell_action(self):
        """Test trade notification for SELL action"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.alert_on_trade = True
            mock_config.telegram_bot_token = "123456:ABC"
            mock_config.telegram_chat_id = "123"

            with patch('app.telegram_notifier.TelegramNotifier.send_message', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = True

                from app.telegram_notifier import TelegramNotifier
                notifier = TelegramNotifier()

                trade = {
                    'action': 'SELL',
                    'symbol': 'ETHUSDT',
                    'quantity': 10.0,
                    'price': 3000.0,
                    'timestamp': '2025-11-23T12:00:00'
                }

                result = await notifier.notify_trade_executed(trade)

                assert result is True
                mock_send.assert_called_once()
                call_args = mock_send.call_args[0][0]
                assert 'SELL' in call_args
                assert 'ETHUSDT' in call_args
                assert '🔴' in call_args or 'Sell' in call_args

    @pytest.mark.asyncio
    async def test_notify_trade_when_alerts_disabled(self):
        """Test trade notification when alerts disabled"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.alert_on_trade = False

            from app.telegram_notifier import TelegramNotifier
            notifier = TelegramNotifier()

            trade = {
                'action': 'BUY',
                'symbol': 'BTCUSDT',
                'quantity': 1.0,
                'price': 45000.0,
                'timestamp': '2025-11-23T12:00:00'
            }

            result = await notifier.notify_trade_executed(trade)

            assert result is False


class TestNotifyProfitLoss:
    """Test notify_profit_loss method"""

    @pytest.mark.asyncio
    async def test_notify_profit_above_threshold(self):
        """Test profit notification when above threshold"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.alert_on_profit = True
            mock_config.min_profit_alert = 100.0

            with patch('app.telegram_notifier.TelegramNotifier.send_message', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = True

                from app.telegram_notifier import TelegramNotifier
                notifier = TelegramNotifier()

                trade = {
                    'action': 'SELL',
                    'symbol': 'BTCUSDT',
                    'quantity': 1.0,
                    'price': 46000.0,
                    'timestamp': '2025-11-23T12:00:00'
                }

                result = await notifier.notify_profit_loss(trade, 1000.0)

                assert result is True
                mock_send.assert_called_once()
                call_args = mock_send.call_args[0][0]
                assert 'PROFIT' in call_args or '📈' in call_args
                assert '1000' in call_args or '1,000' in call_args

    @pytest.mark.asyncio
    async def test_notify_loss_above_threshold(self):
        """Test loss notification when above threshold"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.alert_on_loss = True
            mock_config.min_loss_alert = 100.0

            with patch('app.telegram_notifier.TelegramNotifier.send_message', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = True

                from app.telegram_notifier import TelegramNotifier
                notifier = TelegramNotifier()

                trade = {
                    'action': 'SELL',
                    'symbol': 'BTCUSDT',
                    'quantity': 1.0,
                    'price': 44000.0,
                    'timestamp': '2025-11-23T12:00:00'
                }

                result = await notifier.notify_profit_loss(trade, -500.0)

                assert result is True
                mock_send.assert_called_once()
                call_args = mock_send.call_args[0][0]
                assert 'LOSS' in call_args or '📉' in call_args

    @pytest.mark.asyncio
    async def test_notify_profit_below_threshold(self):
        """Test profit notification skipped when below threshold"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.alert_on_profit = True
            mock_config.min_profit_alert = 1000.0

            from app.telegram_notifier import TelegramNotifier
            notifier = TelegramNotifier()

            trade = {'action': 'SELL', 'symbol': 'BTCUSDT', 'quantity': 0.01, 'price': 45100.0, 'timestamp': '2025-11-23'}
            result = await notifier.notify_profit_loss(trade, 50.0)

            assert result is False

    @pytest.mark.asyncio
    async def test_notify_loss_below_threshold(self):
        """Test loss notification skipped when below threshold"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.alert_on_loss = True
            mock_config.min_loss_alert = 500.0

            from app.telegram_notifier import TelegramNotifier
            notifier = TelegramNotifier()

            trade = {'action': 'SELL', 'symbol': 'BTCUSDT', 'quantity': 0.01, 'price': 44900.0, 'timestamp': '2025-11-23'}
            result = await notifier.notify_profit_loss(trade, -50.0)

            assert result is False

    @pytest.mark.asyncio
    async def test_notify_profit_when_alerts_disabled(self):
        """Test profit notification skipped when alerts disabled"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.alert_on_profit = False
            mock_config.min_profit_alert = 0.0

            from app.telegram_notifier import TelegramNotifier
            notifier = TelegramNotifier()

            trade = {'action': 'SELL', 'symbol': 'BTCUSDT', 'quantity': 1.0, 'price': 46000.0, 'timestamp': '2025-11-23'}
            result = await notifier.notify_profit_loss(trade, 1000.0)

            assert result is False

    @pytest.mark.asyncio
    async def test_notify_loss_when_alerts_disabled(self):
        """Test loss notification skipped when alerts disabled"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.alert_on_loss = False
            mock_config.min_loss_alert = 0.0

            from app.telegram_notifier import TelegramNotifier
            notifier = TelegramNotifier()

            trade = {'action': 'SELL', 'symbol': 'BTCUSDT', 'quantity': 1.0, 'price': 44000.0, 'timestamp': '2025-11-23'}
            result = await notifier.notify_profit_loss(trade, -1000.0)

            assert result is False


class TestNotifyDailyLimitReached:
    """Test notify_daily_limit_reached method"""

    @pytest.mark.asyncio
    async def test_notify_daily_limit_reached(self):
        """Test daily limit notification"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.alert_on_daily_limit = True

            with patch('app.telegram_notifier.TelegramNotifier.send_message', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = True

                from app.telegram_notifier import TelegramNotifier
                notifier = TelegramNotifier()

                result = await notifier.notify_daily_limit_reached(5000.0)

                assert result is True
                mock_send.assert_called_once()
                call_args = mock_send.call_args[0][0]
                assert 'CRITICAL' in call_args or '🚨' in call_args
                assert '5000' in call_args or '5,000' in call_args

    @pytest.mark.asyncio
    async def test_notify_daily_limit_when_disabled(self):
        """Test daily limit notification when alerts disabled"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.alert_on_daily_limit = False

            from app.telegram_notifier import TelegramNotifier
            notifier = TelegramNotifier()

            result = await notifier.notify_daily_limit_reached(5000.0)

            assert result is False


class TestNotifyError:
    """Test notify_error method"""

    @pytest.mark.asyncio
    async def test_notify_error_without_context(self):
        """Test error notification without context"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.alert_on_error = True

            with patch('app.telegram_notifier.TelegramNotifier.send_message', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = True

                from app.telegram_notifier import TelegramNotifier
                notifier = TelegramNotifier()

                result = await notifier.notify_error("Connection timeout")

                assert result is True
                mock_send.assert_called_once()
                call_args = mock_send.call_args[0][0]
                assert 'Error' in call_args or '⚠️' in call_args
                assert 'Connection timeout' in call_args

    @pytest.mark.asyncio
    async def test_notify_error_with_context(self):
        """Test error notification with additional context"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.alert_on_error = True

            with patch('app.telegram_notifier.TelegramNotifier.send_message', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = True

                from app.telegram_notifier import TelegramNotifier
                notifier = TelegramNotifier()

                context = {
                    'symbol': 'BTCUSDT',
                    'error_code': 'INSUFFICIENT_MARGIN',
                    'order_id': '123456'
                }

                result = await notifier.notify_error("Order failed", context)

                assert result is True
                mock_send.assert_called_once()
                call_args = mock_send.call_args[0][0]
                assert 'Order failed' in call_args
                assert 'BTCUSDT' in call_args
                assert 'INSUFFICIENT_MARGIN' in call_args
                assert '123456' in call_args

    @pytest.mark.asyncio
    async def test_notify_error_when_disabled(self):
        """Test error notification when alerts disabled"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.alert_on_error = False

            from app.telegram_notifier import TelegramNotifier
            notifier = TelegramNotifier()

            result = await notifier.notify_error("Test error")

            assert result is False


class TestNotifyStartup:
    """Test notify_startup method"""

    @pytest.mark.asyncio
    async def test_notify_startup_paper_trading(self):
        """Test startup notification for paper trading mode"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.alert_on_startup = True

            with patch('app.telegram_notifier.TelegramNotifier.send_message', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = True

                from app.telegram_notifier import TelegramNotifier
                notifier = TelegramNotifier()

                config_summary = {
                    'mode': 'PAPER_TRADING',
                    'symbols': ['BTCUSDT', 'ETHUSDT'],
                    'interval_minutes': 60,
                    'capital': 100000.0,
                    'max_position_pct': 20.0,
                    'daily_loss_limit': 5.0,
                    'stop_loss_pct': 2.0
                }

                result = await notifier.notify_startup(config_summary)

                assert result is True
                mock_send.assert_called_once()
                call_args = mock_send.call_args[0][0]
                assert 'Started' in call_args or '🚀' in call_args
                assert 'PAPER_TRADING' in call_args
                assert 'BTCUSDT' in call_args

    @pytest.mark.asyncio
    async def test_notify_startup_live_trading(self):
        """Test startup notification for live trading mode"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.alert_on_startup = True

            with patch('app.telegram_notifier.TelegramNotifier.send_message', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = True

                from app.telegram_notifier import TelegramNotifier
                notifier = TelegramNotifier()

                config_summary = {
                    'mode': 'LIVE_TRADING',
                    'symbols': ['BTCUSDT'],
                    'interval_minutes': 30,
                    'capital': 10000.0,
                    'max_position_pct': 10.0,
                    'daily_loss_limit': 2.0,
                    'stop_loss_pct': 1.5
                }

                result = await notifier.notify_startup(config_summary)

                assert result is True
                call_args = mock_send.call_args[0][0]
                assert 'LIVE_TRADING' in call_args
                assert '10,000' in call_args or '10000' in call_args

    @pytest.mark.asyncio
    async def test_notify_startup_when_disabled(self):
        """Test startup notification when alerts disabled"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True
            mock_config.alert_on_startup = False

            from app.telegram_notifier import TelegramNotifier
            notifier = TelegramNotifier()

            config_summary = {'mode': 'PAPER_TRADING', 'symbols': ['BTCUSDT']}
            result = await notifier.notify_startup(config_summary)

            assert result is False


class TestNotifyDailySummary:
    """Test notify_daily_summary method"""

    @pytest.mark.asyncio
    async def test_notify_daily_summary_profitable(self):
        """Test daily summary notification for profitable day"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True

            with patch('app.telegram_notifier.TelegramNotifier.send_message', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = True

                from app.telegram_notifier import TelegramNotifier
                notifier = TelegramNotifier()

                summary = {
                    'total_pnl': 2500.0,
                    'total_trades': 10,
                    'win_rate': 0.70,
                    'best_trade': 800.0,
                    'worst_trade': -300.0,
                    'balance': 102500.0,
                    'open_positions': 2
                }

                result = await notifier.notify_daily_summary(summary)

                assert result is True
                mock_send.assert_called_once()
                call_args = mock_send.call_args[0][0]
                assert 'Summary' in call_args or '📈' in call_args
                assert '2500' in call_args or '2,500' in call_args

    @pytest.mark.asyncio
    async def test_notify_daily_summary_losing(self):
        """Test daily summary notification for losing day"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True

            with patch('app.telegram_notifier.TelegramNotifier.send_message', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = True

                from app.telegram_notifier import TelegramNotifier
                notifier = TelegramNotifier()

                summary = {
                    'total_pnl': -1500.0,
                    'total_trades': 8,
                    'win_rate': 0.25,
                    'best_trade': 200.0,
                    'worst_trade': -600.0,
                    'balance': 98500.0,
                    'open_positions': 0
                }

                result = await notifier.notify_daily_summary(summary)

                assert result is True
                mock_send.assert_called_once()
                call_args = mock_send.call_args[0][0]
                assert '📉' in call_args or 'Summary' in call_args
                assert '1500' in call_args or '1,500' in call_args

    @pytest.mark.asyncio
    async def test_notify_daily_summary_zero_pnl(self):
        """Test daily summary notification for breakeven day"""
        with patch('app.telegram_notifier.config') as mock_config:
            mock_config.telegram_enabled = True

            with patch('app.telegram_notifier.TelegramNotifier.send_message', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = True

                from app.telegram_notifier import TelegramNotifier
                notifier = TelegramNotifier()

                summary = {
                    'total_pnl': 0.0,
                    'total_trades': 5,
                    'win_rate': 0.50,
                    'best_trade': 100.0,
                    'worst_trade': -100.0,
                    'balance': 100000.0,
                    'open_positions': 1
                }

                result = await notifier.notify_daily_summary(summary)

                assert result is True
                mock_send.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
