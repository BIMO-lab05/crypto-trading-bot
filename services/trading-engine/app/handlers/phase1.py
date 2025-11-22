"""
Phase 1 Enhancement Endpoint Handlers
Extracted from main.py - Responsibility: Phase 1 metrics and monitoring

Handles Phase 1 enhancement metrics including filtering rates,
GATEKEEPER/VALIDATOR statistics, and system health.
"""

import logging
import time
from fastapi import HTTPException

from app.phase1_metrics import get_phase1_metrics

logger = logging.getLogger(__name__)


async def get_phase1_metrics_endpoint(hours: int = 24):
    """
    Get Phase 1 performance metrics

    Analyzes signal processing over specified timeframe:
    - Filtering rates (GATEKEEPER rejection rate)
    - Validator acceptance rate
    - Signal quality metrics
    - Volume confirmation stats

    Args:
        hours: Number of hours to analyze (default: 24)

    Returns:
        Dict with Phase 1 metrics

    Raises:
        HTTPException: If metrics retrieval fails
    """
    try:
        provider = get_phase1_metrics()
        metrics = provider.get_metrics(hours=hours)

        return {
            "success": True,
            "data": metrics,
            "timestamp": int(time.time() * 1000)
        }

    except Exception as e:
        logger.error(f"Error getting Phase 1 metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_phase1_health():
    """
    Get Phase 1 system health status

    Checks:
    - GATEKEEPER operational status
    - VALIDATOR operational status
    - Trend filter availability
    - Volume confirmation availability

    Returns:
        Dict with Phase 1 health status

    Raises:
        HTTPException: If health check fails
    """
    try:
        provider = get_phase1_metrics()
        health = provider.get_system_health()

        return {
            "success": True,
            "data": health,
            "timestamp": int(time.time() * 1000)
        }

    except Exception as e:
        logger.error(f"Error getting Phase 1 health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_latest_phase1_signal():
    """
    Get the most recent Phase 1 signal

    Returns the last signal processed through Phase 1 enhancements
    including all filtering and validation results.

    Returns:
        Dict with latest Phase 1 signal or None

    Raises:
        HTTPException: If signal retrieval fails
    """
    try:
        provider = get_phase1_metrics()
        signal = provider.get_latest_signal()

        if not signal:
            return {
                "success": True,
                "data": None,
                "message": "No recent signals",
                "timestamp": int(time.time() * 1000)
            }

        return {
            "success": True,
            "data": signal,
            "timestamp": int(time.time() * 1000)
        }

    except Exception as e:
        logger.error(f"Error getting latest Phase 1 signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))
