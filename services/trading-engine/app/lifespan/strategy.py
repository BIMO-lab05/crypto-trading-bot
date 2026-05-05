"""Strategy-layer lifespan phase: correlation manager, Kelly position sizer."""

import logging
from contextlib import asynccontextmanager

from app.config import get_settings
from app.risk import get_correlation_manager
from app.risk.kelly_position_sizing import get_kelly_sizer

logger = logging.getLogger(__name__)


@asynccontextmanager
async def init_strategy():
    """Correlation manager (Phase 3.1) + Kelly sizer (Phase 3.2).

    Pure relocation from main.py. CLAUDE.md guard: do NOT change Kelly
    fraction caps or correlation thresholds during this move.
    """
    logger.info("init_strategy: enter")
    settings = get_settings()

    try:
        try:
            correlation_manager = get_correlation_manager()
            await correlation_manager.initialize(redis_url=settings.redis_url)
            logger.info("[OK] Correlation Manager initialized (Phase 3.1)")
        except Exception as e:
            logger.warning(f"[WARN] Failed to initialize Correlation Manager: {e}")

        try:
            kelly_sizer = get_kelly_sizer()
            logger.info("[OK] Kelly Position Sizer initialized (Phase 3.2)")
            logger.info(
                f"     Default fraction: {kelly_sizer.default_kelly_fraction * 100:.0f}%"
            )
            logger.info(f"     Max position: {kelly_sizer.MAX_POSITION_PCT:.0f}%")
        except Exception as e:
            logger.warning(f"[WARN] Failed to initialize Kelly Position Sizer: {e}")

        yield
    finally:
        try:
            correlation_manager = get_correlation_manager()
            await correlation_manager.close()
            logger.info("Correlation Manager closed")
        except Exception as e:
            logger.error(f"Error closing Correlation Manager: {e}")
        logger.info("init_strategy: exit")
