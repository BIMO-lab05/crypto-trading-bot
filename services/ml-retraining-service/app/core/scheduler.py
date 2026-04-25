"""
Retraining Scheduler System
Purpose: Automate periodic model retraining on schedule or on-demand
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor

from app.config.settings import get_settings
from app.database.database import get_db
from app.database.models import RetrainingJob, JobStatus, TriggerType
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import httpx

logger = logging.getLogger(__name__)


class RetrainingScheduler:
    """
    Manages scheduled and on-demand retraining jobs

    Features:
    - Weekly automated retraining (Monday 2AM UTC)
    - On-demand manual triggers via API
    - Job queue management to prevent overlaps
    - Retry logic for failed jobs
    - Job status tracking
    """

    def __init__(self):
        """Initialize the retraining scheduler"""
        self.settings = get_settings()
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.running_jobs: Dict[str, str] = {}  # symbol -> job_id mapping
        self.is_running = False

        # Configure APScheduler
        jobstores = {
            'default': MemoryJobStore()
        }
        executors = {
            'default': AsyncIOExecutor()
        }
        job_defaults = {
            'coalesce': True,  # Combine missed executions
            'max_instances': 1,  # Only one instance per job
            'misfire_grace_time': 3600  # 1 hour grace period
        }

        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone='UTC'
        )

    async def start(self):
        """Start the scheduler"""
        if self.is_running:
            logger.warning("Scheduler already running")
            return

        logger.info("Starting retraining scheduler...")

        # Add scheduled jobs if enabled
        if self.settings.retrain_schedule_enabled:
            await self._add_scheduled_jobs()

        # Start the scheduler
        self.scheduler.start()
        self.is_running = True

        logger.info(f"Scheduler started successfully. Scheduled jobs: {len(self.scheduler.get_jobs())}")

    async def stop(self):
        """Stop the scheduler"""
        if not self.is_running:
            logger.warning("Scheduler not running")
            return

        logger.info("Stopping retraining scheduler...")

        # Wait for running jobs to complete (max 30 seconds)
        if self.running_jobs:
            logger.info(f"Waiting for {len(self.running_jobs)} running jobs to complete...")
            await asyncio.sleep(30)

        self.scheduler.shutdown(wait=False)
        self.is_running = False

        logger.info("Scheduler stopped successfully")

    async def _add_scheduled_jobs(self):
        """Add scheduled retraining jobs based on configuration"""
        # Parse cron expression
        cron_parts = self.settings.retrain_schedule_cron.split()

        if len(cron_parts) != 5:
            logger.error(f"Invalid cron expression: {self.settings.retrain_schedule_cron}")
            return

        minute, hour, day, month, day_of_week = cron_parts

        # Add job for each symbol
        for symbol in self.settings.retrain_data_symbols:
            job_id = f"retrain_{symbol}_scheduled"

            self.scheduler.add_job(
                self._execute_scheduled_retrain,
                trigger=CronTrigger(
                    minute=minute,
                    hour=hour,
                    day=day,
                    month=month,
                    day_of_week=day_of_week,
                    timezone='UTC'
                ),
                id=job_id,
                name=f"Scheduled retraining for {symbol}",
                args=[symbol],
                replace_existing=True
            )

            logger.info(
                f"Added scheduled job for {symbol}: "
                f"{minute} {hour} {day} {month} {day_of_week} UTC"
            )

    async def _execute_scheduled_retrain(self, symbol: str):
        """
        Execute scheduled retraining for a symbol

        Args:
            symbol: Trading symbol to retrain
        """
        logger.info(f"Executing scheduled retraining for {symbol}")

        try:
            # Check if already running for this symbol
            if symbol in self.running_jobs:
                logger.warning(
                    f"Retraining already in progress for {symbol} "
                    f"(job_id: {self.running_jobs[symbol]})"
                )
                return

            # Trigger retraining via internal API call
            result = await self._trigger_retrain_api(
                symbol=symbol,
                trigger_type=TriggerType.SCHEDULED,
                triggered_by="scheduler"
            )

            if result.get('success'):
                job_id = result.get('job_id')
                self.running_jobs[symbol] = job_id
                logger.info(f"Started retraining job {job_id} for {symbol}")

                # Monitor job completion in background
                asyncio.create_task(self._monitor_job_completion(symbol, job_id))
            else:
                logger.error(f"Failed to start retraining for {symbol}: {result.get('error')}")

        except Exception as e:
            logger.error(f"Error executing scheduled retraining for {symbol}: {e}", exc_info=True)

    async def _trigger_retrain_api(
        self,
        symbol: str,
        trigger_type: TriggerType,
        triggered_by: str,
        interval: str = "60"
    ) -> Dict[str, Any]:
        """
        Trigger retraining via internal API call

        Args:
            symbol: Trading symbol
            trigger_type: Type of trigger (SCHEDULED/MANUAL/API)
            triggered_by: Who triggered the job
            interval: Candle interval

        Returns:
            API response dict
        """
        try:
            # Build API URL (internal call to same service)
            base_url = f"http://{self.settings.service_host}:{self.settings.service_port}"
            url = f"{base_url}/api/v1/retrain/{symbol}"

            params = {
                "interval": interval,
                "auto_validate": True,
                "auto_deploy": self.settings.retrain_auto_deploy
            }

            # Make async HTTP request
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(url, params=params)

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "job_id": data.get("job_id"),
                        "data": data
                    }
                else:
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}: {response.text}"
                    }

        except Exception as e:
            logger.error(f"Error calling retrain API for {symbol}: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def _monitor_job_completion(self, symbol: str, job_id: str):
        """
        Monitor job completion and clean up running_jobs dict

        Args:
            symbol: Trading symbol
            job_id: Job ID to monitor
        """
        try:
            # Poll job status every 30 seconds
            max_wait_time = 3600  # 1 hour max
            elapsed = 0

            while elapsed < max_wait_time:
                await asyncio.sleep(30)
                elapsed += 30

                # Check job status in database
                async for session in get_db():
                    try:
                        result = await session.execute(
                            select(RetrainingJob).where(RetrainingJob.job_id == job_id)
                        )
                        job = result.scalars().first()

                        if job and job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                            # Job finished
                            logger.info(
                                f"Job {job_id} for {symbol} completed with status: {job.status}"
                            )

                            # Remove from running jobs
                            if symbol in self.running_jobs:
                                del self.running_jobs[symbol]

                            return
                    finally:
                        await session.close()

            # Timeout - job still running after max wait
            logger.warning(
                f"Job {job_id} for {symbol} still running after {max_wait_time}s"
            )
            if symbol in self.running_jobs:
                del self.running_jobs[symbol]

        except Exception as e:
            logger.error(f"Error monitoring job {job_id}: {e}", exc_info=True)
            # Clean up on error
            if symbol in self.running_jobs:
                del self.running_jobs[symbol]

    async def trigger_manual_retrain(
        self,
        symbols: Optional[List[str]] = None,
        triggered_by: str = "manual"
    ) -> Dict[str, Any]:
        """
        Trigger manual retraining for one or more symbols

        Args:
            symbols: List of symbols to retrain (None = all configured symbols)
            triggered_by: Who triggered the retraining

        Returns:
            Dict with results for each symbol
        """
        if symbols is None:
            symbols = self.settings.retrain_data_symbols

        logger.info(f"Manual retraining triggered for {len(symbols)} symbols by {triggered_by}")

        results = {}

        for symbol in symbols:
            # Check if already running
            if symbol in self.running_jobs:
                results[symbol] = {
                    "success": False,
                    "error": f"Already running (job_id: {self.running_jobs[symbol]})"
                }
                continue

            # Trigger retraining
            result = await self._trigger_retrain_api(
                symbol=symbol,
                trigger_type=TriggerType.MANUAL,
                triggered_by=triggered_by
            )

            if result.get('success'):
                job_id = result.get('job_id')
                self.running_jobs[symbol] = job_id

                # Monitor in background
                asyncio.create_task(self._monitor_job_completion(symbol, job_id))

                results[symbol] = {
                    "success": True,
                    "job_id": job_id
                }
            else:
                results[symbol] = result

        logger.info(f"Manual retraining initiated for {len([r for r in results.values() if r.get('success')])} symbols")

        return {
            "triggered_symbols": len(symbols),
            "successful": len([r for r in results.values() if r.get('success')]),
            "failed": len([r for r in results.values() if not r.get('success')]),
            "results": results
        }

    def get_scheduled_jobs(self) -> List[Dict[str, Any]]:
        """
        Get list of scheduled jobs

        Returns:
            List of job information dicts
        """
        if not self.scheduler:
            return []

        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "job_id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            })

        return jobs

    def get_running_jobs(self) -> Dict[str, str]:
        """
        Get currently running retraining jobs

        Returns:
            Dict mapping symbol to job_id
        """
        return self.running_jobs.copy()

    async def pause_scheduled_jobs(self):
        """Pause all scheduled jobs"""
        if not self.scheduler:
            return

        self.scheduler.pause()
        logger.info("Scheduled jobs paused")

    async def resume_scheduled_jobs(self):
        """Resume all scheduled jobs"""
        if not self.scheduler:
            return

        self.scheduler.resume()
        logger.info("Scheduled jobs resumed")

    def is_scheduler_running(self) -> bool:
        """Check if scheduler is running"""
        return self.is_running and (self.scheduler.running if self.scheduler else False)


# Global scheduler instance
_scheduler: Optional[RetrainingScheduler] = None


async def get_scheduler() -> RetrainingScheduler:
    """
    Get the global scheduler instance

    Returns:
        RetrainingScheduler instance
    """
    global _scheduler

    if _scheduler is None:
        _scheduler = RetrainingScheduler()

    return _scheduler


async def start_scheduler():
    """Start the global scheduler"""
    scheduler = await get_scheduler()
    await scheduler.start()


async def stop_scheduler():
    """Stop the global scheduler"""
    global _scheduler

    if _scheduler:
        await _scheduler.stop()
        _scheduler = None
