-- Database Optimization Script
-- Run this to create indexes and improve query performance

-- TimescaleDB Market Data Indexes
\c market_data;

-- Index on klines for faster symbol+interval queries
CREATE INDEX IF NOT EXISTS idx_klines_symbol_interval_timestamp
ON klines(symbol, interval, timestamp DESC);

-- Index for recent data queries
CREATE INDEX IF NOT EXISTS idx_klines_created_at
ON klines(created_at DESC);

-- Index for volume analysis
CREATE INDEX IF NOT EXISTS idx_klines_volume
ON klines(symbol, volume) WHERE volume > 0;

-- PostgreSQL Portfolio Database Indexes
\c crypto_trading;

-- Index on positions for faster portfolio queries
CREATE INDEX IF NOT EXISTS idx_positions_symbol
ON positions(symbol) WHERE status = 'open';

CREATE INDEX IF NOT EXISTS idx_positions_timestamp
ON positions(entry_time DESC);

-- Index on trades for performance analysis
CREATE INDEX IF NOT EXISTS idx_trades_symbol_timestamp
ON trades(symbol, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_trades_pnl
ON trades(pnl) WHERE pnl IS NOT NULL;

-- Vacuum and analyze for statistics
VACUUM ANALYZE klines;
VACUUM ANALYZE positions;
VACUUM ANALYZE trades;

SELECT 'Database optimization complete!' as status;
