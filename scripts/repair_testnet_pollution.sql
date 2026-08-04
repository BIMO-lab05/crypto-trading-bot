-- ============================================================================
-- repair_testnet_pollution.sql
-- ============================================================================
-- Purpose: Repair testnet data pollution in the TimescaleDB `market_data`
--          database left behind by the 2026-04-25 testnet -> mainnet flip.
--          Before that date the ingest pipeline wrote Bybit TESTNET candles
--          into the same tables now used for mainnet data; when the
--          `is_mainnet` column was added (2026-04-29 audit) all pre-existing
--          rows were defaulted to TRUE, so pre-flip testnet rows are wrongly
--          tagged as mainnet.
--
-- Schema facts (see services/market-data-service/app/models.py):
--   * klines.timestamp  : BIGINT, Unix epoch in MILLISECONDS (not timestamptz)
--   * klines.is_mainnet : BOOLEAN NOT NULL DEFAULT true
--   * klines.close      : NUMERIC(20,8)
--   * tickers.timestamp : BIGINT, Unix epoch in MILLISECONDS
--   * tickers has NO is_mainnet column in the current model — the ticker
--     update below is guarded and only runs if the column exists (e.g. if a
--     later migration added it), otherwise it logs a NOTICE and skips.
--
-- Cutoff: the flip happened mid-day 2026-04-25; we use a CONSERVATIVE cutoff
--         of 2026-04-26 00:00:00 UTC so any row that could possibly be
--         testnet is demoted. Better to lose a few hours of genuine mainnet
--         history than to keep polluted candles in backtests.
--         2026-04-26T00:00:00Z == 1777161600 s == 1777161600000 ms epoch.
--
-- Run via scripts/repair_testnet_pollution.sh (docker exec into the
-- crypto-bot-timescaledb container). Idempotent: re-running is a no-op.
-- ============================================================================

\set ON_ERROR_STOP on
\set cutoff_ms 1777161600000

BEGIN;

-- ----------------------------------------------------------------------------
-- STEP 0: BEFORE counts — snapshot of current tagging so the operator can
--         verify how many rows each step demotes.
-- ----------------------------------------------------------------------------
\echo '=== BEFORE: klines tagging summary ==='
SELECT is_mainnet, count(*) AS rows
FROM klines
GROUP BY is_mainnet
ORDER BY is_mainnet;

\echo '=== BEFORE: klines rows before cutoff still tagged mainnet ==='
SELECT count(*) AS pre_cutoff_mainnet_rows
FROM klines
WHERE timestamp < :cutoff_ms
  AND is_mainnet IS TRUE;

-- ----------------------------------------------------------------------------
-- STEP 1 (a): Demote every kline row from before the flip cutoff.
--   Rationale: everything ingested before 2026-04-26 00:00 UTC may be
--   testnet data mis-tagged as mainnet by the ALTER TABLE default. Marking
--   is_mainnet=false (rather than deleting) preserves the rows for forensic
--   queries via mainnet_only=false while removing them from all default
--   (mainnet-only) reads.
-- ----------------------------------------------------------------------------
\echo '=== STEP 1: demoting pre-cutoff klines (timestamp < 2026-04-26T00:00Z) ==='
UPDATE klines
SET is_mainnet = false
WHERE timestamp < :cutoff_ms
  AND is_mainnet IS TRUE;

-- Same treatment for tickers — but only if a later migration has added the
-- is_mainnet column (the current SQLAlchemy Ticker model does not define
-- it). Guarded so this script works against both schema generations.
\echo '=== STEP 1b: demoting pre-cutoff tickers (if is_mainnet column exists) ==='
DO $$
DECLARE
    n_demoted bigint;
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'tickers' AND column_name = 'is_mainnet'
    ) THEN
        UPDATE tickers
        SET is_mainnet = false
        WHERE timestamp < 1777161600000
          AND is_mainnet IS TRUE;
        GET DIAGNOSTICS n_demoted = ROW_COUNT;
        RAISE NOTICE 'tickers: demoted % pre-cutoff row(s)', n_demoted;
    ELSE
        RAISE NOTICE 'tickers.is_mainnet column does not exist - skipping ticker repair (pre-cutoff ticker rows cannot be tagged)';
    END IF;
END
$$;

-- ----------------------------------------------------------------------------
-- STEP 2 (b): Demote price-outlier klines that survived the date cutoff.
--   Testnet prices frequently bear no relation to real markets (e.g. BTC at
--   $300k or $9 on testnet). For each symbol we compute the MEDIAN close
--   over rows still tagged mainnet (percentile_cont(0.5) — robust to the
--   very outliers we are hunting, unlike AVG), then demote any mainnet row
--   whose close is more than 5x above or below that median.
--   Defensibility: no real crypto asset's true close sits >5x away from its
--   own recent median within the retained (90-day retention) window, while
--   testnet prints routinely do; the median itself is computed only from
--   rows that passed Step 1, so pre-flip pollution cannot drag it.
-- ----------------------------------------------------------------------------
\echo '=== STEP 2: demoting >5x price-outlier klines vs per-symbol mainnet median ==='
WITH medians AS (
    SELECT
        symbol,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY close) AS median_close
    FROM klines
    WHERE is_mainnet IS TRUE
    GROUP BY symbol
)
UPDATE klines k
SET is_mainnet = false
FROM medians m
WHERE k.symbol = m.symbol
  AND k.is_mainnet IS TRUE
  AND m.median_close > 0
  AND (
        k.close > m.median_close * 5.0   -- >5x above median
     OR k.close < m.median_close / 5.0   -- >5x below median (1/5th)
  );

-- ----------------------------------------------------------------------------
-- STEP 3 (c): AFTER counts — verify the repair.
-- ----------------------------------------------------------------------------
\echo '=== AFTER: klines tagging summary ==='
SELECT is_mainnet, count(*) AS rows
FROM klines
GROUP BY is_mainnet
ORDER BY is_mainnet;

\echo '=== AFTER: klines rows before cutoff still tagged mainnet (expect 0) ==='
SELECT count(*) AS pre_cutoff_mainnet_rows
FROM klines
WHERE timestamp < :cutoff_ms
  AND is_mainnet IS TRUE;

\echo '=== AFTER: per-symbol mainnet row counts ==='
SELECT symbol, count(*) AS mainnet_rows
FROM klines
WHERE is_mainnet IS TRUE
GROUP BY symbol
ORDER BY symbol;

COMMIT;

\echo '=== repair_testnet_pollution.sql complete ==='
