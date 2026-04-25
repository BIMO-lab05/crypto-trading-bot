"""
Enhanced Email Client
Provides HTML templates, batch digest mode, and priority headers
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate
from datetime import datetime
from typing import Optional, Dict, Any, List
import asyncio
from collections import deque

from .base import BaseChannel, ChannelResult
from ..config import config

logger = logging.getLogger(__name__)


class EmailClient(BaseChannel):
    """
    Enhanced Email notification client

    Features:
    - HTML templates for each alert type
    - Inline charts/graphs capability
    - Batch digest mode (hourly/daily)
    - Priority headers for email clients
    - Multiple recipient support
    """

    def __init__(self):
        """Initialize Email client with configuration"""
        super().__init__(
            name="email",
            rate_limit=60,
            retry_attempts=3,
            retry_delay=2.0
        )

        self.enabled = config.email_enabled
        self.smtp_host = config.smtp_host
        self.smtp_port = config.smtp_port
        self.username = config.smtp_username
        self.password = config.smtp_password
        self.from_email = config.email_from
        self.to_emails = [
            e.strip() for e in config.email_to.split(",")
            if e.strip()
        ]

        # Batch queue for LOW priority emails
        self._batch_queue: deque = deque(maxlen=100)
        self._batch_interval = config.email_batch_interval
        self._last_batch_sent: Optional[datetime] = None

        if self.enabled and self.to_emails:
            logger.info(f"Email client initialized: {self.from_email} -> {self.to_emails}")
        elif self.enabled:
            logger.warning("Email enabled but missing recipients")

    def is_enabled(self) -> bool:
        """Check if email is enabled and configured"""
        return (
            self.enabled and
            bool(self.username) and
            bool(self.password) and
            bool(self.to_emails)
        )

    async def send(
        self,
        message: str,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ChannelResult:
        """
        Send an email

        Args:
            message: Email body content
            title: Email subject
            metadata: Additional options:
                - html: Whether message is HTML
                - priority: 1 (high), 3 (normal), 5 (low)
                - recipients: Override default recipients
                - template: Template name to use

        Returns:
            ChannelResult with success status
        """
        if not self.is_enabled():
            return ChannelResult(
                success=False,
                channel=self.name,
                error_message="Email not enabled or not configured"
            )

        metadata = metadata or {}
        is_html = metadata.get("html", False)
        priority = metadata.get("priority", 3)
        recipients = metadata.get("recipients", self.to_emails)
        template = metadata.get("template")

        # Use template if specified
        if template:
            message = self._apply_template(template, message, metadata)
            is_html = True

        subject = f"[Trading Bot] {title}" if title else "[Trading Bot] Notification"

        # Run SMTP in thread pool (it's blocking)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self._send_email_sync,
            subject,
            message,
            is_html,
            priority,
            recipients
        )

        return result

    def _send_email_sync(
        self,
        subject: str,
        body: str,
        is_html: bool,
        priority: int,
        recipients: List[str]
    ) -> ChannelResult:
        """
        Synchronous email sending (runs in thread pool)

        Args:
            subject: Email subject
            body: Email body
            is_html: Whether body is HTML
            priority: Email priority 1-5
            recipients: List of recipient addresses

        Returns:
            ChannelResult with success status
        """
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.from_email
            msg['To'] = ", ".join(recipients)
            msg['Subject'] = subject
            msg['Date'] = formatdate(localtime=True)

            # Set priority headers
            if priority == 1:
                msg['X-Priority'] = '1'
                msg['X-MSMail-Priority'] = 'High'
                msg['Importance'] = 'High'
            elif priority == 5:
                msg['X-Priority'] = '5'
                msg['X-MSMail-Priority'] = 'Low'
                msg['Importance'] = 'Low'

            # Attach body
            mime_type = 'html' if is_html else 'plain'
            msg.attach(MIMEText(body, mime_type, 'utf-8'))

            # Connect and send
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)

            logger.info(f"Email sent: {subject}")
            return ChannelResult(
                success=True,
                channel=self.name,
                metadata={"recipients": recipients, "subject": subject}
            )

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"Email authentication failed: {e}")
            return ChannelResult(
                success=False,
                channel=self.name,
                error_message=f"Authentication failed: {e}"
            )
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            return ChannelResult(
                success=False,
                channel=self.name,
                error_message=f"SMTP error: {e}"
            )
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return ChannelResult(
                success=False,
                channel=self.name,
                error_message=str(e)
            )

    def add_to_batch(self, alert_data: Dict[str, Any]):
        """
        Add an alert to the batch queue

        Args:
            alert_data: Alert data to queue
        """
        self._batch_queue.append({
            "data": alert_data,
            "timestamp": datetime.utcnow()
        })
        logger.debug(f"Alert added to batch queue. Queue size: {len(self._batch_queue)}")

    async def send_batch_digest(self) -> ChannelResult:
        """
        Send all queued alerts as a digest email

        Returns:
            ChannelResult with success status
        """
        if not self._batch_queue:
            return ChannelResult(
                success=True,
                channel=self.name,
                metadata={"message": "No alerts in batch queue"}
            )

        # Collect all queued alerts
        alerts = list(self._batch_queue)
        self._batch_queue.clear()

        # Build digest HTML
        html_content = self._build_digest_html(alerts)

        result = await self.send(
            html_content,
            title=f"Alert Digest - {len(alerts)} alerts",
            metadata={
                "html": True,
                "priority": 5  # Low priority for digests
            }
        )

        if result.success:
            self._last_batch_sent = datetime.utcnow()

        return result

    def _build_digest_html(self, alerts: List[Dict[str, Any]]) -> str:
        """
        Build HTML digest from queued alerts

        Args:
            alerts: List of alert data

        Returns:
            HTML string
        """
        html = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .header { background: #2c3e50; color: white; padding: 20px; border-radius: 5px; }
        .alert { border: 1px solid #ddd; margin: 10px 0; padding: 15px; border-radius: 5px; }
        .alert-critical { border-left: 4px solid #e74c3c; }
        .alert-high { border-left: 4px solid #e67e22; }
        .alert-medium { border-left: 4px solid #f1c40f; }
        .alert-low { border-left: 4px solid #3498db; }
        .timestamp { color: #7f8c8d; font-size: 12px; }
        .footer { margin-top: 20px; color: #7f8c8d; font-size: 12px; }
    </style>
</head>
<body>
    <div class="header">
        <h2>Trading Bot Alert Digest</h2>
        <p>You have {count} alerts</p>
    </div>
""".format(count=len(alerts))

        for item in alerts:
            alert = item.get("data", {})
            timestamp = item.get("timestamp", datetime.utcnow())
            severity = alert.get("severity", "LOW").lower()

            html += f"""
    <div class="alert alert-{severity}">
        <strong>{alert.get('title', 'Alert')}</strong>
        <p>{alert.get('message', '')}</p>
        <span class="timestamp">{timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC</span>
    </div>
"""

        html += """
    <div class="footer">
        <p>This digest was generated automatically by your Trading Bot.</p>
        <p>Manage your notification preferences in the dashboard.</p>
    </div>
</body>
</html>
"""
        return html

    def _apply_template(
        self,
        template_name: str,
        content: str,
        metadata: Dict[str, Any]
    ) -> str:
        """
        Apply an HTML template to content

        Args:
            template_name: Name of the template
            content: Content to insert
            metadata: Additional template variables

        Returns:
            Formatted HTML string
        """
        templates = {
            "critical_alert": self._template_critical,
            "trade_alert": self._template_trade,
            "risk_alert": self._template_risk,
            "daily_summary": self._template_daily_summary,
        }

        template_func = templates.get(template_name)
        if template_func:
            return template_func(content, metadata)

        # Default template
        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .content {{ padding: 20px; border: 1px solid #ddd; border-radius: 5px; }}
    </style>
</head>
<body>
    <div class="content">
        {content}
    </div>
</body>
</html>
"""

    def _template_critical(self, content: str, metadata: Dict[str, Any]) -> str:
        """Critical alert HTML template"""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 0; }}
        .banner {{ background: #e74c3c; color: white; padding: 30px; text-align: center; }}
        .banner h1 {{ margin: 0; font-size: 28px; }}
        .content {{ padding: 30px; }}
        .action-required {{ background: #fcf8e3; border: 1px solid #faebcc; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .footer {{ background: #f5f5f5; padding: 20px; text-align: center; color: #666; }}
    </style>
</head>
<body>
    <div class="banner">
        <h1>CRITICAL ALERT</h1>
    </div>
    <div class="content">
        {content}
        <div class="action-required">
            <strong>Immediate action may be required.</strong>
            <p>Please review this alert and take appropriate action.</p>
        </div>
    </div>
    <div class="footer">
        <p>This is an automated alert from your Trading Bot.</p>
        <p>Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
    </div>
</body>
</html>
"""

    def _template_trade(self, content: str, metadata: Dict[str, Any]) -> str:
        """Trade alert HTML template"""
        action = metadata.get("action", "TRADE")
        color = "#27ae60" if action.upper() == "BUY" else "#e74c3c"

        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 0; }}
        .header {{ background: {color}; color: white; padding: 20px; }}
        .content {{ padding: 30px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        td {{ padding: 10px; border-bottom: 1px solid #eee; }}
        .label {{ color: #666; width: 40%; }}
        .value {{ font-weight: bold; }}
        .footer {{ background: #f5f5f5; padding: 20px; text-align: center; color: #666; }}
    </style>
</head>
<body>
    <div class="header">
        <h2>Trade Executed: {action.upper()}</h2>
    </div>
    <div class="content">
        {content}
    </div>
    <div class="footer">
        <p>Trading Bot Notification | {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
    </div>
</body>
</html>
"""

    def _template_risk(self, content: str, metadata: Dict[str, Any]) -> str:
        """Risk alert HTML template"""
        severity = metadata.get("severity", "HIGH")
        colors = {
            "CRITICAL": "#e74c3c",
            "HIGH": "#e67e22",
            "MEDIUM": "#f1c40f",
            "LOW": "#3498db"
        }
        color = colors.get(severity, "#e67e22")

        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 0; }}
        .header {{ background: {color}; color: white; padding: 20px; }}
        .content {{ padding: 30px; }}
        .metric {{ display: inline-block; margin: 10px; padding: 15px; background: #f5f5f5; border-radius: 5px; }}
        .footer {{ background: #f5f5f5; padding: 20px; text-align: center; color: #666; }}
    </style>
</head>
<body>
    <div class="header">
        <h2>Risk Alert: {severity}</h2>
    </div>
    <div class="content">
        {content}
    </div>
    <div class="footer">
        <p>Risk Management System | {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
    </div>
</body>
</html>
"""

    def _template_daily_summary(self, content: str, metadata: Dict[str, Any]) -> str:
        """Daily summary HTML template"""
        total_pnl = metadata.get("total_pnl", 0)
        pnl_color = "#27ae60" if total_pnl >= 0 else "#e74c3c"

        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 0; }}
        .header {{ background: #2c3e50; color: white; padding: 30px; text-align: center; }}
        .pnl {{ font-size: 36px; color: {pnl_color}; margin: 10px 0; }}
        .content {{ padding: 30px; }}
        .stats {{ display: flex; justify-content: space-around; flex-wrap: wrap; }}
        .stat {{ text-align: center; padding: 20px; margin: 10px; background: #f5f5f5; border-radius: 5px; min-width: 120px; }}
        .stat-value {{ font-size: 24px; font-weight: bold; }}
        .stat-label {{ color: #666; margin-top: 5px; }}
        .footer {{ background: #f5f5f5; padding: 20px; text-align: center; color: #666; }}
    </style>
</head>
<body>
    <div class="header">
        <h2>Daily Trading Summary</h2>
        <div class="pnl">${total_pnl:,.2f}</div>
    </div>
    <div class="content">
        {content}
    </div>
    <div class="footer">
        <p>Generated on {datetime.utcnow().strftime('%Y-%m-%d')} | Trading Bot</p>
    </div>
</body>
</html>
"""

    async def health_check(self) -> bool:
        """
        Check SMTP server connectivity

        Returns:
            True if SMTP server is reachable
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
            logger.error(f"Email health check error: {e}")
            return False

    def _health_check_sync(self) -> bool:
        """Synchronous health check"""
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.noop()
                return True
        except Exception as e:
            logger.error(f"Email health check failed: {e}")
            return False

    def get_batch_queue_size(self) -> int:
        """Get current batch queue size"""
        return len(self._batch_queue)


# Create global email client instance
email_client = EmailClient()
