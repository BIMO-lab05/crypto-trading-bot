"""
Notification Service - Main Application
Provides REST API for sending alerts via multiple channels
Enhanced with multi-channel orchestration and advanced alerting

PROMETHEUS METRICS: 2025-12-12
- Added /metrics endpoint for Prometheus scraping
- HTTP request counters and histograms
- Notification delivery metrics
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Dict, Optional
import asyncio  # MLGATE-03 (Plan 09-03 D-09-03-07): lifespan cancels the ML-gate digest scheduler task
import logging
import time
from datetime import datetime

# Prometheus metrics imports
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from prometheus_client import multiprocess, CollectorRegistry
import os
import tempfile

# Import local modules
try:
    from .utils.structured_logging import (
        setup_logging,
        RequestContextLogger,
        install_token_redaction,
    )
    from .utils.graceful_shutdown import GracefulShutdownHandler
except ImportError:
    from pathlib import Path
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))
    from utils.structured_logging import (
        install_token_redaction,
    )

from .config import config
from .routers.alerts import router as alerts_router
from .alert_manager import alert_manager
from . import dlq

# Legacy imports for backward compatibility
from .email_notifier import email_notifier
from .telegram_notifier import telegram_notifier

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
install_token_redaction()
logger = logging.getLogger(__name__)


# ============================================================================
# DELIVERY-STATUS HELPER
# ============================================================================
# Replaces the prior false-success pattern: every endpoint returned
# `{"success": True}` regardless of whether email_sent / telegram_sent were
# actually True, so the trading-engine logged "notification sent" while
# Telegram/SMTP had silently failed. The helper raises 502 on partial /
# total delivery failure so callers can react instead of trusting HTTP 200.


def _build_delivery_response(
    *,
    email_attempted: bool,
    email_sent: bool,
    telegram_attempted: bool,
    telegram_sent: bool,
    endpoint: str = "unknown",
    payload: Optional[Dict] = None,
) -> Dict:
    attempted = []
    if email_attempted:
        attempted.append(("email", email_sent))
    if telegram_attempted:
        attempted.append(("telegram", telegram_sent))

    failed = [name for name, ok in attempted if not ok]
    all_succeeded = bool(attempted) and not failed

    body = {
        "success": all_succeeded,
        "email_sent": email_sent if email_attempted else None,
        "telegram_sent": telegram_sent if telegram_attempted else None,
        "timestamp": datetime.now().isoformat(),
    }

    if not attempted:
        body["reason"] = "no notification channels enabled"
        logger.error("Notification request had no enabled channels to deliver on")
        dlq.enqueue(
            endpoint=endpoint,
            failed_channels=["__none_enabled__"],
            payload=payload or {},
            response=body,
        )
        raise HTTPException(status_code=503, detail=body)

    if failed:
        body["failed_channels"] = failed
        body["reason"] = f"delivery failed on: {failed}"
        logger.warning(
            "Notification delivery FAILED on channels=%s body=%s", failed, body
        )
        dlq.enqueue(
            endpoint=endpoint,
            failed_channels=failed,
            payload=payload or {},
            response=body,
        )
        raise HTTPException(status_code=502, detail=body)

    return body


# ============================================================================
# PROMETHEUS METRICS
# ============================================================================

# HTTP request counter
http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status_code"]
)

# HTTP request duration histogram
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0],
)

# Active requests gauge
http_requests_active = Gauge("http_requests_active", "Number of active HTTP requests")

# Notification-specific metrics
notifications_sent_total = Counter(
    "notifications_sent_total",
    "Total notifications sent",
    ["channel", "type", "status"],
)

notification_delivery_duration_seconds = Histogram(
    "notification_delivery_duration_seconds",
    "Notification delivery duration in seconds",
    ["channel"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

notification_channel_health = Gauge(
    "notification_channel_health",
    "Notification channel health status (1=healthy, 0=unhealthy)",
    ["channel"],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown"""
    # Setup multiprocess metrics directory
    temp_dir = tempfile.mkdtemp(prefix="prometheus_multiproc_")
    os.environ["PROMETHEUS_MULTIPROC_DIR"] = temp_dir
    logger.info(f"Prometheus multiprocess directory: {temp_dir}")

    # Startup
    logger.info("Notification Service starting...")
    logger.info("Prometheus metrics: enabled at /metrics")
    dlq.init_dlq()
    await alert_manager.start()
    logger.info("Alert Manager started")

    # Set channel health metrics
    notification_channel_health.labels(channel="email").set(
        1 if config.email_enabled else 0
    )
    notification_channel_health.labels(channel="telegram").set(
        1 if config.telegram_enabled else 0
    )
    notification_channel_health.labels(channel="slack").set(
        1 if config.slack_enabled else 0
    )
    notification_channel_health.labels(channel="sms").set(
        1 if config.sms_enabled else 0
    )

    # MLGATE-03 (Plan 09-03 D-09-03-07): feature-flagged ML-gate digest
    # scheduler. Off by default per CLAUDE.md flag discipline (mirror of
    # ENABLE_SENTIMENT_ANALYSIS). When ML_GATE_DIGEST_ENABLED=true, spawn
    # the cross-service fetcher that pulls reason counts from the
    # trading-engine and ships them in the daily Telegram digest.
    app.state.ml_gate_digest_task = None
    if os.environ.get("ML_GATE_DIGEST_ENABLED", "false").lower() == "true":
        from .scheduler.ml_gate_digest import start_scheduler as _start_ml_gate_digest

        app.state.ml_gate_digest_task = await _start_ml_gate_digest()
        logger.info("ML-gate digest scheduler started (feature-flag active)")

    yield

    # Shutdown
    logger.info("Notification Service shutting down...")
    if app.state.ml_gate_digest_task is not None:
        app.state.ml_gate_digest_task.cancel()
        try:
            await app.state.ml_gate_digest_task
        except (asyncio.CancelledError, Exception):
            pass
        logger.info("ML-gate digest scheduler stopped")
    await alert_manager.stop()
    logger.info("Alert Manager stopped")

    # Cleanup multiprocess metrics
    try:
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)
        if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
            del os.environ["PROMETHEUS_MULTIPROC_DIR"]
    except Exception as e:
        logger.error(f"Error cleaning up multiprocess metrics directory: {e}")


