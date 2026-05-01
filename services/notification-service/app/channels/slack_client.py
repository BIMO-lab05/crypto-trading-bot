"""
Slack Client
Provides webhook integration, channel routing, rich message blocks, and thread replies
"""

import httpx
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from .base import BaseChannel, ChannelResult
from ..config import config

logger = logging.getLogger(__name__)


class SlackClient(BaseChannel):
    """
    Slack notification client

    Features:
    - Webhook integration
    - Channel routing (#trading-critical, #trading-alerts)
    - Rich message blocks
    - Thread replies for related alerts
    - Emoji reactions for alert types
    """

    def __init__(self):
        """Initialize Slack client with configuration"""
        super().__init__(
            name="slack",
            rate_limit=60,
            retry_attempts=3,
            retry_delay=1.0
        )

        self.enabled = config.slack_enabled
        self.webhook_url = config.slack_webhook_url
        self.channel_critical = config.slack_channel_critical
        self.channel_alerts = config.slack_channel_alerts
        self.bot_token = config.slack_bot_token

        # Thread tracking: store thread timestamps
        self._thread_ts: Dict[str, str] = {}

        if self.enabled and self.webhook_url:
            logger.info("Slack client initialized")
        elif self.enabled:
            logger.warning("Slack enabled but webhook URL not configured")

    def is_enabled(self) -> bool:
        """Check if Slack is enabled and configured (webhook OR bot-token)."""
        return self.enabled and (bool(self.webhook_url) or bool(self.bot_token))

    async def send(
        self,
        message: str,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ChannelResult:
        """
        Send a message to Slack

        Args:
            message: Message text
            title: Optional title for the message
            metadata: Additional options:
                - channel: Override default channel
                - blocks: Custom Slack blocks
                - thread_key: Key for threading
                - color: Attachment color
                - emoji: Custom emoji for the message

        Returns:
            ChannelResult with success status
        """
        if not self.is_enabled():
            return ChannelResult(
                success=False,
                channel=self.name,
                error_message="Slack not enabled or webhook not configured"
            )

        metadata = metadata or {}
        channel = metadata.get("channel", self.channel_alerts)
        blocks = metadata.get("blocks")
        thread_key = metadata.get("thread_key")
        color = metadata.get("color", "#3498db")
        emoji = metadata.get("emoji", ":robot_face:")

        # Bot-token path: chat.postMessage (allows per-event channel routing).
        # Webhook is locked to one channel; bot token is required for #bimo-trades
        # vs #bimo-alerts vs #bimo-performance routing.
        if self.bot_token:
            text = f"*{title}*\n{message}" if title else message
            api_payload: Dict[str, Any] = {
                "channel": channel,
                "text": text,
            }
            if blocks:
                api_payload["blocks"] = blocks
            if thread_key and thread_key in self._thread_ts:
                api_payload["thread_ts"] = self._thread_ts[thread_key]
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        "https://slack.com/api/chat.postMessage",
                        headers={"Authorization": f"Bearer {self.bot_token}"},
                        json=api_payload,
                    )
                    data = response.json()
                    if response.status_code == 200 and data.get("ok"):
                        if thread_key and "ts" in data:
                            self._thread_ts[thread_key] = data["ts"]
                        logger.info(f"Slack chat.postMessage delivered to {channel}")
                        return ChannelResult(
                            success=True,
                            channel=self.name,
                            message_id=data.get("ts"),
                            metadata={"channel": channel},
                        )
                    err = data.get("error") or f"HTTP {response.status_code}"
                    logger.error(f"Slack chat.postMessage failed: {err}")
                    return ChannelResult(
                        success=False,
                        channel=self.name,
                        error_message=err,
                    )
            except httpx.TimeoutException:
                logger.error("Slack chat.postMessage timed out")
                return ChannelResult(
                    success=False,
                    channel=self.name,
                    error_message="Request timed out",
                )
            except Exception as e:
                logger.error(f"Slack chat.postMessage exception: {e}")
                return ChannelResult(
                    success=False,
                    channel=self.name,
                    error_message=str(e),
                )

        # Webhook fallback (single-channel)
        payload: Dict[str, Any] = {
            "channel": channel,
            "icon_emoji": emoji,
            "username": "Trading Bot"
        }

        # Use blocks if provided, otherwise build simple message
        if blocks:
            payload["blocks"] = blocks
        else:
            # Build attachment for better formatting
            attachment = {
                "color": color,
                "blocks": self._build_message_blocks(message, title, metadata)
            }
            payload["attachments"] = [attachment]

        # Add thread_ts for threading
        if thread_key and thread_key in self._thread_ts:
            payload["thread_ts"] = self._thread_ts[thread_key]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload
                )

                if response.status_code == 200:
                    # Note: Webhook doesn't return thread_ts, would need Bot API for that
                    logger.info(f"Slack message sent to {channel}")
                    return ChannelResult(
                        success=True,
                        channel=self.name,
                        metadata={"channel": channel}
                    )
                else:
                    error = response.text
                    logger.error(f"Slack error: {response.status_code} - {error}")
                    return ChannelResult(
                        success=False,
                        channel=self.name,
                        error_message=f"HTTP {response.status_code}: {error}"
                    )

        except httpx.TimeoutException:
            logger.error("Slack request timed out")
            return ChannelResult(
                success=False,
                channel=self.name,
                error_message="Request timed out"
            )
        except Exception as e:
            logger.error(f"Slack send failed: {e}")
            return ChannelResult(
                success=False,
                channel=self.name,
                error_message=str(e)
            )

    async def send_to_critical(
        self,
        message: str,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ChannelResult:
        """
        Send a message to the critical alerts channel

        Args:
            message: Message content
            title: Optional title
            metadata: Additional metadata

        Returns:
            ChannelResult with success status
        """
        metadata = metadata or {}
        metadata["channel"] = self.channel_critical
        metadata["color"] = "#e74c3c"  # Red for critical
        metadata["emoji"] = ":rotating_light:"

        return await self.send(message, title, metadata)

    async def send_trade_alert(
        self,
        action: str,
        symbol: str,
        quantity: float,
        price: float,
        pnl: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> ChannelResult:
        """
        Send a formatted trade alert

        Args:
            action: BUY or SELL
            symbol: Trading pair
            quantity: Trade quantity
            price: Trade price
            pnl: Profit/loss if closing
            stop_loss: Stop loss price
            take_profit: Take profit price

        Returns:
            ChannelResult with success status
        """
        color = "#27ae60" if action.upper() == "BUY" else "#e74c3c"
        emoji = ":chart_with_upwards_trend:" if action.upper() == "BUY" else ":chart_with_downwards_trend:"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Trade Executed: {action.upper()} {symbol}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Action:*\n{action.upper()}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Symbol:*\n{symbol}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Quantity:*\n{quantity:.6f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Price:*\n${price:,.2f}"
                    }
                ]
            }
        ]

        # Add risk management fields
        if stop_loss or take_profit:
            risk_fields = []
            if stop_loss:
                risk_fields.append({
                    "type": "mrkdwn",
                    "text": f"*Stop Loss:*\n${stop_loss:,.2f}"
                })
            if take_profit:
                risk_fields.append({
                    "type": "mrkdwn",
                    "text": f"*Take Profit:*\n${take_profit:,.2f}"
                })

            blocks.append({
                "type": "section",
                "fields": risk_fields
            })

        # Add P&L if provided
        if pnl is not None:
            pnl_emoji = ":moneybag:" if pnl >= 0 else ":money_with_wings:"
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{pnl_emoji} *P&L:* ${pnl:,.2f}"
                }
            })

        # Add timestamp
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"_{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC_"
                }
            ]
        })

        return await self.send(
            "",
            metadata={
                "blocks": blocks,
                "color": color,
                "emoji": emoji,
                "thread_key": f"trade_{symbol}"
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
        Send a system status alert

        Args:
            service_name: Name of the service
            status: Current status
            error_message: Error details if applicable
            context: Additional context

        Returns:
            ChannelResult with success status
        """
        status_config = {
            "DOWN": {
                "color": "#e74c3c",
                "emoji": ":x:",
                "channel": self.channel_critical
            },
            "ERROR": {
                "color": "#e74c3c",
                "emoji": ":warning:",
                "channel": self.channel_critical
            },
            "WARNING": {
                "color": "#f1c40f",
                "emoji": ":warning:",
                "channel": self.channel_alerts
            },
            "RECOVERED": {
                "color": "#27ae60",
                "emoji": ":white_check_mark:",
                "channel": self.channel_alerts
            },
            "HEALTHY": {
                "color": "#27ae60",
                "emoji": ":green_heart:",
                "channel": self.channel_alerts
            }
        }

        cfg = status_config.get(status.upper(), {
            "color": "#3498db",
            "emoji": ":information_source:",
            "channel": self.channel_alerts
        })

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"System Alert: {service_name}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Service:*\n{service_name}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Status:*\n{cfg['emoji']} {status.upper()}"
                    }
                ]
            }
        ]

        if error_message:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Error:*\n```{error_message}```"
                }
            })

        if context:
            context_text = "\n".join([f"- {k}: {v}" for k, v in context.items()])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Context:*\n{context_text}"
                }
            })

        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"_{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC_"
                }
            ]
        })

        return await self.send(
            "",
            metadata={
                "blocks": blocks,
                "channel": cfg["channel"],
                "color": cfg["color"],
                "emoji": cfg["emoji"],
                "thread_key": f"system_{service_name}"
            }
        )

    async def send_daily_summary(
        self,
        total_pnl: float,
        total_trades: int,
        win_rate: float,
        best_trade: float,
        worst_trade: float,
        balance: float
    ) -> ChannelResult:
        """
        Send daily trading summary

        Args:
            total_pnl: Total profit/loss
            total_trades: Number of trades
            win_rate: Win percentage 0-1
            best_trade: Best trade P&L
            worst_trade: Worst trade P&L
            balance: Current balance

        Returns:
            ChannelResult with success status
        """
        pnl_emoji = ":chart_with_upwards_trend:" if total_pnl >= 0 else ":chart_with_downwards_trend:"
        color = "#27ae60" if total_pnl >= 0 else "#e74c3c"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Daily Trading Summary",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{pnl_emoji} *Today's P&L: ${total_pnl:,.2f}*"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Total Trades:*\n{total_trades}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Win Rate:*\n{win_rate:.1%}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Best Trade:*\n${best_trade:,.2f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Worst Trade:*\n${worst_trade:,.2f}"
                    }
                ]
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":bank: *Current Balance: ${balance:,.2f}*"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"_Summary for {datetime.utcnow().strftime('%Y-%m-%d')}_"
                    }
                ]
            }
        ]

        return await self.send(
            "",
            metadata={
                "blocks": blocks,
                "color": color,
                "emoji": ":bar_chart:"
            }
        )

    def _build_message_blocks(
        self,
        message: str,
        title: Optional[str],
        metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Build Slack message blocks from simple message

        Args:
            message: Message text
            title: Optional title
            metadata: Additional metadata

        Returns:
            List of Slack block dictionaries
        """
        blocks = []

        if title:
            blocks.append({
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": title,
                    "emoji": True
                }
            })

        if message:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message
                }
            })

        # Add timestamp
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"_{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC_"
                }
            ]
        })

        return blocks

    async def health_check(self) -> bool:
        """
        Check Slack webhook connectivity

        Returns:
            True if webhook is reachable
        """
        if not self.is_enabled():
            return False

        # We can't really health check a webhook without posting
        # Just verify the URL is set
        return bool(self.webhook_url)


# Create global Slack client instance
slack_client = SlackClient()
