-- Sync Portfolio P&L with Actual Trades
-- This script updates the portfolio table with the correct realized P&L from positions

-- First, let's see what we have
SELECT 'Current Portfolio State' as info;
SELECT portfolio_id, cash_balance, total_value, realized_pnl, unrealized_pnl
FROM portfolios;

SELECT 'Actual P&L from Positions' as info;
SELECT
    portfolio_id,
    COUNT(*) as total_positions,
    SUM(CASE WHEN status = 'CLOSED' THEN 1 ELSE 0 END) as closed_positions,
    SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END) as open_positions,
    SUM(realized_pnl) as total_realized_pnl,
    SUM(unrealized_pnl) as total_unrealized_pnl
FROM positions
GROUP BY portfolio_id;

-- Update portfolio with correct realized P&L
UPDATE portfolios p
SET
    realized_pnl = COALESCE((
        SELECT SUM(realized_pnl)
        FROM positions
        WHERE portfolio_id = p.portfolio_id
        AND status = 'CLOSED'
    ), 0),
    unrealized_pnl = COALESCE((
        SELECT SUM(unrealized_pnl)
        FROM positions
        WHERE portfolio_id = p.portfolio_id
        AND status = 'OPEN'
    ), 0);

-- Recalculate total_value (cash + unrealized P&L)
UPDATE portfolios
SET total_value = cash_balance + unrealized_pnl;

-- Show updated state
SELECT 'Updated Portfolio State' as info;
SELECT portfolio_id, cash_balance, total_value, realized_pnl, unrealized_pnl,
       (total_value - 10000) as total_pnl,
       ((total_value - 10000) / 10000 * 100) as roi_pct
FROM portfolios;
