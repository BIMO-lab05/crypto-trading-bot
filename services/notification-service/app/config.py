"""
Notification Service Configuration
Handles email and Telegram notification settings
"""

from pydantic_settings import BaseSettings
from typing import Optional


class NotificationConfig(BaseSettings):
    """Notification service configuration"""

    # Service settings
    service_name: str = "notification-service"
    service_version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = 8007

    # Email settings (SMTP)
    email_enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: str = ""  # Comma-separated list

    # Telegram settings
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Alert settings
    alert_on_trade: bool = True
    alert_on_profit: bool = True
    alert_on_loss: bool = True
    alert_on_daily_limit: bool = True
    alert_on_error: bool = True
    alert_on_startup: bool = True

    # Alert thresholds
    min_profit_alert: float = 10.0  # Alert on profit > $10
    min_loss_alert: float = 10.0    # Alert on loss > $10

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Create global config instance
config = NotificationConfig()
