-- ==========================================
-- MIGRATION 006: Kelly Position-Sizer State
-- ==========================================
-- Description: Persist KellyPositionSizer aggregates + rolling window so the
-- Kelly fraction survives trading-engine restarts. A single 'global' row
-- holds the full state; rolling-window trades are stored as JSON (TEXT for
-- portability — the field is small and not queried).
-- Date: 2026-05-03
-- Depends on: 002_create_tables.sql
-- ==========================================

\c crypto_trading_bot

CREATE TABLE IF NOT EXISTS kelly_state (
    id VARCHAR(50) PRIMARY KEY DEFAULT 'global',
    total_trades INTEGER NOT NULL DEFAULT 0,
    winning_trades INTEGER NOT NULL DEFAULT 0,
    losing_trades INTEGER NOT NULL DEFAULT 0,
    total_wins_pct DOUBLE PRECISION NOT NULL DEFAULT 0,
    total_losses_pct DOUBLE PRECISION NOT NULL DEFAULT 0,
    current_streak INTEGER NOT NULL DEFAULT 0,
    current_kelly_fraction DOUBLE PRECISION NOT NULL DEFAULT 0.25,
    rolling_window_json TEXT NOT NULL DEFAULT '[]',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

DO $$
BEGIN
    RAISE NOTICE '✅ Migration 006 completed: kelly_state table created';
END $$;
