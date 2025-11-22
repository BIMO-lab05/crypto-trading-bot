#!/usr/bin/env python3
"""
Advanced Parameter Optimization for SQZMOM Strategy
Purpose: Test multiple parameter combinations to find optimal settings for each symbol

Features:
- Grid search optimization across parameter space
- Multiple optimization metrics (Sharpe, return, win rate)
- Heatmap data generation for visualization
- Top-N parameter set tracking
- JSON export for results
- Comprehensive reporting

Usage:
    python3 optimize_parameters.py
"""

import asyncio
import asyncpg
from typing import Dict, List, Tuple, Optional
import pandas as pd
import numpy as np
from itertools import product
import json
from datetime import datetime
import logging

from sqzmom_backtest import SQZMOMBacktester

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ParameterOptimizer:
    """
    Advanced parameter optimization using grid search

    This optimizer tests all combinations of parameters and tracks
    the best performing sets for each optimization metric.

    Attributes:
        db_config: Database connection configuration
        backtester: SQZMOMBacktester instance for running tests
        results_cache: Cache of backtest results to avoid re-running
    """

    def __init__(self, db_config: Dict):
        """
        Initialize optimizer

        Args:
            db_config: Database connection configuration dict
        """
        self.db_config = db_config
        self.backtester = SQZMOMBacktester(
            db_config=db_config,
            initial_capital=10000.0,
            commission=0.001  # 0.1% commission per trade
        )
        self.results_cache = {}
        logger.info("ParameterOptimizer initialized")

    async def optimize_symbol(
        self,
        symbol: str,
        param_grid: Dict[str, List],
        optimize_for: str = "sharpe_ratio"  # or "total_return_pct" or "win_rate"
    ) -> Dict:
        """
        Run grid search optimization for a single symbol

        This method tests all possible combinations of parameters from the grid
        and finds the best set based on the optimization metric.

        Args:
            symbol: Trading pair (e.g., SOLUSDT)
            param_grid: Dictionary mapping parameter names to lists of values
                Example: {
                    'bb_length': [15, 20, 25],
                    'kc_length': [15, 20, 25],
                    'min_momentum_threshold': [0.2, 0.3, 0.4],
                    'stop_loss_pct': [1.0, 1.5, 2.0],
                    'take_profit_pct': [2.5, 3.0, 3.5]
                }
            optimize_for: Metric to optimize
                - 'sharpe_ratio': Best risk-adjusted return (recommended)
                - 'total_return_pct': Maximum absolute return
                - 'win_rate': Highest percentage of winning trades

        Returns:
            Dictionary containing:
            - best_params: The optimal parameter set
            - best_score: Value of the optimization metric for best params
            - all_results: List of all parameter combinations tested
            - top_10_results: Top 10 parameter sets by optimization metric
            - optimization_time_seconds: Time taken to complete
        """
        await self.backtester.connect_db()

        start_time = datetime.now()

        # Generate all parameter combinations (Cartesian product)
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        combinations = list(product(*param_values))

        total_combinations = len(combinations)
        logger.info(f"\n{'='*80}")
        logger.info(f"Optimizing {symbol}")
        logger.info(f"Testing {total_combinations} parameter combinations")
        logger.info(f"Optimizing for: {optimize_for}")
        logger.info(f"{'='*80}\n")

        results = []
        best_score = -float('inf')
        best_params = None

        # Test each parameter combination
        for idx, combo in enumerate(combinations, 1):
            # Build parameter dictionary from combination
            params = dict(zip(param_names, combo))

            # Create full strategy parameter set with defaults for missing values
            strategy_params = {
                'bb_length': params.get('bb_length', 20),
                'kc_length': params.get('kc_length', 20),
                'min_momentum_threshold': params.get('min_momentum_threshold', 0.3),
                'stop_loss_pct': params.get('stop_loss_pct', 1.5),
                'take_profit_pct': params.get('take_profit_pct', 3.0),
                'require_squeeze_release': False,  # More trades for testing
                'require_volume_confirmation': False
            }

            # Create cache key from parameters
            cache_key = f"{symbol}_{json.dumps(strategy_params, sort_keys=True)}"

            # Check cache first
            if cache_key in self.results_cache:
                result = self.results_cache[cache_key]
            else:
                # Run backtest with these parameters
                try:
                    result = await self.backtester.run_backtest(
                        symbol=symbol,
                        strategy_params=strategy_params,
                        verbose=False
                    )

                    # Cache the result
                    self.results_cache[cache_key] = result

                except Exception as e:
                    logger.error(f"Error with params {params}: {e}")
                    continue

            # Get optimization metric score
            score = result.get(optimize_for, 0)

            # Handle special cases (e.g., negative Sharpe ratios)
            if optimize_for == 'sharpe_ratio' and score < -10:
                score = -10  # Cap extremely negative Sharpe ratios

            # Store result
            result_entry = {
                'params': params,
                'full_params': strategy_params,
                'total_return_pct': result['total_return_pct'],
                'sharpe_ratio': result['sharpe_ratio'],
                'win_rate': result['win_rate'],
                'max_drawdown': result['max_drawdown'],
                'total_trades': result['total_trades'],
                'profit_factor': result.get('profit_factor', 0),
                'avg_win': result['avg_win'],
                'avg_loss': result['avg_loss'],
                'optimization_score': score
            }
            results.append(result_entry)

            # Update best if this is better
            if score > best_score:
                best_score = score
                best_params = params.copy()
                logger.info(f"✨ New best found at combination {idx}/{total_combinations}!")
                logger.info(f"   {optimize_for} = {score:.2f}")
                logger.info(f"   Params: {params}")
                logger.info(f"   Return: {result['total_return_pct']:.2f}%, WR: {result['win_rate']:.2f}%, Trades: {result['total_trades']}")

            # Progress update every 10 combinations
            if idx % 10 == 0:
                logger.info(f"Progress: {idx}/{total_combinations} ({idx/total_combinations*100:.1f}%)")

        end_time = datetime.now()
        elapsed = (end_time - start_time).total_seconds()

        # Sort results by optimization metric (best first)
        results.sort(key=lambda x: x.get('optimization_score', -float('inf')), reverse=True)

        # Build optimization result
        optimization_result = {
            'symbol': symbol,
            'optimize_for': optimize_for,
            'best_params': best_params,
            'best_score': best_score,
            'total_combinations_tested': total_combinations,
            'optimization_time_seconds': elapsed,
            'top_10_results': results[:10],  # Top 10 parameter sets
            'all_results': results  # All results for further analysis
        }

        await self.backtester.close()

        logger.info(f"\nOptimization complete: Best {optimize_for} = {best_score:.2f}")

        return optimization_result

    def create_heatmap_data(
        self,
        results: List[Dict],
        param1: str,
        param2: str,
        metric: str = "total_return_pct"
    ) -> pd.DataFrame:
        """
        Create 2D heatmap data for visualizing parameter relationships

        This helps visualize how two parameters interact and affect performance.

        Args:
            results: List of backtest results from optimization
            param1: First parameter name (will be x-axis)
            param2: Second parameter name (will be y-axis)
            metric: Metric to plot as heatmap values

        Returns:
            DataFrame with param1 as columns, param2 as rows, metric as values
        """
        data = []
        for r in results:
            data.append({
                param1: r['params'][param1],
                param2: r['params'][param2],
                metric: r[metric]
            })

        df = pd.DataFrame(data)

        # Create pivot table (heatmap format)
        heatmap = df.pivot_table(
            index=param2,
            columns=param1,
            values=metric,
            aggfunc='mean'  # Average if multiple values for same combination
        )

        return heatmap

    def save_results(self, results: Dict, filename: str):
        """
        Save optimization results to JSON file

        Args:
            results: Optimization results dictionary
            filename: Path to save JSON file
        """
        # Convert any non-serializable objects
        def convert(obj):
            if isinstance(obj, (np.integer, np.floating)):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            return obj

        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=convert)

        logger.info(f"Results saved to: {filename}")

    def analyze_parameter_sensitivity(
        self,
        results: List[Dict],
        param_name: str,
        metric: str = "total_return_pct"
    ) -> Dict:
        """
        Analyze how sensitive performance is to a single parameter

        This helps identify which parameters have the biggest impact on performance.

        Args:
            results: List of backtest results
            param_name: Parameter to analyze
            metric: Performance metric to measure

        Returns:
            Dictionary with sensitivity analysis:
            - mean_by_value: Average metric for each parameter value
            - std_by_value: Standard deviation for each value
            - best_value: Parameter value with best average performance
            - sensitivity_score: How much performance varies (higher = more sensitive)
        """
        # Group results by parameter value
        by_value = {}
        for r in results:
            value = r['params'][param_name]
            if value not in by_value:
                by_value[value] = []
            by_value[value].append(r[metric])

        # Calculate statistics for each value
        stats = {}
        for value, metrics in by_value.items():
            stats[value] = {
                'mean': np.mean(metrics),
                'std': np.std(metrics),
                'min': np.min(metrics),
                'max': np.max(metrics),
                'count': len(metrics)
            }

        # Find best value
        best_value = max(stats.keys(), key=lambda v: stats[v]['mean'])

        # Calculate sensitivity score (range of means)
        means = [stats[v]['mean'] for v in stats]
        sensitivity_score = max(means) - min(means)

        return {
            'param_name': param_name,
            'metric': metric,
            'stats_by_value': stats,
            'best_value': best_value,
            'sensitivity_score': sensitivity_score
        }


