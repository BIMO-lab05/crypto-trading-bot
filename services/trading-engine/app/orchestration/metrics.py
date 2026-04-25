"""
Strategy Metrics
=================
Purpose: Per-strategy performance tracking and comparative analytics

The Strategy Metrics module provides comprehensive performance tracking:
1. Per-strategy performance metrics (win rate, PnL, Sharpe, etc.)
2. Comparative metrics across strategies
3. Correlation analysis between strategies
4. Auto-pause logic for underperforming strategies
5. Attribution analysis for portfolio returns

Phase 9: Multi-Strategy Orchestration Engine
Author: Backend Developer Agent
Date: 2025-12-11
"""

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from threading import RLock
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import deque
import math
import statistics

from app.orchestration.models import (
    StrategyPerformanceMetrics,
    StrategyState,
    StrategyStatus,
    StrategyConfig,
)

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# TRADE RECORD FOR METRICS
# =============================================================================

@dataclass
class MetricsTrade:
    """
    Record of a completed trade for metrics calculation

    Contains essential trade data for performance analysis.
    """
    trade_id: str
    strategy_id: str
    symbol: str
    side: str  # LONG or SHORT
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float  # Absolute PnL
    pnl_pct: float  # Percentage PnL
    fees: float = 0.0
    slippage: float = 0.0

    @property
    def is_winner(self) -> bool:
        """Check if trade was profitable"""
        return self.pnl > 0

    @property
    def hold_time_hours(self) -> float:
        """Calculate hold time in hours"""
        return (self.exit_time - self.entry_time).total_seconds() / 3600

    @property
    def gross_pnl(self) -> float:
        """PnL before fees and slippage"""
        return self.pnl + self.fees + self.slippage

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "trade_id": self.trade_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "side": self.side,
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat(),
            "pnl": self.pnl,
            "pnl_pct": self.pnl_pct,
            "is_winner": self.is_winner,
        }


# =============================================================================
# STRATEGY METRICS CONFIG
# =============================================================================

@dataclass
class StrategyMetricsConfig:
    """
    Configuration for Strategy Metrics

    Controls metric calculation, auto-pause thresholds, and correlation analysis.
    """
    # Rolling window sizes
    trade_history_limit: int = 500  # Max trades to keep per strategy
    daily_return_lookback: int = 30  # Days for daily return calculations
    correlation_lookback_days: int = 30  # Days for correlation calculation

    # Sharpe ratio calculation
    risk_free_rate_annual: float = 0.05  # 5% annual risk-free rate
    trading_days_per_year: int = 365  # Crypto trades 24/7

    # Auto-pause thresholds
    auto_pause_enabled: bool = True
    auto_pause_min_trades: int = 20  # Min trades before auto-pause kicks in
    auto_pause_max_drawdown_pct: float = 15.0  # Pause at 15% drawdown
    auto_pause_max_consecutive_losses: int = 5  # Pause after 5 losses
    auto_pause_min_sharpe: float = -0.5  # Pause if Sharpe below -0.5
    auto_pause_min_win_rate: float = 0.35  # Pause if win rate below 35%
    auto_pause_cooldown_hours: int = 24  # Cooldown after auto-pause

    # Underperformer detection
    underperformer_sharpe_threshold: float = 0.0  # Below 0 = underperforming
    underperformer_profit_factor_threshold: float = 1.0  # Below 1 = losing money

    # Correlation thresholds
    high_correlation_threshold: float = 0.7  # High correlation
    negative_correlation_threshold: float = -0.3  # Diversifying

    # Metric refresh intervals
    metrics_refresh_interval_seconds: int = 60

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "trade_history_limit": self.trade_history_limit,
            "auto_pause_enabled": self.auto_pause_enabled,
            "auto_pause_max_drawdown_pct": self.auto_pause_max_drawdown_pct,
            "auto_pause_min_sharpe": self.auto_pause_min_sharpe,
            "correlation_lookback_days": self.correlation_lookback_days,
        }


# =============================================================================
# STRATEGY METRICS TRACKER
# =============================================================================

