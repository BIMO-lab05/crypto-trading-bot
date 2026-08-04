"""
Performance Snapshot Scheduler
Automated daily performance tracking using APScheduler

Responsibilities:
- Take daily performance snapshots at market close (00:00 UTC)
- Store snapshots for all active portfolios
- Handle errors gracefully without disrupting service
- Log snapshot operations for monitoring
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

logger = logging.getLogger(__name__)


class PerformanceSnapshotScheduler:
    """
    Scheduler for automated daily performance snapshots

    Uses APScheduler to run daily snapshot tasks at configured times.
    Integrates with PortfolioManager and PerformanceHistory services.

    Attributes:
        scheduler: APScheduler instance
        portfolio_manager: Reference to portfolio manager service
        performance_history: Reference to performance history service
        snapshot_time: Time to take snapshots (default: 00:00 UTC)
    """

    def __init__(
        self,
        portfolio_manager=None,
        performance_history=None,
        snapshot_hour: int = 0,
        snapshot_minute: int = 0
    ):
        """
        Initialize performance snapshot scheduler

        Args:
            portfolio_manager: PortfolioManager instance
            performance_history: PerformanceHistory instance
            snapshot_hour: Hour to take snapshot (0-23, default: 0 for midnight UTC)
            snapshot_minute: Minute to take snapshot (0-59, default: 0)
        """
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self.portfolio_manager = portfolio_manager
        self.performance_history = performance_history
        self.snapshot_hour = snapshot_hour
        self.snapshot_minute = snapshot_minute
        self.is_running = False

        # Add event listeners for monitoring
        self.scheduler.add_listener(
            self._job_executed_listener,
            EVENT_JOB_EXECUTED
        )
        self.scheduler.add_listener(
            self._job_error_listener,
            EVENT_JOB_ERROR
        )

        logger.info(
            f"PerformanceSnapshotScheduler initialized "
            f"(snapshot time: {snapshot_hour:02d}:{snapshot_minute:02d} UTC)"
        )

    def set_services(self, portfolio_manager, performance_history):
        """
        Set service references after initialization

        Args:
            portfolio_manager: PortfolioManager instance
            performance_history: PerformanceHistory instance
        """
        self.portfolio_manager = portfolio_manager
        self.performance_history = performance_history
        logger.info("Services set for PerformanceSnapshotScheduler")

    async def start(self) -> None:
        """
        Start the scheduler

        Adds jobs and starts the scheduler.
        - Periodic price updates: Always enabled (every 60 seconds)
        - Daily snapshots: Only if performance_history is available

        Safe to call multiple times (won't start if already running).
        """
        if self.is_running:
            logger.warning("Scheduler already running")
            return

        if not self.portfolio_manager:
            logger.error(
                "Cannot start scheduler: portfolio_manager not initialized. "
                "Call set_services() first."
            )
            return

        # Add daily snapshot job (only if performance_history is available)
        if self.performance_history:
            self.scheduler.add_job(
                func=self._take_daily_snapshot,
                trigger=CronTrigger(
                    hour=self.snapshot_hour,
                    minute=self.snapshot_minute,
                    timezone="UTC"
                ),
                id='daily_performance_snapshot',
                name='Daily Performance Snapshot',
                replace_existing=True,
                misfire_grace_time=3600  # Allow 1 hour grace for missed jobs
            )
            logger.info("Daily snapshot job added")
        else:
            logger.warning("Daily snapshot job skipped (performance_history not available)")

        # Add periodic price update job (ALWAYS enabled - every 60 seconds)
        from apscheduler.triggers.interval import IntervalTrigger
        self.scheduler.add_job(
            func=self._update_portfolio_prices,
            trigger=IntervalTrigger(seconds=60),
            id='periodic_price_update',
            name='Periodic Price Update',
            replace_existing=True,
            misfire_grace_time=300  # Allow 5 min grace
        )
        logger.info("Periodic price update job added (every 60 seconds)")

        # Start scheduler
        self.scheduler.start()
        self.is_running = True

        logger.info("Scheduler started successfully")

        # Log next run times
        if self.performance_history:
            next_run = self.scheduler.get_job('daily_performance_snapshot').next_run_time
            logger.info(f"Next snapshot scheduled for: {next_run}")

        price_job = self.scheduler.get_job('periodic_price_update')
        if price_job:
            logger.info(f"Next price update at: {price_job.next_run_time}")

    async def stop(self) -> None:
        """
        Stop the scheduler

        Gracefully shuts down the scheduler, allowing running jobs to complete.
        """
        if not self.is_running:
            logger.warning("Scheduler not running")
            return

        self.scheduler.shutdown(wait=True)
        self.is_running = False
        logger.info("Performance snapshot scheduler stopped")

    async def trigger_manual_snapshot(self) -> Dict[str, Any]:
        """
        Manually trigger a performance snapshot

        Useful for testing or taking snapshots outside the regular schedule.

        Returns:
            Dict with snapshot results
        """
        logger.info("Manual snapshot triggered")
        return await self._take_daily_snapshot(snapshot_type="MANUAL")

    async def _take_daily_snapshot(self, snapshot_type: str = "DAILY") -> Dict[str, Any]:
        """
        Take performance snapshot for all active portfolios

        This is the main job that runs daily at the scheduled time.
        It iterates through all portfolios and creates performance snapshots.

        Args:
            snapshot_type: Type of snapshot (DAILY, MANUAL)

        Returns:
            Dict with results summary
        """
        start_time = datetime.now(timezone.utc)
        logger.info(f"Starting {snapshot_type} performance snapshot at {start_time}")

        results = {
            'timestamp': start_time.isoformat(),
            'snapshot_type': snapshot_type,
            'portfolios_processed': 0,
            'portfolios_failed': 0,
            'errors': []
        }

        try:
            # Get all portfolio IDs
            # For now, we'll use a default set, but this should query active portfolios
            portfolio_ids = await self._get_active_portfolios()

            for portfolio_id in portfolio_ids:
                try:
                    await self._snapshot_portfolio(portfolio_id, snapshot_type)
                    results['portfolios_processed'] += 1
                    logger.info(f"Snapshot saved for portfolio: {portfolio_id}")

                except Exception as e:
                    results['portfolios_failed'] += 1
                    error_msg = f"Failed to snapshot {portfolio_id}: {str(e)}"
                    results['errors'].append(error_msg)
                    logger.error(error_msg, exc_info=True)

            # Calculate duration
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            logger.info(
                f"{snapshot_type} snapshot complete: "
                f"{results['portfolios_processed']} success, "
                f"{results['portfolios_failed']} failed, "
                f"duration: {duration:.2f}s"
            )

            results['duration_seconds'] = duration
            return results

        except Exception as e:
            logger.error(f"Fatal error during snapshot process: {e}", exc_info=True)
            results['errors'].append(f"Fatal error: {str(e)}")
            return results

    async def _snapshot_portfolio(
        self,
        portfolio_id: str,
        snapshot_type: str
    ) -> None:
        """
        Take snapshot for a single portfolio

        Args:
            portfolio_id: Portfolio identifier
            snapshot_type: Type of snapshot (DAILY, MANUAL, EOD)

        Raises:
            Exception: If snapshot fails
        """
        # Sync with Trading Engine to get latest positions. FIX 2026-07-29:
        # sync now mirrors the engine's authoritative cash/P&L/equity, so we do
        # NOT follow it with update_prices() (the old spot recompute) which
        # would clobber the mirrored equity with cash + full notional.
        logger.info(f"Syncing portfolio {portfolio_id} with Trading Engine")
        sync_success = await self.portfolio_manager.sync_with_trading_engine(portfolio_id)
        if not sync_success:
            logger.warning(f"Failed to sync portfolio {portfolio_id} with Trading Engine")
            # Only fall back to the local price refresh when the mirror failed.
            await self.portfolio_manager.update_prices(portfolio_id)

        # Get current portfolio state
        portfolio = self.portfolio_manager.get_portfolio(portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        # Calculate current metrics
        from app.services.performance_calculator import PerformanceCalculator
        calculator = PerformanceCalculator()
        metrics = calculator.calculate_metrics(portfolio)

        # Portfolio equity is the engine-mirrored total_value (cash + unrealized
        # for the leveraged book); positions_value is notional exposure, kept as
        # a separate column. Using portfolio.total_value here keeps the stored
        # history row consistent with what the dashboard shows.
        total_value = portfolio.total_value
        positions_value = Decimal("0")
        for asset in portfolio.assets.values():
            positions_value += asset.quantity * asset.current_price

        # Save snapshot
        await self.performance_history.snapshot_performance(
            portfolio_id=portfolio_id,
            metrics=metrics,
            total_value=total_value,
            cash_balance=portfolio.cash_balance,
            positions_value=positions_value,
            snapshot_type=snapshot_type
        )

    async def _update_portfolio_prices(self) -> None:
        """
        Periodic task to update portfolio prices and sync positions

        Runs every 60 seconds to:
        1. Sync positions with Trading Engine
        2. Update current prices from Market Data service
        3. Recalculate unrealized P&L
        """
        try:
            # Get all active portfolios
            portfolio_ids = await self._get_active_portfolios()

            for portfolio_id in portfolio_ids:
                try:
                    # Sync mirrors the engine's authoritative book. FIX
                    # 2026-07-29: only fall back to the local spot price refresh
                    # when the mirror fails, so we don't clobber mirrored equity.
                    sync_success = await self.portfolio_manager.sync_with_trading_engine(portfolio_id)
                    if sync_success:
                        logger.debug(f"Synced portfolio {portfolio_id} with Trading Engine")
                    else:
                        update_success = await self.portfolio_manager.update_prices(portfolio_id)
                        if update_success:
                            logger.debug(f"Updated prices for portfolio {portfolio_id}")

                except Exception as e:
                    logger.error(f"Error updating portfolio {portfolio_id}: {e}")

        except Exception as e:
            logger.error(f"Error in periodic price update job: {e}", exc_info=True)

    async def _get_active_portfolios(self) -> list[str]:
        """
        Get list of active portfolio IDs.

        Portfolios live in-memory on PortfolioManager (see
        app/services/portfolio_manager.py); there is no persistent
        portfolios table in this service. Returns every portfolio
        currently registered with the manager, falling back to the
        default portfolio if the manager is not wired up.
        """
        if self.portfolio_manager is not None and hasattr(self.portfolio_manager, "list_portfolios"):
            return [p.portfolio_id for p in self.portfolio_manager.list_portfolios()]
        if self.portfolio_manager is not None and hasattr(self.portfolio_manager, "portfolios"):
            return list(self.portfolio_manager.portfolios.keys())
        return ["default"]

    def _job_executed_listener(self, event):
        """
        Event listener for successful job executions

        Args:
            event: APScheduler job execution event
        """
        logger.info(
            f"Scheduled job '{event.job_id}' executed successfully at {event.scheduled_run_time}"
        )

    def _job_error_listener(self, event):
        """
        Event listener for job errors

        Args:
            event: APScheduler job error event
        """
        logger.error(
            f"Scheduled job '{event.job_id}' failed: {event.exception}",
            exc_info=True
        )

    def get_next_run_time(self) -> Optional[datetime]:
        """
        Get next scheduled snapshot time

        Returns:
            Next run datetime or None if scheduler not running
        """
        if not self.is_running:
            return None

        job = self.scheduler.get_job('daily_performance_snapshot')
        if job:
            return job.next_run_time
        return None

    def get_scheduler_status(self) -> Dict[str, Any]:
        """
        Get scheduler status information

        Returns:
            Dict with scheduler status details
        """
        status = {
            'is_running': self.is_running,
            'snapshot_time': f"{self.snapshot_hour:02d}:{self.snapshot_minute:02d} UTC",
            'next_run_time': None,
            'jobs_count': 0
        }

        if self.is_running:
            next_run = self.get_next_run_time()
            status['next_run_time'] = next_run.isoformat() if next_run else None
            status['jobs_count'] = len(self.scheduler.get_jobs())

        return status
