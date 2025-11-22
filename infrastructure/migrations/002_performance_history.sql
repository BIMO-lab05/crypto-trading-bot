-- Migration 002: Performance History Tracking
-- Purpose: Add historical performance tracking tables
-- Date: 2025-11-20
-- Author: Backend Developer Agent

-- ============================================================================
-- PERFORMANCE HISTORY TABLE
-- ============================================================================
-- Stores daily snapshots of portfolio performance for historical tracking
-- Enables period-based performance analysis (week, month, year, all-time)
CREATE TABLE IF NOT EXISTS portfolio.performance_history (
    id SERIAL PRIMARY KEY,
    portfolio_id VARCHAR(255) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Portfolio values snapshot
    total_value DECIMAL(30, 8) NOT NULL,
    cash_balance DECIMAL(30, 8) NOT NULL,
    positions_value DECIMAL(30, 8) NOT NULL,

    -- P&L metrics
    realized_pnl DECIMAL(30, 8) NOT NULL DEFAULT 0,
    unrealized_pnl DECIMAL(30, 8) NOT NULL DEFAULT 0,
    total_pnl DECIMAL(30, 8) NOT NULL DEFAULT 0,
    daily_pnl DECIMAL(30, 8),

    -- Return metrics
    roi_percent DECIMAL(10, 4),
    daily_return_percent DECIMAL(10, 4),

    -- Risk metrics
    sharpe_ratio DECIMAL(10, 4),
    max_drawdown DECIMAL(10, 4),
    volatility DECIMAL(10, 4),

    -- Trading statistics
    win_rate DECIMAL(10, 4),
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,

    -- Metadata
    snapshot_type VARCHAR(20) DEFAULT 'DAILY', -- DAILY, MANUAL, EOD
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Ensure one snapshot per portfolio per day
    UNIQUE(portfolio_id, date_trunc('day', timestamp))
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================
-- Index for portfolio-based queries with time ordering (most common query)
CREATE INDEX idx_performance_portfolio_time
ON portfolio.performance_history(portfolio_id, timestamp DESC);

-- Index for date-based queries
CREATE INDEX idx_performance_date
ON portfolio.performance_history(date_trunc('day', timestamp) DESC);

-- Index for snapshot type filtering
CREATE INDEX idx_performance_type
ON portfolio.performance_history(snapshot_type);

-- Composite index for period queries
CREATE INDEX idx_performance_portfolio_date_range
ON portfolio.performance_history(portfolio_id, timestamp)
WHERE snapshot_type = 'DAILY';

-- ============================================================================
-- COMMENTS FOR DOCUMENTATION
-- ============================================================================
COMMENT ON TABLE portfolio.performance_history IS
'Daily snapshots of portfolio performance for historical analysis';

COMMENT ON COLUMN portfolio.performance_history.portfolio_id IS
'Reference to portfolio identifier (e.g., "default", "paper_trading")';

COMMENT ON COLUMN portfolio.performance_history.timestamp IS
'Snapshot timestamp (typically end of day UTC)';

COMMENT ON COLUMN portfolio.performance_history.total_value IS
'Total portfolio value (cash + positions) at snapshot time';

COMMENT ON COLUMN portfolio.performance_history.daily_pnl IS
'Profit/loss change from previous day';

COMMENT ON COLUMN portfolio.performance_history.roi_percent IS
'Return on investment percentage since inception';

COMMENT ON COLUMN portfolio.performance_history.sharpe_ratio IS
'Risk-adjusted return metric (annualized)';

COMMENT ON COLUMN portfolio.performance_history.snapshot_type IS
'Type of snapshot: DAILY (automated), MANUAL (user-triggered), EOD (end-of-day)';

-- ============================================================================
-- HELPER VIEWS
-- ============================================================================

-- View: Latest performance snapshot for each portfolio
CREATE OR REPLACE VIEW portfolio.latest_performance AS
SELECT DISTINCT ON (portfolio_id)
    portfolio_id,
    timestamp,
    total_value,
    total_pnl,
    roi_percent,
    sharpe_ratio,
    win_rate,
    total_trades
FROM portfolio.performance_history
ORDER BY portfolio_id, timestamp DESC;

COMMENT ON VIEW portfolio.latest_performance IS
'Most recent performance snapshot for each portfolio';

-- View: Daily performance changes
CREATE OR REPLACE VIEW portfolio.daily_performance_changes AS
SELECT
    portfolio_id,
    timestamp::DATE as date,
    total_value,
    daily_pnl,
    daily_return_percent,
    LAG(total_value) OVER (PARTITION BY portfolio_id ORDER BY timestamp) as prev_value,
    total_pnl,
    roi_percent
FROM portfolio.performance_history
WHERE snapshot_type = 'DAILY'
ORDER BY portfolio_id, timestamp DESC;

COMMENT ON VIEW portfolio.daily_performance_changes IS
'Daily performance with previous day comparison';

-- ============================================================================
-- FUNCTIONS FOR PERFORMANCE CALCULATIONS
-- ============================================================================

-- Function: Calculate daily return percentage
CREATE OR REPLACE FUNCTION portfolio.calculate_daily_return(
    p_portfolio_id VARCHAR(255),
    p_current_value DECIMAL(30, 8)
) RETURNS DECIMAL(10, 4) AS $$
DECLARE
    v_previous_value DECIMAL(30, 8);
    v_return_pct DECIMAL(10, 4);
BEGIN
    -- Get previous day's total value
    SELECT total_value INTO v_previous_value
    FROM portfolio.performance_history
    WHERE portfolio_id = p_portfolio_id
    ORDER BY timestamp DESC
    LIMIT 1;

    -- If no previous value, return 0
    IF v_previous_value IS NULL OR v_previous_value = 0 THEN
        RETURN 0;
    END IF;

    -- Calculate return percentage
    v_return_pct := ((p_current_value - v_previous_value) / v_previous_value) * 100;

    RETURN v_return_pct;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION portfolio.calculate_daily_return IS
'Calculate daily return percentage compared to previous snapshot';

-- Function: Get period performance statistics
CREATE OR REPLACE FUNCTION portfolio.get_period_stats(
    p_portfolio_id VARCHAR(255),
    p_days INTEGER
) RETURNS TABLE (
    start_date TIMESTAMPTZ,
    end_date TIMESTAMPTZ,
    start_value DECIMAL(30, 8),
    end_value DECIMAL(30, 8),
    total_return DECIMAL(30, 8),
    return_percent DECIMAL(10, 4),
    avg_daily_return DECIMAL(10, 4),
    volatility DECIMAL(10, 4),
    max_value DECIMAL(30, 8),
    min_value DECIMAL(30, 8),
    total_trades INTEGER
) AS $$
BEGIN
    RETURN QUERY
    WITH period_data AS (
        SELECT
            timestamp,
            total_value,
            daily_return_percent,
            total_trades
        FROM portfolio.performance_history
        WHERE portfolio_id = p_portfolio_id
            AND timestamp >= NOW() - (p_days || ' days')::INTERVAL
        ORDER BY timestamp ASC
    ),
    stats AS (
        SELECT
            MIN(timestamp) as start_date,
            MAX(timestamp) as end_date,
            (SELECT total_value FROM period_data ORDER BY timestamp ASC LIMIT 1) as start_value,
            (SELECT total_value FROM period_data ORDER BY timestamp DESC LIMIT 1) as end_value,
            MAX(total_value) as max_value,
            MIN(total_value) as min_value,
            AVG(daily_return_percent) as avg_daily_return,
            STDDEV(daily_return_percent) as volatility,
            (SELECT total_trades FROM period_data ORDER BY timestamp DESC LIMIT 1) as total_trades
        FROM period_data
    )
    SELECT
        start_date,
        end_date,
        start_value,
        end_value,
        (end_value - start_value) as total_return,
        CASE
            WHEN start_value > 0 THEN ((end_value - start_value) / start_value * 100)
            ELSE 0
        END as return_percent,
        avg_daily_return,
        volatility,
        max_value,
        min_value,
        total_trades
    FROM stats;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION portfolio.get_period_stats IS
'Get aggregated performance statistics for a specific time period';

-- ============================================================================
-- CLEANUP FUNCTION
-- ============================================================================

-- Function: Archive old performance data (keep last 2 years)
CREATE OR REPLACE FUNCTION portfolio.archive_old_performance()
RETURNS INTEGER AS $$
DECLARE
    v_deleted_count INTEGER;
BEGIN
    -- Delete snapshots older than 2 years
    DELETE FROM portfolio.performance_history
    WHERE timestamp < NOW() - INTERVAL '2 years'
        AND snapshot_type = 'DAILY';

    GET DIAGNOSTICS v_deleted_count = ROW_COUNT;

    RETURN v_deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION portfolio.archive_old_performance IS
'Archive/delete performance snapshots older than 2 years (automated cleanup)';

-- ============================================================================
-- GRANTS (adjust based on your user permissions)
-- ============================================================================
-- GRANT SELECT, INSERT ON portfolio.performance_history TO cryptobot;
-- GRANT SELECT ON portfolio.latest_performance TO cryptobot;
-- GRANT SELECT ON portfolio.daily_performance_changes TO cryptobot;
-- GRANT EXECUTE ON FUNCTION portfolio.calculate_daily_return TO cryptobot;
-- GRANT EXECUTE ON FUNCTION portfolio.get_period_stats TO cryptobot;

-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Migration 002_performance_history.sql completed successfully';
    RAISE NOTICE 'Created: portfolio.performance_history table';
    RAISE NOTICE 'Created: 4 indexes for query optimization';
    RAISE NOTICE 'Created: 2 views for common queries';
    RAISE NOTICE 'Created: 3 helper functions';
    RAISE NOTICE 'Ready for historical performance tracking';
    RAISE NOTICE '========================================';
END $$;
