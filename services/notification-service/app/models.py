"""
Notification Service Models
Pydantic models for alerts, configurations, and channel management
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, List, Any
from datetime import datetime
from enum import Enum
import uuid


class AlertSeverity(str, Enum):
    """Alert severity levels for routing decisions"""
    CRITICAL = "CRITICAL"  # System failures, large losses, emergency stops
    HIGH = "HIGH"          # Risk limit breaches, significant events
    MEDIUM = "MEDIUM"      # Trade completions, position changes
    LOW = "LOW"            # Daily summaries, informational
    INFO = "INFO"          # Routine operations


class AlertType(str, Enum):
    """Types of alerts for categorization"""
    TRADE = "TRADE"              # Trade entry, exit, position size change
    RISK = "RISK"                # Limit breach, high correlation, drawdown
    SYSTEM = "SYSTEM"            # Service down, API error, connection loss
    PERFORMANCE = "PERFORMANCE"  # Profit target hit, loss limit, summary
    MARKET = "MARKET"            # Volatility spike, price movement, news


class NotificationChannel(str, Enum):
    """Available notification channels"""
    TELEGRAM = "telegram"
    EMAIL = "email"
    SLACK = "slack"
    SMS = "sms"
    DASHBOARD = "dashboard"


class DeliveryStatus(str, Enum):
    """Alert delivery status"""
    PENDING = "PENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    SUPPRESSED = "SUPPRESSED"
    BATCHED = "BATCHED"


# ========================================
# Alert Models
# ========================================

class AlertCreate(BaseModel):
    """Model for creating a new alert"""
    alert_type: AlertType = Field(
        description="Type of alert (TRADE, RISK, SYSTEM, PERFORMANCE, MARKET)"
    )
    severity: AlertSeverity = Field(
        description="Severity level (CRITICAL, HIGH, MEDIUM, LOW, INFO)"
    )
    title: str = Field(
        min_length=1,
        max_length=200,
        description="Alert title"
    )
    message: str = Field(
        min_length=1,
        max_length=4000,
        description="Alert message body"
    )
    source: str = Field(
        default="notification-service",
        description="Source service that generated the alert"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional metadata for the alert"
    )
    channels: Optional[List[NotificationChannel]] = Field(
        default=None,
        description="Override default channels for this alert"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "alert_type": "TRADE",
                "severity": "MEDIUM",
                "title": "Trade Executed",
                "message": "BUY 0.5 BTC at $42,000",
                "source": "trading-engine",
                "metadata": {
                    "symbol": "BTCUSDT",
                    "action": "BUY",
                    "quantity": 0.5,
                    "price": 42000.0
                }
            }
        }


class Alert(BaseModel):
    """Full alert model with all fields"""
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique alert identifier"
    )
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    source: str
    metadata: Optional[Dict[str, Any]] = None
    channels: List[str] = Field(
        default_factory=list,
        description="Channels this alert was sent to"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Alert creation timestamp"
    )
    acknowledged_at: Optional[datetime] = Field(
        default=None,
        description="When the alert was acknowledged"
    )
    acknowledged_by: Optional[str] = Field(
        default=None,
        description="Who acknowledged the alert"
    )
    is_acknowledged: bool = Field(
        default=False,
        description="Whether alert has been acknowledged"
    )
    delivery_statuses: Dict[str, DeliveryStatus] = Field(
        default_factory=dict,
        description="Delivery status per channel"
    )
    dedup_key: Optional[str] = Field(
        default=None,
        description="Key used for deduplication"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "alert_type": "TRADE",
                "severity": "MEDIUM",
                "title": "Trade Executed",
                "message": "BUY 0.5 BTC at $42,000",
                "source": "trading-engine",
                "metadata": {"symbol": "BTCUSDT"},
                "channels": ["telegram", "email"],
                "created_at": "2024-01-15T10:30:00Z",
                "is_acknowledged": False,
                "delivery_statuses": {
                    "telegram": "DELIVERED",
                    "email": "SENT"
                }
            }
        }


class AlertBatch(BaseModel):
    """Batch of alerts to send together"""
    alerts: List[AlertCreate] = Field(
        min_length=1,
        max_length=100,
        description="List of alerts to send"
    )
    batch_id: Optional[str] = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Batch identifier"
    )


class AlertAcknowledge(BaseModel):
    """Model for acknowledging an alert"""
    acknowledged_by: str = Field(
        min_length=1,
        max_length=100,
        description="User or system that acknowledged the alert"
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Optional notes about the acknowledgment"
    )


# ========================================
# Alert History and Statistics
# ========================================

class AlertHistory(BaseModel):
    """Record of alert delivery attempt"""
    alert_id: str
    channel: str
    sent_at: datetime
    status: DeliveryStatus
    delivery_time_ms: Optional[int] = Field(
        default=None,
        description="Time taken to deliver in milliseconds"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if delivery failed"
    )
    retry_count: int = Field(
        default=0,
        description="Number of retry attempts"
    )


class AlertStats(BaseModel):
    """Alert statistics"""
    total_alerts: int = 0
    alerts_by_severity: Dict[str, int] = Field(default_factory=dict)
    alerts_by_type: Dict[str, int] = Field(default_factory=dict)
    alerts_by_channel: Dict[str, int] = Field(default_factory=dict)
    delivery_success_rate: float = Field(
        default=0.0,
        description="Percentage of successful deliveries"
    )
    avg_delivery_time_ms: float = Field(
        default=0.0,
        description="Average delivery time in milliseconds"
    )
    suppressed_count: int = 0
    failed_count: int = 0
    period_start: datetime
    period_end: datetime


# ========================================
# Channel Configuration Models
# ========================================

class ChannelConfig(BaseModel):
    """Configuration for a notification channel"""
    channel_type: NotificationChannel
    enabled: bool = True
    credentials: Dict[str, Any] = Field(
        default_factory=dict,
        description="Channel-specific credentials"
    )
    rate_limit: int = Field(
        default=60,
        description="Max messages per minute"
    )
    retry_attempts: int = Field(
        default=3,
        description="Number of retry attempts"
    )
    retry_delay_seconds: float = Field(
        default=1.0,
        description="Initial retry delay"
    )
    fallback_channel: Optional[NotificationChannel] = Field(
        default=None,
        description="Fallback channel if this one fails"
    )


class ChannelStatus(BaseModel):
    """Current status of a notification channel"""
    channel: NotificationChannel
    enabled: bool
    healthy: bool
    last_message_at: Optional[datetime] = None
    messages_sent_today: int = 0
    failures_today: int = 0
    rate_limit_remaining: int = 60
    error_message: Optional[str] = None


# ========================================
# Alert Rules Models
# ========================================

class SuppressionRule(BaseModel):
    """Rule for suppressing alerts"""
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4())
    )
    name: str
    enabled: bool = True
    rule_type: str = Field(
        description="Type: dedup, throttle, quiet_hours, custom"
    )
    alert_types: Optional[List[AlertType]] = Field(
        default=None,
        description="Alert types this rule applies to (None = all)"
    )
    severities: Optional[List[AlertSeverity]] = Field(
        default=None,
        description="Severities this rule applies to (None = all)"
    )
    conditions: Dict[str, Any] = Field(
        default_factory=dict,
        description="Rule-specific conditions"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": "rule-001",
                "name": "Dedup identical alerts",
                "enabled": True,
                "rule_type": "dedup",
                "alert_types": None,
                "severities": None,
                "conditions": {
                    "window_seconds": 300
                }
            }
        }


class EscalationRule(BaseModel):
    """Rule for escalating unacknowledged alerts"""
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4())
    )
    name: str
    enabled: bool = True
    severity: AlertSeverity
    timeout_seconds: int = Field(
        description="Seconds to wait before escalation"
    )
    escalate_to_channel: NotificationChannel
    notify_contact: Optional[str] = Field(
        default=None,
        description="Contact to notify on escalation"
    )


class AlertRules(BaseModel):
    """Collection of alert rules"""
    suppression_rules: List[SuppressionRule] = Field(default_factory=list)
    escalation_rules: List[EscalationRule] = Field(default_factory=list)


class AlertRulesUpdate(BaseModel):
    """Update request for alert rules"""
    suppression_rules: Optional[List[SuppressionRule]] = None
    escalation_rules: Optional[List[EscalationRule]] = None


# ========================================
# Alert Configuration Models
# ========================================

class UserAlertPreferences(BaseModel):
    """User-specific alert preferences"""
    user_id: str
    preferred_channels: Dict[AlertSeverity, List[NotificationChannel]] = Field(
        default_factory=dict,
        description="Channel preferences by severity"
    )
    muted_alert_types: List[AlertType] = Field(
        default_factory=list,
        description="Alert types to mute"
    )
    custom_thresholds: Dict[str, float] = Field(
        default_factory=dict,
        description="Custom thresholds for alerts"
    )
    schedule: Optional[str] = Field(
        default="24/7",
        description="Alert schedule: 24/7, working_hours, custom"
    )
    working_hours_start: Optional[str] = Field(
        default="09:00",
        description="Start of working hours"
    )
    working_hours_end: Optional[str] = Field(
        default="17:00",
        description="End of working hours"
    )
    timezone: str = Field(
        default="UTC",
        description="User's timezone"
    )


class AlertConfigResponse(BaseModel):
    """Response model for alert configuration"""
    channels: Dict[str, bool] = Field(
        description="Enabled status of each channel"
    )
    routing: Dict[str, List[str]] = Field(
        description="Channel routing by severity"
    )
    suppression: Dict[str, Any] = Field(
        description="Suppression settings"
    )
    escalation: Dict[str, Any] = Field(
        description="Escalation settings"
    )
    quiet_hours: Dict[str, Any] = Field(
        description="Quiet hours settings"
    )


class AlertConfigUpdate(BaseModel):
    """Update request for alert configuration"""
    telegram_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    slack_enabled: Optional[bool] = None
    sms_enabled: Optional[bool] = None
    critical_channels: Optional[str] = None
    high_channels: Optional[str] = None
    medium_channels: Optional[str] = None
    low_channels: Optional[str] = None
    info_channels: Optional[str] = None
    dedup_window_seconds: Optional[int] = None
    throttle_max_per_hour: Optional[int] = None
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None


# ========================================
# Response Models
# ========================================

class AlertResponse(BaseModel):
    """Standard response for alert operations"""
    success: bool
    alert_id: Optional[str] = None
    message: str
    channels_sent: List[str] = Field(default_factory=list)
    channels_failed: List[str] = Field(default_factory=list)
    suppressed: bool = False
    suppression_reason: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AlertListResponse(BaseModel):
    """Response for listing alerts"""
    success: bool
    alerts: List[Alert]
    total: int
    page: int = 1
    page_size: int = 50
    has_more: bool = False


class ChannelTestResult(BaseModel):
    """Result of testing a notification channel"""
    channel: str
    success: bool
    response_time_ms: int
    error_message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
