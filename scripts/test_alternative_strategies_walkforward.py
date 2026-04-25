#!/usr/bin/env python3
"""
Phase 2: Test Alternative Strategies with Walk-Forward Validation
Purpose: Find if multi-indicator or mean reversion strategies are robust
Date: 2025-12-06

We already tested Simple RSI (FAILED on all symbols).
Now test the other strategies we built:
1. Multi-Indicator Consensus
2. Mean Reversion

If ANY strategy passes walk-forward, we have a winner!
"""

import sys
from pathlib import Path
import pandas as pd
import logging
import json
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backtesting.backtest_engine import BacktestEngine
from backtesting.optimizers.walk_forward_optimizer import WalkForwardOptimizer
from backtesting.strategies.multi_indicator_strategy import create_multi_indicator_strategy
from backtesting.strategies.mean_reversion_strategy import create_mean_reversion_strategy

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)
logger = logging.getLogger(__name__)


def test_multi_indicator_walkforward(symbol: str, data: pd.DataFrame):
    """Test multi-indicator strategy with walk-forward optimization"""
    logger.info(f"\n{'='*80}")
    logger.info(f"TESTING MULTI-INDICATOR STRATEGY ON {symbol}")
    logger.info(f"{'='*80}")

    # Parameter grid for multi-indicator optimization
    param_grid = {
        'min_confirmations': [2, 3],  # How many indicators must agree
        'rsi_period': [14, 20],
        'rsi_oversold': [30, 35],
        'rsi_overbought': [65, 70]
    }

    logger.info(f"Testing {len(param_grid['min_confirmations']) * len(param_grid['rsi_period']) * len(param_grid['rsi_oversold']) * len(param_grid['rsi_overbought'])} parameter combinations")

    # Initialize optimizer
    optimizer = WalkForwardOptimizer(
        data=data,
        strategy_name=f"Multi-Indicator_{symbol}",
        num_periods=5,
        is_oos_ratio=0.65
    )

    # Create strategy factory
    def strategy_factory(params):
        return create_multi_indicator_strategy(
            require_all=False,
            min_confirmations=params.get('min_confirmations', 2),
            rsi_period=params.get('rsi_period', 14),
            rsi_oversold=params.get('rsi_oversold', 30),
            rsi_overbought=params.get('rsi_overbought', 70)
        )

    # Run optimization
    results = optimizer.optimize(
        param_grid=param_grid,
        strategy_factory=strategy_factory
    )

    # Save results
    results_path = project_root / f'backtesting/results/{symbol}_multi_indicator_wf_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    results_path.parent.mkdir(parents=True, exist_ok=True)

    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    logger.info(f"\n{symbol} MULTI-INDICATOR RESULTS:")
    logger.info(f"  Average WFE: {results['average_wfe']:.2f}%")
    logger.info(f"  OOS Sharpe:  {results['oos_sharpe']:.3f}")
    logger.info(f"  OOS Profit:  {results['oos_total_return_pct']:.2f}%")
    logger.info(f"  Robust:      {'YES ✅' if results['is_robust'] else 'NO ❌'}")
    logger.info(f"  Saved to: {results_path}")

    return results


def test_mean_reversion_walkforward(symbol: str, data: pd.DataFrame):
    """Test mean reversion strategy with walk-forward optimization"""
    logger.info(f"\n{'='*80}")
    logger.info(f"TESTING MEAN REVERSION STRATEGY ON {symbol}")
    logger.info(f"{'='*80}")

    # Parameter grid for mean reversion optimization
    param_grid = {
        'bb_period': [15, 20, 25],
        'bb_std': [1.5, 2.0, 2.5],
        'stop_loss_pct': [1.5, 2.0],
        'take_profit_pct': [2.0, 3.0]
    }

    logger.info(f"Testing {len(param_grid['bb_period']) * len(param_grid['bb_std']) * len(param_grid['stop_loss_pct']) * len(param_grid['take_profit_pct'])} parameter combinations")

    # Initialize optimizer
    optimizer = WalkForwardOptimizer(
        data=data,
        strategy_name=f"MeanReversion_{symbol}",
        num_periods=5,
        is_oos_ratio=0.65
    )

    # Create strategy factory
    def strategy_factory(params):
        return create_mean_reversion_strategy(
            bb_period=params.get('bb_period', 20),
            bb_std=params.get('bb_std', 2.0),
            stop_loss_pct=params.get('stop_loss_pct', 2.0),
            take_profit_pct=params.get('take_profit_pct', 3.0),
            require_rsi=True
        )

    # Run optimization
    results = optimizer.optimize(
        param_grid=param_grid,
        strategy_factory=strategy_factory
    )

    # Save results
    results_path = project_root / f'backtesting/results/{symbol}_mean_reversion_wf_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    results_path.parent.mkdir(parents=True, exist_ok=True)

    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    logger.info(f"\n{symbol} MEAN REVERSION RESULTS:")
    logger.info(f"  Average WFE: {results['average_wfe']:.2f}%")
    logger.info(f"  OOS Sharpe:  {results['oos_sharpe']:.3f}")
    logger.info(f"  OOS Profit:  {results['oos_total_return_pct']:.2f}%")
    logger.info(f"  Robust:      {'YES ✅' if results['is_robust'] else 'NO ❌'}")
    logger.info(f"  Saved to: {results_path}")

    return results


