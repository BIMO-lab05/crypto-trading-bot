"""
Market Data Service - Data Collection Scheduler
Purpose: Automated scheduled collection of market data from Bybit
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import errno
import fcntl
import logging
import os
import time
from typing import List
import asyncio

from app.fetcher import BybitDataFetcher, get_interval_minutes
from app.repository import (
    KlineRepository,
    OpenInterestRepository,  # noqa: F401 - patched via app.scheduler.OpenInterestRepository in tests
    OrderbookRepository,
    TickerRepository,
)
from app.config import get_settings

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: AsyncIOScheduler = None

# Held for the process lifetime by whichever uvicorn worker owns the scheduler.
# Kept at module scope so the fd is never garbage-collected (which would drop
# the lock and let a second worker start a duplicate scheduler).
_owner_lock_fd = None

# Runs are dropped by APScheduler if they fire later than this many seconds
# past their deadline. The default is 1 second, which this service cannot meet:
# it serves heavy kline reads from technical-analysis, so the event loop
# routinely delays a fire by 2-20s. That silently killed ingest entirely
# (audit DL-1). Grace is set generous relative to each interval -- a busy loop
# should *delay* a collection, never cancel it.
_INTERVAL_JOB_GRACE_SECONDS = 240  # 5-minute jobs
_HOURLY_JOB_GRACE_SECONDS = 1800  # hourly backup job

_SCHEDULER_LOCK_PATH = "/tmp/market-data-scheduler.lock"

# Module-level lazy singleton for the orderbook job only (final review H-2).
# Every other job still constructs a fresh BybitDataFetcher per tick and
# closes it in `finally` -- unchanged. The orderbook job runs every 5s (vs.
# 5min/1h elsewhere), so building a fresh 100-connection httpx pool and
# tearing it down every tick meant 17k fetcher lifecycles/day and zero
# keepalive reuse across ticks; that churn was the main cadence lever.
# Closed in stop_scheduler().
_orderbook_fetcher: BybitDataFetcher = None

# Bounds concurrent in-flight orderbook requests per tick (final review H-2).
# 14 symbols fully concurrent would burst the connector's rate limiter
# (final review H-4); 8 keeps a tick's burst well under it while still
# collapsing 14 sequential round trips into ~2 waves.
_ORDERBOOK_CONCURRENCY = 8


def _get_orderbook_fetcher() -> BybitDataFetcher:
    global _orderbook_fetcher
    if _orderbook_fetcher is None:
        _orderbook_fetcher = BybitDataFetcher()
    return _orderbook_fetcher


def _reset_orderbook_fetcher_for_tests() -> None:
    """Test-only escape hatch for the module-level singleton above. Without
    this, a test that patches BybitDataFetcher or app.scheduler.BybitDataFetcher
    after an earlier test already populated `_orderbook_fetcher` gets a stale
    instance instead of its own mock -- the singleton is process-global and
    outlives any one test's patch context. Call from an autouse fixture."""
    global _orderbook_fetcher
    _orderbook_fetcher = None


def _claim_scheduler_ownership() -> bool:
    """
    Return True if this process should own the collection scheduler.

    The service runs under `uvicorn --workers N`. Each worker is a separate
    process with its own module state, so the `_scheduler is not None` guard
    cannot see a sibling -- every worker used to start its own scheduler and
    register the same three jobs, doubling Bybit API load and duplicating
    ticker rows.

    An flock on a shared path elects exactly one owner regardless of worker
    count, without giving up the extra worker's read throughput. The lock is
    released automatically when the process dies, so a crashed owner is
    replaced on the next boot rather than leaving ingest permanently dead.
    """
    global _owner_lock_fd

    # Already the owner. flock is per open-file-description, so re-acquiring on
    # a second fd from this same process would conflict with the one we already
    # hold and lock us out of our own scheduler -- which happens on any
    # start -> stop -> start cycle via the /api/v1/scheduler/* endpoints.
    if _owner_lock_fd is not None:
        return True

    try:
        fd = os.open(_SCHEDULER_LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o644)
    except OSError as exc:
        # Never trade ingest for a lock we couldn't create. Degrading to
        # "every worker schedules" is strictly better than "nobody does".
        logger.warning(
            f"Could not open scheduler lock {_SCHEDULER_LOCK_PATH} ({exc}); "
            f"starting scheduler unconditionally in pid {os.getpid()}"
        )
        return True

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(fd)
        if exc.errno in (errno.EACCES, errno.EAGAIN):
            logger.info(
                f"Scheduler owned by another worker; pid {os.getpid()} will "
                f"serve reads only and run no collection jobs"
            )
            return False
        raise

    _owner_lock_fd = fd
    return True


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
                            k for k in klines if k["timestamp"] + interval_ms <= now_ms
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


