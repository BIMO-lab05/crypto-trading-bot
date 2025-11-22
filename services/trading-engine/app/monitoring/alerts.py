"""
Alerting Module for Trading Engine
Provides Slack and Email alerting functionality
"""

import os
import smtplib
import logging
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logging.warning("httpx not available - Slack alerts will be disabled")


logger = logging.getLogger(__name__)


class AlertLevel(str, Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class TradingAlert:
    """Trading-specific alert types"""
    DAILY_LOSS_LIMIT = "daily_loss_limit_reached"
    POSITION_SIZE_LIMIT = "position_size_limit_exceeded"
    TRADE_ERROR = "trade_execution_error"
    API_CONNECTION_FAILED = "api_connection_failed"
    DATABASE_ERROR = "database_error"
    EMERGENCY_STOP = "emergency_stop_triggered"
    UNUSUAL_ACTIVITY = "unusual_trading_activity"
    BALANCE_LOW = "account_balance_low"
    WINNING_STREAK = "winning_streak_detected"
    LOSING_STREAK = "losing_streak_detected"


async def send_slack_alert(
    message: str,
    level: AlertLevel = AlertLevel.INFO,
    title: Optional[str] = None,
    fields: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Send alert to Slack channel via webhook

    Args:
        message: Alert message
        level: Alert severity level
        title: Optional title for the alert
        fields: Optional dictionary of additional fields to include

    Returns:
        True if sent successfully, False otherwise
    """
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")

    if not webhook_url:
        logger.debug("SLACK_WEBHOOK_URL not configured - skipping Slack alert")
        return False

    if not HTTPX_AVAILABLE:
        logger.warning("httpx not available - cannot send Slack alert")
        return False

    # Color mapping for alert levels
    color_map = {
        AlertLevel.INFO: "#36a64f",      # Green
        AlertLevel.WARNING: "#ff9900",   # Orange
        AlertLevel.ERROR: "#ff0000",     # Red
        AlertLevel.CRITICAL: "#8b0000"   # Dark Red
    }

    # Build Slack message payload
    payload = {
        "text": title or f"[{level.value.upper()}] Trading Engine Alert",
        "attachments": [
            {
                "color": color_map.get(level, "#808080"),
                "text": message,
                "footer": "Trading Engine",
                "footer_icon": "https://platform.slack-edge.com/img/default_application_icon.png",
                "ts": int(datetime.utcnow().timestamp())
            }
        ]
    }

    # Add additional fields if provided
    if fields:
        attachment_fields = []
        for key, value in fields.items():
            attachment_fields.append({
                "title": key,
                "value": str(value),
                "short": True
            })
        payload["attachments"][0]["fields"] = attachment_fields

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                webhook_url,
                json=payload,
                timeout=10.0
            )
            response.raise_for_status()
            logger.info(f"Slack alert sent successfully: {title or message[:50]}")
            return True

    except Exception as e:
        logger.error(f"Failed to send Slack alert: {e}")
        return False


def send_email_alert(
    subject: str,
    message: str,
    level: AlertLevel = AlertLevel.INFO,
    html_message: Optional[str] = None
) -> bool:
    """
    Send email alert

    Args:
        subject: Email subject
        message: Email message (plain text)
        level: Alert severity level
        html_message: Optional HTML version of message

    Returns:
        True if sent successfully, False otherwise
    """
    # Check if email is enabled
    email_enabled = os.getenv("EMAIL_ALERT_ENABLED", "false").lower() == "true"
    if not email_enabled:
        logger.debug("Email alerts not enabled - skipping")
        return False

    # Get email configuration
    smtp_server = os.getenv("EMAIL_SMTP_SERVER")
    smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
    from_email = os.getenv("EMAIL_FROM")
    to_email = os.getenv("EMAIL_TO")
    password = os.getenv("EMAIL_PASSWORD")

    if not all([smtp_server, from_email, to_email, password]):
        logger.warning("Email configuration incomplete - cannot send alert")
        return False

    try:
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"[{level.value.upper()}] {subject}"
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Date'] = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")

        # Attach plain text
        text_part = MIMEText(message, 'plain')
        msg.attach(text_part)

        # Attach HTML if provided
        if html_message:
            html_part = MIMEText(html_message, 'html')
            msg.attach(html_part)

        # Send email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(from_email, password)
            server.send_message(msg)

        logger.info(f"Email alert sent successfully: {subject}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email alert: {e}")
        return False


async def send_trading_alert(
    alert_type: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    level: AlertLevel = AlertLevel.WARNING
) -> None:
    """
    Send trading-specific alert via all configured channels

    Args:
        alert_type: Type of trading alert (from TradingAlert)
        message: Alert message
        details: Optional dictionary with additional details
        level: Alert severity level
    """
    # Build alert title
    title = f"Trading Alert: {alert_type.replace('_', ' ').title()}"

    # Send to Slack
    await send_slack_alert(
        message=message,
        level=level,
        title=title,
        fields=details
    )

    # Send email for ERROR and CRITICAL levels
    if level in [AlertLevel.ERROR, AlertLevel.CRITICAL]:
        # Build HTML message
        html_message = f"""
        <html>
        <body>
            <h2 style="color: {'red' if level == AlertLevel.CRITICAL else 'orange'};">
                {title}
            </h2>
            <p>{message}</p>
        """

        if details:
            html_message += "<h3>Details:</h3><ul>"
            for key, value in details.items():
                html_message += f"<li><strong>{key}:</strong> {value}</li>"
            html_message += "</ul>"

        html_message += """
            <hr>
            <p style="color: gray; font-size: 12px;">
                This is an automated alert from the Trading Engine Service.
            </p>
        </body>
        </html>
        """

        send_email_alert(
            subject=title,
            message=message,
            level=level,
            html_message=html_message
        )


async def send_daily_loss_alert(
    current_loss: float,
    max_loss: float,
    percentage: float
) -> None:
    """Send alert when daily loss limit is reached"""
    await send_trading_alert(
        alert_type=TradingAlert.DAILY_LOSS_LIMIT,
        message=f"Daily loss limit reached: ${current_loss:.2f} ({percentage:.2f}% of capital)",
        details={
            "Current Loss": f"${current_loss:.2f}",
            "Max Allowed": f"${max_loss:.2f}",
            "Percentage": f"{percentage:.2f}%",
            "Action": "Trading automatically stopped"
        },
        level=AlertLevel.CRITICAL
    )


async def send_position_size_alert(
    symbol: str,
    position_size: float,
    max_size: float
) -> None:
    """Send alert when position size limit is exceeded"""
    await send_trading_alert(
        alert_type=TradingAlert.POSITION_SIZE_LIMIT,
        message=f"Position size limit exceeded for {symbol}",
        details={
            "Symbol": symbol,
            "Requested Size": f"${position_size:.2f}",
            "Max Allowed": f"${max_size:.2f}",
            "Action": "Trade rejected"
        },
        level=AlertLevel.WARNING
    )


async def send_trade_error_alert(
    symbol: str,
    error: str,
    order_details: Optional[Dict[str, Any]] = None
) -> None:
    """Send alert when trade execution fails"""
    details = {"Symbol": symbol, "Error": error}
    if order_details:
        details.update(order_details)

    await send_trading_alert(
        alert_type=TradingAlert.TRADE_ERROR,
        message=f"Trade execution failed for {symbol}: {error}",
        details=details,
        level=AlertLevel.ERROR
    )


async def send_api_connection_alert(
    service: str,
    error: str
) -> None:
    """Send alert when external API connection fails"""
    await send_trading_alert(
        alert_type=TradingAlert.API_CONNECTION_FAILED,
        message=f"Failed to connect to {service}: {error}",
        details={
            "Service": service,
            "Error": error,
            "Action": "Retrying connection"
        },
        level=AlertLevel.ERROR
    )


async def send_emergency_stop_alert(
    reason: str
) -> None:
    """Send alert when emergency stop is triggered"""
    await send_trading_alert(
        alert_type=TradingAlert.EMERGENCY_STOP,
        message=f"EMERGENCY STOP TRIGGERED: {reason}",
        details={
            "Reason": reason,
            "Action": "All trading halted immediately",
            "Next Steps": "Manual intervention required"
        },
        level=AlertLevel.CRITICAL
    )


async def send_performance_alert(
    alert_type: str,
    streak_count: int,
    total_pnl: float
) -> None:
    """Send alert for performance milestones (winning/losing streaks)"""
    level = AlertLevel.INFO if "winning" in alert_type else AlertLevel.WARNING

    await send_trading_alert(
        alert_type=alert_type,
        message=f"{alert_type.replace('_', ' ').title()}: {streak_count} trades",
        details={
            "Streak Count": streak_count,
            "Total P&L": f"${total_pnl:.2f}",
            "Recommendation": "Review strategy" if level == AlertLevel.WARNING else "Keep monitoring"
        },
        level=level
    )


async def send_balance_alert(
    current_balance: float,
    threshold: float
) -> None:
    """Send alert when account balance is low"""
    await send_trading_alert(
        alert_type=TradingAlert.BALANCE_LOW,
        message=f"Account balance below threshold: ${current_balance:.2f}",
        details={
            "Current Balance": f"${current_balance:.2f}",
            "Threshold": f"${threshold:.2f}",
            "Action": "Consider adding funds or reducing position sizes"
        },
        level=AlertLevel.WARNING
    )