# Create FastAPI app with lifespan
app = FastAPI(
    title="Notification Service",
    description="Multi-channel alert system with intelligent routing, suppression, and escalation",
    version=config.service_version,
    lifespan=lifespan,
)


# ============================================================================
# PROMETHEUS METRICS MIDDLEWARE
# ============================================================================


@app.middleware("http")
async def prometheus_metrics_middleware(request: Request, call_next):
    """Middleware to collect Prometheus metrics for all HTTP requests"""
    # Skip metrics endpoint itself
    if request.url.path == "/metrics":
        return await call_next(request)

    method = request.method
    path = request.url.path

    # Normalize path to prevent high cardinality
    import re

    normalized_path = re.sub(
        r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "/{uuid}",
        path,
        flags=re.IGNORECASE,
    )

    http_requests_active.inc()
    start_time = time.time()

    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception:
        status_code = 500
        raise
    finally:
        duration = time.time() - start_time
        http_requests_active.dec()

        http_requests_total.labels(
            method=method, endpoint=normalized_path, status_code=status_code
        ).inc()

        http_request_duration_seconds.labels(
            method=method, endpoint=normalized_path
        ).observe(duration)

    return response


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the alerts router
app.include_router(alerts_router)


# ============================================================================
# PROMETHEUS METRICS ENDPOINT
# ============================================================================


def get_metrics_registry():
    """Get appropriate registry based on multiprocess environment"""
    if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return registry
    else:
        return None


@app.get("/metrics", include_in_schema=False)
async def metrics():
    """Prometheus metrics endpoint"""
    registry = get_metrics_registry()
    if registry:
        data = generate_latest(registry)
    else:
        data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


# ========================================
# Legacy Request Models (Backward Compatibility)
# ========================================


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


