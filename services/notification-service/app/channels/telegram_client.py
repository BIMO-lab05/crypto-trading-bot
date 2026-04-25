"""
Enhanced Telegram Client
Provides rich formatting, inline buttons, message threading, and rate limiting
"""

import httpx
import logging
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from .base import BaseChannel, ChannelResult
from ..config import config

logger = logging.getLogger(__name__)


@dataclass
class InlineButton:
    """Telegram inline keyboard button"""
    text: str
    callback_data: Optional[str] = None
    url: Optional[str] = None


class TelegramClient(BaseChannel):
    """
    Enhanced Telegram notification client

    Features:
    - Rich Markdown/HTML formatting
    - Inline buttons for actions
    - Message threading (reply to messages)
    - Rate limiting (max 20/min)
    - Retry logic with exponential backoff
    """

    def __init__(self):
        """Initialize Telegram client with configuration"""
        super().__init__(
            name="telegram",
            rate_limit=config.telegram_rate_limit,
            retry_attempts=config.telegram_retry_attempts,
            retry_delay=config.telegram_retry_delay
        )

        self.bot_token = config.telegram_bot_token
        self.chat_id = config.telegram_chat_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.enabled = config.telegram_enabled

        # Message threading: store message IDs for threads
        self._thread_messages: Dict[str, int] = {}

        if self.enabled and self.bot_token and self.chat_id:
            logger.info(f"Telegram client initialized for chat: {self.chat_id}")
        elif self.enabled:
            logger.warning("Telegram enabled but missing bot_token or chat_id")

    def is_enabled(self) -> bool:
        """Check if Telegram is enabled and configured"""
        return (
            self.enabled and
            bool(self.bot_token) and
            bool(self.chat_id)
        )

    async def send(
        self,
        message: str,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ChannelResult:
        """
        Send a message via Telegram

        Args:
            message: Message content (supports HTML)
            title: Optional title (will be bold prefixed)
            metadata: Additional options:
                - parse_mode: HTML or Markdown (default: HTML)
                - buttons: List of InlineButton for inline keyboard
                - thread_key: Key for message threading
                - disable_notification: Silent message
                - disable_preview: Disable link preview

        Returns:
            ChannelResult with success status
        """
        if not self.is_enabled():
            return ChannelResult(
                success=False,
                channel=self.name,
                error_message="Telegram not enabled or not configured"
            )

        metadata = metadata or {}
        parse_mode = metadata.get("parse_mode", "HTML")

        # Format message with title if provided
        formatted_message = message
        if title:
            if parse_mode == "HTML":
                formatted_message = f"<b>{title}</b>\n\n{message}"
            else:
                formatted_message = f"*{title}*\n\n{message}"

        # Build payload
        payload: Dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": formatted_message,
            "parse_mode": parse_mode
        }

        # Add optional parameters
        if metadata.get("disable_notification"):
            payload["disable_notification"] = True

        if metadata.get("disable_preview"):
            payload["disable_web_page_preview"] = True

        # Handle message threading
        thread_key = metadata.get("thread_key")
        if thread_key and thread_key in self._thread_messages:
            payload["reply_to_message_id"] = self._thread_messages[thread_key]

        # Add inline keyboard if buttons provided
        buttons = metadata.get("buttons")
        if buttons:
            keyboard = self._build_inline_keyboard(buttons)
            payload["reply_markup"] = keyboard

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/sendMessage",
                    json=payload
                )
                response.raise_for_status()
                data = response.json()

                if data.get("ok"):
                    message_id = data.get("result", {}).get("message_id")

                    # Store message ID for threading
                    if thread_key:
                        self._thread_messages[thread_key] = message_id

                    logger.info(f"Telegram message sent: {message_id}")
                    return ChannelResult(
                        success=True,
                        channel=self.name,
                        message_id=str(message_id),
                        metadata={"telegram_message_id": message_id}
                    )
                else:
                    error = data.get("description", "Unknown error")
                    logger.error(f"Telegram API error: {error}")
                    return ChannelResult(
                        success=False,
                        channel=self.name,
                        error_message=error
                    )

        except httpx.TimeoutException:
            logger.error("Telegram request timed out")
            return ChannelResult(
                success=False,
                channel=self.name,
                error_message="Request timed out"
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"Telegram HTTP error: {e.response.status_code}")
            return ChannelResult(
                success=False,
                channel=self.name,
                error_message=f"HTTP {e.response.status_code}: {e.response.text}"
            )
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return ChannelResult(
                success=False,
                channel=self.name,
                error_message=str(e)
            )

    async def send_with_buttons(
        self,
        message: str,
        buttons: List[List[InlineButton]],
        title: Optional[str] = None,
        parse_mode: str = "HTML"
    ) -> ChannelResult:
        """
        Send a message with inline action buttons

        Args:
            message: Message content
            buttons: 2D list of buttons (rows x columns)
            title: Optional title
            parse_mode: HTML or Markdown

        Returns:
            ChannelResult with success status
        """
        button_data = []
        for row in buttons:
            button_row = []
            for btn in row:
                btn_dict = {"text": btn.text}
                if btn.callback_data:
                    btn_dict["callback_data"] = btn.callback_data
                elif btn.url:
                    btn_dict["url"] = btn.url
                button_row.append(btn_dict)
            button_data.append(button_row)

        return await self.send(
            message,
            title,
            metadata={
                "parse_mode": parse_mode,
                "buttons": button_data
            }
        )

    async def send_trade_alert(
        self,
        action: str,
        symbol: str,
        quantity: float,
        price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        confidence: float = 0.0,
        position_id: Optional[str] = None
    ) -> ChannelResult:
        """
        Send a formatted trade alert with action buttons

        Args:
            action: BUY or SELL
            symbol: Trading pair
            quantity: Trade quantity
            price: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            confidence: Signal confidence 0-1
            position_id: Position ID for button callbacks

        Returns:
            ChannelResult with success status
        """
        emoji = "BUY" if action.upper() == "BUY" else "SELL"

        # Calculate risk/reward if SL and TP available
        rr_info = ""
        if stop_loss and take_profit:
            if action.upper() == "BUY":
                risk_pct = abs((price - stop_loss) / price * 100)
                reward_pct = abs((take_profit - price) / price * 100)
            else:
                risk_pct = abs((stop_loss - price) / price * 100)
                reward_pct = abs((price - take_profit) / price * 100)

            if risk_pct > 0:
                rr_ratio = reward_pct / risk_pct
                rr_info = f"\n- Risk/Reward: 1:{rr_ratio:.2f}"

        message = f"""
<b>Action:</b> {action.upper()}
<b>Symbol:</b> {symbol}
<b>Quantity:</b> {quantity:.6f}
<b>Entry Price:</b> ${price:,.2f}
<b>Total Value:</b> ${quantity * price:,.2f}

<b>Risk Management:</b>"""

        if stop_loss:
            if action.upper() == "BUY":
                sl_pct = ((price - stop_loss) / price) * 100
            else:
                sl_pct = ((stop_loss - price) / price) * 100
            message += f"\n- Stop Loss: ${stop_loss:,.2f} (-{sl_pct:.2f}%)"

        if take_profit:
            if action.upper() == "BUY":
                tp_pct = ((take_profit - price) / price) * 100
            else:
                tp_pct = ((price - take_profit) / price) * 100
            message += f"\n- Take Profit: ${take_profit:,.2f} (+{tp_pct:.2f}%)"

        message += rr_info
        message += f"\n\n<b>Confidence:</b> {confidence:.1%}"
        message += f"\n<b>Time:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"

        # Create action buttons if position_id provided
        buttons = None
        if position_id:
            buttons = [
                [
                    {"text": "Close Position", "callback_data": f"close_{position_id}"},
                    {"text": "Modify SL/TP", "callback_data": f"modify_{position_id}"}
                ],
                [
                    {"text": "Pause Trading", "callback_data": "pause_trading"}
                ]
            ]

        emoji_icon = "+" if action.upper() == "BUY" else "-"
        return await self.send(
            message,
            title=f"{emoji_icon} Trade Executed",
            metadata={
                "buttons": buttons,
                "thread_key": f"trade_{symbol}"
            }
        )

    async def send_risk_alert(
        self,
        alert_type: str,
        message: str,
        current_value: float,
        threshold: float,
        severity: str = "HIGH"
    ) -> ChannelResult:
        """
        Send a risk management alert

        Args:
            alert_type: Type of risk alert
            message: Alert description
            current_value: Current metric value
            threshold: Threshold that was breached
            severity: Alert severity

        Returns:
            ChannelResult with success status
        """
        emoji_map = {
            "CRITICAL": "!",
            "HIGH": "!",
            "MEDIUM": "!",
            "LOW": "!",
        }
        emoji = emoji_map.get(severity, "!")

        formatted_message = f"""
<b>Alert Type:</b> {alert_type}
<b>Current Value:</b> {current_value:.2f}
<b>Threshold:</b> {threshold:.2f}

{message}

<b>Time:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
"""

        buttons = [
            [
                {"text": "Acknowledge", "callback_data": f"ack_risk_{alert_type}"},
                {"text": "View Details", "callback_data": f"details_risk_{alert_type}"}
            ]
        ]

        return await self.send(
            formatted_message,
            title=f"{emoji} Risk Alert: {severity}",
            metadata={
                "buttons": buttons,
                "thread_key": "risk_alerts"
            }
        )

    async def send_system_alert(
        self,
        service_name: str,
        status: str,
        error_message: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> ChannelResult:
        """
        Send a system/service alert

        Args:
            service_name: Name of the affected service
            status: Current status (DOWN, ERROR, RECOVERED, etc.)
            error_message: Error details if applicable
            context: Additional context data

        Returns:
            ChannelResult with success status
        """
        status_emoji = {
            "DOWN": "x",
            "ERROR": "!",
            "WARNING": "!",
            "RECOVERED": "+",
            "HEALTHY": "+",
        }
        emoji = status_emoji.get(status.upper(), "?")

        message = f"""
<b>Service:</b> {service_name}
<b>Status:</b> {status.upper()}
"""

        if error_message:
            message += f"\n<b>Error:</b> <code>{error_message}</code>"

        if context:
            message += "\n\n<b>Context:</b>"
            for key, value in context.items():
                message += f"\n- {key}: {value}"

        message += f"\n\n<b>Time:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"

        return await self.send(
            message,
            title=f"{emoji} System Alert",
            metadata={
                "thread_key": f"system_{service_name}",
                "disable_preview": True
            }
        )

    async def health_check(self) -> bool:
        """
        Check Telegram API connectivity

        Returns:
            True if API is reachable and bot is valid
        """
        if not self.is_enabled():
            return False

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/getMe")
                data = response.json()
                is_healthy = data.get("ok", False)

                if is_healthy:
                    logger.debug(f"Telegram health check passed: {data.get('result', {}).get('username')}")
                else:
                    logger.warning(f"Telegram health check failed: {data.get('description')}")

                return is_healthy

        except Exception as e:
            logger.error(f"Telegram health check error: {e}")
            return False

    def _build_inline_keyboard(
        self,
        buttons: List[List[Dict[str, str]]]
    ) -> Dict[str, Any]:
        """
        Build Telegram inline keyboard markup

        Args:
            buttons: 2D list of button dictionaries

        Returns:
            Inline keyboard markup dictionary
        """
        return {"inline_keyboard": buttons}

    def get_thread_message_id(self, thread_key: str) -> Optional[int]:
        """Get message ID for a thread key"""
        return self._thread_messages.get(thread_key)

    def clear_thread(self, thread_key: str):
        """Clear a message thread"""
        if thread_key in self._thread_messages:
            del self._thread_messages[thread_key]


# Create global Telegram client instance
telegram_client = TelegramClient()
