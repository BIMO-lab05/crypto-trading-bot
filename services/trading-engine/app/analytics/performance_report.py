"""
Performance Report Generator - Phase 5.2
Purpose: Generate comprehensive PDF/HTML reports for trading performance

This module provides report generation capabilities including:
- Daily/Weekly/Monthly performance summaries
- Equity curve visualization data
- Drawdown chart data
- Monte Carlo simulation for future performance
- Benchmarking vs BTC/ETH/Market

Author: Backend Developer Agent
Date: 2025-12-12
Version: 1.0
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
import numpy as np

from .advanced_metrics import (
    get_advanced_metrics_calculator,
    AdvancedMetricsCalculator,
    MetricsPeriod,
    TradeMetadata,
)

logger = logging.getLogger(__name__)


@dataclass
class DailyReportData:
    """Data structure for daily report"""
    date: str
    generated_at: str
    # Summary metrics
    total_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    # Performance breakdown
    best_trade_pnl: float = 0.0
    best_trade_symbol: str = ""
    worst_trade_pnl: float = 0.0
    worst_trade_symbol: str = ""
    # By strategy
    strategy_breakdown: List[Dict[str, Any]] = field(default_factory=list)
    # By symbol
    symbol_breakdown: List[Dict[str, Any]] = field(default_factory=list)
    # Equity info
    starting_equity: float = 0.0
    ending_equity: float = 0.0
    daily_return_pct: float = 0.0
    current_drawdown: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "generated_at": self.generated_at,
            "summary": {
                "total_trades": self.total_trades,
                "total_pnl": round(self.total_pnl, 2),
                "win_rate_pct": round(self.win_rate * 100, 2),
                "sharpe_ratio": round(self.sharpe_ratio, 4),
            },
            "best_trade": {
                "pnl": round(self.best_trade_pnl, 2),
                "symbol": self.best_trade_symbol,
            },
            "worst_trade": {
                "pnl": round(self.worst_trade_pnl, 2),
                "symbol": self.worst_trade_symbol,
            },
            "strategy_breakdown": self.strategy_breakdown,
            "symbol_breakdown": self.symbol_breakdown,
            "equity": {
                "starting": round(self.starting_equity, 2),
                "ending": round(self.ending_equity, 2),
                "daily_return_pct": round(self.daily_return_pct, 4),
                "current_drawdown_pct": round(self.current_drawdown * 100, 2),
            },
        }


@dataclass
class MonthlyReportData:
    """Data structure for monthly report"""
    month: str  # YYYY-MM format
    generated_at: str
    # Summary metrics
    total_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    # Weekly breakdown
    weekly_performance: List[Dict[str, Any]] = field(default_factory=list)
    # Strategy performance
    strategy_breakdown: List[Dict[str, Any]] = field(default_factory=list)
    # Symbol performance
    symbol_breakdown: List[Dict[str, Any]] = field(default_factory=list)
    # Equity curve
    equity_curve: List[Tuple[str, float]] = field(default_factory=list)
    # Drawdown curve
    drawdown_curve: List[Tuple[str, float]] = field(default_factory=list)
    # Trade statistics
    avg_trade_duration_hours: float = 0.0
    trades_per_day: float = 0.0
    kelly_percentage: float = 0.0
    # Comparison
    vs_btc_return: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "month": self.month,
            "generated_at": self.generated_at,
            "summary": {
                "total_trades": self.total_trades,
                "total_pnl": round(self.total_pnl, 2),
                "win_rate_pct": round(self.win_rate * 100, 2),
                "sharpe_ratio": round(self.sharpe_ratio, 4),
                "sortino_ratio": round(self.sortino_ratio, 4),
                "calmar_ratio": round(self.calmar_ratio, 4),
                "max_drawdown_pct": round(self.max_drawdown * 100, 2),
                "profit_factor": round(self.profit_factor, 4),
            },
            "weekly_performance": self.weekly_performance,
            "strategy_breakdown": self.strategy_breakdown,
            "symbol_breakdown": self.symbol_breakdown,
            "equity_curve": [{"date": d, "equity": round(e, 2)} for d, e in self.equity_curve],
            "drawdown_curve": [{"date": d, "drawdown": round(dd * 100, 2)} for d, dd in self.drawdown_curve],
            "trade_statistics": {
                "avg_trade_duration_hours": round(self.avg_trade_duration_hours, 2),
                "trades_per_day": round(self.trades_per_day, 2),
                "kelly_percentage": round(self.kelly_percentage * 100, 2),
            },
            "benchmark_comparison": {
                "vs_btc_return_pct": round(self.vs_btc_return * 100, 2),
                "alpha": round(self.alpha, 4),
                "beta": round(self.beta, 4),
            },
        }


@dataclass
class MonteCarloResult:
    """Results from Monte Carlo simulation"""
    simulations: int = 1000
    horizon_days: int = 30
    # Percentile outcomes
    p5_return: float = 0.0    # 5th percentile (worst case)
    p25_return: float = 0.0   # 25th percentile
    p50_return: float = 0.0   # Median outcome
    p75_return: float = 0.0   # 75th percentile
    p95_return: float = 0.0   # 95th percentile (best case)
    # Expected
    expected_return: float = 0.0
    std_dev: float = 0.0
    # Risk
    prob_profit: float = 0.0
    prob_loss_10pct: float = 0.0
    prob_loss_20pct: float = 0.0
    # VaR
    var_95: float = 0.0
    cvar_95: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameters": {
                "simulations": self.simulations,
                "horizon_days": self.horizon_days,
            },
            "percentile_outcomes": {
                "p5_return_pct": round(self.p5_return * 100, 2),
                "p25_return_pct": round(self.p25_return * 100, 2),
                "p50_return_pct": round(self.p50_return * 100, 2),
                "p75_return_pct": round(self.p75_return * 100, 2),
                "p95_return_pct": round(self.p95_return * 100, 2),
            },
            "expected": {
                "expected_return_pct": round(self.expected_return * 100, 2),
                "std_dev_pct": round(self.std_dev * 100, 2),
            },
            "probabilities": {
                "prob_profit_pct": round(self.prob_profit * 100, 2),
                "prob_loss_10pct": round(self.prob_loss_10pct * 100, 2),
                "prob_loss_20pct": round(self.prob_loss_20pct * 100, 2),
            },
            "risk_measures": {
                "var_95_pct": round(self.var_95 * 100, 2),
                "cvar_95_pct": round(self.cvar_95 * 100, 2),
            },
        }


class PerformanceReportGenerator:
    """
    Generates comprehensive performance reports

    Supports daily, weekly, and monthly reports with:
    - Performance summaries
    - Equity curves
    - Drawdown analysis
    - Strategy/symbol breakdowns
    - Monte Carlo projections
    - Benchmark comparisons
    """

    def __init__(
        self,
        calculator: Optional[AdvancedMetricsCalculator] = None,
    ):
        """
        Initialize report generator

        Args:
            calculator: Optional calculator instance (uses global if not provided)
        """
        self._calculator = calculator or get_advanced_metrics_calculator()
        logger.info("PerformanceReportGenerator initialized")

    def generate_daily_report(
        self,
        date: Optional[datetime] = None,
    ) -> DailyReportData:
        """
        Generate daily performance report

        Args:
            date: Date for report (defaults to today)

        Returns:
            DailyReportData with all daily metrics
        """
        if date is None:
            date = datetime.now(timezone.utc)

        # Get date boundaries
        date_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        date_end = date_start + timedelta(days=1)

        # Filter trades for this day
        all_trades = self._calculator._trades
        day_trades = [
            t for t in all_trades
            if date_start <= t.timestamp < date_end
        ]

        # Calculate metrics
        total_pnl = sum(t.pnl for t in day_trades)
        winners = [t for t in day_trades if t.is_winner]
        win_rate = len(winners) / len(day_trades) if day_trades else 0.0

        # Best/worst trade
        best_trade = max(day_trades, key=lambda t: t.pnl) if day_trades else None
        worst_trade = min(day_trades, key=lambda t: t.pnl) if day_trades else None

        # Strategy breakdown
        strategy_stats = self._group_trades_by_dimension(day_trades, "strategy")

        # Symbol breakdown
        symbol_stats = self._group_trades_by_dimension(day_trades, "symbol")

        # Equity calculation
        # Find equity at start of day
        prev_trades = [t for t in all_trades if t.timestamp < date_start]
        starting_equity = self._calculator.initial_capital + sum(t.pnl for t in prev_trades)
        ending_equity = starting_equity + total_pnl
        daily_return = (ending_equity - starting_equity) / starting_equity if starting_equity > 0 else 0.0

        # Current drawdown
        current_dd = 0.0
        if self._calculator._peak_equity > 0:
            current_dd = (self._calculator._current_equity - self._calculator._peak_equity) / self._calculator._peak_equity

        # Calculate Sharpe for the day's trades
        returns = [t.pnl_pct for t in day_trades]
        sharpe = 0.0
        if len(returns) >= 2:
            mean_ret = np.mean(returns)
            std_ret = np.std(returns, ddof=1)
            if std_ret > 0:
                sharpe = mean_ret / std_ret * np.sqrt(252)  # Annualized

        return DailyReportData(
            date=date.strftime("%Y-%m-%d"),
            generated_at=datetime.now(timezone.utc).isoformat(),
            total_trades=len(day_trades),
            total_pnl=total_pnl,
            win_rate=win_rate,
            sharpe_ratio=sharpe,
            best_trade_pnl=best_trade.pnl if best_trade else 0.0,
            best_trade_symbol=best_trade.symbol if best_trade else "",
            worst_trade_pnl=worst_trade.pnl if worst_trade else 0.0,
            worst_trade_symbol=worst_trade.symbol if worst_trade else "",
            strategy_breakdown=strategy_stats,
            symbol_breakdown=symbol_stats,
            starting_equity=starting_equity,
            ending_equity=ending_equity,
            daily_return_pct=daily_return,
            current_drawdown=current_dd,
        )

    def generate_monthly_report(
        self,
        year: int,
        month: int,
    ) -> MonthlyReportData:
        """
        Generate monthly performance report

        Args:
            year: Year for report
            month: Month for report (1-12)

        Returns:
            MonthlyReportData with comprehensive monthly metrics
        """
        from calendar import monthrange

        # Get month boundaries
        month_start = datetime(year, month, 1, tzinfo=timezone.utc)
        _, last_day = monthrange(year, month)
        month_end = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)

        # Filter trades for this month
        all_trades = self._calculator._trades
        month_trades = [
            t for t in all_trades
            if month_start <= t.timestamp <= month_end
        ]

        # Basic metrics
        total_pnl = sum(t.pnl for t in month_trades)
        winners = [t for t in month_trades if t.is_winner]
        losers = [t for t in month_trades if not t.is_winner and t.pnl < 0]
        win_rate = len(winners) / len(month_trades) if month_trades else 0.0

        # Calculate risk-adjusted metrics
        returns = np.array([t.pnl_pct for t in month_trades]) if month_trades else np.array([])

        sharpe = 0.0
        sortino = 0.0
        calmar = 0.0
        max_dd = 0.0
        profit_factor = 0.0
        kelly_pct = 0.0

        if len(returns) >= 2:
            # Sharpe
            mean_ret = np.mean(returns)
            std_ret = np.std(returns, ddof=1)
            if std_ret > 0:
                sharpe = mean_ret / std_ret * np.sqrt(252)

            # Sortino
            downside = returns[returns < 0]
            if len(downside) > 0:
                downside_std = np.std(downside, ddof=1)
                if downside_std > 0:
                    sortino = mean_ret / downside_std * np.sqrt(252)

            # Max drawdown
            cumulative = np.cumprod(1 + returns)
            running_max = np.maximum.accumulate(cumulative)
            drawdowns = (cumulative - running_max) / running_max
            max_dd = np.min(drawdowns)

            # Calmar
            total_return = np.sum(returns)
            if max_dd != 0:
                calmar = total_return / abs(max_dd)

        # Profit factor
        gross_profit = sum(t.pnl for t in winners) if winners else 0.0
        gross_loss = abs(sum(t.pnl for t in losers)) if losers else 0.0
        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss

        # Kelly percentage
        if win_rate > 0 and gross_loss > 0:
            avg_win = gross_profit / len(winners) if winners else 0
            avg_loss = gross_loss / len(losers) if losers else 0
            if avg_loss > 0:
                payoff = avg_win / avg_loss
                kelly_pct = max(0, min((win_rate - (1 - win_rate) / payoff) * 0.5, 0.5))

        # Weekly breakdown
        weekly_perf = self._calculate_weekly_breakdown(month_trades, year, month)

        # Strategy/Symbol breakdown
        strategy_stats = self._group_trades_by_dimension(month_trades, "strategy")
        symbol_stats = self._group_trades_by_dimension(month_trades, "symbol")

        # Equity curve for month
        equity_curve = self._build_equity_curve(month_trades, month_start)

        # Drawdown curve
        drawdown_curve = self._build_drawdown_curve(equity_curve)

        # Trade efficiency
        durations = [t.duration_seconds / 3600 for t in month_trades if t.duration_seconds > 0]
        avg_duration = np.mean(durations) if durations else 0.0
        days_in_month = (month_end - month_start).days + 1
        trades_per_day = len(month_trades) / days_in_month

        # Benchmark comparison (simplified)
        benchmark_comparison = self._calculator.get_benchmark_comparison()

        return MonthlyReportData(
            month=f"{year}-{month:02d}",
            generated_at=datetime.now(timezone.utc).isoformat(),
            total_trades=len(month_trades),
            total_pnl=total_pnl,
            win_rate=win_rate,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_drawdown=max_dd,
            profit_factor=profit_factor,
            weekly_performance=weekly_perf,
            strategy_breakdown=strategy_stats,
            symbol_breakdown=symbol_stats,
            equity_curve=equity_curve,
            drawdown_curve=drawdown_curve,
            avg_trade_duration_hours=avg_duration,
            trades_per_day=trades_per_day,
            kelly_percentage=kelly_pct,
            vs_btc_return=benchmark_comparison.excess_return,
            alpha=benchmark_comparison.alpha,
            beta=benchmark_comparison.beta,
        )

    def run_monte_carlo_simulation(
        self,
        num_simulations: int = 1000,
        horizon_days: int = 30,
        initial_capital: Optional[float] = None,
    ) -> MonteCarloResult:
        """
        Run Monte Carlo simulation for future performance projection

        Args:
            num_simulations: Number of simulation runs
            horizon_days: Investment horizon in days
            initial_capital: Starting capital (uses current equity if not provided)

        Returns:
            MonteCarloResult with percentile outcomes
        """
        capital = initial_capital or self._calculator._current_equity

        # Get historical returns
        returns = np.array(self._calculator._returns)

        if len(returns) < 10:
            logger.warning("Insufficient data for Monte Carlo simulation")
            return MonteCarloResult(
                simulations=num_simulations,
                horizon_days=horizon_days,
            )

        # Calculate daily return statistics
        mean_return = np.mean(returns)
        std_return = np.std(returns, ddof=1)

        # Estimate average trades per day
        if len(self._calculator._trades) >= 2:
            first_trade = min(t.timestamp for t in self._calculator._trades)
            last_trade = max(t.timestamp for t in self._calculator._trades)
            trading_days = max(1, (last_trade - first_trade).days)
            trades_per_day = len(self._calculator._trades) / trading_days
        else:
            trades_per_day = 1.0

        # Run simulations
        final_values = np.zeros(num_simulations)

        for sim in range(num_simulations):
            current_value = capital

            for day in range(horizon_days):
                # Simulate number of trades for this day
                num_trades = max(1, int(np.random.poisson(trades_per_day)))

                for _ in range(num_trades):
                    # Sample return from historical distribution
                    daily_return = np.random.normal(mean_return, std_return)
                    current_value *= (1 + daily_return)

            final_values[sim] = current_value

        # Calculate metrics from simulation results
        final_returns = (final_values - capital) / capital

        return MonteCarloResult(
            simulations=num_simulations,
            horizon_days=horizon_days,
            p5_return=float(np.percentile(final_returns, 5)),
            p25_return=float(np.percentile(final_returns, 25)),
            p50_return=float(np.percentile(final_returns, 50)),
            p75_return=float(np.percentile(final_returns, 75)),
            p95_return=float(np.percentile(final_returns, 95)),
            expected_return=float(np.mean(final_returns)),
            std_dev=float(np.std(final_returns, ddof=1)),
            prob_profit=float(np.mean(final_returns > 0)),
            prob_loss_10pct=float(np.mean(final_returns < -0.10)),
            prob_loss_20pct=float(np.mean(final_returns < -0.20)),
            var_95=float(-np.percentile(final_returns, 5)),  # Positive loss
            cvar_95=float(-np.mean(final_returns[final_returns <= np.percentile(final_returns, 5)])),
        )

    def _group_trades_by_dimension(
        self,
        trades: List[TradeMetadata],
        dimension: str,
    ) -> List[Dict[str, Any]]:
        """Group trades by dimension and calculate stats"""
        from collections import defaultdict

        groups: Dict[str, List[TradeMetadata]] = defaultdict(list)

        for trade in trades:
            if dimension == "strategy":
                key = trade.strategy
            elif dimension == "symbol":
                key = trade.symbol
            else:
                key = "unknown"
            groups[key].append(trade)

        results = []
        total_pnl = sum(t.pnl for t in trades) if trades else 0.0

        for value, group_trades in groups.items():
            pnl = sum(t.pnl for t in group_trades)
            winners = sum(1 for t in group_trades if t.is_winner)

            results.append({
                dimension: value,
                "trades": len(group_trades),
                "pnl": round(pnl, 2),
                "win_rate_pct": round(winners / len(group_trades) * 100, 2) if group_trades else 0.0,
                "contribution_pct": round(pnl / abs(total_pnl) * 100, 2) if total_pnl != 0 else 0.0,
            })

        # Sort by PnL descending
        results.sort(key=lambda x: x["pnl"], reverse=True)

        return results

    def _calculate_weekly_breakdown(
        self,
        trades: List[TradeMetadata],
        year: int,
        month: int,
    ) -> List[Dict[str, Any]]:
        """Calculate weekly performance breakdown"""
        from collections import defaultdict

        weekly: Dict[int, List[TradeMetadata]] = defaultdict(list)

        for trade in trades:
            week_num = trade.timestamp.isocalendar()[1]
            weekly[week_num].append(trade)

        results = []
        for week, week_trades in sorted(weekly.items()):
            pnl = sum(t.pnl for t in week_trades)
            winners = sum(1 for t in week_trades if t.is_winner)

            results.append({
                "week": week,
                "trades": len(week_trades),
                "pnl": round(pnl, 2),
                "win_rate_pct": round(winners / len(week_trades) * 100, 2) if week_trades else 0.0,
            })

        return results

    def _build_equity_curve(
        self,
        trades: List[TradeMetadata],
        start_date: datetime,
    ) -> List[Tuple[str, float]]:
        """Build equity curve from trades"""
        # Find starting equity
        all_trades = self._calculator._trades
        prev_trades = [t for t in all_trades if t.timestamp < start_date]
        starting_equity = self._calculator.initial_capital + sum(t.pnl for t in prev_trades)

        # Sort trades by timestamp
        sorted_trades = sorted(trades, key=lambda t: t.timestamp)

        curve = [(start_date.strftime("%Y-%m-%d"), starting_equity)]
        equity = starting_equity

        for trade in sorted_trades:
            equity += trade.pnl
            curve.append((trade.timestamp.strftime("%Y-%m-%d %H:%M"), equity))

        return curve

    def _build_drawdown_curve(
        self,
        equity_curve: List[Tuple[str, float]],
    ) -> List[Tuple[str, float]]:
        """Build drawdown curve from equity curve"""
        if not equity_curve:
            return []

        drawdown_curve = []
        peak = equity_curve[0][1]

        for date, equity in equity_curve:
            if equity > peak:
                peak = equity
            dd = (equity - peak) / peak if peak > 0 else 0.0
            drawdown_curve.append((date, dd))

        return drawdown_curve


# Global instance
_report_generator: Optional[PerformanceReportGenerator] = None


def get_report_generator(
    calculator: Optional[AdvancedMetricsCalculator] = None,
) -> PerformanceReportGenerator:
    """Get or create global report generator instance"""
    global _report_generator

    if _report_generator is None:
        _report_generator = PerformanceReportGenerator(calculator)

    return _report_generator
