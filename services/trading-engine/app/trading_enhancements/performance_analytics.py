"""
Performance Analytics Engine
Research Source: Sharpe Ratio, Sortino Ratio, Calmar Ratio, VaR, CVaR

Purpose:
- Calculate comprehensive trading performance metrics
- Risk-adjusted return analysis
- Drawdown analysis
- Trade expectancy calculations
- Value at Risk (VaR) and Expected Shortfall (CVaR)

RESEARCH: Professional traders focus on risk-adjusted returns, not raw returns.
Sharpe > 1.0 is good, > 2.0 is excellent. Sortino is better for asymmetric returns.
"""

import logging
import numpy as np
from enum import Enum
from typing import Optional, List, Dict, Tuple, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from collections import deque

logger = logging.getLogger(__name__)


class RiskMetricMethod(Enum):
    """Method for calculating risk metrics"""
    HISTORICAL = "historical"    # Historical simulation
    PARAMETRIC = "parametric"    # Normal distribution assumption
    MONTE_CARLO = "monte_carlo"  # Monte Carlo simulation


@dataclass
class TradeRecord:
    """Record of a single trade"""
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_pct: float
    entry_time: datetime
    exit_time: datetime
    holding_period_hours: float
    strategy: str = "unknown"


@dataclass
class DrawdownInfo:
    """Information about a drawdown period"""
    max_drawdown_pct: float
    peak_value: float
    trough_value: float
    peak_date: datetime
    trough_date: datetime
    recovery_date: Optional[datetime]
    duration_days: int
    recovered: bool


@dataclass
class RiskMetrics:
    """Value at Risk and Expected Shortfall metrics"""
    var_95: float           # 95% VaR
    var_99: float           # 99% VaR
    cvar_95: float          # 95% CVaR (Expected Shortfall)
    cvar_99: float          # 99% CVaR
    method: RiskMetricMethod
    sample_size: int


@dataclass
class TradeStatistics:
    """Comprehensive trade statistics"""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float
    profit_factor: float
    reward_risk_ratio: float
    expectancy: float               # Expected P&L per trade
    expectancy_r: float             # Expectancy in R-multiples
    avg_holding_period_hours: float
    avg_trades_per_day: float


@dataclass
class PerformanceReport:
    """Complete performance analytics report"""
    # Return metrics
    total_return_pct: float
    cagr_pct: float
    monthly_return_pct: float
    daily_return_pct: float
    annualized_volatility: float

    # Risk-adjusted metrics
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    omega_ratio: float

    # Drawdown metrics
    max_drawdown: DrawdownInfo
    avg_drawdown_pct: float
    max_drawdown_duration_days: int

    # Trade statistics
    trade_stats: TradeStatistics

    # Risk metrics
    risk_metrics: RiskMetrics

    # Additional metrics
    skewness: float
    kurtosis: float
    best_day_pct: float
    worst_day_pct: float
    positive_days_pct: float

    # Time period
    start_date: datetime
    end_date: datetime
    trading_days: int


