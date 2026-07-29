"""
Market Data Service - Data Collection Scheduler
Purpose: Automated scheduled collection of market data from Bybit
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import logging
import time
from typing import List
import asyncio

from app.fetcher import BybitDataFetcher, get_interval_minutes
from app.repository import KlineRepository, TickerRepository
from app.config import get_settings

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: AsyncIOScheduler = None


# Trading pairs to collect data for.
#
# 2026-05-15: Switched from hardcoded module-level constant to settings-driven
# accessor. The old hardcoded list silently re-added XRPUSDT + DOGEUSDT,
# violating the "no silent re-add" project rule (CLAUDE.md). The single source
# of truth for which symbols this service ingests is now
# `config.Settings.default_symbols` (exposed via `symbols_list` property).
def _trading_pairs() -> List[str]:
    """Return the active trading pair list from settings."""
    return get_settings().symbols_list


def __getattr__(name: str):
    # Backward-compatible accessor: existing tests / external callers do
    # `from app.scheduler import TRADING_PAIRS`. Resolve dynamically from
    # settings so the deprecated symbol stays in sync with the new source
    # of truth instead of drifting back into a hardcoded list.
    if name == "TRADING_PAIRS":
        return _trading_pairs()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Kline intervals to collect
KLINE_INTERVALS = [
    "1",  # 1 minute
    "5",  # 5 minutes
    "15",  # 15 minutes
    "60",  # 1 hour
    "240",  # 4 hours
    "D",  # Daily
]


async def collect_ticker_data():
    """
    Scheduled job: Collect ticker data for all trading pairs
    Runs every 5 minutes
    """
    logger.info("📊 Starting scheduled ticker data collection")

    fetcher = BybitDataFetcher()
    ticker_repo = TickerRepository()

    success_count = 0
    error_count = 0

    try:
        for symbol in _trading_pairs():
            try:
                # Fetch ticker data
                ticker_data = await fetcher.get_ticker(symbol=symbol)

                if ticker_data:
                    # Save to database
                    await ticker_repo.save_ticker(ticker_data)
                    success_count += 1
                    logger.info(f"✅ Collected ticker for {symbol}")
                else:
                    logger.warning(f"⚠️ No ticker data returned for {symbol}")
                    error_count += 1

            except Exception as e:
                logger.error(f"❌ Error collecting ticker for {symbol}: {e}")
                error_count += 1
    finally:
        # Always release the httpx connection pool. A new BybitDataFetcher
        # (100-connection pool) is created every scheduled run; without this
        # close() the pools leaked every 5 minutes and eventually exhausted
        # sockets / file descriptors.
        await fetcher.close()

    logger.info(
        f"📊 Ticker collection complete: {success_count} success, {error_count} errors"
    )


async def collect_kline_data():
    """
    Scheduled job: Collect kline/candlestick data for all pairs and intervals
    Runs every 5 minutes
    """
    logger.info("📈 Starting scheduled kline data collection")

    fetcher = BybitDataFetcher()
    kline_repo = KlineRepository()

    success_count = 0
    error_count = 0

    try:
      for symbol in _trading_pairs():
        for interval in KLINE_INTERVALS:
            try:
                # Fetch kline data (last 200 candles)
                klines = await fetcher.get_kline(
                    symbol=symbol, interval=interval, limit=200
                )

                # Defensive filter: fetcher.get_kline already discards the
                # still-forming (unclosed) candle — Bybit returns it as the
                # newest entry — but re-check here so a future fetcher
                # change cannot silently re-introduce partial-candle
                # pollution into the database. A candle is closed only when
                # timestamp + interval_duration <= now.
                if klines:
                    interval_ms = get_interval_minutes(interval) * 60 * 1000
                    now_ms = int(time.time() * 1000)
                    n_before = len(klines)
                    klines = [
                        k for k in klines
                        if k["timestamp"] + interval_ms <= now_ms
                    ]
                    if len(klines) < n_before:
                        logger.debug(
                            f"Dropped {n_before - len(klines)} still-forming "
                            f"candle(s) for {symbol} ({interval}) before store"
                        )

                if klines:
                    # Add symbol and interval to each kline
                    for kline in klines:
                        kline["symbol"] = symbol
                        kline["interval"] = interval

                    # Bulk insert/update
                    inserted = await kline_repo.bulk_upsert(klines)
                    success_count += 1
                    logger.info(
                        f"✅ Collected {inserted} klines for {symbol} ({interval})"
                    )
                else:
                    logger.warning(
                        f"⚠️ No kline data returned for {symbol} ({interval})"
                    )
                    error_count += 1

            except Exception as e:
                logger.error(
                    f"❌ Error collecting klines for {symbol} ({interval}): {e}"
                )
                error_count += 1

            # Small delay to avoid rate limits
            await asyncio.sleep(0.5)
    finally:
        # Always release the httpx connection pool (see collect_ticker_data).
        await fetcher.close()

    logger.info(
        f"📈 Kline collection complete: {success_count} success, {error_count} errors"
    )


async def collect_all_data():
    """
    Scheduled job: Collect both ticker and kline data
    Runs every 5 minutes (can be adjusted)
    """
    logger.info("🔄 Starting full data collection cycle")

    try:
        # Collect ticker data
        await collect_ticker_data()

        # Wait a bit before klines
        await asyncio.sleep(2)

        # Collect kline data
        await collect_kline_data()

        logger.info("✅ Full data collection cycle complete")

    except Exception as e:
        logger.error(f"❌ Error in full data collection: {e}")


def start_scheduler():
    """
    Initialize and start the APScheduler for automated data collection
    """
    global _scheduler

    if _scheduler is not None:
        logger.warning("Scheduler already running")
        return

    logger.info("🚀 Initializing data collection scheduler")

    # Create AsyncIO scheduler
    _scheduler = AsyncIOScheduler()

    # Job 1: Collect ticker data every 5 minutes
    _scheduler.add_job(
        collect_ticker_data,
        trigger=IntervalTrigger(minutes=5),
        id="ticker_collection",
        name="Ticker Data Collection",
        replace_existing=True,
        max_instances=1,  # Only one instance at a time
    )
    logger.info("✅ Scheduled: Ticker collection every 5 minutes")

    # Job 2: Collect kline data every 5 minutes (offset by 2 minutes)
    _scheduler.add_job(
        collect_kline_data,
        trigger=IntervalTrigger(minutes=5, start_date="2024-01-01 00:02:00"),
        id="kline_collection",
        name="Kline Data Collection",
        replace_existing=True,
        max_instances=1,
    )
    logger.info("✅ Scheduled: Kline collection every 5 minutes (offset +2min)")

    # Job 3: Hourly comprehensive collection (backup)
    _scheduler.add_job(
        collect_all_data,
        trigger=CronTrigger(minute=0),  # Top of every hour
        id="hourly_full_collection",
        name="Hourly Full Data Collection",
        replace_existing=True,
        max_instances=1,
    )
    logger.info("✅ Scheduled: Full data collection every hour")

    # Start the scheduler
    _scheduler.start()
    logger.info("🎯 Scheduler started successfully - automated data collection active!")

    # Log next run times
    for job in _scheduler.get_jobs():
        logger.info(f"📅 Job '{job.name}' next run: {job.next_run_time}")


def stop_scheduler():
    """
    Stop the scheduler gracefully
    """
    global _scheduler

    if _scheduler is None:
        logger.warning("Scheduler not running")
        return

    logger.info("🛑 Stopping scheduler...")
    _scheduler.shutdown(wait=True)
    _scheduler = None
    logger.info("✅ Scheduler stopped successfully")


def get_scheduler_status() -> dict:
    """
    Get current scheduler status and job information

    Returns:
        dict: Scheduler status including running jobs
    """
    if _scheduler is None:
        return {"running": False, "jobs": []}

    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append(
            {
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
        )

    return {"running": _scheduler.running, "jobs": jobs, "job_count": len(jobs)}


async def run_manual_collection():
    """
    Manually trigger data collection (useful for testing)
    """
    logger.info("🔧 Manual data collection triggered")
    await collect_all_data()
