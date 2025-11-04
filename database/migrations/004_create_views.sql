-- ==========================================
-- MIGRATION 004: Create Views
-- ==========================================
-- Description: Create useful views for querying
-- Date: 2025-11-01
-- Depends on: 002_create_tables.sql
-- ==========================================

\c crypto_trading_bot

-- ==========================================
-- VIEW: Active Positions
-- ==========================================
CREATE OR REPLACE VIEW v_active_positions AS
SELECT
    p.*,
    (p.current_price - p.entry_price) * p.quantity AS current_unrealized_pnl,
    ((p.current_price - p.entry_price) / p.entry_price) * 100 AS unrealized_pnl_pct
FROM positions p
WHERE p.status = 'OPEN';

-- ==========================================
-- VIEW: Daily Trading Summary
-- ==========================================
CREATE OR REPLACE VIEW v_daily_trading_summary AS
SELECT
    portfolio_id,
    DATE(executed_at) as trade_date,
    COUNT(*) as total_trades,
    SUM(CASE WHEN action = 'BUY' THEN 1 ELSE 0 END) as buy_count,
    SUM(CASE WHEN action = 'SELL' THEN 1 ELSE 0 END) as sell_count,
    SUM(total_cost) as total_volume,
    SUM(COALESCE(realized_pnl, 0)) as daily_pnl,
    AVG(signal_confidence) as avg_confidence
FROM trades
GROUP BY portfolio_id, DATE(executed_at)
ORDER BY trade_date DESC;

-- ==========================================
-- VIEW: Portfolio Performance
-- ==========================================
CREATE OR REPLACE VIEW v_portfolio_performance AS
SELECT
    pf.portfolio_id,
    pf.name,
    pf.cash_balance,
    pf.realized_pnl,
    pf.unrealized_pnl,
    pf.total_pnl,
    COUNT(DISTINCT p.position_id) as total_positions,
    COUNT(DISTINCT CASE WHEN p.status = 'OPEN' THEN p.position_id END) as open_positions,
    COUNT(DISTINCT t.trade_id) as total_trades,
    SUM(CASE WHEN t.realized_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
    SUM(CASE WHEN t.realized_pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
    CASE
        WHEN COUNT(DISTINCT t.trade_id) > 0
        THEN (SUM(CASE WHEN t.realized_pnl > 0 THEN 1 ELSE 0 END)::DECIMAL / COUNT(DISTINCT t.trade_id))
        ELSE 0
    END as win_rate
FROM portfolios pf
LEFT JOIN positions p ON pf.portfolio_id = p.portfolio_id
LEFT JOIN trades t ON pf.portfolio_id = t.portfolio_id AND t.realized_pnl IS NOT NULL
WHERE pf.is_active = TRUE
GROUP BY pf.portfolio_id, pf.name, pf.cash_balance, pf.realized_pnl, pf.unrealized_pnl, pf.total_pnl;

-- Log migration
DO $$
BEGIN
    RAISE NOTICE '✅ Migration 004 completed: Views created';
END $$;
