"""
Database ORM Models
SQLAlchemy models matching the database schema
"""

from typing import Dict
from uuid import uuid4

from sqlalchemy import (
    Column,
    String,
    DECIMAL,
    Boolean,
    DateTime,
    Integer,
    ForeignKey,
    Text,
    CheckConstraint,
    Index,
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

    __tablename__ = "portfolios"

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
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    is_active = Column(Boolean, default=True)

    # Configuration
    trading_mode = Column(String(20), default="PAPER")
    risk_per_trade = Column(DECIMAL(5, 4), default=0.02)
    max_daily_loss = Column(DECIMAL(5, 4), default=0.05)

    # Relationships
    positions = relationship("Position", back_populates="portfolio", lazy="dynamic")
    trades = relationship("Trade", back_populates="portfolio", lazy="dynamic")
    snapshots = relationship(
        "PortfolioSnapshot", back_populates="portfolio", lazy="dynamic"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint("initial_balance > 0", name="check_positive_balance"),
        CheckConstraint("trading_mode IN ('PAPER', 'LIVE')", name="check_trading_mode"),
        Index("idx_portfolios_active", "is_active"),
    )

    def __repr__(self):
        return f"<Portfolio(id={self.portfolio_id}, name={self.name}, balance={self.cash_balance})>"

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "portfolio_id": self.portfolio_id,
            "name": self.name,
            "initial_balance": float(self.initial_balance),
            "cash_balance": float(self.cash_balance),
            "realized_pnl": float(self.realized_pnl),
            "unrealized_pnl": float(self.unrealized_pnl),
            "total_pnl": float(self.total_pnl),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_active": self.is_active,
            "trading_mode": self.trading_mode,
            "risk_per_trade": float(self.risk_per_trade),
            "max_daily_loss": float(self.max_daily_loss),
        }


# ==========================================
# POSITION MODEL
# ==========================================
class Position(Base):
    """Position model - tracks open and closed trading positions"""

    __tablename__ = "positions"

    position_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    portfolio_id = Column(
        String(100), ForeignKey("portfolios.portfolio_id"), nullable=False
    )

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
    # NET of commissions (entry + exit legs) as of 2026-08-04 (AUDIT.md 6.2/H7).
    # Accumulates across partial exits; before that date rows held gross P&L.
    realized_pnl = Column(DECIMAL(20, 8))

    # Partial-exit + fee accounting (2026-08-04, AUDIT.md 6.6/H5+H7,
    # migration database/migrations/007_position_fee_partial_exit_accounting.sql).
    # remaining_quantity: quantity still open after partial exits (0 when
    # CLOSED). Without it, restarts resurrected already-sold quantity.
    remaining_quantity = Column(DECIMAL(20, 8))
    # entry_fee: commission paid on the opening leg(s) (scale-ins accumulate).
    # exit_fee: accumulated commissions on reduce/close legs.
    entry_fee = Column(DECIMAL(20, 8), nullable=False, default=0)
    exit_fee = Column(DECIMAL(20, 8), nullable=False, default=0)

    # Added by migration 008 (2026-08-07, Stage 0). posted_margin is the
    # dollar margin still posted; leverage is recorded for audit only.
    # exit_kind is a structured close reason stored ALONGSIDE the free-text
    # exit_reason, which is left untouched (API-visible, not backfilled).
    # No CheckConstraint on exit_kind deliberately: trades.order_type already
    # carries a CHECK that disagrees with its enum, and a stale CHECK rejects
    # valid writes.
    posted_margin = Column(DECIMAL(20, 8), nullable=False, default=0)
    leverage = Column(DECIMAL(10, 4), nullable=False, default=1)
    exit_kind = Column(String(30), nullable=True)

    # Risk management
    stop_loss = Column(DECIMAL(20, 8))
    take_profit = Column(DECIMAL(20, 8))

    # Status
    status = Column(String(20), nullable=False, default="OPEN")

    # Strategy and metadata
    strategy = Column(String(50))
    entry_signal_confidence = Column(DECIMAL(5, 4))
    exit_reason = Column(String(100))

    # Timestamps
    opened_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_at = Column(DateTime(timezone=True))
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    portfolio = relationship("Portfolio", back_populates="positions")
    trades = relationship("Trade", back_populates="position")

    # Constraints
    __table_args__ = (
        CheckConstraint("quantity > 0", name="check_positive_quantity"),
        CheckConstraint("entry_price > 0", name="check_positive_entry_price"),
        CheckConstraint("side IN ('LONG', 'SHORT')", name="check_valid_side"),
        CheckConstraint("status IN ('OPEN', 'CLOSED')", name="check_valid_status"),
        Index("idx_positions_portfolio", "portfolio_id"),
        Index("idx_positions_symbol", "symbol"),
        Index("idx_positions_status", "status"),
        Index("idx_positions_opened_at", "opened_at"),
        Index("idx_positions_portfolio_status", "portfolio_id", "status"),
    )

    def __repr__(self):
        return f"<Position(id={self.position_id}, symbol={self.symbol}, status={self.status})>"

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "position_id": str(self.position_id),
            "portfolio_id": self.portfolio_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": float(self.quantity),
            "entry_price": float(self.entry_price),
            "current_price": float(self.current_price) if self.current_price else None,
            "exit_price": float(self.exit_price) if self.exit_price else None,
            "cost_basis": float(self.cost_basis),
            "unrealized_pnl": float(self.unrealized_pnl),
            "realized_pnl": float(self.realized_pnl) if self.realized_pnl else None,
            "remaining_quantity": float(self.remaining_quantity)
            if self.remaining_quantity is not None
            else None,
            "entry_fee": float(self.entry_fee) if self.entry_fee is not None else 0.0,
            "exit_fee": float(self.exit_fee) if self.exit_fee is not None else 0.0,
            "posted_margin": float(self.posted_margin)
            if self.posted_margin is not None
            else 0.0,
            "leverage": float(self.leverage) if self.leverage is not None else 1.0,
            "exit_kind": self.exit_kind,
            "stop_loss": float(self.stop_loss) if self.stop_loss else None,
            "take_profit": float(self.take_profit) if self.take_profit else None,
            "status": self.status,
            "strategy": self.strategy,
            "entry_signal_confidence": float(self.entry_signal_confidence)
            if self.entry_signal_confidence
            else None,
            "exit_reason": self.exit_reason,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ==========================================
