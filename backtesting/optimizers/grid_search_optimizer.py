"""
Grid Search Parameter Optimizer
Created: 2025-12-06
Purpose: Exhaustive parameter search across all combinations

Grid Search tests EVERY possible parameter combination:
- Systematic: Tests all combinations systematically
- Thorough: Guarantees finding global optimum in search space
- Simple: Easy to understand and interpret
- Slow: Can be computationally expensive for large spaces

Best for:
- Small parameter spaces (< 10,000 combinations)
- When you need to be certain of finding the best combination
- Creating parameter heatmaps and sensitivity analysis
"""

import logging
from typing import Dict, List, Any, Optional, Tuple, Callable
from dataclasses import dataclass, field
import numpy as np
import pandas as pd
import itertools
from concurrent.futures import ProcessPoolExecutor, as_completed, ThreadPoolExecutor
import json
from tqdm import tqdm
import time

logger = logging.getLogger(__name__)


@dataclass
class GridSearchConfig:
    """Configuration for grid search optimization"""

    # Performance metric
    metric_to_optimize: str = 'sharpe_ratio'  # Primary optimization metric
    min_trades: int = 10  # Minimum trades required for valid result

    # Parallel processing
    max_workers: int = 4  # CPU cores for parallel execution
    use_threading: bool = False  # Use threads instead of processes (for I/O bound)

    # Progress reporting
    show_progress: bool = True  # Display progress bar
    log_interval: int = 100  # Log every N combinations

    # Result filtering
    min_sharpe: float = 0.5  # Filter results below this Sharpe
    max_drawdown: float = 0.30  # Filter results with drawdown > 30%


@dataclass
class GridSearchResult:
    """Single grid search result"""
    parameters: Dict[str, Any]
    metrics: Dict[str, float]
    rank: int = 0

    @property
    def fitness(self) -> float:
        """Get primary fitness metric"""
        return self.metrics.get('sharpe_ratio', 0)


@dataclass
class GridSearchResults:
    """Complete grid search optimization results"""
    config: GridSearchConfig
    all_results: List[GridSearchResult]
    best_result: GridSearchResult
    parameter_ranges: Dict[str, Any]

    # Statistics
    total_combinations: int = 0
    valid_combinations: int = 0
    execution_time_seconds: float = 0.0

    def get_top_n(self, n: int = 10) -> List[GridSearchResult]:
        """Get top N results by fitness"""
        return sorted(self.all_results, key=lambda r: r.fitness, reverse=True)[:n]

    def get_parameter_statistics(self, param_name: str) -> Dict[str, Any]:
        """
        Get statistics for a specific parameter

        Shows which values of the parameter performed best

        Returns:
            Dict with mean/median/best metrics for each parameter value
        """
        # Group results by parameter value
        param_groups = {}
        for result in self.all_results:
            param_value = result.parameters[param_name]
            if param_value not in param_groups:
                param_groups[param_value] = []
            param_groups[param_value].append(result.fitness)

        # Calculate statistics
        statistics = {}
        for value, fitness_values in param_groups.items():
            statistics[value] = {
                'mean_sharpe': round(np.mean(fitness_values), 4),
                'median_sharpe': round(np.median(fitness_values), 4),
                'max_sharpe': round(np.max(fitness_values), 4),
                'min_sharpe': round(np.min(fitness_values), 4),
                'count': len(fitness_values)
            }

        return statistics

    def create_heatmap_data(
        self,
        param1: str,
        param2: str,
        metric: str = 'sharpe_ratio'
    ) -> pd.DataFrame:
        """
        Create heatmap data for two parameters

        Args:
            param1: First parameter name (X-axis)
            param2: Second parameter name (Y-axis)
            metric: Metric to display (default: sharpe_ratio)

        Returns:
            DataFrame with parameter values as index/columns and metric as values
        """
        # Extract unique values for each parameter
        param1_values = sorted(set(r.parameters[param1] for r in self.all_results))
        param2_values = sorted(set(r.parameters[param2] for r in self.all_results))

        # Create empty matrix
        heatmap = pd.DataFrame(
            index=param2_values,
            columns=param1_values,
            dtype=float
        )

        # Fill matrix with metric values
        for result in self.all_results:
            row = result.parameters[param2]
            col = result.parameters[param1]
            value = result.metrics.get(metric, np.nan)
            heatmap.loc[row, col] = value

        return heatmap

    def to_dict(self) -> Dict[str, Any]:
        """Convert results to dictionary"""
        return {
            'config': {
                'metric_to_optimize': self.config.metric_to_optimize,
                'min_trades': self.config.min_trades,
            },
            'statistics': {
                'total_combinations': self.total_combinations,
                'valid_combinations': self.valid_combinations,
                'execution_time_seconds': round(self.execution_time_seconds, 2),
                'combinations_per_second': round(self.total_combinations / max(self.execution_time_seconds, 1), 2),
            },
            'best_result': {
                'parameters': self.best_result.parameters,
                'metrics': {k: round(v, 4) for k, v in self.best_result.metrics.items()},
            },
            'top_10_results': [
                {
                    'rank': i + 1,
                    'parameters': r.parameters,
                    'sharpe_ratio': round(r.metrics.get('sharpe_ratio', 0), 4),
                    'total_return': round(r.metrics.get('total_return', 0), 4),
                    'max_drawdown': round(r.metrics.get('max_drawdown', 0), 4),
                }
                for i, r in enumerate(self.get_top_n(10))
            ]
        }


