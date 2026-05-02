-- ==========================================
-- MIGRATION 006: Kelly Trade History
-- ==========================================
-- Description: Persist completed trades for Kelly position sizer recovery
--              on trading-engine restart.
-- Date: 2026-05-02
-- Depends on: 002_create_tables.sql
--
-- Mirrors services/trading-engine/app/risk/kelly_models.py::KellyTradeHistory.
-- The sizer's load_trades_from_db() replays the most recent rows on boot to
-- rebuild the rolling window + win/loss counters; without this table that
-- recovery path silently no-ops (load returns 0).
-- ==========================================

\c crypto_trading_bot

CREATE TABLE IF NOT EXISTS kelly_trade_history (
    trade_id VARCHAR(100) PRIMARY KEY,
    symbol VARCHAR(40) NOT NULL,
    entry_time TIMESTAMP WITH TIME ZONE NOT NULL,
    exit_time TIMESTAMP WITH TIME ZONE NOT NULL,
    entry_price DOUBLE PRECISION NOT NULL,
    exit_price DOUBLE PRECISION NOT NULL,
    pnl DOUBLE PRECISION NOT NULL,
    pnl_pct DOUBLE PRECISION NOT NULL,
    is_win BOOLEAN NOT NULL,
    strategy VARCHAR(50) NOT NULL DEFAULT 'stat_arb',
    kelly_suggested DOUBLE PRECISION,
    actual_size DOUBLE PRECISION,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kelly_trade_history_exit_time
    ON kelly_trade_history (exit_time);

CREATE INDEX IF NOT EXISTS idx_kelly_trade_history_symbol
    ON kelly_trade_history (symbol);

-- Log migration
DO $$
BEGIN
    RAISE NOTICE '✅ Migration 006 completed: kelly_trade_history table created';
END $$;
