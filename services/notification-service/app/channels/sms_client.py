"""
SMS Client (Twilio)
Provides SMS notifications for CRITICAL alerts and escalation fallback
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
import asyncio

from .base import BaseChannel, ChannelResult
from ..config import config

logger = logging.getLogger(__name__)

# Twilio is optional dependency
try:
    from twilio.rest import Client as TwilioClient
    from twilio.base.exceptions import TwilioRestException
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    logger.warning("Twilio not installed. SMS notifications disabled. Install with: pip install twilio")


class SMSClient(BaseChannel):
    """
    SMS notification client using Twilio

    Features:
    - Only for CRITICAL alerts
    - Short concise messages (160 char limit awareness)
    - Fallback if other channels fail
    - Multiple recipient support
    """

    # SMS has a 160 character limit per segment
    MAX_MESSAGE_LENGTH = 160

    def __init__(self):
        """Initialize SMS client with Twilio configuration"""
        super().__init__(
            name="sms",
            rate_limit=10,  # Lower rate limit for SMS
            retry_attempts=2,
            retry_delay=2.0
        )

        self.enabled = config.sms_enabled and TWILIO_AVAILABLE
        self.account_sid = config.twilio_account_sid
        self.auth_token = config.twilio_auth_token
        self.from_number = config.twilio_phone_number
        self.recipient_numbers = [
            n.strip() for n in config.sms_recipient_numbers.split(",")
            if n.strip()
        ]

        self._client: Optional["TwilioClient"] = None

        if self.enabled and self._validate_config():
            try:
                self._client = TwilioClient(self.account_sid, self.auth_token)
                logger.info(f"SMS client initialized. Recipients: {len(self.recipient_numbers)}")
            except Exception as e:
                logger.error(f"Failed to initialize Twilio client: {e}")
                self.enabled = False
        elif config.sms_enabled and not TWILIO_AVAILABLE:
            logger.warning("SMS enabled in config but Twilio package not installed")

    def _validate_config(self) -> bool:
        """Validate Twilio configuration"""
        if not self.account_sid:
            logger.warning("Twilio Account SID not configured")
            return False
        if not self.auth_token:
            logger.warning("Twilio Auth Token not configured")
            return False
        if not self.from_number:
            logger.warning("Twilio phone number not configured")
            return False
        if not self.recipient_numbers:
            logger.warning("No SMS recipient numbers configured")
            return False
        return True

    def is_enabled(self) -> bool:
        """Check if SMS is enabled and configured"""
        return self.enabled and self._client is not None

    async def send(
        self,
        message: str,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ChannelResult:
        """
        Send an SMS message

        Args:
            message: Message content
            title: Optional title (will be prefixed)
            metadata: Additional options:
                - recipients: Override default recipients
                - truncate: Whether to truncate long messages (default: True)

        Returns:
            ChannelResult with success status
        """
        if not self.is_enabled():
            return ChannelResult(
                success=False,
                channel=self.name,
                error_message="SMS not enabled or Twilio not configured"
            )

        metadata = metadata or {}
        recipients = metadata.get("recipients", self.recipient_numbers)
        truncate = metadata.get("truncate", True)

        # Format message
        formatted_message = self._format_message(message, title, truncate)

        # Send to all recipients
        results = []
        loop = asyncio.get_event_loop()

        for recipient in recipients:
            result = await loop.run_in_executor(
                None,
                self._send_sms_sync,
                recipient,
                formatted_message
            )
            results.append(result)

        # Aggregate results
        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]

        if len(successes) == len(recipients):
            return ChannelResult(
                success=True,
                channel=self.name,
                metadata={
                    "recipients_sent": len(successes),
                    "message_length": len(formatted_message)
                }
            )
        elif successes:
            return ChannelResult(
                success=True,  # Partial success
                channel=self.name,
                error_message=f"Sent to {len(successes)}/{len(recipients)} recipients",
                metadata={
                    "recipients_sent": len(successes),
                    "recipients_failed": len(failures)
                }
            )
        else:
            return ChannelResult(
                success=False,
                channel=self.name,
                error_message=failures[0].error_message if failures else "All sends failed"
            )

    def _send_sms_sync(self, recipient: str, message: str) -> ChannelResult:
        """
        Synchronous SMS sending via Twilio

        Args:
            recipient: Phone number to send to
            message: Message content

        Returns:
            ChannelResult with success status
        """
        if not self._client:
            return ChannelResult(
                success=False,
                channel=self.name,
                error_message="Twilio client not initialized"
            )

        try:
            twilio_message = self._client.messages.create(
                body=message,
                from_=self.from_number,
                to=recipient
            )

            logger.info(f"SMS sent to {recipient}: {twilio_message.sid}")
            return ChannelResult(
                success=True,
                channel=self.name,
                message_id=twilio_message.sid,
                metadata={
                    "recipient": recipient,
                    "status": twilio_message.status
                }
            )

        except TwilioRestException as e:
            logger.error(f"Twilio error sending to {recipient}: {e}")
            return ChannelResult(
                success=False,
                channel=self.name,
                error_message=f"Twilio error: {e.msg}"
            )
        except Exception as e:
            logger.error(f"SMS send failed to {recipient}: {e}")
            return ChannelResult(
                success=False,
                channel=self.name,
                error_message=str(e)
            )

    def _format_message(
        self,
        message: str,
        title: Optional[str],
        truncate: bool
    ) -> str:
        """
        Format message for SMS (160 char awareness)

        Args:
            message: Raw message
            title: Optional title
            truncate: Whether to truncate to 160 chars

        Returns:
            Formatted message string
        """
        # Build message with title
        if title:
            formatted = f"[{title}] {message}"
        else:
            formatted = f"[Trading Bot] {message}"

        # Truncate if needed
        if truncate and len(formatted) > self.MAX_MESSAGE_LENGTH:
            formatted = formatted[:self.MAX_MESSAGE_LENGTH - 3] + "..."

        return formatted

    async def send_critical_alert(
        self,
        alert_type: str,
        message: str
    ) -> ChannelResult:
        """
        Send a critical alert via SMS

        Args:
            alert_type: Type of critical alert
            message: Alert message

        Returns:
            ChannelResult with success status
        """
        # Keep it short for SMS
        short_message = f"{alert_type}: {message}"

        return await self.send(
            short_message,
            title="CRITICAL",
            metadata={"truncate": True}
        )

    async def send_escalation(
        self,
        original_alert: str,
        escalation_reason: str
    ) -> ChannelResult:
        """
        Send an escalation alert when other channels fail

        Args:
            original_alert: The original alert message
            escalation_reason: Why escalation occurred

        Returns:
            ChannelResult with success status
        """
        message = f"{escalation_reason}. Check dashboard immediately."

        return await self.send(
            message,
            title="ESCALATION",
            metadata={"truncate": True}
        )

    async def send_system_down_alert(
        self,
        service_name: str,
        downtime_minutes: int
    ) -> ChannelResult:
        """
        Send system down alert

        Args:
            service_name: Name of the down service
            downtime_minutes: Minutes of downtime

        Returns:
            ChannelResult with success status
        """
        message = f"{service_name} down for {downtime_minutes}min. Immediate action required."

        return await self.send(
            message,
            title="SYSTEM DOWN",
            metadata={"truncate": True}
        )

    async def health_check(self) -> bool:
        """
        Check Twilio API connectivity

        Returns:
            True if Twilio API is reachable
        """
        if not self.is_enabled():
            return False

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._health_check_sync
            )
            return result
        except Exception as e:
            logger.error(f"SMS health check error: {e}")
            return False

    def _health_check_sync(self) -> bool:
        """Synchronous health check"""
        if not self._client:
            return False

        try:
            # Fetch account info to verify credentials
            account = self._client.api.accounts(self.account_sid).fetch()
            is_active = account.status == "active"

            if is_active:
                logger.debug("Twilio health check passed")
            else:
                logger.warning(f"Twilio account status: {account.status}")

            return is_active

        except Exception as e:
            logger.error(f"Twilio health check failed: {e}")
            return False

    def get_remaining_balance(self) -> Optional[float]:
        """
        Get remaining Twilio account balance

        Returns:
            Balance in USD or None if unavailable
        """
        if not self._client:
            return None

        try:
            balance = self._client.api.accounts(self.account_sid).balance.fetch()
            return float(balance.balance)
        except Exception as e:
            logger.error(f"Failed to fetch Twilio balance: {e}")
            return None


# Create global SMS client instance
sms_client = SMSClient()
