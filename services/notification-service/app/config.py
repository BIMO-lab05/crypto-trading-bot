"""
Notification Service Configuration
Handles email, Telegram, Slack, and SMS notification settings
Enhanced with multi-channel routing and alert management
"""

from pydantic_settings import BaseSettings
from pydantic import AliasChoices, Field, model_validator
from typing import List
from enum import Enum


class AlertSeverity(str, Enum):
    """Alert severity levels for routing decisions"""

    CRITICAL = "CRITICAL"  # System failures, large losses, emergency stops
    HIGH = "HIGH"  # Risk limit breaches, significant events
    MEDIUM = "MEDIUM"  # Trade completions, position changes
    LOW = "LOW"  # Daily summaries, informational
    INFO = "INFO"  # Routine operations


class AlertType(str, Enum):
    """Types of alerts for categorization"""

    TRADE = "TRADE"  # Trade entry, exit, position size change
    RISK = "RISK"  # Limit breach, high correlation, drawdown
    SYSTEM = "SYSTEM"  # Service down, API error, connection loss
    PERFORMANCE = "PERFORMANCE"  # Profit target hit, loss limit, summary
    MARKET = "MARKET"  # Volatility spike, price movement, news


class NotificationChannel(str, Enum):
    """Available notification channels"""

    TELEGRAM = "telegram"
    EMAIL = "email"
    SLACK = "slack"
    SMS = "sms"
    DASHBOARD = "dashboard"


