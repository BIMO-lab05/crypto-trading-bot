"""
Attribution Analysis Module
Purpose: Comprehensive P&L attribution system to decompose trading performance

This module provides multi-dimensional attribution analysis for trading performance:
- Strategy Attribution: Which strategies generate profits/losses
- Symbol Attribution: Which symbols are performing best/worst
- Timeframe Attribution: Performance breakdown by time periods
- Direction Attribution: Long vs Short performance comparison
- Market Condition Attribution: Trending vs Ranging market performance

Features:
- Real-time attribution updates after each trade
- Historical attribution stored in TimescaleDB
- Performance decomposition (Alpha, Beta, Residual)
- Daily attribution report generation

Author: Backend Developer Agent
Date: 2025-12-11
"""

import logging
from typing import List, Dict, Optional, Tuple, Any

from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import math
import numpy as np

# Used in __init__/reset bodies below; the noqa keeps autoflake from stripping
# it after refactors (known repo gotcha).
from app.config import get_settings  # noqa: F401

# Configure logging for attribution module
logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS FOR ATTRIBUTION DIMENSIONS
# =============================================================================


class AttributionDimension(str, Enum):
    """Dimensions available for P&L attribution analysis"""

    STRATEGY = "strategy"  # By trading strategy
    SYMBOL = "symbol"  # By trading pair/symbol
    TIMEFRAME = "timeframe"  # By time period (hourly, daily, weekly)
    DIRECTION = "direction"  # By trade direction (long/short)
    MARKET_CONDITION = "market_condition"  # By market condition (trending/ranging)


class MarketCondition(str, Enum):
    """Market condition classification for trades"""

    TRENDING_UP = "trending_up"  # Price moving up consistently
    TRENDING_DOWN = "trending_down"  # Price moving down consistently
    RANGING = "ranging"  # Price moving sideways
    VOLATILE = "volatile"  # High volatility, no clear trend
    UNKNOWN = "unknown"  # Could not determine condition


class TradeDirection(str, Enum):
    """Trade direction for attribution"""

    LONG = "long"  # Buy low, sell high
    SHORT = "short"  # Sell high, buy low


class TradePeriod(str, Enum):
    """Time periods for attribution aggregation"""

    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


# =============================================================================
# DATA MODELS
# =============================================================================


@dataclass
class AttributionMetrics:
    """
    Core metrics for attribution analysis

    These metrics are calculated for each attribution dimension (strategy, symbol, etc.)
    to provide comprehensive performance insights.

    Attributes:
        total_pnl: Total profit/loss in USD
        win_rate: Percentage of winning trades (0.0 to 1.0)
        sharpe_ratio: Risk-adjusted return metric
        max_drawdown: Maximum peak-to-trough decline
        avg_win: Average profit on winning trades
        avg_loss: Average loss on losing trades
        profit_factor: Ratio of gross profit to gross loss
        trades_count: Total number of trades
        sortino_ratio: Risk-adjusted return using downside deviation
        calmar_ratio: Return divided by max drawdown
    """

    total_pnl: float = 0.0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    trades_count: int = 0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for API response"""
        return {
            "total_pnl": round(self.total_pnl, 2),
            "win_rate": round(self.win_rate * 100, 2),  # Convert to percentage
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "max_drawdown": round(self.max_drawdown, 2),
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "profit_factor": round(self.profit_factor, 3),
            "trades_count": self.trades_count,
            "sortino_ratio": round(self.sortino_ratio, 3),
            "calmar_ratio": round(self.calmar_ratio, 3),
        }


@dataclass
class TradeRecord:
    """
    Complete trade record with all metadata for attribution analysis

    Each closed trade is stored with comprehensive metadata to enable
    multi-dimensional attribution analysis.

    Attributes:
        trade_id: Unique identifier for the trade
        symbol: Trading pair (e.g., BTCUSDT)
        strategy: Strategy that generated the trade
        direction: Long or Short
        entry_time: Trade entry timestamp
        exit_time: Trade exit timestamp
        entry_price: Entry price
        exit_price: Exit price
        quantity: Trade quantity
        pnl: Profit/loss in USD
        pnl_pct: Profit/loss as percentage
        fees: Trading fees paid
        market_condition: Market condition at trade time
        timeframe: Aggregation timeframe for the trade
        metadata: Additional trade metadata
    """

    trade_id: str
    symbol: str
    strategy: str
    direction: TradeDirection
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_pct: float
    fees: float = 0.0
    market_condition: MarketCondition = MarketCondition.UNKNOWN
    timeframe: str = "1h"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_winner(self) -> bool:
        """Check if trade was profitable"""
        return self.pnl > 0

    @property
    def duration_seconds(self) -> int:
        """Calculate trade duration in seconds"""
        return int((self.exit_time - self.entry_time).total_seconds())

    def to_dict(self) -> Dict[str, Any]:
        """Convert trade record to dictionary"""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "direction": self.direction.value,
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat(),
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "pnl": round(self.pnl, 2),
            "pnl_pct": round(self.pnl_pct, 4),
            "fees": round(self.fees, 4),
            "market_condition": self.market_condition.value,
            "is_winner": self.is_winner,
            "duration_seconds": self.duration_seconds,
            "metadata": self.metadata,
        }


@dataclass
class AttributionResult:
    """
    Attribution result for a specific dimension value

    Contains metrics and contribution percentage for one dimension value
    (e.g., one strategy, one symbol, etc.)

    Attributes:
        dimension: The attribution dimension (strategy, symbol, etc.)
        value: The dimension value (e.g., "BTCUSDT", "pairs_trading")
        metrics: Performance metrics for this dimension value
        contribution_pct: Percentage contribution to total P&L
        trades: List of trades in this attribution bucket
    """

    dimension: AttributionDimension
    value: str
    metrics: AttributionMetrics
    contribution_pct: float = 0.0
    trades: List[TradeRecord] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert attribution result to dictionary"""
        return {
            "dimension": self.dimension.value,
            "value": self.value,
            "metrics": self.metrics.to_dict(),
            "contribution_pct": round(self.contribution_pct, 2),
            "trades_count": len(self.trades),
        }


