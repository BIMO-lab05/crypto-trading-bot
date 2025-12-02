"""
Performance Metrics for Backtesting Framework
Comprehensive metrics for evaluating trading strategy performance.
"""

import logging
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """
    Complete performance metrics for a backtest

    Includes:
    - Return metrics (total, CAGR, monthly)
    - Risk metrics (Sharpe, Sortino, Max Drawdown)
    - Trade metrics (win rate, profit factor, avg trade)
    """
    # Return metrics
    total_return_pct: float = 0.0
    cagr: float = 0.0
    monthly_returns: List[float] = field(default_factory=list)

    # Risk metrics
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_days: int = 0
    volatility: float = 0.0

    # Trade metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    avg_trade_duration_hours: float = 0.0

    # Equity metrics
    initial_equity: float = 0.0
    final_equity: float = 0.0
    peak_equity: float = 0.0

    # Time period
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    trading_days: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "returns": {
                "total_return_pct": round(self.total_return_pct, 2),
                "cagr": round(self.cagr, 2),
                "monthly_avg": round(np.mean(self.monthly_returns), 2) if self.monthly_returns else 0
            },
            "risk": {
                "sharpe_ratio": round(self.sharpe_ratio, 2),
                "sortino_ratio": round(self.sortino_ratio, 2),
                "max_drawdown_pct": round(self.max_drawdown_pct, 2),
                "max_drawdown_duration_days": self.max_drawdown_duration_days,
                "volatility": round(self.volatility, 2)
            },
            "trades": {
                "total_trades": self.total_trades,
                "winning_trades": self.winning_trades,
                "losing_trades": self.losing_trades,
                "win_rate": round(self.win_rate, 2),
                "profit_factor": round(self.profit_factor, 2),
                "avg_win": round(self.avg_win, 2),
                "avg_loss": round(self.avg_loss, 2),
                "largest_win": round(self.largest_win, 2),
                "largest_loss": round(self.largest_loss, 2),
                "avg_duration_hours": round(self.avg_trade_duration_hours, 1)
            },
            "equity": {
                "initial": round(self.initial_equity, 2),
                "final": round(self.final_equity, 2),
                "peak": round(self.peak_equity, 2)
            },
            "period": {
                "start": self.start_date.isoformat() if self.start_date else None,
                "end": self.end_date.isoformat() if self.end_date else None,
                "trading_days": self.trading_days
            }
        }

    def summary(self) -> str:
        """Generate text summary of metrics"""
        return f"""
=== BACKTEST PERFORMANCE SUMMARY ===
Period: {self.start_date.strftime('%Y-%m-%d') if self.start_date else 'N/A'} to {self.end_date.strftime('%Y-%m-%d') if self.end_date else 'N/A'}
Trading Days: {self.trading_days}

RETURNS:
  Total Return: {self.total_return_pct:.2f}%
  CAGR: {self.cagr:.2f}%
  Initial Equity: ${self.initial_equity:,.2f}
  Final Equity: ${self.final_equity:,.2f}

RISK METRICS:
  Sharpe Ratio: {self.sharpe_ratio:.2f}
  Sortino Ratio: {self.sortino_ratio:.2f}
  Max Drawdown: {self.max_drawdown_pct:.2f}%
  Volatility: {self.volatility:.2f}%

TRADE STATISTICS:
  Total Trades: {self.total_trades}
  Win Rate: {self.win_rate:.1f}%
  Profit Factor: {self.profit_factor:.2f}
  Avg Win: ${self.avg_win:.2f}
  Avg Loss: ${self.avg_loss:.2f}
  Largest Win: ${self.largest_win:.2f}
  Largest Loss: ${self.largest_loss:.2f}
========================================
"""


