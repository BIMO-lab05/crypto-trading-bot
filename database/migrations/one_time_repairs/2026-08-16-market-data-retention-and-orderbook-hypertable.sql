-- ==========================================
-- ONE-TIME REPAIR 2026-08-16: market-data retention policies + orderbook hypertable
-- ==========================================
-- RES-02. Quick task 260816-qjn.
--
-- THIS FILE IS A RECORD, NOT A RUNBOOK STEP. It was NOT executed.
--
-- The live mechanism is the boot DDL in
--   services/market-data-service/app/database.py::DDL_STATEMENTS
-- applied by create_hypertables() on every market-data-service startup. This
-- file exists so the schema change is discoverable from the migrations tree
-- rather than only from Python source. If the two ever disagree, database.py
-- is authoritative — it is the one that runs.
--
-- NOT a numbered migration: database/scripts/setup_database.sh globs
-- $MIGRATIONS_DIR/*.sql non-recursively and re-applies everything on every
-- run. Schema reshapes must never sit on that path.
--
-- ------------------------------------------------------------------
-- ROOT CAUSES (verified live 2026-08-16 against TimescaleDB 2.26.3)
-- ------------------------------------------------------------------
-- 1. public.klines and public.tickers are hypertables partitioned on
--    `timestamp BIGINT` (Unix epoch milliseconds), with
--    `integer_now_func = NULL`. `add_retention_policy(..., INTERVAL '90 days')`
--    can NEVER succeed on an integer time dimension: it needs an integer
--    `drop_after` AND a registered integer-now function. Result:
--    `timescaledb_information.jobs` contained ZERO retention jobs.
--
-- 2. public.orderbook_snapshots had `PRIMARY KEY (id)` only.
--    `create_hypertable` refuses that, because every unique index on a
--    hypertable must include the partition column. The table had 0 rows and
--    had never been a hypertable.
--
-- Both failures were swallowed by `_run_isolated` (log a warning, continue),
-- so market-data-service booted green on every restart and nobody noticed.
--
-- ------------------------------------------------------------------
-- WHY EVERY NAME IS SCHEMA-QUALIFIED public.
-- ------------------------------------------------------------------
-- infrastructure/scripts/init-timescale.sql created four never-used shadow
-- hypertables under the `market_data` schema (ticks, candles, indicators,
-- orderbook_snapshots). They are dead. An unqualified name can resolve to one
-- of those depending on search_path — including in the hypertable existence
-- guard below, where an unqualified check would match the shadow and skip the
-- real conversion forever.
--
-- ------------------------------------------------------------------
-- klines DELIBERATELY HAS NO RETENTION POLICY
-- ------------------------------------------------------------------
-- This is the point of the change, not an omission. The previous boot DDL
-- asked for a 90-day window on klines. Had it ever worked, it would have
-- deleted 385,808 rows — 52% of the table — i.e. the entire backfilled
-- research history that every backtest depends on. Total klines footprint is
-- 288 MB for 2.7 years of data, so disk pressure is not a reason to prune.
-- Deleting research data must be an explicit operator action, never a
-- background job with no human in the loop.
--
-- tickers is 180 days rather than the previous 30: a 30-day window would wipe
-- 72% of tickers, including the clean post-2026-08-12 mainnet epoch that
-- current trading evidence rests on.
--
-- Guarded by services/market-data-service/tests/test_database_ddl.py.
--
-- ------------------------------------------------------------------
-- 1. Integer-now function (STABLE is mandatory; VOLATILE is rejected)
-- ------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.unix_now_ms() RETURNS BIGINT
LANGUAGE SQL STABLE
AS $$ SELECT (extract(epoch FROM now()) * 1000)::bigint $$;

-- ------------------------------------------------------------------
-- 2. Hypertable conversions (klines/tickers already converted; no-ops)
-- ------------------------------------------------------------------
SELECT create_hypertable('public.klines', 'timestamp',
    chunk_time_interval => 86400000,
    if_not_exists => TRUE,
    migrate_data => TRUE
);

SELECT create_hypertable('public.tickers', 'timestamp',
    chunk_time_interval => 86400000,
    if_not_exists => TRUE,
    migrate_data => TRUE
);

-- ------------------------------------------------------------------
-- 3. orderbook_snapshots: PK reshape + conversion, ATOMICALLY
-- ------------------------------------------------------------------
-- One DO block on purpose. Split into separate statements, a create_hypertable
-- failure would commit the PK drop anyway and leave a table with no usable
-- primary key. The old constraint name is resolved at runtime from
-- pg_constraint — the live diagnosis verified the PK's COLUMNS, not its name.
DO $$
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
END $$;

-- ------------------------------------------------------------------
-- 4. Register the integer-now function on every hypertable
-- ------------------------------------------------------------------
-- Must run AFTER the conversions above: the table has to already be a
-- hypertable. Without these, integer_now_func stays NULL and no retention
-- policy can ever be created.
SELECT set_integer_now_func('public.klines', 'public.unix_now_ms', replace_if_exists => TRUE);
SELECT set_integer_now_func('public.tickers', 'public.unix_now_ms', replace_if_exists => TRUE);
SELECT set_integer_now_func('public.orderbook_snapshots', 'public.unix_now_ms', replace_if_exists => TRUE);

-- ------------------------------------------------------------------
-- 5. Retention policies — drop_after in epoch ms, NOT INTERVAL
-- ------------------------------------------------------------------
-- The ::bigint cast on the multiplier is required: `90 * 86400000` overflows
-- int4 and was reproduced failing live.
--
-- NOTE: there is intentionally NO add_retention_policy for public.klines here.
-- See the klines section at the top of this file.
SELECT add_retention_policy('public.tickers',
    drop_after => 180::bigint * 86400000, if_not_exists => TRUE);
SELECT add_retention_policy('public.orderbook_snapshots',
    drop_after => 7::bigint * 86400000, if_not_exists => TRUE);

-- ------------------------------------------------------------------
-- 6. Idempotent column migrations (unchanged in substance; qualified only)
-- ------------------------------------------------------------------
-- is_mainnet flag (audit 2026-04-29) — pre-flip testnet rows default to True;
-- operators should wipe pre-flip data manually.
ALTER TABLE public.klines ADD COLUMN IF NOT EXISTS is_mainnet BOOLEAN NOT NULL DEFAULT true;
CREATE INDEX IF NOT EXISTS idx_klines_mainnet ON public.klines (is_mainnet);

-- ------------------------------------------------------------------
-- POST-REBUILD VERIFICATION (operator; not part of this file's execution)
-- ------------------------------------------------------------------
-- After `docker compose -f docker-compose.unified.yml up -d --build
-- market-data-service` (WSL2: prefix DOCKER_BUILDKIT=0):
--
--   SELECT hypertable_name, config FROM timescaledb_information.jobs
--    WHERE proc_name = 'policy_retention';
--     -> exactly TWO rows: tickers, orderbook_snapshots.
--        ZERO klines rows is the PASS condition, not a failure.
--
--   SELECT integer_now_func FROM timescaledb_information.dimensions
--    WHERE hypertable_schema = 'public';
--     -> non-NULL for klines, tickers, orderbook_snapshots.
--
--   SELECT * FROM timescaledb_information.hypertables
--    WHERE hypertable_schema = 'public' AND hypertable_name = 'orderbook_snapshots';
--     -> one row; its PK is (id, timestamp).
--
--   SELECT count(*) FROM public.klines;
--     -> unchanged from the pre-change count. Nothing deleted.
