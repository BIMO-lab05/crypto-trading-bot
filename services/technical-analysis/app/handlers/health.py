"""
Health Check Endpoint Handlers
Extracted from main.py - Responsibility: Health monitoring
"""

import time
from app.config import get_settings
from app.fetcher import get_fetcher
from app.models import HealthResponse, ReadyResponse

settings = get_settings()


async def health_check() -> HealthResponse:
    """
    Health check endpoint
    Returns service health and dependency status
    """
    fetcher = get_fetcher()
    market_data_healthy = await fetcher.health_check()

    return HealthResponse(
        status="healthy",
        service=settings.service_name,
        market_data_connection=market_data_healthy,
        timestamp=int(time.time() * 1000)
    )


async def readiness_check() -> ReadyResponse:
    """
    Readiness check endpoint
    Returns whether service is ready to handle requests
    """
    fetcher = get_fetcher()
    market_data_healthy = await fetcher.health_check()

    return ReadyResponse(
        status="ready" if market_data_healthy else "not_ready",
        service=settings.service_name,
        dependencies={
            "market_data_service": market_data_healthy
        },
        timestamp=int(time.time() * 1000)
    )
