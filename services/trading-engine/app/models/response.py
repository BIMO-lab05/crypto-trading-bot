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