class PerformanceAnalytics:
    """
    Comprehensive Performance Analytics Engine

    RESEARCH-BACKED IMPLEMENTATION:
    - Sharpe Ratio for risk-adjusted returns
    - Sortino Ratio for downside risk
    - Calmar Ratio for drawdown-adjusted returns
    - VaR and CVaR for tail risk
    - Maximum Drawdown analysis
    - Trade expectancy calculation

    Usage:
        analytics = PerformanceAnalytics()

        # Add trades
        analytics.record_trade(trade)

        # Add daily returns
        analytics.record_daily_return(0.02)

        # Get full report
        report = analytics.generate_report()
    """

    def __init__(
        self,
        risk_free_rate: float = 0.0,
        trading_days_per_year: int = 365  # Crypto markets are 24/7
    ):
        """
        Initialize performance analytics

        Args:
            risk_free_rate: Annual risk-free rate (default 0%)
            trading_days_per_year: Trading days per year (365 for crypto)
        """
        self.risk_free_rate = risk_free_rate
        self.trading_days_per_year = trading_days_per_year

        self._trades: List[TradeRecord] = []
        self._daily_returns: List[float] = []
        self._equity_curve: List[Tuple[datetime, float]] = []
        self._initial_capital: float = 0
        self._current_capital: float = 0

        logger.info(
            f"PerformanceAnalytics initialized: "
            f"rf_rate={risk_free_rate:.2%}, "
            f"trading_days={trading_days_per_year}"
        )

    def set_initial_capital(self, capital: float):
        """Set initial capital for equity curve tracking"""
        self._initial_capital = capital
        self._current_capital = capital
        self._equity_curve = [(datetime.now(), capital)]

    def record_trade(self, trade: TradeRecord):
        """Record a completed trade"""
        self._trades.append(trade)

        # Update equity curve
        self._current_capital += trade.pnl
        self._equity_curve.append((trade.exit_time, self._current_capital))

        # Calculate daily return for the trade
        if len(self._equity_curve) >= 2:
            prev_capital = self._equity_curve[-2][1]
            if prev_capital > 0:
                daily_return = trade.pnl / prev_capital
                self._daily_returns.append(daily_return)

    def record_daily_return(self, return_pct: float):
        """Record a daily return percentage"""
        self._daily_returns.append(return_pct)

    def record_equity_value(self, value: float, timestamp: Optional[datetime] = None):
        """Record current equity value"""
        ts = timestamp or datetime.now()
        self._equity_curve.append((ts, value))
        self._current_capital = value

        # Calculate return from previous
        if len(self._equity_curve) >= 2:
            prev_value = self._equity_curve[-2][1]
            if prev_value > 0:
                daily_return = (value - prev_value) / prev_value
                self._daily_returns.append(daily_return)

    # =========================================================================
    # RISK-ADJUSTED RETURN METRICS
    # =========================================================================

    def calculate_sharpe_ratio(
        self,
        returns: Optional[List[float]] = None,
        annualize: bool = True
    ) -> float:
        """
        Calculate Sharpe Ratio

        Formula: (Rp - Rf) / sigma_p

        Args:
            returns: List of returns (uses stored returns if None)
            annualize: Whether to annualize the ratio

        Returns:
            Sharpe Ratio
        """
        rets = np.array(returns or self._daily_returns)
        if len(rets) < 2:
            return 0.0

        excess_returns = rets - (self.risk_free_rate / self.trading_days_per_year)
        mean_excess = np.mean(excess_returns)
        std_excess = np.std(excess_returns, ddof=1)

        if std_excess == 0:
            return 0.0

        sharpe = mean_excess / std_excess

        if annualize:
            sharpe *= np.sqrt(self.trading_days_per_year)

        return float(sharpe)

    def calculate_sortino_ratio(
        self,
        returns: Optional[List[float]] = None,
        annualize: bool = True
    ) -> float:
        """
        Calculate Sortino Ratio

        Like Sharpe but uses downside deviation (only negative returns)

        Args:
            returns: List of returns
            annualize: Whether to annualize

        Returns:
            Sortino Ratio
        """
        rets = np.array(returns or self._daily_returns)
        if len(rets) < 2:
            return 0.0

        excess_returns = rets - (self.risk_free_rate / self.trading_days_per_year)
        mean_excess = np.mean(excess_returns)

        # Calculate downside deviation (only negative returns)
        negative_returns = rets[rets < 0]
        if len(negative_returns) == 0:
            return float('inf')  # No losses

        downside_std = np.std(negative_returns, ddof=1)
        if downside_std == 0:
            return 0.0

        sortino = mean_excess / downside_std

        if annualize:
            sortino *= np.sqrt(self.trading_days_per_year)

        return float(sortino)

    def calculate_calmar_ratio(
        self,
        returns: Optional[List[float]] = None
    ) -> float:
        """
        Calculate Calmar Ratio

        Formula: CAGR / |Maximum Drawdown|

        Args:
            returns: List of returns

        Returns:
            Calmar Ratio
        """
        rets = np.array(returns or self._daily_returns)
        if len(rets) < 2:
            return 0.0

        # Calculate CAGR
        cumulative = np.cumprod(1 + rets)
        total_return = cumulative[-1] - 1
        years = len(rets) / self.trading_days_per_year
        if years <= 0:
            return 0.0

        cagr = (1 + total_return) ** (1 / years) - 1

        # Calculate max drawdown
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max
        max_dd = abs(np.min(drawdown))

        if max_dd == 0:
            return float('inf')

        return float(cagr / max_dd)

    def calculate_omega_ratio(
        self,
        returns: Optional[List[float]] = None,
        threshold: float = 0.0
    ) -> float:
        """
        Calculate Omega Ratio

        Ratio of probability-weighted gains vs losses

        Args:
            returns: List of returns
            threshold: Minimum acceptable return

        Returns:
            Omega Ratio
        """
        rets = np.array(returns or self._daily_returns)
        if len(rets) < 2:
            return 0.0

        gains = rets[rets > threshold] - threshold
        losses = threshold - rets[rets <= threshold]

        sum_losses = np.sum(losses)
        if sum_losses == 0:
            return float('inf')

        return float(np.sum(gains) / sum_losses)

    # =========================================================================
    # DRAWDOWN ANALYSIS
    # =========================================================================

    def calculate_max_drawdown(
        self,
        returns: Optional[List[float]] = None
    ) -> DrawdownInfo:
        """
        Calculate Maximum Drawdown and related info

        Args:
            returns: List of returns

        Returns:
            DrawdownInfo with detailed drawdown data
        """
        rets = np.array(returns or self._daily_returns)
        if len(rets) < 2:
            return DrawdownInfo(
                max_drawdown_pct=0.0,
                peak_value=0.0,
                trough_value=0.0,
                peak_date=datetime.now(),
                trough_date=datetime.now(),
                recovery_date=None,
                duration_days=0,
                recovered=True
            )

        # Calculate cumulative returns
        cumulative = np.cumprod(1 + rets)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max

        # Find max drawdown
        max_dd_idx = np.argmin(drawdown)
        max_dd = drawdown[max_dd_idx]

        # Find peak before max drawdown
        peak_idx = np.argmax(running_max[:max_dd_idx + 1])

        # Find recovery (if any)
        recovery_idx = None
        if max_dd_idx < len(cumulative) - 1:
            post_trough = cumulative[max_dd_idx:]
            recovery_points = np.where(post_trough >= running_max[max_dd_idx])[0]
            if len(recovery_points) > 0:
                recovery_idx = max_dd_idx + recovery_points[0]

        # Get dates if equity curve available
        if len(self._equity_curve) >= len(rets):
            peak_date = self._equity_curve[peak_idx][0]
            trough_date = self._equity_curve[max_dd_idx][0]
            recovery_date = self._equity_curve[recovery_idx][0] if recovery_idx else None
        else:
            now = datetime.now()
            peak_date = now - timedelta(days=len(rets) - peak_idx)
            trough_date = now - timedelta(days=len(rets) - max_dd_idx)
            recovery_date = now - timedelta(days=len(rets) - recovery_idx) if recovery_idx else None

        duration = (trough_date - peak_date).days if peak_date and trough_date else 0

        return DrawdownInfo(
            max_drawdown_pct=abs(float(max_dd)) * 100,
            peak_value=float(cumulative[peak_idx]),
            trough_value=float(cumulative[max_dd_idx]),
            peak_date=peak_date,
            trough_date=trough_date,
            recovery_date=recovery_date,
            duration_days=duration,
            recovered=recovery_idx is not None
        )

    # =========================================================================
    # VALUE AT RISK (VaR) & EXPECTED SHORTFALL (CVaR)
    # =========================================================================

    def calculate_var(
        self,
        returns: Optional[List[float]] = None,
        confidence: float = 0.95,
        method: RiskMetricMethod = RiskMetricMethod.HISTORICAL
    ) -> float:
        """
        Calculate Value at Risk

        Args:
            returns: List of returns
            confidence: Confidence level (0.95 = 95%)
            method: Calculation method

        Returns:
            VaR as positive percentage
        """
        rets = np.array(returns or self._daily_returns)
        if len(rets) < 10:
            return 0.0

        if method == RiskMetricMethod.HISTORICAL:
            var = np.percentile(rets, (1 - confidence) * 100)

        elif method == RiskMetricMethod.PARAMETRIC:
            from scipy.stats import norm
            mean = np.mean(rets)
            std = np.std(rets, ddof=1)
            z_score = norm.ppf(1 - confidence)
            var = mean + z_score * std

        elif method == RiskMetricMethod.MONTE_CARLO:
            mean = np.mean(rets)
            std = np.std(rets, ddof=1)
            simulated = np.random.normal(mean, std, 10000)
            var = np.percentile(simulated, (1 - confidence) * 100)

        else:
            var = np.percentile(rets, (1 - confidence) * 100)

        return abs(float(var))

    def calculate_cvar(
        self,
        returns: Optional[List[float]] = None,
        confidence: float = 0.95,
        method: RiskMetricMethod = RiskMetricMethod.HISTORICAL
    ) -> float:
        """
        Calculate Conditional VaR (Expected Shortfall)

        CVaR is the expected loss given that the loss exceeds VaR

        Args:
            returns: List of returns
            confidence: Confidence level
            method: Calculation method

        Returns:
            CVaR as positive percentage
        """
        rets = np.array(returns or self._daily_returns)
        if len(rets) < 10:
            return 0.0

        if method == RiskMetricMethod.HISTORICAL:
            var_threshold = np.percentile(rets, (1 - confidence) * 100)
            tail_losses = rets[rets <= var_threshold]
            cvar = np.mean(tail_losses) if len(tail_losses) > 0 else var_threshold

        elif method == RiskMetricMethod.PARAMETRIC:
            from scipy.stats import norm
            mean = np.mean(rets)
            std = np.std(rets, ddof=1)
            z = norm.ppf(1 - confidence)
            # Expected shortfall for normal distribution
            es_factor = norm.pdf(z) / (1 - confidence)
            cvar = mean - std * es_factor

        elif method == RiskMetricMethod.MONTE_CARLO:
            mean = np.mean(rets)
            std = np.std(rets, ddof=1)
            simulated = np.random.normal(mean, std, 10000)
            var_threshold = np.percentile(simulated, (1 - confidence) * 100)
            tail_losses = simulated[simulated <= var_threshold]
            cvar = np.mean(tail_losses)

        else:
            var_threshold = np.percentile(rets, (1 - confidence) * 100)
            tail_losses = rets[rets <= var_threshold]
            cvar = np.mean(tail_losses) if len(tail_losses) > 0 else var_threshold

        return abs(float(cvar))

    def calculate_risk_metrics(
        self,
        returns: Optional[List[float]] = None,
        method: RiskMetricMethod = RiskMetricMethod.HISTORICAL
    ) -> RiskMetrics:
        """
        Calculate comprehensive risk metrics

        Args:
            returns: List of returns
            method: Calculation method

        Returns:
            RiskMetrics with VaR and CVaR
        """
        rets = returns or self._daily_returns

        return RiskMetrics(
            var_95=self.calculate_var(rets, 0.95, method),
            var_99=self.calculate_var(rets, 0.99, method),
            cvar_95=self.calculate_cvar(rets, 0.95, method),
            cvar_99=self.calculate_cvar(rets, 0.99, method),
            method=method,
            sample_size=len(rets)
        )

    # =========================================================================
    # TRADE STATISTICS
    # =========================================================================

    def calculate_trade_statistics(self) -> TradeStatistics:
        """
        Calculate comprehensive trade statistics

        Returns:
            TradeStatistics with win rate, expectancy, etc.
        """
        if not self._trades:
            return TradeStatistics(
                total_trades=0, winning_trades=0, losing_trades=0,
                win_rate=0, avg_win=0, avg_loss=0,
                largest_win=0, largest_loss=0,
                profit_factor=0, reward_risk_ratio=0,
                expectancy=0, expectancy_r=0,
                avg_holding_period_hours=0, avg_trades_per_day=0
            )

        wins = [t for t in self._trades if t.pnl > 0]
        losses = [t for t in self._trades if t.pnl < 0]

        total = len(self._trades)
        win_count = len(wins)
        loss_count = len(losses)

        win_rate = win_count / total if total > 0 else 0
        loss_rate = loss_count / total if total > 0 else 0

        avg_win = np.mean([t.pnl for t in wins]) if wins else 0
        avg_loss = abs(np.mean([t.pnl for t in losses])) if losses else 0

        largest_win = max([t.pnl for t in wins]) if wins else 0
        largest_loss = abs(min([t.pnl for t in losses])) if losses else 0

        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        reward_risk = avg_win / avg_loss if avg_loss > 0 else float('inf')

        # Expectancy = (Win% * Avg Win) - (Loss% * Avg Loss)
        expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
        expectancy_r = expectancy / avg_loss if avg_loss > 0 else 0

        # Average holding period
        holding_periods = [t.holding_period_hours for t in self._trades]
        avg_holding = np.mean(holding_periods) if holding_periods else 0

        # Trades per day
        if len(self._trades) >= 2:
            first_trade = min(t.entry_time for t in self._trades)
            last_trade = max(t.exit_time for t in self._trades)
            days = max(1, (last_trade - first_trade).days)
            trades_per_day = total / days
        else:
            trades_per_day = 0

        return TradeStatistics(
            total_trades=total,
            winning_trades=win_count,
            losing_trades=loss_count,
            win_rate=win_rate,
            avg_win=float(avg_win),
            avg_loss=float(avg_loss),
            largest_win=float(largest_win),
            largest_loss=float(largest_loss),
            profit_factor=float(profit_factor),
            reward_risk_ratio=float(reward_risk),
            expectancy=float(expectancy),
            expectancy_r=float(expectancy_r),
            avg_holding_period_hours=float(avg_holding),
            avg_trades_per_day=float(trades_per_day)
        )

    # =========================================================================
    # FULL PERFORMANCE REPORT
    # =========================================================================

    def generate_report(self) -> PerformanceReport:
        """
        Generate comprehensive performance report

        Returns:
            PerformanceReport with all metrics
        """
        rets = np.array(self._daily_returns) if self._daily_returns else np.array([0])

        # Return metrics
        if len(rets) > 1:
            cumulative = np.cumprod(1 + rets)
            total_return = (cumulative[-1] - 1) * 100
            years = len(rets) / self.trading_days_per_year
            cagr = ((1 + total_return/100) ** (1/years) - 1) * 100 if years > 0 else 0
            monthly_return = total_return / (years * 12) if years > 0 else 0
            daily_return = np.mean(rets) * 100
            volatility = np.std(rets, ddof=1) * np.sqrt(self.trading_days_per_year) * 100
        else:
            total_return = cagr = monthly_return = daily_return = volatility = 0.0
            cumulative = np.array([1.0])

        # Risk-adjusted metrics
        sharpe = self.calculate_sharpe_ratio()
        sortino = self.calculate_sortino_ratio()
        calmar = self.calculate_calmar_ratio()
        omega = self.calculate_omega_ratio()

        # Drawdown
        max_dd = self.calculate_max_drawdown()

        # Calculate all drawdowns for average
        if len(rets) > 1:
            running_max = np.maximum.accumulate(cumulative)
            drawdowns = (cumulative - running_max) / running_max
            avg_dd = abs(np.mean(drawdowns[drawdowns < 0])) * 100 if any(drawdowns < 0) else 0
        else:
            avg_dd = 0

        # Trade statistics
        trade_stats = self.calculate_trade_statistics()

        # Risk metrics
        risk_metrics = self.calculate_risk_metrics()

        # Additional metrics
        if len(rets) > 1:
            skewness = float(np.mean(((rets - np.mean(rets)) / np.std(rets)) ** 3)) if np.std(rets) > 0 else 0
            kurtosis = float(np.mean(((rets - np.mean(rets)) / np.std(rets)) ** 4) - 3) if np.std(rets) > 0 else 0
            best_day = float(np.max(rets)) * 100
            worst_day = float(np.min(rets)) * 100
            positive_days = float(np.sum(rets > 0) / len(rets)) * 100
        else:
            skewness = kurtosis = best_day = worst_day = 0.0
            positive_days = 0.0

        # Time period
        if self._equity_curve:
            start_date = self._equity_curve[0][0]
            end_date = self._equity_curve[-1][0]
        else:
            start_date = end_date = datetime.now()

        return PerformanceReport(
            total_return_pct=float(total_return),
            cagr_pct=float(cagr),
            monthly_return_pct=float(monthly_return),
            daily_return_pct=float(daily_return),
            annualized_volatility=float(volatility),
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            omega_ratio=omega,
            max_drawdown=max_dd,
            avg_drawdown_pct=float(avg_dd),
            max_drawdown_duration_days=max_dd.duration_days,
            trade_stats=trade_stats,
            risk_metrics=risk_metrics,
            skewness=skewness,
            kurtosis=kurtosis,
            best_day_pct=best_day,
            worst_day_pct=worst_day,
            positive_days_pct=positive_days,
            start_date=start_date,
            end_date=end_date,
            trading_days=len(rets)
        )

    def get_summary(self) -> Dict:
        """Get performance summary as dictionary"""
        report = self.generate_report()

        return {
            "returns": {
                "total_return_pct": round(report.total_return_pct, 2),
                "cagr_pct": round(report.cagr_pct, 2),
                "annualized_volatility": round(report.annualized_volatility, 2)
            },
            "risk_adjusted": {
                "sharpe_ratio": round(report.sharpe_ratio, 3),
                "sortino_ratio": round(report.sortino_ratio, 3),
                "calmar_ratio": round(report.calmar_ratio, 3)
            },
            "drawdown": {
                "max_drawdown_pct": round(report.max_drawdown.max_drawdown_pct, 2),
                "avg_drawdown_pct": round(report.avg_drawdown_pct, 2),
                "max_duration_days": report.max_drawdown_duration_days
            },
            "trade_stats": {
                "total_trades": report.trade_stats.total_trades,
                "win_rate": round(report.trade_stats.win_rate * 100, 2),
                "profit_factor": round(report.trade_stats.profit_factor, 2),
                "expectancy": round(report.trade_stats.expectancy, 2)
            },
            "risk_metrics": {
                "var_95": round(report.risk_metrics.var_95 * 100, 3),
                "cvar_95": round(report.risk_metrics.cvar_95 * 100, 3)
            },
            "period": {
                "start_date": report.start_date.isoformat(),
                "end_date": report.end_date.isoformat(),
                "trading_days": report.trading_days
            }
        }

    def get_status(self) -> Dict:
        """Get analytics status"""
        return {
            "trades_recorded": len(self._trades),
            "daily_returns_count": len(self._daily_returns),
            "equity_points": len(self._equity_curve),
            "initial_capital": self._initial_capital,
            "current_capital": self._current_capital,
            "summary": self.get_summary() if self._daily_returns else {}
        }


# Global instance
_performance_analytics: Optional[PerformanceAnalytics] = None


def get_performance_analytics(
    risk_free_rate: float = 0.0,
    trading_days_per_year: int = 365
) -> PerformanceAnalytics:
    """Get or create global performance analytics instance"""
    global _performance_analytics
    if _performance_analytics is None:
        _performance_analytics = PerformanceAnalytics(risk_free_rate, trading_days_per_year)
    return _performance_analytics
