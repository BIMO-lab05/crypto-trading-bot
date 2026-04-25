"""
Walk-Forward Optimization Engine
Created: 2025-12-06
Purpose: Prevent overfitting through rolling window optimization

Walk-Forward Analysis divides historical data into multiple periods:
- In-Sample (IS): 70% of each window used for optimization
- Out-of-Sample (OOS): 30% of each window used for validation
- Rolling Windows: Move forward in time, re-optimize, validate

Walk-Forward Efficiency (WFE) = OOS Performance / IS Performance
Target: WFE > 0.50 (50%+) indicates robust strategy
"""

import logging
from typing import Dict, List, Any, Callable, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import pandas as pd
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
import json

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardConfig:
    """Configuration for walk-forward optimization"""

    # Window configuration
    total_periods: int = 5  # Number of rolling windows
    in_sample_ratio: float = 0.70  # 70% for optimization
    out_sample_ratio: float = 0.30  # 30% for validation

    # Optimization settings
    metric_to_optimize: str = 'sharpe_ratio'  # Can be: sharpe_ratio, profit_factor, sortino_ratio
    min_trades_per_period: int = 10  # Minimum trades required per period

    # Performance thresholds
    min_wfe: float = 0.50  # Minimum Walk-Forward Efficiency (50%)
    min_oos_sharpe: float = 0.50  # Minimum Out-of-Sample Sharpe
    max_oos_drawdown: float = 0.25  # Maximum Out-of-Sample Drawdown (25%)

    # Parallel processing
    max_workers: int = 4  # CPU cores for parallel optimization


@dataclass
class WalkForwardPeriod:
    """Represents a single walk-forward period"""
    period_number: int
    is_start_date: datetime
    is_end_date: datetime
    oos_start_date: datetime
    oos_end_date: datetime
    is_data: pd.DataFrame = field(default_factory=pd.DataFrame)
    oos_data: pd.DataFrame = field(default_factory=pd.DataFrame)

    # Results
    optimal_parameters: Dict[str, Any] = field(default_factory=dict)
    is_performance: Dict[str, float] = field(default_factory=dict)
    oos_performance: Dict[str, float] = field(default_factory=dict)


