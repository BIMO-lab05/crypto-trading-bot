"""Risk/execution-layer lifespan phase: risk budget, smart router, execution scheduler."""

import logging
from contextlib import asynccontextmanager

from app.execution.execution_scheduler import get_execution_scheduler
from app.execution.smart_router import get_smart_router
from app.risk.dynamic_risk_budget import get_risk_budget_manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def init_risk():
    """Risk budget (Phase 3.3) + smart router (Phase 4.1) + execution scheduler (Phase 4.2).

    Pure relocation from main.py. CLAUDE.md guard: do NOT relax 2% per-trade
    or 5% daily-loss caps in risk_budget_manager during this move.
    """
    logger.info("init_risk: enter")

    try:
        try:
            risk_budget_manager = get_risk_budget_manager()
            logger.info("[OK] Dynamic Risk Budget Manager initialized (Phase 3.3)")
            budget = risk_budget_manager.calculate_risk_budget()
            logger.info(
                f"     Base equity: ${risk_budget_manager.config.base_equity:,.0f}"
            )
            logger.info(
                f"     Risk budget: {budget.adjusted_budget_pct:.2f}% "
                f"(${budget.adjusted_budget_usd:,.0f})"
            )
            logger.info(f"     Risk level: {budget.risk_level}")
            logger.info(f"     Market regime: {budget.market_regime.value}")
        except Exception as e:
            logger.warning(
                f"[WARN] Failed to initialize Dynamic Risk Budget Manager: {e}"
            )

        try:
            smart_router = get_smart_router()
            logger.info("[OK] Smart Order Router initialized (Phase 4.1)")
            status = smart_router.get_status()
            logger.info(
                f"     Tight spread threshold: "
                f"{status.get('config', {}).get('tight_spread_threshold', 'N/A')}"
            )
        except Exception as e:
            logger.warning(f"[WARN] Failed to initialize Smart Order Router: {e}")

        try:
            execution_scheduler = get_execution_scheduler()
            await execution_scheduler.start()
            logger.info("[OK] Execution Scheduler initialized (Phase 4.2)")
            scheduler_status = execution_scheduler.get_scheduler_status()
            logger.info(
                f"     Max concurrent orders: "
                f"{scheduler_status['config']['max_concurrent_orders']}"
            )
            logger.info(
                f"     Default participation: "
                f"{scheduler_status['config']['default_participation_rate']:.0%}"
            )
        except Exception as e:
            logger.warning(f"[WARN] Failed to initialize Execution Scheduler: {e}")

        yield
    finally:
        try:
            execution_scheduler = get_execution_scheduler()
            await execution_scheduler.stop(wait_for_completion=True)
            logger.info("Execution Scheduler stopped")
        except Exception as e:
            logger.error(f"Error stopping Execution Scheduler: {e}")
        logger.info("init_risk: exit")
