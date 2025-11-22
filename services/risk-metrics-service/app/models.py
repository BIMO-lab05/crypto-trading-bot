"""
Data models for Risk & Metrics Service
"""

from pydantic import BaseModel, Field, field_validator, model_serializer
from typing import List, Dict, Optional, Any
from decimal import Decimal
from datetime import datetime
from enum import Enum


class RiskLevel(str, Enum):
    """Risk level classification - using lowercase values for API consistency"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CircuitBreakerState(str, Enum):
    """Circuit breaker state machine states"""
    CLOSED = "closed"      # Normal operation, trading allowed
    OPEN = "open"          # Circuit tripped, trading halted, cooldown active
    HALF_OPEN = "half_open"  # Testing recovery, limited trading allowed


class RiskAlert(BaseModel):
    """Risk alert model"""
    alert_id: str
    timestamp: datetime
    # Support both 'level' and 'severity' for backward compatibility
    level: Optional[RiskLevel] = None
    severity: Optional[RiskLevel] = None
    category: str
    message: str
    metric_value: float
    threshold: float
    recommendation: str

    def __init__(self, **data):
        # Map severity to level if provided
        if 'severity' in data and 'level' not in data:
            data['level'] = data['severity']
        elif 'level' in data and 'severity' not in data:
            data['severity'] = data['level']
        super().__init__(**data)

    @model_serializer
    def serialize_model(self) -> Dict[str, Any]:
        """Serialize model with lowercase enum values"""
        return {
            'alert_id': self.alert_id,
            'timestamp': self.timestamp,
            'level': self.level.value if self.level else None,
            'severity': self.severity.value if self.severity else None,
            'category': self.category,
            'message': self.message,
            'metric_value': self.metric_value,
            'threshold': self.threshold,
            'recommendation': self.recommendation
        }


class CapitalMetrics(BaseModel):
    """Capital allocation and usage metrics"""
    total_capital: Decimal
    available_capital: Decimal
    allocated_capital: Decimal
    reserved_capital: Decimal = Decimal("0")
    capital_utilization: float = Field(ge=0)  # Allow values > 1 for over-leveraged scenarios
    max_position_size: Decimal  # Maximum position size per trade
    recommended_position_size: Decimal  # Recommended conservative position size

    @field_validator('capital_utilization')
    @classmethod
    def validate_capital_utilization(cls, v: float) -> float:
        """Ensure capital utilization is capped at reasonable levels"""
        # Cap at 10.0 (1000%) for extreme over-leverage cases
        return min(v, 10.0)


class ExposureMetrics(BaseModel):
    """Portfolio exposure metrics"""
    total_exposure: Decimal
    long_exposure: Decimal
    short_exposure: Decimal
    net_exposure: Decimal
    gross_exposure: Decimal
    exposure_ratio: float = Field(ge=0)  # Ratio to total capital
    leverage: float = Field(ge=0)
    concentrated_positions: List[Dict[str, Any]] = []  # List of dicts with position details


class DrawdownMetrics(BaseModel):
    """Drawdown tracking metrics"""
    current_drawdown: float = Field(ge=0, le=1)  # Current drawdown percentage
    max_drawdown: float = Field(ge=0, le=1)  # Maximum drawdown since inception
    max_drawdown_date: Optional[datetime] = None
    underwater_period_days: int = 0  # Days since last peak
    recovery_factor: Optional[float] = None  # Ratio of gain to max loss
    underwater_periods: int = 0  # Number of underwater periods
    avg_drawdown: float = 0.0  # Average drawdown across all periods


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
    largest_win: Optional[float] = None  # Largest single win
    largest_loss: Optional[float] = None  # Largest single loss
    total_trades: Optional[int] = None  # Total number of trades


class ValueAtRisk(BaseModel):
    """Value at Risk calculations"""
    var_95: Decimal  # 95% confidence VaR
    var_99: Decimal  # 99% confidence VaR
    cvar_95: Decimal  # Conditional VaR (Expected Shortfall) 95%
    cvar_99: Decimal  # Conditional VaR (Expected Shortfall) 99%
    confidence_level: float
    time_horizon_days: int
    calculation_method: str  # "historical", "parametric", "monte_carlo"

    @property
    def method(self) -> str:
        """Alias for calculation_method for backward compatibility"""
        return self.calculation_method


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

    @model_serializer
    def serialize_model(self) -> Dict[str, Any]:
        """Serialize model with lowercase enum values"""
        return {
            'timestamp': self.timestamp,
            'overall_risk_level': self.overall_risk_level.value,
            'risk_score': self.risk_score,
            'capital_risk_score': self.capital_risk_score,
            'exposure_risk_score': self.exposure_risk_score,
            'concentration_risk_score': self.concentration_risk_score,
            'volatility_risk_score': self.volatility_risk_score,
            'drawdown_risk_score': self.drawdown_risk_score,
            'capital_metrics': self.capital_metrics,
            'exposure_metrics': self.exposure_metrics,
            'drawdown_metrics': self.drawdown_metrics,
            'performance_metrics': self.performance_metrics,
            'var_metrics': self.var_metrics,
            'active_alerts': self.active_alerts,
            'recommendations': self.recommendations
        }


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
    """
    Circuit breaker status with complete state machine

    States:
    - CLOSED: Normal operation, all trading allowed
    - OPEN: Circuit tripped, trading halted, cooldown period active
    - HALF_OPEN: Testing recovery, limited trading allowed (1 request)

    State Transitions:
    - CLOSED -> OPEN: When risk thresholds exceeded
    - OPEN -> HALF_OPEN: After cooldown period expires
    - HALF_OPEN -> CLOSED: On successful trade in half-open state
    - HALF_OPEN -> OPEN: On failed trade in half-open state (extended cooldown)
    """
    # Current state of the circuit breaker
    state: CircuitBreakerState = CircuitBreakerState.CLOSED

    # Primary status fields
    is_tripped: bool
    tripped_at: Optional[datetime] = None
    reason: Optional[str] = None
    reasons: List[str] = []  # Changed from Optional to always be a list

    # Cooldown management
    cooldown_until: Optional[datetime] = None  # When cooldown period ends
    cooldown_duration: int = 300  # Cooldown duration in seconds (default: 5 minutes)

    # State machine tracking
    failure_count: int = 0  # Consecutive failures (for extending cooldown)
    success_count: int = 0  # Successful trades in HALF_OPEN state

    # Trading permissions
    can_trade: bool
    trading_allowed: bool = Field(default=True)  # Alias field for backward compatibility

    # Backward compatibility
    circuit_breaker_active: Optional[bool] = None
    cooldown_ends_at: Optional[datetime] = None  # Alias for cooldown_until

    def __init__(self, **data):
        # Ensure reasons is always a list
        if 'reasons' not in data or data['reasons'] is None:
            data['reasons'] = []

        # Sync trading_allowed with can_trade
        if 'can_trade' in data and 'trading_allowed' not in data:
            data['trading_allowed'] = data['can_trade']
        elif 'trading_allowed' in data and 'can_trade' not in data:
            data['can_trade'] = data['trading_allowed']

        # Sync circuit_breaker_active with is_tripped
        if 'is_tripped' in data and 'circuit_breaker_active' not in data:
            data['circuit_breaker_active'] = data['is_tripped']
        elif 'circuit_breaker_active' in data and 'is_tripped' not in data:
            data['is_tripped'] = data['circuit_breaker_active']

        # Sync cooldown_ends_at with cooldown_until
        if 'cooldown_until' in data and 'cooldown_ends_at' not in data:
            data['cooldown_ends_at'] = data['cooldown_until']
        elif 'cooldown_ends_at' in data and 'cooldown_until' not in data:
            data['cooldown_until'] = data['cooldown_ends_at']

        # Initialize reasons list if reason is provided
        if 'reason' in data and data['reason'] and not data.get('reasons'):
            data['reasons'] = [data['reason']]

        super().__init__(**data)


class HealthCheckResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    version: str
    timestamp: datetime
    dependencies: Dict[str, bool] = {}
