"""
Health Endpoint Handlers
Extracted from main.py - Responsibility: Service health and status monitoring

Handles health checks and service status reporting.
"""

import logging
from fastapi import HTTPException

from app.models import HealthResponse, StatusResponse
from app.services import PortfolioManager
from app.config import settings
from app.utils import check_service_health

logger = logging.getLogger(__name__)


def get_portfolio_manager() -> PortfolioManager:
    """Get portfolio manager instance (from global state)"""
    from app.main import portfolio_manager
    if portfolio_manager is None:
        raise HTTPException(status_code=503, detail="Portfolio Manager not initialized")
    return portfolio_manager


async def health_check() -> HealthResponse:
    """
    Health check endpoint

    Checks connectivity to external services:
    - Trading Engine Service
    - Market Data Service
    - Database (when implemented)

    Returns:
        HealthResponse with connection status for each service
    """
    trading_engine_healthy = await check_service_health(settings.trading_engine_url)
    market_data_healthy = await check_service_health(settings.market_data_url)

    # Check database connection if enabled
    database_healthy = False
    if settings.use_database:
        try:
            # Import database manager only if database is enabled
            from shared.database.connection import db_manager
            database_healthy = db_manager.health_check()
        except ImportError:
            # shared.database module not available - this is expected when not using database
            database_healthy = False
        except Exception as e:
            logger.warning(f"Database check error: {e}")
            database_healthy = False

    return HealthResponse(
        status="healthy",
        trading_engine_connection=trading_engine_healthy,
        market_data_connection=market_data_healthy,
        database_connection=database_healthy
    )


async def get_status() -> StatusResponse:
    """
    Get service status

    Returns:
    - Service operational status
    - Number of portfolios managed
    - Total portfolio value across all portfolios
    - Count of active positions

    Returns:
        StatusResponse with service statistics
    """
    manager = get_portfolio_manager()
    portfolios = manager.list_portfolios()

    total_value = sum(p.total_value for p in portfolios)
    active_positions = sum(len(p.assets) for p in portfolios)

    return StatusResponse(
        status="running",
        portfolio_count=len(portfolios),
        total_value=str(total_value),
        active_positions=active_positions
    )