class StrategyMetrics:
    """
    Strategy Performance Metrics Tracker

    Provides comprehensive performance tracking for trading strategies:

    1. Per-Strategy Metrics:
       - Win rate and trade statistics
       - PnL (total, daily, unrealized)
       - Drawdown tracking
       - Risk-adjusted returns (Sharpe, Sortino, Calmar)
       - Kelly fraction for optimal sizing

    2. Comparative Analytics:
       - Cross-strategy performance comparison
       - Ranking by various metrics
       - Relative performance vs benchmark

    3. Correlation Analysis:
       - Strategy return correlations
       - Diversification scoring
       - Optimal allocation hints

    4. Auto-Pause Logic:
       - Automatic detection of underperformers
       - Drawdown-based pausing
       - Consecutive loss triggers
       - Sharpe/win rate thresholds

    5. Attribution Analysis:
       - Portfolio return decomposition
       - Strategy contribution to returns
       - Risk contribution analysis

    Usage:
        config = StrategyMetricsConfig()
        tracker = StrategyMetrics(config)

        # Record trade
        tracker.record_trade(MetricsTrade(...))

        # Get strategy metrics
        metrics = tracker.get_strategy_metrics("trend_following")

        # Compare strategies
        comparison = tracker.compare_strategies()

        # Check for auto-pause
        should_pause = tracker.should_auto_pause("trend_following")

        # Get correlations
        correlations = tracker.get_correlations()
    """

    def __init__(self, config: Optional[StrategyMetricsConfig] = None):
        """
        Initialize Strategy Metrics Tracker

        Args:
            config: Metrics configuration
        """
        self.config = config or StrategyMetricsConfig()
        self._lock = RLock()

        # Trade history per strategy
        self._trade_history: Dict[str, deque] = {}

        # Daily returns for Sharpe calculation
        self._daily_returns: Dict[str, List[Tuple[datetime, float]]] = {}

        # Cached metrics
        self._cached_metrics: Dict[str, StrategyPerformanceMetrics] = {}
        self._cache_timestamps: Dict[str, datetime] = {}

        # Running state per strategy
        self._strategy_states: Dict[str, Dict[str, Any]] = {}

        # Equity curves for drawdown calculation
        self._equity_curves: Dict[str, List[Tuple[datetime, float]]] = {}

        # Portfolio-level tracking
        self._portfolio_trades: deque = deque(maxlen=self.config.trade_history_limit)
        self._portfolio_daily_returns: List[Tuple[datetime, float]] = []

        logger.info(
            f"StrategyMetrics initialized: "
            f"history_limit={self.config.trade_history_limit}, "
            f"auto_pause={self.config.auto_pause_enabled}"
        )

    # =========================================================================
    # TRADE RECORDING
    # =========================================================================

    def record_trade(self, trade: MetricsTrade) -> Dict[str, Any]:
        """
        Record a completed trade for metrics

        Args:
            trade: Completed trade record

        Returns:
            Recording result with updated metrics summary
        """
        with self._lock:
            strategy_id = trade.strategy_id

            # Initialize strategy storage if needed
            if strategy_id not in self._trade_history:
                self._trade_history[strategy_id] = deque(maxlen=self.config.trade_history_limit)
                self._daily_returns[strategy_id] = []
                self._equity_curves[strategy_id] = []
                self._strategy_states[strategy_id] = {
                    "total_trades": 0,
                    "winning_trades": 0,
                    "losing_trades": 0,
                    "consecutive_wins": 0,
                    "consecutive_losses": 0,
                    "total_pnl": 0.0,
                    "peak_equity": 0.0,
                    "max_drawdown_pct": 0.0,
                }

            # Add to history
            self._trade_history[strategy_id].append(trade)
            self._portfolio_trades.append(trade)

            # Update running state
            state = self._strategy_states[strategy_id]
            state["total_trades"] += 1

            if trade.is_winner:
                state["winning_trades"] += 1
                if state.get("last_trade_winner", True):
                    state["consecutive_wins"] += 1
                else:
                    state["consecutive_wins"] = 1
                state["consecutive_losses"] = 0
                state["last_trade_winner"] = True
            else:
                state["losing_trades"] += 1
                if not state.get("last_trade_winner", False):
                    state["consecutive_losses"] += 1
                else:
                    state["consecutive_losses"] = 1
                state["consecutive_wins"] = 0
                state["last_trade_winner"] = False

            state["total_pnl"] += trade.pnl

            # Update equity curve
            current_equity = state["total_pnl"]
            self._equity_curves[strategy_id].append((trade.exit_time, current_equity))

            # Update peak and drawdown
            if current_equity > state["peak_equity"]:
                state["peak_equity"] = current_equity

            if state["peak_equity"] > 0:
                current_dd = (state["peak_equity"] - current_equity) / state["peak_equity"] * 100
                if current_dd > state["max_drawdown_pct"]:
                    state["max_drawdown_pct"] = current_dd

            # Update daily returns
            trade_date = trade.exit_time.date()
            self._update_daily_return(strategy_id, trade_date, trade.pnl_pct)

            # Invalidate cache
            self._cached_metrics.pop(strategy_id, None)

            logger.debug(
                f"Recorded trade for {strategy_id}: "
                f"{'WIN' if trade.is_winner else 'LOSS'} {trade.pnl_pct:+.2f}%, "
                f"Total PnL: ${state['total_pnl']:.2f}"
            )

            return {
                "success": True,
                "strategy_id": strategy_id,
                "trade_count": state["total_trades"],
                "win_rate": state["winning_trades"] / state["total_trades"] if state["total_trades"] > 0 else 0,
                "total_pnl": state["total_pnl"],
                "current_drawdown_pct": self._calculate_current_drawdown(strategy_id),
            }

    def _update_daily_return(
        self,
        strategy_id: str,
        trade_date: datetime,
        pnl_pct: float
    ) -> None:
        """Update daily return tracking"""
        returns = self._daily_returns[strategy_id]

        # Check if we have an entry for this date
        if returns and returns[-1][0].date() == trade_date:
            # Update existing entry
            existing_date, existing_return = returns[-1]
            returns[-1] = (existing_date, existing_return + pnl_pct)
        else:
            # Add new entry
            returns.append((datetime.combine(trade_date, datetime.min.time()), pnl_pct))

        # Trim to lookback period
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.config.daily_return_lookback)
        self._daily_returns[strategy_id] = [
            (d, r) for d, r in returns if d.replace(tzinfo=timezone.utc) > cutoff
        ]

    def _calculate_current_drawdown(self, strategy_id: str) -> float:
        """Calculate current drawdown percentage"""
        state = self._strategy_states.get(strategy_id, {})
        peak = state.get("peak_equity", 0.0)
        current = state.get("total_pnl", 0.0)

        if peak <= 0:
            return 0.0

        return max(0.0, (peak - current) / peak * 100)

    # =========================================================================
    # METRICS CALCULATION
    # =========================================================================

    def get_strategy_metrics(
        self,
        strategy_id: str,
        force_recalculate: bool = False
    ) -> Optional[StrategyPerformanceMetrics]:
        """
        Get comprehensive metrics for a strategy

        Args:
            strategy_id: Strategy identifier
            force_recalculate: Force recalculation ignoring cache

        Returns:
            StrategyPerformanceMetrics or None if no data
        """
        with self._lock:
            # Check cache
            if not force_recalculate and strategy_id in self._cached_metrics:
                cache_time = self._cache_timestamps.get(strategy_id)
                if cache_time:
                    age = (datetime.now(timezone.utc) - cache_time).total_seconds()
                    if age < self.config.metrics_refresh_interval_seconds:
                        return self._cached_metrics[strategy_id]

            # Get trade history
            trades = list(self._trade_history.get(strategy_id, []))

            if not trades:
                return None

            # Calculate metrics
            metrics = self._calculate_metrics(strategy_id, trades)

            # Cache result
            self._cached_metrics[strategy_id] = metrics
            self._cache_timestamps[strategy_id] = datetime.now(timezone.utc)

            return metrics

    def _calculate_metrics(
        self,
        strategy_id: str,
        trades: List[MetricsTrade]
    ) -> StrategyPerformanceMetrics:
        """
        Calculate comprehensive metrics from trade history

        Args:
            strategy_id: Strategy identifier
            trades: List of trades

        Returns:
            Calculated StrategyPerformanceMetrics
        """
        # Basic trade statistics
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.is_winner)
        losing_trades = total_trades - winning_trades
        win_rate = winning_trades / total_trades if total_trades > 0 else 0

        # PnL calculations
        wins = [t.pnl for t in trades if t.is_winner]
        losses = [abs(t.pnl) for t in trades if not t.is_winner]

        gross_profit = sum(wins) if wins else 0.0
        gross_loss = sum(losses) if losses else 0.0
        total_pnl = gross_profit - gross_loss

        avg_win = statistics.mean(wins) if wins else 0.0
        avg_loss = statistics.mean(losses) if losses else 0.0
        avg_trade = total_pnl / total_trades if total_trades > 0 else 0.0

        largest_win = max(wins) if wins else 0.0
        largest_loss = max(losses) if losses else 0.0

        # Profit factor
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Win/loss streaks
        win_streak_max = self._calculate_max_streak(trades, is_win=True)
        loss_streak_max = self._calculate_max_streak(trades, is_win=False)

        # Risk-adjusted returns
        sharpe = self._calculate_sharpe_ratio(strategy_id)
        sortino = self._calculate_sortino_ratio(strategy_id)

        # Drawdown metrics
        state = self._strategy_states.get(strategy_id, {})
        max_drawdown_pct = state.get("max_drawdown_pct", 0.0)
        max_dd_duration = self._calculate_max_drawdown_duration(strategy_id)

        # Calmar ratio (annual return / max drawdown)
        annual_return = self._estimate_annual_return(strategy_id)
        calmar = annual_return / max_drawdown_pct if max_drawdown_pct > 0 else 0.0

        # Kelly fraction
        kelly = self._calculate_kelly_fraction(win_rate, avg_win, avg_loss)

        # Hold time statistics
        hold_times = [t.hold_time_hours for t in trades]
        avg_hold_time = statistics.mean(hold_times) if hold_times else 0.0

        # Trade frequency
        if len(trades) >= 2:
            date_range = (trades[-1].exit_time - trades[0].entry_time).days
            avg_trades_per_day = total_trades / max(date_range, 1)
        else:
            avg_trades_per_day = 0.0

        # Determine period
        period_start = trades[0].entry_time if trades else datetime.now(timezone.utc)
        period_end = trades[-1].exit_time if trades else datetime.now(timezone.utc)

        return StrategyPerformanceMetrics(
            strategy_id=strategy_id,
            period_start=period_start,
            period_end=period_end,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_pnl=total_pnl,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_trade=avg_trade,
            largest_win=largest_win,
            largest_loss=largest_loss,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown_pct=max_drawdown_pct,
            max_drawdown_duration_hours=max_dd_duration,
            calmar_ratio=calmar,
            win_streak_max=win_streak_max,
            loss_streak_max=loss_streak_max,
            kelly_fraction=kelly,
            avg_hold_time_hours=avg_hold_time,
            avg_trades_per_day=avg_trades_per_day,
        )

    def _calculate_sharpe_ratio(self, strategy_id: str) -> float:
        """
        Calculate Sharpe ratio for a strategy

        Sharpe = (Mean Return - Risk Free) / Std Dev Return
        """
        returns = self._daily_returns.get(strategy_id, [])

        if len(returns) < 5:  # Need minimum data
            return 0.0

        daily_returns = [r for _, r in returns]

        mean_return = statistics.mean(daily_returns)
        std_return = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0

        if std_return <= 0:
            return 0.0

        # Daily risk-free rate
        daily_rf = self.config.risk_free_rate_annual / self.config.trading_days_per_year

        # Daily Sharpe
        daily_sharpe = (mean_return - daily_rf) / std_return

        # Annualize
        annual_sharpe = daily_sharpe * math.sqrt(self.config.trading_days_per_year)

        return annual_sharpe

    def _calculate_sortino_ratio(self, strategy_id: str) -> float:
        """
        Calculate Sortino ratio (uses downside deviation)

        Sortino = (Mean Return - Risk Free) / Downside Deviation
        """
        returns = self._daily_returns.get(strategy_id, [])

        if len(returns) < 5:
            return 0.0

        daily_returns = [r for _, r in returns]
        mean_return = statistics.mean(daily_returns)

        # Downside deviation (only negative returns)
        negative_returns = [r for r in daily_returns if r < 0]
        if not negative_returns:
            return float('inf') if mean_return > 0 else 0.0

        downside_dev = math.sqrt(
            sum(r ** 2 for r in negative_returns) / len(negative_returns)
        )

        if downside_dev <= 0:
            return 0.0

        daily_rf = self.config.risk_free_rate_annual / self.config.trading_days_per_year
        daily_sortino = (mean_return - daily_rf) / downside_dev

        return daily_sortino * math.sqrt(self.config.trading_days_per_year)

    def _calculate_max_streak(
        self,
        trades: List[MetricsTrade],
        is_win: bool
    ) -> int:
        """Calculate maximum win or loss streak"""
        max_streak = 0
        current_streak = 0

        for trade in trades:
            if trade.is_winner == is_win:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0

        return max_streak

    def _calculate_max_drawdown_duration(self, strategy_id: str) -> float:
        """Calculate maximum drawdown duration in hours"""
        equity_curve = self._equity_curves.get(strategy_id, [])

        if len(equity_curve) < 2:
            return 0.0

        peak_time = equity_curve[0][0]
        peak_equity = equity_curve[0][1]
        max_duration = 0.0
        in_drawdown = False
        drawdown_start = None

        for timestamp, equity in equity_curve:
            if equity >= peak_equity:
                # New peak
                if in_drawdown and drawdown_start:
                    duration = (timestamp - drawdown_start).total_seconds() / 3600
                    max_duration = max(max_duration, duration)
                peak_equity = equity
                peak_time = timestamp
                in_drawdown = False
            else:
                # In drawdown
                if not in_drawdown:
                    drawdown_start = peak_time
                    in_drawdown = True

        # Check if still in drawdown
        if in_drawdown and drawdown_start:
            duration = (datetime.now(timezone.utc) - drawdown_start).total_seconds() / 3600
            max_duration = max(max_duration, duration)

        return max_duration

    def _estimate_annual_return(self, strategy_id: str) -> float:
        """Estimate annualized return"""
        returns = self._daily_returns.get(strategy_id, [])

        if not returns:
            return 0.0

        # Calculate cumulative return
        total_return_pct = sum(r for _, r in returns)

        # Days in data
        days = (returns[-1][0] - returns[0][0]).days if len(returns) > 1 else 1
        days = max(days, 1)

        # Annualize
        annual_return = total_return_pct * (365 / days)

        return annual_return

    def _calculate_kelly_fraction(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float
    ) -> float:
        """
        Calculate Kelly fraction for optimal position sizing

        f* = (bp - q) / b
        where b = avg_win / avg_loss, p = win_rate, q = 1 - p
        """
        if win_rate <= 0 or win_rate >= 1:
            return 0.0
        if avg_loss <= 0:
            return 0.0

        b = avg_win / avg_loss  # Odds
        p = win_rate
        q = 1 - p

        kelly = (b * p - q) / b

        return max(0.0, kelly)

    # =========================================================================
    # COMPARATIVE ANALYTICS
    # =========================================================================

    def compare_strategies(self) -> Dict[str, Any]:
        """
        Compare all strategies across key metrics

        Returns:
            Dictionary with comparative analysis
        """
        with self._lock:
            strategies = list(self._trade_history.keys())

            if not strategies:
                return {"strategies": [], "rankings": {}}

            # Get metrics for all strategies
            all_metrics = {}
            for strategy_id in strategies:
                metrics = self.get_strategy_metrics(strategy_id)
                if metrics:
                    all_metrics[strategy_id] = metrics

            if not all_metrics:
                return {"strategies": [], "rankings": {}}

            # Create rankings
            rankings = {
                "by_sharpe": self._rank_by_metric(all_metrics, "sharpe_ratio", reverse=True),
                "by_win_rate": self._rank_by_metric(all_metrics, "win_rate", reverse=True),
                "by_profit_factor": self._rank_by_metric(all_metrics, "profit_factor", reverse=True),
                "by_total_pnl": self._rank_by_metric(all_metrics, "total_pnl", reverse=True),
                "by_max_drawdown": self._rank_by_metric(all_metrics, "max_drawdown_pct", reverse=False),
                "by_calmar": self._rank_by_metric(all_metrics, "calmar_ratio", reverse=True),
            }

            # Summary statistics
            summary = {
                "total_strategies": len(all_metrics),
                "profitable_strategies": sum(1 for m in all_metrics.values() if m.total_pnl > 0),
                "avg_sharpe": statistics.mean(m.sharpe_ratio for m in all_metrics.values()),
                "avg_win_rate": statistics.mean(m.win_rate for m in all_metrics.values()),
                "best_performer": rankings["by_sharpe"][0] if rankings["by_sharpe"] else None,
                "worst_performer": rankings["by_sharpe"][-1] if rankings["by_sharpe"] else None,
            }

            return {
                "strategies": [m.to_dict() for m in all_metrics.values()],
                "rankings": rankings,
                "summary": summary,
            }

    def _rank_by_metric(
        self,
        metrics: Dict[str, StrategyPerformanceMetrics],
        metric_name: str,
        reverse: bool = True
    ) -> List[str]:
        """Rank strategies by a specific metric"""
        ranked = sorted(
            metrics.keys(),
            key=lambda s: getattr(metrics[s], metric_name, 0),
            reverse=reverse
        )
        return ranked

    def get_best_strategies(
        self,
        metric: str = "sharpe_ratio",
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Get top performing strategies by a metric"""
        comparison = self.compare_strategies()
        rankings = comparison.get("rankings", {})

        ranking_key = f"by_{metric}"
        if ranking_key not in rankings:
            ranking_key = "by_sharpe"

        top_strategies = rankings.get(ranking_key, [])[:limit]

        return [
            {
                "rank": i + 1,
                "strategy_id": sid,
                "metrics": self._cached_metrics.get(sid, {})
            }
            for i, sid in enumerate(top_strategies)
        ]

    # =========================================================================
    # CORRELATION ANALYSIS
    # =========================================================================

    def get_correlations(self) -> Dict[str, Dict[str, float]]:
        """
        Calculate return correlations between strategies

        Returns:
            Correlation matrix as nested dictionary
        """
        with self._lock:
            strategies = list(self._daily_returns.keys())

            if len(strategies) < 2:
                return {}

            correlations = {}

            for s1 in strategies:
                correlations[s1] = {}
                for s2 in strategies:
                    if s1 == s2:
                        correlations[s1][s2] = 1.0
                    else:
                        corr = self._calculate_correlation(s1, s2)
                        correlations[s1][s2] = corr

            return correlations

    def _calculate_correlation(self, strategy_1: str, strategy_2: str) -> float:
        """Calculate return correlation between two strategies"""
        returns_1 = self._daily_returns.get(strategy_1, [])
        returns_2 = self._daily_returns.get(strategy_2, [])

        # Align returns by date
        dates_1 = {r[0].date(): r[1] for r in returns_1}
        dates_2 = {r[0].date(): r[1] for r in returns_2}

        common_dates = set(dates_1.keys()) & set(dates_2.keys())

        if len(common_dates) < 5:
            return 0.0

        aligned_1 = [dates_1[d] for d in sorted(common_dates)]
        aligned_2 = [dates_2[d] for d in sorted(common_dates)]

        # Calculate Pearson correlation
        n = len(aligned_1)
        mean_1 = statistics.mean(aligned_1)
        mean_2 = statistics.mean(aligned_2)

        numerator = sum((a1 - mean_1) * (a2 - mean_2) for a1, a2 in zip(aligned_1, aligned_2))
        denominator = math.sqrt(
            sum((a1 - mean_1) ** 2 for a1 in aligned_1) *
            sum((a2 - mean_2) ** 2 for a2 in aligned_2)
        )

        if denominator == 0:
            return 0.0

        return numerator / denominator

    def get_diversification_score(self) -> Dict[str, Any]:
        """
        Calculate portfolio diversification score based on correlations

        Lower average correlation = better diversification
        """
        correlations = self.get_correlations()

        if not correlations:
            return {"score": 0.0, "interpretation": "Insufficient data"}

        # Calculate average off-diagonal correlation
        off_diagonal = []
        for s1, corrs in correlations.items():
            for s2, corr in corrs.items():
                if s1 != s2:
                    off_diagonal.append(corr)

        if not off_diagonal:
            return {"score": 1.0, "interpretation": "Single strategy"}

        avg_correlation = statistics.mean(off_diagonal)

        # Score: 1.0 = perfectly diversified (correlation = -1)
        # Score: 0.0 = not diversified (correlation = 1)
        score = 1 - (avg_correlation + 1) / 2

        # Interpretation
        if score >= 0.8:
            interpretation = "Excellent diversification"
        elif score >= 0.6:
            interpretation = "Good diversification"
        elif score >= 0.4:
            interpretation = "Moderate diversification"
        else:
            interpretation = "Poor diversification - strategies highly correlated"

        return {
            "score": score,
            "average_correlation": avg_correlation,
            "interpretation": interpretation,
            "highly_correlated_pairs": [
                (s1, s2, corr)
                for s1, corrs in correlations.items()
                for s2, corr in corrs.items()
                if s1 < s2 and corr > self.config.high_correlation_threshold
            ]
        }

    # =========================================================================
    # AUTO-PAUSE LOGIC
    # =========================================================================

    def should_auto_pause(self, strategy_id: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a strategy should be auto-paused

        Args:
            strategy_id: Strategy to check

        Returns:
            Tuple of (should_pause, reason)
        """
        if not self.config.auto_pause_enabled:
            return False, None

        with self._lock:
            state = self._strategy_states.get(strategy_id, {})

            # Check minimum trades requirement
            total_trades = state.get("total_trades", 0)
            if total_trades < self.config.auto_pause_min_trades:
                return False, None  # Not enough data

            # Check drawdown
            current_dd = self._calculate_current_drawdown(strategy_id)
            if current_dd >= self.config.auto_pause_max_drawdown_pct:
                return True, f"Drawdown {current_dd:.1f}% exceeds limit {self.config.auto_pause_max_drawdown_pct}%"

            # Check consecutive losses
            consecutive_losses = state.get("consecutive_losses", 0)
            if consecutive_losses >= self.config.auto_pause_max_consecutive_losses:
                return True, f"Consecutive losses ({consecutive_losses}) exceed limit ({self.config.auto_pause_max_consecutive_losses})"

            # Check Sharpe ratio
            metrics = self.get_strategy_metrics(strategy_id)
            if metrics:
                if metrics.sharpe_ratio < self.config.auto_pause_min_sharpe:
                    return True, f"Sharpe ratio ({metrics.sharpe_ratio:.2f}) below minimum ({self.config.auto_pause_min_sharpe})"

                # Check win rate
                if metrics.win_rate < self.config.auto_pause_min_win_rate:
                    return True, f"Win rate ({metrics.win_rate:.1%}) below minimum ({self.config.auto_pause_min_win_rate:.1%})"

            return False, None

    def get_underperformers(self) -> List[Dict[str, Any]]:
        """
        Get list of underperforming strategies

        Returns:
            List of underperforming strategies with reasons
        """
        with self._lock:
            underperformers = []

            for strategy_id in self._trade_history.keys():
                metrics = self.get_strategy_metrics(strategy_id)
                if not metrics:
                    continue

                reasons = []

                # Check Sharpe
                if metrics.sharpe_ratio < self.config.underperformer_sharpe_threshold:
                    reasons.append(f"Low Sharpe ({metrics.sharpe_ratio:.2f})")

                # Check profit factor
                if metrics.profit_factor < self.config.underperformer_profit_factor_threshold:
                    reasons.append(f"Low profit factor ({metrics.profit_factor:.2f})")

                # Check drawdown
                if metrics.max_drawdown_pct > self.config.auto_pause_max_drawdown_pct * 0.8:
                    reasons.append(f"High drawdown ({metrics.max_drawdown_pct:.1f}%)")

                if reasons:
                    underperformers.append({
                        "strategy_id": strategy_id,
                        "reasons": reasons,
                        "metrics": metrics.to_dict(),
                        "recommendation": "pause" if len(reasons) >= 2 else "monitor"
                    })

            return underperformers

    # =========================================================================
    # ATTRIBUTION ANALYSIS
    # =========================================================================

    def get_portfolio_attribution(self) -> Dict[str, Any]:
        """
        Calculate portfolio return attribution by strategy

        Returns:
            Attribution breakdown
        """
        with self._lock:
            if not self._portfolio_trades:
                return {"total_pnl": 0.0, "by_strategy": {}}

            # Calculate total portfolio PnL
            total_pnl = sum(t.pnl for t in self._portfolio_trades)

            # Attribution by strategy
            by_strategy = {}
            for strategy_id, state in self._strategy_states.items():
                strategy_pnl = state.get("total_pnl", 0.0)
                contribution_pct = (strategy_pnl / total_pnl * 100) if total_pnl != 0 else 0

                by_strategy[strategy_id] = {
                    "pnl": strategy_pnl,
                    "contribution_pct": contribution_pct,
                    "trade_count": state.get("total_trades", 0),
                }

            return {
                "total_pnl": total_pnl,
                "by_strategy": by_strategy,
                "top_contributors": sorted(
                    by_strategy.items(),
                    key=lambda x: x[1]["pnl"],
                    reverse=True
                )[:5]
            }

    # =========================================================================
    # STATE MANAGEMENT
    # =========================================================================

    def get_strategy_summary(self, strategy_id: str) -> Dict[str, Any]:
        """Get summary for a single strategy"""
        with self._lock:
            state = self._strategy_states.get(strategy_id, {})
            metrics = self.get_strategy_metrics(strategy_id)

            return {
                "strategy_id": strategy_id,
                "total_trades": state.get("total_trades", 0),
                "win_rate": state.get("winning_trades", 0) / max(state.get("total_trades", 1), 1),
                "total_pnl": state.get("total_pnl", 0.0),
                "current_drawdown_pct": self._calculate_current_drawdown(strategy_id),
                "max_drawdown_pct": state.get("max_drawdown_pct", 0.0),
                "consecutive_wins": state.get("consecutive_wins", 0),
                "consecutive_losses": state.get("consecutive_losses", 0),
                "sharpe_ratio": metrics.sharpe_ratio if metrics else 0.0,
                "kelly_fraction": metrics.kelly_fraction if metrics else 0.0,
            }

    def get_all_summaries(self) -> Dict[str, Dict[str, Any]]:
        """Get summaries for all strategies"""
        with self._lock:
            return {
                sid: self.get_strategy_summary(sid)
                for sid in self._trade_history.keys()
            }

    def reset_strategy(self, strategy_id: str) -> None:
        """Reset metrics for a single strategy"""
        with self._lock:
            self._trade_history.pop(strategy_id, None)
            self._daily_returns.pop(strategy_id, None)
            self._equity_curves.pop(strategy_id, None)
            self._strategy_states.pop(strategy_id, None)
            self._cached_metrics.pop(strategy_id, None)
            self._cache_timestamps.pop(strategy_id, None)

            logger.info(f"Reset metrics for strategy: {strategy_id}")

    def reset_all(self) -> None:
        """Reset all metrics"""
        with self._lock:
            self._trade_history.clear()
            self._daily_returns.clear()
            self._equity_curves.clear()
            self._strategy_states.clear()
            self._cached_metrics.clear()
            self._cache_timestamps.clear()
            self._portfolio_trades.clear()
            self._portfolio_daily_returns.clear()

            logger.info("Reset all strategy metrics")


# =============================================================================
# GLOBAL INSTANCE MANAGEMENT
# =============================================================================

# Global metrics tracker instance
_strategy_metrics: Optional[StrategyMetrics] = None


def get_strategy_metrics_tracker(
    config: Optional[StrategyMetricsConfig] = None
) -> StrategyMetrics:
    """Get or create global strategy metrics instance"""
    global _strategy_metrics
    if _strategy_metrics is None:
        _strategy_metrics = StrategyMetrics(config)
    return _strategy_metrics


def reset_strategy_metrics_tracker() -> None:
    """Reset global strategy metrics instance"""
    global _strategy_metrics
    _strategy_metrics = None
    logger.info("Strategy metrics tracker instance reset")
