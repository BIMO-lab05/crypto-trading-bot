"""
Base Channel Interface
Abstract base class for all notification channels
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
import logging
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class ChannelResult:
    """Result of a channel send operation"""
    success: bool
    channel: str
    message_id: Optional[str] = None
    delivery_time_ms: int = 0
    error_message: Optional[str] = None
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


class BaseChannel(ABC):
    """
    Abstract base class for notification channels

    All channel implementations must inherit from this class
    and implement the abstract methods.
    """

    def __init__(
        self,
        name: str,
        rate_limit: int = 60,
        retry_attempts: int = 3,
        retry_delay: float = 1.0
    ):
        """
        Initialize the base channel

        Args:
            name: Channel name identifier
            rate_limit: Maximum messages per minute
            retry_attempts: Number of retry attempts on failure
            retry_delay: Initial delay between retries (exponential backoff)
        """
        self.name = name
        self.rate_limit = rate_limit
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay

        # Rate limiting state
        self._message_timestamps: List[datetime] = []
        self._rate_limit_window = 60  # seconds

        # Health tracking
        self._last_success: Optional[datetime] = None
        self._last_failure: Optional[datetime] = None
        self._consecutive_failures = 0
        self._total_sent = 0
        self._total_failed = 0

        logger.info(f"Initialized {self.name} channel")

    @abstractmethod
    async def send(
        self,
        message: str,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ChannelResult:
        """
        Send a message through this channel

        Args:
            message: The message content
            title: Optional message title
            metadata: Additional metadata for the message

        Returns:
            ChannelResult with success status and details
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the channel is healthy and operational

        Returns:
            True if channel is healthy, False otherwise
        """
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        """
        Check if the channel is enabled in configuration

        Returns:
            True if channel is enabled, False otherwise
        """
        pass

    def _check_rate_limit(self) -> bool:
        """
        Check if we're within rate limits

        Returns:
            True if we can send, False if rate limited
        """
        now = datetime.utcnow()

        # Remove timestamps older than the window
        cutoff = now.timestamp() - self._rate_limit_window
        self._message_timestamps = [
            ts for ts in self._message_timestamps
            if ts.timestamp() > cutoff
        ]

        # Check if we're under the limit
        return len(self._message_timestamps) < self.rate_limit

    def _record_send(self):
        """Record a message send for rate limiting"""
        self._message_timestamps.append(datetime.utcnow())

    def get_rate_limit_remaining(self) -> int:
        """Get remaining messages allowed in current window"""
        self._check_rate_limit()  # Clean up old timestamps
        return max(0, self.rate_limit - len(self._message_timestamps))

    async def send_with_retry(
        self,
        message: str,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ChannelResult:
        """
        Send a message with automatic retry on failure

        Uses exponential backoff for retries.

        Args:
            message: The message content
            title: Optional message title
            metadata: Additional metadata

        Returns:
            ChannelResult with final status
        """
        start_time = datetime.utcnow()
        last_error = None

        # Check rate limit first
        if not self._check_rate_limit():
            return ChannelResult(
                success=False,
                channel=self.name,
                error_message="Rate limit exceeded",
                timestamp=start_time
            )

        for attempt in range(self.retry_attempts):
            try:
                result = await self.send(message, title, metadata)

                if result.success:
                    self._record_send()
                    self._last_success = datetime.utcnow()
                    self._consecutive_failures = 0
                    self._total_sent += 1
                    result.retry_count = attempt
                    result.delivery_time_ms = int(
                        (datetime.utcnow() - start_time).total_seconds() * 1000
                    )
                    return result

                last_error = result.error_message

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"{self.name} send attempt {attempt + 1} failed: {e}"
                )

            # Wait before retry (exponential backoff)
            if attempt < self.retry_attempts - 1:
                delay = self.retry_delay * (2 ** attempt)
                await asyncio.sleep(delay)

        # All retries failed
        self._last_failure = datetime.utcnow()
        self._consecutive_failures += 1
        self._total_failed += 1

        return ChannelResult(
            success=False,
            channel=self.name,
            error_message=f"Failed after {self.retry_attempts} attempts: {last_error}",
            retry_count=self.retry_attempts,
            delivery_time_ms=int(
                (datetime.utcnow() - start_time).total_seconds() * 1000
            ),
            timestamp=start_time
        )

    def get_health_status(self) -> Dict[str, Any]:
        """
        Get comprehensive health status of the channel

        Returns:
            Dictionary with health metrics
        """
        return {
            "channel": self.name,
            "enabled": self.is_enabled(),
            "healthy": self._consecutive_failures < 3,
            "last_success": self._last_success.isoformat() if self._last_success else None,
            "last_failure": self._last_failure.isoformat() if self._last_failure else None,
            "consecutive_failures": self._consecutive_failures,
            "total_sent": self._total_sent,
            "total_failed": self._total_failed,
            "rate_limit_remaining": self.get_rate_limit_remaining(),
            "success_rate": (
                self._total_sent / (self._total_sent + self._total_failed) * 100
                if (self._total_sent + self._total_failed) > 0 else 100.0
            )
        }

    def reset_stats(self):
        """Reset channel statistics"""
        self._last_success = None
        self._last_failure = None
        self._consecutive_failures = 0
        self._total_sent = 0
        self._total_failed = 0
        logger.info(f"Reset stats for {self.name} channel")
