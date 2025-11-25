"""
Health Check Endpoint Handlers
Extracted from main.py - Responsibility: Health monitoring endpoints

Provides comprehensive health and status checks for the trading engine service.

UPGRADED: Integrated with new HealthMonitor module
"""

import logging
import time

from app.config import get_settings
from app.signal_aggregator import get_aggregator
from app.position_manager import get_position_manager
from app.paper_trading import get_paper_engine
from app.models import HealthResponse, StatusResponse
from app.monitoring import get_health_monitor
from app.database.connection import db_manager

logger = logging.getLogger(__name__)
settings = get_settings()


async def health_check() -> HealthResponse:
    """
    Enhanced health check endpoint with comprehensive monitoring

    Checks connectivity to:
    - Technical Analysis Service
    - Database (PostgreSQL)
    - Redis Cache
    - Bybit Connector
    - System resources

    Returns:
        HealthResponse with connection statuses and health metrics
    """
    # Get health monitor instance
    health_monitor = get_health_monitor()

    # Try to get cached health check (max 10 seconds old)
    cached_health = await health_monitor.get_cached_health(max_age_seconds=10)

    if cached_health:
        # Use cached result for better performance
        logger.debug("Using cached health check result")

        # Extract dependency statuses
        ta_healthy = cached_health.dependencies.get("technical_analysis", None)
        db_healthy_obj = cached_health.dependencies.get("postgres", None)
        redis_healthy_obj = cached_health.dependencies.get("redis", None)
        bybit_healthy_obj = cached_health.dependencies.get("bybit_connector", None)

        return HealthResponse(
            status=cached_health.status.value,
            service=settings.service_name,
            technical_analysis_connection=ta_healthy.status.value == "healthy" if ta_healthy else False,
            bybit_connector_connection=bybit_healthy_obj.status.value == "healthy" if bybit_healthy_obj else False,
            database_connection=db_healthy_obj.status.value == "healthy" if db_healthy_obj else False,
            timestamp=int(time.time() * 1000),
            details={
                "dependencies": {
                    name: dep.to_dict()
                    for name, dep in cached_health.dependencies.items()
                },
                "metrics": cached_health.metrics
            }
        )

    # Perform fresh health check
    external_apis = {
        "technical_analysis": f"{settings.technical_analysis_url}/health",
        "bybit_connector": f"{settings.bybit_connector_url}/health",
    }

    system_health = await health_monitor.perform_health_check(
        postgres_enabled=True,
        redis_url=settings.redis_url,
        external_apis=external_apis
    )

    # Extract individual statuses for backward compatibility
    ta_healthy = system_health.dependencies.get("technical_analysis", None)
    db_healthy_obj = system_health.dependencies.get("postgres", None)
    bybit_healthy_obj = system_health.dependencies.get("bybit_connector", None)

    # Build enhanced response
    return HealthResponse(
        status=system_health.status.value,
        service=settings.service_name,
        technical_analysis_connection=ta_healthy.status.value == "healthy" if ta_healthy else False,
        bybit_connector_connection=bybit_healthy_obj.status.value == "healthy" if bybit_healthy_obj else False,
        database_connection=db_healthy_obj.status.value == "healthy" if db_healthy_obj else False,
        timestamp=int(time.time() * 1000),
        details={
            "dependencies": {
                name: dep.to_dict()
                for name, dep in system_health.dependencies.items()
            },
            "metrics": system_health.metrics
        }
    )


async def get_status() -> StatusResponse:
    """
    Get trading engine status

    Returns current operational status:
    - Trading mode (PAPER/LIVE)
    - Auto trading enabled/disabled
    - Active strategy
    - Open positions count
    - Current balance
    - System health metrics

    Returns:
        StatusResponse with operational metrics
    """
    position_manager = get_position_manager()
    paper_engine = get_paper_engine()

    open_positions = position_manager.get_open_positions()

    # Get basic system metrics
    health_monitor = get_health_monitor()
    system_metrics = health_monitor.get_system_metrics()

    return StatusResponse(
        status="running",
        trading_mode=settings.trading_mode,
        auto_trading_enabled=settings.auto_trading_enabled,
        active_strategy=settings.default_strategy,
        open_positions_count=len(open_positions),
        current_balance=float(paper_engine.get_balance()),
        timestamp=int(time.time() * 1000),
        system_metrics=system_metrics
    )


async def get_detailed_health() -> dict:
    """
    Get detailed health status with all metrics

    Returns:
        Comprehensive health report with all dependencies and metrics
    """
    health_monitor = get_health_monitor()

    # Perform comprehensive health check
    external_apis = {
        "technical_analysis": f"{settings.technical_analysis_url}/health",
        "bybit_connector": f"{settings.bybit_connector_url}/health",
        "portfolio_manager": f"{settings.portfolio_manager_url}/health",
    }

    system_health = await health_monitor.perform_health_check(
        postgres_enabled=True,
        redis_url=settings.redis_url,
        external_apis=external_apis
    )

    return {
        "overall_status": system_health.status.value,
        "timestamp": system_health.timestamp.isoformat(),
        "service": settings.service_name,
        "dependencies": {
            name: dep.to_dict()
            for name, dep in system_health.dependencies.items()
        },
        "system_metrics": system_health.metrics,
        "health_check_config": {
            "check_interval_seconds": health_monitor.check_interval,
            "failure_threshold": health_monitor.failure_threshold,
            "timeout_seconds": health_monitor.timeout_seconds
        }
    }