# ========================================
# Health and Info Endpoints
# ========================================


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": config.service_name,
        "version": config.service_version,
        "timestamp": int(datetime.now().timestamp() * 1000),
        "channels": {
            "email_enabled": config.email_enabled,
            "telegram_enabled": config.telegram_enabled,
            "slack_enabled": config.slack_enabled,
            "sms_enabled": config.sms_enabled,
        },
    }


@app.get("/ready")
async def readiness_check():
    """Readiness probe endpoint"""
    return {"status": "ready", "service": config.service_name}


@app.get("/api/v1/config")
async def get_config():
    """Get notification configuration"""
    return {
        "success": True,
        "config": {
            "email_enabled": config.email_enabled,
            "telegram_enabled": config.telegram_enabled,
            "slack_enabled": config.slack_enabled,
            "sms_enabled": config.sms_enabled,
            "alert_on_trade": config.alert_on_trade,
            "alert_on_profit": config.alert_on_profit,
            "alert_on_loss": config.alert_on_loss,
            "alert_on_daily_limit": config.alert_on_daily_limit,
            "alert_on_error": config.alert_on_error,
            "alert_on_startup": config.alert_on_startup,
            "min_profit_alert": config.min_profit_alert,
            "min_loss_alert": config.min_loss_alert,
        },
    }


# ========================================
# Legacy Notification Endpoints (Backward Compatibility)
# ========================================


