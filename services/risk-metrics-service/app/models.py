"""
Data models for Risk & Metrics Service
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from decimal import Decimal
from datetime import datetime
from enum import Enum


class RiskLevel(str, Enum):
    """Risk level classification"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskAlert(BaseModel):
    """Risk alert model"""
    alert_id: str
    timestamp: datetime
    level: RiskLevel
    category: str
    message: str
    metric_value: float
    threshold: float
    recommendation: str


class CapitalMetrics(BaseModel):
    """Capital allocation and usage metrics"""
    total_capital: Decimal
    available_capital: Decimal
    allocated_capital: Decimal
    reserved_capital: Decimal
    capital_utilization: float = Field(ge=0, le=1)  # 0-1 (0-100%)


class ExposureMetrics(BaseModel):
    """Portfolio exposure metrics"""
    total_exposure: Decimal
    long_exposure: Decimal
    short_exposure: Decimal
    net_exposure: Decimal
    gross_exposure: Decimal
    exposure_ratio: float = Field(ge=0)  # Ratio to total capital
    leverage: float = Field(ge=0)
    concentrated_positions: List[Dict[str, Any]] = []


class DrawdownMetrics(BaseModel):
    """Drawdown tracking metrics"""
    current_drawdown: float = Field(ge=0, le=1)  # Current drawdown percentage
    max_drawdown: float = Field(ge=0, le=1)  # Maximum drawdown since inception
    max_drawdown_date: Optional[datetime] = None
    underwater_period_days: int = 0  # Days since last peak
    recovery_factor: Optional[float] = None  # Ratio of gain to max loss


class PerformanceMetrics(BaseModel):
    """Performance and risk-adjusted return metrics"""
    total_return: float
    annualized_return: float
    volatility: float  # Standard deviation of returns
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    calmar_ratio: Optional[float] = None  # Return / Max Drawdown
    max_drawdown: float
    win_rate: Optional[float] = None
    profit_factor: Optional[float] = None  # Gross profit / Gross loss
    average_win: Optional[float] = None
    average_loss: Optional[float] = None


class ValueAtRisk(BaseModel):
    """Value at Risk calculations"""
    var_95: Decimal  # 95% confidence VaR
    var_99: Decimal  # 99% confidence VaR
    cvar_95: Decimal  # Conditional VaR (Expected Shortfall) 95%
    confidence_level: float
    time_horizon_days: int
    calculation_method: str  # "historical", "parametric", "monte_carlo"


class RiskScorecard(BaseModel):
    """Overall risk assessment scorecard"""
    timestamp: datetime
    overall_risk_level: RiskLevel
    risk_score: float = Field(ge=0, le=100)  # 0-100 composite score

    # Component scores
    capital_risk_score: float
    exposure_risk_score: float
    concentration_risk_score: float
    volatility_risk_score: float
    drawdown_risk_score: float

    # Risk metrics
    capital_metrics: CapitalMetrics
    exposure_metrics: ExposureMetrics
    drawdown_metrics: DrawdownMetrics
    performance_metrics: PerformanceMetrics
    var_metrics: ValueAtRisk

    # Active alerts
    active_alerts: List[RiskAlert] = []

    # Recommendations
    recommendations: List[str] = []


class RiskLimits(BaseModel):
    """Risk limits configuration"""
    max_position_size: float = Field(gt=0, le=1)
    max_portfolio_risk: float = Field(gt=0, le=1)
    max_drawdown: float = Field(gt=0, le=1)
    max_daily_loss: float = Field(gt=0, le=1)
    max_exposure: float = Field(gt=0, le=1)
    max_leverage: float = Field(gt=0)
    min_sharpe_ratio: Optional[float] = None


class CircuitBreakerStatus(BaseModel):
    """Circuit breaker status"""
    is_tripped: bool
    tripped_at: Optional[datetime] = None
    reason: Optional[str] = None
    cooldown_ends_at: Optional[datetime] = None
    can_trade: bool


class HealthCheckResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    version: str
    timestamp: datetime
    dependencies: Dict[str, bool] = {}
