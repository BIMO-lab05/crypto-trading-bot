"""
Market Data Service - Database Connection
Purpose: Manage database connections and sessions
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from contextlib import asynccontextmanager
import logging

from app.config import get_settings
from app.models import Base

logger = logging.getLogger(__name__)

# Global engine and session maker
_engine = None
_async_session_maker = None


def get_engine():
    """Get or create database engine"""
    global _engine

    if _engine is None:
        settings = get_settings()

        # Use TimescaleDB for market data storage
        _engine = create_async_engine(
            settings.timescale_url,  # Changed from postgres_url to timescale_url
            echo=settings.debug,  # Log SQL queries in debug mode
            pool_size=settings.db_pool_min_size,
            max_overflow=settings.db_pool_max_size - settings.db_pool_min_size,
            pool_pre_ping=True,  # Verify connections before using
            pool_recycle=3600,  # Recycle connections after 1 hour
        )

        logger.info(
            f"Created database engine for TimescaleDB: {settings.timescale_host}:{settings.timescale_port}"
        )

    return _engine


def get_session_maker():
    """Get or create session maker"""
    global _async_session_maker

    if _async_session_maker is None:
        engine = get_engine()
        _async_session_maker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        logger.info("Created async session maker")

    return _async_session_maker


@asynccontextmanager
async def get_db_session():
    """
    Get database session context manager

    Usage:
        async with get_db_session() as session:
            # Use session
            result = await session.execute(...)
    """
    session_maker = get_session_maker()
    session = session_maker()

    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"Database error, rolling back: {e}")
        raise
    finally:
        await session.close()


async def init_database(max_retries: int = 10, retry_delay: float = 2.0):
    """
    Initialize database (create tables) with retry logic

    Handles the case where database is still starting up by retrying
    the connection with exponential backoff.

    Args:
        max_retries: Maximum number of connection attempts
        retry_delay: Initial delay between retries (doubles each attempt)
    """
    import asyncio

    engine = get_engine()
    last_error = None

    for attempt in range(max_retries):
        try:
            async with engine.begin() as conn:
                # Create all tables
                await conn.run_sync(Base.metadata.create_all)
                logger.info("Database tables created")
                return  # Success - exit function

        except Exception as e:
            last_error = e
            wait_time = retry_delay * (2**attempt)  # Exponential backoff
            logger.warning(
                f"Database connection attempt {attempt + 1}/{max_retries} failed: {e}. "
                f"Retrying in {wait_time:.1f}s..."
            )
            await asyncio.sleep(wait_time)

    # All retries exhausted
    logger.error(f"Failed to connect to database after {max_retries} attempts")
    raise last_error


# ---------------------------------------------------------------------------
# Boot DDL (RES-02) — one ordered, schema-qualified statement sequence.
#
# Each entry is `(label, statement, level)`. `level` selects the log level used
# when that statement fails: "error" for statements that MUST converge for the
# intended DB state to exist, "warning" for ones that legitimately no-op against
# an already-migrated database. Failures are ALWAYS swallowed by
# `_run_isolated` — `app/main.py` wraps this call but must keep booting against
# a plain (non-TimescaleDB) PostgreSQL, so DDL is never fatal.
#
# ORDER IS LOAD-BEARING. TimescaleDB enforces each of these dependencies:
#   * the integer-now function must exist before `set_integer_now_func` names it
#   * a table must already BE a hypertable before `set_integer_now_func` on it
#   * an integer time dimension must have an integer-now function registered
#     before any retention policy can be created on it
#
# Every table reference is schema-qualified `public.`.
# `infrastructure/scripts/init-timescale.sql` created four never-used shadow
# hypertables under the `market_data` schema; an unqualified name can resolve to
# one of those depending on `search_path`.
#
# Why this was rewritten (verified live 2026-08-16, TimescaleDB 2.26.3):
#   * `klines` and `tickers` are partitioned on `timestamp BIGINT` (epoch ms)
#     with `integer_now_func = NULL`. An INTERVAL-based retention window can
#     never apply to an integer time dimension, so
#     `timescaledb_information.jobs` held ZERO retention jobs.
#   * `public.orderbook_snapshots` carried `PRIMARY KEY (id)` only, so
#     `create_hypertable` refused it — every unique index must include the
#     partition column. The table had never been a hypertable.
# Both failures were swallowed as warnings, so the service booted green and
# nobody noticed. Hence the "error" levels below.
DDL_STATEMENTS: list[tuple[str, str, str]] = [
    # 1. Integer-now function. Required before any retention policy on an
    #    integer time dimension. STABLE is mandatory — TimescaleDB rejects a
    #    VOLATILE function here.
    (
        "Integer-now function (public.unix_now_ms)",
        "CREATE OR REPLACE FUNCTION public.unix_now_ms() RETURNS BIGINT "
        "LANGUAGE SQL STABLE "
        "AS $$ SELECT (extract(epoch FROM now()) * 1000)::bigint $$",
        "error",
    ),
    # 2. klines -> hypertable. Already converted on every live deployment, so
    #    `if_not_exists` makes this a no-op; a failure here is informational.
    (
        "Hypertable (public.klines)",
        """SELECT create_hypertable('public.klines', 'timestamp',
            chunk_time_interval => 86400000,
            if_not_exists => TRUE,
            migrate_data => TRUE
        )""",
        "warning",
    ),
    # 3. tickers -> hypertable. Same: already converted, no-op.
    (
        "Hypertable (public.tickers)",
        """SELECT create_hypertable('public.tickers', 'timestamp',
            chunk_time_interval => 86400000,
            if_not_exists => TRUE,
            migrate_data => TRUE
        )""",
        "warning",
    ),
    # 4. orderbook_snapshots -> hypertable, via an ATOMIC PK reshape.
    #
    #    This is deliberately ONE statement, not three. `_run_isolated` gives
    #    every entry its own transaction and swallows the exception; splitting
    #    DROP CONSTRAINT / ADD PRIMARY KEY / create_hypertable into separate
    #    entries would COMMIT the PK reshape even when the conversion fails,
    #    leaving a half-migrated table behind a single log warning. One DO block
    #    = one transaction = rollback on any step.
    #
    #    The existing PK constraint name is resolved at runtime from
    #    `pg_constraint`, never hardcoded: the live diagnosis verified the PK's
    #    COLUMNS, not its name, and a wrong literal would abort the block and be
    #    swallowed as a warning.
    #
    #    The `hypertable_schema = 'public'` guard is mandatory.
    #    `timescaledb_information.hypertables.hypertable_name` stores the
    #    UNQUALIFIED name, so without the schema predicate this existence check
    #    matches the dead `market_data.orderbook_snapshots` shadow hypertable and
    #    the real conversion is skipped forever.
    (
        "Hypertable (public.orderbook_snapshots, atomic PK reshape)",
        """DO $$
