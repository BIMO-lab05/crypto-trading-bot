"""
Database ORM Models
SQLAlchemy models matching the database schema
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, List
from uuid import UUID, uuid4

from sqlalchemy import (
    Column, String, DECIMAL, Boolean, DateTime, Integer,
    ForeignKey, Text, CheckConstraint, Index, ARRAY
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .connection import Base


# ==========================================
# PORTFOLIO MODEL
# ==========================================
class Portfolio(Base):
    """Portfolio model - tracks trading accounts"""

    __tablename__ = 'portfolios'

    portfolio_id = Column(String(100), primary_key=True)
    name = Column(String(255), nullable=False)

    # Balance tracking
    initial_balance = Column(DECIMAL(20, 8), nullable=False)
    cash_balance = Column(DECIMAL(20, 8), nullable=False)

    # P&L tracking
    realized_pnl = Column(DECIMAL(20, 8), default=0)
    unrealized_pnl = Column(DECIMAL(20, 8), default=0)
    total_pnl = Column(DECIMAL(20, 8), default=0)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, default=True)

    # Configuration
    trading_mode = Column(String(20), default='PAPER')
    risk_per_trade = Column(DECIMAL(5, 4), default=0.02)
    max_daily_loss = Column(DECIMAL(5, 4), default=0.05)

    # Relationships
    positions = relationship("Position", back_populates="portfolio", lazy="dynamic")
    trades = relationship("Trade", back_populates="portfolio", lazy="dynamic")
    snapshots = relationship("PortfolioSnapshot", back_populates="portfolio", lazy="dynamic")

    # Constraints
    __table_args__ = (
        CheckConstraint('initial_balance > 0', name='check_positive_balance'),
        CheckConstraint("trading_mode IN ('PAPER', 'LIVE')", name='check_trading_mode'),
        Index('idx_portfolios_active', 'is_active'),
    )

    def __repr__(self):
        return f"<Portfolio(id={self.portfolio_id}, name={self.name}, balance={self.cash_balance})>"

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'portfolio_id': self.portfolio_id,
            'name': self.name,
            'initial_balance': float(self.initial_balance),
            'cash_balance': float(self.cash_balance),
            'realized_pnl': float(self.realized_pnl),
            'unrealized_pnl': float(self.unrealized_pnl),
            'total_pnl': float(self.total_pnl),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'is_active': self.is_active,
            'trading_mode': self.trading_mode,
            'risk_per_trade': float(self.risk_per_trade),
            'max_daily_loss': float(self.max_daily_loss),
        }


# ==========================================
# POSITION MODEL
# ==========================================
class Position(Base):
    """Position model - tracks open and closed trading positions"""

    __tablename__ = 'positions'

    position_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    portfolio_id = Column(String(100), ForeignKey('portfolios.portfolio_id'), nullable=False)

    # Position details
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)

    # Quantity and pricing
    quantity = Column(DECIMAL(20, 8), nullable=False)
    entry_price = Column(DECIMAL(20, 8), nullable=False)
    current_price = Column(DECIMAL(20, 8))
    exit_price = Column(DECIMAL(20, 8))

    # Cost basis and P&L
    cost_basis = Column(DECIMAL(20, 8), nullable=False)
    unrealized_pnl = Column(DECIMAL(20, 8), default=0)
    realized_pnl = Column(DECIMAL(20, 8))

    # Risk management
    stop_loss = Column(DECIMAL(20, 8))
    take_profit = Column(DECIMAL(20, 8))

    # Status
    status = Column(String(20), nullable=False, default='OPEN')

    # Strategy and metadata
    strategy = Column(String(50))
    entry_signal_confidence = Column(DECIMAL(5, 4))
    exit_reason = Column(String(100))

    # Timestamps
    opened_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    portfolio = relationship("Portfolio", back_populates="positions")
    trades = relationship("Trade", back_populates="position")

    # Constraints
    __table_args__ = (
        CheckConstraint('quantity > 0', name='check_positive_quantity'),
        CheckConstraint('entry_price > 0', name='check_positive_entry_price'),
        CheckConstraint("side IN ('LONG', 'SHORT')", name='check_valid_side'),
        CheckConstraint("status IN ('OPEN', 'CLOSED')", name='check_valid_status'),
        Index('idx_positions_portfolio', 'portfolio_id'),
        Index('idx_positions_symbol', 'symbol'),
        Index('idx_positions_status', 'status'),
        Index('idx_positions_opened_at', 'opened_at'),
        Index('idx_positions_portfolio_status', 'portfolio_id', 'status'),
    )

    def __repr__(self):
        return f"<Position(id={self.position_id}, symbol={self.symbol}, status={self.status})>"

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'position_id': str(self.position_id),
            'portfolio_id': self.portfolio_id,
            'symbol': self.symbol,
            'side': self.side,
            'quantity': float(self.quantity),
            'entry_price': float(self.entry_price),
            'current_price': float(self.current_price) if self.current_price else None,
            'exit_price': float(self.exit_price) if self.exit_price else None,
            'cost_basis': float(self.cost_basis),
            'unrealized_pnl': float(self.unrealized_pnl),
            'realized_pnl': float(self.realized_pnl) if self.realized_pnl else None,
            'stop_loss': float(self.stop_loss) if self.stop_loss else None,
            'take_profit': float(self.take_profit) if self.take_profit else None,
            'status': self.status,
            'strategy': self.strategy,
            'entry_signal_confidence': float(self.entry_signal_confidence) if self.entry_signal_confidence else None,
            'exit_reason': self.exit_reason,
            'opened_at': self.opened_at.isoformat() if self.opened_at else None,
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


# ==========================================
# TRADE MODEL
# ==========================================
class Trade(Base):
    """Trade model - records all buy/sell transactions"""

    __tablename__ = 'trades'

    trade_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    portfolio_id = Column(String(100), ForeignKey('portfolios.portfolio_id'), nullable=False)
    position_id = Column(PGUUID(as_uuid=True), ForeignKey('positions.position_id'))

    # Trade details
    symbol = Column(String(20), nullable=False)
    action = Column(String(10), nullable=False)
    order_type = Column(String(20), nullable=False)

    # Quantity and pricing
    quantity = Column(DECIMAL(20, 8), nullable=False)
    price = Column(DECIMAL(20, 8), nullable=False)
    total_cost = Column(DECIMAL(20, 8), nullable=False)

    # Fees
    fee = Column(DECIMAL(20, 8), default=0)
    fee_currency = Column(String(10), default='USDT')

    # Execution details
    executed_at = Column(DateTime(timezone=True), server_default=func.now())
    exchange_order_id = Column(String(100))

    # Strategy and signal
    strategy = Column(String(50))
    signal_confidence = Column(DECIMAL(5, 4))
    signal_indicators = Column(JSONB)

    # P&L (for closing trades)
    realized_pnl = Column(DECIMAL(20, 8))
    pnl_percentage = Column(DECIMAL(10, 4))

    # Metadata
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    portfolio = relationship("Portfolio", back_populates="trades")
    position = relationship("Position", back_populates="trades")

    # Constraints
    __table_args__ = (
        CheckConstraint('quantity > 0', name='check_positive_quantity'),
        CheckConstraint('price > 0', name='check_positive_price'),
        CheckConstraint("action IN ('BUY', 'SELL')", name='check_valid_action'),
        CheckConstraint("order_type IN ('MARKET', 'LIMIT', 'STOP', 'STOP_LIMIT')", name='check_valid_order_type'),
        Index('idx_trades_portfolio', 'portfolio_id'),
        Index('idx_trades_symbol', 'symbol'),
        Index('idx_trades_executed_at', 'executed_at'),
        Index('idx_trades_position', 'position_id'),
        Index('idx_trades_portfolio_date', 'portfolio_id', 'executed_at'),
    )

    def __repr__(self):
        return f"<Trade(id={self.trade_id}, symbol={self.symbol}, action={self.action})>"

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'trade_id': str(self.trade_id),
            'portfolio_id': self.portfolio_id,
            'position_id': str(self.position_id) if self.position_id else None,
            'symbol': self.symbol,
            'action': self.action,
            'order_type': self.order_type,
            'quantity': float(self.quantity),
            'price': float(self.price),
            'total_cost': float(self.total_cost),
            'fee': float(self.fee),
            'fee_currency': self.fee_currency,
            'executed_at': self.executed_at.isoformat() if self.executed_at else None,
            'exchange_order_id': self.exchange_order_id,
            'strategy': self.strategy,
            'signal_confidence': float(self.signal_confidence) if self.signal_confidence else None,
            'signal_indicators': self.signal_indicators,
            'realized_pnl': float(self.realized_pnl) if self.realized_pnl else None,
            'pnl_percentage': float(self.pnl_percentage) if self.pnl_percentage else None,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ==========================================
# PORTFOLIO SNAPSHOT MODEL
# ==========================================
class PortfolioSnapshot(Base):
    """Portfolio snapshot model - time-series portfolio state"""

    __tablename__ = 'portfolio_snapshots'

    snapshot_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    portfolio_id = Column(String(100), ForeignKey('portfolios.portfolio_id'), nullable=False)

    # Balance data
    cash_balance = Column(DECIMAL(20, 8), nullable=False)
    positions_value = Column(DECIMAL(20, 8), nullable=False)
    total_value = Column(DECIMAL(20, 8), nullable=False)

    # P&L data
    realized_pnl = Column(DECIMAL(20, 8), default=0)
    unrealized_pnl = Column(DECIMAL(20, 8), default=0)
    total_pnl = Column(DECIMAL(20, 8), default=0)
    total_return_pct = Column(DECIMAL(10, 4), default=0)

    # Performance metrics
    daily_pnl = Column(DECIMAL(20, 8))
    daily_return_pct = Column(DECIMAL(10, 4))

    # Position counts
    open_positions_count = Column(Integer, default=0)
    total_positions_count = Column(Integer, default=0)

    # Asset allocation and holdings (JSON)
    asset_allocation = Column(JSONB)
    holdings = Column(JSONB)

    # Timestamp
    snapshot_time = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    snapshot_type = Column(String(20), default='SCHEDULED')

    # Relationships
    portfolio = relationship("Portfolio", back_populates="snapshots")

    # Constraints
    __table_args__ = (
        CheckConstraint("snapshot_type IN ('SCHEDULED', 'ON_TRADE', 'ON_DEMAND')", name='check_valid_snapshot_type'),
        Index('idx_snapshots_portfolio', 'portfolio_id', 'snapshot_time'),
        Index('idx_snapshots_time', 'snapshot_time'),
    )

    def __repr__(self):
        return f"<PortfolioSnapshot(portfolio={self.portfolio_id}, time={self.snapshot_time})>"

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'snapshot_id': str(self.snapshot_id),
            'portfolio_id': self.portfolio_id,
            'cash_balance': float(self.cash_balance),
            'positions_value': float(self.positions_value),
            'total_value': float(self.total_value),
            'realized_pnl': float(self.realized_pnl),
            'unrealized_pnl': float(self.unrealized_pnl),
            'total_pnl': float(self.total_pnl),
            'total_return_pct': float(self.total_return_pct),
            'daily_pnl': float(self.daily_pnl) if self.daily_pnl else None,
            'daily_return_pct': float(self.daily_return_pct) if self.daily_return_pct else None,
            'open_positions_count': self.open_positions_count,
            'total_positions_count': self.total_positions_count,
            'asset_allocation': self.asset_allocation,
            'holdings': self.holdings,
            'snapshot_time': self.snapshot_time.isoformat() if self.snapshot_time else None,
            'snapshot_type': self.snapshot_type,
        }


# ==========================================
# NOTIFICATION HISTORY MODEL
# ==========================================
class NotificationHistory(Base):
    """Notification history model - audit trail of sent notifications"""

    __tablename__ = 'notification_history'

    notification_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # Notification details
    notification_type = Column(String(50), nullable=False)
    channel = Column(String(20), nullable=False)

    # Content
    subject = Column(String(255))
    message = Column(Text, nullable=False)

    # Status
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String(20), default='SENT')
    error_message = Column(Text)

    # Related entities
    portfolio_id = Column(String(100))
    trade_id = Column(PGUUID(as_uuid=True), ForeignKey('trades.trade_id'))
    position_id = Column(PGUUID(as_uuid=True), ForeignKey('positions.position_id'))

    # Metadata (renamed from 'metadata' to avoid SQLAlchemy reserved word conflict)
    notification_metadata = Column(JSONB)

    # Constraints
    __table_args__ = (
        CheckConstraint("channel IN ('EMAIL', 'TELEGRAM')", name='check_valid_channel'),
        CheckConstraint("status IN ('SENT', 'FAILED', 'PENDING')", name='check_valid_status'),
        Index('idx_notifications_sent_at', 'sent_at'),
        Index('idx_notifications_type', 'notification_type'),
        Index('idx_notifications_portfolio', 'portfolio_id', 'sent_at'),
    )

    def __repr__(self):
        return f"<NotificationHistory(type={self.notification_type}, channel={self.channel}, status={self.status})>"

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'notification_id': str(self.notification_id),
            'notification_type': self.notification_type,
            'channel': self.channel,
            'subject': self.subject,
            'message': self.message,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'status': self.status,
            'error_message': self.error_message,
            'portfolio_id': self.portfolio_id,
            'trade_id': str(self.trade_id) if self.trade_id else None,
            'position_id': str(self.position_id) if self.position_id else None,
            'metadata': self.notification_metadata,
        }
