"""
Notification Service - Main Application
Provides REST API for sending alerts via email and Telegram
"""

from fastapi import FastAPI, HTTPException
import uuid
from pathlib import Path

# Import local utils module (works in Docker without shared directory)
try:
    from .utils.structured_logging import setup_logging, RequestContextLogger
    from .utils.graceful_shutdown import GracefulShutdownHandler
except ImportError:
    # Fallback: Try shared directory for local development
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))
    from utils.structured_logging import setup_logging, RequestContextLogger
    from utils.graceful_shutdown import GracefulShutdownHandler

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Optional
import logging
from datetime import datetime

from .config import config
from .email_notifier import email_notifier
from .telegram_notifier import telegram_notifier

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Notification Service",
    description="Sends trading alerts via email and Telegram",
    version=config.service_version
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request models
class TradeNotification(BaseModel):
    """Trade notification data"""
    action: str
    symbol: str
    quantity: float
    price: float
    timestamp: str
    signal_confidence: Optional[float] = 0.0


class ProfitLossNotification(BaseModel):
    """Profit/loss notification data"""
    trade: TradeNotification
    pnl: float


class ErrorNotification(BaseModel):
    """Error notification data"""
    error_message: str
    context: Optional[Dict] = None


class StartupNotification(BaseModel):
    """Startup notification data"""
    mode: str
    symbols: list
    interval_minutes: int
    capital: float
    max_position_pct: float
    daily_loss_limit: float
    stop_loss_pct: float


class DailySummary(BaseModel):
    """Daily summary data"""
    total_pnl: float
    total_trades: int
    win_rate: float
    best_trade: float
    worst_trade: float
    balance: float
    open_positions: int


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": config.service_name,
        "version": config.service_version,
        "timestamp": int(datetime.now().timestamp() * 1000),
        "email_enabled": config.email_enabled,
        "telegram_enabled": config.telegram_enabled
    }


# Configuration endpoint
@app.get("/api/v1/config")
async def get_config():
    """Get notification configuration"""
    return {
        "success": True,
        "config": {
            "email_enabled": config.email_enabled,
            "telegram_enabled": config.telegram_enabled,
            "alert_on_trade": config.alert_on_trade,
            "alert_on_profit": config.alert_on_profit,
            "alert_on_loss": config.alert_on_loss,
            "alert_on_daily_limit": config.alert_on_daily_limit,
            "alert_on_error": config.alert_on_error,
            "alert_on_startup": config.alert_on_startup,
            "min_profit_alert": config.min_profit_alert,
            "min_loss_alert": config.min_loss_alert
        }
    }


# Trade notification endpoint
@app.post("/api/v1/notify/trade")
async def notify_trade(notification: TradeNotification):
    """
    Send trade execution notification

    Args:
        notification: Trade notification data

    Returns:
        dict: Notification status
    """
    try:
        trade_dict = notification.dict()

        # Send via email
        email_sent = False
        if config.email_enabled:
            email_sent = email_notifier.notify_trade_executed(trade_dict)

        # Send via Telegram
        telegram_sent = False
        if config.telegram_enabled:
            telegram_sent = await telegram_notifier.notify_trade_executed(trade_dict)

        return {
            "success": True,
            "email_sent": email_sent,
            "telegram_sent": telegram_sent,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to send trade notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Profit/loss notification endpoint
@app.post("/api/v1/notify/pnl")
async def notify_pnl(notification: ProfitLossNotification):
    """
    Send profit/loss notification

    Args:
        notification: P&L notification data

    Returns:
        dict: Notification status
    """
    try:
        trade_dict = notification.trade.dict()
        pnl = notification.pnl

        # Send via email
        email_sent = False
        if config.email_enabled:
            email_sent = email_notifier.notify_profit_loss(trade_dict, pnl)

        # Send via Telegram
        telegram_sent = False
        if config.telegram_enabled:
            telegram_sent = await telegram_notifier.notify_profit_loss(trade_dict, pnl)

        return {
            "success": True,
            "email_sent": email_sent,
            "telegram_sent": telegram_sent,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to send P&L notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Daily limit notification endpoint
@app.post("/api/v1/notify/daily-limit")
async def notify_daily_limit(total_loss: float):
    """
    Send daily loss limit notification

    Args:
        total_loss: Total loss amount

    Returns:
        dict: Notification status
    """
    try:
        # Send via email
        email_sent = False
        if config.email_enabled:
            email_sent = email_notifier.notify_daily_limit_reached(total_loss)

        # Send via Telegram
        telegram_sent = False
        if config.telegram_enabled:
            telegram_sent = await telegram_notifier.notify_daily_limit_reached(total_loss)

        return {
            "success": True,
            "email_sent": email_sent,
            "telegram_sent": telegram_sent,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to send daily limit notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Error notification endpoint
@app.post("/api/v1/notify/error")
async def notify_error(notification: ErrorNotification):
    """
    Send error notification

    Args:
        notification: Error notification data

    Returns:
        dict: Notification status
    """
    try:
        # Send via email
        email_sent = False
        if config.email_enabled:
            email_sent = email_notifier.notify_error(
                notification.error_message,
                notification.context
            )

        # Send via Telegram
        telegram_sent = False
        if config.telegram_enabled:
            telegram_sent = await telegram_notifier.notify_error(
                notification.error_message,
                notification.context
            )

        return {
            "success": True,
            "email_sent": email_sent,
            "telegram_sent": telegram_sent,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to send error notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Startup notification endpoint
@app.post("/api/v1/notify/startup")
async def notify_startup(notification: StartupNotification):
    """
    Send startup notification

    Args:
        notification: Startup notification data

    Returns:
        dict: Notification status
    """
    try:
        config_dict = notification.dict()

        # Send via email
        email_sent = False
        if config.email_enabled:
            email_sent = email_notifier.notify_startup(config_dict)

        # Send via Telegram
        telegram_sent = False
        if config.telegram_enabled:
            telegram_sent = await telegram_notifier.notify_startup(config_dict)

        return {
            "success": True,
            "email_sent": email_sent,
            "telegram_sent": telegram_sent,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to send startup notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Daily summary notification endpoint
@app.post("/api/v1/notify/daily-summary")
async def notify_daily_summary(summary: DailySummary):
    """
    Send daily summary notification

    Args:
        summary: Daily summary data

    Returns:
        dict: Notification status
    """
    try:
        summary_dict = summary.dict()

        # Send via Telegram only (daily summaries are better suited for Telegram)
        telegram_sent = False
        if config.telegram_enabled:
            telegram_sent = await telegram_notifier.notify_daily_summary(summary_dict)

        return {
            "success": True,
            "telegram_sent": telegram_sent,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to send daily summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Test notification endpoint
@app.post("/api/v1/test")
async def test_notifications():
    """
    Test notification systems

    Returns:
        dict: Test results
    """
    results = {
        "email": {"enabled": config.email_enabled, "sent": False},
        "telegram": {"enabled": config.telegram_enabled, "sent": False}
    }

    # Test email
    if config.email_enabled:
        results["email"]["sent"] = email_notifier.send_email(
            "Test Notification",
            "This is a test notification from your trading bot. If you receive this, email notifications are working correctly!"
        )

    # Test Telegram
    if config.telegram_enabled:
        results["telegram"]["sent"] = await telegram_notifier.send_message(
            "🧪 <b>Test Notification</b>\n\nThis is a test message from your trading bot. If you receive this, Telegram notifications are working correctly! ✅"
        )

    return {
        "success": True,
        "results": results,
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.host, port=config.port)