# TRADE MODEL
# ==========================================
class Trade(Base):
    """Trade model - records all buy/sell transactions"""

    __tablename__ = "trades"

    trade_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    portfolio_id = Column(
        String(100), ForeignKey("portfolios.portfolio_id"), nullable=False
    )
    position_id = Column(PGUUID(as_uuid=True), ForeignKey("positions.position_id"))

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
    fee_currency = Column(String(10), default="USDT")

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
        CheckConstraint("quantity > 0", name="check_positive_quantity"),
        CheckConstraint("price > 0", name="check_positive_price"),
        CheckConstraint("action IN ('BUY', 'SELL')", name="check_valid_action"),
        CheckConstraint(
            "order_type IN ('MARKET', 'LIMIT', 'STOP', 'STOP_LIMIT')",
            name="check_valid_order_type",
        ),
        Index("idx_trades_portfolio", "portfolio_id"),
        Index("idx_trades_symbol", "symbol"),
        Index("idx_trades_executed_at", "executed_at"),
        Index("idx_trades_position", "position_id"),
        Index("idx_trades_portfolio_date", "portfolio_id", "executed_at"),
    )

    def __repr__(self):
        return (
            f"<Trade(id={self.trade_id}, symbol={self.symbol}, action={self.action})>"
        )

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "trade_id": str(self.trade_id),
            "portfolio_id": self.portfolio_id,
            "position_id": str(self.position_id) if self.position_id else None,
            "symbol": self.symbol,
            "action": self.action,
            "order_type": self.order_type,
            "quantity": float(self.quantity),
            "price": float(self.price),
            "total_cost": float(self.total_cost),
            "fee": float(self.fee),
            "fee_currency": self.fee_currency,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "exchange_order_id": self.exchange_order_id,
            "strategy": self.strategy,
            "signal_confidence": float(self.signal_confidence)
            if self.signal_confidence
            else None,
            "signal_indicators": self.signal_indicators,
            "realized_pnl": float(self.realized_pnl) if self.realized_pnl else None,
            "pnl_percentage": float(self.pnl_percentage)
            if self.pnl_percentage
            else None,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ==========================================
# PORTFOLIO SNAPSHOT MODEL
# ==========================================
class PortfolioSnapshot(Base):
    """Portfolio snapshot model - time-series portfolio state"""

    __tablename__ = "portfolio_snapshots"

    snapshot_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    portfolio_id = Column(
        String(100), ForeignKey("portfolios.portfolio_id"), nullable=False
    )

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
    snapshot_time = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    snapshot_type = Column(String(20), default="SCHEDULED")

    # Relationships
    portfolio = relationship("Portfolio", back_populates="snapshots")

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "snapshot_type IN ('SCHEDULED', 'ON_TRADE', 'ON_DEMAND')",
            name="check_valid_snapshot_type",
        ),
        Index("idx_snapshots_portfolio", "portfolio_id", "snapshot_time"),
        Index("idx_snapshots_time", "snapshot_time"),
    )

    def __repr__(self):
        return f"<PortfolioSnapshot(portfolio={self.portfolio_id}, time={self.snapshot_time})>"

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "snapshot_id": str(self.snapshot_id),
            "portfolio_id": self.portfolio_id,
            "cash_balance": float(self.cash_balance),
            "positions_value": float(self.positions_value),
            "total_value": float(self.total_value),
            "realized_pnl": float(self.realized_pnl),
            "unrealized_pnl": float(self.unrealized_pnl),
            "total_pnl": float(self.total_pnl),
            "total_return_pct": float(self.total_return_pct),
            "daily_pnl": float(self.daily_pnl) if self.daily_pnl else None,
            "daily_return_pct": float(self.daily_return_pct)
            if self.daily_return_pct
            else None,
            "open_positions_count": self.open_positions_count,
            "total_positions_count": self.total_positions_count,
            "asset_allocation": self.asset_allocation,
            "holdings": self.holdings,
            "snapshot_time": self.snapshot_time.isoformat()
            if self.snapshot_time
            else None,
            "snapshot_type": self.snapshot_type,
        }


