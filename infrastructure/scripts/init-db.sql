-- PostgreSQL initialization script for Crypto Trading Bot
--
-- Canonical schema layout (audit 2026-04-27):
--   public.*    — transactional state (portfolios, positions, trades, ...)
--                 Created by infrastructure/migrations/001_initial_schema.sql.
--   portfolio.* — analytics-only. portfolio.performance_history is the only
--                 table here, created by infrastructure/migrations/002_performance_history.sql.
--   audit.*     — compliance/event audit log. Defined below.
--
-- This script is responsible only for the audit schema, the `portfolio` schema
-- container, the shared trigger function, and required extensions. Application
-- tables live in the migrations files above so a fresh DB run looks like:
--   1) docker-entrypoint runs init-db.sql (this file)
--   2) operator runs 001_initial_schema.sql + 002_performance_history.sql
--
-- Earlier versions of this file ALSO created `trading_engine.*` and
-- `portfolio.{balances,positions}` tables that conflicted with the canonical
-- public.* tables. Those orphans were dropped 2026-04-27 after an audit found
-- zero code consumers — see git log for details.

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Container schemas. `public` exists by default. `trading_engine` is gone.
CREATE SCHEMA IF NOT EXISTS portfolio;
CREATE SCHEMA IF NOT EXISTS audit;

-- ----------------------------------------------------------------------------
-- Audit tables (consumed by application code via raw inserts; not in any ORM)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit.api_calls (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    service_name VARCHAR(50) NOT NULL,
    endpoint VARCHAR(200) NOT NULL,
    method VARCHAR(10) NOT NULL,
    request_data JSONB,
    response_data JSONB,
    status_code INTEGER,
    duration_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit.system_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB,
    severity VARCHAR(20) DEFAULT 'INFO' CHECK (severity IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_api_calls_created_at ON audit.api_calls(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_system_events_created_at ON audit.system_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_system_events_severity ON audit.system_events(severity);

-- ----------------------------------------------------------------------------
-- Shared utility: updated_at autoupdate trigger function
-- (Used by 001_initial_schema.sql attaching to public.portfolios etc.)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