async def optimize_all_symbols():
    """
    Optimize parameters for all three profitable symbols

    This function runs comprehensive optimization on SOLUSDT, DOGEUSDT, and BNBUSDT
    to find the best parameters for each symbol.
    """
    # Database configuration
    db_config = {
        'host': 'localhost',
        'port': 5433,
        'database': 'market_data',
        'user': 'cryptobot',
        'password': 'timescale_dev_password'
    }

    optimizer = ParameterOptimizer(db_config)

    # Define parameter grid to search
    # This is a comprehensive grid that will test 1,600 combinations per symbol
    param_grid = {
        'bb_length': [15, 20, 25, 30],
        'kc_length': [15, 20, 25, 30],
        'min_momentum_threshold': [0.2, 0.3, 0.4, 0.5],
        'stop_loss_pct': [1.0, 1.5, 2.0, 2.5, 3.0],
        'take_profit_pct': [2.5, 3.0, 3.5, 4.0, 5.0]
    }

    # Calculate total combinations
    total_combos = 1
    for values in param_grid.values():
        total_combos *= len(values)

    logger.info(f"\n{'#'*80}")
    logger.info(f"# ADVANCED PARAMETER OPTIMIZATION")
    logger.info(f"{'#'*80}")
    logger.info(f"Total parameter combinations to test: {total_combos}")
    logger.info(f"Grid breakdown: 4×4×4×5×5 = {total_combos} backtests per symbol")
    logger.info(f"Symbols to optimize: SOLUSDT, DOGEUSDT, BNBUSDT")
    logger.info(f"Optimization metric: Sharpe Ratio (risk-adjusted return)")
    logger.info(f"{'#'*80}\n")

    # Symbols to optimize (the three profitable ones)
    symbols = ['SOLUSDT', 'DOGEUSDT', 'BNBUSDT']

    all_optimization_results = {}

    # Optimize each symbol
    for symbol in symbols:
        logger.info(f"\n\n{'#'*80}")
        logger.info(f"# OPTIMIZING {symbol}")
        logger.info(f"{'#'*80}")

        # Optimize for Sharpe ratio (best risk-adjusted return)
        result = await optimizer.optimize_symbol(
            symbol=symbol,
            param_grid=param_grid,
            optimize_for='sharpe_ratio'  # Change to 'total_return_pct' for max return
        )

        all_optimization_results[symbol] = result

        # Save individual symbol results
        optimizer.save_results(
            result,
            f'/mnt/d/Bimo_max/crypto-trading-bot/services/technical-analysis/backtesting/optimization_{symbol}.json'
        )

        # Print detailed summary
        logger.info(f"\n{'='*80}")
        logger.info(f"{symbol} OPTIMIZATION COMPLETE")
        logger.info(f"{'='*80}")
        logger.info(f"Best Sharpe Ratio: {result['best_score']:.2f}")
        logger.info(f"Optimization Time: {result['optimization_time_seconds']:.1f} seconds")
        logger.info(f"\nBest Parameters:")
        for key, value in result['best_params'].items():
            logger.info(f"  {key:30} = {value}")

        # Show top 5 parameter sets
        logger.info(f"\nTop 5 Parameter Sets:")
        logger.info(f"{'Rank':<6} {'Return %':<10} {'Sharpe':<8} {'Win Rate %':<12} {'Trades':<8} {'Max DD %':<10}")
        logger.info("-" * 70)

        for idx, r in enumerate(result['top_10_results'][:5], 1):
            logger.info(
                f"{idx:<6} "
                f"{r['total_return_pct']:<10.2f} "
                f"{r['sharpe_ratio']:<8.2f} "
                f"{r['win_rate']:<12.2f} "
                f"{r['total_trades']:<8} "
                f"{r['max_drawdown']:<10.2f}"
            )

        # Analyze parameter sensitivity
        logger.info(f"\nParameter Sensitivity Analysis:")
        for param in param_grid.keys():
            sensitivity = optimizer.analyze_parameter_sensitivity(
                result['all_results'],
                param,
                'total_return_pct'
            )
            logger.info(
                f"  {param:30} - Best value: {sensitivity['best_value']:<6} "
                f"(Sensitivity: {sensitivity['sensitivity_score']:.2f}%)"
            )

    # Save combined results
    optimizer.save_results(
        all_optimization_results,
        '/mnt/d/Bimo_max/crypto-trading-bot/services/technical-analysis/backtesting/all_optimizations.json'
    )

    # Create comprehensive summary report
    create_optimization_report(all_optimization_results)

    return all_optimization_results


