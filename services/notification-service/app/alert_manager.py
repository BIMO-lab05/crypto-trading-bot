"""
Alert Manager
Central orchestration for multi-channel alert routing, delivery, and tracking
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from collections import defaultdict
import uuid

from .config import config, AlertSeverity, AlertType, NotificationChannel
from .models import (
    Alert, AlertCreate, AlertBatch, AlertResponse, AlertHistory,
    AlertStats, ChannelStatus, DeliveryStatus
)
from .alert_rules import alert_rules_engine, SuppressionResult
from .channels import (
    TelegramClient, EmailClient, SlackClient, SMSClient,
    BaseChannel, ChannelResult
)

logger = logging.getLogger(__name__)


class AlertManager:
    """
    Central alert management system

    Responsibilities:
    - Route alerts to appropriate channels based on severity
    - Apply suppression and throttling rules
    - Handle escalation for unacknowledged alerts
    - Track delivery status and statistics
    - Manage batch/digest delivery for low-priority alerts
    """

    def __init__(self):
        """Initialize the Alert Manager"""
        # Initialize channel clients
        self._telegram = TelegramClient()
        self._email = EmailClient()
        self._slack = SlackClient()
        self._sms = SMSClient()

        # Channel registry
        self._channels: Dict[str, BaseChannel] = {
            "telegram": self._telegram,
            "email": self._email,
            "slack": self._slack,
            "sms": self._sms,
        }

        # Alert storage (in production, this would be database-backed)
        self._alerts: Dict[str, Alert] = {}
        self._alert_history: List[AlertHistory] = []

        # Batch queue for low priority alerts
        self._batch_queue: List[Alert] = []
        self._batch_task: Optional[asyncio.Task] = None

        # Statistics
        self._stats = defaultdict(int)
        self._stats_start = datetime.utcnow()

        logger.info("Alert Manager initialized")

    async def start(self):
        """Start background tasks"""
        # Start batch processing task
        self._batch_task = asyncio.create_task(self._process_batch_queue())
        logger.info("Alert Manager background tasks started")

    async def stop(self):
        """Stop background tasks"""
        if self._batch_task:
            self._batch_task.cancel()
            try:
                await self._batch_task
            except asyncio.CancelledError:
                pass
        logger.info("Alert Manager stopped")

    async def send_alert(self, alert_create: AlertCreate) -> AlertResponse:
        """
        Send an alert through the appropriate channels

        This is the main entry point for sending alerts.

        Args:
            alert_create: Alert creation data

        Returns:
            AlertResponse with delivery status
        """
        # Create full alert object
        alert = Alert(
            id=str(uuid.uuid4()),
            alert_type=alert_create.alert_type,
            severity=alert_create.severity,
            title=alert_create.title,
            message=alert_create.message,
            source=alert_create.source,
            metadata=alert_create.metadata,
            created_at=datetime.utcnow()
        )

        logger.info(f"Processing alert: {alert.id} - {alert.severity.value} - {alert.title}")

        # Check suppression rules
        suppression = alert_rules_engine.should_suppress(alert)
        if suppression.suppressed:
            self._stats["suppressed"] += 1
            return AlertResponse(
                success=True,
                alert_id=alert.id,
                message="Alert suppressed",
                suppressed=True,
                suppression_reason=suppression.reason
            )

        # Determine channels
        if alert_create.channels:
            channels = [ch.value for ch in alert_create.channels]
        else:
            channels = config.get_channels_for_severity(alert.severity)

        # Filter to enabled channels
        enabled_channels = [
            ch for ch in channels
            if config.is_channel_enabled(ch)
        ]

        if not enabled_channels:
            logger.warning(f"No enabled channels for alert {alert.id}")
            return AlertResponse(
                success=False,
                alert_id=alert.id,
                message="No enabled channels available"
            )

        # Check if this should be batched (LOW priority email)
        if (
            alert.severity == AlertSeverity.LOW and
            enabled_channels == ["email"]
        ):
            return await self._add_to_batch(alert)

        # Send to channels
        channels_sent = []
        channels_failed = []

        for channel_name in enabled_channels:
            if channel_name == "dashboard":
                # Dashboard notifications are stored but not sent
                alert.delivery_statuses["dashboard"] = DeliveryStatus.DELIVERED
                channels_sent.append("dashboard")
                continue

            result = await self._send_to_channel(alert, channel_name)

            if result.success:
                channels_sent.append(channel_name)
                alert.delivery_statuses[channel_name] = DeliveryStatus.DELIVERED
                self._record_history(alert.id, channel_name, result)
            else:
                channels_failed.append(channel_name)
                alert.delivery_statuses[channel_name] = DeliveryStatus.FAILED
                self._record_history(alert.id, channel_name, result)

        # Store alert
        alert.channels = channels_sent
        self._alerts[alert.id] = alert
        self._stats["total"] += 1
        self._stats[f"severity_{alert.severity.value}"] += 1

        success = len(channels_sent) > 0

        return AlertResponse(
            success=success,
            alert_id=alert.id,
            message="Alert sent" if success else "Alert delivery failed",
            channels_sent=channels_sent,
            channels_failed=channels_failed
        )

    async def send_batch(self, batch: AlertBatch) -> List[AlertResponse]:
        """
        Send multiple alerts

        Args:
            batch: Batch of alerts

        Returns:
            List of AlertResponse for each alert
        """
        responses = []
        for alert_create in batch.alerts:
            response = await self.send_alert(alert_create)
            responses.append(response)
        return responses

    async def _send_to_channel(
        self,
        alert: Alert,
        channel_name: str
    ) -> ChannelResult:
        """
        Send alert to a specific channel

        Args:
            alert: The alert to send
            channel_name: Name of the channel

        Returns:
            ChannelResult with delivery status
        """
        channel = self._channels.get(channel_name)
        if not channel:
            return ChannelResult(
                success=False,
                channel=channel_name,
                error_message=f"Unknown channel: {channel_name}"
            )

        # Prepare metadata for channel
        metadata = alert.metadata or {}
        metadata["severity"] = alert.severity.value
        metadata["alert_type"] = alert.alert_type.value
        metadata["source"] = alert.source

        try:
            result = await channel.send_with_retry(
                message=alert.message,
                title=alert.title,
                metadata=metadata
            )
            return result

        except Exception as e:
            logger.error(f"Error sending to {channel_name}: {e}")
            return ChannelResult(
                success=False,
                channel=channel_name,
                error_message=str(e)
            )

    async def _add_to_batch(self, alert: Alert) -> AlertResponse:
        """
        Add alert to batch queue for later delivery

        Args:
            alert: The alert to batch

        Returns:
            AlertResponse indicating batched status
        """
        self._batch_queue.append(alert)
        alert.delivery_statuses["email"] = DeliveryStatus.BATCHED
        self._alerts[alert.id] = alert

        logger.debug(f"Alert {alert.id} added to batch queue. Queue size: {len(self._batch_queue)}")

        return AlertResponse(
            success=True,
            alert_id=alert.id,
            message="Alert queued for batch delivery",
            channels_sent=[],
            channels_failed=[]
        )

    async def _process_batch_queue(self):
        """Background task to process batch queue"""
        while True:
            try:
                await asyncio.sleep(config.email_batch_interval)

                if self._batch_queue:
                    logger.info(f"Processing batch queue: {len(self._batch_queue)} alerts")
                    await self._send_batch_digest()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing batch queue: {e}")

    async def _send_batch_digest(self):
        """Send batched alerts as digest"""
        if not self._batch_queue:
            return

        # Collect alerts
        alerts = self._batch_queue.copy()
        self._batch_queue.clear()

        # Build digest content
        digest_parts = []
        for alert in alerts:
            digest_parts.append(f"**{alert.title}**\n{alert.message}\n")

        digest_message = "\n---\n".join(digest_parts)

        # Send via email
        result = await self._email.send(
            message=digest_message,
            title=f"Alert Digest ({len(alerts)} alerts)",
            metadata={"html": False}
        )

        # Update alert statuses
        status = DeliveryStatus.DELIVERED if result.success else DeliveryStatus.FAILED
        for alert in alerts:
            alert.delivery_statuses["email"] = status

        logger.info(f"Batch digest sent: {len(alerts)} alerts, success={result.success}")

    def _record_history(
        self,
        alert_id: str,
        channel: str,
        result: ChannelResult
    ):
        """Record delivery attempt in history"""
        history = AlertHistory(
            alert_id=alert_id,
            channel=channel,
            sent_at=datetime.utcnow(),
            status=DeliveryStatus.DELIVERED if result.success else DeliveryStatus.FAILED,
            delivery_time_ms=result.delivery_time_ms,
            error_message=result.error_message,
            retry_count=result.retry_count
        )
        self._alert_history.append(history)

        # Keep only last 1000 entries
        if len(self._alert_history) > 1000:
            self._alert_history = self._alert_history[-1000:]

    # ========================================
    # Alert Retrieval
    # ========================================

    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Get alert by ID"""
        return self._alerts.get(alert_id)

    def get_alerts(
        self,
        limit: int = 50,
        offset: int = 0,
        severity: Optional[AlertSeverity] = None,
        alert_type: Optional[AlertType] = None,
        acknowledged: Optional[bool] = None
    ) -> List[Alert]:
        """
        Get alerts with filtering

        Args:
            limit: Maximum alerts to return
            offset: Number of alerts to skip
            severity: Filter by severity
            alert_type: Filter by type
            acknowledged: Filter by acknowledgment status

        Returns:
            List of matching alerts
        """
        alerts = list(self._alerts.values())

        # Apply filters
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        if alert_type:
            alerts = [a for a in alerts if a.alert_type == alert_type]
        if acknowledged is not None:
            alerts = [a for a in alerts if a.is_acknowledged == acknowledged]

        # Sort by creation time (newest first)
        alerts.sort(key=lambda a: a.created_at, reverse=True)

        # Apply pagination
        return alerts[offset:offset + limit]

    def get_active_alerts(self) -> List[Alert]:
        """Get unacknowledged alerts"""
        return [
            a for a in self._alerts.values()
            if not a.is_acknowledged
        ]

    # ========================================
    # Alert Acknowledgment
    # ========================================

    def acknowledge_alert(
        self,
        alert_id: str,
        acknowledged_by: str,
        notes: Optional[str] = None
    ) -> bool:
        """
        Acknowledge an alert

        Args:
            alert_id: Alert ID
            acknowledged_by: User/system acknowledging
            notes: Optional notes

        Returns:
            True if acknowledged, False if not found
        """
        alert = self._alerts.get(alert_id)
        if not alert:
            return False

        alert.is_acknowledged = True
        alert.acknowledged_at = datetime.utcnow()
        alert.acknowledged_by = acknowledged_by

        if notes and alert.metadata:
            alert.metadata["acknowledgment_notes"] = notes

        logger.info(f"Alert {alert_id} acknowledged by {acknowledged_by}")
        return True

    # ========================================
    # Channel Management
    # ========================================

    async def get_channel_status(self, channel_name: str) -> ChannelStatus:
        """Get status of a specific channel"""
        channel = self._channels.get(channel_name)
        if not channel:
            return ChannelStatus(
                channel=NotificationChannel(channel_name),
                enabled=False,
                healthy=False,
                error_message="Unknown channel"
            )

        is_healthy = await channel.health_check()
        health_data = channel.get_health_status()

        return ChannelStatus(
            channel=NotificationChannel(channel_name),
            enabled=channel.is_enabled(),
            healthy=is_healthy,
            last_message_at=health_data.get("last_success"),
            messages_sent_today=health_data.get("total_sent", 0),
            failures_today=health_data.get("total_failed", 0),
            rate_limit_remaining=health_data.get("rate_limit_remaining", 0),
            error_message=None if is_healthy else "Health check failed"
        )

    async def get_all_channel_status(self) -> Dict[str, ChannelStatus]:
        """Get status of all channels"""
        statuses = {}
        for name in self._channels:
            statuses[name] = await self.get_channel_status(name)
        return statuses

    async def test_channel(self, channel_name: str) -> ChannelResult:
        """
        Send test message to a channel

        Args:
            channel_name: Name of the channel to test

        Returns:
            ChannelResult with test status
        """
        channel = self._channels.get(channel_name)
        if not channel:
            return ChannelResult(
                success=False,
                channel=channel_name,
                error_message="Unknown channel"
            )

        if not channel.is_enabled():
            return ChannelResult(
                success=False,
                channel=channel_name,
                error_message="Channel not enabled"
            )

        return await channel.send_with_retry(
            message="This is a test notification from your Trading Bot. "
                    "If you receive this, the channel is working correctly!",
            title="Test Notification",
            metadata={"is_test": True}
        )

    # ========================================
    # Statistics
    # ========================================

    def get_stats(
        self,
        period_hours: int = 24
    ) -> AlertStats:
        """
        Get alert statistics

        Args:
            period_hours: Hours to include in stats

        Returns:
            AlertStats with aggregated metrics
        """
        cutoff = datetime.utcnow() - timedelta(hours=period_hours)

        # Filter alerts in period
        period_alerts = [
            a for a in self._alerts.values()
            if a.created_at >= cutoff
        ]

        # Count by severity
        by_severity: Dict[str, int] = defaultdict(int)
        for alert in period_alerts:
            by_severity[alert.severity.value] += 1

        # Count by type
        by_type: Dict[str, int] = defaultdict(int)
        for alert in period_alerts:
            by_type[alert.alert_type.value] += 1

        # Count by channel
        by_channel: Dict[str, int] = defaultdict(int)
        for alert in period_alerts:
            for ch in alert.channels:
                by_channel[ch] += 1

        # Calculate delivery stats from history
        period_history = [
            h for h in self._alert_history
            if h.sent_at >= cutoff
        ]

        successful = sum(1 for h in period_history if h.status == DeliveryStatus.DELIVERED)
        total_deliveries = len(period_history)
        success_rate = (successful / total_deliveries * 100) if total_deliveries > 0 else 100.0

        avg_delivery_time = 0.0
        if period_history:
            times = [h.delivery_time_ms for h in period_history if h.delivery_time_ms]
            avg_delivery_time = sum(times) / len(times) if times else 0.0

        return AlertStats(
            total_alerts=len(period_alerts),
            alerts_by_severity=dict(by_severity),
            alerts_by_type=dict(by_type),
            alerts_by_channel=dict(by_channel),
            delivery_success_rate=success_rate,
            avg_delivery_time_ms=avg_delivery_time,
            suppressed_count=self._stats.get("suppressed", 0),
            failed_count=total_deliveries - successful,
            period_start=cutoff,
            period_end=datetime.utcnow()
        )

    def get_history(
        self,
        limit: int = 100,
        channel: Optional[str] = None
    ) -> List[AlertHistory]:
        """
        Get delivery history

        Args:
            limit: Maximum entries to return
            channel: Filter by channel

        Returns:
            List of AlertHistory entries
        """
        history = self._alert_history.copy()

        if channel:
            history = [h for h in history if h.channel == channel]

        # Sort by time (newest first)
        history.sort(key=lambda h: h.sent_at, reverse=True)

        return history[:limit]

    # ========================================
    # Specialized Alert Methods
    # ========================================

    async def send_trade_alert(
        self,
        action: str,
        symbol: str,
        quantity: float,
        price: float,
        **kwargs
    ) -> AlertResponse:
        """Send a trade execution alert"""
        metadata = {
            "action": action,
            "symbol": symbol,
            "quantity": quantity,
            "price": price,
            **kwargs
        }

        return await self.send_alert(AlertCreate(
            alert_type=AlertType.TRADE,
            severity=AlertSeverity.MEDIUM,
            title=f"Trade Executed: {action} {symbol}",
            message=f"{action} {quantity:.6f} {symbol} @ ${price:,.2f}",
            source="trading-engine",
            metadata=metadata
        ))

    async def send_risk_alert(
        self,
        alert_type: str,
        message: str,
        severity: AlertSeverity = AlertSeverity.HIGH,
        **kwargs
    ) -> AlertResponse:
        """Send a risk management alert"""
        return await self.send_alert(AlertCreate(
            alert_type=AlertType.RISK,
            severity=severity,
            title=f"Risk Alert: {alert_type}",
            message=message,
            source="risk-manager",
            metadata=kwargs
        ))

    async def send_system_alert(
        self,
        service_name: str,
        status: str,
        error_message: Optional[str] = None,
        **kwargs
    ) -> AlertResponse:
        """Send a system status alert"""
        severity = AlertSeverity.CRITICAL if status.upper() in ["DOWN", "ERROR"] else AlertSeverity.HIGH

        message = f"Service: {service_name}\nStatus: {status}"
        if error_message:
            message += f"\nError: {error_message}"

        return await self.send_alert(AlertCreate(
            alert_type=AlertType.SYSTEM,
            severity=severity,
            title=f"System Alert: {service_name}",
            message=message,
            source="system-monitor",
            metadata={"service": service_name, "status": status, "error": error_message, **kwargs}
        ))

    async def send_daily_summary(
        self,
        total_pnl: float,
        total_trades: int,
        win_rate: float,
        balance: float,
        **kwargs
    ) -> AlertResponse:
        """Send daily performance summary"""
        emoji = "+" if total_pnl >= 0 else "-"

        message = f"""
Performance Summary:
- Total P&L: ${total_pnl:,.2f}
- Trades: {total_trades}
- Win Rate: {win_rate:.1%}
- Balance: ${balance:,.2f}
"""

        return await self.send_alert(AlertCreate(
            alert_type=AlertType.PERFORMANCE,
            severity=AlertSeverity.LOW,
            title=f"{emoji} Daily Summary: ${total_pnl:,.2f}",
            message=message,
            source="post-trade-analysis",
            metadata={"total_pnl": total_pnl, "total_trades": total_trades, **kwargs}
        ))


# Create global alert manager instance
alert_manager = AlertManager()
