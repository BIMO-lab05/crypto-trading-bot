"""ML/TA-layer lifespan phase: aggregator health, multi-timeframe, sqzmom, attribution."""

import logging
from contextlib import asynccontextmanager

from app.analytics import get_attribution_analyzer
from app.config import get_settings
from app.multi_timeframe import close_multi_timeframe_analyzer
from app.signal_aggregator import close_aggregator, get_aggregator
from app.strategies import sqzmom_config, sqzmom_strategy

logger = logging.getLogger(__name__)


@asynccontextmanager
async def init_ml():
    """TA aggregator health probe + attribution analyzer init.

    On exit: close aggregator, multi-timeframe analyzer, sqzmom strategy.
    """
    logger.info("init_ml: enter")
    settings = get_settings()
    from app.main import ta_service_health  # deferred: avoid circular import

    try:
        aggregator = await get_aggregator()
        is_healthy = await aggregator.health_check()
        if is_healthy:
            logger.info("Technical Analysis Service connection verified")
            ta_service_health.set(1)
        else:
            logger.warning("Technical Analysis Service not available")
            ta_service_health.set(0)

        try:
            get_attribution_analyzer(initial_capital=settings.paper_initial_balance)
            logger.info("[OK] Attribution Analyzer initialized (Phase 5.1)")
            logger.info(f"     Initial capital: ${settings.paper_initial_balance:,.2f}")
        except Exception as e:
            logger.warning(f"[WARN] Failed to initialize Attribution Analyzer: {e}")

        logger.info("=" * 60)
        logger.info("SQZMOM Strategy Configuration:")
        logger.info(f"  Enabled symbols: {sqzmom_config.enabled_symbols}")
        logger.info(f"  Paper trading: {sqzmom_config.paper_trading}")
        logger.info(f"  Auto trading: {sqzmom_config.auto_trading}")
        logger.info(f"  Max positions: {sqzmom_config.max_positions}")
        logger.info("=" * 60)

        yield
    finally:
        try:
            await close_aggregator()
        except Exception as e:
            logger.error(f"Error closing aggregator: {e}")
        try:
            await close_multi_timeframe_analyzer()
        except Exception as e:
            logger.error(f"Error closing multi-timeframe analyzer: {e}")
        try:
            await sqzmom_strategy.close()
        except Exception as e:
            logger.error(f"Error closing sqzmom strategy: {e}")
        logger.info("init_ml: exit")
