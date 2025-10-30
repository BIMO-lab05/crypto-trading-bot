-- PostgreSQL initialization script for Crypto Trading Bot
-- Creates initial database schema and tables

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create schemas for different services
CREATE SCHEMA IF NOT EXISTS trading_engine;
CREATE SCHEMA IF NOT EXISTS portfolio;
CREATE SCHEMA IF NOT EXISTS audit;

-- Trading Engine Tables
CREATE TABLE IF NOT EXISTS trading_engine.strategies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    parameters JSONB,
    is_active BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trading_engine.trades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID REFERENCES trading_engine.strategies(id),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    order_type VARCHAR(20) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8),
    status VARCHAR(20) DEFAULT 'PENDING',
    order_id VARCHAR(100),
    executed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Portfolio Tables
CREATE TABLE IF NOT EXISTS portfolio.balances (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    asset VARCHAR(20) NOT NULL,
    free_balance DECIMAL(20, 8) DEFAULT 0,
    locked_balance DECIMAL(20, 8) DEFAULT 0,
    total_balance DECIMAL(20, 8) GENERATED ALWAYS AS (free_balance + locked_balance) STORED,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(asset)
);

CREATE TABLE IF NOT EXISTS portfolio.positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('LONG', 'SHORT')),
    quantity DECIMAL(20, 8) NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    current_price DECIMAL(20, 8),
    unrealized_pnl DECIMAL(20, 8),
    realized_pnl DECIMAL(20, 8) DEFAULT 0,
    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED')),
    UNIQUE(symbol, status) WHERE status = 'OPEN'
);

-- Audit Tables (for compliance and tracking)
CREATE TABLE IF NOT EXISTS audit.api_calls (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    service_name VARCHAR(50) NOT NULL,
    endpoint VARCHAR(200) NOT NULL,
    method VARCHAR(10) NOT NULL,
    request_data JSONB,
    response_data JSONB,
    status_code INTEGER,
    duration_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit.system_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB,
    severity VARCHAR(20) DEFAULT 'INFO' CHECK (severity IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX idx_trades_symbol ON trading_engine.trades(symbol);
CREATE INDEX idx_trades_created_at ON trading_engine.trades(created_at DESC);
CREATE INDEX idx_trades_status ON trading_engine.trades(status);
CREATE INDEX idx_positions_symbol ON portfolio.positions(symbol);
CREATE INDEX idx_positions_status ON portfolio.positions(status);
CREATE INDEX idx_api_calls_created_at ON audit.api_calls(created_at DESC);
CREATE INDEX idx_system_events_created_at ON audit.system_events(created_at DESC);
CREATE INDEX idx_system_events_severity ON audit.system_events(severity);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to strategies table
CREATE TRIGGER update_strategies_updated_at
    BEFORE UPDATE ON trading_engine.strategies
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Insert default data
INSERT INTO trading_engine.strategies (name, description, parameters, is_active)
VALUES
    ('Simple Moving Average', 'Basic SMA crossover strategy', '{"short_period": 10, "long_period": 50}', false),
    ('RSI Oversold/Overbought', 'Trade on RSI extreme values', '{"rsi_period": 14, "oversold": 30, "overbought": 70}', false)
ON CONFLICT (name) DO NOTHING;

-- Grant permissions (adjust as needed)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA trading_engine TO cryptobot;
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA portfolio TO cryptobot;
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA audit TO cryptobot;
