-- Migration 001: Initial Database Schema
-- Purpose: Create core tables for crypto trading bot
-- Date: 2025-11-09
-- Author: Claude Code
--
-- NOTE (owner decision 2026-08-04): database/migrations/ is the AUTHORITATIVE
-- migration directory. This file (infrastructure/migrations/) is kept in sync
-- MANUALLY — when the seeds diverge, database/migrations/ wins.
-- FIX 2026-08-05 (AUDIT 2.3): the portfolio seed below used to disagree with
-- the declared account size; production ran this copy, which is why the live
-- portfolios row carried the wrong initial_balance.
-- UPDATE 2026-08-25 (ADR-029): the account is $10,000 (shared/account.py is
-- the declaration of record; was $100). The seed values below must match it.

-- ============================================================================
-- PORTFOLIOS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS portfolios (
    id SERIAL PRIMARY KEY,
    portfolio_id VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    initial_balance DECIMAL(20, 8) NOT NULL,
    cash_balance DECIMAL(20, 8) NOT NULL,
    total_value DECIMAL(20, 8) NOT NULL DEFAULT 0,
    total_pnl DECIMAL(20, 8) NOT NULL DEFAULT 0,
    total_return_pct DECIMAL(10, 4) DEFAULT 0,
    sharpe_ratio DECIMAL(10, 4),
    max_drawdown DECIMAL(10, 4),
    win_rate DECIMAL(5, 2),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_portfolios_portfolio_id ON portfolios(portfolio_id);
CREATE INDEX idx_portfolios_created_at ON portfolios(created_at DESC);

COMMENT ON TABLE portfolios IS 'Portfolio records tracking balance and performance';
COMMENT ON COLUMN portfolios.portfolio_id IS 'Unique identifier for portfolio (e.g., paper_trading)';
COMMENT ON COLUMN portfolios.total_pnl IS 'Total profit/loss across all closed positions';

-- ============================================================================
-- POSITIONS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    position_id UUID UNIQUE NOT NULL,
    portfolio_id VARCHAR(100) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- LONG or SHORT
    quantity DECIMAL(20, 8) NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    current_price DECIMAL(20, 8),
    exit_price DECIMAL(20, 8),
    cost_basis DECIMAL(20, 8) NOT NULL,
    unrealized_pnl DECIMAL(20, 8) DEFAULT 0,
    realized_pnl DECIMAL(20, 8) DEFAULT 0,
    stop_loss DECIMAL(20, 8),
    take_profit DECIMAL(20, 8),
    status VARCHAR(20) DEFAULT 'OPEN',  -- OPEN, CLOSED
    strategy VARCHAR(100),
    exit_reason VARCHAR(100),
    opened_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_position_portfolio FOREIGN KEY (portfolio_id) 
        REFERENCES portfolios(portfolio_id) ON DELETE CASCADE
);

CREATE INDEX idx_positions_position_id ON positions(position_id);
CREATE INDEX idx_positions_portfolio_symbol ON positions(portfolio_id, symbol);
CREATE INDEX idx_positions_status ON positions(status);
CREATE INDEX idx_positions_opened_at ON positions(opened_at DESC);
CREATE INDEX idx_positions_closed_at ON positions(closed_at DESC);

COMMENT ON TABLE positions IS 'Trading positions (open and closed)';
COMMENT ON COLUMN positions.position_id IS 'UUID for position tracking';
COMMENT ON COLUMN positions.unrealized_pnl IS 'Floating P&L for open positions';
COMMENT ON COLUMN positions.realized_pnl IS 'Actual P&L when position closed';

-- ============================================================================
-- TRADES TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    trade_id UUID UNIQUE NOT NULL,
    portfolio_id VARCHAR(100) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- BUY or SELL
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    total_value DECIMAL(20, 8) NOT NULL,
    fee DECIMAL(20, 8) DEFAULT 0,
    realized_pnl DECIMAL(20, 8),
    strategy VARCHAR(100),
    signal_confidence DECIMAL(5, 4),
    executed_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB,
    CONSTRAINT fk_trade_portfolio FOREIGN KEY (portfolio_id) 
        REFERENCES portfolios(portfolio_id) ON DELETE CASCADE
);

CREATE INDEX idx_trades_trade_id ON trades(trade_id);
CREATE INDEX idx_trades_portfolio_executed ON trades(portfolio_id, executed_at DESC);
CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_side ON trades(side);
CREATE INDEX idx_trades_executed_at ON trades(executed_at DESC);
CREATE INDEX idx_trades_metadata_gin ON trades USING GIN (metadata);

COMMENT ON TABLE trades IS 'Individual trade executions';
COMMENT ON COLUMN trades.signal_confidence IS 'Confidence score from technical analysis (0-1)';
COMMENT ON COLUMN trades.metadata IS 'Additional trade information (JSON)';

