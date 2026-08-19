"""
Market Data Service - Database Models
Purpose: SQLAlchemy models for TimescaleDB
"""

from sqlalchemy import JSON, Boolean, Column, String, Numeric, BigInteger, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Kline(Base):
    """
    Candlestick/Kline data model
    Stores OHLCV (Open, High, Low, Close, Volume) data

    Optimized for TimescaleDB with time-based partitioning
    """

    __tablename__ = "klines"

    # Primary key: timestamp + symbol + interval
    timestamp = Column(
        BigInteger,
        primary_key=True,
        nullable=False,
        comment="Unix timestamp in milliseconds",
    )
    symbol = Column(
        String(20),
        primary_key=True,
        nullable=False,
        comment="Trading pair (e.g., BTCUSDT)",
    )
    interval = Column(
        String(10),
        primary_key=True,
        nullable=False,
        comment="Candlestick interval (e.g., 1, 5, 60)",
    )

    # OHLCV data
    open = Column(Numeric(20, 8), nullable=False, comment="Opening price")
    high = Column(Numeric(20, 8), nullable=False, comment="Highest price")
    low = Column(Numeric(20, 8), nullable=False, comment="Lowest price")
    close = Column(Numeric(20, 8), nullable=False, comment="Closing price")
    volume = Column(Numeric(20, 8), nullable=False, comment="Trading volume")
    turnover = Column(
        Numeric(30, 8), nullable=True, comment="Trading turnover (volume * price)"
    )

    # Source flag: True for Bybit mainnet, False for testnet. Added
    # 2026-04-29 (audit finding) — earlier the table mixed both, and the
    # 2026-04-25 mid-day flip contaminated backtest history. Default True
    # (`server_default='true'`) so existing rows get the conservative
    # value during the ALTER TABLE migration. Operators who had testnet
    # data before the flip should still wipe (see CLAUDE.md gotcha) — the
    # default-True can't tell apart pre-flip rows by itself.
    is_mainnet = Column(
        Boolean,
        nullable=False,
        server_default=text("true"),
        default=True,
        comment="True for Bybit mainnet rows, False for testnet",
    )

    # Metadata
    created_at = Column(BigInteger, nullable=False, comment="Record creation timestamp")

    # Indexes for efficient querying
    __table_args__ = (
        Index("idx_klines_symbol_interval_time", "symbol", "interval", "timestamp"),
        Index("idx_klines_time", "timestamp"),
        Index("idx_klines_mainnet", "is_mainnet"),
        {"comment": "Candlestick/Kline OHLCV data"},
    )

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "interval": self.interval,
            "open": float(self.open),
            "high": float(self.high),
            "low": float(self.low),
            "close": float(self.close),
            "volume": float(self.volume),
            "turnover": float(self.turnover) if self.turnover else None,
            # `default=True` on the Column applies at INSERT only — an
            # un-flushed Kline() instance keeps the attribute as None.
            # Fall back to True (server default) so to_dict() output is
            # consistent regardless of persistence state.
            "is_mainnet": bool(self.is_mainnet)
            if self.is_mainnet is not None
            else True,
            "created_at": self.created_at,
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
    price_change_24h = Column(
        Numeric(10, 4), nullable=True, comment="24h price change %"
    )

    # Metadata
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index("idx_tickers_symbol_time", "symbol", "timestamp"),
        {"comment": "Real-time ticker data"},
    )

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "last_price": float(self.last_price),
            "bid_price": float(self.bid_price) if self.bid_price else None,
            "ask_price": float(self.ask_price) if self.ask_price else None,
            "high_24h": float(self.high_24h) if self.high_24h else None,
            "low_24h": float(self.low_24h) if self.low_24h else None,
            "volume_24h": float(self.volume_24h) if self.volume_24h else None,
            "turnover_24h": float(self.turnover_24h) if self.turnover_24h else None,
            "price_change_24h": float(self.price_change_24h)
            if self.price_change_24h
            else None,
            "created_at": self.created_at,
        }


class OrderBook(Base):
    """
    Order book snapshots
    Stores bid/ask depth

    NOTE: the DB-level primary key is the COMPOSITE `(id, timestamp)`, not the
    `id` mapped below. TimescaleDB requires the partition column to appear in
    every unique index, and this table is a hypertable partitioned on
    `timestamp`. The reshape is performed by the boot DDL — see
    `app/database.py::DDL_STATEMENTS`. The ORM mapping intentionally keeps `id`
    as the sole key: this model is insert-only and never loads or updates by
    primary key, so declaring the composite here would only make SQLAlchemy
    emit a compound key it does not need.
    """

    __tablename__ = "orderbook_snapshots"

    # Primary key (ORM-level only — see the class docstring; the DB PK is
    # the composite (id, timestamp))
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(BigInteger, nullable=False)
    symbol = Column(String(20), nullable=False)

    # Full 25x2 ladder as JSONB (spec §2 A1; final review H-3). The column was
    # varchar in production until the boot DDL casts it in place — see
    # app/database.py::DDL_STATEMENTS. SQLAlchemy's postgresql.JSONB binds
    # Python dicts directly; do NOT json.dumps() before assigning here.
    # JSON generic type with a postgresql variant so tests running against
    # SQLite (no native JSONB support) still compile the DDL; production
    # (postgresql dialect) gets real JSONB with jsonb operators/GIN indexing.
    snapshot_data = Column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        comment="JSONB snapshot of orderbook",
    )

    # Top-of-book, persisted explicitly so Phase C consumers don't have to
    # parse the whole ladder for the field they read most (final review H-3).
    best_bid = Column(Numeric(38, 8), nullable=True)
    best_ask = Column(Numeric(38, 8), nullable=True)

    # Metadata
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index("idx_orderbook_symbol_time", "symbol", "timestamp"),
        {"comment": "Order book snapshots"},
    )


class OpenInterest(Base):
    """Open-interest history (edge-search v2 A2). Insert-only; unique on
    (symbol, timestamp) so 5min polls of an overlapping window upsert clean."""

    __tablename__ = "open_interest"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(BigInteger, nullable=False)
    symbol = Column(String(20), nullable=False)
    open_interest = Column(Numeric(38, 8), nullable=False)
    # Notional value when Bybit's payload provides it (spec §2 A2; final
    # review H-3). NULL when the venue omits `openInterestValue`.
    open_interest_value = Column(Numeric(38, 8), nullable=True)
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index("idx_oi_symbol_time", "symbol", "timestamp", unique=True),
        {"comment": "Open interest history"},
    )


# TimescaleDB hypertable / retention DDL is NOT declared here.
#
# The authoritative, executed definition is `app/database.py::DDL_STATEMENTS`,
# applied on every service boot by `create_hypertables()`. The former
# `CREATE_HYPERTABLE_SQL` constant that lived at this spot had zero importers
# (dead since it was written) and still asserted the wrong state: unqualified
# table names and a 90-day klines retention policy that would delete the
# backfilled research history. Removed 2026-08-16 (RES-02) so there is exactly
# one place describing this schema.
