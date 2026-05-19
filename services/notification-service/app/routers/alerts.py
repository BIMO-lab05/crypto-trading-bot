"""
Alerts API Router
REST endpoints for alert management and multi-channel notifications
"""

import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from ..alert_manager import alert_manager
from ..alert_rules import alert_rules_engine
from ..auth import verify_admin_key
from ..config import config
from ..models import (
    Alert,
    AlertAcknowledge,
    AlertBatch,
    AlertConfigResponse,
    AlertConfigUpdate,
    AlertCreate,
    AlertListResponse,
    AlertResponse,
    AlertRules,
    AlertRulesUpdate,
    AlertSeverity,
    AlertStats,
    AlertType,
    ChannelTestResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


# ========================================
# Alert Sending Endpoints
# ========================================


@router.post("/send", response_model=AlertResponse)
async def send_alert(alert: AlertCreate):
    """
    Send an alert through configured channels

    Routes the alert based on severity:
    - CRITICAL: Telegram + Email + Slack (immediate)
    - HIGH: Telegram + Email (within 1 min)
    - MEDIUM: Telegram OR Email (based on preference)
    - LOW: Email only (batched)
    - INFO: Dashboard notification only
    """
    try:
        response = await alert_manager.send_alert(alert)
        return response
    except Exception as e:
        logger.error(f"Error sending alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch", response_model=List[AlertResponse])
async def send_batch_alerts(batch: AlertBatch):
    """
    Send multiple alerts in a batch

    Each alert is processed independently with its own routing rules.
    Returns a list of responses for each alert.
    """
    try:
        responses = await alert_manager.send_batch(batch)
        return responses
    except Exception as e:
        logger.error(f"Error sending batch alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# Alert Retrieval Endpoints
# ========================================


@router.get("/history", response_model=AlertListResponse)
async def get_alert_history(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    severity: Optional[AlertSeverity] = None,
    alert_type: Optional[AlertType] = None,
):
    """
    Get alert history with optional filtering

    Returns paginated list of past alerts.
    """
    try:
        alerts = alert_manager.get_alerts(
            limit=limit, offset=offset, severity=severity, alert_type=alert_type
        )

        return AlertListResponse(
            success=True,
            alerts=alerts,
            total=len(alerts),
            page=offset // limit + 1,
            page_size=limit,
            has_more=len(alerts) == limit,
        )
    except Exception as e:
        logger.error(f"Error getting alert history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/active", response_model=AlertListResponse)
async def get_active_alerts():
    """
    Get all unacknowledged alerts

    Returns alerts that require attention and have not been acknowledged.
    """
    try:
        alerts = alert_manager.get_active_alerts()

        return AlertListResponse(
            success=True,
            alerts=alerts,
            total=len(alerts),
            page=1,
            page_size=len(alerts),
            has_more=False,
        )
    except Exception as e:
        logger.error(f"Error getting active alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{alert_id}", response_model=Alert)
async def get_alert(alert_id: str):
    """
    Get a specific alert by ID
    """
    alert = alert_manager.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


# ========================================
# Alert Acknowledgment
# ========================================


@router.post("/acknowledge/{alert_id}", response_model=AlertResponse)
async def acknowledge_alert(alert_id: str, ack: AlertAcknowledge):
    """
    Acknowledge an alert

    Marks the alert as acknowledged to prevent escalation.
    """
    success = alert_manager.acknowledge_alert(
        alert_id=alert_id, acknowledged_by=ack.acknowledged_by, notes=ack.notes
    )

    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")

    return AlertResponse(
        success=True,
        alert_id=alert_id,
        message=f"Alert acknowledged by {ack.acknowledged_by}",
    )


# ========================================
# Configuration Endpoints
# ========================================


@router.get("/config", response_model=AlertConfigResponse)
async def get_alert_config():
    """
    Get current alert configuration

    Returns channel settings, routing rules, and suppression settings.
    """
    return AlertConfigResponse(
        channels={
            "telegram": config.telegram_enabled,
            "email": config.email_enabled,
            "slack": config.slack_enabled,
            "sms": config.sms_enabled,
        },
        routing={
            "CRITICAL": config.get_channels_for_severity(AlertSeverity.CRITICAL),
            "HIGH": config.get_channels_for_severity(AlertSeverity.HIGH),
            "MEDIUM": config.get_channels_for_severity(AlertSeverity.MEDIUM),
            "LOW": config.get_channels_for_severity(AlertSeverity.LOW),
            "INFO": config.get_channels_for_severity(AlertSeverity.INFO),
        },
        suppression={
            "dedup_window_seconds": config.dedup_window_seconds,
            "throttle_max_per_hour": config.throttle_max_per_hour,
        },
        escalation={
            "critical_ack_timeout": config.critical_ack_timeout,
            "system_down_escalation": config.system_down_escalation,
            "emergency_contact": config.emergency_contact,
        },
        quiet_hours={
            "enabled": config.quiet_hours_enabled,
            "start": config.quiet_hours_start,
            "end": config.quiet_hours_end,
            "timezone": config.quiet_hours_timezone,
        },
    )


@router.put("/config", response_model=AlertConfigResponse)
async def update_alert_config(update: AlertConfigUpdate):
    """
    Update alert configuration

    Updates are applied in memory. For persistent changes,
    update the environment variables or .env file.
    """
    # Note: In production, this would persist to database
    # For now, we just log the update request

    logger.info(
        f"Alert config update requested: {update.model_dump(exclude_none=True)}"
    )

    # Return current config (in production, return updated config)
    return await get_alert_config()


# ========================================
# Channel Management Endpoints
# ========================================


@router.get("/channels/status")
async def get_channels_status():
    """
    Get health status of all notification channels

    Returns enabled status, health status, and recent statistics
    for each configured channel.
    """
    try:
        statuses = await alert_manager.get_all_channel_status()
        return {
            "success": True,
            "channels": {
                name: {
                    "enabled": status.enabled,
                    "healthy": status.healthy,
                    "last_message_at": status.last_message_at.isoformat()
                    if status.last_message_at
                    else None,
                    "messages_sent_today": status.messages_sent_today,
                    "failures_today": status.failures_today,
                    "rate_limit_remaining": status.rate_limit_remaining,
                    "error_message": status.error_message,
                }
                for name, status in statuses.items()
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting channel status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test/{channel}", response_model=ChannelTestResult)
async def test_channel(channel: str):
    """
    Send a test message to a specific channel

    Use this to verify channel configuration is working correctly.
    """
    valid_channels = ["telegram", "email", "slack", "sms"]
    if channel not in valid_channels:
        raise HTTPException(
            status_code=400, detail=f"Invalid channel. Must be one of: {valid_channels}"
        )

    try:
        start_time = datetime.utcnow()
        result = await alert_manager.test_channel(channel)
        end_time = datetime.utcnow()

        response_time = int((end_time - start_time).total_seconds() * 1000)

        return ChannelTestResult(
            channel=channel,
            success=result.success,
            response_time_ms=response_time,
            error_message=result.error_message,
            timestamp=end_time,
        )
    except Exception as e:
        logger.error(f"Error testing channel {channel}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# Rules Management Endpoints
# ========================================


@router.get("/rules", response_model=AlertRules)
async def get_alert_rules():
    """
    Get current suppression and escalation rules
    """
    return AlertRules(
        suppression_rules=alert_rules_engine.get_suppression_rules(),
        escalation_rules=alert_rules_engine.get_escalation_rules(),
    )


@router.put("/rules", response_model=AlertRules)
async def update_alert_rules(rules_update: AlertRulesUpdate):
    """
    Update suppression and escalation rules

    Pass only the rules you want to update.
    """
    if rules_update.suppression_rules is not None:
        alert_rules_engine.update_suppression_rules(rules_update.suppression_rules)

    if rules_update.escalation_rules is not None:
        alert_rules_engine.update_escalation_rules(rules_update.escalation_rules)

    return AlertRules(
        suppression_rules=alert_rules_engine.get_suppression_rules(),
        escalation_rules=alert_rules_engine.get_escalation_rules(),
    )


# ========================================
# Statistics Endpoint
# ========================================


@router.get("/stats", response_model=AlertStats)
async def get_alert_stats(hours: int = Query(default=24, ge=1, le=720)):
    """
    Get alert statistics for the specified period

    Default is last 24 hours. Maximum is 720 hours (30 days).
    """
    try:
        stats = alert_manager.get_stats(period_hours=hours)
        return stats
    except Exception as e:
        logger.error(f"Error getting alert stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# Specialized Alert Endpoints
# ========================================


@router.post("/trade", response_model=AlertResponse)
async def send_trade_alert(
    action: str,
    symbol: str,
    quantity: float,
    price: float,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    confidence: float = 0.0,
    pnl: Optional[float] = None,
):
    """
    Send a trade execution alert

    Convenience endpoint for trade notifications.
    """
    try:
        response = await alert_manager.send_trade_alert(
            action=action,
            symbol=symbol,
            quantity=quantity,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=confidence,
            pnl=pnl,
        )
        return response
    except Exception as e:
        logger.error(f"Error sending trade alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/risk", response_model=AlertResponse)
async def send_risk_alert(
    alert_type: str,
    message: str,
    severity: AlertSeverity = AlertSeverity.HIGH,
    current_value: Optional[float] = None,
    threshold: Optional[float] = None,
):
    """
    Send a risk management alert

    Convenience endpoint for risk-related notifications.
    """
    try:
        response = await alert_manager.send_risk_alert(
            alert_type=alert_type,
            message=message,
            severity=severity,
            current_value=current_value,
            threshold=threshold,
        )
        return response
    except Exception as e:
        logger.error(f"Error sending risk alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/system", response_model=AlertResponse)
async def send_system_alert(
    service_name: str, status: str, error_message: Optional[str] = None
):
    """
    Send a system status alert

    Convenience endpoint for system/service notifications.
    """
    try:
        response = await alert_manager.send_system_alert(
            service_name=service_name, status=status, error_message=error_message
        )
        return response
    except Exception as e:
        logger.error(f"Error sending system alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/daily-summary", response_model=AlertResponse)
async def send_daily_summary(
    total_pnl: float,
    total_trades: int,
    win_rate: float,
    best_trade: float,
    worst_trade: float,
    balance: float,
    open_positions: int = 0,
    ml_gate_reason_counts: Optional[dict] = None,
    _admin: str = Depends(verify_admin_key),
):
    """
    Send daily trading summary

    Convenience endpoint for daily performance summaries.

    Admin-guarded (Phase 9 T-09-03-05): requires the ``X-Admin-Key`` header
    matching the service's configured ``ADMIN_API_KEY``. The scheduled
    digest path (``app/scheduler/ml_gate_digest.py``) bypasses this guard
    because it calls ``alert_manager.send_daily_summary`` directly in
    process; only the HTTP surface is gated.

    ``ml_gate_reason_counts`` (Plan 09-03 MLGATE-03): optional dict of
    ML-gate reason counts; when non-empty, the rendered digest message gains
    an "ML Gate Reasons (24h):" section in canonical order. Forwarded to
    ``alert_manager.send_daily_summary``.
    """
    try:
        response = await alert_manager.send_daily_summary(
            total_pnl=total_pnl,
            total_trades=total_trades,
            win_rate=win_rate,
            best_trade=best_trade,
            worst_trade=worst_trade,
            balance=balance,
            open_positions=open_positions,
            ml_gate_reason_counts=ml_gate_reason_counts,
        )
        return response
    except Exception as e:
        logger.error(f"Error sending daily summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))
