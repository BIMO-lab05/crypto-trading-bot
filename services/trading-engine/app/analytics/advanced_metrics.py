"""
Advanced Performance Metrics Module - Phase 5.2 Enhancement
Purpose: Comprehensive professional-grade performance analytics with
         institutional-quality metrics for trading strategy evaluation

This module provides advanced performance metrics for trading strategy evaluation:
- Risk-Adjusted Returns: Sharpe, Sortino, Calmar, Omega, Treynor, Information ratios
- Risk Metrics: VaR (Value at Risk), CVaR (Conditional VaR), Beta, Maximum Drawdown
- Drawdown Analysis: Max DD, Average DD, Recovery Factor, Ulcer Index, Pain Index
- Win/Loss Metrics: Win Rate, Profit Factor, Payoff Ratio, Expectancy, Kelly %
- Statistical Analysis: Skewness, Kurtosis, Consecutive streaks
- Trade Efficiency: MAE, MFE, Trade Duration, Capital Utilization, Turnover
- Benchmark Comparison: vs BTC performance

Features:
- Thread-safe singleton pattern for global instance
- Real-time metrics updates after each trade
- Historical metrics storage with configurable retention
- Benchmark comparison for relative performance
- Confidence intervals for statistical measures
- Monte Carlo simulation support

Author: Backend Developer Agent
Date: 2025-12-12
Version: 2.0 - Phase 5.2 Enhancement
"""

import logging
import threading
import math
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import numpy as np
from scipy import stats

# Used in __init__/factory bodies below; the noqa keeps autoflake from
# stripping it after refactors (known repo gotcha).
from app.config import get_settings  # noqa: F401


# Configure logging for advanced metrics module
logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS FOR METRICS CONFIGURATION
# =============================================================================


class MetricsPeriod(str, Enum):
    """Time periods for metrics calculation"""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    ALL_TIME = "all_time"


class RiskLevel(str, Enum):
    """Risk level classification"""

    VERY_LOW = "very_low"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


class DrawdownStatus(str, Enum):
    """Current drawdown status"""

    NO_DRAWDOWN = "no_drawdown"
    IN_DRAWDOWN = "in_drawdown"
    RECOVERING = "recovering"
    NEW_HIGH = "new_high"


# =============================================================================
# DATA MODELS
# =============================================================================


@dataclass
class RiskAdjustedMetrics:
    """
    Risk-adjusted return metrics for comprehensive performance evaluation

    These metrics account for the risk taken to achieve returns, providing
    a more complete picture of strategy performance.

    Attributes:
        sharpe_ratio: (Return - Risk Free) / Volatility
        sortino_ratio: (Return - Risk Free) / Downside Deviation
        calmar_ratio: Annualized Return / Max Drawdown
        omega_ratio: Probability weighted gains / losses at threshold
        treynor_ratio: (Return - Risk Free) / Beta
        information_ratio: Excess Return / Tracking Error
        gain_to_pain_ratio: Sum of returns / Abs sum of negative returns
        sterling_ratio: (Annualized Return - Risk Free) / Average Drawdown
        burke_ratio: (Return - Risk Free) / Square Root of Sum of Squared Drawdowns
    """

    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    omega_ratio: float = 0.0
    treynor_ratio: float = 0.0
    information_ratio: float = 0.0
    gain_to_pain_ratio: float = 0.0
    sterling_ratio: float = 0.0
    burke_ratio: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "sortino_ratio": round(self.sortino_ratio, 4),
            "calmar_ratio": round(self.calmar_ratio, 4),
            "omega_ratio": round(self.omega_ratio, 4),
            "treynor_ratio": round(self.treynor_ratio, 4),
            "information_ratio": round(self.information_ratio, 4),
            "gain_to_pain_ratio": round(self.gain_to_pain_ratio, 4),
            "sterling_ratio": round(self.sterling_ratio, 4),
            "burke_ratio": round(self.burke_ratio, 4),
        }


@dataclass
class DrawdownMetrics:
    """
    Comprehensive drawdown analysis metrics

    Attributes:
        max_drawdown: Maximum peak-to-trough decline (percentage)
        avg_drawdown: Average drawdown depth across all drawdowns
        drawdown_duration: Longest drawdown period in days
        recovery_factor: Net profit / Max drawdown
        ulcer_index: Root mean square of drawdowns (measures severity)
        pain_index: Product of drawdown depth and duration
        time_underwater_pct: Percentage of time spent in drawdown
        current_drawdown: Current drawdown from peak
    """

    max_drawdown: float = 0.0
    avg_drawdown: float = 0.0
    drawdown_duration: int = 0
    recovery_factor: float = 0.0
    ulcer_index: float = 0.0
    pain_index: float = 0.0
    time_underwater_pct: float = 0.0
    current_drawdown: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "max_drawdown": round(self.max_drawdown * 100, 2),  # As percentage
            "avg_drawdown": round(self.avg_drawdown * 100, 2),
            "drawdown_duration": self.drawdown_duration,
            "recovery_factor": round(self.recovery_factor, 2),
            "ulcer_index": round(self.ulcer_index, 4),
            "pain_index": round(self.pain_index, 4),
            "time_underwater_pct": round(self.time_underwater_pct * 100, 2),
            "current_drawdown": round(self.current_drawdown * 100, 2),
        }


@dataclass
class WinLossMetrics:
    """
    Win/Loss analysis metrics for trade performance

    Attributes:
        win_rate: Percentage of winning trades (0-1)
        profit_factor: Gross profit / Gross loss
        payoff_ratio: Average win / Average loss
        expectancy: Expected value per trade
        kelly_percentage: Optimal position size (Kelly Criterion)
        consecutive_wins: Maximum consecutive winning trades
        consecutive_losses: Maximum consecutive losing trades
        current_streak: Current win/loss streak (positive=wins)
        avg_win: Average profit on winning trades
        avg_loss: Average loss on losing trades
        largest_win: Largest single winning trade
        largest_loss: Largest single losing trade
    """

    win_rate: float = 0.0
    profit_factor: float = 0.0
    payoff_ratio: float = 0.0
    expectancy: float = 0.0
    kelly_percentage: float = 0.0
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    current_streak: int = 0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "win_rate": round(self.win_rate * 100, 2),  # As percentage
            "profit_factor": round(self.profit_factor, 4),
            "payoff_ratio": round(self.payoff_ratio, 4),
            "expectancy": round(self.expectancy, 4),
            "kelly_percentage": round(self.kelly_percentage * 100, 2),  # As percentage
            "consecutive_wins": self.consecutive_wins,
            "consecutive_losses": self.consecutive_losses,
            "current_streak": self.current_streak,
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "largest_win": round(self.largest_win, 2),
            "largest_loss": round(self.largest_loss, 2),
        }


@dataclass
class RiskMetrics:
    """
    Comprehensive risk metrics for portfolio/strategy analysis

    These metrics quantify the risk exposure and potential losses.

    Attributes:
        var_95: Value at Risk at 95% confidence level
        var_99: Value at Risk at 99% confidence level
        cvar_95: Conditional VaR (Expected Shortfall) at 95%
        cvar_99: Conditional VaR (Expected Shortfall) at 99%
        beta: Correlation with market benchmark
        max_adverse_excursion: Average maximum loss during trades
        max_favorable_excursion: Average maximum profit during trades
        risk_of_ruin: Probability of total account loss
        volatility: Standard deviation of returns (annualized)
        downside_volatility: Standard deviation of negative returns
        tail_ratio: Ratio of 95th percentile to 5th percentile returns
        risk_level: Classified risk level based on metrics
    """

    var_95: float = 0.0
    var_99: float = 0.0
    cvar_95: float = 0.0
    cvar_99: float = 0.0
    beta: float = 0.0
    max_adverse_excursion: float = 0.0
    max_favorable_excursion: float = 0.0
    risk_of_ruin: float = 0.0
    volatility: float = 0.0
    downside_volatility: float = 0.0
    tail_ratio: float = 0.0
    risk_level: RiskLevel = RiskLevel.MODERATE

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "var_95": round(self.var_95 * 100, 2),  # As percentage
            "var_99": round(self.var_99 * 100, 2),
            "cvar_95": round(self.cvar_95 * 100, 2),
            "cvar_99": round(self.cvar_99 * 100, 2),
            "beta": round(self.beta, 4),
            "max_adverse_excursion": round(self.max_adverse_excursion * 100, 2),
            "max_favorable_excursion": round(self.max_favorable_excursion * 100, 2),
            "risk_of_ruin": round(self.risk_of_ruin * 100, 4),  # As percentage
            "volatility": round(self.volatility * 100, 2),
            "downside_volatility": round(self.downside_volatility * 100, 2),
            "tail_ratio": round(self.tail_ratio, 4),
            "risk_level": self.risk_level.value,
        }


@dataclass
class EfficiencyMetrics:
    """
    Trade efficiency metrics for analyzing trade execution quality

    Attributes:
        avg_trade_duration: Average trade duration in hours
        trades_per_day: Average trades per day
        trades_per_week: Average trades per week
        trades_per_month: Average trades per month
        avg_position_size: Average position size as % of capital
        capital_utilization: Average capital deployed percentage
        turnover_ratio: Annual portfolio turnover
        holding_period_return: Return per unit of holding time
    """

    avg_trade_duration: float = 0.0  # hours
    trades_per_day: float = 0.0
    trades_per_week: float = 0.0
    trades_per_month: float = 0.0
    avg_position_size: float = 0.0  # percentage
    capital_utilization: float = 0.0  # percentage
    turnover_ratio: float = 0.0  # annualized
    holding_period_return: float = 0.0  # return per hour

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "avg_trade_duration_hours": round(self.avg_trade_duration, 2),
            "trades_per_day": round(self.trades_per_day, 2),
            "trades_per_week": round(self.trades_per_week, 2),
            "trades_per_month": round(self.trades_per_month, 2),
            "avg_position_size_pct": round(self.avg_position_size * 100, 2),
            "capital_utilization_pct": round(self.capital_utilization * 100, 2),
            "turnover_ratio": round(self.turnover_ratio, 2),
            "holding_period_return": round(self.holding_period_return * 100, 4),
        }


@dataclass
class BenchmarkComparison:
    """
    Benchmark comparison metrics (vs BTC or ETH)

    Attributes:
        strategy_return: Strategy total return
        benchmark_return: Benchmark total return (BTC)
        excess_return: Strategy return - Benchmark return
        alpha: Risk-adjusted excess return
        beta: Sensitivity to benchmark movements
        correlation: Correlation with benchmark
        tracking_error: Standard deviation of excess returns
        information_ratio: Excess return / Tracking error
        up_capture: Capture ratio in up markets
        down_capture: Capture ratio in down markets
    """

    strategy_return: float = 0.0
    benchmark_return: float = 0.0
    excess_return: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0
    correlation: float = 0.0
    tracking_error: float = 0.0
    information_ratio: float = 0.0
    up_capture: float = 0.0
    down_capture: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "strategy_return_pct": round(self.strategy_return * 100, 2),
            "benchmark_return_pct": round(self.benchmark_return * 100, 2),
            "excess_return_pct": round(self.excess_return * 100, 2),
            "alpha": round(self.alpha, 4),
            "beta": round(self.beta, 4),
            "correlation": round(self.correlation, 4),
            "tracking_error_pct": round(self.tracking_error * 100, 2),
            "information_ratio": round(self.information_ratio, 4),
            "up_capture_pct": round(self.up_capture * 100, 2),
            "down_capture_pct": round(self.down_capture * 100, 2),
        }