@dataclass
class AttributionSummary:
    """
    Complete attribution summary across all dimensions

    Provides a comprehensive view of performance attribution including
    overall metrics and breakdown by each dimension.

    Attributes:
        overall_metrics: Total portfolio performance metrics
        by_strategy: Attribution breakdown by strategy
        by_symbol: Attribution breakdown by symbol
        by_direction: Attribution breakdown by trade direction
        by_market_condition: Attribution breakdown by market condition
        generated_at: Timestamp when summary was generated
        period_start: Start of analysis period
        period_end: End of analysis period
    """

    overall_metrics: AttributionMetrics
    by_strategy: List[AttributionResult] = field(default_factory=list)
    by_symbol: List[AttributionResult] = field(default_factory=list)
    by_direction: List[AttributionResult] = field(default_factory=list)
    by_market_condition: List[AttributionResult] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert summary to dictionary for API response"""
        return {
            "overall_metrics": self.overall_metrics.to_dict(),
            "by_strategy": [r.to_dict() for r in self.by_strategy],
            "by_symbol": [r.to_dict() for r in self.by_symbol],
            "by_direction": [r.to_dict() for r in self.by_direction],
            "by_market_condition": [r.to_dict() for r in self.by_market_condition],
            "generated_at": self.generated_at.isoformat(),
            "period_start": self.period_start.isoformat()
            if self.period_start
            else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
        }


@dataclass
class TrendAnalysis:
    """
    Trend analysis for attribution over time periods

    Tracks how attribution metrics change over different time periods
    to identify improving or declining strategies/symbols.

    Attributes:
        dimension: Attribution dimension being analyzed
        value: Dimension value (strategy name, symbol, etc.)
        periods: List of time periods
        pnl_trend: P&L for each period
        win_rate_trend: Win rate for each period
        trades_count_trend: Trade count for each period
        moving_avg_pnl: Moving average of P&L
        trend_direction: Overall trend direction (up, down, flat)
    """

    dimension: AttributionDimension
    value: str
    periods: List[str] = field(default_factory=list)
    pnl_trend: List[float] = field(default_factory=list)
    win_rate_trend: List[float] = field(default_factory=list)
    trades_count_trend: List[int] = field(default_factory=list)
    moving_avg_pnl: List[float] = field(default_factory=list)
    trend_direction: str = "flat"  # "up", "down", "flat"

    def to_dict(self) -> Dict[str, Any]:
        """Convert trend analysis to dictionary"""
        return {
            "dimension": self.dimension.value,
            "value": self.value,
            "periods": self.periods,
            "pnl_trend": [round(p, 2) for p in self.pnl_trend],
            "win_rate_trend": [round(w * 100, 2) for w in self.win_rate_trend],
            "trades_count_trend": self.trades_count_trend,
            "moving_avg_pnl": [round(m, 2) for m in self.moving_avg_pnl],
            "trend_direction": self.trend_direction,
        }


@dataclass
class PerformanceDecomposition:
    """
    Performance decomposition into Alpha, Beta, and Residual components

    Decomposes strategy returns into:
    - Alpha: Strategy-specific returns (skill)
    - Beta: Market correlation (systematic risk)
    - Residual: Unexplained variance (luck/noise)

    Attributes:
        strategy: Strategy name
        alpha: Strategy-specific return (skill component)
        beta: Market correlation coefficient
        residual: Unexplained variance
        r_squared: Coefficient of determination
        total_return: Total return of the strategy
        benchmark_return: Benchmark (market) return
        information_ratio: Risk-adjusted excess return
    """

    strategy: str
    alpha: float = 0.0
    beta: float = 0.0
    residual: float = 0.0
    r_squared: float = 0.0
    total_return: float = 0.0
    benchmark_return: float = 0.0
    information_ratio: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert decomposition to dictionary"""
        return {
            "strategy": self.strategy,
            "alpha": round(self.alpha, 4),
            "beta": round(self.beta, 4),
            "residual": round(self.residual, 4),
            "r_squared": round(self.r_squared, 4),
            "total_return": round(self.total_return * 100, 2),  # Percentage
            "benchmark_return": round(self.benchmark_return * 100, 2),
            "information_ratio": round(self.information_ratio, 3),
        }


# =============================================================================
# MAIN ATTRIBUTION ANALYZER CLASS
# =============================================================================


