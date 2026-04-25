#!/usr/bin/env python3
"""
Walk-Forward Optimization for Multi-Indicator Strategy
Purpose: Find optimal parameters for RSI, MACD, and Bollinger Bands periods and thresholds
Date: 2026-02-05

This script runs comprehensive walk-forward optimization to find the most robust
parameters for the multi-indicator strategy combining RSI, MACD, and Bollinger Bands.
"""

import sys
from pathlib import Path
import pandas as pd
import logging
import json
from datetime import datetime
import itertools

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backtesting.backtest_engine import BacktestEngine
from backtesting.optimizers.walk_forward_optimizer import WalkForwardOptimizer
from backtesting.strategies.multi_indicator_strategy import create_multi_indicator_strategy

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)
logger = logging.getLogger(__name__)


def test_comprehensive_multi_indicator_walkforward(symbol: str, data: pd.DataFrame):
    """Test multi-indicator strategy with comprehensive parameter optimization"""
    logger.info(f"\n{'='*100}")
    logger.info(f"COMPREHENSIVE MULTI-INDICATOR WALK-FORWARD OPTIMIZATION ON {symbol}")
    logger.info(f"{'='*100}")

    # Comprehensive parameter grid for RSI, MACD, and Bollinger Bands
    param_grid = {
        # RSI Parameters
        'rsi_period': [10, 14, 20, 25],  # Different RSI periods
        'rsi_oversold': [20, 25, 30, 35],  # Different oversold thresholds
        'rsi_overbought': [65, 70, 75, 80],  # Different overbought thresholds
        
        # MACD Parameters
        'macd_fast': [10, 12, 15],  # Fast EMA period
        'macd_slow': [26, 30, 35],  # Slow EMA period
        'macd_signal': [7, 9, 12],  # Signal line period
        
        # Bollinger Bands Parameters
        'bb_period': [15, 20, 25, 30],  # BB period
        'bb_std': [1.5, 2.0, 2.5],  # Standard deviation multiplier
        
        # Strategy Parameters
        'min_confirmations': [2, 3],  # Minimum confirmations needed
    }

    # Calculate total combinations
    total_combinations = 1
    for param_values in param_grid.values():
        total_combinations *= len(param_values)

    logger.info(f"Testing {total_combinations} parameter combinations")

    # Initialize optimizer with correct config
    from backtesting.optimizers.walk_forward_optimizer import WalkForwardConfig
    config = WalkForwardConfig(
        total_periods=6,  # Increased periods for better validation
        in_sample_ratio=0.60,  # 60% in-sample, 40% out-of-sample
        metric_to_optimize='sharpe_ratio'
    )
    optimizer = WalkForwardOptimizer(config)

    # Create strategy factory
    def strategy_factory(params):
        return create_multi_indicator_strategy(
            require_all=False,
            min_confirmations=params.get('min_confirmations', 2),
            rsi_period=params.get('rsi_period', 14),
            rsi_oversold=params.get('rsi_oversold', 30),
            rsi_overbought=params.get('rsi_overbought', 70),
            macd_fast=params.get('macd_fast', 12),
            macd_slow=params.get('macd_slow', 26),
            macd_signal=params.get('macd_signal', 9),
            bb_period=params.get('bb_period', 20),
            bb_std=params.get('bb_std', 2.0)
        )

    # Create a wrapper for the backtest engine that matches the expected interface
    from backtesting.backtest_engine import BacktestEngine

    class BacktestEngineWrapper:
        def __init__(self):
            self.engine = BacktestEngine()

        def run(self, data, strategy_params):
            # Create the actual strategy function with the given parameters
            strategy_func = strategy_factory(strategy_params)
            # Run the backtest
            result = self.engine.run_backtest(
                data=data,
                strategy_func=strategy_func,
                strategy_name=f"Multi-Indicator_{symbol}"
            )
            # Convert the result to the expected format
            return {
                'sharpe_ratio': result.sharpe_ratio,
                'total_return': result.total_profit_loss_pct,
                'max_drawdown': result.max_drawdown,
                'win_rate': result.win_rate * 100,  # Convert to percentage
                'total_trades': result.total_trades,
                'profit_factor': result.profit_factor if hasattr(result, 'profit_factor') else 1.0
            }

    # Create wrapped backtest engine instance
    backtest_engine = BacktestEngineWrapper()

    results = optimizer.optimize(
        data=data,
        strategy_func=strategy_factory,
        parameter_space=param_grid,
        backtest_engine=backtest_engine
    )

    # Save detailed results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_path = project_root / f'backtesting/results/{symbol}_comprehensive_multi_indicator_wf_{timestamp}.json'
    results_path.parent.mkdir(parents=True, exist_ok=True)

    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    # Convert results to dictionary for logging
    results_dict = results.to_dict()

    logger.info(f"\n{symbol} COMPREHENSIVE MULTI-INDICATOR RESULTS:")
    logger.info(f"  Average WFE: {results_dict['aggregate_metrics']['average_wfe']:.3f}")
    logger.info(f"  OOS Sharpe:  {results_dict['out_of_sample_performance']['sharpe_ratio']:.3f}")
    logger.info(f"  OOS Profit:  {results_dict['out_of_sample_performance']['total_profit']:.2f}")
    logger.info(f"  OOS Win Rate: {results_dict['out_of_sample_performance']['win_rate']:.3f}")
    logger.info(f"  Max Drawdown: {results_dict['out_of_sample_performance']['max_drawdown']:.3f}")
    logger.info(f"  Robust:      {'YES ✅' if results_dict['is_robust'] else 'NO ❌'}")
    logger.info(f"  Best Params: {results_dict.get('periods', [{}])[0].get('optimal_params', 'Not available') if results_dict.get('periods') else 'N/A'}")
    logger.info(f"  Saved to: {results_path}")

    return results_dict