@dataclass
class StatisticalMetrics:
    """
    Statistical analysis metrics for return distribution

    These metrics describe the shape and characteristics of return distribution.

    Attributes:
        mean_return: Average return per period
        median_return: Median return per period
        std_deviation: Standard deviation of returns
        skewness: Asymmetry of return distribution (positive = right tail)
        kurtosis: Tail heaviness (>3 = fat tails, <3 = thin tails)
        total_return: Total cumulative return
        annualized_return: Annualized return
        total_trades: Total number of trades
    """

    mean_return: float = 0.0
    median_return: float = 0.0
    std_deviation: float = 0.0
    skewness: float = 0.0
    kurtosis: float = 0.0
    total_return: float = 0.0
    annualized_return: float = 0.0
    total_trades: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "mean_return_pct": round(self.mean_return * 100, 4),
            "median_return_pct": round(self.median_return * 100, 4),
            "std_deviation_pct": round(self.std_deviation * 100, 4),
            "skewness": round(self.skewness, 4),
            "kurtosis": round(self.kurtosis, 4),
            "total_return_pct": round(self.total_return * 100, 2),
            "annualized_return_pct": round(self.annualized_return * 100, 2),
            "total_trades": self.total_trades,
        }


@dataclass
class DrawdownInfo:
    """
    Detailed drawdown information for a specific drawdown period

    Attributes:
        start_date: When drawdown started
        end_date: When drawdown ended (None if ongoing)
        trough_date: Date of maximum drawdown point
        depth: Maximum drawdown depth (percentage)
        duration_days: Total days in drawdown
        recovery_days: Days from trough to recovery (None if not recovered)
        peak_equity: Equity at start of drawdown
        trough_equity: Lowest equity during drawdown
        recovery_equity: Equity when recovered
        status: Current status of this drawdown
    """

    start_date: datetime
    end_date: Optional[datetime] = None
    trough_date: Optional[datetime] = None
    depth: float = 0.0
    duration_days: int = 0
    recovery_days: Optional[int] = None
    peak_equity: float = 0.0
    trough_equity: float = 0.0
    recovery_equity: Optional[float] = None
    status: DrawdownStatus = DrawdownStatus.IN_DRAWDOWN

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "trough_date": self.trough_date.isoformat() if self.trough_date else None,
            "depth": round(self.depth * 100, 2),  # As percentage
            "duration_days": self.duration_days,
            "recovery_days": self.recovery_days,
            "peak_equity": round(self.peak_equity, 2),
            "trough_equity": round(self.trough_equity, 2),
            "recovery_equity": round(self.recovery_equity, 2)
            if self.recovery_equity
            else None,
            "status": self.status.value,
        }


@dataclass
class DrawdownAnalysis:
    """
    Comprehensive drawdown analysis with history

    Attributes:
        current_drawdown: Current drawdown percentage (0 if at high)
        current_drawdown_duration: Days in current drawdown (0 if at high)
        max_drawdown: Maximum drawdown ever recorded
        max_drawdown_duration: Longest drawdown period ever
        avg_drawdown: Average drawdown depth
        avg_recovery_time: Average time to recover from drawdowns
        drawdown_count: Total number of drawdown periods
        current_status: Current drawdown status
        drawdown_history: List of historical drawdown periods
        time_in_drawdown_pct: Percentage of time spent in drawdown
        underwater_curve: Equity underwater curve data points
    """

    current_drawdown: float = 0.0
    current_drawdown_duration: int = 0
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0
    avg_drawdown: float = 0.0
    avg_recovery_time: float = 0.0
    drawdown_count: int = 0
    current_status: DrawdownStatus = DrawdownStatus.NO_DRAWDOWN
    drawdown_history: List[DrawdownInfo] = field(default_factory=list)
    time_in_drawdown_pct: float = 0.0
    underwater_curve: List[Tuple[datetime, float]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "current_drawdown": round(self.current_drawdown * 100, 2),
            "current_drawdown_duration": self.current_drawdown_duration,
            "max_drawdown": round(self.max_drawdown * 100, 2),
            "max_drawdown_duration": self.max_drawdown_duration,
            "avg_drawdown": round(self.avg_drawdown * 100, 2),
            "avg_recovery_time": round(self.avg_recovery_time, 1),
            "drawdown_count": self.drawdown_count,
            "current_status": self.current_status.value,
            "drawdown_history": [
                d.to_dict() for d in self.drawdown_history[-10:]
            ],  # Last 10
            "time_in_drawdown_pct": round(self.time_in_drawdown_pct * 100, 2),
        }


@dataclass
class AttributionByDimension:
    """
    Performance attribution for a specific dimension

    Attributes:
        dimension_name: Name of the dimension (strategy, symbol, etc.)
        dimension_value: Value of the dimension
        total_pnl: Total P&L for this dimension
        contribution_pct: Percentage contribution to overall P&L
        trades_count: Number of trades
        win_rate: Win rate percentage
        avg_return: Average return per trade
        sharpe_ratio: Risk-adjusted return
        max_drawdown: Maximum drawdown
    """

    dimension_name: str
    dimension_value: str
    total_pnl: float = 0.0
    contribution_pct: float = 0.0
    trades_count: int = 0
    win_rate: float = 0.0
    avg_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "dimension_name": self.dimension_name,
            "dimension_value": self.dimension_value,
            "total_pnl": round(self.total_pnl, 2),
            "contribution_pct": round(self.contribution_pct, 2),
            "trades_count": self.trades_count,
            "win_rate": round(self.win_rate * 100, 2),
            "avg_return": round(self.avg_return * 100, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "max_drawdown": round(self.max_drawdown * 100, 2),
        }


@dataclass
class RollingMetrics:
    """
    Rolling window metrics over time

    Attributes:
        window_size: Number of periods in rolling window
        period_type: Type of period (daily, weekly, etc.)
        timestamps: List of timestamps for data points
        rolling_sharpe: Rolling Sharpe ratio values
        rolling_sortino: Rolling Sortino ratio values
        rolling_volatility: Rolling volatility values
        rolling_win_rate: Rolling win rate values
        rolling_pnl: Rolling cumulative P&L
        rolling_max_drawdown: Rolling maximum drawdown
    """

    window_size: int = 30
    period_type: MetricsPeriod = MetricsPeriod.DAILY
    timestamps: List[datetime] = field(default_factory=list)
    rolling_sharpe: List[float] = field(default_factory=list)
    rolling_sortino: List[float] = field(default_factory=list)
    rolling_volatility: List[float] = field(default_factory=list)
    rolling_win_rate: List[float] = field(default_factory=list)
    rolling_pnl: List[float] = field(default_factory=list)
    rolling_max_drawdown: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "window_size": self.window_size,
            "period_type": self.period_type.value,
            "data_points": len(self.timestamps),
            "timestamps": [ts.isoformat() for ts in self.timestamps[-50:]],  # Last 50
            "rolling_sharpe": [round(v, 4) for v in self.rolling_sharpe[-50:]],
            "rolling_sortino": [round(v, 4) for v in self.rolling_sortino[-50:]],
            "rolling_volatility": [
                round(v * 100, 2) for v in self.rolling_volatility[-50:]
            ],
            "rolling_win_rate": [
                round(v * 100, 2) for v in self.rolling_win_rate[-50:]
            ],
            "rolling_pnl": [round(v, 2) for v in self.rolling_pnl[-50:]],
            "rolling_max_drawdown": [
                round(v * 100, 2) for v in self.rolling_max_drawdown[-50:]
            ],
        }


@dataclass
class TradeMetadata:
    """
    Trade metadata for metrics calculation

    Attributes:
        trade_id: Unique trade identifier
        timestamp: Trade exit timestamp
        pnl: Profit/loss in USD
        pnl_pct: Profit/loss as percentage
        strategy: Strategy name
        symbol: Trading symbol
        direction: Long or short
        duration_seconds: Trade duration
        is_winner: Whether trade was profitable
        entry_price: Entry price
        exit_price: Exit price
        position_size: Position size in base currency
        max_adverse_excursion: Maximum loss during trade (percentage)
        max_favorable_excursion: Maximum profit during trade (percentage)
    """

    trade_id: str
    timestamp: datetime
    pnl: float
    pnl_pct: float
    strategy: str
    symbol: str
    direction: str
    duration_seconds: int = 0
    is_winner: bool = False
    entry_price: float = 0.0
    exit_price: float = 0.0
    position_size: float = 0.0
    max_adverse_excursion: float = 0.0
    max_favorable_excursion: float = 0.0


@dataclass
class AllMetrics:
    """
    Complete metrics summary combining all metric types for API response

    Attributes:
        risk_adjusted: Risk-adjusted return metrics
        drawdown: Drawdown analysis metrics
        win_loss: Win/loss analysis metrics
        risk: Risk quantification metrics
        efficiency: Trade efficiency metrics
        total_trades: Total number of trades analyzed
        total_pnl: Total profit/loss
        generated_at: When metrics were generated
    """

    risk_adjusted: RiskAdjustedMetrics = field(default_factory=RiskAdjustedMetrics)
    drawdown: DrawdownMetrics = field(default_factory=DrawdownMetrics)
    win_loss: WinLossMetrics = field(default_factory=WinLossMetrics)
    risk: RiskMetrics = field(default_factory=RiskMetrics)
    efficiency: EfficiencyMetrics = field(default_factory=EfficiencyMetrics)
    total_trades: int = 0
    total_pnl: float = 0.0
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "risk_adjusted": self.risk_adjusted.to_dict(),
            "drawdown": self.drawdown.to_dict(),
            "win_loss": self.win_loss.to_dict(),
            "risk": self.risk.to_dict(),
            "efficiency": self.efficiency.to_dict(),
            "total_trades": self.total_trades,
            "total_pnl": round(self.total_pnl, 2),
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass
class ComprehensiveMetrics:
    """
    Complete metrics summary combining all metric types

    Attributes:
        risk_adjusted: Risk-adjusted return metrics
        risk_metrics: Risk quantification metrics
        statistical: Statistical analysis metrics
        drawdown_analysis: Drawdown tracking and history
        attribution_by_strategy: P&L attribution by strategy
        attribution_by_symbol: P&L attribution by symbol
        attribution_by_period: P&L attribution by time period
        rolling_metrics: Time-windowed metrics
        total_trades: Total number of trades analyzed
        total_pnl: Total profit/loss
        generated_at: When metrics were generated
    """

    risk_adjusted: RiskAdjustedMetrics = field(default_factory=RiskAdjustedMetrics)
    risk_metrics: RiskMetrics = field(default_factory=RiskMetrics)
    statistical: StatisticalMetrics = field(default_factory=StatisticalMetrics)
    drawdown_analysis: DrawdownAnalysis = field(default_factory=DrawdownAnalysis)
    attribution_by_strategy: List[AttributionByDimension] = field(default_factory=list)
    attribution_by_symbol: List[AttributionByDimension] = field(default_factory=list)
    attribution_by_period: List[AttributionByDimension] = field(default_factory=list)
    rolling_metrics: Optional[RollingMetrics] = None
    total_trades: int = 0
    total_pnl: float = 0.0
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "risk_adjusted": self.risk_adjusted.to_dict(),
            "risk_metrics": self.risk_metrics.to_dict(),
            "statistical": self.statistical.to_dict(),
            "drawdown_analysis": self.drawdown_analysis.to_dict(),
            "attribution_by_strategy": [
                a.to_dict() for a in self.attribution_by_strategy
            ],
            "attribution_by_symbol": [a.to_dict() for a in self.attribution_by_symbol],
            "attribution_by_period": [a.to_dict() for a in self.attribution_by_period],
            "rolling_metrics": self.rolling_metrics.to_dict()
            if self.rolling_metrics
            else None,
            "total_trades": self.total_trades,
            "total_pnl": round(self.total_pnl, 2),
            "generated_at": self.generated_at.isoformat(),
        }