class NotificationConfig(BaseSettings):
    """Notification service configuration with multi-channel support"""

    # Service settings
    service_name: str = "notification-service"
    service_version: str = "2.0.0"
    host: str = "0.0.0.0"
    port: int = 8006

    # Database settings for alert storage
    # No hardcoded fallback — silent fall-through to localhost has caused
    # outages where the service connected to a stale/empty DB without warning.
    # If the env var is missing the service must fail at first DB use, not silently succeed.
    database_url: str = Field(
        default="",
        description="PostgreSQL connection string for alert storage. REQUIRED via DATABASE_URL env var.",
    )

    # Redis settings for rate limiting and caching
    redis_url: str = Field(
        default="",
        description="Redis connection string. REQUIRED via REDIS_URL env var.",
    )

    # ========================================
    # Email settings (SMTP)
    # ========================================
    email_enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: str = ""  # Comma-separated list
    email_batch_interval: int = Field(
        default=300, description="Batch email interval in seconds for LOW priority"
    )

    # ========================================
    # Telegram settings
    # ========================================
    telegram_enabled: bool = False
    # BL-03 follow-up (Phase 2): AliasChoices lets the field accept either
    # TELEGRAM_BOT_TOKEN (production / dev .env file) OR TEST_TELEGRAM_BOT_TOKEN
    # (CI workflow secret + integration suite). Without this, the BL-03 compose
    # rename (TELEGRAM_TEST_* → TEST_TELEGRAM_*) only delivered the env var to
    # the container — Pydantic still read TELEGRAM_BOT_TOKEN, so CI saw an
    # empty token and the test still failed identically. AliasChoices preserves
    # the primary TELEGRAM_BOT_TOKEN lookup so `services/notification-service/.env`
    # in dev is unaffected.
    telegram_bot_token: str = Field(
        default="",
        validation_alias=AliasChoices("TELEGRAM_BOT_TOKEN", "TEST_TELEGRAM_BOT_TOKEN"),
    )
    telegram_chat_id: str = Field(
        default="",
        validation_alias=AliasChoices("TELEGRAM_CHAT_ID", "TEST_TELEGRAM_CHAT_ID"),
    )
    telegram_rate_limit: int = Field(default=20, description="Max messages per minute")
    telegram_retry_attempts: int = Field(
        default=3, description="Number of retry attempts"
    )
    telegram_retry_delay: float = Field(
        default=1.0, description="Initial retry delay in seconds"
    )

    # CD-01 — Phase 2 INFRA-01 notification verification
    # - "" (default, production): live API behavior preserved
    # - "record": write would-be sends to tests/.notifications.log instead of POSTing
    # - "live":   force live POST even in test contexts (CI uses this with TEST_TELEGRAM_*)
    notification_test_mode: str = Field(
        default="",
        description="record|live; empty string = default production behavior",
    )
    notification_record_path: str = Field(
        default="tests/.notifications.log",
        description="Path the record-mode writer appends JSON lines to",
    )

    # ========================================
    # Slack settings (NEW)
    # ========================================
    slack_enabled: bool = False
    slack_webhook_url: str = Field(default="", description="Slack webhook URL")
    slack_channel_critical: str = Field(
        default="#trading-critical", description="Channel for critical alerts"
    )
    slack_channel_alerts: str = Field(
        default="#trading-alerts", description="Channel for general alerts"
    )
    slack_channel_performance: str = Field(
        default="#bimo-performance",
        description="Channel for daily/weekly performance digests",
    )
    slack_bot_token: str = Field(
        default="", description="Slack bot token for interactive features"
    )

    # ========================================
    # SMS settings (NEW - Twilio)
    # ========================================
    sms_enabled: bool = False
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    sms_recipient_numbers: str = Field(
        default="", description="Comma-separated list of phone numbers"
    )

    # ========================================
    # Alert routing rules
    # ========================================
    # Default channel preferences by severity
    critical_channels: str = Field(
        default="telegram,email,slack", description="Channels for CRITICAL alerts"
    )
    high_channels: str = Field(
        default="telegram,email", description="Channels for HIGH alerts"
    )
    medium_channels: str = Field(
        default="telegram", description="Channels for MEDIUM alerts"
    )
    low_channels: str = Field(
        default="email", description="Channels for LOW alerts (batched)"
    )
    info_channels: str = Field(
        default="dashboard", description="Channels for INFO alerts"
    )

    # ========================================
    # Alert suppression rules
    # ========================================
    dedup_window_seconds: int = Field(
        default=300, description="Deduplicate identical alerts within this window"
    )
    throttle_max_per_hour: int = Field(
        default=3, description="Max alerts of same type per hour"
    )
    quiet_hours_enabled: bool = False
    quiet_hours_start: str = Field(
        default="22:00", description="Start of quiet hours (24h format)"
    )
    quiet_hours_end: str = Field(
        default="08:00", description="End of quiet hours (24h format)"
    )
    quiet_hours_timezone: str = Field(
        default="UTC", description="Timezone for quiet hours"
    )

    # ========================================
    # Escalation rules
    # ========================================
    critical_ack_timeout: int = Field(
        default=300, description="Seconds to wait for CRITICAL ack before SMS"
    )
    system_down_escalation: int = Field(
        default=600, description="Seconds of downtime before emergency escalation"
    )
    emergency_contact: str = Field(
        default="", description="Emergency contact phone number"
    )

    # ========================================
    # Legacy alert settings (backward compatibility)
    # ========================================
    alert_on_trade: bool = True
    alert_on_profit: bool = True
    alert_on_loss: bool = True
    alert_on_daily_limit: bool = True
    alert_on_error: bool = True
    alert_on_startup: bool = True

    # Alert thresholds
    min_profit_alert: float = 10.0  # Alert on profit > $10
    min_loss_alert: float = 10.0  # Alert on loss > $10

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra environment variables not defined in model

    @model_validator(mode="after")
    def _validate_enabled_channels_have_creds(self):
        """
        Fail-fast at startup if a channel is enabled but its credentials are
        empty. Audit 2026-04-27: prior incident shipped with telegram_enabled=True
        but an empty bot token, so the service silently dropped every alert while
        returning HTTP 200.
        """
        problems = []
        if self.telegram_enabled and not (
            self.telegram_bot_token and self.telegram_chat_id
        ):
            problems.append(
                "telegram_enabled=True but TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is empty"
            )
        if self.email_enabled and not (
            self.smtp_username and self.smtp_password and self.email_to
        ):
            problems.append(
                "email_enabled=True but SMTP_USERNAME / SMTP_PASSWORD / EMAIL_TO is empty"
            )
        if self.slack_enabled and not self.slack_webhook_url:
            problems.append("slack_enabled=True but SLACK_WEBHOOK_URL is empty")
        if self.sms_enabled and not (
            self.twilio_account_sid
            and self.twilio_auth_token
            and self.twilio_phone_number
        ):
            problems.append("sms_enabled=True but Twilio credentials are incomplete")
        if problems:
            raise ValueError(
                "Notification config validation failed:\n  - "
                + "\n  - ".join(problems)
                + "\nFix the env vars or disable the channel."
            )
        return self

    def get_channels_for_severity(self, severity: AlertSeverity) -> List[str]:
        """Get list of channels for a given severity level"""
        channel_map = {
            AlertSeverity.CRITICAL: self.critical_channels,
            AlertSeverity.HIGH: self.high_channels,
            AlertSeverity.MEDIUM: self.medium_channels,
            AlertSeverity.LOW: self.low_channels,
            AlertSeverity.INFO: self.info_channels,
        }
        channels_str = channel_map.get(severity, self.medium_channels)
        return [ch.strip() for ch in channels_str.split(",") if ch.strip()]

    def is_channel_enabled(self, channel: str) -> bool:
        """Check if a notification channel is enabled"""
        channel_status = {
            "telegram": self.telegram_enabled,
            "email": self.email_enabled,
            "slack": self.slack_enabled,
            "sms": self.sms_enabled,
            "dashboard": True,  # Dashboard is always enabled
        }
        return channel_status.get(channel.lower(), False)


# Create global config instance
config = NotificationConfig()
