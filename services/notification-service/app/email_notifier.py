"""
Email notification handler using SMTP
Sends trading alerts via email
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, Optional
from .config import config

# Configure logging
logger = logging.getLogger(__name__)


class EmailNotifier:
    """Handles email notifications"""

    def __init__(self):
        """Initialize email notifier"""
        self.enabled = config.email_enabled
        self.smtp_host = config.smtp_host
        self.smtp_port = config.smtp_port
        self.username = config.smtp_username
        self.password = config.smtp_password
        self.from_email = config.email_from
        self.to_emails = [e.strip() for e in config.email_to.split(",") if e.strip()]

        if self.enabled:
            logger.info(f"Email notifications enabled: {self.from_email} -> {self.to_emails}")
        else:
            logger.info("Email notifications disabled")

    def send_email(self, subject: str, body: str, html: bool = False) -> bool:
        """
        Send email notification

        Args:
            subject: Email subject
            body: Email body content
            html: Whether body is HTML

        Returns:
            bool: Success status
        """
        if not self.enabled:
            logger.debug("Email notifications disabled, skipping")
            return False

        if not self.to_emails:
            logger.warning("No recipient email addresses configured")
            return False

        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = self.from_email
            msg['To'] = ", ".join(self.to_emails)
            msg['Subject'] = f"[Trading Bot] {subject}"

            # Add body
            mime_type = 'html' if html else 'plain'
            msg.attach(MIMEText(body, mime_type))

            # Connect and send
            logger.debug(f"Connecting to SMTP server {self.smtp_host}:{self.smtp_port}")
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)

            logger.info(f"Email sent successfully: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    def notify_trade_executed(self, trade: Dict) -> bool:
        """
        Notify about trade execution

        Args:
            trade: Trade details

        Returns:
            bool: Success status
        """
        if not config.alert_on_trade:
            return False

        subject = f"{trade['action']} {trade['symbol']}"

        body = f"""
Trading Bot Alert - Trade Executed

Action: {trade['action']}
Symbol: {trade['symbol']}
Quantity: {trade['quantity']:.6f}
Price: ${trade['price']:,.2f}
Total Value: ${trade['quantity'] * trade['price']:,.2f}
Time: {trade['timestamp']}

Signal Confidence: {trade.get('signal_confidence', 0):.1%}

Check your dashboard for more details.
"""

        return self.send_email(subject, body)

    def notify_profit_loss(self, trade: Dict, pnl: float) -> bool:
        """
        Notify about profit or loss

        Args:
            trade: Trade details
            pnl: Profit/loss amount

        Returns:
            bool: Success status
        """
        # Check thresholds
        if pnl > 0 and pnl < config.min_profit_alert:
            return False
        if pnl < 0 and abs(pnl) < config.min_loss_alert:
            return False

        # Check alert settings
        if pnl > 0 and not config.alert_on_profit:
            return False
        if pnl < 0 and not config.alert_on_loss:
            return False

        status = "Profit" if pnl > 0 else "Loss"
        emoji = "📈" if pnl > 0 else "📉"

        subject = f"{emoji} {status}: ${abs(pnl):.2f} on {trade['symbol']}"

        body = f"""
Trading Bot Alert - {status}

Symbol: {trade['symbol']}
Action: {trade['action']}
{status}: ${pnl:.2f}

Trade Details:
- Quantity: {trade['quantity']:.6f}
- Price: ${trade['price']:,.2f}
- Total Value: ${trade['quantity'] * trade['price']:,.2f}
- Time: {trade['timestamp']}

Your trading strategy is working!
"""

        return self.send_email(subject, body)

    def notify_daily_limit_reached(self, total_loss: float) -> bool:
        """
        Notify when daily loss limit is reached

        Args:
            total_loss: Total loss amount

        Returns:
            bool: Success status
        """
        if not config.alert_on_daily_limit:
            return False

        subject = "🚨 CRITICAL: Daily Loss Limit Reached"

        body = f"""
CRITICAL ALERT - Trading Bot Stopped

Your trading bot has reached the daily loss limit and has been automatically stopped.

Daily Loss: ${abs(total_loss):.2f}
Limit: 5% of portfolio

The bot will not execute any more trades today. This is a safety mechanism to protect your capital.

Action Required:
1. Review today's trades
2. Analyze what went wrong
3. Consider adjusting your strategy
4. Restart tomorrow with caution

Do not restart the bot until you understand what happened.
"""

        return self.send_email(subject, body)

    def notify_error(self, error_message: str, context: Optional[Dict] = None) -> bool:
        """
        Notify about system error

        Args:
            error_message: Error description
            context: Additional context

        Returns:
            bool: Success status
        """
        if not config.alert_on_error:
            return False

        subject = "⚠️ System Error"

        body = f"""
Trading Bot Error Alert

An error occurred in your trading bot:

Error: {error_message}

Time: {datetime.now().isoformat()}

"""

        if context:
            body += "\nContext:\n"
            for key, value in context.items():
                body += f"  {key}: {value}\n"

        body += """
The bot may have stopped. Please check the logs and restart if necessary.
"""

        return self.send_email(subject, body)

    def notify_startup(self, config_summary: Dict) -> bool:
        """
        Notify about bot startup

        Args:
            config_summary: Configuration summary

        Returns:
            bool: Success status
        """
        if not config.alert_on_startup:
            return False

        subject = "🚀 Trading Bot Started"

        body = f"""
Trading Bot Startup Notification

Your automated trading bot has started successfully.

Configuration:
- Mode: {config_summary.get('mode', 'Unknown')}
- Symbols: {', '.join(config_summary.get('symbols', []))}
- Check Interval: {config_summary.get('interval_minutes', 'N/A')} minutes
- Capital: ${config_summary.get('capital', 0):,.2f}

Risk Management:
- Max Position Size: {config_summary.get('max_position_pct', 0)}%
- Daily Loss Limit: {config_summary.get('daily_loss_limit', 0)}%
- Stop Loss: {config_summary.get('stop_loss_pct', 0)}%

The bot is now monitoring the markets and will execute trades automatically.

Time: {datetime.now().isoformat()}
"""

        return self.send_email(subject, body)


# Create global notifier instance
email_notifier = EmailNotifier()
