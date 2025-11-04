"""
Performance Metrics Models
Tracks and calculates portfolio performance metrics
"""

from pydantic import BaseModel, Field
from decimal import Decimal
from typing import List, Dict, Optional
from datetime import datetime


class PerformanceMetrics(BaseModel):
    """Comprehensive portfolio performance metrics"""

    # Returns
    total_return: Decimal = Field(default=Decimal("0"), description="Total return")
    total_return_pct: Decimal = Field(default=Decimal("0"), description="Total return %")
    daily_return: Decimal = Field(default=Decimal("0"), description="Daily return")
    daily_return_pct: Decimal = Field(default=Decimal("0"), description="Daily return %")

    # Risk Metrics
    volatility: Optional[float] = Field(default=None, description="Portfolio volatility (std dev)")
    sharpe_ratio: Optional[float] = Field(default=None, description="Sharpe ratio")
    sortino_ratio: Optional[float] = Field(default=None, description="Sortino ratio")
    max_drawdown: Optional[float] = Field(default=None, description="Maximum drawdown %")
    max_drawdown_duration: Optional[int] = Field(default=None, description="Max drawdown duration (days)")

    # Trading Statistics
    total_trades: int = Field(default=0, description="Total number of trades")
    winning_trades: int = Field(default=0, description="Number of winning trades")
    losing_trades: int = Field(default=0, description="Number of losing trades")
    win_rate: float = Field(default=0.0, description="Win rate %")
    average_win: Decimal = Field(default=Decimal("0"), description="Average winning trade")
    average_loss: Decimal = Field(default=Decimal("0"), description="Average losing trade")
    profit_factor: Optional[float] = Field(default=None, description="Profit factor (total wins / total losses)")

    # P&L
    total_pnl: Decimal = Field(default=Decimal("0"), description="Total P&L")
    realized_pnl: Decimal = Field(default=Decimal("0"), description="Realized P&L")
    unrealized_pnl: Decimal = Field(default=Decimal("0"), description="Unrealized P&L")

    # Comparison
    benchmark_return: Optional[float] = Field(default=None, description="Benchmark return %")
    alpha: Optional[float] = Field(default=None, description="Alpha vs benchmark")
    beta: Optional[float] = Field(default=None, description="Beta vs benchmark")

    # Timestamp
    calculated_at: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))

    class Config:
        json_encoders = {
            Decimal: str
        }


class DailyPerformance(BaseModel):
    """Daily performance snapshot"""

    date: str = Field(..., description="Date in YYYY-MM-DD format")
    portfolio_value: str  # String for Decimal
    daily_pnl: str
    daily_return_pct: str
    cumulative_return_pct: str
    trades_count: int = 0


class PeriodPerformance(BaseModel):
    """Performance over a specific period"""

    period: str = Field(..., description="Period label (e.g., '7d', '30d')")
    start_date: str
    end_date: str
    start_value: str
    end_value: str
    total_return: str
    total_return_pct: str
    volatility: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    trades_count: int = 0


class AssetPerformance(BaseModel):
    """Performance of individual asset"""

    symbol: str
    quantity: str
    entry_price: str
    current_price: str
    unrealized_pnl: str
    unrealized_pnl_pct: str
    hold_duration_days: int
    allocation_pct: str
