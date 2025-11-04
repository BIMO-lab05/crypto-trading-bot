-- ==========================================
-- CRYPTO TRADING BOT - DATABASE SCHEMA
-- ==========================================
-- Purpose: Persistent storage for trading data, portfolio tracking, and performance analysis
-- Database: PostgreSQL 14+ with TimescaleDB extension
-- Created: 2025-11-01
-- ==========================================

-- Enable UUID extension for unique identifiers
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable TimescaleDB extension for time-series data
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- ==========================================
-- PORTFOLIOS TABLE
-- ==========================================
-- Stores portfolio configurations and current state
CREATE TABLE portfolios (
    portfolio_id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,

    -- Balance tracking
    initial_balance DECIMAL(20, 8) NOT NULL,
    cash_balance DECIMAL(20, 8) NOT NULL,

    -- P&L tracking
    realized_pnl DECIMAL(20, 8) DEFAULT 0,
    unrealized_pnl DECIMAL(20, 8) DEFAULT 0,
    total_pnl DECIMAL(20, 8) DEFAULT 0,

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,

    -- Configuration
    trading_mode VARCHAR(20) DEFAULT 'PAPER', -- PAPER or LIVE
    risk_per_trade DECIMAL(5, 4) DEFAULT 0.02, -- 2% default
    max_daily_loss DECIMAL(5, 4) DEFAULT 0.05, -- 5% default

    -- Constraints
    CONSTRAINT check_positive_balance CHECK (initial_balance > 0),
    CONSTRAINT check_trading_mode CHECK (trading_mode IN ('PAPER', 'LIVE'))
);

-- Index for active portfolio queries
CREATE INDEX idx_portfolios_active ON portfolios(is_active);

-- ==========================================
-- POSITIONS TABLE
-- ==========================================
-- Stores all trading positions (open and closed)
CREATE TABLE positions (
    position_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    portfolio_id VARCHAR(100) NOT NULL REFERENCES portfolios(portfolio_id),

    -- Position details
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL, -- LONG or SHORT

    -- Quantity and pricing
    quantity DECIMAL(20, 8) NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    current_price DECIMAL(20, 8),
    exit_price DECIMAL(20, 8),

    -- Cost basis and P&L
    cost_basis DECIMAL(20, 8) NOT NULL,
    unrealized_pnl DECIMAL(20, 8) DEFAULT 0,
    realized_pnl DECIMAL(20, 8),

    -- Risk management
    stop_loss DECIMAL(20, 8),
    take_profit DECIMAL(20, 8),

    -- Status tracking
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN', -- OPEN or CLOSED

    -- Strategy and metadata
    strategy VARCHAR(50),
    entry_signal_confidence DECIMAL(5, 4),
    exit_reason VARCHAR(100),

    -- Timestamps
    opened_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    closed_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    CONSTRAINT check_positive_quantity CHECK (quantity > 0),
    CONSTRAINT check_positive_entry_price CHECK (entry_price > 0),
    CONSTRAINT check_valid_side CHECK (side IN ('LONG', 'SHORT')),
    CONSTRAINT check_valid_status CHECK (status IN ('OPEN', 'CLOSED'))
);

-- Indexes for common queries
CREATE INDEX idx_positions_portfolio ON positions(portfolio_id);
CREATE INDEX idx_positions_symbol ON positions(symbol);
CREATE INDEX idx_positions_status ON positions(status);
CREATE INDEX idx_positions_opened_at ON positions(opened_at DESC);

-- Composite index for portfolio + status queries
CREATE INDEX idx_positions_portfolio_status ON positions(portfolio_id, status);

-- ==========================================
-- TRADES TABLE
-- ==========================================
-- Stores all executed trades (buy/sell transactions)
CREATE TABLE trades (
    trade_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    portfolio_id VARCHAR(100) NOT NULL REFERENCES portfolios(portfolio_id),
    position_id UUID REFERENCES positions(position_id),

    -- Trade details
    symbol VARCHAR(20) NOT NULL,
    action VARCHAR(10) NOT NULL, -- BUY or SELL
    order_type VARCHAR(20) NOT NULL, -- MARKET, LIMIT, STOP

    -- Quantity and pricing
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    total_cost DECIMAL(20, 8) NOT NULL,

    -- Fees
    fee DECIMAL(20, 8) DEFAULT 0,
    fee_currency VARCHAR(10) DEFAULT 'USDT',

    -- Execution details
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    exchange_order_id VARCHAR(100), -- For live trading

    -- Strategy and signal
    strategy VARCHAR(50),
    signal_confidence DECIMAL(5, 4),
    signal_indicators JSONB, -- Store all indicator values at trade time

    -- P&L (for closing trades)
    realized_pnl DECIMAL(20, 8),
    pnl_percentage DECIMAL(10, 4),

    -- Metadata
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    CONSTRAINT check_positive_quantity CHECK (quantity > 0),
    CONSTRAINT check_positive_price CHECK (price > 0),
    CONSTRAINT check_valid_action CHECK (action IN ('BUY', 'SELL')),
    CONSTRAINT check_valid_order_type CHECK (order_type IN ('MARKET', 'LIMIT', 'STOP', 'STOP_LIMIT'))
);