# =============================================================================
# MAIN ADVANCED METRICS CALCULATOR CLASS
# =============================================================================


class AdvancedMetricsCalculator:
    """
    Comprehensive Advanced Performance Metrics Calculator

    This class provides advanced analytics for trading performance including:
    - Risk-adjusted return metrics (Sharpe, Sortino, Calmar, Omega, Treynor)
    - Risk metrics (VaR, CVaR, Beta, Maximum Drawdown, MAE, MFE)
    - Drawdown analysis (Ulcer Index, Pain Index, Recovery Factor)
    - Win/Loss metrics (Kelly %, consecutive streaks, profit factor)
    - Trade efficiency (duration, frequency, capital utilization)
    - Benchmark comparison (vs BTC performance)

    Thread-safe singleton pattern ensures consistent global state.

    Usage:
        calculator = get_advanced_metrics_calculator()  # capital from Settings
        calculator.add_trade(trade_metadata)
        metrics = calculator.get_all_metrics()

    Example:
        >>> calc = AdvancedMetricsCalculator()  # capital from Settings.paper_initial_balance
        >>> calc.add_trade(TradeMetadata(
        ...     trade_id="tr_001",
        ...     timestamp=datetime.now(timezone.utc),
        ...     pnl=150.0,
        ...     pnl_pct=0.015,
        ...     strategy="momentum",
        ...     symbol="BTCUSDT",
        ...     direction="long",
        ...     is_winner=True
        ... ))
        >>> metrics = calc.get_risk_adjusted_metrics()
    """

    # Thread lock for singleton pattern
    _lock: threading.Lock = threading.Lock()

    def __init__(
        self,
        initial_capital: Optional[float] = None,
        risk_free_rate: float = 0.02,
        benchmark_returns: Optional[List[float]] = None,
        rolling_window: int = 30,
        annualization_factor: int = 252,
    ):
        """
        Initialize the Advanced Metrics Calculator

        Args:
            initial_capital: Starting capital for calculations. None (default)
                resolves to Settings.paper_initial_balance — never a hardcoded
                account size.
            risk_free_rate: Annual risk-free rate for risk-adjusted metrics (default: 2%)
            benchmark_returns: Market benchmark returns for Beta calculation
            rolling_window: Window size for rolling metrics (default: 30 periods)
            annualization_factor: Factor to annualize returns (default: 252 trading days)
        """
        # Configuration parameters
        if initial_capital is None:
            initial_capital = get_settings().paper_initial_balance
        self.initial_capital = initial_capital
        self.risk_free_rate = risk_free_rate
        self.rolling_window = rolling_window
        self.annualization_factor = annualization_factor

        # Data storage with thread lock
        self._lock = threading.Lock()
        self._trades: List[TradeMetadata] = []
        self._returns: List[float] = []
        self._equity_curve: List[Tuple[datetime, float]] = []

        # Benchmark data
        self._benchmark_returns = benchmark_returns or []

        # Equity tracking
        self._current_equity = initial_capital
        self._peak_equity = initial_capital

        # Drawdown tracking
        self._current_drawdown_start: Optional[datetime] = None
        self._current_drawdown_trough: Optional[float] = None
        self._current_drawdown_trough_date: Optional[datetime] = None
        self._drawdown_history: List[DrawdownInfo] = []

        # Cache for computed metrics (invalidated on new trades)
        self._metrics_cache: Optional[ComprehensiveMetrics] = None
        self._cache_valid = False

        logger.info(
            f"AdvancedMetricsCalculator initialized: "
            f"capital=${initial_capital:,.2f}, "
            f"risk_free={risk_free_rate:.2%}, "
            f"rolling_window={rolling_window}"
        )

    # =========================================================================
    # TRADE MANAGEMENT
    # =========================================================================

    def add_trade(self, trade: TradeMetadata) -> None:
        """
        Add a completed trade for metrics calculation

        This method is thread-safe and updates all tracking data.

        Args:
            trade: Complete trade metadata including P&L and attribution info
        """
        with self._lock:
            # Store trade and return
            self._trades.append(trade)
            self._returns.append(trade.pnl_pct)

            # Update equity
            self._current_equity += trade.pnl
            self._equity_curve.append((trade.timestamp, self._current_equity))

            # Update drawdown tracking
            self._update_drawdown_tracking(trade.timestamp)

            # Invalidate cache
            self._cache_valid = False

            logger.debug(
                f"Trade added: {trade.trade_id} "
                f"P&L=${trade.pnl:+.2f} ({trade.pnl_pct:+.2%}) "
                f"Strategy={trade.strategy} Symbol={trade.symbol}"
            )

    def add_trades_batch(self, trades: List[TradeMetadata]) -> None:
        """
        Add multiple trades at once (efficient for historical data loading)

        Args:
            trades: List of trade metadata objects
        """
        with self._lock:
            for trade in trades:
                self._trades.append(trade)
                self._returns.append(trade.pnl_pct)
                self._current_equity += trade.pnl
                self._equity_curve.append((trade.timestamp, self._current_equity))

            # Update drawdown tracking for last trade
            if trades:
                self._update_drawdown_tracking(trades[-1].timestamp)

            self._cache_valid = False

            logger.info(f"Added {len(trades)} trades to metrics calculator")

    def _update_drawdown_tracking(self, current_time: datetime) -> None:
        """
        Update drawdown tracking based on current equity

        Args:
            current_time: Current timestamp for drawdown recording
        """
        # Check if we hit new high
        if self._current_equity >= self._peak_equity:
            # Close any existing drawdown
            if self._current_drawdown_start is not None:
                self._close_current_drawdown(current_time)

            # Update peak
            self._peak_equity = self._current_equity
        else:
            # We are in drawdown
            if self._current_drawdown_start is None:
                # Start new drawdown period
                self._current_drawdown_start = current_time
                self._current_drawdown_trough = self._current_equity
                self._current_drawdown_trough_date = current_time
            elif self._current_equity < (
                self._current_drawdown_trough or self._peak_equity
            ):
                # New trough in current drawdown
                self._current_drawdown_trough = self._current_equity
                self._current_drawdown_trough_date = current_time

    def _close_current_drawdown(self, recovery_time: datetime) -> None:
        """
        Close the current drawdown period and add to history

        Args:
            recovery_time: Time when equity recovered to previous peak
        """
        if self._current_drawdown_start is None:
            return

        # Calculate drawdown depth
        trough = self._current_drawdown_trough or self._peak_equity
        depth = (trough - self._peak_equity) / self._peak_equity

        # Calculate duration
        duration = (recovery_time - self._current_drawdown_start).days

        # Calculate recovery time
        trough_date = self._current_drawdown_trough_date or self._current_drawdown_start
        recovery_days = (recovery_time - trough_date).days

        # Create drawdown record
        drawdown_info = DrawdownInfo(
            start_date=self._current_drawdown_start,
            end_date=recovery_time,
            trough_date=trough_date,
            depth=depth,
            duration_days=duration,
            recovery_days=recovery_days,
            peak_equity=self._peak_equity,
            trough_equity=trough,
            recovery_equity=self._current_equity,
            status=DrawdownStatus.RECOVERING,
        )

        self._drawdown_history.append(drawdown_info)

        # Reset tracking
        self._current_drawdown_start = None
        self._current_drawdown_trough = None
        self._current_drawdown_trough_date = None

    def set_benchmark_returns(self, returns: List[float]) -> None:
        """
        Set benchmark returns for relative performance metrics

        Args:
            returns: List of benchmark returns (should align with trade returns)
        """
        with self._lock:
            self._benchmark_returns = returns
            self._cache_valid = False
            logger.info(f"Set {len(returns)} benchmark returns")

    # =========================================================================
    # RISK-ADJUSTED METRICS CALCULATION
    # =========================================================================

    def get_risk_adjusted_metrics(self) -> RiskAdjustedMetrics:
        """
        Calculate all risk-adjusted return metrics

        Returns:
            RiskAdjustedMetrics with Sharpe, Sortino, Calmar, Omega, Treynor ratios
        """
        with self._lock:
            if len(self._returns) < 2:
                return RiskAdjustedMetrics()

            returns = np.array(self._returns)

            # Calculate individual metrics
            sharpe = self._calculate_sharpe_ratio(returns)
            sortino = self._calculate_sortino_ratio(returns)
            calmar = self._calculate_calmar_ratio(returns)
            omega = self._calculate_omega_ratio(returns)
            treynor = self._calculate_treynor_ratio(returns)
            info_ratio = self._calculate_information_ratio(returns)
            gtp = self._calculate_gain_to_pain_ratio(returns)
            sterling = self._calculate_sterling_ratio(returns)
            burke = self._calculate_burke_ratio(returns)

            return RiskAdjustedMetrics(
                sharpe_ratio=sharpe,
                sortino_ratio=sortino,
                calmar_ratio=calmar,
                omega_ratio=omega,
                treynor_ratio=treynor,
                information_ratio=info_ratio,
                gain_to_pain_ratio=gtp,
                sterling_ratio=sterling,
                burke_ratio=burke,
            )

    def _calculate_sharpe_ratio(self, returns: np.ndarray) -> float:
        """
        Calculate Sharpe ratio: (Mean Return - Risk Free) / Volatility

        Args:
            returns: Array of period returns

        Returns:
            Annualized Sharpe ratio
        """
        if len(returns) < 2:
            return 0.0

        mean_return = np.mean(returns)
        std_return = np.std(returns, ddof=1)

        if std_return == 0:
            return 0.0

        # Daily risk-free rate
        daily_rf = self.risk_free_rate / self.annualization_factor

        # Calculate Sharpe
        sharpe = (mean_return - daily_rf) / std_return

        # Annualize
        annualized = sharpe * np.sqrt(min(len(returns), self.annualization_factor))

        return float(annualized)

    def _calculate_sortino_ratio(self, returns: np.ndarray) -> float:
        """
        Calculate Sortino ratio using downside deviation

        The Sortino ratio only penalizes downside volatility, making it
        more appropriate for strategies with asymmetric return distributions.

        Args:
            returns: Array of period returns

        Returns:
            Annualized Sortino ratio
        """
        if len(returns) < 2:
            return 0.0

        mean_return = np.mean(returns)

        # Calculate downside deviation (only negative returns)
        downside_returns = returns[returns < 0]

        if len(downside_returns) == 0:
            return float("inf") if mean_return > 0 else 0.0

        downside_std = np.std(downside_returns, ddof=1)

        if downside_std == 0:
            return 0.0

        # Daily risk-free rate
        daily_rf = self.risk_free_rate / self.annualization_factor

        # Calculate Sortino
        sortino = (mean_return - daily_rf) / downside_std

        # Annualize
        annualized = sortino * np.sqrt(min(len(returns), self.annualization_factor))

        return float(annualized)

    def _calculate_calmar_ratio(self, returns: np.ndarray) -> float:
        """
        Calculate Calmar ratio: Annualized Return / Max Drawdown

        The Calmar ratio measures return relative to maximum drawdown risk.

        Args:
            returns: Array of period returns

        Returns:
            Calmar ratio
        """
        if len(returns) < 2:
            return 0.0

        # Calculate cumulative return
        cumulative_return = np.sum(returns)

        # Annualize return
        periods = len(returns)
        annualized_return = cumulative_return * (self.annualization_factor / periods)

        # Calculate max drawdown from returns
        max_dd = self._calculate_max_drawdown_from_returns(returns)

        if max_dd == 0:
            return float("inf") if annualized_return > 0 else 0.0

        calmar = annualized_return / abs(max_dd)

        return float(calmar)

    def _calculate_omega_ratio(
        self,
        returns: np.ndarray,
        threshold: float = 0.0,
    ) -> float:
        """
        Calculate Omega ratio: Probability-weighted gains / losses

        Omega ratio considers the entire distribution of returns,
        not just mean and variance.

        Args:
            returns: Array of period returns
            threshold: Return threshold (default: 0)

        Returns:
            Omega ratio
        """
        if len(returns) < 2:
            return 0.0

        # Calculate gains and losses relative to threshold
        gains = returns[returns > threshold] - threshold
        losses = threshold - returns[returns <= threshold]

        sum_gains = np.sum(gains)
        sum_losses = np.sum(losses)

        if sum_losses == 0:
            return float("inf") if sum_gains > 0 else 1.0

        omega = sum_gains / sum_losses

        return float(omega)

    def _calculate_treynor_ratio(self, returns: np.ndarray) -> float:
        """
        Calculate Treynor ratio: (Return - Risk Free) / Beta

        Measures excess return per unit of systematic risk.

        Args:
            returns: Array of period returns

        Returns:
            Treynor ratio
        """
        if len(returns) < 2:
            return 0.0

        # Calculate beta
        beta = self._calculate_beta(returns)

        if beta == 0:
            return 0.0

        mean_return = np.mean(returns)
        daily_rf = self.risk_free_rate / self.annualization_factor

        treynor = (mean_return - daily_rf) / beta

        # Annualize
        annualized = treynor * self.annualization_factor

        return float(annualized)

    def _calculate_information_ratio(self, returns: np.ndarray) -> float:
        """
        Calculate Information ratio: Excess Return / Tracking Error

        Measures risk-adjusted excess return relative to benchmark.

        Args:
            returns: Array of period returns

        Returns:
            Information ratio
        """
        if len(returns) < 2 or len(self._benchmark_returns) < 2:
            return 0.0

        # Align lengths
        benchmark = np.array(self._benchmark_returns[: len(returns)])
        strategy_returns = returns[: len(benchmark)]

        if len(benchmark) < 2:
            return 0.0

        # Calculate excess returns
        excess_returns = strategy_returns - benchmark

        mean_excess = np.mean(excess_returns)
        tracking_error = np.std(excess_returns, ddof=1)

        if tracking_error == 0:
            return 0.0

        info_ratio = mean_excess / tracking_error

        # Annualize
        annualized = info_ratio * np.sqrt(min(len(returns), self.annualization_factor))

        return float(annualized)

    def _calculate_gain_to_pain_ratio(self, returns: np.ndarray) -> float:
        """
        Calculate Gain to Pain ratio: Sum of returns / Abs sum of negative returns

        Args:
            returns: Array of period returns

        Returns:
            Gain to pain ratio
        """
        if len(returns) == 0:
            return 0.0

        total_return = np.sum(returns)
        negative_returns = returns[returns < 0]
        total_pain = abs(np.sum(negative_returns))

        if total_pain == 0:
            return float("inf") if total_return > 0 else 0.0

        return float(total_return / total_pain)

    def _calculate_sterling_ratio(self, returns: np.ndarray) -> float:
        """
        Calculate Sterling ratio: (Annualized Return - Risk Free) / Average Drawdown

        The Sterling ratio is similar to the Calmar ratio but uses average drawdown
        instead of maximum drawdown, providing a more representative measure of
        typical drawdown risk.

        Args:
            returns: Array of period returns

        Returns:
            Sterling ratio (higher is better)
        """
        if len(returns) < 2:
            return 0.0

        # Calculate annualized return
        total_return = np.sum(returns)
        annualized_return = total_return * self.annualization_factor / len(returns)

        # Calculate average drawdown
        avg_dd = abs(self._calculate_average_drawdown(returns))

        if avg_dd == 0:
            return float("inf") if annualized_return > 0 else 0.0

        # Sterling ratio: (Annualized Return - Risk Free Rate) / Average Drawdown
        risk_free_annual = self.risk_free_rate * self.annualization_factor
        sterling = (annualized_return - risk_free_annual) / avg_dd

        return float(sterling)

    def _calculate_burke_ratio(self, returns: np.ndarray) -> float:
        """
        Calculate Burke ratio: (Return - Risk Free) / sqrt(Sum of Squared Drawdowns)

        The Burke ratio uses the square root of the sum of squared drawdowns,
        similar to how the Sharpe ratio uses standard deviation. This penalizes
        large drawdowns more heavily than average drawdown metrics.

        Args:
            returns: Array of period returns

        Returns:
            Burke ratio (higher is better)
        """
        if len(returns) < 2:
            return 0.0

        # Calculate cumulative returns
        cumulative = np.cumprod(1 + returns) - 1

        # Calculate running maximum
        running_max = np.maximum.accumulate(cumulative)

        # Calculate drawdowns (as positive values)
        drawdowns = running_max - cumulative

        # Sum of squared drawdowns
        sum_squared_dd = np.sum(drawdowns**2)

        if sum_squared_dd == 0:
            total_return = np.sum(returns)
            return float("inf") if total_return > 0 else 0.0

        # Burke ratio: (Total Return - Risk Free) / sqrt(Sum of Squared Drawdowns)
        total_return = np.sum(returns)
        risk_free_total = self.risk_free_rate * len(returns) / self.annualization_factor
        burke = (total_return - risk_free_total) / np.sqrt(sum_squared_dd)

        return float(burke)

    # =========================================================================
    # DRAWDOWN METRICS CALCULATION
    # =========================================================================

    def get_drawdown_metrics(self) -> DrawdownMetrics:
        """
        Calculate comprehensive drawdown analysis metrics

        Returns:
            DrawdownMetrics with max DD, ulcer index, pain index, recovery factor
        """
        with self._lock:
            if len(self._returns) < 2:
                return DrawdownMetrics()

            returns = np.array(self._returns)

            # Calculate max drawdown
            max_dd = self._calculate_max_drawdown_from_returns(returns)
            max_dd_duration = self._calculate_max_drawdown_duration()

            # Calculate average drawdown
            avg_dd = self._calculate_average_drawdown(returns)

            # Calculate recovery factor: Net Profit / Max Drawdown
            total_pnl = sum(t.pnl for t in self._trades)
            recovery_factor = 0.0
            if abs(max_dd) > 0:
                recovery_factor = total_pnl / (abs(max_dd) * self.initial_capital)

            # Calculate Ulcer Index
            ulcer_index = self._calculate_ulcer_index(returns)

            # Calculate Pain Index
            pain_index = self._calculate_pain_index()

            # Time underwater percentage
            time_underwater = self._calculate_time_underwater()

            # Current drawdown
            current_dd = 0.0
            if self._current_equity < self._peak_equity:
                current_dd = (
                    self._current_equity - self._peak_equity
                ) / self._peak_equity

            return DrawdownMetrics(
                max_drawdown=max_dd,
                avg_drawdown=avg_dd,
                drawdown_duration=max_dd_duration,
                recovery_factor=recovery_factor,
                ulcer_index=ulcer_index,
                pain_index=pain_index,
                time_underwater_pct=time_underwater,
                current_drawdown=current_dd,
            )

    def _calculate_ulcer_index(self, returns: np.ndarray) -> float:
        """
        Calculate Ulcer Index: Root mean square of drawdowns

        The Ulcer Index measures the depth and duration of drawdowns,
        giving more weight to longer, deeper drawdowns.

        Args:
            returns: Array of period returns

        Returns:
            Ulcer Index value
        """
        if len(returns) < 2:
            return 0.0

        # Build cumulative return curve
        cumulative = np.cumprod(1 + returns)

        # Calculate running maximum
        running_max = np.maximum.accumulate(cumulative)

        # Calculate percentage drawdowns
        drawdowns = (cumulative - running_max) / running_max * 100

        # Calculate Ulcer Index (RMS of drawdowns)
        ulcer_index = np.sqrt(np.mean(drawdowns**2))

        return float(ulcer_index)

    def _calculate_pain_index(self) -> float:
        """
        Calculate Pain Index: Average product of drawdown depth and duration

        Pain Index combines both the severity and duration of drawdowns.

        Returns:
            Pain Index value
        """
        if not self._drawdown_history:
            return 0.0

        # Calculate pain for each drawdown (depth * duration)
        total_pain = 0.0
        total_days = 0

        for dd in self._drawdown_history:
            pain = abs(dd.depth) * dd.duration_days
            total_pain += pain
            total_days += dd.duration_days

        # Include current drawdown if any
        if self._current_drawdown_start and self._peak_equity > 0:
            current_dd = abs(
                (self._current_equity - self._peak_equity) / self._peak_equity
            )
            current_duration = (
                datetime.now(timezone.utc) - self._current_drawdown_start
            ).days
            total_pain += current_dd * current_duration
            total_days += current_duration

        # Average pain per day
        if total_days > 0:
            return total_pain / total_days

        return 0.0

    def _calculate_average_drawdown(self, returns: np.ndarray) -> float:
        """
        Calculate average drawdown depth

        Args:
            returns: Array of period returns

        Returns:
            Average drawdown as percentage (negative value)
        """
        if len(returns) < 2:
            return 0.0

        # Build cumulative return curve
        cumulative = np.cumprod(1 + returns)

        # Calculate running maximum
        running_max = np.maximum.accumulate(cumulative)

        # Calculate drawdowns
        drawdowns = (cumulative - running_max) / running_max

        # Filter to only periods in drawdown
        in_drawdown = drawdowns[drawdowns < 0]

        if len(in_drawdown) == 0:
            return 0.0

        return float(np.mean(in_drawdown))

    def _calculate_time_underwater(self) -> float:
        """
        Calculate percentage of time spent in drawdown

        Returns:
            Time underwater as percentage (0-1)
        """
        if not self._equity_curve or len(self._equity_curve) < 2:
            return 0.0

        first_date = self._equity_curve[0][0]
        last_date = self._equity_curve[-1][0]
        total_days = max(1, (last_date - first_date).days)

        days_in_drawdown = 0
        for dd in self._drawdown_history:
            days_in_drawdown += dd.duration_days

        # Add current drawdown
        if self._current_drawdown_start:
            days_in_drawdown += (
                datetime.now(timezone.utc) - self._current_drawdown_start
            ).days

        return days_in_drawdown / total_days

    # =========================================================================
    # WIN/LOSS METRICS CALCULATION
    # =========================================================================

    def get_win_loss_metrics(self) -> WinLossMetrics:
        """
        Calculate win/loss analysis metrics

        Returns:
            WinLossMetrics with win rate, profit factor, Kelly %, streaks
        """
        with self._lock:
            if not self._trades:
                return WinLossMetrics()

            trades = self._trades

            # Separate winners and losers
            winners = [t for t in trades if t.is_winner]
            losers = [t for t in trades if not t.is_winner and t.pnl < 0]

            total_trades = len(trades)
            win_count = len(winners)
            loss_count = len(losers)

            # Win rate
            win_rate = win_count / total_trades if total_trades > 0 else 0.0
            loss_rate = loss_count / total_trades if total_trades > 0 else 0.0

            # P&L statistics
            gross_profit = sum(t.pnl for t in winners) if winners else 0.0
            gross_loss = abs(sum(t.pnl for t in losers)) if losers else 0.0

            # Profit factor
            profit_factor = (
                gross_profit / gross_loss if gross_loss > 0 else float("inf")
            )
            if math.isinf(profit_factor):
                profit_factor = gross_profit if gross_profit > 0 else 0.0

            # Average win/loss
            avg_win = gross_profit / win_count if win_count > 0 else 0.0
            avg_loss = gross_loss / loss_count if loss_count > 0 else 0.0

            # Largest win/loss
            largest_win = max((t.pnl for t in winners), default=0.0)
            largest_loss = abs(min((t.pnl for t in losers), default=0.0))

            # Payoff ratio (avg win / avg loss)
            payoff_ratio = avg_win / avg_loss if avg_loss > 0 else float("inf")
            if math.isinf(payoff_ratio):
                payoff_ratio = avg_win if avg_win > 0 else 0.0

            # Expectancy: (Win Rate * Avg Win) - (Loss Rate * Avg Loss)
            expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)

            # Kelly Percentage: W/P - (1-W)/Q where W=win rate, P=payoff, Q=avg loss/avg win
            kelly_pct = self._calculate_kelly_percentage(win_rate, payoff_ratio)

            # Consecutive wins/losses
            max_consecutive_wins, max_consecutive_losses, current_streak = (
                self._calculate_streaks()
            )

            return WinLossMetrics(
                win_rate=win_rate,
                profit_factor=profit_factor,
                payoff_ratio=payoff_ratio,
                expectancy=expectancy,
                kelly_percentage=kelly_pct,
                consecutive_wins=max_consecutive_wins,
                consecutive_losses=max_consecutive_losses,
                current_streak=current_streak,
                avg_win=avg_win,
                avg_loss=avg_loss,
                largest_win=largest_win,
                largest_loss=largest_loss,
            )

    def _calculate_kelly_percentage(
        self,
        win_rate: float,
        payoff_ratio: float,
    ) -> float:
        """
        Calculate Kelly Criterion for optimal position sizing

        Kelly % = W - (1-W)/R
        Where W = win probability, R = win/loss ratio

        Args:
            win_rate: Probability of winning (0-1)
            payoff_ratio: Average win / Average loss ratio

        Returns:
            Optimal position size as fraction (0-1)
        """
        if payoff_ratio <= 0 or win_rate <= 0:
            return 0.0

        loss_rate = 1 - win_rate
        kelly = win_rate - (loss_rate / payoff_ratio)

        # Cap at 0-1 range and apply safety factor (half Kelly)
        kelly = max(0.0, min(kelly * 0.5, 0.5))

        return kelly

    def _calculate_streaks(self) -> Tuple[int, int, int]:
        """
        Calculate consecutive win/loss streaks

        Returns:
            Tuple of (max_wins, max_losses, current_streak)
            current_streak is positive for wins, negative for losses
        """
        if not self._trades:
            return 0, 0, 0

        max_wins = 0
        max_losses = 0
        current_wins = 0
        current_losses = 0

        for trade in self._trades:
            if trade.is_winner:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            elif trade.pnl < 0:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)
            else:
                # Breakeven - doesn't break streak
                pass

        # Current streak (positive for wins, negative for losses)
        current_streak = current_wins if current_wins > 0 else -current_losses

        return max_wins, max_losses, current_streak

    # =========================================================================
    # RISK METRICS CALCULATION
    # =========================================================================

    def get_risk_metrics(self) -> RiskMetrics:
        """
        Calculate all risk quantification metrics

        Returns:
            RiskMetrics with VaR, CVaR, Beta, MAE, MFE, risk of ruin
        """
        with self._lock:
            if len(self._returns) < 2:
                return RiskMetrics()

            returns = np.array(self._returns)

            # Calculate individual risk metrics
            var_95 = self._calculate_var(returns, confidence=0.95)
            var_99 = self._calculate_var(returns, confidence=0.99)
            cvar_95 = self._calculate_cvar(returns, confidence=0.95)
            cvar_99 = self._calculate_cvar(returns, confidence=0.99)
            beta = self._calculate_beta(returns)
            max_dd = self._calculate_max_drawdown_from_returns(returns)
            volatility = float(
                np.std(returns, ddof=1) * np.sqrt(self.annualization_factor)
            )
            downside_vol = self._calculate_downside_volatility(returns)
            tail_ratio = self._calculate_tail_ratio(returns)

            # MAE and MFE from trades
            mae = self._calculate_mae()
            mfe = self._calculate_mfe()

            # Risk of ruin
            risk_of_ruin = self._calculate_risk_of_ruin()

            risk_level = self._classify_risk_level(max_dd, volatility, var_95)

            return RiskMetrics(
                var_95=var_95,
                var_99=var_99,
                cvar_95=cvar_95,
                cvar_99=cvar_99,
                beta=beta,
                max_adverse_excursion=mae,
                max_favorable_excursion=mfe,
                risk_of_ruin=risk_of_ruin,
                volatility=volatility,
                downside_volatility=downside_vol,
                tail_ratio=tail_ratio,
                risk_level=risk_level,
            )

    def _calculate_var(
        self,
        returns: np.ndarray,
        confidence: float = 0.95,
    ) -> float:
        """
        Calculate Value at Risk at specified confidence level

        Uses historical simulation method.

        Args:
            returns: Array of period returns
            confidence: Confidence level (default: 95%)

        Returns:
            VaR as a positive percentage (loss)
        """
        if len(returns) < 10:
            return 0.0

        # VaR is the percentile loss
        percentile = (1 - confidence) * 100
        var = np.percentile(returns, percentile)

        # Return as positive loss value
        return float(-var) if var < 0 else 0.0

    def _calculate_cvar(
        self,
        returns: np.ndarray,
        confidence: float = 0.95,
    ) -> float:
        """
        Calculate Conditional Value at Risk (Expected Shortfall)

        CVaR is the expected loss given that loss exceeds VaR.

        Args:
            returns: Array of period returns
            confidence: Confidence level (default: 95%)

        Returns:
            CVaR as a positive percentage (loss)
        """
        if len(returns) < 10:
            return 0.0

        # Get VaR threshold
        var_threshold = np.percentile(returns, (1 - confidence) * 100)

        # CVaR is mean of returns below VaR
        tail_returns = returns[returns <= var_threshold]

        if len(tail_returns) == 0:
            return 0.0

        cvar = np.mean(tail_returns)

        # Return as positive loss value
        return float(-cvar) if cvar < 0 else 0.0

    def _calculate_beta(self, returns: np.ndarray) -> float:
        """
        Calculate Beta relative to benchmark

        Beta measures systematic risk (correlation with market).

        Args:
            returns: Array of period returns

        Returns:
            Beta coefficient
        """
        if len(returns) < 2 or len(self._benchmark_returns) < 2:
            return 1.0  # Assume market neutral if no benchmark

        # Align lengths
        benchmark = np.array(self._benchmark_returns[: len(returns)])
        strategy_returns = returns[: len(benchmark)]

        if len(benchmark) < 2:
            return 1.0

        # Calculate covariance
        covariance = np.cov(strategy_returns, benchmark)

        if covariance.ndim < 2:
            return 1.0

        cov_with_market = covariance[0, 1]
        market_variance = np.var(benchmark, ddof=1)

        if market_variance == 0:
            return 1.0

        beta = cov_with_market / market_variance

        return float(beta)

    def _calculate_mae(self) -> float:
        """
        Calculate Maximum Adverse Excursion (average)

        MAE is the maximum loss experienced during each trade.

        Returns:
            Average MAE as percentage
        """
        if not self._trades:
            return 0.0

        mae_values = [
            t.max_adverse_excursion for t in self._trades if t.max_adverse_excursion > 0
        ]

        if not mae_values:
            return 0.0

        return float(np.mean(mae_values))

    def _calculate_mfe(self) -> float:
        """
        Calculate Maximum Favorable Excursion (average)

        MFE is the maximum profit experienced during each trade.

        Returns:
            Average MFE as percentage
        """
        if not self._trades:
            return 0.0

        mfe_values = [
            t.max_favorable_excursion
            for t in self._trades
            if t.max_favorable_excursion > 0
        ]

        if not mfe_values:
            return 0.0

        return float(np.mean(mfe_values))

    def _calculate_risk_of_ruin(self) -> float:
        """
        Calculate Risk of Ruin probability

        Risk of ruin is the probability of losing all capital.
        Uses the formula: ((1-E)/E)^N where E is edge and N is capital units.

        Returns:
            Risk of ruin as probability (0-1)
        """
        if not self._trades:
            return 0.0

        # Calculate edge (expectancy as percentage of risk)
        winners = [t for t in self._trades if t.is_winner]
        losers = [t for t in self._trades if not t.is_winner and t.pnl < 0]

        if not losers:
            return 0.0  # No losses = no risk of ruin

        win_rate = len(winners) / len(self._trades)
        loss_rate = 1 - win_rate

        if win_rate == 0:
            return 1.0  # All losses = certain ruin

        avg_win_pct = np.mean([abs(t.pnl_pct) for t in winners]) if winners else 0
        avg_loss_pct = np.mean([abs(t.pnl_pct) for t in losers]) if losers else 0

        if avg_loss_pct == 0:
            return 0.0

        # Edge calculation
        edge = (win_rate * avg_win_pct) - (loss_rate * avg_loss_pct)

        if edge <= 0:
            return 1.0  # Negative edge = eventual ruin

        # Risk of ruin formula
        # Number of "units" is capital / avg_loss
        units = 1.0 / avg_loss_pct if avg_loss_pct > 0 else 100

        # Simplified risk of ruin
        q = loss_rate / win_rate if win_rate > 0 else 999

        if q >= 1:
            return 1.0

        risk_of_ruin = q ** min(units, 100)  # Cap at 100 units to avoid overflow

        return float(min(risk_of_ruin, 1.0))

    def _calculate_max_drawdown_from_returns(self, returns: np.ndarray) -> float:
        """
        Calculate maximum drawdown from returns array

        Args:
            returns: Array of period returns

        Returns:
            Maximum drawdown as negative percentage
        """
        if len(returns) == 0:
            return 0.0

        # Build cumulative return curve
        cumulative = np.cumprod(1 + returns)

        # Calculate running maximum
        running_max = np.maximum.accumulate(cumulative)

        # Calculate drawdowns
        drawdowns = (cumulative - running_max) / running_max

        # Get maximum drawdown
        max_dd = np.min(drawdowns)

        return float(max_dd)

    def _calculate_max_drawdown_duration(self) -> int:
        """
        Calculate longest drawdown duration in days

        Returns:
            Maximum drawdown duration in days
        """
        max_duration = 0

        # Check historical drawdowns
        for dd in self._drawdown_history:
            if dd.duration_days > max_duration:
                max_duration = dd.duration_days

        # Check current drawdown
        if self._current_drawdown_start is not None:
            current_duration = (
                datetime.now(timezone.utc) - self._current_drawdown_start
            ).days
            if current_duration > max_duration:
                max_duration = current_duration

        return max_duration

    def _calculate_downside_volatility(self, returns: np.ndarray) -> float:
        """
        Calculate annualized downside volatility

        Args:
            returns: Array of period returns

        Returns:
            Annualized downside volatility
        """
        if len(returns) < 2:
            return 0.0

        negative_returns = returns[returns < 0]

        if len(negative_returns) == 0:
            return 0.0

        downside_std = np.std(negative_returns, ddof=1)
        annualized = downside_std * np.sqrt(self.annualization_factor)

        return float(annualized)

    def _calculate_tail_ratio(self, returns: np.ndarray) -> float:
        """
        Calculate tail ratio: 95th percentile / abs(5th percentile)

        Measures asymmetry of tails.

        Args:
            returns: Array of period returns

        Returns:
            Tail ratio
        """
        if len(returns) < 20:
            return 1.0

        upper_tail = np.percentile(returns, 95)
        lower_tail = abs(np.percentile(returns, 5))

        if lower_tail == 0:
            return float("inf") if upper_tail > 0 else 1.0

        return float(upper_tail / lower_tail)

    def _classify_risk_level(
        self,
        max_drawdown: float,
        volatility: float,
        var_95: float,
    ) -> RiskLevel:
        """
        Classify overall risk level based on multiple metrics

        Args:
            max_drawdown: Maximum drawdown percentage
            volatility: Annualized volatility
            var_95: 95% Value at Risk

        Returns:
            RiskLevel classification
        """
        # Score based on multiple factors
        score = 0

        # Max drawdown scoring
        if abs(max_drawdown) < 0.05:
            score += 1
        elif abs(max_drawdown) < 0.10:
            score += 2
        elif abs(max_drawdown) < 0.20:
            score += 3
        elif abs(max_drawdown) < 0.30:
            score += 4
        else:
            score += 5

        # Volatility scoring
        if volatility < 0.10:
            score += 1
        elif volatility < 0.20:
            score += 2
        elif volatility < 0.35:
            score += 3
        elif volatility < 0.50:
            score += 4
        else:
            score += 5

        # VaR scoring
        if var_95 < 0.02:
            score += 1
        elif var_95 < 0.05:
            score += 2
        elif var_95 < 0.08:
            score += 3
        elif var_95 < 0.12:
            score += 4
        else:
            score += 5

        # Average score determines risk level
        avg_score = score / 3

        if avg_score < 1.5:
            return RiskLevel.VERY_LOW
        elif avg_score < 2.5:
            return RiskLevel.LOW
        elif avg_score < 3.5:
            return RiskLevel.MODERATE
        elif avg_score < 4.5:
            return RiskLevel.HIGH
        else:
            return RiskLevel.VERY_HIGH

    # =========================================================================
    # EFFICIENCY METRICS CALCULATION
    # =========================================================================

    def get_efficiency_metrics(self) -> EfficiencyMetrics:
        """
        Calculate trade efficiency metrics

        Returns:
            EfficiencyMetrics with duration, frequency, capital utilization
        """
        with self._lock:
            if not self._trades:
                return EfficiencyMetrics()

            trades = self._trades

            # Average trade duration (in hours)
            durations = [
                t.duration_seconds / 3600 for t in trades if t.duration_seconds > 0
            ]
            avg_duration = np.mean(durations) if durations else 0.0

            # Calculate trading period
            if len(trades) >= 2:
                first_trade = min(t.timestamp for t in trades)
                last_trade = max(t.timestamp for t in trades)
                total_days = max(1, (last_trade - first_trade).days)
                total_weeks = total_days / 7
                total_months = total_days / 30
            else:
                total_days = 1
                total_weeks = 1
                total_months = 1

            # Trade frequency
            trades_per_day = len(trades) / total_days
            trades_per_week = len(trades) / total_weeks
            trades_per_month = len(trades) / total_months

            # Average position size as % of capital
            position_sizes = [t.position_size for t in trades if t.position_size > 0]
            avg_position_pct = 0.0
            if position_sizes:
                avg_position_value = np.mean(position_sizes)
                avg_position_pct = avg_position_value / self.initial_capital

            # Capital utilization
            # Estimate based on concurrent positions
            capital_util = min(avg_position_pct * 2, 1.0)  # Rough estimate

            # Turnover ratio (annualized)
            total_volume = sum(
                t.position_size * t.entry_price
                for t in trades
                if t.position_size > 0 and t.entry_price > 0
            )
            turnover_ratio = (total_volume / self.initial_capital) * (
                365 / max(total_days, 1)
            )

            # Holding period return (return per hour)
            total_return = sum(t.pnl_pct for t in trades)
            total_hours = sum(durations) if durations else 1
            holding_period_return = total_return / total_hours if total_hours > 0 else 0

            return EfficiencyMetrics(
                avg_trade_duration=avg_duration,
                trades_per_day=trades_per_day,
                trades_per_week=trades_per_week,
                trades_per_month=trades_per_month,
                avg_position_size=avg_position_pct,
                capital_utilization=capital_util,
                turnover_ratio=turnover_ratio,
                holding_period_return=holding_period_return,
            )

    # =========================================================================
    # BENCHMARK COMPARISON
    # =========================================================================

    def get_benchmark_comparison(self) -> BenchmarkComparison:
        """
        Calculate benchmark comparison metrics (vs BTC)

        Returns:
            BenchmarkComparison with alpha, beta, correlation, capture ratios
        """
        with self._lock:
            if len(self._returns) < 2 or len(self._benchmark_returns) < 2:
                return BenchmarkComparison()

            returns = np.array(self._returns)
            benchmark = np.array(self._benchmark_returns[: len(returns)])

            if len(benchmark) < 2:
                return BenchmarkComparison()

            strategy_returns = returns[: len(benchmark)]

            # Total returns
            strategy_return = np.sum(strategy_returns)
            benchmark_return = np.sum(benchmark)
            excess_return = strategy_return - benchmark_return

            # Beta calculation
            covariance = np.cov(strategy_returns, benchmark)
            if covariance.ndim >= 2:
                cov_with_market = covariance[0, 1]
                market_variance = np.var(benchmark, ddof=1)
                beta = cov_with_market / market_variance if market_variance > 0 else 1.0
            else:
                beta = 1.0

            # Alpha = Actual Return - (Beta * Benchmark Return)
            alpha = strategy_return - (beta * benchmark_return)

            # Correlation
            correlation = (
                np.corrcoef(strategy_returns, benchmark)[0, 1]
                if len(strategy_returns) > 1
                else 0.0
            )

            # Tracking error
            excess_returns = strategy_returns - benchmark
            tracking_error = np.std(excess_returns, ddof=1)

            # Information ratio
            info_ratio = (
                np.mean(excess_returns) / tracking_error if tracking_error > 0 else 0.0
            )

            # Up/Down capture ratios
            up_capture, down_capture = self._calculate_capture_ratios(
                strategy_returns, benchmark
            )

            return BenchmarkComparison(
                strategy_return=strategy_return,
                benchmark_return=benchmark_return,
                excess_return=excess_return,
                alpha=alpha,
                beta=beta,
                correlation=float(correlation) if not np.isnan(correlation) else 0.0,
                tracking_error=tracking_error,
                information_ratio=info_ratio * np.sqrt(self.annualization_factor),
                up_capture=up_capture,
                down_capture=down_capture,
            )

    def _calculate_capture_ratios(
        self,
        strategy_returns: np.ndarray,
        benchmark_returns: np.ndarray,
    ) -> Tuple[float, float]:
        """
        Calculate up and down capture ratios

        Up capture: How well strategy captures market gains
        Down capture: How much strategy loses during market declines

        Args:
            strategy_returns: Strategy returns array
            benchmark_returns: Benchmark returns array

        Returns:
            Tuple of (up_capture, down_capture)
        """
        # Up periods (benchmark positive)
        up_mask = benchmark_returns > 0
        up_strategy = strategy_returns[up_mask]
        up_benchmark = benchmark_returns[up_mask]

        if len(up_benchmark) > 0 and np.sum(up_benchmark) != 0:
            up_capture = np.sum(up_strategy) / np.sum(up_benchmark)
        else:
            up_capture = 1.0

        # Down periods (benchmark negative)
        down_mask = benchmark_returns < 0
        down_strategy = strategy_returns[down_mask]
        down_benchmark = benchmark_returns[down_mask]

        if len(down_benchmark) > 0 and np.sum(down_benchmark) != 0:
            down_capture = np.sum(down_strategy) / np.sum(down_benchmark)
        else:
            down_capture = 1.0

        return float(up_capture), float(down_capture)

    # =========================================================================
    # STATISTICAL METRICS CALCULATION
    # =========================================================================

    def get_statistical_metrics(self) -> StatisticalMetrics:
        """
        Calculate statistical analysis metrics for return distribution

        Returns:
            StatisticalMetrics with distribution characteristics
        """
        with self._lock:
            if len(self._returns) < 2:
                return StatisticalMetrics()

            returns = np.array(self._returns)

            # Basic statistics
            mean_return = float(np.mean(returns))
            median_return = float(np.median(returns))
            std_dev = float(np.std(returns, ddof=1))

            # Distribution shape
            skewness = float(stats.skew(returns)) if len(returns) >= 3 else 0.0
            kurtosis = float(stats.kurtosis(returns)) if len(returns) >= 4 else 0.0

            # Total and annualized return
            total_return = np.sum(returns)

            # Calculate annualized return
            if len(self._trades) >= 2:
                first_trade = min(t.timestamp for t in self._trades)
                last_trade = max(t.timestamp for t in self._trades)
                days = max(1, (last_trade - first_trade).days)
                annualized_return = total_return * (365 / days)
            else:
                annualized_return = total_return

            return StatisticalMetrics(
                mean_return=mean_return,
                median_return=median_return,
                std_deviation=std_dev,
                skewness=skewness,
                kurtosis=kurtosis,
                total_return=total_return,
                annualized_return=annualized_return,
                total_trades=len(self._trades),
            )

    # =========================================================================
    # DRAWDOWN ANALYSIS
    # =========================================================================

    def get_drawdown_analysis(self) -> DrawdownAnalysis:
        """
        Get comprehensive drawdown analysis including history

        Returns:
            DrawdownAnalysis with current state and historical data
        """
        with self._lock:
            # Current drawdown calculation
            current_dd = 0.0
            current_dd_duration = 0
            current_status = DrawdownStatus.NO_DRAWDOWN

            if self._current_equity < self._peak_equity:
                current_dd = (
                    self._current_equity - self._peak_equity
                ) / self._peak_equity
                current_status = DrawdownStatus.IN_DRAWDOWN

                if self._current_drawdown_start:
                    current_dd_duration = (
                        datetime.now(timezone.utc) - self._current_drawdown_start
                    ).days
            elif (
                self._current_equity >= self._peak_equity
                and len(self._drawdown_history) > 0
            ):
                current_status = DrawdownStatus.NEW_HIGH

            # Historical statistics
            max_dd = current_dd
            max_dd_duration = current_dd_duration
            total_dd_depth = 0.0
            total_recovery_time = 0.0
            recovery_count = 0

            for dd in self._drawdown_history:
                if dd.depth < max_dd:
                    max_dd = dd.depth
                if dd.duration_days > max_dd_duration:
                    max_dd_duration = dd.duration_days
                total_dd_depth += abs(dd.depth)
                if dd.recovery_days is not None:
                    total_recovery_time += dd.recovery_days
                    recovery_count += 1

            drawdown_count = len(self._drawdown_history)
            if self._current_drawdown_start:
                drawdown_count += 1

            avg_dd = total_dd_depth / drawdown_count if drawdown_count > 0 else 0.0
            avg_recovery = (
                total_recovery_time / recovery_count if recovery_count > 0 else 0.0
            )

            # Time in drawdown percentage
            total_days = 0
            days_in_drawdown = 0

            if self._equity_curve:
                first_date = self._equity_curve[0][0]
                last_date = self._equity_curve[-1][0]
                total_days = max(1, (last_date - first_date).days)

                for dd in self._drawdown_history:
                    days_in_drawdown += dd.duration_days

                if self._current_drawdown_start:
                    days_in_drawdown += current_dd_duration

            time_in_dd_pct = days_in_drawdown / total_days if total_days > 0 else 0.0

            # Build underwater curve (last 100 points)
            underwater_curve = []
            if self._equity_curve:
                peak = self._equity_curve[0][1]
                for ts, equity in self._equity_curve[-100:]:
                    if equity > peak:
                        peak = equity
                    dd = (equity - peak) / peak if peak > 0 else 0.0
                    underwater_curve.append((ts, dd))

            return DrawdownAnalysis(
                current_drawdown=current_dd,
                current_drawdown_duration=current_dd_duration,
                max_drawdown=max_dd,
                max_drawdown_duration=max_dd_duration,
                avg_drawdown=avg_dd,
                avg_recovery_time=avg_recovery,
                drawdown_count=drawdown_count,
                current_status=current_status,
                drawdown_history=self._drawdown_history.copy(),
                time_in_drawdown_pct=time_in_dd_pct,
                underwater_curve=underwater_curve,
            )

    # =========================================================================
    # ATTRIBUTION ANALYSIS
    # =========================================================================

    def get_attribution_by_strategy(self) -> List[AttributionByDimension]:
        """
        Get performance attribution breakdown by strategy

        Returns:
            List of AttributionByDimension for each strategy
        """
        return self._calculate_attribution("strategy")

    def get_attribution_by_symbol(self) -> List[AttributionByDimension]:
        """
        Get performance attribution breakdown by symbol

        Returns:
            List of AttributionByDimension for each symbol
        """
        return self._calculate_attribution("symbol")

    def get_attribution_by_period(
        self,
        period: MetricsPeriod = MetricsPeriod.MONTHLY,
    ) -> List[AttributionByDimension]:
        """
        Get performance attribution breakdown by time period

        Args:
            period: Time period granularity

        Returns:
            List of AttributionByDimension for each period
        """
        return self._calculate_attribution("period", period=period)

    def _calculate_attribution(
        self,
        dimension: str,
        period: Optional[MetricsPeriod] = None,
    ) -> List[AttributionByDimension]:
        """
        Calculate attribution for a specific dimension

        Args:
            dimension: Dimension to group by (strategy, symbol, period)
            period: Period granularity for time-based attribution

        Returns:
            List of attribution results
        """
        with self._lock:
            if not self._trades:
                return []

            # Group trades by dimension
            groups: Dict[str, List[TradeMetadata]] = defaultdict(list)

            for trade in self._trades:
                if dimension == "strategy":
                    key = trade.strategy
                elif dimension == "symbol":
                    key = trade.symbol
                elif dimension == "period":
                    key = self._get_period_key(
                        trade.timestamp, period or MetricsPeriod.MONTHLY
                    )
                else:
                    key = "unknown"

                groups[key].append(trade)

            # Calculate total P&L for contribution percentages
            total_pnl = sum(t.pnl for t in self._trades)

            # Calculate metrics for each group
            results = []
            for value, trades in groups.items():
                group_returns = [t.pnl_pct for t in trades]
                group_pnl = sum(t.pnl for t in trades)
                win_count = sum(1 for t in trades if t.is_winner)

                # Calculate Sharpe for group
                if len(group_returns) >= 2:
                    sharpe = self._calculate_sharpe_ratio(np.array(group_returns))
                    max_dd = self._calculate_max_drawdown_from_returns(
                        np.array(group_returns)
                    )
                else:
                    sharpe = 0.0
                    max_dd = 0.0

                attribution = AttributionByDimension(
                    dimension_name=dimension,
                    dimension_value=value,
                    total_pnl=group_pnl,
                    contribution_pct=(group_pnl / abs(total_pnl) * 100)
                    if total_pnl != 0
                    else 0.0,
                    trades_count=len(trades),
                    win_rate=win_count / len(trades) if trades else 0.0,
                    avg_return=np.mean(group_returns) if group_returns else 0.0,
                    sharpe_ratio=sharpe,
                    max_drawdown=max_dd,
                )
                results.append(attribution)

            # Sort by P&L descending
            results.sort(key=lambda x: x.total_pnl, reverse=True)

            return results

    def _get_period_key(self, timestamp: datetime, period: MetricsPeriod) -> str:
        """
        Get period key string for a timestamp

        Args:
            timestamp: Trade timestamp
            period: Period granularity

        Returns:
            Period key string
        """
        if period == MetricsPeriod.DAILY:
            return timestamp.strftime("%Y-%m-%d")
        elif period == MetricsPeriod.WEEKLY:
            return timestamp.strftime("%Y-W%W")
        elif period == MetricsPeriod.MONTHLY:
            return timestamp.strftime("%Y-%m")
        elif period == MetricsPeriod.QUARTERLY:
            quarter = (timestamp.month - 1) // 3 + 1
            return f"{timestamp.year}-Q{quarter}"
        elif period == MetricsPeriod.YEARLY:
            return str(timestamp.year)
        else:
            return "all_time"

    # =========================================================================
    # ROLLING METRICS CALCULATION
    # =========================================================================

    def get_rolling_metrics(
        self,
        window_size: Optional[int] = None,
        period: MetricsPeriod = MetricsPeriod.DAILY,
    ) -> RollingMetrics:
        """
        Calculate rolling window metrics over time

        Args:
            window_size: Rolling window size (default: self.rolling_window)
            period: Time period for aggregation

        Returns:
            RollingMetrics with time-series data
        """
        with self._lock:
            window = window_size or self.rolling_window

            if len(self._returns) < window:
                return RollingMetrics(window_size=window, period_type=period)

            returns = np.array(self._returns)
            n = len(returns)

            # Calculate rolling metrics
            timestamps = []
            rolling_sharpe = []
            rolling_sortino = []
            rolling_volatility = []
            rolling_win_rate = []
            rolling_pnl = []
            rolling_max_dd = []

            for i in range(window - 1, n):
                # Get window slice
                window_returns = returns[i - window + 1 : i + 1]
                window_trades = self._trades[i - window + 1 : i + 1]

                # Timestamp
                timestamps.append(window_trades[-1].timestamp)

                # Sharpe
                rolling_sharpe.append(self._calculate_sharpe_ratio(window_returns))

                # Sortino
                rolling_sortino.append(self._calculate_sortino_ratio(window_returns))

                # Volatility (annualized)
                vol = float(
                    np.std(window_returns, ddof=1) * np.sqrt(self.annualization_factor)
                )
                rolling_volatility.append(vol)

                # Win rate
                wins = sum(1 for t in window_trades if t.is_winner)
                rolling_win_rate.append(wins / window)

                # Cumulative P&L
                rolling_pnl.append(sum(t.pnl for t in window_trades))

                # Max drawdown
                rolling_max_dd.append(
                    self._calculate_max_drawdown_from_returns(window_returns)
                )

            return RollingMetrics(
                window_size=window,
                period_type=period,
                timestamps=timestamps,
                rolling_sharpe=rolling_sharpe,
                rolling_sortino=rolling_sortino,
                rolling_volatility=rolling_volatility,
                rolling_win_rate=rolling_win_rate,
                rolling_pnl=rolling_pnl,
                rolling_max_drawdown=rolling_max_dd,
            )

    # =========================================================================
    # AGGREGATED METRICS
    # =========================================================================

    def get_all_metrics(self) -> AllMetrics:
        """
        Get all metrics in a single response

        Returns:
            AllMetrics containing risk_adjusted, drawdown, win_loss, risk, efficiency
        """
        with self._lock:
            return AllMetrics(
                risk_adjusted=self.get_risk_adjusted_metrics(),
                drawdown=self.get_drawdown_metrics(),
                win_loss=self.get_win_loss_metrics(),
                risk=self.get_risk_metrics(),
                efficiency=self.get_efficiency_metrics(),
                total_trades=len(self._trades),
                total_pnl=sum(t.pnl for t in self._trades),
                generated_at=datetime.now(timezone.utc),
            )

    def get_comprehensive_metrics(
        self, force_recalculate: bool = False
    ) -> ComprehensiveMetrics:
        """
        Get complete metrics summary combining all metric types

        Uses caching for performance. Set force_recalculate=True to bypass cache.

        Args:
            force_recalculate: Force recalculation ignoring cache

        Returns:
            ComprehensiveMetrics with all calculated values
        """
        with self._lock:
            # Check cache
            if self._cache_valid and self._metrics_cache and not force_recalculate:
                return self._metrics_cache

            # Calculate all metrics
            risk_adjusted = self.get_risk_adjusted_metrics()
            risk_metrics = self.get_risk_metrics()
            statistical = self.get_statistical_metrics()
            drawdown = self.get_drawdown_analysis()

            # Attribution
            by_strategy = self._calculate_attribution("strategy")
            by_symbol = self._calculate_attribution("symbol")
            by_period = self._calculate_attribution(
                "period", period=MetricsPeriod.MONTHLY
            )

            # Rolling metrics (if enough data)
            rolling = None
            if len(self._returns) >= self.rolling_window:
                rolling = self.get_rolling_metrics()

            # Build comprehensive metrics
            metrics = ComprehensiveMetrics(
                risk_adjusted=risk_adjusted,
                risk_metrics=risk_metrics,
                statistical=statistical,
                drawdown_analysis=drawdown,
                attribution_by_strategy=by_strategy,
                attribution_by_symbol=by_symbol,
                attribution_by_period=by_period,
                rolling_metrics=rolling,
                total_trades=len(self._trades),
                total_pnl=sum(t.pnl for t in self._trades),
                generated_at=datetime.now(timezone.utc),
            )

            # Cache results
            self._metrics_cache = metrics
            self._cache_valid = True

            logger.info(
                f"Calculated comprehensive metrics: "
                f"{metrics.total_trades} trades, "
                f"P&L=${metrics.total_pnl:+,.2f}, "
                f"Sharpe={risk_adjusted.sharpe_ratio:.2f}"
            )

            return metrics

    # =========================================================================
    # PERIOD COMPARISON
    # =========================================================================

    def compare_periods(
        self,
        period_days: int = 30,
    ) -> Dict[str, Any]:
        """
        Compare metrics between current and previous period

        Args:
            period_days: Number of days per period

        Returns:
            Dictionary with current vs previous period comparison
        """
        with self._lock:
            if not self._trades:
                return {"error": "No trades to compare"}

            now = datetime.now(timezone.utc)
            period_start = now - timedelta(days=period_days)
            prev_period_start = period_start - timedelta(days=period_days)

            # Split trades by period
            current_trades = [t for t in self._trades if t.timestamp >= period_start]
            prev_trades = [
                t
                for t in self._trades
                if prev_period_start <= t.timestamp < period_start
            ]

            def calculate_period_metrics(trades: List[TradeMetadata]) -> Dict[str, Any]:
                if not trades:
                    return {
                        "trades": 0,
                        "pnl": 0.0,
                        "win_rate": 0.0,
                        "avg_return": 0.0,
                    }

                returns = [t.pnl_pct for t in trades]
                winners = sum(1 for t in trades if t.is_winner)

                return {
                    "trades": len(trades),
                    "pnl": sum(t.pnl for t in trades),
                    "win_rate": winners / len(trades),
                    "avg_return": np.mean(returns),
                    "sharpe": self._calculate_sharpe_ratio(np.array(returns))
                    if len(returns) >= 2
                    else 0.0,
                }

            current = calculate_period_metrics(current_trades)
            previous = calculate_period_metrics(prev_trades)

            # Calculate changes
            def calc_change(curr: float, prev: float) -> float:
                if prev == 0:
                    return 0.0 if curr == 0 else float("inf")
                return (curr - prev) / abs(prev) * 100

            return {
                "period_days": period_days,
                "current_period": {
                    "start": period_start.isoformat(),
                    "end": now.isoformat(),
                    **current,
                },
                "previous_period": {
                    "start": prev_period_start.isoformat(),
                    "end": period_start.isoformat(),
                    **previous,
                },
                "changes": {
                    "trades_change": current["trades"] - previous["trades"],
                    "pnl_change": current["pnl"] - previous["pnl"],
                    "win_rate_change_pct": calc_change(
                        current["win_rate"], previous["win_rate"]
                    ),
                    "sharpe_change": current.get("sharpe", 0)
                    - previous.get("sharpe", 0),
                },
                "generated_at": now.isoformat(),
            }

    # =========================================================================
    # STATE MANAGEMENT
    # =========================================================================

    def get_state(self) -> Dict[str, Any]:
        """
        Get current calculator state for persistence

        Returns:
            Dictionary containing all state data
        """
        with self._lock:
            return {
                "initial_capital": self.initial_capital,
                "risk_free_rate": self.risk_free_rate,
                "rolling_window": self.rolling_window,
                "annualization_factor": self.annualization_factor,
                "current_equity": self._current_equity,
                "peak_equity": self._peak_equity,
                "trades": [
                    {
                        "trade_id": t.trade_id,
                        "timestamp": t.timestamp.isoformat(),
                        "pnl": t.pnl,
                        "pnl_pct": t.pnl_pct,
                        "strategy": t.strategy,
                        "symbol": t.symbol,
                        "direction": t.direction,
                        "duration_seconds": t.duration_seconds,
                        "is_winner": t.is_winner,
                        "entry_price": t.entry_price,
                        "exit_price": t.exit_price,
                        "position_size": t.position_size,
                        "max_adverse_excursion": t.max_adverse_excursion,
                        "max_favorable_excursion": t.max_favorable_excursion,
                    }
                    for t in self._trades
                ],
                "benchmark_returns": self._benchmark_returns,
                "drawdown_history": [d.to_dict() for d in self._drawdown_history],
            }

    def load_state(self, state: Dict[str, Any]) -> None:
        """
        Load calculator state from persistence

        Args:
            state: State dictionary from get_state()
        """
        with self._lock:
            if "initial_capital" not in state:
                raise ValueError(
                    "Advanced-metrics state is missing 'initial_capital' — "
                    "refusing to guess an account size. State produced by "
                    "get_state() always carries it; a missing key means the "
                    "state is corrupt."
                )
            self.initial_capital = float(state["initial_capital"])
            self.risk_free_rate = state.get("risk_free_rate", 0.02)
            self.rolling_window = state.get("rolling_window", 30)
            self.annualization_factor = state.get("annualization_factor", 252)
            self._current_equity = state.get("current_equity", self.initial_capital)
            self._peak_equity = state.get("peak_equity", self.initial_capital)
            self._benchmark_returns = state.get("benchmark_returns", [])

            # Reconstruct trades
            self._trades = []
            self._returns = []
            self._equity_curve = []

            equity = self.initial_capital
            for trade_dict in state.get("trades", []):
                trade = TradeMetadata(
                    trade_id=trade_dict["trade_id"],
                    timestamp=datetime.fromisoformat(trade_dict["timestamp"]),
                    pnl=trade_dict["pnl"],
                    pnl_pct=trade_dict["pnl_pct"],
                    strategy=trade_dict["strategy"],
                    symbol=trade_dict["symbol"],
                    direction=trade_dict["direction"],
                    duration_seconds=trade_dict.get("duration_seconds", 0),
                    is_winner=trade_dict.get("is_winner", trade_dict["pnl"] > 0),
                    entry_price=trade_dict.get("entry_price", 0.0),
                    exit_price=trade_dict.get("exit_price", 0.0),
                    position_size=trade_dict.get("position_size", 0.0),
                    max_adverse_excursion=trade_dict.get("max_adverse_excursion", 0.0),
                    max_favorable_excursion=trade_dict.get(
                        "max_favorable_excursion", 0.0
                    ),
                )
                self._trades.append(trade)
                self._returns.append(trade.pnl_pct)
                equity += trade.pnl
                self._equity_curve.append((trade.timestamp, equity))

            # Reconstruct drawdown history
            self._drawdown_history = []
            for dd_dict in state.get("drawdown_history", []):
                dd = DrawdownInfo(
                    start_date=datetime.fromisoformat(dd_dict["start_date"]),
                    end_date=datetime.fromisoformat(dd_dict["end_date"])
                    if dd_dict.get("end_date")
                    else None,
                    trough_date=datetime.fromisoformat(dd_dict["trough_date"])
                    if dd_dict.get("trough_date")
                    else None,
                    depth=dd_dict.get("depth", 0.0) / 100,  # Convert from percentage
                    duration_days=dd_dict.get("duration_days", 0),
                    recovery_days=dd_dict.get("recovery_days"),
                    peak_equity=dd_dict.get("peak_equity", 0.0),
                    trough_equity=dd_dict.get("trough_equity", 0.0),
                    recovery_equity=dd_dict.get("recovery_equity"),
                    status=DrawdownStatus(dd_dict.get("status", "in_drawdown")),
                )
                self._drawdown_history.append(dd)

            self._cache_valid = False
            logger.info(f"Loaded state with {len(self._trades)} trades")

    def reset(self) -> None:
        """Reset calculator to initial state"""
        with self._lock:
            self._trades = []
            self._returns = []
            self._equity_curve = []
            self._current_equity = self.initial_capital
            self._peak_equity = self.initial_capital
            self._current_drawdown_start = None
            self._current_drawdown_trough = None
            self._current_drawdown_trough_date = None
            self._drawdown_history = []
            self._metrics_cache = None
            self._cache_valid = False
            logger.info("Advanced metrics calculator reset to initial state")

    def get_summary(self) -> Dict[str, Any]:
        """
        Get quick summary of current metrics state

        Returns:
            Summary dictionary with key metrics
        """
        with self._lock:
            total_pnl = sum(t.pnl for t in self._trades)
            win_count = sum(1 for t in self._trades if t.is_winner)
            current_dd = (
                (self._current_equity - self._peak_equity) / self._peak_equity
                if self._peak_equity > 0
                else 0.0
            )

            return {
                "total_trades": len(self._trades),
                "total_pnl": round(total_pnl, 2),
                "current_equity": round(self._current_equity, 2),
                "peak_equity": round(self._peak_equity, 2),
                "current_drawdown": round(current_dd * 100, 2),
                "win_rate": round(win_count / len(self._trades) * 100, 2)
                if self._trades
                else 0.0,
                "unique_strategies": len(set(t.strategy for t in self._trades)),
                "unique_symbols": len(set(t.symbol for t in self._trades)),
            }


