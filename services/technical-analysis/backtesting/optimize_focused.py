#!/usr/bin/env python3
"""
Focused Parameter Optimization for SQZMOM Strategy
Purpose: Run faster optimization with a smaller parameter grid for quick results

This is useful for:
- Quick testing of parameter optimization logic
- Getting fast feedback on parameter ranges
- Testing after code changes
- Exploratory parameter analysis

Features:
- Smaller parameter grid (216 combinations vs 1600)
- Focused ranges around current best parameters
- Faster execution time (minutes vs hours)
- Full result export and reporting

Usage:
    python3 optimize_focused.py
"""

import asyncio
import logging
from datetime import datetime

from optimize_parameters import ParameterOptimizer, create_optimization_report

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def focused_optimization():
    """
    Run focused optimization with smaller parameter grid

    This tests a focused range around the current default parameters to find
    improvements more quickly than a full grid search.

    Current defaults:
    - bb_length: 20
    - kc_length: 20
    - min_momentum_threshold: 0.3
    - stop_loss_pct: 1.5
    - take_profit_pct: 3.0
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

    # Focused parameter grid (3×3×4×3×3 = 216 combinations)
    # This grid focuses on ranges around current best values
    param_grid = {
        'bb_length': [18, 20, 22],  # Current: 20
        'kc_length': [18, 20, 22],  # Current: 20
        'min_momentum_threshold': [0.25, 0.3, 0.35, 0.4],  # Current: 0.3
        'stop_loss_pct': [1.25, 1.5, 1.75],  # Current: 1.5
        'take_profit_pct': [2.75, 3.0, 3.25]  # Current: 3.0
    }

    # Calculate total combinations
    total_combos = 1
    for values in param_grid.values():
        total_combos *= len(values)

    logger.info(f"\n{'#'*80}")
    logger.info(f"# FOCUSED PARAMETER OPTIMIZATION")
    logger.info(f"{'#'*80}")
    logger.info(f"Total parameter combinations: {total_combos}")
    logger.info(f"Grid breakdown: 3×3×4×3×3 = {total_combos} backtests per symbol")
    logger.info(f"Expected time: ~5-10 minutes per symbol")
    logger.info(f"{'#'*80}\n")

    # Test all three profitable symbols
    symbols = ['SOLUSDT', 'DOGEUSDT', 'BNBUSDT']

    all_results = {}

    for symbol in symbols:
        logger.info(f"\n{'='*80}")
        logger.info(f"Optimizing {symbol}")
        logger.info(f"{'='*80}\n")

        result = await optimizer.optimize_symbol(
            symbol=symbol,
            param_grid=param_grid,
            optimize_for='sharpe_ratio'
        )

        all_results[symbol] = result

        # Save individual results
        optimizer.save_results(
            result,
            f'/mnt/d/Bimo_max/crypto-trading-bot/services/technical-analysis/backtesting/optimization_{symbol}_focused.json'
        )

        # Print summary
        logger.info(f"\n{'='*80}")
        logger.info(f"{symbol} RESULTS")
        logger.info(f"{'='*80}")
        logger.info(f"Best Sharpe Ratio: {result['best_score']:.2f}")
        logger.info(f"Time: {result['optimization_time_seconds']:.1f} seconds\n")

        logger.info("Best Parameters:")
        for key, value in result['best_params'].items():
            logger.info(f"  {key:30} = {value}")

        logger.info("\nTop 3 Parameter Sets:")
        for idx, r in enumerate(result['top_10_results'][:3], 1):
            logger.info(f"\n  #{idx}:")
            logger.info(f"    Return: {r['total_return_pct']:.2f}%")
            logger.info(f"    Sharpe: {r['sharpe_ratio']:.2f}")
            logger.info(f"    Win Rate: {r['win_rate']:.2f}%")
            logger.info(f"    Trades: {r['total_trades']}")
            logger.info(f"    Params: {r['params']}")

    # Save combined results
    optimizer.save_results(
        all_results,
        '/mnt/d/Bimo_max/crypto-trading-bot/services/technical-analysis/backtesting/all_optimizations_focused.json'
    )

    # Create summary report
    create_optimization_report(all_results)

    # Print final summary
    logger.info(f"\n{'#'*80}")
    logger.info("# FOCUSED OPTIMIZATION COMPLETE")
    logger.info(f"{'#'*80}\n")

    logger.info("Summary Comparison:")
    logger.info(f"{'Symbol':<12} {'Best Sharpe':<12} {'Best Return %':<15} {'Win Rate %':<12} {'Trades':<8}")
    logger.info("-" * 70)

    for symbol, data in all_results.items():
        best = data['top_10_results'][0]
        logger.info(
            f"{symbol:<12} {best['sharpe_ratio']:<12.2f} {best['total_return_pct']:<15.2f} "
            f"{best['win_rate']:<12.2f} {best['total_trades']:<8}"
        )

    logger.info("\nFiles Generated:")
    logger.info("  1. PARAMETER_OPTIMIZATION_REPORT.md")
    logger.info("  2. all_optimizations_focused.json")
    logger.info("  3. optimization_[SYMBOL]_focused.json (for each symbol)")
    logger.info("")

    return all_results


async def quick_test_single_symbol():
    """
    Ultra-fast test on a single symbol for development/testing

    This runs only 27 combinations (3×3×3) on SOLUSDT for quick validation.
    """
    db_config = {
        'host': 'localhost',
        'port': 5433,
        'database': 'market_data',
        'user': 'cryptobot',
        'password': 'timescale_dev_password'
    }

    optimizer = ParameterOptimizer(db_config)

    # Minimal grid for testing (3×3×3 = 27 combinations)
    param_grid = {
        'bb_length': [18, 20, 22],
        'kc_length': [18, 20, 22],
        'min_momentum_threshold': [0.25, 0.3, 0.35]
    }

    logger.info("Running quick test on SOLUSDT (27 combinations)...")

    result = await optimizer.optimize_symbol(
        symbol='SOLUSDT',
        param_grid=param_grid,
        optimize_for='sharpe_ratio'
    )

    optimizer.save_results(
        result,
        '/mnt/d/Bimo_max/crypto-trading-bot/services/technical-analysis/backtesting/optimization_SOLUSDT_quicktest.json'
    )

    logger.info("\nQuick Test Results:")
    logger.info(f"Best Sharpe: {result['best_score']:.2f}")
    logger.info(f"Best Params: {result['best_params']}")
    logger.info(f"Time: {result['optimization_time_seconds']:.1f} seconds")

    return result


if __name__ == "__main__":
    # Choose which optimization to run:

    # Option 1: Focused optimization on all 3 symbols (default)
    asyncio.run(focused_optimization())

    # Option 2: Ultra-quick test on single symbol (uncomment to use)
    # asyncio.run(quick_test_single_symbol())