DECLARE pk_name text;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.hypertables
        WHERE hypertable_schema = 'public'
          AND hypertable_name = 'orderbook_snapshots'
    ) THEN
        SELECT conname INTO pk_name FROM pg_constraint
        WHERE conrelid = 'public.orderbook_snapshots'::regclass
          AND contype = 'p';
        IF pk_name IS NOT NULL THEN
            EXECUTE format(
                'ALTER TABLE public.orderbook_snapshots DROP CONSTRAINT %I',
                pk_name
            );
        END IF;
        ALTER TABLE public.orderbook_snapshots ADD PRIMARY KEY (id, "timestamp");
        PERFORM create_hypertable('public.orderbook_snapshots', 'timestamp',
            chunk_time_interval => 86400000::bigint,
            if_not_exists => TRUE, migrate_data => TRUE);
    END IF;
END $$""",
        "error",
    ),
    # 5-7. Register the integer-now function on every hypertable. MUST come
    #      after the corresponding conversion above — the table has to already
    #      be a hypertable. Without this, `integer_now_func` stays NULL and no
    #      retention policy can ever be created.
    (
        "Integer-now registration (public.klines)",
        "SELECT set_integer_now_func('public.klines', 'public.unix_now_ms', "
        "replace_if_exists => TRUE)",
        "error",
    ),
    (
        "Integer-now registration (public.tickers)",
        "SELECT set_integer_now_func('public.tickers', 'public.unix_now_ms', "
        "replace_if_exists => TRUE)",
        "error",
    ),
    (
        "Integer-now registration (public.orderbook_snapshots)",
        "SELECT set_integer_now_func('public.orderbook_snapshots', "
        "'public.unix_now_ms', replace_if_exists => TRUE)",
        "error",
    ),
    # 8-9. Retention policies. `drop_after` is an INTEGER count of epoch-ms,
    #      NOT an INTERVAL — the time dimension is BIGINT. The `::bigint` cast
    #      on the multiplier is required: `90 * 86400000` overflows int4 and was
    #      reproduced failing live.
    #
    #      klines DELIBERATELY GETS NO RETENTION POLICY. This is the whole point
    #      of the rewrite, not an omission. The old
    #      `add_retention_policy('klines', INTERVAL '90 days', ...)` lived right
    #      here. A 90-day window would delete 385,808 rows — 52% of the table,
    #      i.e. the entire backfilled research history every backtest depends
    #      on. Total klines footprint is 288 MB for 2.7 years of data, so disk
    #      is a non-issue. Deleting research data must be an explicit operator
    #      action, never a background job. Enforced by
    #      tests/test_database_ddl.py::test_klines_has_no_retention_policy.
    #
    #      tickers is 180 days rather than the old 30: a 30-day window would
    #      wipe 72% of tickers, including the clean post-2026-08-12 mainnet
    #      record that current trading evidence rests on.
    (
        "Retention policy (public.tickers, 180d)",
        "SELECT add_retention_policy('public.tickers', "
        "drop_after => 180::bigint * 86400000, if_not_exists => TRUE)",
        "error",
    ),
    # widened 7d -> 90d for edge-search v2 (spec 2026-08-19 §2 A1; Phase C
    # gate needs >=21 consecutive days of snapshots). add_retention_policy
    # alone won't change an already-created policy's window, so this drops
    # the existing policy (if any) and re-adds it at the new window in one
    # atomic DO block, same convention as entry 4's PK reshape.
    (
        "Retention policy (public.orderbook_snapshots, 90d)",
        """DO $$