def test_targeted_multi_indicator_walkforward(symbol: str, data: pd.DataFrame):
    """Test multi-indicator strategy with targeted parameter optimization focusing on specific ranges"""
    logger.info(f"\n{'='*100}")
    logger.info(f"TARGETED MULTI-INDICATOR WALK-FORWARD OPTIMIZATION ON {symbol}")
    logger.info(f"{'='*100}")

    # Targeted parameter grid based on known good ranges for crypto
    param_grid = {
        # RSI - Focus on shorter periods for crypto volatility
        'rsi_period': [8, 10, 12, 14],  # Shorter periods for crypto
        'rsi_oversold': [25, 30, 35],    # Standard ranges
        'rsi_overbought': [65, 70, 75],  # Standard ranges
        
        # MACD - Focus on faster settings for crypto
        'macd_fast': [8, 10, 12],        # Faster settings
        'macd_slow': [17, 20, 26],       # Standard to medium settings
        'macd_signal': [6, 8, 9],        # Standard settings
        
        # Bollinger Bands - Focus on standard settings with variation
        'bb_period': [14, 20, 21],       # Standard periods
        'bb_std': [1.8, 2.0, 2.2],      # Tighter to wider bands
        
        # Strategy - Focus on confirmation requirements
        'min_confirmations': [2, 3],      # 2 or 3 confirmations
    }

    # Calculate total combinations
    total_combinations = 1
    for param_values in param_grid.values():
        total_combinations *= len(param_values)

    logger.info(f"Testing {total_combinations} targeted parameter combinations")

    # Initialize optimizer with correct config
    from backtesting.optimizers.walk_forward_optimizer import WalkForwardConfig
    config = WalkForwardConfig(
        total_periods=5,
        in_sample_ratio=0.65,  # 65% in-sample, 35% out-of-sample
        metric_to_optimize='sharpe_ratio'
    )
    optimizer = WalkForwardOptimizer(config)

    # Create strategy factory
    def strategy_factory(params):
        return create_multi_indicator_strategy(
            require_all=False,
            min_confirmations=params.get('min_confirmations', 2),
            rsi_period=params.get('rsi_period', 14),
            rsi_oversold=params.get('rsi_oversold', 30),
            rsi_overbought=params.get('rsi_overbought', 70),
            macd_fast=params.get('macd_fast', 12),
            macd_slow=params.get('macd_slow', 26),
            macd_signal=params.get('macd_signal', 9),
            bb_period=params.get('bb_period', 20),
            bb_std=params.get('bb_std', 2.0)
        )

    # Create a wrapper for the backtest engine that matches the expected interface
    from backtesting.backtest_engine import BacktestEngine

    class BacktestEngineWrapper:
        def __init__(self):
            self.engine = BacktestEngine()

        def run(self, data, strategy_params):
            # Create the actual strategy function with the given parameters
            strategy_func = strategy_factory(strategy_params)
            # Run the backtest
            result = self.engine.run_backtest(
                data=data,
                strategy_func=strategy_func,
                strategy_name=f"Multi-Indicator_{symbol}"
            )
            # Convert the result to the expected format
            return {
                'sharpe_ratio': result.sharpe_ratio,
                'total_return': result.total_profit_loss_pct,
                'max_drawdown': result.max_drawdown,
                'win_rate': result.win_rate * 100,  # Convert to percentage
                'total_trades': result.total_trades,
                'profit_factor': result.profit_factor if hasattr(result, 'profit_factor') else 1.0
            }

    # Create wrapped backtest engine instance
    backtest_engine = BacktestEngineWrapper()

    results = optimizer.optimize(
        data=data,
        strategy_func=strategy_factory,
        parameter_space=param_grid,
        backtest_engine=backtest_engine
    )

    # Save detailed results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_path = project_root / f'backtesting/results/{symbol}_targeted_multi_indicator_wf_{timestamp}.json'
    results_path.parent.mkdir(parents=True, exist_ok=True)

    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    # Convert results to dictionary for logging
    results_dict = results.to_dict()

    logger.info(f"\n{symbol} TARGETED MULTI-INDICATOR RESULTS:")
    logger.info(f"  Average WFE: {results_dict['aggregate_metrics']['average_wfe']:.3f}")
    logger.info(f"  OOS Sharpe:  {results_dict['out_of_sample_performance']['sharpe_ratio']:.3f}")
    logger.info(f"  OOS Profit:  {results_dict['out_of_sample_performance']['total_profit']:.2f}")
    logger.info(f"  OOS Win Rate: {results_dict['out_of_sample_performance']['win_rate']:.3f}")
    logger.info(f"  Max Drawdown: {results_dict['out_of_sample_performance']['max_drawdown']:.3f}")
    logger.info(f"  Robust:      {'YES ✅' if results_dict['is_robust'] else 'NO ❌'}")
    logger.info(f"  Best Params: {results_dict.get('periods', [{}])[0].get('optimal_params', 'Not available') if results_dict.get('periods') else 'N/A'}")
    logger.info(f"  Saved to: {results_path}")

    return results_dict