@app.post("/api/v1/notify/trade")
async def notify_trade(notification: TradeNotification):
    """
    Send trade execution notification (Legacy endpoint)

    Args:
        notification: Trade notification data

    Returns:
        dict: Notification status
    """
    logger.info(
        f"[notify_trade] RECEIVED - symbol={notification.symbol}, action={notification.action}"
    )
    try:
        trade_dict = notification.model_dump()

        # Send via email
        email_sent = False
        email_start = time.time()
        if config.email_enabled:
            email_sent = email_notifier.notify_trade_executed(trade_dict)
            notification_delivery_duration_seconds.labels(channel="email").observe(
                time.time() - email_start
            )
            notifications_sent_total.labels(
                channel="email",
                type="trade",
                status="success" if email_sent else "failed",
            ).inc()

        # Send via Telegram
        telegram_sent = False
        telegram_start = time.time()
        if config.telegram_enabled:
            telegram_sent = await telegram_notifier.notify_trade_executed(trade_dict)
            notification_delivery_duration_seconds.labels(channel="telegram").observe(
                time.time() - telegram_start
            )
            notifications_sent_total.labels(
                channel="telegram",
                type="trade",
                status="success" if telegram_sent else "failed",
            ).inc()

        return _build_delivery_response(
            email_attempted=config.email_enabled,
            email_sent=email_sent,
            telegram_attempted=config.telegram_enabled,
            telegram_sent=telegram_sent,
            endpoint="/api/v1/notify/trade",
            payload=trade_dict,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send trade notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/notify/pnl")
async def notify_pnl(notification: ProfitLossNotification):
    """
    Send profit/loss notification (Legacy endpoint)

    Args:
        notification: P&L notification data

    Returns:
        dict: Notification status
    """
    try:
        trade_dict = notification.trade.model_dump()
        pnl = notification.pnl

        # Send via email
        email_sent = False
        email_start = time.time()
        if config.email_enabled:
            email_sent = email_notifier.notify_profit_loss(trade_dict, pnl)
            notification_delivery_duration_seconds.labels(channel="email").observe(
                time.time() - email_start
            )
            notifications_sent_total.labels(
                channel="email",
                type="pnl",
                status="success" if email_sent else "failed",
            ).inc()

        # Send via Telegram
        telegram_sent = False
        telegram_start = time.time()
        if config.telegram_enabled:
            telegram_sent = await telegram_notifier.notify_profit_loss(trade_dict, pnl)
            notification_delivery_duration_seconds.labels(channel="telegram").observe(
                time.time() - telegram_start
            )
            notifications_sent_total.labels(
                channel="telegram",
                type="pnl",
                status="success" if telegram_sent else "failed",
            ).inc()

        return _build_delivery_response(
            email_attempted=config.email_enabled,
            email_sent=email_sent,
            telegram_attempted=config.telegram_enabled,
            telegram_sent=telegram_sent,
            endpoint="/api/v1/notify/pnl",
            payload={"trade": trade_dict, "pnl": pnl},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send P&L notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/notify/daily-limit")
async def notify_daily_limit(total_loss: float):
    """
    Send daily loss limit notification (Legacy endpoint)

    Args:
        total_loss: Total loss amount

    Returns:
        dict: Notification status
    """
    try:
        # Send via email
        email_sent = False
        email_start = time.time()
        if config.email_enabled:
            email_sent = email_notifier.notify_daily_limit_reached(total_loss)
            notification_delivery_duration_seconds.labels(channel="email").observe(
                time.time() - email_start
            )
            notifications_sent_total.labels(
                channel="email",
                type="daily_limit",
                status="success" if email_sent else "failed",
            ).inc()

        # Send via Telegram
        telegram_sent = False
        telegram_start = time.time()
        if config.telegram_enabled:
            telegram_sent = await telegram_notifier.notify_daily_limit_reached(
                total_loss
            )
            notification_delivery_duration_seconds.labels(channel="telegram").observe(
                time.time() - telegram_start
            )
            notifications_sent_total.labels(
                channel="telegram",
                type="daily_limit",
                status="success" if telegram_sent else "failed",
            ).inc()

        return _build_delivery_response(
            email_attempted=config.email_enabled,
            email_sent=email_sent,
            telegram_attempted=config.telegram_enabled,
            telegram_sent=telegram_sent,
            endpoint="/api/v1/notify/daily-limit",
            payload={"total_loss": total_loss},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send daily limit notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/notify/error")
async def notify_error(notification: ErrorNotification):
    """
    Send error notification (Legacy endpoint)

    Args:
        notification: Error notification data

    Returns:
        dict: Notification status
    """
    try:
        # Send via email
        email_sent = False
        email_start = time.time()
        if config.email_enabled:
            email_sent = email_notifier.notify_error(
                notification.error_message, notification.context
            )
            notification_delivery_duration_seconds.labels(channel="email").observe(
                time.time() - email_start
            )
            notifications_sent_total.labels(
                channel="email",
                type="error",
                status="success" if email_sent else "failed",
            ).inc()

        # Send via Telegram
        telegram_sent = False
        telegram_start = time.time()
        if config.telegram_enabled:
            telegram_sent = await telegram_notifier.notify_error(
                notification.error_message, notification.context
            )
            notification_delivery_duration_seconds.labels(channel="telegram").observe(
                time.time() - telegram_start
            )
            notifications_sent_total.labels(
                channel="telegram",
                type="error",
                status="success" if telegram_sent else "failed",
            ).inc()

        return _build_delivery_response(
            email_attempted=config.email_enabled,
            email_sent=email_sent,
            telegram_attempted=config.telegram_enabled,
            telegram_sent=telegram_sent,
            endpoint="/api/v1/notify/error",
            payload=notification.model_dump(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send error notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/notify/startup")
async def notify_startup(notification: StartupNotification):
    """
    Send startup notification (Legacy endpoint)

    Args:
        notification: Startup notification data

    Returns:
        dict: Notification status
    """
    try:
        config_dict = notification.model_dump()

        # Send via email
        email_sent = False
        email_start = time.time()
        if config.email_enabled:
            email_sent = email_notifier.notify_startup(config_dict)
            notification_delivery_duration_seconds.labels(channel="email").observe(
                time.time() - email_start
            )
            notifications_sent_total.labels(
                channel="email",
                type="startup",
                status="success" if email_sent else "failed",
            ).inc()

        # Send via Telegram
        telegram_sent = False
        telegram_start = time.time()
        if config.telegram_enabled:
            telegram_sent = await telegram_notifier.notify_startup(config_dict)
            notification_delivery_duration_seconds.labels(channel="telegram").observe(
                time.time() - telegram_start
            )
            notifications_sent_total.labels(
                channel="telegram",
                type="startup",
                status="success" if telegram_sent else "failed",
            ).inc()

        return _build_delivery_response(
            email_attempted=config.email_enabled,
            email_sent=email_sent,
            telegram_attempted=config.telegram_enabled,
            telegram_sent=telegram_sent,
            endpoint="/api/v1/notify/startup",
            payload=config_dict,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send startup notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/notify/daily-summary")
async def notify_daily_summary(summary: DailySummary):
    """
    Send daily summary notification (Legacy endpoint)

    Args:
        summary: Daily summary data

    Returns:
        dict: Notification status
    """
    try:
        summary_dict = summary.model_dump()

        # Send via Telegram only (daily summaries are better suited for Telegram)
        telegram_sent = False
        telegram_start = time.time()
        if config.telegram_enabled:
            telegram_sent = await telegram_notifier.notify_daily_summary(summary_dict)
            notification_delivery_duration_seconds.labels(channel="telegram").observe(
                time.time() - telegram_start
            )
            notifications_sent_total.labels(
                channel="telegram",
                type="daily_summary",
                status="success" if telegram_sent else "failed",
            ).inc()

        return _build_delivery_response(
            email_attempted=False,
            email_sent=False,
            telegram_attempted=config.telegram_enabled,
            telegram_sent=telegram_sent,
            endpoint="/api/v1/notify/daily-summary",
            payload=summary_dict,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send daily summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# Dead-letter queue (visibility for failed deliveries)
# ========================================


@app.get("/api/v1/dlq")
async def list_dlq(limit: int = 50):
    """
    List the most recent failed-delivery alerts. Each entry includes the
    original payload so it can be re-driven manually if needed. Replay
    endpoint is a separate follow-up.
    """
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be 1..500")
    return {
        "total": dlq.count(),
        "returned": min(limit, dlq.count()) if dlq.count() >= 0 else 0,
        "items": dlq.list_recent(limit=limit),
    }


@app.post("/api/v1/test")
async def test_notifications():
    """
    Test notification systems (Legacy endpoint)

    Returns:
        dict: Test results
    """
    results = {
        "email": {"enabled": config.email_enabled, "sent": False},
        "telegram": {"enabled": config.telegram_enabled, "sent": False},
        "slack": {"enabled": config.slack_enabled, "sent": False},
        "sms": {"enabled": config.sms_enabled, "sent": False},
    }

    # Test email
    if config.email_enabled:
        email_start = time.time()
        results["email"]["sent"] = email_notifier.send_email(
            "Test Notification",
            "This is a test notification from your trading bot. If you receive this, email notifications are working correctly!",
        )
        notification_delivery_duration_seconds.labels(channel="email").observe(
            time.time() - email_start
        )
        notifications_sent_total.labels(
            channel="email",
            type="test",
            status="success" if results["email"]["sent"] else "failed",
        ).inc()

    # Test Telegram
    if config.telegram_enabled:
        telegram_start = time.time()
        results["telegram"]["sent"] = await telegram_notifier.send_message(
            "<b>Test Notification</b>\n\nThis is a test message from your trading bot. If you receive this, Telegram notifications are working correctly!"
        )
        notification_delivery_duration_seconds.labels(channel="telegram").observe(
            time.time() - telegram_start
        )
        notifications_sent_total.labels(
            channel="telegram",
            type="test",
            status="success" if results["telegram"]["sent"] else "failed",
        ).inc()

    # Honest top-level success: at least one *enabled* channel must have delivered.
    # Previously hardcoded True so a fully-failing test still showed success.
    attempted = [r["sent"] for r in results.values() if r["enabled"]]
    overall_success = bool(attempted) and all(attempted)
    return {
        "success": overall_success,
        "results": results,
        "timestamp": datetime.now().isoformat(),
    }


# ========================================
# Root Endpoint
# ========================================


@app.get("/")
async def root():
    """Service information endpoint"""
    return {
        "service": config.service_name,
        "version": config.service_version,
        "description": "Multi-channel alert system with intelligent routing, suppression, and escalation",
        "channels": {
            "email": config.email_enabled,
            "telegram": config.telegram_enabled,
            "slack": config.slack_enabled,
            "sms": config.sms_enabled,
        },
        "endpoints": {
            "health": "/health",
            "ready": "/ready",
            "metrics": "/metrics",
            "config": "/api/v1/config",
            "test": "/api/v1/test",
            "docs": "/docs",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.host, port=config.port)