-- Indexes for trade queries
CREATE INDEX idx_trades_portfolio ON trades(portfolio_id);
CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_executed_at ON trades(executed_at DESC);
CREATE INDEX idx_trades_position ON trades(position_id);

-- Composite index for portfolio + date range queries
CREATE INDEX idx_trades_portfolio_date ON trades(portfolio_id, executed_at DESC);

-- JSONB index for signal indicators
CREATE INDEX idx_trades_signal_indicators ON trades USING GIN (signal_indicators);

-- ==========================================
-- PORTFOLIO_SNAPSHOTS TABLE (Time-Series)
-- ==========================================
-- Historical snapshots of portfolio state for performance tracking
CREATE TABLE portfolio_snapshots (
    snapshot_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    portfolio_id VARCHAR(100) NOT NULL REFERENCES portfolios(portfolio_id),

    -- Balance data
    cash_balance DECIMAL(20, 8) NOT NULL,
    positions_value DECIMAL(20, 8) NOT NULL,
    total_value DECIMAL(20, 8) NOT NULL,

    -- P&L data
    realized_pnl DECIMAL(20, 8) DEFAULT 0,
    unrealized_pnl DECIMAL(20, 8) DEFAULT 0,
    total_pnl DECIMAL(20, 8) DEFAULT 0,
    total_return_pct DECIMAL(10, 4) DEFAULT 0,

    -- Performance metrics
    daily_pnl DECIMAL(20, 8),
    daily_return_pct DECIMAL(10, 4),

    -- Position counts
    open_positions_count INTEGER DEFAULT 0,
    total_positions_count INTEGER DEFAULT 0,

    -- Asset allocation (JSON for flexibility)
    asset_allocation JSONB,

    -- Holdings snapshot (JSON array of current holdings)
    holdings JSONB,

    -- Timestamp
    snapshot_time TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Snapshot type
    snapshot_type VARCHAR(20) DEFAULT 'SCHEDULED', -- SCHEDULED, ON_TRADE, ON_DEMAND

    CONSTRAINT check_valid_snapshot_type CHECK (snapshot_type IN ('SCHEDULED', 'ON_TRADE', 'ON_DEMAND'))
);

-- Convert to hypertable for TimescaleDB (time-series optimization)
SELECT create_hypertable('portfolio_snapshots', 'snapshot_time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 day'
);

-- Indexes for snapshot queries
CREATE INDEX idx_snapshots_portfolio ON portfolio_snapshots(portfolio_id, snapshot_time DESC);
CREATE INDEX idx_snapshots_time ON portfolio_snapshots(snapshot_time DESC);

-- ==========================================
-- MARKET_DATA TABLE (Time-Series)
-- ==========================================
-- Historical market data for backtesting and analysis
CREATE TABLE market_data (
    symbol VARCHAR(20) NOT NULL,
    interval VARCHAR(10) NOT NULL, -- 1m, 5m, 15m, 1h, 4h, 1d

    -- OHLCV data
    open_time TIMESTAMP WITH TIME ZONE NOT NULL,
    close_time TIMESTAMP WITH TIME ZONE NOT NULL,
    open_price DECIMAL(20, 8) NOT NULL,
    high_price DECIMAL(20, 8) NOT NULL,
    low_price DECIMAL(20, 8) NOT NULL,
    close_price DECIMAL(20, 8) NOT NULL,
    volume DECIMAL(20, 8) NOT NULL,

    -- Additional metrics
    quote_volume DECIMAL(20, 8),
    num_trades INTEGER,

    -- Technical indicators (calculated and stored)
    rsi_14 DECIMAL(10, 4),
    macd_line DECIMAL(20, 8),
    macd_signal DECIMAL(20, 8),
    macd_histogram DECIMAL(20, 8),
    bb_upper DECIMAL(20, 8),
    bb_middle DECIMAL(20, 8),
    bb_lower DECIMAL(20, 8),
    sma_20 DECIMAL(20, 8),
    ema_20 DECIMAL(20, 8),

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Composite primary key
    PRIMARY KEY (symbol, interval, open_time)
);