def main():
    """Run comprehensive walk-forward optimization for multi-indicator strategy"""

    logger.info("="*100)
    logger.info("COMPREHENSIVE MULTI-INDICATOR WALK-FORWARD OPTIMIZATION")
    logger.info("Finding optimal parameters for RSI, MACD, and Bollinger Bands")
    logger.info("="*100)

    # Test symbols
    symbols = ['BNBUSDT', 'SOLUSDT', 'ADAUSDT']

    all_results = {
        'comprehensive': {},
        'targeted': {}
    }

    for symbol in symbols:
        # Load data - look for the correct path (using the actual files in the directory)
        # Construct the file paths directly
        import os
        data_paths = [
            f'/mnt/d/Bimo_max/crypto-trading-bot/data/historical/{symbol}_180days_20251211.csv',  # Latest data
            f'/mnt/d/Bimo_max/crypto-trading-bot/data/historical/{symbol}_180days_20251208.csv',  # Older data
            f'/mnt/d/Bimo_max/crypto-trading-bot/backtesting/data/{symbol}_60m_90d_bybit.csv'    # Backup
        ]

        data_path = None
        for path in data_paths:
            if os.path.exists(path):
                data_path = path
                break

        if data_path is None:
            logger.warning(f"Data file not found for {symbol} in any of: {data_paths}")
            continue

        logger.info(f"Loading data from: {data_path}")
        data = pd.read_csv(data_path)

        # Handle timestamp conversion - the data has Unix timestamps in milliseconds
        if 'timestamp' in data.columns:
            # Convert Unix timestamp (milliseconds) to datetime
            data['timestamp'] = pd.to_datetime(data['timestamp'], unit='ms')
            data = data.set_index('timestamp').sort_index()
        elif 'datetime' in data.columns:
            # Use the datetime column directly
            data['datetime'] = pd.to_datetime(data['datetime'])
            data = data.set_index('datetime').sort_index()
        else:
            # If no timestamp column, assume index is the time
            logger.warning(f"No timestamp column found in {symbol} data, using index")
            data.index = pd.to_datetime(data.index, unit='s') if data.index.dtype == 'int64' else pd.to_datetime(data.index)

        # Ensure required columns exist - check for common variations
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in data.columns]
        if missing_cols:
            logger.info(f"Some required columns missing for {symbol}, checking for variations...")
            # Try to map common variations
            col_mapping = {
                'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume',
                'open_price': 'open', 'high_price': 'high', 'low_price': 'low', 'close_price': 'close',
                'quote_asset_volume': 'volume',
                'open_usdt': 'open', 'high_usdt': 'high', 'low_usdt': 'low', 'close_usdt': 'close',
                'volume_usdt': 'volume', 'base_volume': 'volume', 'quote_volume': 'volume'
            }
            for old_col, new_col in col_mapping.items():
                if old_col in data.columns and new_col not in data.columns:
                    data[new_col] = data[old_col]
                    logger.info(f"Mapped {old_col} to {new_col}")

        # Check again for missing columns
        missing_cols = [col for col in required_cols if col not in data.columns]
        if missing_cols:
            logger.warning(f"Still missing required columns for {symbol}: {missing_cols}, skipping")
            continue

        # Ensure data is sorted by index
        data = data.sort_index()

        logger.info(f"Successfully loaded {symbol}: {len(data)} candles from {data.index[0]} to {data.index[-1]}")

        logger.info(f"\nLoaded {symbol}: {len(data)} candles from {data.index[0]} to {data.index[-1]}")

        # Run comprehensive optimization
        try:
            comp_results = test_comprehensive_multi_indicator_walkforward(symbol, data)
            all_results['comprehensive'][symbol] = comp_results
        except Exception as e:
            logger.error(f"Error in comprehensive optimization on {symbol}: {e}")
            import traceback
            traceback.print_exc()

        # Run targeted optimization
        try:
            targ_results = test_targeted_multi_indicator_walkforward(symbol, data)
            all_results['targeted'][symbol] = targ_results
        except Exception as e:
            logger.error(f"Error in targeted optimization on {symbol}: {e}")
            import traceback
            traceback.print_exc()

    # Print comprehensive summary
    logger.info("\n" + "="*100)
    logger.info("COMPREHENSIVE OPTIMIZATION SUMMARY")
    logger.info("="*100)

    robust_strategies_found = []

    # Comprehensive Optimization Summary
    logger.info("\n--- COMPREHENSIVE OPTIMIZATION RESULTS ---")
    logger.info(f"{'Symbol':<12} {'WFE':<8} {'Sharpe':<8} {'Return':<8} {'Trades':<8} {'WinRate':<8} {'Drawdown':<10} {'Robust':<8} {'Params'}")
    logger.info("-"*120)

    for symbol, result in all_results['comprehensive'].items():
        status = "✅" if result['is_robust'] else "❌"
        params = result.get('best_params', {})
        rsi_period = params.get('rsi_period', 'N/A')
        macd_fast = params.get('macd_fast', 'N/A')
        bb_period = params.get('bb_period', 'N/A')
        param_summary = f"RSI:{rsi_period},MACD:{macd_fast},BB:{bb_period}"
        
        logger.info(f"{symbol:<12} {result['average_wfe']:<8.2f}% {result['oos_sharpe']:<8.3f} {result['oos_total_return_pct']:<8.2f}% "
                   f"{result['oos_num_trades']:<8} {result['oos_win_rate']:<8.2f}% {result['oos_max_drawdown']:<10.2f}% {status:<8} {param_summary}")

        if result['is_robust']:
            robust_strategies_found.append(f"Comprehensive Multi-Indicator on {symbol}")

    # Targeted Optimization Summary
    logger.info("\n--- TARGETED OPTIMIZATION RESULTS ---")
    logger.info(f"{'Symbol':<12} {'WFE':<8} {'Sharpe':<8} {'Return':<8} {'Trades':<8} {'WinRate':<8} {'Drawdown':<10} {'Robust':<8} {'Params'}")
    logger.info("-"*120)

    for symbol, result in all_results['targeted'].items():
        status = "✅" if result['is_robust'] else "❌"
        params = result.get('best_params', {})
        rsi_period = params.get('rsi_period', 'N/A')
        macd_fast = params.get('macd_fast', 'N/A')
        bb_period = params.get('bb_period', 'N/A')
        param_summary = f"RSI:{rsi_period},MACD:{macd_fast},BB:{bb_period}"
        
        logger.info(f"{symbol:<12} {result['average_wfe']:<8.2f}% {result['oos_sharpe']:<8.3f} {result['oos_total_return_pct']:<8.2f}% "
                   f"{result['oos_num_trades']:<8} {result['oos_win_rate']:<8.2f}% {result['oos_max_drawdown']:<10.2f}% {status:<8} {param_summary}")

        if result['is_robust']:
            robust_strategies_found.append(f"Targeted Multi-Indicator on {symbol}")

    # Final analysis
    logger.info("\n" + "="*100)
    logger.info("FINAL ANALYSIS")
    logger.info("="*100)

    if robust_strategies_found:
        logger.info(f"\n✅ SUCCESS! Found {len(robust_strategies_found)} robust strategy combinations:")
        for strategy in robust_strategies_found:
            logger.info(f"   - {strategy}")
        
        logger.info("\nPARAMETER EFFECTIVENESS ANALYSIS:")
        
        # Analyze best parameters across symbols
        best_params_summary = {}
        for symbol, result in {**all_results['comprehensive'], **all_results['targeted']}.items():
            if result['is_robust']:
                params = result.get('best_params', {})
                if symbol not in best_params_summary:
                    best_params_summary[symbol] = params
        
        if best_params_summary:
            logger.info("\nBest performing parameter ranges:")
            rsi_periods = [params.get('rsi_period', 14) for params in best_params_summary.values()]
            macd_fast_vals = [params.get('macd_fast', 12) for params in best_params_summary.values()]
            bb_periods = [params.get('bb_period', 20) for params in best_params_summary.values()]
            
            logger.info(f"  RSI Period: {min(rsi_periods)}-{max(rsi_periods)} (common: {max(set(rsi_periods), key=rsi_periods.count)})")
            logger.info(f"  MACD Fast: {min(macd_fast_vals)}-{max(macd_fast_vals)} (common: {max(set(macd_fast_vals), key=macd_fast_vals.count)})")
            logger.info(f"  BB Period: {min(bb_periods)}-{max(bb_periods)} (common: {max(set(bb_periods), key=bb_periods.count)})")
        
        logger.info("\nRECOMMENDATION: These parameters are robust and can be deployed!")
    else:
        logger.info("\n❌ NO ROBUST STRATEGIES FOUND")
        logger.info("\nPOTENTIAL CAUSES:")
        logger.info("  1. Multi-indicator approach may be fundamentally flawed for this market period")
        logger.info("  2. Crypto markets may be too noisy for technical indicators")
        logger.info("  3. Parameter optimization may be overfitting to in-sample data")
        logger.info("  4. Market conditions may not favor trend-following/momentum strategies")
        logger.info("\nRECOMMENDATIONS:")
        logger.info("  A. Try different strategy types (mean reversion, breakout)")
        logger.info("  B. Test on different timeframes (15m, 4H, 1D)")
        logger.info("  C. Consider machine learning approaches")
        logger.info("  D. Wait for more favorable market conditions")
        logger.info("  E. Implement market regime detection")

    logger.info("\n" + "="*100)

    # Save comprehensive results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_path = project_root / f'backtesting/results/comprehensive_multi_indicator_optimization_{timestamp}.json'
    summary_path.parent.mkdir(parents=True, exist_ok=True)  # Create directory if it doesn't exist
    with open(summary_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)

    logger.info(f"\nComprehensive optimization results saved to: {summary_path}")


if __name__ == "__main__":
    main()