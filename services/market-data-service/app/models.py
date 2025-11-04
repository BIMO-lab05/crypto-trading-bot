"""
Market Data Service - Database Models
Purpose: SQLAlchemy models for TimescaleDB
"""

from sqlalchemy import Column, String, Numeric, BigInteger, Index, text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from typing import Optional

Base = declarative_base()


class Kline(Base):
    """
    Candlestick/Kline data model
    Stores OHLCV (Open, High, Low, Close, Volume) data
    
    Optimized for TimescaleDB with time-based partitioning
    """
    __tablename__ = "klines"
    
    # Primary key: timestamp + symbol + interval
    timestamp = Column(BigInteger, primary_key=True, nullable=False, comment="Unix timestamp in milliseconds")
    symbol = Column(String(20), primary_key=True, nullable=False, comment="Trading pair (e.g., BTCUSDT)")
    interval = Column(String(10), primary_key=True, nullable=False, comment="Candlestick interval (e.g., 1, 5, 60)")
    
    # OHLCV data
    open = Column(Numeric(20, 8), nullable=False, comment="Opening price")
    high = Column(Numeric(20, 8), nullable=False, comment="Highest price")
    low = Column(Numeric(20, 8), nullable=False, comment="Lowest price")
    close = Column(Numeric(20, 8), nullable=False, comment="Closing price")
    volume = Column(Numeric(20, 8), nullable=False, comment="Trading volume")
    turnover = Column(Numeric(30, 8), nullable=True, comment="Trading turnover (volume * price)")
    
    # Metadata
    created_at = Column(BigInteger, nullable=False, comment="Record creation timestamp")
    
    # Indexes for efficient querying
    __table_args__ = (
        Index('idx_klines_symbol_interval_time', 'symbol', 'interval', 'timestamp'),
        Index('idx_klines_time', 'timestamp'),
        {'comment': 'Candlestick/Kline OHLCV data'}
    )
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'timestamp': self.timestamp,
            'symbol': self.symbol,
            'interval': self.interval,
            'open': float(self.open),
            'high': float(self.high),
            'low': float(self.low),
            'close': float(self.close),
            'volume': float(self.volume),
            'turnover': float(self.turnover) if self.turnover else None,
            'created_at': self.created_at
        }


class Ticker(Base):
    """
    Real-time ticker data
    Stores latest price, 24h volume, etc.
    """
    __tablename__ = "tickers"
    
    # Primary key
    timestamp = Column(BigInteger, primary_key=True, nullable=False)
    symbol = Column(String(20), primary_key=True, nullable=False)
    
    # Price data
    last_price = Column(Numeric(20, 8), nullable=False, comment="Last traded price")
    bid_price = Column(Numeric(20, 8), nullable=True, comment="Best bid price")
    ask_price = Column(Numeric(20, 8), nullable=True, comment="Best ask price")
    
    # 24h statistics
    high_24h = Column(Numeric(20, 8), nullable=True, comment="24h high price")
    low_24h = Column(Numeric(20, 8), nullable=True, comment="24h low price")
    volume_24h = Column(Numeric(20, 8), nullable=True, comment="24h volume")
    turnover_24h = Column(Numeric(30, 8), nullable=True, comment="24h turnover")
    price_change_24h = Column(Numeric(10, 4), nullable=True, comment="24h price change %")
    
    # Metadata
    created_at = Column(BigInteger, nullable=False)
    
    __table_args__ = (
        Index('idx_tickers_symbol_time', 'symbol', 'timestamp'),
        {'comment': 'Real-time ticker data'}
    )
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'timestamp': self.timestamp,
            'symbol': self.symbol,
            'last_price': float(self.last_price),
            'bid_price': float(self.bid_price) if self.bid_price else None,
            'ask_price': float(self.ask_price) if self.ask_price else None,
            'high_24h': float(self.high_24h) if self.high_24h else None,
            'low_24h': float(self.low_24h) if self.low_24h else None,
            'volume_24h': float(self.volume_24h) if self.volume_24h else None,
            'turnover_24h': float(self.turnover_24h) if self.turnover_24h else None,
            'price_change_24h': float(self.price_change_24h) if self.price_change_24h else None,
            'created_at': self.created_at
        }


class OrderBook(Base):
    """
    Order book snapshots
    Stores bid/ask depth
    """
    __tablename__ = "orderbook_snapshots"
    
    # Primary key
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(BigInteger, nullable=False)
    symbol = Column(String(20), nullable=False)
    
    # Order book data (stored as JSON in production, simplified here)
    # In production, you might want separate tables for bids/asks
    snapshot_data = Column(String, nullable=False, comment="JSON snapshot of orderbook")
    
    # Metadata
    created_at = Column(BigInteger, nullable=False)
    
    __table_args__ = (
        Index('idx_orderbook_symbol_time', 'symbol', 'timestamp'),
        {'comment': 'Order book snapshots'}
    )


# SQL to create TimescaleDB hypertable (run after table creation)
CREATE_HYPERTABLE_SQL = """
-- Convert tables to TimescaleDB hypertables
SELECT create_hypertable('klines', 'timestamp', 
    chunk_time_interval => 86400000,  -- 1 day chunks
    if_not_exists => TRUE,
    migrate_data => TRUE
);

SELECT create_hypertable('tickers', 'timestamp',
    chunk_time_interval => 86400000,  -- 1 day chunks  
    if_not_exists => TRUE,
    migrate_data => TRUE
);

SELECT create_hypertable('orderbook_snapshots', 'timestamp',
    chunk_time_interval => 86400000,  -- 1 day chunks
    if_not_exists => TRUE,
    migrate_data => TRUE
);

-- Create continuous aggregates for common queries
CREATE MATERIALIZED VIEW IF NOT EXISTS klines_1h
WITH (timescaledb.continuous) AS
SELECT
    time_bucket(3600000, timestamp) AS bucket,  -- 1 hour buckets
    symbol,
    interval,
    first(open, timestamp) as open,
    max(high) as high,
    min(low) as low,
    last(close, timestamp) as close,
    sum(volume) as volume,
    sum(turnover) as turnover
FROM klines
GROUP BY bucket, symbol, interval
WITH NO DATA;

-- Add refresh policy (refresh every hour)
SELECT add_continuous_aggregate_policy('klines_1h',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Create retention policy (keep data for 90 days)
SELECT add_retention_policy('klines', INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_retention_policy('tickers', INTERVAL '30 days', if_not_exists => TRUE);
SELECT add_retention_policy('orderbook_snapshots', INTERVAL '7 days', if_not_exists => TRUE);
"""