# ==========================================
# NOTIFICATION HISTORY MODEL
# ==========================================
class NotificationHistory(Base):
    """Notification history model - audit trail of sent notifications"""

    __tablename__ = "notification_history"

    notification_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # Notification details
    notification_type = Column(String(50), nullable=False)
    channel = Column(String(20), nullable=False)

    # Content
    subject = Column(String(255))
    message = Column(Text, nullable=False)

    # Status
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String(20), default="SENT")
    error_message = Column(Text)

    # Related entities
    portfolio_id = Column(String(100))
    trade_id = Column(PGUUID(as_uuid=True), ForeignKey("trades.trade_id"))
    position_id = Column(PGUUID(as_uuid=True), ForeignKey("positions.position_id"))

    # Metadata (renamed from 'metadata' to avoid SQLAlchemy reserved word conflict)
    notification_metadata = Column(JSONB)

    # Constraints
    __table_args__ = (
        CheckConstraint("channel IN ('EMAIL', 'TELEGRAM')", name="check_valid_channel"),
        CheckConstraint(
            "status IN ('SENT', 'FAILED', 'PENDING')", name="check_valid_status"
        ),
        Index("idx_notifications_sent_at", "sent_at"),
        Index("idx_notifications_type", "notification_type"),
        Index("idx_notifications_portfolio", "portfolio_id", "sent_at"),
    )

    def __repr__(self):
        return f"<NotificationHistory(type={self.notification_type}, channel={self.channel}, status={self.status})>"

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "notification_id": str(self.notification_id),
            "notification_type": self.notification_type,
            "channel": self.channel,
            "subject": self.subject,
            "message": self.message,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "status": self.status,
            "error_message": self.error_message,
            "portfolio_id": self.portfolio_id,
            "trade_id": str(self.trade_id) if self.trade_id else None,
            "position_id": str(self.position_id) if self.position_id else None,
            "metadata": self.notification_metadata,
        }


