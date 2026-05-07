"""
Telegram notification handler
Sends trading alerts via Telegram bot
"""

import httpx
import logging
from datetime import datetime
from typing import Dict, Optional
from .config import config

# Configure logging
logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Handles Telegram notifications"""

    def __init__(self):
        """Initialize Telegram notifier"""
        self.enabled = config.telegram_enabled
        self.bot_token = config.telegram_bot_token
        self.chat_id = config.telegram_chat_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

        # DEBUGGER: Log configuration on init
        logger.info(
            f"[DEBUGGER:TelegramNotifier:__init__:20] enabled={self.enabled}, chat_id={self.chat_id}, bot_token_set={bool(self.bot_token)}"
        )

        if self.enabled:
            logger.info(f"Telegram notifications enabled: Chat ID {self.chat_id}")
        else:
            logger.info("Telegram notifications disabled")

    async def send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """
        Send Telegram message

        Args:
            message: Message text
            parse_mode: Formatting mode (HTML or Markdown)

        Returns:
            bool: Success status
        """
        # DEBUGGER: Entry log
        logger.info(
            f"[DEBUGGER:TelegramNotifier:send_message:42] CALLED - enabled={self.enabled}, chat_id={self.chat_id}, msg_len={len(message)}"
        )

        if not self.enabled:
            logger.debug("Telegram notifications disabled, skipping")
            # DEBUGGER: disabled check
            logger.warning(
                "[DEBUGGER:TelegramNotifier:send_message:47] SKIPPED - enabled=False"
            )
            return False

        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram bot token or chat ID not configured")
            # DEBUGGER: token/chat check
            logger.warning(
                f"[DEBUGGER:TelegramNotifier:send_message:52] SKIPPED - token_set={bool(self.bot_token)}, chat_id_set={bool(self.chat_id)}"
            )
            return False

        # CD-01 — Record mode: write JSON line to file, do not POST.
        if config.notification_test_mode == "record":
            import json
            from datetime import datetime, timezone
            from pathlib import Path

            record_path = Path(config.notification_record_path)
            record_path.parent.mkdir(parents=True, exist_ok=True)
            # Loud, grep-able state-transition line per project convention.
            logger.warning("NOTIFICATION_RECORD: path=%s", record_path)
            line = json.dumps(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": parse_mode,
                },
                ensure_ascii=False,
            )
            with record_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            return True

        # Default + live mode: POST to api.telegram.org as today.
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode,
            }

            # DEBUGGER: Before API call
            logger.info(
                f"[DEBUGGER:TelegramNotifier:send_message:63] Calling Telegram API: chat_id={self.chat_id}"
            )

            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=10.0)
                # DEBUGGER: Response status
                logger.info(
                    f"[DEBUGGER:TelegramNotifier:send_message:68] API response status={response.status_code}"
                )
                response.raise_for_status()

            logger.info("Telegram message sent successfully")
            # DEBUGGER: Success
            logger.info(
                f"[DEBUGGER:TelegramNotifier:send_message:73] SUCCESS - message sent to {self.chat_id}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            # DEBUGGER: Error details
            logger.error(
                f"[DEBUGGER:TelegramNotifier:send_message:79] ERROR - type={type(e).__name__}, msg={str(e)}"
            )
            return False

    async def notify_trade_executed(self, trade: Dict) -> bool:
        """
        Notify about trade execution

        Args:
            trade: Trade details

        Returns:
            bool: Success status
        """
        if not config.alert_on_trade:
            return False

        emoji = "🟢" if trade["action"] == "BUY" else "🔴"

        # Calculate risk/reward ratio if SL and TP are available
        entry_price = trade["price"]
        stop_loss = trade.get("stop_loss")
        take_profit = trade.get("take_profit")

        # Calculate distances from entry
        risk_pct = 0.0
        reward_pct = 0.0
        rr_ratio = 0.0

        if stop_loss and take_profit:
            if trade["action"] == "BUY":
                risk_pct = abs((entry_price - stop_loss) / entry_price * 100)
                reward_pct = abs((take_profit - entry_price) / entry_price * 100)
            else:  # SELL
                risk_pct = abs((stop_loss - entry_price) / entry_price * 100)
                reward_pct = abs((entry_price - take_profit) / entry_price * 100)

            if risk_pct > 0:
                rr_ratio = reward_pct / risk_pct

        message = f"""
{emoji} <b>Trade Executed</b>

<b>Action:</b> {trade["action"]}
<b>Symbol:</b> {trade["symbol"]}
<b>Quantity:</b> {trade["quantity"]:.6f}
<b>Entry Price:</b> ${trade["price"]:,.2f}
<b>Total Value:</b> ${trade["quantity"] * trade["price"]:,.2f}

<b>🎯 Risk Management:</b>"""

        if stop_loss:
            message += f"\n• Stop Loss: ${stop_loss:,.2f} (-{risk_pct:.2f}%)"
        if take_profit:
            message += f"\n• Take Profit: ${take_profit:,.2f} (+{reward_pct:.2f}%)"
        if rr_ratio > 0:
            message += f"\n• Risk/Reward: 1:{rr_ratio:.2f}"

        message += f"""

