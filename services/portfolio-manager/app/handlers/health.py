"""
Health Endpoint Handlers
Extracted from main.py - Responsibility: Service health and status monitoring

Handles health checks and service status reporting.
"""

import asyncio
import logging
from fastapi import HTTPException

from app.models import HealthResponse, StatusResponse
from app.services import PortfolioManager
from app.config import settings
from app.utils import check_service_health

logger = logging.getLogger(__name__)

# Hard ceiling on the whole acquire+query round-trip. Covers pool.acquire()
# too — an exhausted pool blocks there, not at fetchval.
_DB_PROBE_TIMEOUT_SECONDS = 2.0


async def _probe_db_pool(pool) -> bool:
    """Probe the live asyncpg pool with SELECT 1 under a hard timeout.

    Returns True when the pool answers within the timeout; False on ANY
    failure (including asyncio.TimeoutError). Never raises — health and
    readiness endpoints must degrade, not 500.
    """

    async def _query() -> None:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")

    try:
        await asyncio.wait_for(_query(), timeout=_DB_PROBE_TIMEOUT_SECONDS)
        return True
    except Exception as e:
        logger.warning(f"Database pool probe failed: {e}")
        return False


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
        # Function-level import against app.main globals (same pattern as
        # get_portfolio_manager) — keeps tests patchable and import order safe.
        from app.main import db_pool

        if db_pool is not None:
            # The service's real connection: probe the live asyncpg pool.
            database_healthy = await _probe_db_pool(db_pool)
        else:
            # Legacy fallback, only reached when the real pool is absent.
            # In-container this import is dead (empty ./shared dir in the
            # image — see .claude/rules/money.md) and lands in ImportError.
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
        database_connection=database_healthy,
    )


async def readiness_check() -> dict:
    """
    Readiness check - verifies the service is ready to handle traffic.

    Stricter than /health: requires portfolio_manager to be initialized.
    DB check is best-effort; absence of DB does not fail readiness when
    use_database is False (in-memory mode is supported).

    Raises HTTPException(503) when not ready.
    """
    from app.main import portfolio_manager

    if portfolio_manager is None:
        raise HTTPException(
            status_code=503,
            detail="Portfolio Manager not initialized",
        )

    db_status = "skipped"
    if settings.use_database:
        from app.main import db_pool

        if db_pool is not None:
            # The service's real connection: probe the live asyncpg pool.
            if await _probe_db_pool(db_pool):
                db_status = "ok"
            else:
                raise HTTPException(
                    status_code=503,
                    detail="Database unavailable",
                )
        else:
            # Legacy fallback, only reached when the real pool is absent.
            try:
                from shared.database.connection import db_manager

                if not db_manager.health_check():
                    raise HTTPException(
                        status_code=503,
                        detail="Database unavailable",
                    )
                db_status = "ok"
            except ImportError:
                db_status = "unavailable"
            except HTTPException:
                raise
            except Exception as e:
                logger.warning(f"Readiness DB check error: {e}")
                raise HTTPException(
                    status_code=503,
                    detail=f"Database check failed: {e}",
                )

    return {"status": "ready", "portfolio_manager": "ok", "database": db_status}


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
        active_positions=active_positions,
    )