def create_optimization_report(results: Dict):
    """
    Create detailed markdown report comparing optimization results across symbols

    Args:
        results: Dictionary mapping symbols to their optimization results
    """
    report = []
    report.append("# Parameter Optimization Results - SQZMOM Strategy")
    report.append("")
    report.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    report.append("---")
    report.append("")

    # Executive Summary
    report.append("## Executive Summary")
    report.append("")
    report.append("This report presents the results of comprehensive parameter optimization ")
    report.append("for the Squeeze Momentum (SQZMOM) trading strategy on three profitable symbols.")
    report.append("")

    total_combinations = sum(data['total_combinations_tested'] for data in results.values())
    total_time = sum(data['optimization_time_seconds'] for data in results.values())

    report.append(f"- **Symbols Optimized:** {', '.join(results.keys())}")
    report.append(f"- **Total Combinations Tested:** {total_combinations:,}")
    report.append(f"- **Total Optimization Time:** {total_time:.1f} seconds ({total_time/60:.1f} minutes)")
    report.append(f"- **Optimization Metric:** Sharpe Ratio (risk-adjusted return)")
    report.append("")
    report.append("---")
    report.append("")

    # Individual Symbol Results
    for symbol, data in results.items():
        report.append(f"## {symbol}")
        report.append("")
        report.append(f"**Optimization Metric:** {data['optimize_for']}")
        report.append(f"**Best Score:** {data['best_score']:.2f}")
        report.append(f"**Combinations Tested:** {data['total_combinations_tested']:,}")
        report.append(f"**Time:** {data['optimization_time_seconds']:.1f} seconds")
        report.append("")

        # Best parameters
        report.append("### Best Parameters")
        report.append("")
        report.append("```python")
        report.append("{")
        for key, value in data['best_params'].items():
            report.append(f"    '{key}': {value},")
        report.append("}")
        report.append("```")
        report.append("")

        # Performance with best parameters
        best_result = data['top_10_results'][0]
        report.append("### Performance with Best Parameters")
        report.append("")
        report.append(f"- **Total Return:** {best_result['total_return_pct']:.2f}%")
        report.append(f"- **Sharpe Ratio:** {best_result['sharpe_ratio']:.2f}")
        report.append(f"- **Win Rate:** {best_result['win_rate']:.2f}%")
        report.append(f"- **Total Trades:** {best_result['total_trades']}")
        report.append(f"- **Profit Factor:** {best_result['profit_factor']:.2f}")
        report.append(f"- **Max Drawdown:** {best_result['max_drawdown']:.2f}%")
        report.append(f"- **Average Win:** ${best_result['avg_win']:.2f}")
        report.append(f"- **Average Loss:** ${best_result['avg_loss']:.2f}")
        report.append("")

        # Top 5 results table
        report.append("### Top 5 Parameter Sets")
        report.append("")
        report.append("| Rank | Return % | Sharpe | Win Rate % | Trades | Max DD % | Profit Factor |")
        report.append("|------|----------|--------|------------|--------|----------|---------------|")

        for idx, r in enumerate(data['top_10_results'][:5], 1):
            report.append(
                f"| {idx} | {r['total_return_pct']:.1f} | {r['sharpe_ratio']:.2f} | "
                f"{r['win_rate']:.1f} | {r['total_trades']} | {r['max_drawdown']:.1f} | "
                f"{r['profit_factor']:.2f} |"
            )

        report.append("")
        report.append("---")
        report.append("")

    # Comparison Table
    report.append("## Cross-Symbol Comparison")
    report.append("")
    report.append("| Symbol | Best Sharpe | Best Return % | Win Rate % | Trades | Best Parameters |")
    report.append("|--------|-------------|---------------|------------|--------|-----------------|")

    for symbol, data in results.items():
        best = data['top_10_results'][0]
        params_str = ', '.join([f"{k}={v}" for k, v in data['best_params'].items()])
        if len(params_str) > 40:
            params_str = params_str[:37] + "..."

        report.append(
            f"| {symbol} | {best['sharpe_ratio']:.2f} | {best['total_return_pct']:.1f} | "
            f"{best['win_rate']:.1f} | {best['total_trades']} | {params_str} |"
        )

    report.append("")

    # Key Insights
    report.append("## Key Insights")
    report.append("")

    # Find best overall performer
    best_symbol = max(results.items(), key=lambda x: x[1]['best_score'])
    report.append(f"1. **Best Overall Performance:** {best_symbol[0]} with Sharpe ratio of {best_symbol[1]['best_score']:.2f}")
    report.append("")

    # Check if different symbols need different parameters
    all_params = [data['best_params'] for data in results.values()]
    if len(set(str(p) for p in all_params)) == 1:
        report.append("2. **Parameter Consistency:** All symbols perform best with the same parameters")
    else:
        report.append("2. **Parameter Variation:** Different symbols require different optimal parameters")
        report.append("   - This suggests symbol-specific optimization is beneficial")
    report.append("")

    # Recommendations
    report.append("## Recommendations")
    report.append("")
    report.append("### For Production Deployment")
    report.append("")
    report.append("1. **Use Symbol-Specific Parameters:** Each symbol has its own optimal configuration")
    report.append("2. **Monitor Performance:** Continue tracking if optimized parameters remain effective")
    report.append("3. **Re-optimize Periodically:** Market conditions change; re-run optimization monthly")
    report.append("4. **Risk Management:** Maintain 2% risk per trade regardless of parameters")
    report.append("")

    report.append("### Configuration Files")
    report.append("")
    report.append("Create separate configuration for each symbol:")
    report.append("")

    for symbol, data in results.items():
        report.append(f"**{symbol} Configuration:**")
        report.append("```python")
        report.append(f"{symbol.lower()}_params = {{")
        for key, value in data['best_params'].items():
            report.append(f"    '{key}': {value},")
        report.append("}")
        report.append("```")
        report.append("")

    report.append("---")
    report.append("")
    report.append("*Report generated by Advanced Parameter Optimizer v1.0*")
    report.append(f"*Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    report.append("")

    # Save report
    report_path = '/mnt/d/Bimo_max/crypto-trading-bot/services/technical-analysis/backtesting/PARAMETER_OPTIMIZATION_REPORT.md'
    with open(report_path, 'w') as f:
        f.write('\n'.join(report))

    logger.info(f"\n✅ Optimization report saved to: {report_path}")


if __name__ == "__main__":
    # Run optimization
    asyncio.run(optimize_all_symbols())