# ==========================================
# TRADE ANALYSIS MODEL (Phase 4.3)
# ==========================================
class TradeAnalysis(Base):
    """
    Trade analysis model - stores post-trade analysis results

    Phase 4.3: Post-Trade Analysis System

    Stores comprehensive analysis of each trade including:
    - Slippage breakdown (market impact, spread, timing)
    - Execution quality metrics (implementation shortfall, quality score)
    - Trade classification (execution style, market conditions, liquidity)
    - Recommendations for improvement
    """

    __tablename__ = "trade_analysis"

    # Primary key
    analysis_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # Reference to original trade
    trade_id = Column(String(100), nullable=False, unique=True)

    # Trade details
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)
    size = Column(DECIMAL(20, 8), nullable=False)

    # Pricing
    expected_price = Column(DECIMAL(20, 8), nullable=False)
    execution_price = Column(DECIMAL(20, 8), nullable=False)

    # Slippage breakdown
    slippage_market_impact = Column(DECIMAL(20, 8), default=0)
    slippage_spread_cost = Column(DECIMAL(20, 8), default=0)
    slippage_timing_cost = Column(DECIMAL(20, 8), default=0)
    slippage_total = Column(DECIMAL(20, 8), default=0)
    slippage_bps = Column(DECIMAL(10, 4), default=0)

    # Costs
    fees = Column(DECIMAL(20, 8), default=0)
    total_cost = Column(DECIMAL(20, 8), default=0)
    cost_bps = Column(DECIMAL(10, 4), default=0)

    # Execution quality metrics
    implementation_shortfall = Column(DECIMAL(20, 8), default=0)
    implementation_shortfall_bps = Column(DECIMAL(10, 4), default=0)
    price_improvement = Column(DECIMAL(20, 8), default=0)
    price_improvement_bps = Column(DECIMAL(10, 4), default=0)
    fill_rate = Column(DECIMAL(5, 2), default=100)
    time_to_completion = Column(DECIMAL(10, 3), default=0)
    spread_capture_rate = Column(DECIMAL(5, 2), default=0)
    quality_score = Column(Integer, nullable=False)
    quality_grade = Column(String(20), nullable=False)

    # Benchmark comparisons (JSON)
    benchmark_comparisons = Column(JSONB)

    # Trade classification
    execution_style = Column(String(20), nullable=False)
    market_condition = Column(String(20), nullable=False)
    liquidity_level = Column(String(20), nullable=False)
    trading_session = Column(String(20), nullable=False)
    order_urgency = Column(String(20), default="normal")

    # Strategy
    strategy = Column(String(50))

    # Recommendations (JSON array)
    recommendations = Column(JSONB)

    # Timestamps
    decision_timestamp = Column(DateTime(timezone=True))
    execution_timestamp = Column(DateTime(timezone=True))
    analyzed_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Additional market data (JSON)
    market_data = Column(JSONB)

    # Constraints and Indices
    __table_args__ = (
        CheckConstraint("size > 0", name="check_positive_size"),
        CheckConstraint("expected_price > 0", name="check_positive_expected_price"),
        CheckConstraint("execution_price > 0", name="check_positive_execution_price"),
        CheckConstraint(
            "quality_score >= 0 AND quality_score <= 100",
            name="check_valid_quality_score",
        ),
        CheckConstraint("side IN ('BUY', 'SELL')", name="check_valid_trade_side"),
        CheckConstraint(
            "quality_grade IN ('excellent', 'good', 'fair', 'poor', 'very_poor')",
            name="check_valid_quality_grade",
        ),
        CheckConstraint(
            "execution_style IN ('aggressive', 'passive', 'hybrid')",
            name="check_valid_execution_style",
        ),
        CheckConstraint(
            "market_condition IN ('volatile', 'stable', 'trending_up', 'trending_down', 'ranging')",
            name="check_valid_market_condition",
        ),
        CheckConstraint(
            "liquidity_level IN ('deep', 'normal', 'thin')",
            name="check_valid_liquidity_level",
        ),
        CheckConstraint(
            "trading_session IN ('asia', 'europe', 'us')",
            name="check_valid_trading_session",
        ),
        # Indices for common queries
        Index("idx_trade_analysis_trade_id", "trade_id"),
        Index("idx_trade_analysis_symbol", "symbol"),
        Index("idx_trade_analysis_strategy", "strategy"),
        Index("idx_trade_analysis_analyzed_at", "analyzed_at"),
        Index("idx_trade_analysis_quality_score", "quality_score"),
        Index("idx_trade_analysis_symbol_date", "symbol", "analyzed_at"),
        Index("idx_trade_analysis_strategy_date", "strategy", "analyzed_at"),
    )

    def __repr__(self):
        return f"<TradeAnalysis(trade_id={self.trade_id}, symbol={self.symbol}, quality={self.quality_score})>"

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "analysis_id": str(self.analysis_id),
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "size": float(self.size),
            "expected_price": float(self.expected_price),
            "execution_price": float(self.execution_price),
            "slippage": {
                "market_impact": float(self.slippage_market_impact),
                "spread_cost": float(self.slippage_spread_cost),
                "timing_cost": float(self.slippage_timing_cost),
                "total_slippage": float(self.slippage_total),
                "slippage_bps": float(self.slippage_bps),
            },
            "fees": float(self.fees),
            "total_cost": float(self.total_cost),
            "cost_bps": float(self.cost_bps),
            "execution_quality": {
                "implementation_shortfall": float(self.implementation_shortfall),
                "implementation_shortfall_bps": float(
                    self.implementation_shortfall_bps
                ),
                "price_improvement": float(self.price_improvement),
                "price_improvement_bps": float(self.price_improvement_bps),
                "fill_rate": float(self.fill_rate),
                "time_to_completion": float(self.time_to_completion),
                "spread_capture_rate": float(self.spread_capture_rate),
                "benchmark_comparisons": self.benchmark_comparisons or {},
                "quality_score": self.quality_score,
                "quality_grade": self.quality_grade,
            },
            "classification": {
                "execution_style": self.execution_style,
                "market_condition": self.market_condition,
                "liquidity_level": self.liquidity_level,
                "trading_session": self.trading_session,
                "order_urgency": self.order_urgency,
            },
            "strategy": self.strategy,
            "recommendations": self.recommendations or [],
            "decision_timestamp": self.decision_timestamp.isoformat()
            if self.decision_timestamp
            else None,
            "execution_timestamp": self.execution_timestamp.isoformat()
            if self.execution_timestamp
            else None,
            "analyzed_at": self.analyzed_at.isoformat() if self.analyzed_at else None,
            "market_data": self.market_data,
        }
