"""
Tests for Alert Manager
Tests alert routing, suppression rules, channel delivery, and statistics
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

# Import models and modules under test
from app.models import (
    AlertCreate, Alert, AlertBatch, AlertResponse,
    AlertSeverity, AlertType, NotificationChannel, DeliveryStatus,
    SuppressionRule, EscalationRule
)
from app.alert_manager import AlertManager
from app.alert_rules import AlertRulesEngine, SuppressionResult
from app.channels.base import BaseChannel, ChannelResult


# ========================================
# Fixtures
# ========================================

@pytest.fixture
def alert_manager():
    """Create a fresh AlertManager for each test"""
    manager = AlertManager()
    # Reset stats
    manager._stats.clear()
    manager._alerts.clear()
    manager._alert_history.clear()
    return manager


@pytest.fixture
def rules_engine():
    """Create a fresh AlertRulesEngine for each test"""
    engine = AlertRulesEngine()
    engine.clear_history()
    return engine


@pytest.fixture
def sample_alert_create():
    """Create a sample AlertCreate for testing"""
    return AlertCreate(
        alert_type=AlertType.TRADE,
        severity=AlertSeverity.MEDIUM,
        title="Test Trade Alert",
        message="BUY 0.5 BTC at $42,000",
        source="test",
        metadata={"symbol": "BTCUSDT", "action": "BUY"}
    )


@pytest.fixture
def sample_critical_alert():
    """Create a critical alert for testing"""
    return AlertCreate(
        alert_type=AlertType.SYSTEM,
        severity=AlertSeverity.CRITICAL,
        title="System Down",
        message="Trading engine is not responding",
        source="system-monitor",
        metadata={"service": "trading-engine"}
    )


@pytest.fixture
def mock_channel():
    """Create a mock channel for testing"""
    channel = MagicMock(spec=BaseChannel)
    channel.name = "mock"
    channel.is_enabled.return_value = True
    channel.send_with_retry = AsyncMock(return_value=ChannelResult(
        success=True,
        channel="mock",
        message_id="msg-123",
        delivery_time_ms=50
    ))
    channel.health_check = AsyncMock(return_value=True)
    channel.get_health_status.return_value = {
        "channel": "mock",
        "enabled": True,
        "healthy": True,
        "total_sent": 10,
        "total_failed": 0,
        "rate_limit_remaining": 55
    }
    return channel


# ========================================
# AlertManager Tests
# ========================================

class TestAlertManager:
    """Tests for AlertManager class"""

    @pytest.mark.asyncio
    async def test_send_alert_basic(self, alert_manager, sample_alert_create):
        """Test basic alert sending"""
        # Mock the telegram channel
        with patch.object(alert_manager._telegram, 'is_enabled', return_value=True):
            with patch.object(alert_manager._telegram, 'send_with_retry', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = ChannelResult(
                    success=True,
                    channel="telegram",
                    message_id="123"
                )

                response = await alert_manager.send_alert(sample_alert_create)

                assert response.success is True
                assert response.alert_id is not None
                assert "telegram" in response.channels_sent

    @pytest.mark.asyncio
    async def test_send_alert_suppressed(self, alert_manager, sample_alert_create):
        """Test alert suppression for duplicates"""
        # First alert should go through
        with patch.object(alert_manager._telegram, 'is_enabled', return_value=True):
            with patch.object(alert_manager._telegram, 'send_with_retry', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = ChannelResult(success=True, channel="telegram")

                response1 = await alert_manager.send_alert(sample_alert_create)
                assert response1.success is True
                assert response1.suppressed is False

                # Second identical alert within 5 minutes should be suppressed
                response2 = await alert_manager.send_alert(sample_alert_create)
                assert response2.suppressed is True
                assert "Duplicate" in response2.suppression_reason

    @pytest.mark.asyncio
    async def test_send_batch_alerts(self, alert_manager):
        """Test batch alert sending"""
        alerts = [
            AlertCreate(
                alert_type=AlertType.TRADE,
                severity=AlertSeverity.MEDIUM,
                title=f"Trade {i}",
                message=f"Test trade {i}",
                source="test"
            )
            for i in range(3)
        ]
        batch = AlertBatch(alerts=alerts)

        with patch.object(alert_manager._telegram, 'is_enabled', return_value=True):
            with patch.object(alert_manager._telegram, 'send_with_retry', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = ChannelResult(success=True, channel="telegram")

                responses = await alert_manager.send_batch(batch)

                assert len(responses) == 3
                assert all(r.success for r in responses)

    @pytest.mark.asyncio
    async def test_critical_alert_routing(self, alert_manager, sample_critical_alert):
        """Test critical alerts route to multiple channels"""
        with patch.object(alert_manager._telegram, 'is_enabled', return_value=True):
            with patch.object(alert_manager._email, 'is_enabled', return_value=True):
                with patch.object(alert_manager._slack, 'is_enabled', return_value=True):
                    with patch.object(alert_manager._telegram, 'send_with_retry', new_callable=AsyncMock) as mock_tg:
                        with patch.object(alert_manager._email, 'send_with_retry', new_callable=AsyncMock) as mock_email:
                            with patch.object(alert_manager._slack, 'send_with_retry', new_callable=AsyncMock) as mock_slack:
                                mock_tg.return_value = ChannelResult(success=True, channel="telegram")
                                mock_email.return_value = ChannelResult(success=True, channel="email")
                                mock_slack.return_value = ChannelResult(success=True, channel="slack")

                                response = await alert_manager.send_alert(sample_critical_alert)

                                assert response.success is True
                                assert "telegram" in response.channels_sent
                                assert "email" in response.channels_sent
                                assert "slack" in response.channels_sent

    @pytest.mark.asyncio
    async def test_acknowledge_alert(self, alert_manager, sample_alert_create):
        """Test alert acknowledgment"""
        with patch.object(alert_manager._telegram, 'is_enabled', return_value=True):
            with patch.object(alert_manager._telegram, 'send_with_retry', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = ChannelResult(success=True, channel="telegram")

                response = await alert_manager.send_alert(sample_alert_create)
                alert_id = response.alert_id

                # Acknowledge the alert
                success = alert_manager.acknowledge_alert(
                    alert_id=alert_id,
                    acknowledged_by="test_user",
                    notes="Reviewed and addressed"
                )

                assert success is True

                # Verify alert is acknowledged
                alert = alert_manager.get_alert(alert_id)
                assert alert.is_acknowledged is True
                assert alert.acknowledged_by == "test_user"

    @pytest.mark.asyncio
    async def test_get_alerts_filtering(self, alert_manager):
        """Test alert retrieval with filtering"""
        # Create alerts with different severities
        severities = [AlertSeverity.CRITICAL, AlertSeverity.HIGH, AlertSeverity.MEDIUM]

        with patch.object(alert_manager._telegram, 'is_enabled', return_value=True):
            with patch.object(alert_manager._telegram, 'send_with_retry', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = ChannelResult(success=True, channel="telegram")

                for i, sev in enumerate(severities):
                    alert = AlertCreate(
                        alert_type=AlertType.TRADE,
                        severity=sev,
                        title=f"Alert {i}",
                        message=f"Test {i}",
                        source="test",
                        metadata={"index": i}  # Make each unique
                    )
                    await alert_manager.send_alert(alert)

        # Filter by severity
        critical_alerts = alert_manager.get_alerts(severity=AlertSeverity.CRITICAL)
        assert len(critical_alerts) == 1

        high_alerts = alert_manager.get_alerts(severity=AlertSeverity.HIGH)
        assert len(high_alerts) == 1

    @pytest.mark.asyncio
    async def test_get_active_alerts(self, alert_manager, sample_alert_create):
        """Test getting unacknowledged alerts"""
        with patch.object(alert_manager._telegram, 'is_enabled', return_value=True):
            with patch.object(alert_manager._telegram, 'send_with_retry', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = ChannelResult(success=True, channel="telegram")

                # Create and acknowledge first alert
                response1 = await alert_manager.send_alert(sample_alert_create)

                # Create second alert with different metadata
                alert2 = AlertCreate(
                    alert_type=AlertType.RISK,
                    severity=AlertSeverity.HIGH,
                    title="Risk Alert",
                    message="Test risk",
                    source="test"
                )
                response2 = await alert_manager.send_alert(alert2)

                # Acknowledge first alert
                alert_manager.acknowledge_alert(response1.alert_id, "user")

                # Get active alerts
                active = alert_manager.get_active_alerts()
                assert len(active) == 1
                assert active[0].id == response2.alert_id

    @pytest.mark.asyncio
    async def test_get_stats(self, alert_manager):
        """Test alert statistics"""
        with patch.object(alert_manager._telegram, 'is_enabled', return_value=True):
            with patch.object(alert_manager._telegram, 'send_with_retry', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = ChannelResult(
                    success=True,
                    channel="telegram",
                    delivery_time_ms=100
                )

                # Send various alerts
                for i in range(5):
                    alert = AlertCreate(
                        alert_type=AlertType.TRADE,
                        severity=AlertSeverity.MEDIUM,
                        title=f"Trade {i}",
                        message=f"Test {i}",
                        source="test",
                        metadata={"unique_id": str(uuid.uuid4())}
                    )
                    await alert_manager.send_alert(alert)

        stats = alert_manager.get_stats(period_hours=24)
        assert stats.total_alerts == 5
        assert stats.alerts_by_severity.get("MEDIUM", 0) == 5
        assert stats.delivery_success_rate == 100.0

    @pytest.mark.asyncio
    async def test_channel_failure_handling(self, alert_manager, sample_alert_create):
        """Test handling of channel failures"""
        with patch.object(alert_manager._telegram, 'is_enabled', return_value=True):
            with patch.object(alert_manager._telegram, 'send_with_retry', new_callable=AsyncMock) as mock_send:
                # Simulate failure
                mock_send.return_value = ChannelResult(
                    success=False,
                    channel="telegram",
                    error_message="API error"
                )

                response = await alert_manager.send_alert(sample_alert_create)

                assert response.success is False
                assert "telegram" in response.channels_failed

    @pytest.mark.asyncio
    async def test_test_channel(self, alert_manager):
        """Test channel testing functionality"""
        with patch.object(alert_manager._telegram, 'is_enabled', return_value=True):
            with patch.object(alert_manager._telegram, 'send_with_retry', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = ChannelResult(
                    success=True,
                    channel="telegram"
                )

                result = await alert_manager.test_channel("telegram")
                assert result.success is True


# ========================================
# AlertRulesEngine Tests
# ========================================

class TestAlertRulesEngine:
    """Tests for AlertRulesEngine class"""

    def test_dedup_rule(self, rules_engine):
        """Test deduplication rule"""
        alert = Alert(
            id=str(uuid.uuid4()),
            alert_type=AlertType.TRADE,
            severity=AlertSeverity.MEDIUM,
            title="Test Alert",
            message="Test message",
            source="test"
        )

        # First alert should not be suppressed
        result1 = rules_engine.should_suppress(alert)
        assert result1.suppressed is False

        # Same alert should be suppressed
        result2 = rules_engine.should_suppress(alert)
        assert result2.suppressed is True
        assert "Duplicate" in result2.reason

    def test_throttle_rule(self, rules_engine):
        """Test throttle rule"""
        # Send max allowed alerts
        for i in range(3):
            alert = Alert(
                id=str(uuid.uuid4()),
                alert_type=AlertType.TRADE,
                severity=AlertSeverity.MEDIUM,
                title="Trade Alert",
                message=f"Trade {i}",
                source="test",
                metadata={"unique": i}  # Make unique for dedup
            )
            result = rules_engine.should_suppress(alert)
            assert result.suppressed is False

        # Next alert should be throttled
        alert = Alert(
            id=str(uuid.uuid4()),
            alert_type=AlertType.TRADE,
            severity=AlertSeverity.MEDIUM,
            title="Trade Alert",
            message="Trade 4",
            source="test",
            metadata={"unique": 4}
        )
        result = rules_engine.should_suppress(alert)
        assert result.suppressed is True
        assert "Throttled" in result.reason

    def test_quiet_hours_rule(self, rules_engine):
        """Test quiet hours rule"""
        # Enable quiet hours
        quiet_rule = SuppressionRule(
            id="quiet_test",
            name="Test quiet hours",
            enabled=True,
            rule_type="quiet_hours",
            severities=[AlertSeverity.LOW, AlertSeverity.INFO],
            conditions={
                "start": "00:00",
                "end": "23:59",  # Always quiet for test
                "timezone": "UTC"
            }
        )
        rules_engine._suppression_rules.append(quiet_rule)

        alert = Alert(
            id=str(uuid.uuid4()),
            alert_type=AlertType.TRADE,
            severity=AlertSeverity.LOW,
            title="Low Priority",
            message="Test",
            source="test"
        )

        result = rules_engine.should_suppress(alert)
        assert result.suppressed is True
        assert "Quiet hours" in result.reason

    def test_critical_not_suppressed_in_quiet_hours(self, rules_engine):
        """Test critical alerts not suppressed during quiet hours"""
        quiet_rule = SuppressionRule(
            id="quiet_test",
            name="Test quiet hours",
            enabled=True,
            rule_type="quiet_hours",
            severities=[AlertSeverity.LOW, AlertSeverity.INFO],
            conditions={
                "start": "00:00",
                "end": "23:59",
                "timezone": "UTC"
            }
        )
        rules_engine._suppression_rules.append(quiet_rule)

        alert = Alert(
            id=str(uuid.uuid4()),
            alert_type=AlertType.SYSTEM,
            severity=AlertSeverity.CRITICAL,
            title="Critical Alert",
            message="System down",
            source="test"
        )

        result = rules_engine.should_suppress(alert)
        assert result.suppressed is False

    def test_update_suppression_rules(self, rules_engine):
        """Test updating suppression rules"""
        new_rules = [
            SuppressionRule(
                id="custom1",
                name="Custom rule",
                enabled=True,
                rule_type="custom",
                conditions={}
            )
        ]

        rules_engine.update_suppression_rules(new_rules)
        rules = rules_engine.get_suppression_rules()

        assert len(rules) == 1
        assert rules[0].id == "custom1"

    def test_user_preferences(self, rules_engine):
        """Test user preference handling"""
        rules_engine.set_user_preferences("user1", {
            "channels": {
                "CRITICAL": ["telegram", "email", "sms"],
                "HIGH": ["telegram"]
            },
            "muted_types": ["MARKET"]
        })

        prefs = rules_engine.get_user_preferences("user1")
        assert prefs is not None
        assert "telegram" in prefs["channels"]["CRITICAL"]

        channels = rules_engine.get_user_channels("user1", AlertSeverity.CRITICAL)
        assert channels == ["telegram", "email", "sms"]

        is_muted = rules_engine.is_alert_type_muted("user1", AlertType.MARKET)
        assert is_muted is True

    def test_suppression_stats(self, rules_engine):
        """Test suppression statistics"""
        # Generate some alerts
        for i in range(5):
            alert = Alert(
                id=str(uuid.uuid4()),
                alert_type=AlertType.TRADE,
                severity=AlertSeverity.MEDIUM,
                title=f"Alert {i}",
                message=f"Test {i}",
                source="test",
                metadata={"index": i}
            )
            rules_engine.should_suppress(alert)

        stats = rules_engine.get_suppression_stats()
        assert stats["total_alerts_tracked"] >= 5
        assert stats["suppression_rules_count"] > 0


# ========================================
# Channel Tests
# ========================================

class TestChannelBase:
    """Tests for base channel functionality"""

    def test_rate_limit_check(self, mock_channel):
        """Test rate limiting check"""
        channel = BaseChannel("test", rate_limit=5)

        # Should allow sends up to rate limit
        for _ in range(5):
            assert channel._check_rate_limit() is True
            channel._record_send()

        # Should deny after rate limit
        assert channel._check_rate_limit() is False

    def test_rate_limit_remaining(self, mock_channel):
        """Test rate limit remaining calculation"""
        channel = BaseChannel("test", rate_limit=10)

        # Record some sends
        for _ in range(3):
            channel._record_send()

        remaining = channel.get_rate_limit_remaining()
        assert remaining == 7

    def test_health_status(self, mock_channel):
        """Test health status reporting"""
        channel = BaseChannel("test")
        channel._total_sent = 50
        channel._total_failed = 5
        channel._last_success = datetime.utcnow()

        status = channel.get_health_status()
        assert status["total_sent"] == 50
        assert status["total_failed"] == 5
        assert status["success_rate"] > 90

    def test_reset_stats(self, mock_channel):
        """Test stats reset"""
        channel = BaseChannel("test")
        channel._total_sent = 100
        channel._total_failed = 10

        channel.reset_stats()

        assert channel._total_sent == 0
        assert channel._total_failed == 0


# ========================================
# Integration Tests
# ========================================

class TestAlertFlowIntegration:
    """Integration tests for complete alert flow"""

    @pytest.mark.asyncio
    async def test_trade_alert_flow(self, alert_manager):
        """Test complete trade alert flow"""
        with patch.object(alert_manager._telegram, 'is_enabled', return_value=True):
            with patch.object(alert_manager._telegram, 'send_with_retry', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = ChannelResult(success=True, channel="telegram")

                response = await alert_manager.send_trade_alert(
                    action="BUY",
                    symbol="BTCUSDT",
                    quantity=0.5,
                    price=42000.0,
                    stop_loss=40000.0,
                    take_profit=45000.0,
                    confidence=0.85
                )

                assert response.success is True
                assert response.alert_id is not None

                # Verify alert was stored
                alert = alert_manager.get_alert(response.alert_id)
                assert alert is not None
                assert alert.alert_type == AlertType.TRADE

    @pytest.mark.asyncio
    async def test_risk_alert_flow(self, alert_manager):
        """Test complete risk alert flow"""
        with patch.object(alert_manager._telegram, 'is_enabled', return_value=True):
            with patch.object(alert_manager._email, 'is_enabled', return_value=True):
                with patch.object(alert_manager._telegram, 'send_with_retry', new_callable=AsyncMock) as mock_tg:
                    with patch.object(alert_manager._email, 'send_with_retry', new_callable=AsyncMock) as mock_email:
                        mock_tg.return_value = ChannelResult(success=True, channel="telegram")
                        mock_email.return_value = ChannelResult(success=True, channel="email")

                        response = await alert_manager.send_risk_alert(
                            alert_type="Drawdown Limit",
                            message="Portfolio drawdown exceeded 10%",
                            severity=AlertSeverity.HIGH,
                            current_value=12.5,
                            threshold=10.0
                        )

                        assert response.success is True
                        assert len(response.channels_sent) >= 1

    @pytest.mark.asyncio
    async def test_system_alert_flow(self, alert_manager):
        """Test complete system alert flow"""
        with patch.object(alert_manager._telegram, 'is_enabled', return_value=True):
            with patch.object(alert_manager._email, 'is_enabled', return_value=True):
                with patch.object(alert_manager._slack, 'is_enabled', return_value=True):
                    with patch.object(alert_manager._telegram, 'send_with_retry', new_callable=AsyncMock) as mock_tg:
                        with patch.object(alert_manager._email, 'send_with_retry', new_callable=AsyncMock) as mock_email:
                            with patch.object(alert_manager._slack, 'send_with_retry', new_callable=AsyncMock) as mock_slack:
                                mock_tg.return_value = ChannelResult(success=True, channel="telegram")
                                mock_email.return_value = ChannelResult(success=True, channel="email")
                                mock_slack.return_value = ChannelResult(success=True, channel="slack")

                                response = await alert_manager.send_system_alert(
                                    service_name="trading-engine",
                                    status="DOWN",
                                    error_message="Connection timeout"
                                )

                                assert response.success is True
                                # CRITICAL system alerts should go to multiple channels

    @pytest.mark.asyncio
    async def test_daily_summary_flow(self, alert_manager):
        """Test daily summary alert flow"""
        with patch.object(alert_manager._email, 'is_enabled', return_value=True):
            with patch.object(alert_manager._email, 'send_with_retry', new_callable=AsyncMock) as mock_email:
                mock_email.return_value = ChannelResult(success=True, channel="email")

                response = await alert_manager.send_daily_summary(
                    total_pnl=1250.50,
                    total_trades=15,
                    win_rate=0.65,
                    best_trade=500.0,
                    worst_trade=-200.0,
                    balance=50000.0
                )

                assert response.success is True


# ========================================
# Edge Case Tests
# ========================================

class TestEdgeCases:
    """Tests for edge cases and error handling"""

    @pytest.mark.asyncio
    async def test_no_enabled_channels(self, alert_manager, sample_alert_create):
        """Test handling when no channels are enabled"""
        with patch.object(alert_manager._telegram, 'is_enabled', return_value=False):
            with patch.object(alert_manager._email, 'is_enabled', return_value=False):
                with patch.object(alert_manager._slack, 'is_enabled', return_value=False):
                    with patch.object(alert_manager._sms, 'is_enabled', return_value=False):
                        response = await alert_manager.send_alert(sample_alert_create)

                        assert response.success is False
                        assert "No enabled channels" in response.message

    @pytest.mark.asyncio
    async def test_all_channels_fail(self, alert_manager, sample_critical_alert):
        """Test handling when all channel deliveries fail"""
        with patch.object(alert_manager._telegram, 'is_enabled', return_value=True):
            with patch.object(alert_manager._email, 'is_enabled', return_value=True):
                with patch.object(alert_manager._slack, 'is_enabled', return_value=True):
                    with patch.object(alert_manager._telegram, 'send_with_retry', new_callable=AsyncMock) as mock_tg:
                        with patch.object(alert_manager._email, 'send_with_retry', new_callable=AsyncMock) as mock_email:
                            with patch.object(alert_manager._slack, 'send_with_retry', new_callable=AsyncMock) as mock_slack:
                                mock_tg.return_value = ChannelResult(success=False, channel="telegram", error_message="Error")
                                mock_email.return_value = ChannelResult(success=False, channel="email", error_message="Error")
                                mock_slack.return_value = ChannelResult(success=False, channel="slack", error_message="Error")

                                response = await alert_manager.send_alert(sample_critical_alert)

                                assert response.success is False
                                assert len(response.channels_failed) == 3

    def test_acknowledge_nonexistent_alert(self, alert_manager):
        """Test acknowledging alert that doesn't exist"""
        success = alert_manager.acknowledge_alert(
            alert_id="nonexistent-id",
            acknowledged_by="user"
        )
        assert success is False

    def test_get_nonexistent_alert(self, alert_manager):
        """Test getting alert that doesn't exist"""
        alert = alert_manager.get_alert("nonexistent-id")
        assert alert is None

    @pytest.mark.asyncio
    async def test_partial_channel_success(self, alert_manager, sample_critical_alert):
        """Test partial success when some channels fail"""
        with patch.object(alert_manager._telegram, 'is_enabled', return_value=True):
            with patch.object(alert_manager._email, 'is_enabled', return_value=True):
                with patch.object(alert_manager._slack, 'is_enabled', return_value=True):
                    with patch.object(alert_manager._telegram, 'send_with_retry', new_callable=AsyncMock) as mock_tg:
                        with patch.object(alert_manager._email, 'send_with_retry', new_callable=AsyncMock) as mock_email:
                            with patch.object(alert_manager._slack, 'send_with_retry', new_callable=AsyncMock) as mock_slack:
                                mock_tg.return_value = ChannelResult(success=True, channel="telegram")
                                mock_email.return_value = ChannelResult(success=False, channel="email", error_message="Error")
                                mock_slack.return_value = ChannelResult(success=True, channel="slack")

                                response = await alert_manager.send_alert(sample_critical_alert)

                                # Should be success if at least one channel succeeded
                                assert response.success is True
                                assert "telegram" in response.channels_sent
                                assert "slack" in response.channels_sent
                                assert "email" in response.channels_failed