def calculate_returns(equity_curve: List[float]) -> List[float]:
    """Calculate period returns from equity curve"""
    if len(equity_curve) < 2:
        return []

    returns = []
    for i in range(1, len(equity_curve)):
        if equity_curve[i - 1] != 0:
            ret = (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
            returns.append(ret)

    return returns


def calculate_sharpe_ratio(
    returns: List[float],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252
) -> float:
    """
    Calculate Sharpe Ratio

    Sharpe = (Mean Return - Risk Free Rate) / Std Dev of Returns
    Annualized by multiplying by sqrt(periods_per_year)

    Args:
        returns: List of period returns (not percentages)
        risk_free_rate: Annual risk-free rate (default 0)
        periods_per_year: Trading periods per year (252 for daily)

    Returns:
        Annualized Sharpe Ratio
    """
    if len(returns) < 2:
        return 0.0

    returns_array = np.array(returns)
    excess_returns = returns_array - (risk_free_rate / periods_per_year)

    mean_return = np.mean(excess_returns)
    std_return = np.std(returns_array, ddof=1)

    if std_return == 0:
        return 0.0

    sharpe = (mean_return / std_return) * np.sqrt(periods_per_year)

    return float(sharpe)


def calculate_sortino_ratio(
    returns: List[float],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252
) -> float:
    """
    Calculate Sortino Ratio

    Similar to Sharpe but only penalizes downside volatility.
    Sortino = (Mean Return - Risk Free Rate) / Downside Deviation

    Args:
        returns: List of period returns
        risk_free_rate: Annual risk-free rate
        periods_per_year: Trading periods per year

    Returns:
        Annualized Sortino Ratio
    """
    if len(returns) < 2:
        return 0.0

    returns_array = np.array(returns)
    target_return = risk_free_rate / periods_per_year

    # Calculate downside returns (only negative deviations)
    downside_returns = np.minimum(returns_array - target_return, 0)
    downside_deviation = np.sqrt(np.mean(downside_returns ** 2))

    if downside_deviation == 0:
        return 0.0

    mean_return = np.mean(returns_array) - target_return
    sortino = (mean_return / downside_deviation) * np.sqrt(periods_per_year)

    return float(sortino)


def calculate_max_drawdown(equity_curve: List[float]) -> tuple:
    """
    Calculate Maximum Drawdown

    Max DD = (Peak - Trough) / Peak

    Args:
        equity_curve: List of equity values

    Returns:
        Tuple of (max_drawdown_pct, max_drawdown_duration_periods)
    """
    if len(equity_curve) < 2:
        return 0.0, 0

    equity_array = np.array(equity_curve)

    # Calculate running peak
    running_peak = np.maximum.accumulate(equity_array)

    # Calculate drawdown at each point
    drawdowns = (running_peak - equity_array) / running_peak

    # Max drawdown percentage
    max_dd = float(np.max(drawdowns)) * 100

    # Calculate drawdown duration
    max_dd_duration = 0
    current_dd_duration = 0

    for i in range(len(equity_array)):
        if equity_array[i] < running_peak[i]:
            current_dd_duration += 1
            max_dd_duration = max(max_dd_duration, current_dd_duration)
        else:
            current_dd_duration = 0

    return max_dd, max_dd_duration


def calculate_win_rate(winning_trades: int, total_trades: int) -> float:
    """Calculate win rate percentage"""
    if total_trades == 0:
        return 0.0
    return (winning_trades / total_trades) * 100


def calculate_profit_factor(gross_profit: float, gross_loss: float) -> float:
    """
    Calculate Profit Factor

    Profit Factor = Gross Profit / Gross Loss

    Values > 1 indicate profitable system
    Values > 2 are considered good
    """
    if gross_loss == 0:
        return float('inf') if gross_profit > 0 else 0.0
    return abs(gross_profit / gross_loss)


def calculate_cagr(
    initial_value: float,
    final_value: float,
    years: float
) -> float:
    """
    Calculate Compound Annual Growth Rate

    CAGR = (Final/Initial)^(1/years) - 1
    """
    if initial_value <= 0 or years <= 0:
        return 0.0

    cagr = ((final_value / initial_value) ** (1 / years)) - 1
    return cagr * 100


def calculate_volatility(returns: List[float], periods_per_year: int = 252) -> float:
    """
    Calculate annualized volatility

    Volatility = Std Dev * sqrt(periods_per_year)
    """
    if len(returns) < 2:
        return 0.0

    return float(np.std(returns, ddof=1) * np.sqrt(periods_per_year) * 100)


def calculate_all_metrics(
    equity_curve: List[float],
    trades: List[Dict[str, Any]],
    initial_equity: float,
    start_date: datetime,
    end_date: datetime
) -> PerformanceMetrics:
    """
    Calculate all performance metrics

    Args:
        equity_curve: List of equity values over time
        trades: List of trade dictionaries with 'pnl' and 'duration_hours'
        initial_equity: Starting equity
        start_date: Backtest start date
        end_date: Backtest end date

    Returns:
        Complete PerformanceMetrics object
    """
    # Calculate returns
    returns = calculate_returns(equity_curve)

    # Calculate time period
    days = (end_date - start_date).days
    years = days / 365.25 if days > 0 else 0

    # Calculate trade statistics
    winning_trades = [t for t in trades if t.get('pnl', 0) > 0]
    losing_trades = [t for t in trades if t.get('pnl', 0) < 0]

    gross_profit = sum(t.get('pnl', 0) for t in winning_trades)
    gross_loss = abs(sum(t.get('pnl', 0) for t in losing_trades))

    # Calculate drawdown
    max_dd, max_dd_duration = calculate_max_drawdown(equity_curve)

    # Build metrics object
    metrics = PerformanceMetrics(
        # Returns
        total_return_pct=((equity_curve[-1] / initial_equity) - 1) * 100 if equity_curve else 0,
        cagr=calculate_cagr(initial_equity, equity_curve[-1] if equity_curve else initial_equity, years),

        # Risk
        sharpe_ratio=calculate_sharpe_ratio(returns),
        sortino_ratio=calculate_sortino_ratio(returns),
        max_drawdown_pct=max_dd,
        max_drawdown_duration_days=max_dd_duration,
        volatility=calculate_volatility(returns),

        # Trades
        total_trades=len(trades),
        winning_trades=len(winning_trades),
        losing_trades=len(losing_trades),
        win_rate=calculate_win_rate(len(winning_trades), len(trades)),
        profit_factor=calculate_profit_factor(gross_profit, gross_loss),
        avg_win=gross_profit / len(winning_trades) if winning_trades else 0,
        avg_loss=gross_loss / len(losing_trades) if losing_trades else 0,
        largest_win=max((t.get('pnl', 0) for t in trades), default=0),
        largest_loss=min((t.get('pnl', 0) for t in trades), default=0),
        avg_trade_duration_hours=np.mean([t.get('duration_hours', 0) for t in trades]) if trades else 0,

        # Equity
        initial_equity=initial_equity,
        final_equity=equity_curve[-1] if equity_curve else initial_equity,
        peak_equity=max(equity_curve) if equity_curve else initial_equity,

        # Period
        start_date=start_date,
        end_date=end_date,
        trading_days=days
    )

    return metrics
