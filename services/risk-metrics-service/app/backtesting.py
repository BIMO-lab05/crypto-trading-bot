"""
Backtesting Engine - Historical risk analysis and strategy validation
Simulates risk metrics over historical data to validate risk management strategies
"""

import math
import time
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
from statistics import mean, stdev

from app.risk_engine import RiskEngine
from app.backtest_models import (
    BacktestConfig,
    BacktestResult,
    BacktestMetrics,
    PortfolioSnapshot,
    RiskViolation,
    StrategyComparison,
    WalkForwardResult,
)

# Configure logging
logger = logging.getLogger(__name__)


class BacktestEngine:
    """
    Historical backtesting engine for risk management strategies
    Replays historical portfolio data to validate risk limits and calculate performance metrics
    """

    def __init__(self, risk_engine: Optional[RiskEngine] = None):
        """Initialize backtest engine with optional risk engine"""
        self.risk_engine = risk_engine or RiskEngine()
        logger.info("Backtest engine initialized")

    def run_backtest(self, config: BacktestConfig, historical_data: List[Dict]) -> BacktestResult:
        """
        Run a backtest with given configuration and historical data

        Args:
            config: Backtest configuration (dates, capital, risk limits)
            historical_data: List of historical portfolio states

        Returns:
            BacktestResult with comprehensive performance metrics and analysis
        """
        start_time = time.time()
        logger.info(f"Starting backtest from {config.start_date} to {config.end_date}")

        # Apply risk limits if provided
        if config.risk_limits:
            self._apply_risk_limits(config.risk_limits)

        # Filter data to backtest period
        filtered_data = self._filter_data_by_period(
            historical_data, config.start_date, config.end_date
        )

        if not filtered_data:
            raise ValueError("No historical data available for specified period")

        # Initialize tracking variables
        snapshots: List[PortfolioSnapshot] = []
        violations: List[RiskViolation] = []
        circuit_breaker_activations = 0
        days_halted = 0

        # Process each historical data point
        for i, data_point in enumerate(filtered_data):
            # Create portfolio snapshot
            snapshot = self._create_snapshot(
                data_point,
                config.initial_capital if i == 0 else snapshots[-1].total_value,
                snapshots,
            )
            snapshots.append(snapshot)

            # Check risk limits and detect violations
            violation = self._check_risk_violations(data_point, snapshots)
            if violation:
                violations.append(violation)
                if violation.would_halt_trading:
                    circuit_breaker_activations += 1
                    days_halted += 1

        # Calculate performance metrics
        metrics = self._calculate_metrics(snapshots, config)

        # Create result
        result = BacktestResult(
            config=config,
            metrics=metrics,
            snapshots=snapshots,
            violations=violations,
            start_value=snapshots[0].total_value,
            end_value=snapshots[-1].total_value,
            peak_value=max(s.total_value for s in snapshots),
            valley_value=min(s.total_value for s in snapshots),
            circuit_breaker_activations=circuit_breaker_activations,
            days_halted=days_halted,
            duration_seconds=time.time() - start_time,
        )

        logger.info(f"Backtest completed in {result.duration_seconds:.2f}s")
        logger.info(f"Final return: {metrics.total_return:.2%}, Sharpe: {metrics.sharpe_ratio:.2f}")

        return result

    def compare_strategies(
        self,
        strategies: List[Dict[str, any]],
        historical_data: List[Dict],
        start_date: datetime,
        end_date: datetime,
        # Declared account size, mirrored literally (ADR-029, was 100).
        # See backtest_models.BacktestConfig.initial_capital.
        initial_capital: Decimal = Decimal("10000"),
    ) -> StrategyComparison:
        """
        Compare multiple risk limit configurations

        Args:
            strategies: List of risk limit configurations to test
            historical_data: Historical portfolio data
            start_date: Start of backtest period
            end_date: End of backtest period
            initial_capital: Starting capital for all tests

        Returns:
            StrategyComparison with rankings and recommendations
        """
        logger.info(f"Comparing {len(strategies)} risk strategies")

        results: List[BacktestResult] = []

        # Run backtest for each strategy
        for i, strategy in enumerate(strategies):
            logger.info(
                f"Testing strategy {i + 1}/{len(strategies)}: {strategy.get('name', 'Unnamed')}"
            )

            config = BacktestConfig(
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                risk_limits=strategy.get("risk_limits"),
            )

            result = self.run_backtest(config, historical_data)
            results.append(result)

        # Rank strategies
        best_sharpe_idx = max(range(len(results)), key=lambda i: results[i].metrics.sharpe_ratio)
        best_return_idx = max(range(len(results)), key=lambda i: results[i].metrics.total_return)
        lowest_dd_idx = min(range(len(results)), key=lambda i: results[i].metrics.max_drawdown)
        most_stable_idx = min(range(len(results)), key=lambda i: results[i].metrics.volatility)

        # Generate recommendation
        recommendation = self._generate_recommendation(results, strategies)

        comparison = StrategyComparison(
            strategies=strategies,
            results=results,
            best_sharpe=strategies[best_sharpe_idx].get("name", f"Strategy {best_sharpe_idx}"),
            best_return=strategies[best_return_idx].get("name", f"Strategy {best_return_idx}"),
            lowest_drawdown=strategies[lowest_dd_idx].get("name", f"Strategy {lowest_dd_idx}"),
            most_stable=strategies[most_stable_idx].get("name", f"Strategy {most_stable_idx}"),
            recommendation=recommendation,
        )

        logger.info(f"Strategy comparison complete. Recommended: {recommendation}")
        return comparison

    def walk_forward_optimization(
        self,
        historical_data: List[Dict],
        training_window_days: int = 90,
        validation_window_days: int = 30,
        step_days: int = 30,
        parameter_grid: Dict[str, List[float]] = None,
    ) -> WalkForwardResult:
        """
        Perform walk-forward optimization to find robust parameters

        Args:
            historical_data: Complete historical dataset
            training_window_days: Days for in-sample training
            validation_window_days: Days for out-of-sample testing
            step_days: Days to move forward between iterations
            parameter_grid: Grid of parameters to test

        Returns:
            WalkForwardResult with optimal parameters and stability metrics
        """
        logger.info("Starting walk-forward optimization")

        if parameter_grid is None:
            # Default parameter grid
            parameter_grid = {
                "max_position_size": [0.01, 0.02, 0.03],
                "max_drawdown": [0.10, 0.15, 0.20],
                "max_exposure": [0.15, 0.20, 0.25],
            }

        in_sample_periods = []
        out_of_sample_periods = []

        # Get date range
        start_date = historical_data[0]["timestamp"]
        end_date = historical_data[-1]["timestamp"]

        current_date = start_date

        # Walk forward through time
        while (
            current_date + timedelta(days=training_window_days + validation_window_days) <= end_date
        ):
            training_end = current_date + timedelta(days=training_window_days)
            validation_end = training_end + timedelta(days=validation_window_days)

            logger.info(f"Period: {current_date} to {validation_end}")

            # In-sample optimization
            best_params, best_sharpe = self._optimize_on_period(
                historical_data, current_date, training_end, parameter_grid
            )

            in_sample_periods.append(
                {
                    "start": current_date,
                    "end": training_end,
                    "best_params": best_params,
                    "sharpe_ratio": best_sharpe,
                }
            )

            # Out-of-sample validation
            validation_sharpe = self._validate_on_period(
                historical_data, training_end, validation_end, best_params
            )

            out_of_sample_periods.append(
                {
                    "start": training_end,
                    "end": validation_end,
                    "params_used": best_params,
                    "sharpe_ratio": validation_sharpe,
                }
            )

            # Move forward
            current_date += timedelta(days=step_days)

        # Calculate metrics
        in_sample_sharpe = mean([p["sharpe_ratio"] for p in in_sample_periods])
        out_of_sample_sharpe = mean([p["sharpe_ratio"] for p in out_of_sample_periods])
        overfitting_score = (
            in_sample_sharpe / out_of_sample_sharpe if out_of_sample_sharpe > 0 else 999
        )

        # Find most stable parameters
        optimal_parameters = self._find_most_stable_parameters(in_sample_periods)
        parameter_stability = self._calculate_parameter_stability(in_sample_periods)

        # Generate recommendation
        recommended_for_live = (
            overfitting_score < 1.3 and out_of_sample_sharpe > 1.0 and parameter_stability > 0.7
        )

        confidence_score = min(1.0, parameter_stability * (2.0 / overfitting_score))

        notes = f"Overfitting score: {overfitting_score:.2f} ({'Low' if overfitting_score < 1.3 else 'High'}). "
        notes += f"Parameter stability: {parameter_stability:.2f}. "
        notes += f"Out-of-sample Sharpe: {out_of_sample_sharpe:.2f}."

        result = WalkForwardResult(
            in_sample_periods=in_sample_periods,
            out_of_sample_periods=out_of_sample_periods,
            optimal_parameters=optimal_parameters,
            parameter_stability=parameter_stability,
            in_sample_sharpe=in_sample_sharpe,
            out_of_sample_sharpe=out_of_sample_sharpe,
            overfitting_score=overfitting_score,
            recommended_for_live=recommended_for_live,
            confidence_score=confidence_score,
            notes=notes,
        )

        logger.info(f"Walk-forward optimization complete. Recommended: {recommended_for_live}")
        return result

    # Private helper methods

    def _apply_risk_limits(self, risk_limits: Dict[str, float]):
        """Apply custom risk limits to risk engine"""
        for key, value in risk_limits.items():
            if hasattr(self.risk_engine, key):
                setattr(self.risk_engine, key, value)
                logger.debug(f"Applied risk limit: {key} = {value}")

    def _filter_data_by_period(
        self, data: List[Dict], start_date: datetime, end_date: datetime
    ) -> List[Dict]:
        """Filter historical data to specified date range"""
        return [d for d in data if start_date <= d.get("timestamp", datetime.now()) <= end_date]

    def _create_snapshot(
        self, data_point: Dict, previous_value: Decimal, previous_snapshots: List[PortfolioSnapshot]
    ) -> PortfolioSnapshot:
        """Create portfolio snapshot from data point"""
        total_value = Decimal(str(data_point.get("total_value", previous_value)))

        # Calculate returns
        daily_return = None
        cumulative_return = None

        if previous_snapshots:
            prev_value = previous_snapshots[-1].total_value
            if prev_value > 0:
                daily_return = float((total_value - prev_value) / prev_value)

            first_value = previous_snapshots[0].total_value
            if first_value > 0:
                cumulative_return = float((total_value - first_value) / first_value)

        snapshot = PortfolioSnapshot(
            timestamp=data_point.get("timestamp", datetime.now()),
            total_value=total_value,
            cash_balance=Decimal(str(data_point.get("cash_balance", 0))),
            positions=data_point.get("positions", []),
            daily_return=daily_return,
            cumulative_return=cumulative_return,
        )

        return snapshot

    def _check_risk_violations(
        self, data_point: Dict, snapshots: List[PortfolioSnapshot]
    ) -> Optional[RiskViolation]:
        """Check if current state violates any risk limits"""
        # Calculate current metrics
        total_capital = snapshots[-1].total_value
        positions = data_point.get("positions", [])

        # Check capital utilization
        allocated = sum(Decimal(str(p.get("market_value", 0))) for p in positions)
        utilization = float(allocated / total_capital) if total_capital > 0 else 0

        if utilization > self.risk_engine.max_exposure:
            return RiskViolation(
                timestamp=data_point.get("timestamp", datetime.now()),
                violation_type="exposure",
                limit_value=self.risk_engine.max_exposure,
                actual_value=utilization,
                severity="warning"
                if utilization < self.risk_engine.max_exposure * 1.1
                else "critical",
                would_halt_trading=utilization > self.risk_engine.max_exposure * 1.2,
            )

        # Check drawdown
        if len(snapshots) > 1:
            peak = max(s.total_value for s in snapshots)
            current = snapshots[-1].total_value
            drawdown = float((peak - current) / peak) if peak > 0 else 0

            if drawdown > self.risk_engine.max_drawdown_threshold:
                return RiskViolation(
                    timestamp=data_point.get("timestamp", datetime.now()),
                    violation_type="drawdown",
                    limit_value=self.risk_engine.max_drawdown_threshold,
                    actual_value=drawdown,
                    severity="critical",
                    would_halt_trading=True,
                )

        return None

    def _calculate_metrics(
        self, snapshots: List[PortfolioSnapshot], config: BacktestConfig
    ) -> BacktestMetrics:
        """Calculate comprehensive performance metrics from snapshots"""
        # Extract returns
        returns = [s.daily_return for s in snapshots if s.daily_return is not None]

        if not returns:
            raise ValueError("Insufficient data to calculate metrics")

        # Basic metrics
        total_return = snapshots[-1].cumulative_return or 0.0
        days = len(snapshots)
        years = days / 365.0

        annualized_return = ((1 + total_return) ** (1 / years) - 1) if years > 0 else 0.0
        volatility = stdev(returns) if len(returns) > 1 else 0.0
        annualized_volatility = volatility * math.sqrt(365)

        # Risk-adjusted metrics
        risk_free_rate = 0.04  # 4% annual risk-free rate
        sharpe_ratio = (
            (annualized_return - risk_free_rate) / annualized_volatility
            if annualized_volatility > 0
            else 0.0
        )

        # Sortino ratio (downside deviation)
        negative_returns = [r for r in returns if r < 0]
        downside_deviation = stdev(negative_returns) if len(negative_returns) > 1 else volatility
        annualized_downside = downside_deviation * math.sqrt(365)
        sortino_ratio = (
            (annualized_return - risk_free_rate) / annualized_downside
            if annualized_downside > 0
            else 0.0
        )

        # Drawdown analysis
        peak = snapshots[0].total_value
        max_drawdown = 0.0
        max_dd_duration = 0
        current_dd_duration = 0

        for snapshot in snapshots:
            if snapshot.total_value > peak:
                peak = snapshot.total_value
                current_dd_duration = 0
            else:
                current_dd_duration += 1
                dd = float((peak - snapshot.total_value) / peak)
                max_drawdown = max(max_drawdown, dd)
                max_dd_duration = max(max_dd_duration, current_dd_duration)

        # Calmar ratio
        calmar_ratio = annualized_return / max_drawdown if max_drawdown > 0 else None

        # Win rate and profit metrics
        winning_days = [r for r in returns if r > 0]
        losing_days = [r for r in returns if r < 0]

        win_rate = len(winning_days) / len(returns) if returns else 0.0
        best_day = max(returns) if returns else 0.0
        worst_day = min(returns) if returns else 0.0
        avg_winning_day = mean(winning_days) if winning_days else 0.0
        avg_losing_day = mean(losing_days) if losing_days else 0.0

        total_wins = sum(winning_days) if winning_days else 0.0
        total_losses = abs(sum(losing_days)) if losing_days else 0.0
        profit_factor = total_wins / total_losses if total_losses > 0 else None

        metrics = BacktestMetrics(
            total_return=total_return,
            annualized_return=annualized_return,
            volatility=annualized_volatility,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_duration_days=max_dd_duration,
            calmar_ratio=calmar_ratio,
            win_rate=win_rate,
            best_day=best_day,
            worst_day=worst_day,
            avg_winning_day=avg_winning_day,
            avg_losing_day=avg_losing_day,
            profit_factor=profit_factor,
            total_trading_days=days,
        )

        return metrics

    def _generate_recommendation(
        self, results: List[BacktestResult], strategies: List[Dict]
    ) -> str:
        """Generate recommendation based on strategy comparison"""
        # Score each strategy
        scores = []
        for result in results:
            m = result.metrics
            # Weighted score: Sharpe (40%), Return (30%), Max DD (30%)
            score = m.sharpe_ratio * 0.4 + m.total_return * 0.3 - m.max_drawdown * 0.3
            scores.append(score)

        best_idx = scores.index(max(scores))
        best_strategy = strategies[best_idx].get("name", f"Strategy {best_idx}")

        return f"Recommended strategy: {best_strategy} with Sharpe {results[best_idx].metrics.sharpe_ratio:.2f}"

    def _optimize_on_period(
        self,
        data: List[Dict],
        start: datetime,
        end: datetime,
        parameter_grid: Dict[str, List[float]],
    ) -> Tuple[Dict[str, float], float]:
        """Optimize parameters on training period"""
        best_params = {}
        best_sharpe = -999.0

        # Simple grid search (in production, use more sophisticated optimization)
        for max_pos in parameter_grid.get("max_position_size", [0.02]):
            for max_dd in parameter_grid.get("max_drawdown", [0.15]):
                for max_exp in parameter_grid.get("max_exposure", [0.20]):
                    params = {
                        "max_position_size": max_pos,
                        "max_drawdown": max_dd,
                        "max_exposure": max_exp,
                    }

                    try:
                        config = BacktestConfig(start_date=start, end_date=end, risk_limits=params)
                        result = self.run_backtest(config, data)

                        if result.metrics.sharpe_ratio > best_sharpe:
                            best_sharpe = result.metrics.sharpe_ratio
                            best_params = params
                    except Exception as e:
                        logger.warning(f"Failed to test params {params}: {e}")
                        continue

        return best_params, best_sharpe

    def _validate_on_period(
        self, data: List[Dict], start: datetime, end: datetime, params: Dict[str, float]
    ) -> float:
        """Validate parameters on out-of-sample period"""
        try:
            config = BacktestConfig(start_date=start, end_date=end, risk_limits=params)
            result = self.run_backtest(config, data)
            return result.metrics.sharpe_ratio
        except Exception as e:
            logger.warning(f"Validation failed: {e}")
            return 0.0

    def _find_most_stable_parameters(self, in_sample_periods: List[Dict]) -> Dict[str, float]:
        """Find parameter values that appear most frequently across periods"""
        all_params = [p["best_params"] for p in in_sample_periods]

        # Average each parameter
        optimal = {}
        if all_params:
            for key in all_params[0].keys():
                values = [p[key] for p in all_params]
                optimal[key] = mean(values)

        return optimal

    def _calculate_parameter_stability(self, in_sample_periods: List[Dict]) -> float:
        """Calculate how stable parameters are across periods (0-1 score)"""
        all_params = [p["best_params"] for p in in_sample_periods]

        if len(all_params) < 2:
            return 1.0

        # Calculate coefficient of variation for each parameter
        stability_scores = []
        for key in all_params[0].keys():
            values = [p[key] for p in all_params]
            if mean(values) > 0:
                cv = stdev(values) / mean(values)
                stability_scores.append(1.0 / (1.0 + cv))  # Lower CV = higher stability

        return mean(stability_scores) if stability_scores else 0.0
