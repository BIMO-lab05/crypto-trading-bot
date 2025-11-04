"""
Performance Calculator Service
Calculates portfolio performance metrics including risk-adjusted returns
"""

import numpy as np
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta

from app.models.performance import PerformanceMetrics, DailyPerformance, PeriodPerformance
from app.models.portfolio import Portfolio
from app.config import settings


class PerformanceCalculator:
    """Calculates comprehensive portfolio performance metrics"""

    def __init__(self):
        self.risk_free_rate = settings.risk_free_rate

    def calculate_metrics(
        self,
        portfolio: Portfolio,
        daily_values: Optional[List[Decimal]] = None,
        trades_history: Optional[List[Dict]] = None
    ) -> PerformanceMetrics:
        """Calculate comprehensive performance metrics"""

        metrics = PerformanceMetrics()

        # Basic returns
        metrics.total_return = portfolio.total_pnl
        metrics.total_return_pct = portfolio.total_return_pct
        metrics.total_pnl = portfolio.total_pnl
        metrics.realized_pnl = portfolio.realized_pnl
        metrics.unrealized_pnl = portfolio.unrealized_pnl

        # Calculate from trade history if available
        if trades_history:
            metrics.total_trades = len(trades_history)
            metrics.winning_trades = sum(1 for t in trades_history if t.get("pnl", 0) > 0)
            metrics.losing_trades = sum(1 for t in trades_history if t.get("pnl", 0) < 0)

            if metrics.total_trades > 0:
                metrics.win_rate = (metrics.winning_trades / metrics.total_trades) * 100

            # Average win/loss
            winning_pnls = [Decimal(str(t["pnl"])) for t in trades_history if t.get("pnl", 0) > 0]
            losing_pnls = [Decimal(str(t["pnl"])) for t in trades_history if t.get("pnl", 0) < 0]

            if winning_pnls:
                metrics.average_win = sum(winning_pnls) / len(winning_pnls)
            if losing_pnls:
                metrics.average_loss = sum(losing_pnls) / len(losing_pnls)

            # Profit factor
            total_wins = sum(winning_pnls) if winning_pnls else Decimal("0")
            total_losses = abs(sum(losing_pnls)) if losing_pnls else Decimal("0")

            if total_losses > 0:
                metrics.profit_factor = float(total_wins / total_losses)

        # Risk metrics from daily values
        if daily_values and len(daily_values) > 1:
            returns = self._calculate_returns(daily_values)

            metrics.volatility = self._calculate_volatility(returns)
            metrics.sharpe_ratio = self._calculate_sharpe_ratio(returns, metrics.volatility)
            metrics.sortino_ratio = self._calculate_sortino_ratio(returns)
            metrics.max_drawdown, metrics.max_drawdown_duration = self._calculate_max_drawdown(daily_values)

        metrics.calculated_at = int(datetime.now().timestamp() * 1000)

        return metrics

    def _calculate_returns(self, values: List[Decimal]) -> np.ndarray:
        """Calculate daily returns from portfolio values"""
        values_array = np.array([float(v) for v in values])
        returns = np.diff(values_array) / values_array[:-1]
        return returns

    def _calculate_volatility(self, returns: np.ndarray) -> float:
        """Calculate annualized volatility"""
        if len(returns) == 0:
            return 0.0

        daily_std = np.std(returns)
        # Annualize assuming 365 trading days
        annualized_vol = daily_std * np.sqrt(365)
        return float(annualized_vol)

    def _calculate_sharpe_ratio(self, returns: np.ndarray, volatility: Optional[float]) -> Optional[float]:
        """Calculate Sharpe ratio"""
        if len(returns) == 0 or volatility is None or volatility == 0:
            return None

        # Average daily return
        avg_return = np.mean(returns)

        # Daily risk-free rate
        daily_rf = self.risk_free_rate / 365

        # Sharpe ratio
        excess_return = avg_return - daily_rf
        sharpe = (excess_return * 365) / volatility  # Annualized

        return float(sharpe)

    def _calculate_sortino_ratio(self, returns: np.ndarray) -> Optional[float]:
        """Calculate Sortino ratio (downside deviation)"""
        if len(returns) == 0:
            return None

        # Average return
        avg_return = np.mean(returns)

        # Downside deviation (only negative returns)
        downside_returns = returns[returns < 0]
        if len(downside_returns) == 0:
            return None

        downside_std = np.std(downside_returns)
        if downside_std == 0:
            return None

        # Annualize
        annualized_downside_std = downside_std * np.sqrt(365)

        # Daily risk-free rate
        daily_rf = self.risk_free_rate / 365

        # Sortino ratio
        excess_return = avg_return - daily_rf
        sortino = (excess_return * 365) / annualized_downside_std

        return float(sortino)

    def _calculate_max_drawdown(self, values: List[Decimal]) -> Tuple[Optional[float], Optional[int]]:
        """Calculate maximum drawdown and its duration"""
        if len(values) < 2:
            return None, None

        values_array = np.array([float(v) for v in values])

        # Calculate running maximum
        running_max = np.maximum.accumulate(values_array)

        # Calculate drawdown
        drawdown = (values_array - running_max) / running_max * 100

        # Maximum drawdown
        max_dd = float(np.min(drawdown))

        # Calculate max drawdown duration
        dd_duration = 0
        current_dd_duration = 0
        in_drawdown = False

        for dd in drawdown:
            if dd < 0:
                if not in_drawdown:
                    in_drawdown = True
                    current_dd_duration = 1
                else:
                    current_dd_duration += 1
            else:
                if in_drawdown:
                    dd_duration = max(dd_duration, current_dd_duration)
                    in_drawdown = False
                    current_dd_duration = 0

        # Check if still in drawdown at the end
        if in_drawdown:
            dd_duration = max(dd_duration, current_dd_duration)

        return max_dd, dd_duration

    def calculate_daily_performance(
        self,
        daily_snapshots: List[Dict]
    ) -> List[DailyPerformance]:
        """Calculate daily performance from snapshots"""

        daily_performances = []
        initial_value = None

        for snapshot in daily_snapshots:
            date_str = datetime.fromtimestamp(snapshot["timestamp"] / 1000).strftime("%Y-%m-%d")
            portfolio_value = Decimal(snapshot["total_value"])

            if initial_value is None:
                initial_value = portfolio_value

            # Calculate daily return
            if len(daily_performances) > 0:
                prev_value = Decimal(daily_performances[-1].portfolio_value)
                daily_pnl = portfolio_value - prev_value
                if prev_value > 0:
                    daily_return_pct = (daily_pnl / prev_value) * Decimal("100")
                else:
                    daily_return_pct = Decimal("0")
            else:
                daily_pnl = Decimal("0")
                daily_return_pct = Decimal("0")

            # Cumulative return
            if initial_value > 0:
                cumulative_return_pct = ((portfolio_value - initial_value) / initial_value) * Decimal("100")
            else:
                cumulative_return_pct = Decimal("0")

            daily_perf = DailyPerformance(
                date=date_str,
                portfolio_value=str(portfolio_value),
                daily_pnl=str(daily_pnl),
                daily_return_pct=str(daily_return_pct),
                cumulative_return_pct=str(cumulative_return_pct),
                trades_count=snapshot.get("trades_count", 0)
            )

            daily_performances.append(daily_perf)

        return daily_performances

    def calculate_period_performance(
        self,
        current_value: Decimal,
        historical_values: List[Tuple[datetime, Decimal]],
        period: str
    ) -> Optional[PeriodPerformance]:
        """Calculate performance for a specific period"""

        # Determine period lookback
        period_days = {
            "1d": 1,
            "7d": 7,
            "30d": 30,
            "90d": 90,
            "365d": 365
        }

        if period not in period_days:
            return None

        lookback_days = period_days[period]
        cutoff_date = datetime.now() - timedelta(days=lookback_days)

        # Filter historical values
        period_values = [(dt, val) for dt, val in historical_values if dt >= cutoff_date]

        if len(period_values) < 2:
            return None

        start_date, start_value = period_values[0]
        end_date = datetime.now()
        end_value = current_value

        # Calculate return
        total_return = end_value - start_value
        if start_value > 0:
            total_return_pct = (total_return / start_value) * Decimal("100")
        else:
            total_return_pct = Decimal("0")

        # Extract just values for metrics
        values = [val for _, val in period_values]
        values.append(current_value)

        # Calculate risk metrics
        returns = self._calculate_returns(values)
        volatility = self._calculate_volatility(returns) if len(returns) > 0 else None
        sharpe = self._calculate_sharpe_ratio(returns, volatility) if volatility else None
        max_dd, _ = self._calculate_max_drawdown(values)

        return PeriodPerformance(
            period=period,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            start_value=str(start_value),
            end_value=str(end_value),
            total_return=str(total_return),
            total_return_pct=str(total_return_pct),
            volatility=volatility,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            trades_count=0  # Would need trade history to calculate
        )
