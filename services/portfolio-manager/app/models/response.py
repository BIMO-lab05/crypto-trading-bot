"""
API Response Models
Standardized responses for all API endpoints
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.models.portfolio import PortfolioSnapshot, RebalanceRecommendation
from app.models.performance import PerformanceMetrics, DailyPerformance, PeriodPerformance, AssetPerformance
from app.models.asset import AssetHolding


class HealthResponse(BaseModel):
    """Health check response"""

    status: str = Field(..., description="Service health status")
    service: str = Field(default="portfolio-manager", description="Service name")
    trading_engine_connection: bool = Field(default=False, description="Trading Engine availability")
    market_data_connection: bool = Field(default=False, description="Market Data availability")
    database_connection: bool = Field(default=False, description="Database connection status")
    timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


class StatusResponse(BaseModel):
    """Portfolio service status"""

    status: str = Field(default="running", description="Service status")
    portfolio_count: int = Field(default=0, description="Number of portfolios")
    total_value: str = Field(default="0", description="Total value across all portfolios")
    active_positions: int = Field(default=0, description="Number of active positions")
    timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


class PortfolioResponse(BaseModel):
    """Portfolio details response"""

    success: bool = True
    portfolio: PortfolioSnapshot
    timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))
    message: Optional[str] = None


class PortfolioListResponse(BaseModel):
    """List of portfolios response"""

    success: bool = True
    portfolios: List[PortfolioSnapshot]
    count: int
    timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


class BalanceResponse(BaseModel):
    """Portfolio balance response"""

    success: bool = True
    portfolio_id: str
    cash_balance: str
    total_value: str
    unrealized_pnl: str
    realized_pnl: str
    total_pnl: str
    total_return_pct: str
    timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


class HoldingsResponse(BaseModel):
    """Portfolio holdings response"""

    success: bool = True
    portfolio_id: str
    holdings: List[AssetHolding]
    total_value: str
    count: int
    timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


class PerformanceResponse(BaseModel):
    """Performance metrics response"""

    success: bool = True
    portfolio_id: str
    metrics: PerformanceMetrics
    daily_performance: Optional[List[DailyPerformance]] = None
    period_performance: Optional[Dict[str, PeriodPerformance]] = None
    timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


class AssetPerformanceResponse(BaseModel):
    """Individual asset performance response"""

    success: bool = True
    portfolio_id: str
    assets: List[AssetPerformance]
    timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


class AllocationResponse(BaseModel):
    """Portfolio allocation response"""

    success: bool = True
    portfolio_id: str
    allocations: Dict[str, str]  # symbol -> allocation %
    needs_rebalancing: bool
    timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


class RebalanceResponse(BaseModel):
    """Rebalancing recommendations response"""

    success: bool = True
    portfolio_id: str
    needs_rebalancing: bool
    recommendations: List[RebalanceRecommendation]
    total_transactions: int
    estimated_total_cost: str
    timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


class TransactionResponse(BaseModel):
    """Transaction execution response"""

    success: bool = True
    transaction_id: str
    symbol: str
    action: str  # "BUY" or "SELL"
    quantity: str
    price: str
    total_cost: str
    realized_pnl: Optional[str] = None
    message: str
    timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


class ErrorResponse(BaseModel):
    """Error response"""

    success: bool = False
    error: str
    details: Optional[str] = None
    timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))