-- Convert to hypertable for TimescaleDB
SELECT create_hypertable('market_data', 'open_time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '7 days'
);

-- Indexes for market data queries
CREATE INDEX idx_market_data_symbol_interval ON market_data(symbol, interval, open_time DESC);

-- ==========================================
-- TRADING_SIGNALS TABLE (Time-Series)
-- ==========================================
-- Historical trading signals for analysis and optimization
CREATE TABLE trading_signals (
    signal_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Symbol and timing
    symbol VARCHAR(20) NOT NULL,
    interval VARCHAR(10) NOT NULL,
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Signal details
    action VARCHAR(10) NOT NULL, -- BUY, SELL, HOLD
    confidence DECIMAL(5, 4) NOT NULL,
    strategy VARCHAR(50) NOT NULL,

    -- All indicator values at signal time
    indicators JSONB NOT NULL,

    -- Market conditions
    current_price DECIMAL(20, 8) NOT NULL,
    volume DECIMAL(20, 8),

    -- Whether signal was acted upon
    was_executed BOOLEAN DEFAULT FALSE,
    executed_trade_id UUID REFERENCES trades(trade_id),

    -- Outcome tracking (for signal effectiveness analysis)
    outcome VARCHAR(20), -- PROFIT, LOSS, NEUTRAL
    outcome_pnl DECIMAL(20, 8),

    CONSTRAINT check_valid_signal_action CHECK (action IN ('BUY', 'SELL', 'HOLD')),
    CONSTRAINT check_confidence_range CHECK (confidence >= 0 AND confidence <= 1)
);

-- Convert to hypertable
SELECT create_hypertable('trading_signals', 'generated_at',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '7 days'
);

-- Indexes for signal queries
CREATE INDEX idx_signals_symbol ON trading_signals(symbol, generated_at DESC);
CREATE INDEX idx_signals_executed ON trading_signals(was_executed);
CREATE INDEX idx_signals_outcome ON trading_signals(outcome);

-- JSONB index for indicators
CREATE INDEX idx_signals_indicators ON trading_signals USING GIN (indicators);

-- ==========================================
-- PERFORMANCE_METRICS TABLE (Time-Series)
-- ==========================================
-- Daily/hourly performance metrics for analytics
CREATE TABLE performance_metrics (
    metric_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    portfolio_id VARCHAR(100) NOT NULL REFERENCES portfolios(portfolio_id),

    -- Time period
    period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    period_end TIMESTAMP WITH TIME ZONE NOT NULL,
    period_type VARCHAR(20) NOT NULL, -- HOUR, DAY, WEEK, MONTH

    -- Trading metrics
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    win_rate DECIMAL(5, 4) DEFAULT 0,

    -- P&L metrics
    gross_profit DECIMAL(20, 8) DEFAULT 0,
    gross_loss DECIMAL(20, 8) DEFAULT 0,
    net_pnl DECIMAL(20, 8) DEFAULT 0,

    -- Performance ratios
    profit_factor DECIMAL(10, 4),
    sharpe_ratio DECIMAL(10, 4),
    max_drawdown DECIMAL(10, 4),
    max_drawdown_pct DECIMAL(10, 4),

    -- Trade statistics
    avg_win DECIMAL(20, 8),
    avg_loss DECIMAL(20, 8),
    largest_win DECIMAL(20, 8),
    largest_loss DECIMAL(20, 8),

    -- Portfolio values
    starting_balance DECIMAL(20, 8),
    ending_balance DECIMAL(20, 8),
    period_return DECIMAL(10, 4),

    -- Volume
    total_volume DECIMAL(20, 8),

    CONSTRAINT check_valid_period_type CHECK (period_type IN ('HOUR', 'DAY', 'WEEK', 'MONTH'))
);

-- Convert to hypertable
SELECT create_hypertable('performance_metrics', 'period_start',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '30 days'
);

-- Indexes for metrics queries
CREATE INDEX idx_metrics_portfolio ON performance_metrics(portfolio_id, period_start DESC);
CREATE INDEX idx_metrics_period ON performance_metrics(period_type, period_start DESC);