-- ============================================================================
-- PERFORMANCE METRICS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS performance_metrics (
    id SERIAL PRIMARY KEY,
    portfolio_id VARCHAR(100) NOT NULL,
    date DATE NOT NULL,
    total_return DECIMAL(10, 4),
    daily_return DECIMAL(10, 4),
    sharpe_ratio DECIMAL(10, 4),
    sortino_ratio DECIMAL(10, 4),
    max_drawdown DECIMAL(10, 4),
    win_rate DECIMAL(5, 2),
    profit_factor DECIMAL(10, 4),
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    avg_win DECIMAL(20, 8),
    avg_loss DECIMAL(20, 8),
    largest_win DECIMAL(20, 8),
    largest_loss DECIMAL(20, 8),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (portfolio_id, date),
    CONSTRAINT fk_metrics_portfolio FOREIGN KEY (portfolio_id) 
        REFERENCES portfolios(portfolio_id) ON DELETE CASCADE
);

CREATE INDEX idx_metrics_portfolio_date ON performance_metrics(portfolio_id, date DESC);

COMMENT ON TABLE performance_metrics IS 'Daily performance metrics for portfolios';
COMMENT ON COLUMN performance_metrics.profit_factor IS 'Gross profit / gross loss';

-- ============================================================================
-- AUDIT LOG TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    portfolio_id VARCHAR(100),
    action VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,  -- POSITION, TRADE, PORTFOLIO
    entity_id VARCHAR(100),
    details JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_audit_portfolio ON audit_log(portfolio_id, created_at DESC);
CREATE INDEX idx_audit_action ON audit_log(action);
CREATE INDEX idx_audit_created_at ON audit_log(created_at DESC);

COMMENT ON TABLE audit_log IS 'Audit trail for all trading operations';

-- ============================================================================
-- VIEWS
-- ============================================================================

-- View: Open Positions Summary
CREATE OR REPLACE VIEW open_positions_summary AS
SELECT 
    portfolio_id,
    symbol,
    COUNT(*) as position_count,
    SUM(quantity) as total_quantity,
    AVG(entry_price) as avg_entry_price,
    SUM(unrealized_pnl) as total_unrealized_pnl
FROM positions
WHERE status = 'OPEN'
GROUP BY portfolio_id, symbol;

COMMENT ON VIEW open_positions_summary IS 'Summary of all open positions by symbol';

-- View: Portfolio Performance
CREATE OR REPLACE VIEW portfolio_performance AS
SELECT 
    p.portfolio_id,
    p.name,
    p.cash_balance,
    p.total_value,
    p.total_pnl,
    p.total_return_pct,
    COUNT(DISTINCT pos.id) FILTER (WHERE pos.status = 'OPEN') as open_positions,
    COUNT(DISTINCT t.id) as total_trades,
    SUM(t.realized_pnl) FILTER (WHERE t.realized_pnl > 0) as total_wins,
    SUM(t.realized_pnl) FILTER (WHERE t.realized_pnl < 0) as total_losses
FROM portfolios p
LEFT JOIN positions pos ON p.portfolio_id = pos.portfolio_id
LEFT JOIN trades t ON p.portfolio_id = t.portfolio_id
GROUP BY p.id;

COMMENT ON VIEW portfolio_performance IS 'Comprehensive portfolio performance metrics';

-- ============================================================================
-- FUNCTIONS
-- ============================================================================

-- Function: Update portfolio updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
CREATE TRIGGER update_portfolios_updated_at
    BEFORE UPDATE ON portfolios
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_positions_updated_at
    BEFORE UPDATE ON positions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMENT ON FUNCTION update_updated_at_column() IS 'Automatically updates updated_at timestamp';

-- ============================================================================
-- INITIAL DATA
-- ============================================================================

-- Insert default paper trading portfolio
INSERT INTO portfolios (
    portfolio_id, 
    name, 
    initial_balance, 
    cash_balance, 
    total_value
) VALUES (
    'paper_trading',
    'Paper Trading Portfolio',
    10000.00,  -- must equal shared/account.py PAPER_INITIAL_BALANCE (ADR-029)
    10000.00,
    10000.00
) ON CONFLICT (portfolio_id) DO NOTHING;

-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================

-- Log migration completion
DO $$
BEGIN
    RAISE NOTICE 'Migration 001_initial_schema.sql completed successfully';
    RAISE NOTICE 'Tables created: portfolios, positions, trades, performance_metrics, audit_log';
    RAISE NOTICE 'Views created: open_positions_summary, portfolio_performance';
    RAISE NOTICE 'Initial data: paper_trading portfolio';
END $$;
