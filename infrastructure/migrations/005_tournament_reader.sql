-- Migration 005: Tournament Reader Role
-- Purpose: Read-only Postgres role for tournament harness experiment containers (D-09)
-- Date: 2026-05-08
-- Author: Tournament Harness (Phase 3)

-- ============================================================================
-- TOURNAMENT_READER ROLE
-- ============================================================================
-- D-09: experiment containers connect to TimescaleDB via this role to SELECT from
-- klines for model fitting. SELECT-only — no INSERT, UPDATE, DELETE, TRUNCATE.
-- Password is set to 'CHANGE_ME_VIA_ENV' on first create; operator MUST run:
--   ALTER ROLE tournament_reader PASSWORD '<value-of-TOURNAMENT_READER_PASSWORD>';
-- before running tournaments. Done automatically by the runbook procedure.
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'tournament_reader') THEN
        CREATE ROLE tournament_reader WITH LOGIN PASSWORD 'CHANGE_ME_VIA_ENV';
        RAISE NOTICE 'tournament_reader role created with placeholder password — operator MUST rotate via ALTER ROLE';
    ELSE
        RAISE NOTICE 'tournament_reader role already exists — skipping create (idempotent)';
    END IF;
END
$$;

-- Grants (SELECT-only path)
-- Canonical DB is market_data (live klines store); historical name trading_bot
-- never existed in this stack — the original migration was authored against an
-- earlier naming assumption. Aligning with docker-compose.unified.yml ${TIMESCALE_DB:-market_data}.
GRANT CONNECT ON DATABASE market_data TO tournament_reader;
GRANT USAGE ON SCHEMA public TO tournament_reader;
GRANT SELECT ON klines TO tournament_reader;

-- Defensive revoke — make sure no broader privilege ever sticks even if a future
-- migration accidentally grants ALL.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON klines FROM tournament_reader;

-- Future-proofing: tournament_reader should NOT inherit from public.
-- (If public schema gets blanket grants in the future, those would leak through.)
REVOKE CREATE ON SCHEMA public FROM tournament_reader;

COMMENT ON ROLE tournament_reader IS
  'Read-only access for tournament-harness experiment containers (D-09, Phase 3). '
  'SELECT on klines only. Password rotated via TOURNAMENT_READER_PASSWORD env var.';

-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================
DO $$
BEGIN
    RAISE NOTICE 'Migration 005 complete: tournament_reader role configured with SELECT-only on klines';
END $$;