# =============================================================================
# GLOBAL INSTANCE MANAGEMENT (THREAD-SAFE SINGLETON)
# =============================================================================

# Global calculator instance
_advanced_metrics_calculator: Optional[AdvancedMetricsCalculator] = None
_instance_lock: threading.Lock = threading.Lock()


def get_advanced_metrics_calculator(
    initial_capital: Optional[float] = None,
    risk_free_rate: Optional[float] = None,
    benchmark_returns: Optional[List[float]] = None,
) -> AdvancedMetricsCalculator:
    """
    Get or create the global advanced metrics calculator instance

    Thread-safe singleton pattern ensures only one instance exists.

    Args:
        initial_capital: Initial capital (only used if creating new instance)
        risk_free_rate: Risk-free rate (only used if creating new instance)
        benchmark_returns: Benchmark returns (only used if creating new instance)

    Returns:
        Global AdvancedMetricsCalculator instance

    Example:
        >>> calc = get_advanced_metrics_calculator()  # capital from Settings
        >>> calc.add_trade(trade_data)
        >>> metrics = calc.get_comprehensive_metrics()
    """
    global _advanced_metrics_calculator

    with _instance_lock:
        if _advanced_metrics_calculator is None:
            # `is None` check, NOT `or`: an explicit capital of 0.0 must not
            # be silently replaced by a fallback (falsy-fallback, AUDIT §2.5).
            capital = (
                get_settings().paper_initial_balance
                if initial_capital is None
                else initial_capital
            )
            rf_rate = 0.02 if risk_free_rate is None else risk_free_rate
            _advanced_metrics_calculator = AdvancedMetricsCalculator(
                initial_capital=capital,
                risk_free_rate=rf_rate,
                benchmark_returns=benchmark_returns,
            )
            logger.info(
                f"Created new AdvancedMetricsCalculator: "
                f"capital=${capital:,.2f}, risk_free={rf_rate:.2%}"
            )

        return _advanced_metrics_calculator


def reset_advanced_metrics_calculator() -> None:
    """
    Reset the global advanced metrics calculator instance

    Useful for testing or starting fresh analysis.
    """
    global _advanced_metrics_calculator

    with _instance_lock:
        _advanced_metrics_calculator = None
        logger.info("Global advanced metrics calculator reset")
