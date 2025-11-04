"""
Performance Models
Purpose: Performance metrics and tracking
"""

from pydantic import BaseModel, Field
from decimal import Decimal
from datetime import datetime
from typing import Optional


class PerformanceMetrics(BaseModel):
    """Performance metrics"""
    total_trades: int = Field(default=0, description="Total number of trades")
    winning_trades: int = Field(default=0, description="Number of winning trades")
    losing_trades: int = Field(default=0, description="Number of losing trades")
    total_pnl: Decimal = Field(default=Decimal("0"), description="Total P&L")
    realized_pnl: Decimal = Field(default=Decimal("0"), description="Realized P&L")
    unrealized_pnl: Decimal = Field(default=Decimal("0"), description="Unrealized P&L")
    win_rate: float = Field(default=0.0, description="Win rate percentage")
    avg_win: Decimal = Field(default=Decimal("0"), description="Average winning trade")
    avg_loss: Decimal = Field(default=Decimal("0"), description="Average losing trade")
    profit_factor: float = Field(default=0.0, description="Profit factor (gross profit / gross loss)")
    max_drawdown: Decimal = Field(default=Decimal("0"), description="Maximum drawdown")
    sharpe_ratio: Optional[float] = Field(default=None, description="Sharpe ratio")
    current_balance: Decimal = Field(default=Decimal("0"), description="Current account balance")
    initial_balance: Decimal = Field(default=Decimal("0"), description="Initial balance")
    roi: float = Field(default=0.0, description="Return on investment percentage")

    def calculate_metrics(self):
        """Calculate derived metrics"""
        # Win rate
        if self.total_trades > 0:
            self.win_rate = (self.winning_trades / self.total_trades) * 100

        # ROI
        if self.initial_balance > 0:
            self.roi = float(((self.current_balance - self.initial_balance) / self.initial_balance) * 100)


class PerformanceSnapshot(PerformanceMetrics):
    """Performance snapshot with timestamp"""
    id: Optional[int] = Field(default=None, description="Snapshot ID")
    snapshot_at: datetime = Field(default_factory=datetime.utcnow, description="Snapshot timestamp")

    class Config:
        from_attributes = True
