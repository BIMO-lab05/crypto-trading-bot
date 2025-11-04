"""
Risk Engine - Core risk calculations and monitoring
"""

import numpy as np
from decimal import Decimal
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging

from app.models import *
from app.config import settings

logger = logging.getLogger(__name__)


class RiskEngine:
    """
    Core risk calculation and monitoring engine
    Implements industry-standard risk metrics and monitoring
    """

    def __init__(self):
        self.risk_free_rate = settings.risk_free_rate
        self.circuit_breaker_active = False
        self.circuit_breaker_tripped_at: Optional[datetime] = None
        self.historical_returns: List[float] = []
        self.peak_value: Decimal = Decimal("0")

    # === CAPITAL MONITORING ===

    def calculate_capital_metrics(
        self,
        total_capital: Decimal,
        positions: List[Dict]
    ) -> CapitalMetrics:
        """
        Calculate capital allocation and utilization metrics
        """
        allocated_capital = Decimal("0")
        reserved_capital = Decimal("0")

        # Calculate allocated capital from positions
        for position in positions:
            position_value = Decimal(str(position.get('current_value', 0)))
            allocated_capital += position_value

        # Reserve capital for potential margin calls and drawdowns
        reserved_capital = total_capital * Decimal(str(settings.max_portfolio_risk))

        available_capital = total_capital - allocated_capital - reserved_capital

        # Calculate utilization (0-1)
        capital_utilization = float(allocated_capital / total_capital) if total_capital > 0 else 0.0

        return CapitalMetrics(
            total_capital=total_capital,
            available_capital=available_capital,
            allocated_capital=allocated_capital,
            reserved_capital=reserved_capital,
            capital_utilization=capital_utilization
        )

    # === EXPOSURE MONITORING ===

    def calculate_exposure_metrics(
        self,
        positions: List[Dict],
        total_capital: Decimal
    ) -> ExposureMetrics:
        """
        Calculate portfolio exposure metrics
        """
        long_exposure = Decimal("0")
        short_exposure = Decimal("0")
        concentrated_positions = []

        # Calculate exposures
        for position in positions:
            value = Decimal(str(position.get('current_value', 0)))
            quantity = float(position.get('quantity', 0))

            if quantity > 0:  # Long position
                long_exposure += value
            else:  # Short position
                short_exposure += abs(value)

            # Check for concentration risk
            position_pct = float(value / total_capital) if total_capital > 0 else 0
            if position_pct > settings.max_position_size:
                concentrated_positions.append({
                    'symbol': position.get('symbol'),
                    'value': float(value),
                    'percentage': position_pct * 100,
                    'excess': (position_pct - settings.max_position_size) * 100
                })

        net_exposure = long_exposure - short_exposure
        gross_exposure = long_exposure + short_exposure
        total_exposure = gross_exposure

        # Calculate exposure ratio and leverage
        exposure_ratio = float(total_exposure / total_capital) if total_capital > 0 else 0.0
        leverage = float(gross_exposure / total_capital) if total_capital > 0 else 0.0

        return ExposureMetrics(
            total_exposure=total_exposure,
            long_exposure=long_exposure,
            short_exposure=short_exposure,
            net_exposure=net_exposure,
            gross_exposure=gross_exposure,
            exposure_ratio=exposure_ratio,
            leverage=leverage,
            concentrated_positions=concentrated_positions
        )

    # === DRAWDOWN CALCULATIONS ===

    def calculate_drawdown_metrics(
        self,
        current_value: Decimal,
        historical_values: List[Tuple[datetime, Decimal]]
    ) -> DrawdownMetrics:
        """
        Calculate current and maximum drawdown metrics
        """
        if not historical_values:
            return DrawdownMetrics(
                current_drawdown=0.0,
                max_drawdown=0.0,
                underwater_period_days=0
            )

        # Update peak value
        if current_value > self.peak_value:
            self.peak_value = current_value

        # Calculate current drawdown
        current_drawdown = 0.0
        if self.peak_value > 0:
            current_drawdown = float((self.peak_value - current_value) / self.peak_value)

        # Calculate maximum drawdown from historical data
        max_drawdown = 0.0
        peak = Decimal("0")
        max_dd_date = None
        underwater_days = 0
        last_peak_date = None

        for date, value in historical_values:
            if value > peak:
                peak = value
                last_peak_date = date
                underwater_days = 0
            else:
                if peak > 0:
                    drawdown = float((peak - value) / peak)
                    if drawdown > max_drawdown:
                        max_drawdown = drawdown
                        max_dd_date = date

                if last_peak_date:
                    underwater_days = (datetime.now() - last_peak_date).days

        # Calculate recovery factor
        recovery_factor = None
        if max_drawdown > 0 and historical_values:
            total_return = float((current_value - historical_values[0][1]) / historical_values[0][1])
            recovery_factor = total_return / max_drawdown if max_drawdown != 0 else None

        return DrawdownMetrics(
            current_drawdown=current_drawdown,
            max_drawdown=max_drawdown,
            max_drawdown_date=max_dd_date,
            underwater_period_days=underwater_days,
            recovery_factor=recovery_factor
        )

    # === PERFORMANCE METRICS ===

    def calculate_performance_metrics(
        self,
        returns: List[float],
        max_drawdown: float,
        trades: List[Dict]
    ) -> PerformanceMetrics:
        """
        Calculate comprehensive performance and risk-adjusted metrics
        """
        if not returns:
            return PerformanceMetrics(
                total_return=0.0,
                annualized_return=0.0,
                volatility=0.0,
                max_drawdown=max_drawdown
            )

        returns_array = np.array(returns)

        # Basic metrics
        total_return = float(np.prod([1 + r for r in returns]) - 1)
        annualized_return = self._annualize_return(total_return, len(returns))
        volatility = float(np.std(returns_array)) * np.sqrt(252)  # Annualized volatility

        # Sharpe Ratio
        sharpe_ratio = None
        if volatility > 0:
            excess_return = annualized_return - self.risk_free_rate
            sharpe_ratio = excess_return / volatility

        # Sortino Ratio (uses downside deviation)
        sortino_ratio = None
        downside_returns = returns_array[returns_array < 0]
        if len(downside_returns) > 0:
            downside_std = float(np.std(downside_returns)) * np.sqrt(252)
            if downside_std > 0:
                sortino_ratio = (annualized_return - self.risk_free_rate) / downside_std

        # Calmar Ratio (return / max drawdown)
        calmar_ratio = None
        if max_drawdown > 0:
            calmar_ratio = annualized_return / max_drawdown

        # Trading metrics
        win_rate, profit_factor, avg_win, avg_loss = self._calculate_trade_metrics(trades)

        return PerformanceMetrics(
            total_return=total_return,
            annualized_return=annualized_return,
            volatility=volatility,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_factor=profit_factor,
            average_win=avg_win,
            average_loss=avg_loss
        )

    def _annualize_return(self, total_return: float, num_periods: int) -> float:
        """Annualize return based on number of periods"""
        if num_periods == 0:
            return 0.0
        periods_per_year = 252  # Trading days
        years = num_periods / periods_per_year
        if years <= 0:
            return 0.0
        return (1 + total_return) ** (1 / years) - 1

    def _calculate_trade_metrics(self, trades: List[Dict]) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        """Calculate win rate and profit factor from trades"""
        if not trades:
            return None, None, None, None

        wins = [t for t in trades if t.get('pnl', 0) > 0]
        losses = [t for t in trades if t.get('pnl', 0) < 0]

        win_rate = len(wins) / len(trades) if trades else None

        gross_profit = sum(t['pnl'] for t in wins) if wins else 0
        gross_loss = abs(sum(t['pnl'] for t in losses)) if losses else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else None

        avg_win = np.mean([t['pnl'] for t in wins]) if wins else None
        avg_loss = np.mean([t['pnl'] for t in losses]) if losses else None

        return win_rate, profit_factor, avg_win, avg_loss

    # === VALUE AT RISK (VaR) ===

    def calculate_var(
        self,
        portfolio_value: Decimal,
        returns: List[float],
        confidence_level: float = 0.95,
        time_horizon_days: int = 1
    ) -> ValueAtRisk:
        """
        Calculate Value at Risk using historical method
        VaR represents the maximum expected loss at a given confidence level
        """
        if not returns or len(returns) < 30:
            # Not enough data, return conservative estimates
            return ValueAtRisk(
                var_95=portfolio_value * Decimal("0.05"),
                var_99=portfolio_value * Decimal("0.10"),
                cvar_95=portfolio_value * Decimal("0.07"),
                confidence_level=confidence_level,
                time_horizon_days=time_horizon_days,
                calculation_method="insufficient_data"
            )

        returns_array = np.array(returns)

        # Calculate VaR at 95% and 99% confidence levels
        var_95_pct = np.percentile(returns_array, 5)  # 5th percentile for 95% confidence
        var_99_pct = np.percentile(returns_array, 1)  # 1st percentile for 99% confidence

        # Scale by time horizon (square root of time rule)
        time_scale = np.sqrt(time_horizon_days)
        var_95 = abs(Decimal(str(var_95_pct))) * portfolio_value * Decimal(str(time_scale))
        var_99 = abs(Decimal(str(var_99_pct))) * portfolio_value * Decimal(str(time_scale))

        # Calculate CVaR (Conditional VaR / Expected Shortfall)
        # Average of losses beyond VaR threshold
        tail_losses_95 = returns_array[returns_array <= var_95_pct]
        cvar_95_pct = np.mean(tail_losses_95) if len(tail_losses_95) > 0 else var_95_pct
        cvar_95 = abs(Decimal(str(cvar_95_pct))) * portfolio_value * Decimal(str(time_scale))

        return ValueAtRisk(
            var_95=var_95,
            var_99=var_99,
            cvar_95=cvar_95,
            confidence_level=confidence_level,
            time_horizon_days=time_horizon_days,
            calculation_method="historical"
        )

    # === RISK SCORING ===

    def calculate_risk_score(
        self,
        capital_metrics: CapitalMetrics,
        exposure_metrics: ExposureMetrics,
        drawdown_metrics: DrawdownMetrics,
        performance_metrics: PerformanceMetrics,
        var_metrics: ValueAtRisk
    ) -> Tuple[float, RiskLevel]:
        """
        Calculate composite risk score (0-100) and risk level
        Lower score = lower risk
        """
        scores = []

        # Capital risk (0-20 points)
        capital_score = capital_metrics.capital_utilization * 20
        scores.append(capital_score)

        # Exposure risk (0-25 points)
        exposure_score = min(exposure_metrics.exposure_ratio / settings.max_exposure, 1.0) * 25
        scores.append(exposure_score)

        # Concentration risk (0-15 points)
        concentration_score = min(len(exposure_metrics.concentrated_positions) * 5, 15)
        scores.append(concentration_score)

        # Volatility risk (0-20 points)
        vol_target = 0.20  # 20% annual volatility
        volatility_score = min(performance_metrics.volatility / vol_target, 1.0) * 20
        scores.append(volatility_score)

        # Drawdown risk (0-20 points)
        drawdown_score = (drawdown_metrics.current_drawdown / settings.max_drawdown_threshold) * 20
        scores.append(min(drawdown_score, 20))

        # Total risk score
        total_score = sum(scores)

        # Determine risk level
        if total_score < 30:
            risk_level = RiskLevel.LOW
        elif total_score < 60:
            risk_level = RiskLevel.MEDIUM
        elif total_score < 80:
            risk_level = RiskLevel.HIGH
        else:
            risk_level = RiskLevel.CRITICAL

        return total_score, risk_level

    # === RISK ALERTS ===

    def generate_risk_alerts(
        self,
        capital_metrics: CapitalMetrics,
        exposure_metrics: ExposureMetrics,
        drawdown_metrics: DrawdownMetrics,
        performance_metrics: PerformanceMetrics
    ) -> List[RiskAlert]:
        """
        Generate risk alerts based on threshold violations
        """
        alerts = []
        now = datetime.now()

        # Capital utilization alert
        if capital_metrics.capital_utilization > 0.90:
            alerts.append(RiskAlert(
                alert_id=f"capital_util_{now.timestamp()}",
                timestamp=now,
                level=RiskLevel.HIGH,
                category="Capital",
                message="Capital utilization exceeds 90%",
                metric_value=capital_metrics.capital_utilization,
                threshold=0.90,
                recommendation="Reduce position sizes or add capital"
            ))

        # Exposure alert
        if exposure_metrics.exposure_ratio > settings.max_exposure:
            alerts.append(RiskAlert(
                alert_id=f"exposure_{now.timestamp()}",
                timestamp=now,
                level=RiskLevel.CRITICAL,
                category="Exposure",
                message=f"Total exposure exceeds limit of {settings.max_exposure*100}%",
                metric_value=exposure_metrics.exposure_ratio,
                threshold=settings.max_exposure,
                recommendation="Immediately reduce positions to comply with risk limits"
            ))

        # Concentration alerts
        for position in exposure_metrics.concentrated_positions:
            alerts.append(RiskAlert(
                alert_id=f"concentration_{position['symbol']}_{now.timestamp()}",
                timestamp=now,
                level=RiskLevel.MEDIUM,
                category="Concentration",
                message=f"{position['symbol']} position exceeds max position size",
                metric_value=position['percentage'] / 100,
                threshold=settings.max_position_size,
                recommendation=f"Reduce {position['symbol']} position by {position['excess']:.1f}%"
            ))

        # Drawdown alert
        if drawdown_metrics.current_drawdown > settings.max_drawdown_threshold:
            alerts.append(RiskAlert(
                alert_id=f"drawdown_{now.timestamp()}",
                timestamp=now,
                level=RiskLevel.CRITICAL,
                category="Drawdown",
                message=f"Drawdown exceeds {settings.max_drawdown_threshold*100}% threshold",
                metric_value=drawdown_metrics.current_drawdown,
                threshold=settings.max_drawdown_threshold,
                recommendation="Consider halting trading and reviewing strategy"
            ))

        # Sharpe ratio alert
        if performance_metrics.sharpe_ratio and performance_metrics.sharpe_ratio < 1.0:
            alerts.append(RiskAlert(
                alert_id=f"sharpe_{now.timestamp()}",
                timestamp=now,
                level=RiskLevel.MEDIUM,
                category="Performance",
                message="Sharpe ratio below 1.0 indicates poor risk-adjusted returns",
                metric_value=performance_metrics.sharpe_ratio,
                threshold=1.0,
                recommendation="Review and adjust trading strategy"
            ))

        return alerts

    # === CIRCUIT BREAKER ===

    def check_circuit_breaker(
        self,
        daily_pnl: float,
        drawdown: float,
        exposure_ratio: float
    ) -> CircuitBreakerStatus:
        """
        Check if circuit breaker should be tripped
        Halts trading if critical risk thresholds are breached
        """
        if not settings.enable_circuit_breaker:
            return CircuitBreakerStatus(
                is_tripped=False,
                can_trade=True
            )

        # Check if already tripped and in cooldown
        if self.circuit_breaker_active and self.circuit_breaker_tripped_at:
            cooldown_ends = self.circuit_breaker_tripped_at + timedelta(seconds=settings.circuit_breaker_cooldown)
            if datetime.now() < cooldown_ends:
                return CircuitBreakerStatus(
                    is_tripped=True,
                    tripped_at=self.circuit_breaker_tripped_at,
                    reason="Circuit breaker active",
                    cooldown_ends_at=cooldown_ends,
                    can_trade=False
                )
            else:
                # Cooldown period over, reset
                self.circuit_breaker_active = False
                self.circuit_breaker_tripped_at = None

        # Check if circuit breaker should be tripped
        trip_reason = None

        if daily_pnl < -settings.max_daily_loss:
            trip_reason = f"Daily loss {daily_pnl*100:.2f}% exceeds limit of {settings.max_daily_loss*100}%"
        elif drawdown > settings.max_drawdown_threshold:
            trip_reason = f"Drawdown {drawdown*100:.2f}% exceeds limit of {settings.max_drawdown_threshold*100}%"
        elif exposure_ratio > settings.max_exposure * 1.2:  # 20% buffer before circuit breaker
            trip_reason = f"Exposure {exposure_ratio*100:.2f}% critically high"

        if trip_reason:
            self.circuit_breaker_active = True
            self.circuit_breaker_tripped_at = datetime.now()
            cooldown_ends = self.circuit_breaker_tripped_at + timedelta(seconds=settings.circuit_breaker_cooldown)

            logger.critical(f"🚨 CIRCUIT BREAKER TRIPPED: {trip_reason}")

            return CircuitBreakerStatus(
                is_tripped=True,
                tripped_at=self.circuit_breaker_tripped_at,
                reason=trip_reason,
                cooldown_ends_at=cooldown_ends,
                can_trade=False
            )

        return CircuitBreakerStatus(
            is_tripped=False,
            can_trade=True
        )
