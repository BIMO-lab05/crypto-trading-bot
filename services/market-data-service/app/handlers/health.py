"""
Health Endpoint Handlers
Extracted from main.py - Responsibility: Health checks and metrics endpoints

Handles:
- Health check endpoint
- Readiness check endpoint
- Prometheus metrics endpoint
"""

import time
import logging
from fastapi import HTTPException, Request, Depends
from fastapi.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

logger = logging.getLogger(__name__)


def get_fetcher(request: Request):
    """Get fetcher instance from app state"""
    return request.app.state.fetcher


async def health_check() -> dict:
    """
    Health check endpoint

    Returns basic service health status with timestamp.
    Used by load balancers and monitoring systems.

    Returns:
        dict: Health status
    """
    return {
        "status": "healthy",
        "service": "market-data-service",
        "timestamp": int(time.time() * 1000)
    }


async def readiness_check(fetcher=Depends(get_fetcher)) -> dict:
    """
    Readiness check endpoint

    Verifies that the service is ready to handle requests
    by checking connectivity to Bybit Connector.

    Args:
        fetcher: Data fetcher instance (injected)

    Returns:
        dict: Readiness status

    Raises:
        HTTPException: 503 if Bybit Connector is not reachable
    """
    is_ready = await fetcher.health_check() if fetcher else False

    if is_ready:
        return {
            "status": "ready",
            "service": "market-data-service",
            "bybit_connector": "ok"
        }
    else:
        raise HTTPException(status_code=503, detail="Bybit Connector not reachable")


async def metrics_endpoint() -> Response:
    """
    Prometheus metrics endpoint

    Returns metrics in Prometheus exposition format.
    Scraped by Prometheus for monitoring and alerting.

    Returns:
        Response: Prometheus metrics in text format
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
