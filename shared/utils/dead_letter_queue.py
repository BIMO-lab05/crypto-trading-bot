"""
Dead Letter Queue (DLQ) Implementation
Handles failed messages for retry and analysis

Features:
- Failed message storage
- Automatic retry with exponential backoff
- Message TTL management
- Pattern analysis
- Alert generation
- Metrics tracking
"""

import asyncio
import json
import time
import logging
from typing import Optional, Dict, Any, Callable, List
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import hashlib

logger = logging.getLogger(__name__)


class DLQMessageStatus(Enum):
    """Dead letter queue message status"""
    PENDING = "pending"
    RETRYING = "retrying"
    FAILED = "failed"
    RESOLVED = "resolved"
    EXPIRED = "expired"


@dataclass
class DLQMessage:
    """Dead letter queue message structure"""
    id: str
    message: Dict[str, Any]
    error: str
    error_type: str
    source: str
    retry_count: int
    max_retries: int
    status: str
    created_at: float
    updated_at: float
    last_retry_at: Optional[float] = None
    resolved_at: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'DLQMessage':
        """Create from dictionary"""
        return cls(**data)


class DeadLetterQueue:
    """
    Dead Letter Queue for handling failed messages

    Features:
    - Store failed messages with full context
    - Automatic retry with exponential backoff
    - TTL-based message expiration
    - Pattern detection for recurring issues
    - Metrics and alerting
    """

    def __init__(
        self,
        redis_pool,
        max_retries: int = 3,
        retry_delay_base: int = 60,
        retry_delay_max: int = 3600,
        message_ttl: int = 604800,  # 7 days
        enable_pattern_detection: bool = True
    ):
        """
        Initialize Dead Letter Queue

        Args:
            redis_pool: Redis connection pool
            max_retries: Maximum retry attempts per message
            retry_delay_base: Base retry delay in seconds
            retry_delay_max: Maximum retry delay in seconds
            message_ttl: Message time-to-live in seconds (default: 7 days)
            enable_pattern_detection: Enable error pattern analysis
        """
        self.redis = redis_pool
        self.max_retries = max_retries
        self.retry_delay_base = retry_delay_base
        self.retry_delay_max = retry_delay_max
        self.message_ttl = message_ttl
        self.enable_pattern_detection = enable_pattern_detection

        # Retry handlers for different sources
        self.retry_handlers: Dict[str, Callable] = {}

    def register_retry_handler(self, source: str, handler: Callable):
        """
        Register a retry handler for a specific source

        Args:
            source: Source identifier (e.g., "trading-engine", "market-data")
            handler: Async function that takes (message, error) and retries

        Usage:
            async def retry_trade(message, error):
                # Retry logic
                await execute_trade(message)

            dlq.register_retry_handler("trading-engine", retry_trade)
        """
        self.retry_handlers[source] = handler
        logger.info(f"Registered DLQ retry handler for source: {source}")

    def _generate_message_id(self, message: Dict, source: str) -> str:
        """Generate unique message ID"""
        content = json.dumps(message, sort_keys=True)
        hash_input = f"{source}:{content}:{time.time()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def _calculate_retry_delay(self, retry_count: int) -> int:
        """Calculate exponential backoff delay"""
        delay = min(
            self.retry_delay_base * (2 ** retry_count),
            self.retry_delay_max
        )
        return delay

    async def send_to_dlq(
        self,
        message: Dict[str, Any],
        error: Exception,
        source: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Send failed message to dead letter queue

        Args:
            message: Original message that failed
            error: Exception that caused the failure
            source: Source of the message (service name)
            metadata: Additional metadata

        Returns:
            Message ID
        """
        current_time = time.time()
        message_id = self._generate_message_id(message, source)

        dlq_message = DLQMessage(
            id=message_id,
            message=message,
            error=str(error),
            error_type=type(error).__name__,
            source=source,
            retry_count=0,
            max_retries=self.max_retries,
            status=DLQMessageStatus.PENDING.value,
            created_at=current_time,
            updated_at=current_time,
            metadata=metadata or {}
        )

        # Store in Redis
        key = f"dlq:{source}:{message_id}"
        await self.redis.set(
            key,
            json.dumps(dlq_message.to_dict()),
            expire=self.message_ttl
        )

        # Add to pending list for retry processing
        await self.redis.lpush(f"dlq:pending:{source}", message_id)

        # Update metrics
        await self._update_metrics(source, "failed", error_type=type(error).__name__)

        # Pattern detection
        if self.enable_pattern_detection:
            await self._detect_patterns(source, type(error).__name__)

        logger.warning(
            "Message sent to DLQ",
            message_id=message_id,
            source=source,
            error_type=type(error).__name__,
            error=str(error)
        )

        return message_id

    async def retry_message(self, message_id: str, source: str) -> bool:
        """
        Retry a specific message from DLQ

        Args:
            message_id: ID of message to retry
            source: Source of the message

        Returns:
            True if retry succeeded, False otherwise
        """
        key = f"dlq:{source}:{message_id}"

        # Get message from Redis
        message_data = await self.redis.get(key)
        if not message_data:
            logger.error(f"DLQ message not found: {message_id}")
            return False

        dlq_message = DLQMessage.from_dict(json.loads(message_data))

        # Check if max retries exceeded
        if dlq_message.retry_count >= dlq_message.max_retries:
            dlq_message.status = DLQMessageStatus.FAILED.value
            await self.redis.set(key, json.dumps(dlq_message.to_dict()))
            logger.error(
                "DLQ message max retries exceeded",
                message_id=message_id,
                retry_count=dlq_message.retry_count
            )
            return False

        # Update retry status
        dlq_message.retry_count += 1
        dlq_message.status = DLQMessageStatus.RETRYING.value
        dlq_message.last_retry_at = time.time()
        dlq_message.updated_at = time.time()

        await self.redis.set(key, json.dumps(dlq_message.to_dict()))

        # Get retry handler
        handler = self.retry_handlers.get(source)
        if not handler:
            logger.error(f"No retry handler registered for source: {source}")
            return False

        # Attempt retry
        try:
            logger.info(
                "Retrying DLQ message",
                message_id=message_id,
                source=source,
                retry_count=dlq_message.retry_count
            )

            await handler(dlq_message.message, dlq_message.error)

            # Mark as resolved
            dlq_message.status = DLQMessageStatus.RESOLVED.value
            dlq_message.resolved_at = time.time()
            dlq_message.updated_at = time.time()

            await self.redis.set(key, json.dumps(dlq_message.to_dict()))
            await self._update_metrics(source, "resolved")

            logger.info(
                "DLQ message retry succeeded",
                message_id=message_id,
                source=source
            )

            return True

        except Exception as e:
            # Retry failed
            logger.error(
                "DLQ message retry failed",
                message_id=message_id,
                source=source,
                error=str(e)
            )

            # Calculate next retry delay
            delay = self._calculate_retry_delay(dlq_message.retry_count)

            # Update status
            dlq_message.status = DLQMessageStatus.PENDING.value
            dlq_message.updated_at = time.time()

            await self.redis.set(key, json.dumps(dlq_message.to_dict()))

            # Schedule next retry
            await self.redis.lpush(f"dlq:pending:{source}", message_id)
            await self.redis.expire(f"dlq:pending:{source}", delay)

            await self._update_metrics(source, "retry_failed", error_type=type(e).__name__)

            return False

    async def retry_pending_messages(self, source: str, batch_size: int = 10):
        """
        Process pending DLQ messages for a source

        Args:
            source: Source identifier
            batch_size: Number of messages to process in batch
        """
        pending_key = f"dlq:pending:{source}"

        for _ in range(batch_size):
            # Get next pending message
            message_id = await self.redis.rpop(pending_key)
            if not message_id:
                break

            # Retry message
            await self.retry_message(message_id, source)

    async def get_message(self, message_id: str, source: str) -> Optional[DLQMessage]:
        """Get DLQ message by ID"""
        key = f"dlq:{source}:{message_id}"
        message_data = await self.redis.get(key)

        if message_data:
            return DLQMessage.from_dict(json.loads(message_data))
        return None

    async def get_messages(
        self,
        source: str,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[DLQMessage]:
        """
        Get DLQ messages for a source

        Args:
            source: Source identifier
            status: Filter by status (optional)
            limit: Maximum messages to return

        Returns:
            List of DLQ messages
        """
        pattern = f"dlq:{source}:*"
        keys = await self.redis.keys(pattern)

        messages = []
        for key in keys[:limit]:
            message_data = await self.redis.get(key)
            if message_data:
                msg = DLQMessage.from_dict(json.loads(message_data))
                if status is None or msg.status == status:
                    messages.append(msg)

        return sorted(messages, key=lambda x: x.created_at, reverse=True)

    async def delete_message(self, message_id: str, source: str) -> bool:
        """Delete message from DLQ"""
        key = f"dlq:{source}:{message_id}"
        result = await self.redis.delete(key)
        return result > 0

    async def get_statistics(self, source: str) -> Dict[str, Any]:
        """
        Get DLQ statistics for a source

        Returns:
            Statistics dictionary
        """
        messages = await self.get_messages(source, limit=1000)

        stats = {
            "total": len(messages),
            "pending": len([m for m in messages if m.status == DLQMessageStatus.PENDING.value]),
            "retrying": len([m for m in messages if m.status == DLQMessageStatus.RETRYING.value]),
            "failed": len([m for m in messages if m.status == DLQMessageStatus.FAILED.value]),
            "resolved": len([m for m in messages if m.status == DLQMessageStatus.RESOLVED.value]),
            "error_types": {},
            "avg_retry_count": 0,
            "oldest_message": None,
            "newest_message": None
        }

        if messages:
            # Error type distribution
            for msg in messages:
                error_type = msg.error_type
                stats["error_types"][error_type] = stats["error_types"].get(error_type, 0) + 1

            # Average retry count
            stats["avg_retry_count"] = sum(m.retry_count for m in messages) / len(messages)

            # Oldest and newest
            stats["oldest_message"] = min(messages, key=lambda x: x.created_at).created_at
            stats["newest_message"] = max(messages, key=lambda x: x.created_at).created_at

        return stats

    async def _update_metrics(
        self,
        source: str,
        metric_type: str,
        error_type: Optional[str] = None
    ):
        """Update DLQ metrics in Redis"""
        metrics_key = f"dlq:metrics:{source}"

        # Increment counters
        await self.redis.hincrby(metrics_key, f"total_{metric_type}", 1)

        if error_type:
            await self.redis.hincrby(metrics_key, f"error:{error_type}", 1)

        # Set TTL on metrics
        await self.redis.expire(metrics_key, 86400 * 30)  # 30 days

    async def _detect_patterns(self, source: str, error_type: str):
        """
        Detect error patterns for alerting

        If same error occurs frequently, trigger alert
        """
        pattern_key = f"dlq:pattern:{source}:{error_type}"

        # Increment error count
        count = await self.redis.incr(pattern_key)
        await self.redis.expire(pattern_key, 3600)  # 1 hour window

        # Alert threshold
        if count >= 10:
            logger.critical(
                "DLQ error pattern detected",
                source=source,
                error_type=error_type,
                count=count,
                window="1 hour"
            )
            # Could integrate with alerting system here

    async def cleanup_old_messages(self, days: int = 7):
        """
        Clean up old resolved/failed messages

        Args:
            days: Delete messages older than this many days
        """
        cutoff_time = time.time() - (days * 86400)
        deleted_count = 0

        # Get all DLQ keys
        pattern = "dlq:*:*"
        keys = await self.redis.keys(pattern)

        for key in keys:
            message_data = await self.redis.get(key)
            if message_data:
                msg = DLQMessage.from_dict(json.loads(message_data))

                # Delete if old and resolved/failed
                if (msg.created_at < cutoff_time and
                    msg.status in [DLQMessageStatus.RESOLVED.value, DLQMessageStatus.FAILED.value]):
                    await self.redis.delete(key)
                    deleted_count += 1

        logger.info(f"DLQ cleanup: deleted {deleted_count} old messages")
        return deleted_count


class DLQWorker:
    """
    Background worker for processing DLQ messages

    Continuously processes pending messages with retry logic
    """

    def __init__(
        self,
        dlq: DeadLetterQueue,
        sources: List[str],
        check_interval: int = 60,
        batch_size: int = 10
    ):
        """
        Initialize DLQ worker

        Args:
            dlq: DeadLetterQueue instance
            sources: List of sources to monitor
            check_interval: Seconds between checks
            batch_size: Messages to process per batch
        """
        self.dlq = dlq
        self.sources = sources
        self.check_interval = check_interval
        self.batch_size = batch_size
        self.running = False
        self.task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the DLQ worker"""
        if self.running:
            logger.warning("DLQ worker already running")
            return

        self.running = True
        self.task = asyncio.create_task(self._worker_loop())
        logger.info(
            "DLQ worker started",
            sources=self.sources,
            check_interval=self.check_interval
        )

    async def stop(self):
        """Stop the DLQ worker"""
        if not self.running:
            return

        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        logger.info("DLQ worker stopped")

    async def _worker_loop(self):
        """Main worker loop"""
        while self.running:
            try:
                for source in self.sources:
                    await self.dlq.retry_pending_messages(source, self.batch_size)

                await asyncio.sleep(self.check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"DLQ worker error: {e}", exc_info=True)
                await asyncio.sleep(self.check_interval)


# Utility functions
async def create_dlq(redis_pool, **kwargs) -> DeadLetterQueue:
    """Factory function to create DLQ instance"""
    return DeadLetterQueue(redis_pool, **kwargs)
