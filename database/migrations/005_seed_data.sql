-- ==========================================
-- MIGRATION 005: Seed Initial Data
-- ==========================================
-- Description: Insert default portfolio and initial configuration
-- Date: 2025-11-01
-- Depends on: 002_create_tables.sql
-- ==========================================

\c crypto_trading_bot

-- ==========================================
-- Create default paper trading portfolio
-- ==========================================
INSERT INTO portfolios (
    portfolio_id,
    name,
    initial_balance,
    cash_balance,
    trading_mode
)
VALUES (
    'default',
    'Default Paper Trading Portfolio',
    100.00,
    100.00,
    'PAPER'
)
ON CONFLICT (portfolio_id) DO NOTHING;

-- Log migration
DO $$
BEGIN
    RAISE NOTICE '✅ Migration 005 completed: Initial data seeded';
    RAISE NOTICE 'Default portfolio created with $10,000 balance';
END $$;
