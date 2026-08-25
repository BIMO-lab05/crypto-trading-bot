"""
Backtesting Models - Data structures for historical risk analysis and validation
Defines models for backtest configuration, results, and performance reporting
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime
from decimal import Decimal


class BacktestConfig(BaseModel):
    """Configuration for running a backtest"""

    start_date: datetime = Field(..., description="Start date for backtest period")
    end_date: datetime = Field(..., description="End date for backtest period")
    # risk-metrics-service Settings has no capital field and adding one is out
    # of scope, so the declared account size is written literally here;
    # tests/test_account_size_invariant.py keeps it honest by exempting ONLY
    # the value declared in shared/account.py (10000 per ADR-029, was 100).
    initial_capital: Decimal = Field(
        default=Decimal("10000"), description="Starting capital (declared account size, ADR-029)"
    )
    risk_limits: Optional[Dict[str, float]] = Field(default=None, description="Risk limits to test")
    rebalance_frequency: str = Field(
        default="daily", description="Rebalancing frequency: daily, weekly, monthly"
    )


class PortfolioSnapshot(BaseModel):
    """Snapshot of portfolio state at a point in time"""

    timestamp: datetime = Field(..., description="Time of snapshot")
    total_value: Decimal = Field(..., description="Total portfolio value")
    cash_balance: Decimal = Field(..., description="Available cash")
    positions: List[Dict] = Field(default=[], description="List of positions")
    daily_return: Optional[float] = Field(default=None, description="Daily return percentage")
    cumulative_return: Optional[float] = Field(
        default=None, description="Cumulative return since start"
    )


class BacktestMetrics(BaseModel):
    """Performance metrics calculated from backtest"""

    total_return: float = Field(..., description="Total return over period")
    annualized_return: float = Field(..., description="Annualized return")
    volatility: float = Field(..., description="Standard deviation of returns")
    sharpe_ratio: float = Field(..., description="Sharpe ratio (risk-adjusted return)")
    sortino_ratio: float = Field(..., description="Sortino ratio (downside risk-adjusted)")
    max_drawdown: float = Field(..., description="Maximum drawdown percentage")
    max_drawdown_duration_days: int = Field(..., description="Longest drawdown period")
    calmar_ratio: Optional[float] = Field(default=None, description="Return/Max Drawdown ratio")
    win_rate: float = Field(..., description="Percentage of profitable days")
    best_day: float = Field(..., description="Best single day return")
    worst_day: float = Field(..., description="Worst single day return")
    avg_winning_day: float = Field(..., description="Average return on winning days")
    avg_losing_day: float = Field(..., description="Average return on losing days")
    profit_factor: Optional[float] = Field(
        default=None, description="Ratio of total wins to total losses"
    )
    total_trading_days: int = Field(..., description="Number of trading days in backtest")


class RiskViolation(BaseModel):
    """Record of a risk limit violation during backtest"""

    timestamp: datetime = Field(..., description="When violation occurred")
    violation_type: str = Field(
        ..., description="Type of violation (capital, exposure, drawdown, etc.)"
    )
    limit_value: float = Field(..., description="The risk limit that was exceeded")
    actual_value: float = Field(..., description="The actual value that triggered violation")
    severity: str = Field(..., description="Severity: warning, critical")
    would_halt_trading: bool = Field(default=False, description="Would circuit breaker activate")


class BacktestResult(BaseModel):
    """Complete results from a backtest run"""

    config: BacktestConfig = Field(..., description="Configuration used for backtest")
    metrics: BacktestMetrics = Field(..., description="Performance metrics")
    snapshots: List[PortfolioSnapshot] = Field(..., description="Time series of portfolio states")
    violations: List[RiskViolation] = Field(default=[], description="Risk limit violations")

    # Summary statistics
    start_value: Decimal = Field(..., description="Starting portfolio value")
    end_value: Decimal = Field(..., description="Ending portfolio value")
    peak_value: Decimal = Field(..., description="Highest portfolio value reached")
    valley_value: Decimal = Field(..., description="Lowest portfolio value reached")

    # Risk analysis
    circuit_breaker_activations: int = Field(
        default=0, description="Number of times circuit breaker would activate"
    )
    days_halted: int = Field(default=0, description="Number of days trading would be halted")

    # Comparison metrics
    benchmark_return: Optional[float] = Field(
        default=None, description="Benchmark return for comparison"
    )
    alpha: Optional[float] = Field(default=None, description="Excess return vs benchmark")
    beta: Optional[float] = Field(default=None, description="Portfolio beta vs benchmark")

    # Metadata
    generated_at: datetime = Field(
        default_factory=datetime.now, description="When backtest was run"
    )
    duration_seconds: float = Field(..., description="Time taken to run backtest")


class StrategyComparison(BaseModel):
    """Comparison of multiple risk limit configurations"""

    strategies: List[Dict[str, Any]] = Field(..., description="List of tested configurations")
    results: List[BacktestResult] = Field(..., description="Results for each strategy")

    # Rankings
    best_sharpe: str = Field(..., description="Strategy with best Sharpe ratio")
    best_return: str = Field(..., description="Strategy with highest return")
    lowest_drawdown: str = Field(..., description="Strategy with lowest max drawdown")
    most_stable: str = Field(..., description="Strategy with lowest volatility")

    # Summary
    comparison_date: datetime = Field(default_factory=datetime.now)
    recommendation: str = Field(..., description="Recommended strategy based on analysis")


class WalkForwardResult(BaseModel):
    """Results from walk-forward optimization"""

    in_sample_periods: List[Dict] = Field(..., description="In-sample training periods and results")
    out_of_sample_periods: List[Dict] = Field(
        ..., description="Out-of-sample validation periods and results"
    )

    # Optimization results
    optimal_parameters: Dict[str, float] = Field(..., description="Best performing parameters")
    parameter_stability: float = Field(
        ..., description="Stability score of parameters across periods"
    )

    # Performance metrics
    in_sample_sharpe: float = Field(..., description="Average Sharpe ratio in training")
    out_of_sample_sharpe: float = Field(..., description="Average Sharpe ratio in validation")
    overfitting_score: float = Field(
        ..., description="Measure of overfitting (1.0 = none, >1.5 = significant)"
    )

    # Recommendations
    recommended_for_live: bool = Field(
        ..., description="Whether strategy is recommended for live trading"
    )
    confidence_score: float = Field(..., description="Confidence in recommendation (0-1)")
    notes: str = Field(..., description="Additional notes and observations")


class EquityCurvePoint(BaseModel):
    """Single point on an equity curve"""

    timestamp: datetime = Field(..., description="Time of this equity snapshot")
    equity: Decimal = Field(..., description="Total portfolio equity at this point")
    cash: Decimal = Field(..., description="Cash balance")
    positions_value: Decimal = Field(..., description="Total value of open positions")
    realized_pnl: Decimal = Field(..., description="Cumulative realized P&L")
    unrealized_pnl: Decimal = Field(..., description="Current unrealized P&L")


class VaRAnalysis(BaseModel):
    """Value at Risk analysis results"""

    confidence_level: float = Field(..., description="Confidence level (e.g., 0.95 for 95%)")
    time_horizon_days: int = Field(..., description="Time horizon in days")
    var_amount: Decimal = Field(..., description="VaR amount in base currency")
    var_percentage: float = Field(..., description="VaR as percentage of portfolio")

    # Calculation methods
    method: str = Field(..., description="Calculation method: historical, parametric, monte_carlo")
    sample_size: Optional[int] = Field(None, description="Number of samples used in calculation")

    # Additional metrics
    conditional_var: Optional[Decimal] = Field(
        None, description="Conditional VaR (CVaR/Expected Shortfall)"
    )
    worst_case_loss: Optional[Decimal] = Field(None, description="Worst historical loss in sample")

    # Metadata
    calculated_at: datetime = Field(
        default_factory=datetime.now, description="When VaR was calculated"
    )
    data_period_start: datetime = Field(..., description="Start of historical data period")
    data_period_end: datetime = Field(..., description="End of historical data period")