-- ==========================================
-- SYSTEM_LOGS TABLE (Time-Series)
-- ==========================================
-- System events, errors, and notifications
CREATE TABLE system_logs (
    log_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Log details
    log_level VARCHAR(20) NOT NULL, -- DEBUG, INFO, WARNING, ERROR, CRITICAL
    service VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,

    -- Context
    portfolio_id VARCHAR(100),
    trade_id UUID,
    position_id UUID,

    -- Additional data
    details JSONB,
    stack_trace TEXT,

    -- Notification status
    notification_sent BOOLEAN DEFAULT FALSE,
    notification_channels TEXT[], -- email, telegram, etc.

    -- Timestamp
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT check_valid_log_level CHECK (log_level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'))
);

-- Convert to hypertable
SELECT create_hypertable('system_logs', 'created_at',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '7 days'
);

-- Indexes for log queries
CREATE INDEX idx_logs_level ON system_logs(log_level, created_at DESC);
CREATE INDEX idx_logs_service ON system_logs(service, created_at DESC);
CREATE INDEX idx_logs_portfolio ON system_logs(portfolio_id, created_at DESC);

-- ==========================================
-- NOTIFICATION_HISTORY TABLE
-- ==========================================
-- Track all sent notifications for audit
CREATE TABLE notification_history (
    notification_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Notification details
    notification_type VARCHAR(50) NOT NULL, -- TRADE, PROFIT, LOSS, ERROR, DAILY_LIMIT, STARTUP
    channel VARCHAR(20) NOT NULL, -- EMAIL, TELEGRAM

    -- Content
    subject VARCHAR(255),
    message TEXT NOT NULL,

    -- Status
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'SENT', -- SENT, FAILED, PENDING
    error_message TEXT,

    -- Related entities
    portfolio_id VARCHAR(100),
    trade_id UUID REFERENCES trades(trade_id),
    position_id UUID REFERENCES positions(position_id),

    -- Metadata
    metadata JSONB,

    CONSTRAINT check_valid_channel CHECK (channel IN ('EMAIL', 'TELEGRAM')),
    CONSTRAINT check_valid_status CHECK (status IN ('SENT', 'FAILED', 'PENDING'))
);

-- Indexes for notification queries
CREATE INDEX idx_notifications_sent_at ON notification_history(sent_at DESC);
CREATE INDEX idx_notifications_type ON notification_history(notification_type);
CREATE INDEX idx_notifications_portfolio ON notification_history(portfolio_id, sent_at DESC);

-- ==========================================
-- TRIGGERS
-- ==========================================

-- Update updated_at timestamp on portfolios
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_portfolios_updated_at BEFORE UPDATE ON portfolios
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_positions_updated_at BEFORE UPDATE ON positions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ==========================================
-- VIEWS
-- ==========================================

-- Active positions view with current P&L
CREATE OR REPLACE VIEW v_active_positions AS
SELECT
    p.*,
    (p.current_price - p.entry_price) * p.quantity AS current_unrealized_pnl,
    ((p.current_price - p.entry_price) / p.entry_price) * 100 AS unrealized_pnl_pct
FROM positions p
WHERE p.status = 'OPEN';

-- Daily trading summary view
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

-- Portfolio performance view
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

-- ==========================================
-- INITIAL DATA
-- ==========================================

-- Create default paper trading portfolio
INSERT INTO portfolios (portfolio_id, name, initial_balance, cash_balance, trading_mode)
VALUES ('default', 'Default Paper Trading Portfolio', 10000.00, 10000.00, 'PAPER')
ON CONFLICT (portfolio_id) DO NOTHING;

-- ==========================================
-- DATA RETENTION POLICIES (TimescaleDB)
-- ==========================================

-- Keep detailed market data for 90 days, then aggregate to hourly
SELECT add_retention_policy('market_data', INTERVAL '90 days', if_not_exists => TRUE);

-- Keep detailed signals for 90 days
SELECT add_retention_policy('trading_signals', INTERVAL '90 days', if_not_exists => TRUE);

-- Keep system logs for 30 days
SELECT add_retention_policy('system_logs', INTERVAL '30 days', if_not_exists => TRUE);

-- Keep portfolio snapshots indefinitely (compressed)
-- Enable compression after 7 days
SELECT add_compression_policy('portfolio_snapshots', INTERVAL '7 days', if_not_exists => TRUE);

-- ==========================================
-- COMMENTS
-- ==========================================

COMMENT ON TABLE portfolios IS 'Portfolio configurations and current state';
COMMENT ON TABLE positions IS 'All trading positions (open and closed)';
COMMENT ON TABLE trades IS 'All executed trades (buy/sell transactions)';
COMMENT ON TABLE portfolio_snapshots IS 'Historical portfolio state snapshots for performance tracking';
COMMENT ON TABLE market_data IS 'Historical OHLCV market data with technical indicators';
COMMENT ON TABLE trading_signals IS 'Historical trading signals for analysis';
COMMENT ON TABLE performance_metrics IS 'Aggregated performance metrics by time period';
COMMENT ON TABLE system_logs IS 'System events, errors, and notifications';
COMMENT ON TABLE notification_history IS 'Audit trail of all sent notifications';

-- ==========================================
-- END OF SCHEMA
-- ==========================================
