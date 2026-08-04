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
        "timestamp": int(time.time() * 1000),
    }


async def data_freshness() -> dict:
    """
    Age of the newest stored ticker row, against the configured budget.

    Deliberately reported on /ready rather than /health. `/health` is wired to
    the container healthcheck (docker-compose.unified.yml:459) and
    trading-engine declares `depends_on: market-data: service_healthy`
    (:552-554), so failing /health on stale data would stop the trading engine
    from *booting*. Stale prices should make a consumer refuse to trade, not
    refuse to start -- and a service whose process is answering is, by
    definition, live.
    """
    from app.config import get_settings
    from app.repository import TickerRepository

    budget = get_settings().market_data_staleness_seconds

    try:
        newest_age = await TickerRepository.get_newest_row_age_seconds()
    except Exception as exc:
        logger.error(f"Could not determine market-data freshness: {exc}")
        return {"ok": False, "reason": "freshness_unknown", "budget_seconds": budget}

    if newest_age is None:
        return {"ok": False, "reason": "no_data", "budget_seconds": budget}

    return {
        "ok": newest_age <= budget,
        "newest_row_age_seconds": round(newest_age, 1),
        "budget_seconds": budget,
    }


async def readiness_check(fetcher=Depends(get_fetcher)) -> dict:
    """
    Readiness check endpoint

    Ready means "can serve correct data", which is stricter than "process is
    up". Two conditions: the Bybit Connector is reachable, AND ingest is
    actually current.

    The freshness half exists because ingest once stalled for 17 hours while
    every endpoint kept returning 200 and the last stored row as current
    (audit DL-1). Repairing the scheduler fixed that instance; this makes the
    failure mode observable rather than silent.

    Args:
        fetcher: Data fetcher instance (injected)

    Returns:
        dict: Readiness status

    Raises:
        HTTPException: 503 if Bybit Connector is unreachable or data is stale
    """
    connector_ok = await fetcher.health_check() if fetcher else False
    freshness = await data_freshness()

    if not connector_ok:
        raise HTTPException(status_code=503, detail="Bybit Connector not reachable")

    if not freshness.get("ok"):
        age = freshness.get("newest_row_age_seconds")
        detail = (
            f"Market data is stale: newest row is {age}s old "
            f"(budget {freshness.get('budget_seconds')}s)"
            if age is not None
            else f"Market data not ready: {freshness.get('reason')}"
        )
        logger.error(detail)
        raise HTTPException(status_code=503, detail=detail)

    return {
        "status": "ready",
        "service": "market-data-service",
        "bybit_connector": "ok",
        "data_freshness": freshness,
    }


async def metrics_endpoint() -> Response:
    """
    Prometheus metrics endpoint

    Returns metrics in Prometheus exposition format.
    Scraped by Prometheus for monitoring and alerting.

    Returns:
        Response: Prometheus metrics in text format
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
