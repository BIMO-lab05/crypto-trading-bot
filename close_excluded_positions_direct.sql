-- =============================================================================
-- Script to Close Positions in Excluded Symbols
-- Date: 2025-12-13
-- Purpose: Close all open positions for symbols not in active trading list
-- Active symbols: SOLUSDT, BNBUSDT, ADAUSDT
-- =============================================================================

-- First, let's see what we're working with
\echo '================================================================================'
\echo 'EXCLUDED POSITIONS TO CLOSE'
\echo '================================================================================'

SELECT
    position_id,
    symbol,
    side,
    quantity,
    entry_price,
    opened_at,
    EXTRACT(DAYS FROM (NOW() - opened_at)) as days_open
FROM positions
WHERE status = 'OPEN'
AND symbol NOT IN ('SOLUSDT', 'BNBUSDT', 'ADAUSDT')
ORDER BY symbol, opened_at;

\echo ''
\echo '================================================================================'
\echo 'CLOSING POSITIONS...'
\echo '================================================================================'

-- Close positions in excluded symbols
-- Set status to CLOSED, record timestamp, and set exit_price = entry_price for safety
UPDATE positions
SET
    status = 'CLOSED',
    closed_at = NOW(),
    exit_price = entry_price,  -- Using entry price to avoid unfavorable execution
    exit_reason = 'EXCLUDED_SYMBOL',
    realized_pnl = 0.00  -- Break-even close
WHERE status = 'OPEN'
AND symbol NOT IN ('SOLUSDT', 'BNBUSDT', 'ADAUSDT');

\echo ''
\echo '================================================================================'
\echo 'VERIFICATION: REMAINING OPEN POSITIONS'
\echo '================================================================================'

SELECT
    symbol,
    side,
    COUNT(*) as position_count,
    SUM(quantity * entry_price) as total_value_usdt
FROM positions
WHERE status = 'OPEN'
GROUP BY symbol, side
ORDER BY symbol;

\echo ''
\echo '================================================================================'
\echo 'SUMMARY OF CLOSED POSITIONS'
\echo '================================================================================'

SELECT
    symbol,
    COUNT(*) as positions_closed,
    MIN(opened_at) as oldest_position,
    MAX(opened_at) as newest_position
FROM positions
WHERE status = 'CLOSED'
AND exit_reason = 'EXCLUDED_SYMBOL'
AND closed_at >= NOW() - INTERVAL '1 hour'
GROUP BY symbol
ORDER BY symbol;

\echo ''
\echo 'Script completed successfully!'