BEGIN
    PERFORM remove_retention_policy('public.orderbook_snapshots', if_exists => TRUE);
    PERFORM add_retention_policy('public.orderbook_snapshots',
        drop_after => 90::bigint * 86400000, if_not_exists => TRUE);
END $$""",
        "error",
    ),
    # 10. Idempotent column-add migrations. SQLAlchemy's create_all() only
    #     creates tables that don't exist; existing tables don't pick up new
    #     Column() declarations. Each ALTER TABLE here is `IF NOT EXISTS`
    #     safe and runs every startup.
    #     is_mainnet flag (audit 2026-04-29) — pre-flip testnet rows
    #     default to True; operators should wipe pre-flip data manually.
    (
        "Column migration (public.klines.is_mainnet)",
        "ALTER TABLE public.klines "
        "ADD COLUMN IF NOT EXISTS is_mainnet BOOLEAN NOT NULL DEFAULT true",
        "warning",
    ),
    (
        "Column migration (idx_klines_mainnet)",
        "CREATE INDEX IF NOT EXISTS idx_klines_mainnet ON public.klines (is_mainnet)",
        "warning",
    ),
]


async def create_hypertables():
    """
    Converge the TimescaleDB schema to the state declared by DDL_STATEMENTS.

    This should be run AFTER init_database() creates the tables.
    Safe to run multiple times — every statement is idempotent or guarded.
    """
    from sqlalchemy import text

    engine = get_engine()

    # Every statement runs in its OWN transaction. PostgreSQL aborts the whole
    # transaction on the first error and silently rejects every following
    # statement with InFailedSQLTransactionError, so a shared transaction would
    # strand later statements behind an earlier legitimate failure — that is
    # exactly what bit the is_mainnet column migration on first deploy
    # (2026-04-29).
    #
    # Exceptions are logged and SWALLOWED, never re-raised: app/main.py must
    # keep booting against a non-TimescaleDB PostgreSQL. `level` only controls
    # visibility — "error" marks the statements whose failure means the intended
    # DB state did NOT converge.
    async def _run_isolated(stmt: str, label: str, level: str = "warning") -> None:
        async with engine.begin() as conn:
            try:
                await conn.execute(text(stmt))
                logger.info(f"{label} applied")
            except Exception as e:
                if level == "error":
                    logger.error(f"{label}: {e}")
                else:
                    logger.warning(f"{label}: {e}")

    for label, stmt, level in DDL_STATEMENTS:
        await _run_isolated(stmt, label, level)

    logger.info("TimescaleDB hypertables, policies, and column migrations configured")


async def close_database():
    """Close database connections"""
    global _engine, _async_session_maker

    if _engine:
        await _engine.dispose()
        logger.info("Database engine disposed")

    _engine = None
    _async_session_maker = None
