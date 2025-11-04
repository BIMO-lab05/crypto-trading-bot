-- ==========================================
-- MIGRATION 002: Create All Tables
-- ==========================================
-- Description: Create core tables for trading bot
-- Date: 2025-11-01
-- Depends on: 001_initial_setup.sql
-- ==========================================

\c crypto_trading_bot

-- ==========================================
-- PORTFOLIOS TABLE
-- ==========================================
CREATE TABLE IF NOT EXISTS portfolios (
    portfolio_id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    initial_balance DECIMAL(20, 8) NOT NULL,
    cash_balance DECIMAL(20, 8) NOT NULL,
    realized_pnl DECIMAL(20, 8) DEFAULT 0,
    unrealized_pnl DECIMAL(20, 8) DEFAULT 0,
    total_pnl DECIMAL(20, 8) DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    trading_mode VARCHAR(20) DEFAULT 'PAPER',
    risk_per_trade DECIMAL(5, 4) DEFAULT 0.02,
    max_daily_loss DECIMAL(5, 4) DEFAULT 0.05,
    CONSTRAINT check_positive_balance CHECK (initial_balance > 0),
    CONSTRAINT check_trading_mode CHECK (trading_mode IN ('PAPER', 'LIVE'))
);

CREATE INDEX IF NOT EXISTS idx_portfolios_active ON portfolios(is_active);

-- ==========================================
-- POSITIONS TABLE
-- ==========================================
CREATE TABLE IF NOT EXISTS positions (
    position_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    portfolio_id VARCHAR(100) NOT NULL REFERENCES portfolios(portfolio_id),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    current_price DECIMAL(20, 8),
    exit_price DECIMAL(20, 8),
    cost_basis DECIMAL(20, 8) NOT NULL,
    unrealized_pnl DECIMAL(20, 8) DEFAULT 0,
    realized_pnl DECIMAL(20, 8),
    stop_loss DECIMAL(20, 8),
    take_profit DECIMAL(20, 8),
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    strategy VARCHAR(50),
    entry_signal_confidence DECIMAL(5, 4),
    exit_reason VARCHAR(100),
    opened_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    closed_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT check_positive_quantity CHECK (quantity > 0),
    CONSTRAINT check_positive_entry_price CHECK (entry_price > 0),
    CONSTRAINT check_valid_side CHECK (side IN ('LONG', 'SHORT')),
    CONSTRAINT check_valid_status CHECK (status IN ('OPEN', 'CLOSED'))
);

CREATE INDEX IF NOT EXISTS idx_positions_portfolio ON positions(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_opened_at ON positions(opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_positions_portfolio_status ON positions(portfolio_id, status);

-- ==========================================
-- TRADES TABLE
-- ==========================================
CREATE TABLE IF NOT EXISTS trades (
    trade_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    portfolio_id VARCHAR(100) NOT NULL REFERENCES portfolios(portfolio_id),
    position_id UUID REFERENCES positions(position_id),
    symbol VARCHAR(20) NOT NULL,
    action VARCHAR(10) NOT NULL,
    order_type VARCHAR(20) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    total_cost DECIMAL(20, 8) NOT NULL,
    fee DECIMAL(20, 8) DEFAULT 0,
    fee_currency VARCHAR(10) DEFAULT 'USDT',
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    exchange_order_id VARCHAR(100),
    strategy VARCHAR(50),
    signal_confidence DECIMAL(5, 4),
    signal_indicators JSONB,
    realized_pnl DECIMAL(20, 8),
    pnl_percentage DECIMAL(10, 4),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT check_positive_quantity CHECK (quantity > 0),
    CONSTRAINT check_positive_price CHECK (price > 0),
    CONSTRAINT check_valid_action CHECK (action IN ('BUY', 'SELL')),
    CONSTRAINT check_valid_order_type CHECK (order_type IN ('MARKET', 'LIMIT', 'STOP', 'STOP_LIMIT'))
);

CREATE INDEX IF NOT EXISTS idx_trades_portfolio ON trades(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_executed_at ON trades(executed_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_position ON trades(position_id);
CREATE INDEX IF NOT EXISTS idx_trades_portfolio_date ON trades(portfolio_id, executed_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_signal_indicators ON trades USING GIN (signal_indicators);

-- ==========================================
-- PORTFOLIO_SNAPSHOTS TABLE
-- ==========================================
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    snapshot_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    portfolio_id VARCHAR(100) NOT NULL REFERENCES portfolios(portfolio_id),
    cash_balance DECIMAL(20, 8) NOT NULL,
    positions_value DECIMAL(20, 8) NOT NULL,
    total_value DECIMAL(20, 8) NOT NULL,
    realized_pnl DECIMAL(20, 8) DEFAULT 0,
    unrealized_pnl DECIMAL(20, 8) DEFAULT 0,
    total_pnl DECIMAL(20, 8) DEFAULT 0,
    total_return_pct DECIMAL(10, 4) DEFAULT 0,
    daily_pnl DECIMAL(20, 8),
    daily_return_pct DECIMAL(10, 4),
    open_positions_count INTEGER DEFAULT 0,
    total_positions_count INTEGER DEFAULT 0,
    asset_allocation JSONB,
    holdings JSONB,
    snapshot_time TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    snapshot_type VARCHAR(20) DEFAULT 'SCHEDULED',
    CONSTRAINT check_valid_snapshot_type CHECK (snapshot_type IN ('SCHEDULED', 'ON_TRADE', 'ON_DEMAND'))
);

-- Convert to hypertable (if not already)
SELECT create_hypertable('portfolio_snapshots', 'snapshot_time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 day'
);

CREATE INDEX IF NOT EXISTS idx_snapshots_portfolio ON portfolio_snapshots(portfolio_id, snapshot_time DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_time ON portfolio_snapshots(snapshot_time DESC);

-- ==========================================
-- NOTIFICATION_HISTORY TABLE
-- ==========================================
CREATE TABLE IF NOT EXISTS notification_history (
    notification_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    notification_type VARCHAR(50) NOT NULL,
    channel VARCHAR(20) NOT NULL,
    subject VARCHAR(255),
    message TEXT NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'SENT',
    error_message TEXT,
    portfolio_id VARCHAR(100),
    trade_id UUID REFERENCES trades(trade_id),
    position_id UUID REFERENCES positions(position_id),
    metadata JSONB,
    CONSTRAINT check_valid_channel CHECK (channel IN ('EMAIL', 'TELEGRAM')),
    CONSTRAINT check_valid_status CHECK (status IN ('SENT', 'FAILED', 'PENDING'))
);

CREATE INDEX IF NOT EXISTS idx_notifications_sent_at ON notification_history(sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_type ON notification_history(notification_type);
CREATE INDEX IF NOT EXISTS idx_notifications_portfolio ON notification_history(portfolio_id, sent_at DESC);

-- Log migration
DO $$
BEGIN
    RAISE NOTICE '✅ Migration 002 completed: Core tables created';
END $$;