class GridSearchOptimizer:
    """
    Grid Search Parameter Optimizer

    Exhaustively tests all parameter combinations to find optimal settings.

    Usage:
        config = GridSearchConfig(metric_to_optimize='sharpe_ratio')
        optimizer = GridSearchOptimizer(config)

        parameter_grid = {
            'rsi_period': [6, 10, 14, 20],
            'rsi_oversold': [20, 25, 30],
            'rsi_overbought': [70, 75, 80],
            'macd_fast': [5, 8, 12],
            'macd_slow': [21, 26, 35],
            'stop_loss_atr': [1.5, 2.0, 2.5, 3.0],
        }

        results = optimizer.optimize(
            data=historical_data,
            parameter_grid=parameter_grid,
            backtest_engine=engine
        )

        print(f"Best parameters: {results.best_result.parameters}")
        print(f"Best Sharpe: {results.best_result.fitness:.4f}")

        # Analyze parameter sensitivity
        rsi_stats = results.get_parameter_statistics('rsi_period')
        print(f"RSI period statistics: {rsi_stats}")
    """

    def __init__(self, config: Optional[GridSearchConfig] = None):
        """Initialize grid search optimizer"""
        self.config = config or GridSearchConfig()
        logger.info(f"Initialized GridSearchOptimizer")

    def generate_parameter_combinations(
        self,
        parameter_grid: Dict[str, List[Any]]
    ) -> List[Dict[str, Any]]:
        """
        Generate all possible parameter combinations

        Args:
            parameter_grid: Dict of {param_name: [list of values to test]}

        Returns:
            List of all parameter combinations
        """
        param_names = list(parameter_grid.keys())
        param_values = [parameter_grid[name] for name in param_names]

        # Generate cartesian product
        combinations = []
        for combination in itertools.product(*param_values):
            param_dict = dict(zip(param_names, combination))
            combinations.append(param_dict)

        total = len(combinations)
        logger.info(f"Generated {total:,} parameter combinations")

        # Log parameter space
        for param_name, values in parameter_grid.items():
            logger.info(f"  {param_name}: {len(values)} values {values}")

        return combinations

    def evaluate_combination(
        self,
        parameters: Dict[str, Any],
        backtest_engine: Any,
        data: Any
    ) -> Optional[GridSearchResult]:
        """
        Evaluate a single parameter combination

        Args:
            parameters: Parameter set to evaluate
            backtest_engine: Backtesting engine
            data: Historical data

        Returns:
            GridSearchResult or None if invalid
        """
        try:
            # Run backtest
            results = backtest_engine.run(
                data=data,
                strategy_params=parameters
            )

            # Check minimum trades requirement
            if results.get('total_trades', 0) < self.config.min_trades:
                return None

            # Check quality filters
            sharpe = results.get('sharpe_ratio', 0)
            drawdown = results.get('max_drawdown', 1.0)

            if sharpe < self.config.min_sharpe or drawdown > self.config.max_drawdown:
                return None

            # Create result
            result = GridSearchResult(
                parameters=parameters,
                metrics={
                    'sharpe_ratio': sharpe,
                    'total_return': results.get('total_return', 0),
                    'max_drawdown': drawdown,
                    'win_rate': results.get('win_rate', 0),
                    'profit_factor': results.get('profit_factor', 0),
                    'total_trades': results.get('total_trades', 0),
                }
            )

            return result

        except Exception as e:
            logger.error(f"Error evaluating combination {parameters}: {e}")
            return None

    def optimize(
        self,
        data: Any,
        parameter_grid: Dict[str, List[Any]],
        backtest_engine: Any
    ) -> GridSearchResults:
        """
        Run complete grid search optimization

        Args:
            data: Historical data for backtesting
            parameter_grid: Dict of parameter names and value lists
            backtest_engine: Backtesting engine

        Returns:
            GridSearchResults with all tested combinations
        """
        logger.info("="*60)
        logger.info("GRID SEARCH OPTIMIZATION STARTING")
        logger.info("="*60)

        start_time = time.time()

        # Generate all combinations
        combinations = self.generate_parameter_combinations(parameter_grid)
        total_combinations = len(combinations)

        # Evaluate all combinations
        all_results = []

        if self.config.show_progress:
            progress_bar = tqdm(total=total_combinations, desc="Grid Search")

        evaluated_count = 0

        # Parallel processing
        if self.config.max_workers > 1:
            executor_class = ThreadPoolExecutor if self.config.use_threading else ProcessPoolExecutor

            with executor_class(max_workers=self.config.max_workers) as executor:
                # Submit all jobs
                futures = {
                    executor.submit(
                        self.evaluate_combination,
                        params,
                        backtest_engine,
                        data
                    ): params
                    for params in combinations
                }

                # Collect results as they complete
                for future in as_completed(futures):
                    result = future.result()
                    if result is not None:
                        all_results.append(result)

                    evaluated_count += 1

                    if self.config.show_progress:
                        progress_bar.update(1)

                    if evaluated_count % self.config.log_interval == 0:
                        logger.info(f"Evaluated {evaluated_count}/{total_combinations} combinations, found {len(all_results)} valid")

        else:
            # Sequential processing
            for i, params in enumerate(combinations):
                result = self.evaluate_combination(params, backtest_engine, data)
                if result is not None:
                    all_results.append(result)

                if self.config.show_progress:
                    progress_bar.update(1)

                if (i + 1) % self.config.log_interval == 0:
                    logger.info(f"Evaluated {i+1}/{total_combinations} combinations, found {len(all_results)} valid")

        if self.config.show_progress:
            progress_bar.close()

        # Find best result
        if len(all_results) == 0:
            raise ValueError("No valid results found! Adjust filtering criteria.")

        all_results.sort(key=lambda r: r.fitness, reverse=True)
        for i, result in enumerate(all_results):
            result.rank = i + 1

        best_result = all_results[0]

        # Calculate execution time
        execution_time = time.time() - start_time

        # Create results object
        results = GridSearchResults(
            config=self.config,
            all_results=all_results,
            best_result=best_result,
            parameter_ranges=parameter_grid,
            total_combinations=total_combinations,
            valid_combinations=len(all_results),
            execution_time_seconds=execution_time
        )

        logger.info("="*60)
        logger.info("GRID SEARCH OPTIMIZATION COMPLETE")
        logger.info(f"Total combinations tested: {total_combinations:,}")
        logger.info(f"Valid results: {len(all_results):,} ({len(all_results)/total_combinations*100:.1f}%)")
        logger.info(f"Execution time: {execution_time:.1f}s ({total_combinations/execution_time:.1f} combinations/sec)")
        logger.info(f"Best Sharpe: {best_result.fitness:.4f}")
        logger.info(f"Best parameters: {best_result.parameters}")
        logger.info("="*60)

        return results

    def save_results(self, results: GridSearchResults, filepath: str):
        """Save grid search results to JSON"""
        with open(filepath, 'w') as f:
            json.dump(results.to_dict(), f, indent=2)
        logger.info(f"Saved grid search results to {filepath}")

    def load_results(self, filepath: str) -> Dict[str, Any]:
        """Load grid search results from JSON"""
        with open(filepath, 'r') as f:
            results_dict = json.load(f)
        logger.info(f"Loaded grid search results from {filepath}")
        return results_dict


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example configuration
    config = GridSearchConfig(
        metric_to_optimize='sharpe_ratio',
        min_trades=10,
        max_workers=4,
        show_progress=True
    )

    optimizer = GridSearchOptimizer(config)

    # Example parameter grid
    parameter_grid = {
        'rsi_period': [6, 10, 14, 20],
        'rsi_oversold': [20, 25, 30, 35],
        'rsi_overbought': [65, 70, 75, 80],
        'stop_loss_pct': [0.02, 0.03, 0.04, 0.05],
    }

    # Calculate total combinations
    total = 1
    for values in parameter_grid.values():
        total *= len(values)

    print(f"Grid Search Optimizer initialized")
    print(f"Parameter grid: {parameter_grid}")
    print(f"Total combinations to test: {total:,}")