<b>Confidence:</b> {trade.get("signal_confidence", 0):.1%}
<b>Time:</b> {trade["timestamp"][:19]}
"""

        return await self.send_message(message)

    async def notify_profit_loss(self, trade: Dict, pnl: float) -> bool:
        """
        Notify about profit or loss

        Args:
            trade: Trade details
            pnl: Profit/loss amount

        Returns:
            bool: Success status
        """
        # Check thresholds
        if pnl > 0 and pnl < config.min_profit_alert:
            return False
        if pnl < 0 and abs(pnl) < config.min_loss_alert:
            return False

        # Check alert settings
        if pnl > 0 and not config.alert_on_profit:
            return False
        if pnl < 0 and not config.alert_on_loss:
            return False

        if pnl > 0:
            emoji = "📈 💰"
            status = "PROFIT"
        else:
            emoji = "📉 ⚠️"
            status = "LOSS"

        # Get entry and exit prices
        entry_price = trade.get("entry_price", trade.get("price", 0))
        exit_price = trade.get("exit_price", trade.get("price", 0))
        stop_loss = trade.get("stop_loss")
        take_profit = trade.get("take_profit")
        exit_reason = trade.get("exit_reason", "Unknown")

        # Calculate price movement
        if entry_price > 0:
            if trade.get("action") == "BUY" or trade.get("side") == "LONG":
                price_change_pct = (exit_price - entry_price) / entry_price * 100
            else:  # SELL/SHORT
                price_change_pct = (entry_price - exit_price) / entry_price * 100
        else:
            price_change_pct = 0.0

        message = f"""
{emoji} <b>{status}: ${abs(pnl):.2f}</b>

<b>Symbol:</b> {trade["symbol"]}
<b>Action:</b> {trade.get("action", trade.get("side", "N/A"))}
<b>Exit Reason:</b> {exit_reason}
<b>P&L:</b> ${pnl:.2f} ({price_change_pct:+.2f}%)

<b>📊 Trade Details:</b>
• Quantity: {trade["quantity"]:.6f}
• Entry: ${entry_price:,.2f}
• Exit: ${exit_price:,.2f}"""

        if stop_loss:
            message += f"\n• Stop Loss: ${stop_loss:,.2f}"
        if take_profit:
            message += f"\n• Take Profit: ${take_profit:,.2f}"

        message += f"\n• Time: {trade['timestamp'][:19]}"

        return await self.send_message(message)

    async def notify_daily_limit_reached(self, total_loss: float) -> bool:
        """
        Notify when daily loss limit is reached

        Args:
            total_loss: Total loss amount

        Returns:
            bool: Success status
        """
        if not config.alert_on_daily_limit:
            return False

        message = f"""
🚨 <b>CRITICAL ALERT</b> 🚨

<b>Daily Loss Limit Reached</b>

Your trading bot has been automatically stopped.

<b>Daily Loss:</b> ${abs(total_loss):.2f}
<b>Limit:</b> 5% of portfolio

⚠️ <b>Action Required:</b>
1. Review today's trades
2. Analyze the strategy
3. Do NOT restart until you understand what happened

The bot will not trade again today.
"""

        return await self.send_message(message)

    async def notify_error(
        self, error_message: str, context: Optional[Dict] = None
    ) -> bool:
        """
        Notify about system error

        Args:
            error_message: Error description
            context: Additional context

        Returns:
            bool: Success status
        """
        if not config.alert_on_error:
            return False

        message = f"""
⚠️ <b>System Error</b>

<b>Error:</b> {error_message}

<b>Time:</b> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

        if context:
            message += "\n<b>Context:</b>\n"
            for key, value in context.items():
                message += f"• {key}: {value}\n"

        message += "\n⚠️ The bot may have stopped. Check logs immediately."

        return await self.send_message(message)

    async def notify_startup(self, config_summary: Dict) -> bool:
        """
        Notify about bot startup

        Args:
            config_summary: Configuration summary

        Returns:
            bool: Success status
        """
        if not config.alert_on_startup:
            return False

        symbols = ", ".join(config_summary.get("symbols", []))

        message = f"""
🚀 <b>Trading Bot Started</b>

<b>Configuration:</b>
• Mode: {config_summary.get("mode", "Unknown")}
• Symbols: {symbols}
• Interval: {config_summary.get("interval_minutes", "N/A")} min
• Capital: ${config_summary.get("capital", 0):,.2f}

<b>Risk Management:</b>
• Position Size: {config_summary.get("max_position_pct", 0)}%
• Daily Limit: {config_summary.get("daily_loss_limit", 0)}%
• Stop Loss: {config_summary.get("stop_loss_pct", 0)}%

✅ Bot is now monitoring markets
"""

        return await self.send_message(message)

    async def notify_daily_summary(self, summary: Dict) -> bool:
        """
        Send daily trading summary

        Args:
            summary: Daily summary data

        Returns:
            bool: Success status
        """
        emoji = "📈" if summary["total_pnl"] >= 0 else "📉"

        message = f"""
{emoji} <b>Daily Trading Summary</b>

<b>Performance:</b>
• Total P&L: ${summary["total_pnl"]:.2f}
• Trades: {summary["total_trades"]}
• Win Rate: {summary["win_rate"]:.1%}

<b>Best Trade:</b> ${summary["best_trade"]:.2f}
<b>Worst Trade:</b> ${summary["worst_trade"]:.2f}

<b>Portfolio:</b>
• Balance: ${summary["balance"]:,.2f}
• Positions: {summary["open_positions"]}

Keep monitoring and stay disciplined! 💪
"""

        return await self.send_message(message)


# Create global notifier instance
telegram_notifier = TelegramNotifier()
