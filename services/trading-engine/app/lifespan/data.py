"""Data-layer lifespan phase: db, portfolio, positions, paper-engine balance sync."""

import logging
from contextlib import asynccontextmanager
from decimal import Decimal

from app.config import get_settings
from app.database.connection import db_manager
from app.position_manager import get_position_manager
from app.repositories import get_portfolio_repository

logger = logging.getLogger(__name__)


@asynccontextmanager
async def init_data():
    """Initialize DB engine, portfolio, positions, paper-engine balance.

    On exit: close DB connections. Errors during init are logged but do not
    abort startup — service continues without DB persistence (matches the
    pre-refactor behavior in main.py).
    """
    logger.info("init_data: enter")
    settings = get_settings()
    from app.main import database_health  # deferred: avoid circular import

    try:
        try:
            db_manager.init_async_engine()
            db_health = db_manager.health_check()
            if db_health:
                logger.info("Database connection initialized")
                database_health.set(1)

                portfolio_repo = get_portfolio_repository()
                await portfolio_repo.get_or_create(
                    portfolio_id="paper_trading",
                    name="Paper Trading Portfolio",
                    initial_balance=Decimal(str(settings.paper_initial_balance)),
                )
                logger.info("Paper trading portfolio verified")

                position_manager = get_position_manager()
                loaded_count = await position_manager.load_positions_from_db()
                logger.info(f"Loaded {loaded_count} positions from database")

                from app.paper_trading import get_paper_engine

                paper_engine = get_paper_engine()
                paper_engine.sync_balance_with_positions()
                logger.info(
                    f"Paper trading balance synced: ${paper_engine.get_balance():.2f}"
                )
            else:
                logger.warning(
                    "Database connection failed - trades will not be persisted"
                )
                database_health.set(0)
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            logger.warning("Continuing without database persistence")
            database_health.set(0)

        # Pre-warm the instruments cache so the min-notional gate has spec
        # available on the first auto-trader cycle. Fail-open: connector
        # outage at boot logs WARN; gate will return None per-symbol until
        # the next get() succeeds.
        try:
            from app.main import get_instruments_cache  # deferred: circular

            cache = get_instruments_cache()
            await cache.refresh(list(settings.trading_symbols))
        except Exception as e:
            logger.warning(
                f"InstrumentsCache pre-warm failed ({e}); min-notional gate "
                f"fails open until first successful refresh"
            )

        yield
    finally:
        try:
            await db_manager.close()
            logger.info("Database connections closed")
        except Exception as e:
            logger.error(f"Error closing database connections: {e}")
        logger.info("init_data: exit")