class AttributionAnalyzer:
    """
    Comprehensive P&L Attribution Analyzer

    This class provides multi-dimensional attribution analysis for trading performance.
    It tracks all closed trades and calculates attribution metrics across different
    dimensions (strategy, symbol, direction, market condition).

    Features:
    - Real-time attribution updates after each trade
    - Historical attribution stored in memory (can be persisted to TimescaleDB)
    - Performance decomposition (Alpha, Beta, Residual)
    - Daily attribution report generation
    - Trend analysis over configurable time periods

    Usage:
        analyzer = AttributionAnalyzer()  # capital from Settings.paper_initial_balance
        analyzer.add_trade(trade_record)
        summary = analyzer.get_attribution_summary()
    """

    def __init__(
        self,
        initial_capital: Optional[float] = None,
        risk_free_rate: float = 0.02,  # Annual risk-free rate (2%)
    ):
        """
        Initialize the Attribution Analyzer

        Args:
            initial_capital: Starting capital for percentage calculations.
                None (default) resolves to Settings.paper_initial_balance —
                never a hardcoded account size.
            risk_free_rate: Annual risk-free rate for Sharpe ratio calculation
        """
        # Store initialization parameters
        if initial_capital is None:
            initial_capital = get_settings().paper_initial_balance
        self.initial_capital = initial_capital
        self.risk_free_rate = risk_free_rate

        # Trade storage
        self._trades: List[TradeRecord] = []

        # Attribution caches (invalidated on new trades)
        self._attribution_cache: Dict[
            AttributionDimension, List[AttributionResult]
        ] = {}
        self._cache_valid = False

        # Equity tracking for drawdown calculation
        self._equity_curve: List[Tuple[datetime, float]] = []
        self._peak_equity = initial_capital
        self._current_equity = initial_capital

        # Benchmark returns for decomposition (can be set externally)
        self._benchmark_returns: List[float] = []

        logger.info(
            f"AttributionAnalyzer initialized with ${initial_capital:,.2f} capital, "
            f"{risk_free_rate:.2%} risk-free rate"
        )

    # =========================================================================
    # TRADE MANAGEMENT
    # =========================================================================

    def add_trade(self, trade: TradeRecord) -> None:
        """
        Add a completed trade to the analyzer

        This method should be called after each trade closes to update
        attribution analysis in real-time.

        Args:
            trade: Completed trade record with all metadata
        """
        # Append trade to storage
        self._trades.append(trade)

        # Update equity tracking
        self._current_equity += trade.pnl
        self._equity_curve.append((trade.exit_time, self._current_equity))

        # Update peak equity for drawdown calculation
        if self._current_equity > self._peak_equity:
            self._peak_equity = self._current_equity

        # Invalidate cache
        self._cache_valid = False

        logger.info(
            f"Trade added to attribution: {trade.symbol} {trade.direction.value} "
            f"P&L: ${trade.pnl:+,.2f} ({trade.pnl_pct:+.2%}) "
            f"Strategy: {trade.strategy}"
        )

    def add_trades_batch(self, trades: List[TradeRecord]) -> None:
        """
        Add multiple trades at once (useful for loading historical data)

        Args:
            trades: List of trade records to add
        """
        for trade in trades:
            self._trades.append(trade)
            self._current_equity += trade.pnl
            self._equity_curve.append((trade.exit_time, self._current_equity))
            if self._current_equity > self._peak_equity:
                self._peak_equity = self._current_equity

        self._cache_valid = False
        logger.info(f"Added {len(trades)} trades to attribution analysis")

    def get_trades(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        strategy: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> List[TradeRecord]:
        """
        Get filtered trades from the analyzer

        Args:
            start_time: Filter trades after this time
            end_time: Filter trades before this time
            strategy: Filter by strategy name
            symbol: Filter by trading symbol

        Returns:
            List of matching trade records
        """
        trades = self._trades

        # Apply filters
        if start_time:
            trades = [t for t in trades if t.exit_time >= start_time]
        if end_time:
            trades = [t for t in trades if t.exit_time <= end_time]
        if strategy:
            trades = [t for t in trades if t.strategy == strategy]
        if symbol:
            trades = [t for t in trades if t.symbol == symbol]

        return trades

    # =========================================================================
    # METRICS CALCULATION
    # =========================================================================

    def _calculate_metrics(self, trades: List[TradeRecord]) -> AttributionMetrics:
        """
        Calculate comprehensive metrics for a set of trades

        Args:
            trades: List of trades to analyze

        Returns:
            AttributionMetrics with all calculated values
        """
        if not trades:
            return AttributionMetrics()

        # Basic counts
        trades_count = len(trades)
        winning_trades = [t for t in trades if t.is_winner]
        losing_trades = [t for t in trades if not t.is_winner and t.pnl < 0]

        # P&L calculations
        total_pnl = sum(t.pnl for t in trades)
        gross_profit = sum(t.pnl for t in winning_trades) if winning_trades else 0.0
        gross_loss = abs(sum(t.pnl for t in losing_trades)) if losing_trades else 0.0

        # Win rate calculation
        win_rate = len(winning_trades) / trades_count if trades_count > 0 else 0.0

        # Average win/loss
        avg_win = gross_profit / len(winning_trades) if winning_trades else 0.0
        avg_loss = gross_loss / len(losing_trades) if losing_trades else 0.0

        # Profit factor (gross profit / gross loss)
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        if math.isinf(profit_factor):
            profit_factor = gross_profit if gross_profit > 0 else 0.0

        # Calculate risk-adjusted metrics
        returns = [t.pnl_pct for t in trades]
        sharpe_ratio = self._calculate_sharpe_ratio(returns)
        sortino_ratio = self._calculate_sortino_ratio(returns)
        max_drawdown = self._calculate_max_drawdown(trades)

        # Calmar ratio (return / max drawdown)
        total_return = (
            total_pnl / self.initial_capital if self.initial_capital > 0 else 0.0
        )
        calmar_ratio = total_return / abs(max_drawdown) if max_drawdown != 0 else 0.0

        return AttributionMetrics(
            total_pnl=total_pnl,
            win_rate=win_rate,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            trades_count=trades_count,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
        )

    def _calculate_sharpe_ratio(
        self,
        returns: List[float],
        annualization_factor: float = 252,  # Trading days per year
    ) -> float:
        """
        Calculate Sharpe ratio for a series of returns

        Formula: (Mean Return - Risk Free Rate) / Std Dev of Returns

        Args:
            returns: List of trade returns (as percentages)
            annualization_factor: Factor to annualize returns

        Returns:
            Sharpe ratio value
        """
        if len(returns) < 2:
            return 0.0

        returns_array = np.array(returns)
        mean_return = np.mean(returns_array)
        std_return = np.std(returns_array, ddof=1)  # Use sample std dev

        if std_return == 0:
            return 0.0

        # Convert risk-free rate to per-trade rate (assuming daily trades)
        risk_free_per_trade = self.risk_free_rate / annualization_factor

        # Calculate Sharpe ratio
        sharpe = (mean_return - risk_free_per_trade) / std_return

        # Annualize (multiply by sqrt of trades per year)
        # Assuming approximately 100 trades per year as rough estimate
        trades_per_year = min(len(returns), 100)
        annualized_sharpe = sharpe * np.sqrt(trades_per_year)

        return float(annualized_sharpe)

    def _calculate_sortino_ratio(
        self,
        returns: List[float],
        annualization_factor: float = 252,
    ) -> float:
        """
        Calculate Sortino ratio (only considers downside volatility)

        Formula: (Mean Return - Risk Free Rate) / Downside Std Dev

        Args:
            returns: List of trade returns (as percentages)
            annualization_factor: Factor to annualize returns

        Returns:
            Sortino ratio value
        """
        if len(returns) < 2:
            return 0.0

        returns_array = np.array(returns)
        mean_return = np.mean(returns_array)

        # Calculate downside deviation (only negative returns)
        downside_returns = returns_array[returns_array < 0]

        if len(downside_returns) == 0:
            return float("inf") if mean_return > 0 else 0.0

        downside_std = np.std(downside_returns, ddof=1)

        if downside_std == 0:
            return 0.0

        # Convert risk-free rate to per-trade rate
        risk_free_per_trade = self.risk_free_rate / annualization_factor

        # Calculate Sortino ratio
        sortino = (mean_return - risk_free_per_trade) / downside_std

        # Annualize
        trades_per_year = min(len(returns), 100)
        annualized_sortino = sortino * np.sqrt(trades_per_year)

        return float(annualized_sortino)

    def _calculate_max_drawdown(self, trades: List[TradeRecord]) -> float:
        """
        Calculate maximum drawdown for a series of trades

        Args:
            trades: List of trades to analyze

        Returns:
            Maximum drawdown as a percentage (negative value)
        """
        if not trades:
            return 0.0

        # Sort trades by exit time
        sorted_trades = sorted(trades, key=lambda t: t.exit_time)

        # Calculate running equity
        equity = self.initial_capital
        peak = equity
        max_drawdown = 0.0

        for trade in sorted_trades:
            equity += trade.pnl
            if equity > peak:
                peak = equity

            drawdown = (equity - peak) / peak if peak > 0 else 0.0
            if drawdown < max_drawdown:
                max_drawdown = drawdown

        return max_drawdown

    # =========================================================================
    # ATTRIBUTION BY DIMENSION
    # =========================================================================

    def get_attribution_by_strategy(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[AttributionResult]:
        """
        Get P&L attribution breakdown by strategy

        Args:
            start_time: Start of analysis period
            end_time: End of analysis period

        Returns:
            List of attribution results, one per strategy
        """
        trades = self.get_trades(start_time=start_time, end_time=end_time)
        return self._calculate_attribution(trades, AttributionDimension.STRATEGY)

    def get_attribution_by_symbol(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[AttributionResult]:
        """
        Get P&L attribution breakdown by symbol

        Args:
            start_time: Start of analysis period
            end_time: End of analysis period

        Returns:
            List of attribution results, one per symbol
        """
        trades = self.get_trades(start_time=start_time, end_time=end_time)
        return self._calculate_attribution(trades, AttributionDimension.SYMBOL)

    def get_attribution_by_direction(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[AttributionResult]:
        """
        Get P&L attribution breakdown by trade direction (Long vs Short)

        Args:
            start_time: Start of analysis period
            end_time: End of analysis period

        Returns:
            List of attribution results for LONG and SHORT
        """
        trades = self.get_trades(start_time=start_time, end_time=end_time)
        return self._calculate_attribution(trades, AttributionDimension.DIRECTION)

    def get_attribution_by_market_condition(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[AttributionResult]:
        """
        Get P&L attribution breakdown by market condition

        Args:
            start_time: Start of analysis period
            end_time: End of analysis period

        Returns:
            List of attribution results for each market condition
        """
        trades = self.get_trades(start_time=start_time, end_time=end_time)
        return self._calculate_attribution(
            trades, AttributionDimension.MARKET_CONDITION
        )

    def _calculate_attribution(
        self,
        trades: List[TradeRecord],
        dimension: AttributionDimension,
    ) -> List[AttributionResult]:
        """
        Calculate attribution for a specific dimension

        Args:
            trades: List of trades to analyze
            dimension: Attribution dimension to group by

        Returns:
            List of attribution results for each unique value
        """
        if not trades:
            return []

        # Group trades by dimension value
        groups: Dict[str, List[TradeRecord]] = defaultdict(list)

        for trade in trades:
            if dimension == AttributionDimension.STRATEGY:
                key = trade.strategy
            elif dimension == AttributionDimension.SYMBOL:
                key = trade.symbol
            elif dimension == AttributionDimension.DIRECTION:
                key = trade.direction.value
            elif dimension == AttributionDimension.MARKET_CONDITION:
                key = trade.market_condition.value
            else:
                key = "unknown"

            groups[key].append(trade)

        # Calculate total P&L for contribution percentages
        total_pnl = sum(t.pnl for t in trades)

        # Calculate metrics for each group
        results = []
        for value, group_trades in groups.items():
            metrics = self._calculate_metrics(group_trades)

            # Calculate contribution percentage
            if total_pnl != 0:
                contribution = metrics.total_pnl / abs(total_pnl) * 100
            else:
                contribution = 0.0

            result = AttributionResult(
                dimension=dimension,
                value=value,
                metrics=metrics,
                contribution_pct=contribution,
                trades=group_trades,
            )
            results.append(result)

        # Sort by total P&L (descending)
        results.sort(key=lambda r: r.metrics.total_pnl, reverse=True)

        return results

    # =========================================================================
    # ATTRIBUTION SUMMARY
    # =========================================================================

    def get_attribution_summary(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> AttributionSummary:
        """
        Get complete attribution summary across all dimensions

        Args:
            start_time: Start of analysis period
            end_time: End of analysis period

        Returns:
            Complete attribution summary with all breakdowns
        """
        trades = self.get_trades(start_time=start_time, end_time=end_time)

        # Calculate overall metrics
        overall_metrics = self._calculate_metrics(trades)

        # Get attribution by each dimension
        by_strategy = self._calculate_attribution(trades, AttributionDimension.STRATEGY)
        by_symbol = self._calculate_attribution(trades, AttributionDimension.SYMBOL)
        by_direction = self._calculate_attribution(
            trades, AttributionDimension.DIRECTION
        )
        by_market_condition = self._calculate_attribution(
            trades, AttributionDimension.MARKET_CONDITION
        )

        # Determine period
        period_start = min(t.entry_time for t in trades) if trades else None
        period_end = max(t.exit_time for t in trades) if trades else None

        return AttributionSummary(
            overall_metrics=overall_metrics,
            by_strategy=by_strategy,
            by_symbol=by_symbol,
            by_direction=by_direction,
            by_market_condition=by_market_condition,
            generated_at=datetime.now(timezone.utc),
            period_start=period_start,
            period_end=period_end,
        )

    # =========================================================================
    # TREND ANALYSIS
    # =========================================================================

    def get_attribution_trends(
        self,
        period: TradePeriod = TradePeriod.DAILY,
        lookback_days: int = 7,
        dimension: AttributionDimension = AttributionDimension.STRATEGY,
    ) -> List[TrendAnalysis]:
        """
        Analyze attribution trends over time periods

        Args:
            period: Time period granularity (hourly, daily, weekly, monthly)
            lookback_days: Number of days to analyze
            dimension: Attribution dimension to analyze

        Returns:
            List of trend analysis for each dimension value
        """
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(days=lookback_days)
        trades = self.get_trades(start_time=start_time)

        if not trades:
            return []

        # Get unique dimension values
        unique_values = set()
        for trade in trades:
            if dimension == AttributionDimension.STRATEGY:
                unique_values.add(trade.strategy)
            elif dimension == AttributionDimension.SYMBOL:
                unique_values.add(trade.symbol)
            elif dimension == AttributionDimension.DIRECTION:
                unique_values.add(trade.direction.value)
            elif dimension == AttributionDimension.MARKET_CONDITION:
                unique_values.add(trade.market_condition.value)

        # Generate periods based on granularity
        periods = self._generate_periods(start_time, now, period)

        # Analyze each dimension value
        trends = []
        for value in unique_values:
            trend = self._analyze_trend(trades, dimension, value, periods, period)
            trends.append(trend)

        # Sort by latest P&L
        trends.sort(key=lambda t: t.pnl_trend[-1] if t.pnl_trend else 0, reverse=True)

        return trends

    def _generate_periods(
        self,
        start_time: datetime,
        end_time: datetime,
        period: TradePeriod,
    ) -> List[Tuple[datetime, datetime, str]]:
        """
        Generate time period boundaries for trend analysis

        Args:
            start_time: Start of analysis period
            end_time: End of analysis period
            period: Period granularity

        Returns:
            List of (period_start, period_end, label) tuples
        """
        periods = []
        current = start_time

        while current < end_time:
            if period == TradePeriod.HOURLY:
                period_end = current + timedelta(hours=1)
                label = current.strftime("%Y-%m-%d %H:00")
            elif period == TradePeriod.DAILY:
                period_end = current + timedelta(days=1)
                label = current.strftime("%Y-%m-%d")
            elif period == TradePeriod.WEEKLY:
                period_end = current + timedelta(weeks=1)
                label = f"Week {current.strftime('%Y-W%W')}"
            elif period == TradePeriod.MONTHLY:
                # Move to first day of next month
                if current.month == 12:
                    period_end = current.replace(year=current.year + 1, month=1, day=1)
                else:
                    period_end = current.replace(month=current.month + 1, day=1)
                label = current.strftime("%Y-%m")
            else:
                period_end = current + timedelta(days=1)
                label = current.strftime("%Y-%m-%d")

            periods.append((current, min(period_end, end_time), label))
            current = period_end

        return periods

    def _analyze_trend(
        self,
        trades: List[TradeRecord],
        dimension: AttributionDimension,
        value: str,
        periods: List[Tuple[datetime, datetime, str]],
        period_type: TradePeriod,
    ) -> TrendAnalysis:
        """
        Analyze trend for a specific dimension value

        Args:
            trades: All trades in the analysis period
            dimension: Attribution dimension
            value: Dimension value to analyze
            periods: Time period boundaries
            period_type: Period granularity type

        Returns:
            Trend analysis for the dimension value
        """
        # Filter trades by dimension value
        if dimension == AttributionDimension.STRATEGY:
            filtered_trades = [t for t in trades if t.strategy == value]
        elif dimension == AttributionDimension.SYMBOL:
            filtered_trades = [t for t in trades if t.symbol == value]
        elif dimension == AttributionDimension.DIRECTION:
            filtered_trades = [t for t in trades if t.direction.value == value]
        elif dimension == AttributionDimension.MARKET_CONDITION:
            filtered_trades = [t for t in trades if t.market_condition.value == value]
        else:
            filtered_trades = trades

        # Calculate metrics for each period
        period_labels = []
        pnl_trend = []
        win_rate_trend = []
        trades_count_trend = []

        for period_start, period_end, label in periods:
            # Get trades in this period
            period_trades = [
                t for t in filtered_trades if period_start <= t.exit_time < period_end
            ]

            period_labels.append(label)

            if period_trades:
                total_pnl = sum(t.pnl for t in period_trades)
                win_rate = len([t for t in period_trades if t.is_winner]) / len(
                    period_trades
                )
                trades_count = len(period_trades)
            else:
                total_pnl = 0.0
                win_rate = 0.0
                trades_count = 0

            pnl_trend.append(total_pnl)
            win_rate_trend.append(win_rate)
            trades_count_trend.append(trades_count)

        # Calculate moving average (3-period)
        moving_avg = self._calculate_moving_average(pnl_trend, window=3)

        # Determine trend direction
        trend_direction = self._determine_trend_direction(moving_avg)

        return TrendAnalysis(
            dimension=dimension,
            value=value,
            periods=period_labels,
            pnl_trend=pnl_trend,
            win_rate_trend=win_rate_trend,
            trades_count_trend=trades_count_trend,
            moving_avg_pnl=moving_avg,
            trend_direction=trend_direction,
        )

    def _calculate_moving_average(
        self,
        values: List[float],
        window: int = 3,
    ) -> List[float]:
        """
        Calculate simple moving average

        Args:
            values: List of values
            window: Moving average window size

        Returns:
            List of moving average values
        """
        if len(values) < window:
            return values.copy()

        moving_avg = []
        for i in range(len(values)):
            start_idx = max(0, i - window + 1)
            avg = sum(values[start_idx : i + 1]) / (i - start_idx + 1)
            moving_avg.append(avg)

        return moving_avg

    def _determine_trend_direction(
        self,
        moving_avg: List[float],
        threshold: float = 0.1,
    ) -> str:
        """
        Determine overall trend direction from moving average

        Args:
            moving_avg: Moving average values
            threshold: Minimum slope to consider a trend

        Returns:
            "up", "down", or "flat"
        """
        if len(moving_avg) < 2:
            return "flat"

        # Calculate average slope over recent periods
        recent_values = moving_avg[-min(5, len(moving_avg)) :]
        if len(recent_values) < 2:
            return "flat"

        # Simple linear regression slope
        n = len(recent_values)
        x_mean = (n - 1) / 2
        y_mean = sum(recent_values) / n

        numerator = sum(
            (i - x_mean) * (y - y_mean) for i, y in enumerate(recent_values)
        )
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return "flat"

        slope = numerator / denominator

        # Normalize slope relative to mean
        if y_mean != 0:
            normalized_slope = slope / abs(y_mean)
        else:
            normalized_slope = slope

        if normalized_slope > threshold:
            return "up"
        elif normalized_slope < -threshold:
            return "down"
        else:
            return "flat"

    # =========================================================================
    # PERFORMANCE DECOMPOSITION
    # =========================================================================

    def get_performance_decomposition(
        self,
        benchmark_returns: Optional[List[float]] = None,
    ) -> List[PerformanceDecomposition]:
        """
        Decompose performance into Alpha, Beta, and Residual components

        Args:
            benchmark_returns: Market benchmark returns (if not provided, uses BTC)

        Returns:
            List of performance decompositions, one per strategy
        """
        # Get all unique strategies
        strategies = list(set(t.strategy for t in self._trades))

        if not strategies:
            return []

        # Use provided benchmark or stored benchmark
        if benchmark_returns:
            self._benchmark_returns = benchmark_returns

        decompositions = []
        for strategy in strategies:
            decomposition = self._calculate_decomposition(strategy)
            decompositions.append(decomposition)

        # Sort by alpha (highest first)
        decompositions.sort(key=lambda d: d.alpha, reverse=True)

        return decompositions

    def set_benchmark_returns(self, returns: List[float]) -> None:
        """
        Set benchmark returns for performance decomposition

        Args:
            returns: List of benchmark returns (matching trade periods)
        """
        self._benchmark_returns = returns
        logger.info(f"Set {len(returns)} benchmark returns for decomposition")

    def _calculate_decomposition(self, strategy: str) -> PerformanceDecomposition:
        """
        Calculate performance decomposition for a single strategy

        Uses simple linear regression to decompose returns into:
        - Alpha (intercept): Strategy-specific skill
        - Beta (slope): Market sensitivity
        - Residual: Unexplained variance

        Args:
            strategy: Strategy name

        Returns:
            Performance decomposition for the strategy
        """
        # Get strategy trades
        strategy_trades = [t for t in self._trades if t.strategy == strategy]

        if not strategy_trades:
            return PerformanceDecomposition(strategy=strategy)

        # Calculate strategy returns
        strategy_returns = [t.pnl_pct for t in strategy_trades]
        total_return = sum(strategy_returns)

        # If no benchmark, return simple metrics
        if not self._benchmark_returns or len(self._benchmark_returns) < len(
            strategy_returns
        ):
            return PerformanceDecomposition(
                strategy=strategy,
                alpha=total_return / len(strategy_returns) if strategy_returns else 0.0,
                beta=0.0,
                residual=0.0,
                r_squared=0.0,
                total_return=total_return,
                benchmark_return=0.0,
                information_ratio=0.0,
            )

        # Align benchmark returns with strategy trades
        # (simplified - assumes benchmark aligns with trade exits)
        benchmark = self._benchmark_returns[: len(strategy_returns)]

        # Calculate regression (Alpha and Beta)
        strategy_arr = np.array(strategy_returns)
        benchmark_arr = np.array(benchmark)

        if len(benchmark_arr) < 2 or np.std(benchmark_arr) == 0:
            return PerformanceDecomposition(
                strategy=strategy,
                alpha=np.mean(strategy_arr),
                beta=0.0,
                residual=0.0,
                r_squared=0.0,
                total_return=total_return,
                benchmark_return=sum(benchmark),
                information_ratio=0.0,
            )

        # Linear regression: strategy_return = alpha + beta * benchmark_return
        cov_matrix = np.cov(strategy_arr, benchmark_arr)
        if cov_matrix.ndim < 2:
            beta = 0.0
        else:
            beta = (
                cov_matrix[0, 1] / np.var(benchmark_arr)
                if np.var(benchmark_arr) > 0
                else 0.0
            )

        alpha = np.mean(strategy_arr) - beta * np.mean(benchmark_arr)

        # Calculate R-squared
        predicted = alpha + beta * benchmark_arr
        ss_res = np.sum((strategy_arr - predicted) ** 2)
        ss_tot = np.sum((strategy_arr - np.mean(strategy_arr)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        # Residual (tracking error)
        residual = np.std(strategy_arr - predicted)

        # Information ratio (excess return / tracking error)
        excess_return = np.mean(strategy_arr) - np.mean(benchmark_arr)
        information_ratio = excess_return / residual if residual > 0 else 0.0

        return PerformanceDecomposition(
            strategy=strategy,
            alpha=float(alpha),
            beta=float(beta),
            residual=float(residual),
            r_squared=float(r_squared),
            total_return=total_return,
            benchmark_return=sum(benchmark),
            information_ratio=float(information_ratio),
        )

    # =========================================================================
    # MARKET CONDITION CLASSIFICATION
    # =========================================================================

    @staticmethod
    def classify_market_condition(
        price_changes: List[float],
        volatility_threshold: float = 0.02,
        trend_threshold: float = 0.6,
    ) -> MarketCondition:
        """
        Classify market condition based on price changes

        Args:
            price_changes: List of price change percentages
            volatility_threshold: Threshold for high volatility
            trend_threshold: Ratio of same-direction moves to consider trending

        Returns:
            Classified market condition
        """
        if not price_changes:
            return MarketCondition.UNKNOWN

        # Calculate volatility
        volatility = np.std(price_changes)

        # Count direction changes
        up_moves = sum(1 for c in price_changes if c > 0)
        down_moves = sum(1 for c in price_changes if c < 0)
        total_moves = len(price_changes)

        # Check for high volatility
        if volatility > volatility_threshold:
            return MarketCondition.VOLATILE

        # Check for trending
        up_ratio = up_moves / total_moves if total_moves > 0 else 0
        down_ratio = down_moves / total_moves if total_moves > 0 else 0

        if up_ratio >= trend_threshold:
            return MarketCondition.TRENDING_UP
        elif down_ratio >= trend_threshold:
            return MarketCondition.TRENDING_DOWN
        else:
            return MarketCondition.RANGING

    # =========================================================================
    # REPORTING
    # =========================================================================

    def generate_daily_report(self) -> Dict[str, Any]:
        """
        Generate daily attribution report

        Returns:
            Dictionary containing comprehensive daily report
        """
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Get today's trades
        today_trades = self.get_trades(start_time=today_start)

        # Get summary for today
        summary = self.get_attribution_summary(start_time=today_start)

        # Get decomposition
        decomposition = self.get_performance_decomposition()

        # Build report
        report = {
            "date": now.strftime("%Y-%m-%d"),
            "generated_at": now.isoformat(),
            "trades_today": len(today_trades),
            "overall_pnl": summary.overall_metrics.total_pnl,
            "win_rate": summary.overall_metrics.win_rate,
            "summary": summary.to_dict(),
            "performance_decomposition": [d.to_dict() for d in decomposition],
            "top_strategies": [r.to_dict() for r in summary.by_strategy[:3]]
            if summary.by_strategy
            else [],
            "top_symbols": [r.to_dict() for r in summary.by_symbol[:3]]
            if summary.by_symbol
            else [],
            "current_equity": self._current_equity,
            "peak_equity": self._peak_equity,
            "current_drawdown": (self._current_equity - self._peak_equity)
            / self._peak_equity
            if self._peak_equity > 0
            else 0.0,
        }

        logger.info(
            f"Generated daily attribution report for {now.strftime('%Y-%m-%d')}"
        )
        return report

    # =========================================================================
    # PERSISTENCE HELPERS
    # =========================================================================

    def get_state(self) -> Dict[str, Any]:
        """
        Get current analyzer state for persistence

        Returns:
            Dictionary containing analyzer state
        """
        return {
            "initial_capital": self.initial_capital,
            "risk_free_rate": self.risk_free_rate,
            "current_equity": self._current_equity,
            "peak_equity": self._peak_equity,
            "trades_count": len(self._trades),
            "trades": [t.to_dict() for t in self._trades],
            "equity_curve": [
                {"timestamp": ts.isoformat(), "equity": eq}
                for ts, eq in self._equity_curve
            ],
            "benchmark_returns": self._benchmark_returns,
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        """
        Load analyzer state from persistence

        Args:
            state: State dictionary from get_state()
        """
        if "initial_capital" not in state:
            raise ValueError(
                "Attribution state is missing 'initial_capital' — refusing to "
                "guess an account size. State produced by get_state() always "
                "carries it; a missing key means the state is corrupt."
            )
        self.initial_capital = float(state["initial_capital"])
        self.risk_free_rate = state.get("risk_free_rate", 0.02)
        self._current_equity = state.get("current_equity", self.initial_capital)
        self._peak_equity = state.get("peak_equity", self.initial_capital)
        self._benchmark_returns = state.get("benchmark_returns", [])

        # Reconstruct trades
        self._trades = []
        for trade_dict in state.get("trades", []):
            trade = TradeRecord(
                trade_id=trade_dict["trade_id"],
                symbol=trade_dict["symbol"],
                strategy=trade_dict["strategy"],
                direction=TradeDirection(trade_dict["direction"]),
                entry_time=datetime.fromisoformat(trade_dict["entry_time"]),
                exit_time=datetime.fromisoformat(trade_dict["exit_time"]),
                entry_price=trade_dict["entry_price"],
                exit_price=trade_dict["exit_price"],
                quantity=trade_dict["quantity"],
                pnl=trade_dict["pnl"],
                pnl_pct=trade_dict["pnl_pct"],
                fees=trade_dict.get("fees", 0.0),
                market_condition=MarketCondition(
                    trade_dict.get("market_condition", "unknown")
                ),
                metadata=trade_dict.get("metadata", {}),
            )
            self._trades.append(trade)

        # Reconstruct equity curve
        self._equity_curve = []
        for point in state.get("equity_curve", []):
            ts = datetime.fromisoformat(point["timestamp"])
            eq = point["equity"]
            self._equity_curve.append((ts, eq))

        self._cache_valid = False
        logger.info(f"Loaded attribution state with {len(self._trades)} trades")

    def reset(self) -> None:
        """Reset analyzer to initial state"""
        self._trades = []
        self._equity_curve = []
        self._peak_equity = self.initial_capital
        self._current_equity = self.initial_capital
        self._benchmark_returns = []
        self._attribution_cache = {}
        self._cache_valid = False
        logger.info("Attribution analyzer reset to initial state")


# =============================================================================
# GLOBAL INSTANCE MANAGEMENT
# =============================================================================

# Global analyzer instance
_attribution_analyzer: Optional[AttributionAnalyzer] = None


def get_attribution_analyzer(
    initial_capital: Optional[float] = None,
) -> AttributionAnalyzer:
    """
    Get or create the global attribution analyzer instance

    Args:
        initial_capital: Initial capital (only used if creating new instance)

    Returns:
        Global AttributionAnalyzer instance
    """
    global _attribution_analyzer

    if _attribution_analyzer is None:
        # `is None` check, NOT `or`: an explicit capital of 0.0 must not be
        # silently replaced by a fallback (the falsy-fallback bug, AUDIT §2.5).
        capital = (
            get_settings().paper_initial_balance
            if initial_capital is None
            else initial_capital
        )
        _attribution_analyzer = AttributionAnalyzer(initial_capital=capital)
        logger.info(f"Created new AttributionAnalyzer with ${capital:,.2f} capital")

    return _attribution_analyzer


def reset_attribution_analyzer() -> None:
    """Reset the global attribution analyzer instance"""
    global _attribution_analyzer
    _attribution_analyzer = None
    logger.info("Global attribution analyzer reset")
