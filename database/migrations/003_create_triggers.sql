-- ==========================================
-- MIGRATION 003: Create Triggers
-- ==========================================
-- Description: Create triggers for automatic updates
-- Date: 2025-11-01
-- Depends on: 002_create_tables.sql
-- ==========================================

\c crypto_trading_bot

-- ==========================================
-- TRIGGER FUNCTION: Update timestamp
-- ==========================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply to portfolios table
DROP TRIGGER IF EXISTS update_portfolios_updated_at ON portfolios;
CREATE TRIGGER update_portfolios_updated_at
    BEFORE UPDATE ON portfolios
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Apply to positions table
DROP TRIGGER IF EXISTS update_positions_updated_at ON positions;
CREATE TRIGGER update_positions_updated_at
    BEFORE UPDATE ON positions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Log migration
DO $$
BEGIN
    RAISE NOTICE '✅ Migration 003 completed: Triggers created';
END $$;
