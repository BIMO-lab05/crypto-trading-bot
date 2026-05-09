"""
Response Models
Purpose: API response data structures
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from app.models.enums import TradingMode
from app.models.signal import TradingSignal
from app.models.position import Position
from app.models.performance import PerformanceMetrics


class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field(description="Health status")
    service: str = Field(description="Service name")
    technical_analysis_connection: bool = Field(description="TA Service connection status")
    bybit_connector_connection: bool = Field(description="Bybit Connector connection status")
    database_connection: bool = Field(description="Database connection status")
    timestamp: int = Field(description="Response timestamp (ms)")


class StatusResponse(BaseModel):
    """Trading engine status response"""
    status: str = Field(description="Service status")
    trading_mode: TradingMode = Field(description="Current trading mode (PAPER/LIVE)")
    auto_trading_enabled: bool = Field(description="Auto trading status")
    active_strategy: Optional[str] = Field(description="Active strategy")
    open_positions_count: int = Field(description="Number of open positions")
    current_balance: float = Field(description="Current account balance")
    timestamp: int = Field(description="Response timestamp (ms)")
    emergency_stop: Optional[Dict] = Field(default=None, description="Emergency stop file kill-switch state")


class SignalResponse(BaseModel):
    """Signal analysis response"""
    success: bool = Field(description="Request success status")
    signal: Optional[TradingSignal] = Field(description="Trading signal")
    message: Optional[str] = Field(default=None, description="Response message")
    timestamp: int = Field(description="Response timestamp (ms)")


class PositionResponse(BaseModel):
    """Position response"""
    success: bool = Field(description="Request success status")
    position: Optional[Position] = Field(description="Position data")
    message: Optional[str] = Field(default=None, description="Response message")
    timestamp: int = Field(description="Response timestamp (ms)")


class PositionListResponse(BaseModel):
    """Position list response"""
    success: bool = Field(description="Request success status")
    positions: List[Position] = Field(description="List of positions")
    count: int = Field(description="Number of positions")
    timestamp: int = Field(description="Response timestamp (ms)")


class PerformanceResponse(BaseModel):
    """Performance metrics response"""
    success: bool = Field(description="Request success status")
    metrics: PerformanceMetrics = Field(description="Performance metrics")
    timestamp: int = Field(description="Response timestamp (ms)")


class StrategyListResponse(BaseModel):
    """Strategy list response"""
    success: bool = Field(description="Request success status")
    strategies: List[Dict] = Field(description="Available strategies")
    active_strategy: Optional[str] = Field(description="Active strategy")
    timestamp: int = Field(description="Response timestamp (ms)")


class TradingControlResponse(BaseModel):
    """Trading control response"""
    success: bool = Field(description="Operation success status")
    message: str = Field(description="Response message")
    trading_enabled: bool = Field(description="Trading enabled status")
    timestamp: int = Field(description="Response timestamp (ms)")


class TradeHistoryStats(BaseModel):
    """Trade history statistics"""
    total_trades: int = Field(description="Total number of closed trades")
    winning_trades: int = Field(description="Number of profitable trades")
    losing_trades: int = Field(description="Number of losing trades")
    win_rate: float = Field(description="Win rate percentage")
    total_realized_pnl: float = Field(description="Total realized P&L")
    avg_win: float = Field(description="Average winning trade P&L")
    avg_loss: float = Field(description="Average losing trade P&L")
    best_trade: float = Field(description="Best trade P&L")
    worst_trade: float = Field(description="Worst trade P&L")
    profit_factor: float = Field(description="Profit factor (gross wins / gross losses)")


class TradeHistoryResponse(BaseModel):
    """Trade history response"""
    success: bool = Field(description="Request success status")
    trades: List[Position] = Field(description="List of closed trades")
    stats: TradeHistoryStats = Field(description="Trade statistics")
    count: int = Field(description="Number of trades")
    timestamp: int = Field(description="Response timestamp (ms)")
