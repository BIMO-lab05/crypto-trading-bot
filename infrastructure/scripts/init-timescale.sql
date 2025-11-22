-- TimescaleDB initialization script for Crypto Trading Bot
-- Optimized for time-series market data storage

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create schema for market data
CREATE SCHEMA IF NOT EXISTS market_data;

-- OHLCV (Open, High, Low, Close, Volume) candle data
CREATE TABLE IF NOT EXISTS market_data.candles (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    interval VARCHAR(10) NOT NULL,  -- 1m, 5m, 15m, 1h, 4h, 1d
    open DECIMAL(30, 8) NOT NULL,
    high DECIMAL(30, 8) NOT NULL,
    low DECIMAL(30, 8) NOT NULL,
    close DECIMAL(30, 8) NOT NULL,
    volume DECIMAL(30, 8) NOT NULL,
    quote_volume DECIMAL(30, 8),
    trades_count INTEGER,
    UNIQUE(time, symbol, interval)
);

-- Convert to hypertable (TimescaleDB optimization)
SELECT create_hypertable('market_data.candles', 'time', if_not_exists => TRUE);

-- Real-time tick data (trades)
CREATE TABLE IF NOT EXISTS market_data.ticks (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    price DECIMAL(30, 8) NOT NULL,
    quantity DECIMAL(30, 8) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    trade_id VARCHAR(50),
    is_buyer_maker BOOLEAN
);

-- Convert to hypertable
SELECT create_hypertable('market_data.ticks', 'time', if_not_exists => TRUE);

-- Order book snapshots
CREATE TABLE IF NOT EXISTS market_data.orderbook_snapshots (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    bids JSONB NOT NULL,  -- Array of [price, quantity]
    asks JSONB NOT NULL,  -- Array of [price, quantity]
    UNIQUE(time, symbol)
);

-- Convert to hypertable
SELECT create_hypertable('market_data.orderbook_snapshots', 'time', if_not_exists => TRUE);

-- Technical indicators cache
CREATE TABLE IF NOT EXISTS market_data.indicators (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    interval VARCHAR(10) NOT NULL,
    indicator_name VARCHAR(50) NOT NULL,
    value DECIMAL(30, 8),
    metadata JSONB,
    UNIQUE(time, symbol, interval, indicator_name)
);

-- Convert to hypertable
SELECT create_hypertable('market_data.indicators', 'time', if_not_exists => TRUE);

-- Create indexes for query performance
CREATE INDEX idx_candles_symbol_time ON market_data.candles (symbol, time DESC);
CREATE INDEX idx_candles_interval ON market_data.candles (interval, time DESC);
CREATE INDEX idx_ticks_symbol_time ON market_data.ticks (symbol, time DESC);
CREATE INDEX idx_orderbook_symbol_time ON market_data.orderbook_snapshots (symbol, time DESC);
CREATE INDEX idx_indicators_symbol_time ON market_data.indicators (symbol, interval, indicator_name, time DESC);

-- Compression policy: compress data older than 7 days
SELECT add_compression_policy('market_data.candles', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_compression_policy('market_data.ticks', INTERVAL '3 days', if_not_exists => TRUE);
SELECT add_compression_policy('market_data.orderbook_snapshots', INTERVAL '2 days', if_not_exists => TRUE);
SELECT add_compression_policy('market_data.indicators', INTERVAL '7 days', if_not_exists => TRUE);

-- Retention policy: keep data for 90 days (adjust as needed)
SELECT add_retention_policy('market_data.ticks', INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_retention_policy('market_data.orderbook_snapshots', INTERVAL '30 days', if_not_exists => TRUE);

-- Create continuous aggregates for common queries
CREATE MATERIALIZED VIEW IF NOT EXISTS market_data.candles_1h
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS time,
    symbol,
    FIRST(open, time) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, time) AS close,
    SUM(volume) AS volume
FROM market_data.candles
WHERE interval = '1m'
GROUP BY time_bucket('1 hour', time), symbol
WITH NO DATA;

-- Refresh policy for continuous aggregates
SELECT add_continuous_aggregate_policy('market_data.candles_1h',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Create view for latest prices
CREATE OR REPLACE VIEW market_data.latest_prices AS
SELECT DISTINCT ON (symbol)
    symbol,
    close AS price,
    time,
    volume
FROM market_data.candles
WHERE interval = '1m'
ORDER BY symbol, time DESC;

-- Create view for 24h price change
CREATE OR REPLACE VIEW market_data.price_change_24h AS
WITH latest AS (
    SELECT DISTINCT ON (symbol)
        symbol,
        close AS current_price,
        time AS current_time
    FROM market_data.candles
    WHERE interval = '1h'
    ORDER BY symbol, time DESC
),
day_ago AS (
    SELECT DISTINCT ON (symbol)
        symbol,
        close AS previous_price
    FROM market_data.candles
    WHERE interval = '1h'
        AND time <= NOW() - INTERVAL '24 hours'
    ORDER BY symbol, time DESC
)
SELECT
    l.symbol,
    l.current_price,
    d.previous_price,
    l.current_price - d.previous_price AS price_change,
    CASE
        WHEN d.previous_price > 0 THEN
            ((l.current_price - d.previous_price) / d.previous_price * 100)
        ELSE 0
    END AS price_change_percent,
    l.current_time
FROM latest l
LEFT JOIN day_ago d ON l.symbol = d.symbol;

-- Grant permissions
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA market_data TO cryptobot;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA market_data TO cryptobot;