def main():
    """Test all alternative strategies on all available symbols"""

    logger.info("="*80)
    logger.info("PHASE 2: ALTERNATIVE STRATEGY WALK-FORWARD VALIDATION")
    logger.info("Testing Multi-Indicator and Mean Reversion strategies")
    logger.info("="*80)

    # Test symbols
    symbols = ['BNBUSDT', 'SOLUSDT', 'ADAUSDT']

    all_results = {
        'multi_indicator': {},
        'mean_reversion': {}
    }

    for symbol in symbols:
        # Load data
        data_path = project_root / f'backtesting/data/{symbol}_60m_90d_bybit.csv'

        if not data_path.exists():
            logger.warning(f"Data file not found: {data_path}")
            continue

        data = pd.read_csv(data_path)
        data['timestamp'] = pd.to_datetime(data['timestamp'])
        data = data.set_index('timestamp').sort_index()

        logger.info(f"\nLoaded {symbol}: {len(data)} candles from {data.index[0]} to {data.index[-1]}")

        # Test Multi-Indicator Strategy
        try:
            multi_results = test_multi_indicator_walkforward(symbol, data)
            all_results['multi_indicator'][symbol] = multi_results
        except Exception as e:
            logger.error(f"Error testing multi-indicator on {symbol}: {e}")

        # Test Mean Reversion Strategy
        try:
            mr_results = test_mean_reversion_walkforward(symbol, data)
            all_results['mean_reversion'][symbol] = mr_results
        except Exception as e:
            logger.error(f"Error testing mean reversion on {symbol}: {e}")

    # Print comprehensive summary
    logger.info("\n" + "="*80)
    logger.info("COMPREHENSIVE SUMMARY - ALL STRATEGIES & SYMBOLS")
    logger.info("="*80)

    robust_strategies_found = []

    # Multi-Indicator Summary
    logger.info("\n--- MULTI-INDICATOR STRATEGY ---")
    logger.info(f"{'Symbol':<12} {'WFE':<15} {'OOS Sharpe':<12} {'OOS Return':<12} {'Robust':<10}")
    logger.info("-"*80)

    for symbol, result in all_results['multi_indicator'].items():
        status = "✅" if result['is_robust'] else "❌"
        logger.info(f"{symbol:<12} {result['average_wfe']:<15.2f}% {result['oos_sharpe']:<12.3f} {result['oos_total_return_pct']:<12.2f}% {status:<10}")
        if result['is_robust']:
            robust_strategies_found.append(f"Multi-Indicator on {symbol}")

    # Mean Reversion Summary
    logger.info("\n--- MEAN REVERSION STRATEGY ---")
    logger.info(f"{'Symbol':<12} {'WFE':<15} {'OOS Sharpe':<12} {'OOS Return':<12} {'Robust':<10}")
    logger.info("-"*80)

    for symbol, result in all_results['mean_reversion'].items():
        status = "✅" if result['is_robust'] else "❌"
        logger.info(f"{symbol:<12} {result['average_wfe']:<15.2f}% {result['oos_sharpe']:<12.3f} {result['oos_total_return_pct']:<12.2f}% {status:<10}")
        if result['is_robust']:
            robust_strategies_found.append(f"Mean Reversion on {symbol}")

    # Final verdict
    logger.info("\n" + "="*80)
    logger.info("FINAL VERDICT")
    logger.info("="*80)

    if robust_strategies_found:
        logger.info(f"\n✅ SUCCESS! Found {len(robust_strategies_found)} robust strategy combinations:")
        for strategy in robust_strategies_found:
            logger.info(f"   - {strategy}")
        logger.info("\nRECOMMENDATION: Deploy these strategies to production!")
    else:
        logger.info("\n❌ NO ROBUST STRATEGIES FOUND")
        logger.info("\nAll tested strategies (Simple RSI, Multi-Indicator, Mean Reversion)")
        logger.info("failed walk-forward validation on all symbols.")
        logger.info("\nPOSSIBLE REASONS:")
        logger.info("  1. Market period (Sept-Dec 2025) fundamentally difficult")
        logger.info("  2. Strategies need different timeframes (try 15m, 4H, 1D)")
        logger.info("  3. Need ML/AI approaches (Phase 3)")
        logger.info("  4. Need market regime detection")
        logger.info("\nRECOMMENDATION:")
        logger.info("  - Option A: Test on different timeframes")
        logger.info("  - Option B: Move to Phase 3 (ML/AI integration)")
        logger.info("  - Option C: Pause systematic trading until better market conditions")

    logger.info("\n" + "="*80)

    # Save comprehensive results
    summary_path = project_root / f'backtesting/results/alternative_strategies_summary_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(summary_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)

    logger.info(f"\nComprehensive results saved to: {summary_path}")


if __name__ == "__main__":
    main()