async def collect_orderbook_data():
    """Scheduled job: top-25 orderbook snapshot per pair. Runs every 5 seconds.

    max_instances=1 + coalesce=True at registration make a slow tick SKIP
    the next rather than queue (spec A1 rate-limit rule).

    Reworked per final review H-2/M-6: symbols fetch concurrently (bounded by
    a semaphore) against a fetcher reused across ticks, and successful
    snapshots are written in one batched session instead of one session per
    symbol. This is what moved achieved cadence back toward the 5s target
    instead of the ~6.1s/18%-loss measured against the old sequential,
    per-tick-fetcher, per-snapshot-session implementation.
    """
    fetcher = _get_orderbook_fetcher()
    repo = OrderbookRepository()
    semaphore = asyncio.Semaphore(_ORDERBOOK_CONCURRENCY)

    async def _fetch_one(symbol: str):
        async with semaphore:
            try:
                return await fetcher.get_orderbook(symbol, limit=25)
            except Exception as e:
                logger.error(f"❌ Error collecting orderbook for {symbol}: {e}")
                return None

    symbols = _trading_pairs()
    results = await asyncio.gather(*(_fetch_one(s) for s in symbols))
    snapshots = [r for r in results if r]
    error_count = len(symbols) - len(snapshots)

    success_count = await repo.save_snapshots_bulk(snapshots) if snapshots else 0
    if success_count < len(snapshots):
        error_count += len(snapshots) - success_count

    if error_count:
        logger.warning(
            f"📖 Orderbook collection: {success_count} ok, {error_count} errors"
        )


async def collect_open_interest_data():
    """Scheduled job: OI history page per pair. Runs every 5 minutes.
    First run per symbol naturally backfills the endpoint's max window (spec A2).
    """
    fetcher = BybitDataFetcher()
    repo = OpenInterestRepository()
    try:
        for symbol in _trading_pairs():
            try:
                rows = await fetcher.get_open_interest(symbol)
                if rows:
                    n = await repo.bulk_upsert(rows)
                    logger.info(f"📈 OI {symbol}: upserted {n} rows")
            except Exception as e:
                logger.error(f"❌ Error collecting OI for {symbol}: {e}")
    finally:
        await fetcher.close()


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

    if not _claim_scheduler_ownership():
        return

    logger.info(f"🚀 Initializing data collection scheduler (pid {os.getpid()})")

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
        misfire_grace_time=_INTERVAL_JOB_GRACE_SECONDS,
        coalesce=True,
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
        misfire_grace_time=_INTERVAL_JOB_GRACE_SECONDS,
        coalesce=True,
    )
    logger.info("✅ Scheduled: Kline collection every 5 minutes (offset +2min)")

    # Job: orderbook snapshots every 5 seconds (edge-search v2 A1)
    _scheduler.add_job(
        collect_orderbook_data,
        trigger=IntervalTrigger(seconds=5),
        id="orderbook_collection",
        name="Orderbook Snapshot Collection",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=4,  # < interval: a missed tick is dropped, not queued
        coalesce=True,
    )
    logger.info("✅ Scheduled: Orderbook snapshots every 5 seconds")

    # Job: open-interest history every 5 minutes, offset +3min (edge-search v2 A2)
    _scheduler.add_job(
        collect_open_interest_data,
        trigger=IntervalTrigger(minutes=5, start_date="2024-01-01 00:03:00"),
        id="open_interest_collection",
        name="Open Interest Collection",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=_INTERVAL_JOB_GRACE_SECONDS,
        coalesce=True,
    )
    logger.info("✅ Scheduled: Open interest collection every 5 minutes (offset +3min)")

    # Job 3: Hourly comprehensive collection (backup)
    _scheduler.add_job(
        collect_all_data,
        trigger=CronTrigger(minute=0),  # Top of every hour
        id="hourly_full_collection",
        name="Hourly Full Data Collection",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=_HOURLY_JOB_GRACE_SECONDS,
        coalesce=True,
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

    # Release the orderbook job's reused connection pool (final review H-2).
    # stop_scheduler() is sync but only ever called from an async context in
    # production (FastAPI shutdown / the stop handler); tests may call it
    # with no running loop, so this degrades to a warning rather than raising.
    global _orderbook_fetcher
    if _orderbook_fetcher is not None:
        fetcher_to_close = _orderbook_fetcher
        _orderbook_fetcher = None
        try:
            asyncio.get_running_loop().create_task(fetcher_to_close.close())
        except RuntimeError:
            logger.warning(
                "No running event loop to close the orderbook fetcher's "
                "connection pool on scheduler stop"
            )

    # Release ownership so a restarting worker can claim it immediately rather
    # than waiting for this process to exit.
    global _owner_lock_fd
    if _owner_lock_fd is not None:
        try:
            fcntl.flock(_owner_lock_fd, fcntl.LOCK_UN)
            os.close(_owner_lock_fd)
        except OSError as exc:
            logger.warning(f"Failed to release scheduler lock: {exc}")
        finally:
            _owner_lock_fd = None

    logger.info("✅ Scheduler stopped successfully")


def get_scheduler_status() -> dict:
    """
    Get current scheduler status and job information

    Returns:
        dict: Scheduler status including running jobs
    """
    if _scheduler is None:
        # Under `uvicorn --workers N` only one worker owns the scheduler, and
        # this endpoint is served round-robin. Say *why* there is no scheduler
        # here, so a non-owner worker answering the probe doesn't read as
        # "ingest is down".
        return {
            "running": False,
            "jobs": [],
            "job_count": 0,
            "scheduler_owner": False,
            "pid": os.getpid(),
            "detail": "This worker does not own the scheduler; another worker runs collection.",
        }

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

    return {
        "running": _scheduler.running,
        "jobs": jobs,
        "job_count": len(jobs),
        "scheduler_owner": True,
        "pid": os.getpid(),
    }


async def run_manual_collection():
    """
    Manually trigger data collection (useful for testing)
    """
    logger.info("🔧 Manual data collection triggered")
    await collect_all_data()
