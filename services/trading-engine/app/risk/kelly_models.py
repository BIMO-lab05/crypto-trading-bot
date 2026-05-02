"""
Kelly position sizing ORM models.

Schema note: this table is NOT created by any existing init SQL — production
deployments need a migration to add it. Tests rely on `Base.metadata.create_all`
against an in-memory SQLite DB.
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    String,
)
from sqlalchemy.sql import func

from app.database.connection import Base


class KellyTradeHistory(Base):
    """Persisted TradeRecord for Kelly position sizer recovery on restart."""

    __tablename__ = "kelly_trade_history"

    trade_id = Column(String(100), primary_key=True)
    symbol = Column(String(40), nullable=False)
    entry_time = Column(DateTime(timezone=True), nullable=False)
    exit_time = Column(DateTime(timezone=True), nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=False)
    pnl = Column(Float, nullable=False)
    pnl_pct = Column(Float, nullable=False)
    is_win = Column(Boolean, nullable=False)
    strategy = Column(String(50), nullable=False, default="stat_arb")
    kelly_suggested = Column(Float, nullable=True)
    actual_size = Column(Float, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_kelly_trade_history_exit_time", "exit_time"),
        Index("idx_kelly_trade_history_symbol", "symbol"),
    )

    def __repr__(self) -> str:
        return (
            f"<KellyTradeHistory(trade_id={self.trade_id}, symbol={self.symbol}, "
            f"is_win={self.is_win}, pnl_pct={self.pnl_pct:.2f})>"
        )