@dataclass
class WalkForwardResults:
    """Complete walk-forward optimization results"""
    config: WalkForwardConfig
    periods: List[WalkForwardPeriod]

    # Aggregate metrics
    average_wfe: float = 0.0
    median_wfe: float = 0.0
    worst_wfe: float = 0.0
    best_wfe: float = 0.0

    # Out-of-sample metrics
    total_oos_sharpe: float = 0.0
    total_oos_profit: float = 0.0
    total_oos_drawdown: float = 0.0
    total_oos_win_rate: float = 0.0

    # Consistency checks
    oos_periods_profitable: int = 0
    oos_periods_total: int = 0

    def is_strategy_robust(self) -> bool:
        """
        Determine if strategy passes robustness criteria

        Returns:
            True if strategy is robust (WFE > 50%, consistent OOS performance)
        """
        return (
            self.average_wfe >= self.config.min_wfe and
            self.total_oos_sharpe >= self.config.min_oos_sharpe and
            self.total_oos_drawdown <= self.config.max_oos_drawdown and
            (self.oos_periods_profitable / max(self.oos_periods_total, 1)) >= 0.60  # 60%+ periods profitable
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert results to dictionary for serialization"""
        return {
            'config': {
                'total_periods': self.config.total_periods,
                'in_sample_ratio': self.config.in_sample_ratio,
                'metric_to_optimize': self.config.metric_to_optimize,
            },
            'aggregate_metrics': {
                'average_wfe': round(self.average_wfe, 3),
                'median_wfe': round(self.median_wfe, 3),
                'worst_wfe': round(self.worst_wfe, 3),
                'best_wfe': round(self.best_wfe, 3),
            },
            'out_of_sample_performance': {
                'sharpe_ratio': round(self.total_oos_sharpe, 3),
                'total_profit': round(self.total_oos_profit, 2),
                'max_drawdown': round(self.total_oos_drawdown, 3),
                'win_rate': round(self.total_oos_win_rate, 3),
            },
            'consistency': {
                'profitable_periods': self.oos_periods_profitable,
                'total_periods': self.oos_periods_total,
                'consistency_ratio': round(self.oos_periods_profitable / max(self.oos_periods_total, 1), 3),
            },
            'is_robust': self.is_strategy_robust(),
            'periods': [
                {
                    'period': p.period_number,
                    'is_dates': f"{p.is_start_date.strftime('%Y-%m-%d')} to {p.is_end_date.strftime('%Y-%m-%d')}",
                    'oos_dates': f"{p.oos_start_date.strftime('%Y-%m-%d')} to {p.oos_end_date.strftime('%Y-%m-%d')}",
                    'optimal_params': p.optimal_parameters,
                    'is_sharpe': round(p.is_performance.get('sharpe_ratio', 0), 3),
                    'oos_sharpe': round(p.oos_performance.get('sharpe_ratio', 0), 3),
                    'wfe': round(p.oos_performance.get('sharpe_ratio', 0) / max(p.is_performance.get('sharpe_ratio', 0.01), 0.01), 3),
                }
                for p in self.periods
            ]
        }


class WalkForwardOptimizer:
    """
    Walk-Forward Optimization Engine

    Implements professional-grade rolling window optimization to prevent overfitting.

    Usage:
        optimizer = WalkForwardOptimizer(config)
        results = optimizer.optimize(
            data=historical_data,
            strategy_func=my_strategy,
            parameter_space=param_space
        )

        if results.is_strategy_robust():
            print("Strategy is robust for live trading!")
        else:
            print(f"Strategy failed: WFE = {results.average_wfe:.2%}")
    """

    def __init__(self, config: Optional[WalkForwardConfig] = None):
        """Initialize walk-forward optimizer with configuration"""
        self.config = config or WalkForwardConfig()
        logger.info(f"Initialized WalkForwardOptimizer with {self.config.total_periods} periods")

    def create_periods(
        self,
        data: pd.DataFrame,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[WalkForwardPeriod]:
        """
        Create rolling walk-forward periods from historical data

        Args:
            data: Historical OHLCV data with datetime index
            start_date: Optional start date (default: first date in data)
            end_date: Optional end date (default: last date in data)

        Returns:
            List of WalkForwardPeriod objects with IS/OOS data splits
        """
        # Determine date range
        if start_date is None:
            start_date = data.index[0]
        if end_date is None:
            end_date = data.index[-1]

        total_days = (end_date - start_date).days

        # Calculate period lengths
        days_per_period = total_days // self.config.total_periods
        is_days = int(days_per_period * self.config.in_sample_ratio)
        oos_days = days_per_period - is_days

        logger.info(f"Creating {self.config.total_periods} periods: {is_days} IS days + {oos_days} OOS days each")

        periods = []
        current_start = start_date

        for period_num in range(1, self.config.total_periods + 1):
            # Calculate period boundaries
            is_start = current_start
            is_end = is_start + timedelta(days=is_days)
            oos_start = is_end
            oos_end = oos_start + timedelta(days=oos_days)

            # Extract data for this period
            is_data = data[(data.index >= is_start) & (data.index < is_end)].copy()
            oos_data = data[(data.index >= oos_start) & (data.index < oos_end)].copy()

            period = WalkForwardPeriod(
                period_number=period_num,
                is_start_date=is_start,
                is_end_date=is_end,
                oos_start_date=oos_start,
                oos_end_date=oos_end,
                is_data=is_data,
                oos_data=oos_data
            )

            periods.append(period)
            logger.debug(f"Period {period_num}: IS={len(is_data)} bars, OOS={len(oos_data)} bars")

            # Move to next period (with slight overlap for continuity)
            current_start = oos_end - timedelta(days=oos_days // 4)  # 25% overlap

        return periods

    def optimize_single_period(
        self,
        period: WalkForwardPeriod,
        strategy_func: Callable,
        parameter_space: Dict[str, List[Any]],
        backtest_engine: Any
    ) -> WalkForwardPeriod:
        """
        Optimize a single walk-forward period

        Args:
            period: WalkForwardPeriod to optimize
            strategy_func: Strategy function that takes parameters and returns signals
            parameter_space: Dictionary of parameter names and possible values
            backtest_engine: Backtesting engine to run simulations

        Returns:
            WalkForwardPeriod with optimal parameters and performance metrics
        """
        logger.info(f"Optimizing Period {period.period_number}...")

        # Step 1: Grid search on in-sample data to find optimal parameters
        best_params = None
        best_is_metric = -np.inf

        # Generate all parameter combinations
        param_combinations = self._generate_parameter_combinations(parameter_space)
        logger.info(f"  Testing {len(param_combinations)} parameter combinations on IS data...")

        for params in param_combinations:
            # Run backtest on in-sample data
            is_results = backtest_engine.run(
                data=period.is_data,
                strategy_params=params
            )

            # Check minimum trades requirement
            if is_results.get('total_trades', 0) < self.config.min_trades_per_period:
                continue

            # Get optimization metric
            is_metric = is_results.get(self.config.metric_to_optimize, 0)

            if is_metric > best_is_metric:
                best_is_metric = is_metric
                best_params = params

        if best_params is None:
            logger.warning(f"  Period {period.period_number}: No valid parameters found!")
            return period

        # Step 2: Run optimal parameters on in-sample data (final IS results)
        is_final_results = backtest_engine.run(
            data=period.is_data,
            strategy_params=best_params
        )

        # Step 3: Validate on out-of-sample data
        oos_results = backtest_engine.run(
            data=period.oos_data,
            strategy_params=best_params
        )

        # Calculate Walk-Forward Efficiency for this period
        is_metric_value = is_final_results.get(self.config.metric_to_optimize, 0.01)
        oos_metric_value = oos_results.get(self.config.metric_to_optimize, 0)
        wfe = oos_metric_value / max(is_metric_value, 0.01)

        # Store results in period
        period.optimal_parameters = best_params
        period.is_performance = {
            'sharpe_ratio': is_final_results.get('sharpe_ratio', 0),
            'total_return': is_final_results.get('total_return', 0),
            'max_drawdown': is_final_results.get('max_drawdown', 0),
            'win_rate': is_final_results.get('win_rate', 0),
            'total_trades': is_final_results.get('total_trades', 0),
        }
        period.oos_performance = {
            'sharpe_ratio': oos_results.get('sharpe_ratio', 0),
            'total_return': oos_results.get('total_return', 0),
            'max_drawdown': oos_results.get('max_drawdown', 0),
            'win_rate': oos_results.get('win_rate', 0),
            'total_trades': oos_results.get('total_trades', 0),
            'wfe': wfe,
        }

        logger.info(f"  Period {period.period_number} Results:")
        logger.info(f"    Optimal Params: {best_params}")
        logger.info(f"    IS Sharpe: {is_final_results.get('sharpe_ratio', 0):.3f}")
        logger.info(f"    OOS Sharpe: {oos_results.get('sharpe_ratio', 0):.3f}")
        logger.info(f"    WFE: {wfe:.3f} ({'PASS' if wfe >= self.config.min_wfe else 'FAIL'})")

        return period

    def optimize(
        self,
        data: pd.DataFrame,
        strategy_func: Callable,
        parameter_space: Dict[str, List[Any]],
        backtest_engine: Any,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> WalkForwardResults:
        """
        Run complete walk-forward optimization

        Args:
            data: Historical OHLCV data with datetime index
            strategy_func: Strategy function
            parameter_space: Dictionary of parameters to optimize
            backtest_engine: Backtesting engine instance
            start_date: Optional start date
            end_date: Optional end date

        Returns:
            WalkForwardResults with complete analysis
        """
        logger.info("="*60)
        logger.info("WALK-FORWARD OPTIMIZATION STARTING")
        logger.info("="*60)

        # Create rolling periods
        periods = self.create_periods(data, start_date, end_date)

        # Optimize each period
        optimized_periods = []
        for period in periods:
            optimized_period = self.optimize_single_period(
                period=period,
                strategy_func=strategy_func,
                parameter_space=parameter_space,
                backtest_engine=backtest_engine
            )
            optimized_periods.append(optimized_period)

        # Calculate aggregate metrics
        results = self._calculate_aggregate_metrics(optimized_periods)

        logger.info("="*60)
        logger.info("WALK-FORWARD OPTIMIZATION COMPLETE")
        logger.info(f"Average WFE: {results.average_wfe:.3f}")
        logger.info(f"OOS Sharpe: {results.total_oos_sharpe:.3f}")
        logger.info(f"Strategy Robust: {'YES ✅' if results.is_strategy_robust() else 'NO ❌'}")
        logger.info("="*60)

        return results

    def _generate_parameter_combinations(self, parameter_space: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
        """Generate all possible parameter combinations from parameter space"""
        import itertools

        # Get parameter names and values
        param_names = list(parameter_space.keys())
        param_values = [parameter_space[name] for name in param_names]

        # Generate all combinations
        combinations = []
        for combination in itertools.product(*param_values):
            param_dict = dict(zip(param_names, combination))
            combinations.append(param_dict)

        return combinations

    def _calculate_aggregate_metrics(self, periods: List[WalkForwardPeriod]) -> WalkForwardResults:
        """Calculate aggregate metrics across all periods"""

        # Extract WFE values
        wfe_values = [p.oos_performance.get('wfe', 0) for p in periods if p.oos_performance.get('wfe')]

        # Extract OOS metrics
        oos_sharpe_values = [p.oos_performance.get('sharpe_ratio', 0) for p in periods]
        oos_profit_values = [p.oos_performance.get('total_return', 0) for p in periods]
        oos_drawdown_values = [p.oos_performance.get('max_drawdown', 0) for p in periods]
        oos_winrate_values = [p.oos_performance.get('win_rate', 0) for p in periods]

        # Count profitable OOS periods
        profitable_periods = sum(1 for p in oos_profit_values if p > 0)

        results = WalkForwardResults(
            config=self.config,
            periods=periods,
            average_wfe=np.mean(wfe_values) if wfe_values else 0,
            median_wfe=np.median(wfe_values) if wfe_values else 0,
            worst_wfe=np.min(wfe_values) if wfe_values else 0,
            best_wfe=np.max(wfe_values) if wfe_values else 0,
            total_oos_sharpe=np.mean(oos_sharpe_values),
            total_oos_profit=np.sum(oos_profit_values),
            total_oos_drawdown=np.mean(oos_drawdown_values),
            total_oos_win_rate=np.mean(oos_winrate_values),
            oos_periods_profitable=profitable_periods,
            oos_periods_total=len(periods),
        )

        return results

    def save_results(self, results: WalkForwardResults, filepath: str):
        """Save walk-forward results to JSON file"""
        with open(filepath, 'w') as f:
            json.dump(results.to_dict(), f, indent=2)
        logger.info(f"Saved walk-forward results to {filepath}")

    def load_results(self, filepath: str) -> Dict[str, Any]:
        """Load walk-forward results from JSON file"""
        with open(filepath, 'r') as f:
            results_dict = json.load(f)
        logger.info(f"Loaded walk-forward results from {filepath}")
        return results_dict


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example: Create walk-forward optimizer
    config = WalkForwardConfig(
        total_periods=5,
        in_sample_ratio=0.70,
        metric_to_optimize='sharpe_ratio',
        min_wfe=0.50
    )

    optimizer = WalkForwardOptimizer(config)
    print(f"Walk-Forward Optimizer initialized with {config.total_periods} periods")
    print(f"Target WFE: {config.min_wfe:.0%}+")
