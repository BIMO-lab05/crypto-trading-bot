#!/usr/bin/env python3
"""
BNB Walk-Forward Optimization
Created: 2025-12-06
Purpose: Optimize strategy parameters for BNBUSDT using walk-forward analysis

This script:
1. Downloads 90 days of BNBUSDT data from Bybit
2. Runs walk-forward optimization with 5 periods
3. Tests parameter robustness across different market conditions
4. Generates comprehensive optimization report

Expected Output:
- Optimal parameters for BNB trading
- Walk-Forward Efficiency (WFE) > 50%
- Out-of-sample Sharpe > 1.0
- Risk metrics and drawdown analysis
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import json

# Import data fetcher
from backtesting.bybit_data_fetcher import BybitDataFetcher

# Import optimizers
from backtesting.optimizers.walk_forward_optimizer import (
    WalkForwardOptimizer,
    WalkForwardConfig
)

# Import backtesting engine
from backtesting.backtest_engine import BacktestEngine

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/mnt/d/Bimo_max/crypto-trading-bot/logs/bnb_walkforward.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def download_bnb_data(days: int = 90) -> pd.DataFrame:
    """
    Download BNBUSDT historical data from Bybit

    Args:
        days: Number of days of historical data to download

    Returns:
        DataFrame with OHLCV data
    """
    logger.info(f"="*80)
    logger.info("DOWNLOADING BNBUSDT DATA")
    logger.info(f"="*80)
    logger.info(f"Downloading {days} days of 1-hour BNBUSDT data from Bybit...")

    try:
        # Create data fetcher
        fetcher = BybitDataFetcher()

        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Download data
        data = fetcher.fetch_klines(
            symbol="BNBUSDT",
            interval="60",  # 1 hour
            start_time=int(start_date.timestamp() * 1000),
            end_time=int(end_date.timestamp() * 1000)
        )

        if data is None or len(data) == 0:
            raise ValueError("No data returned from Bybit")

        logger.info(f"✅ Downloaded {len(data)} candles")
        logger.info(f"Date range: {data['timestamp'].min()} to {data['timestamp'].max()}")
        logger.info(f"Price range: ${data['low'].min():.2f} - ${data['high'].max():.2f}")

        # Save data to cache
        cache_path = project_root / 'backtesting' / 'data' / f'BNBUSDT_1h_{days}d.csv'
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        data.to_csv(cache_path, index=False)
        logger.info(f"💾 Cached data to: {cache_path}")

        return data

    except Exception as e:
        logger.error(f"❌ Failed to download data: {e}")

        # Try to load from cache
        cache_path = project_root / 'backtesting' / 'data' / f'BNBUSDT_1h_{days}d.csv'
        if cache_path.exists():
            logger.info(f"📂 Loading cached data from: {cache_path}")
            return pd.read_csv(cache_path, parse_dates=['timestamp'])
        else:
            raise


def create_strategy_function():
    """
    Create a strategy function for optimization

    This uses the existing SQZMOM strategy from the trading engine
    """
    # Import strategy
    from services.trading_engine.app.strategies.sqzmom_strategy import SQZMOMStrategy

    def strategy_func(data: pd.DataFrame, params: dict) -> pd.DataFrame:
        """
        Run SQZMOM strategy with given parameters

        Args:
            data: OHLCV data
            params: Strategy parameters

        Returns:
            DataFrame with signals
        """
        # Create strategy instance
        strategy = SQZMOMStrategy(
            symbol="BNBUSDT",
            bb_length=params.get('bb_length', 20),
            bb_mult=params.get('bb_mult', 2.0),
            kc_length=params.get('kc_length', 20),
            kc_mult=params.get('kc_mult', 1.5),
            momentum_length=params.get('momentum_length', 12)
        )

        # Generate signals
        signals = strategy.generate_signals(data)

        return signals

    return strategy_func


def main():
    """Main execution"""
    print("\n" + "="*80)
    print("BNB WALK-FORWARD OPTIMIZATION")
    print("="*80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")

    # Step 1: Download data
    logger.info("STEP 1: Downloading BNB data...")
    try:
        data = download_bnb_data(days=90)
    except Exception as e:
        logger.error(f"Failed to download data: {e}")
        return 1

    # Step 2: Create configuration
    logger.info("\nSTEP 2: Creating walk-forward configuration...")
    config = WalkForwardConfig(
        total_periods=5,  # 5 rolling windows
        in_sample_ratio=0.70,  # 70% for optimization
        out_sample_ratio=0.30,  # 30% for validation
        metric_to_optimize='sharpe_ratio',
        min_wfe=0.50,  # Minimum 50% WFE
        min_oos_sharpe=0.50,  # Minimum OOS Sharpe
        max_oos_drawdown=0.25,  # Maximum 25% drawdown
        max_workers=4  # Parallel processing
    )

    logger.info(f"Configuration:")
    logger.info(f"  Periods: {config.total_periods}")
    logger.info(f"  In-Sample: {config.in_sample_ratio:.0%}")
    logger.info(f"  Out-Sample: {config.out_sample_ratio:.0%}")
    logger.info(f"  Target WFE: ≥{config.min_wfe:.0%}")
    logger.info(f"  Target OOS Sharpe: ≥{config.min_oos_sharpe:.2f}")

    # Step 3: Define parameter space
    logger.info("\nSTEP 3: Defining parameter space...")
    parameter_space = {
        'bb_length': [15, 20, 25],
        'bb_mult': [1.5, 2.0, 2.5],
        'kc_length': [15, 20, 25],
        'kc_mult': [1.0, 1.5, 2.0],
        'momentum_length': [10, 12, 15]
    }

    total_combinations = 1
    for param, values in parameter_space.items():
        total_combinations *= len(values)
        logger.info(f"  {param}: {values}")

    logger.info(f"\nTotal combinations: {total_combinations}")
    logger.info(f"Total backtests: {total_combinations * config.total_periods} "
                f"({total_combinations} combinations × {config.total_periods} periods)")

    # Step 4: Create backtest engine
    logger.info("\nSTEP 4: Creating backtest engine...")
    backtest_engine = BacktestEngine(
        initial_capital=10000.0,
        commission=0.001,  # 0.1%
        slippage=0.0005    # 0.05%
    )

    # Step 5: Create strategy function
    logger.info("\nSTEP 5: Creating strategy function...")
    strategy_func = create_strategy_function()

    # Step 6: Run walk-forward optimization
    logger.info("\nSTEP 6: Running walk-forward optimization...")
    logger.info("="*80)
    logger.info("This may take several minutes...")
    logger.info("="*80)

    optimizer = WalkForwardOptimizer(config)

    try:
        results = optimizer.optimize(
            data=data,
            strategy_func=strategy_func,
            parameter_space=parameter_space,
            backtest_engine=backtest_engine
        )

        # Step 7: Analyze results
        logger.info("\n" + "="*80)
        logger.info("OPTIMIZATION RESULTS")
        logger.info("="*80)

        logger.info(f"\nWalk-Forward Efficiency (WFE):")
        logger.info(f"  Average WFE: {results.average_wfe:.2%}")
        logger.info(f"  Median WFE:  {results.median_wfe:.2%}")
        logger.info(f"  Worst WFE:   {results.worst_wfe:.2%}")
        logger.info(f"  Best WFE:    {results.best_wfe:.2%}")

        logger.info(f"\nOut-of-Sample Performance:")
        logger.info(f"  Total OOS Sharpe:     {results.total_oos_sharpe:.3f}")
        logger.info(f"  Total OOS Profit:     {results.total_oos_profit:.2%}")
        logger.info(f"  Total OOS Drawdown:   {results.total_oos_drawdown:.2%}")
        logger.info(f"  Total OOS Win Rate:   {results.total_oos_win_rate:.2%}")

        logger.info(f"\nRobustness Check:")
        logger.info(f"  Profitable Periods: {results.oos_periods_profitable}/{results.oos_periods_total}")
        logger.info(f"  Strategy Robust:    {results.is_strategy_robust()} " +
                   ("✅" if results.is_strategy_robust() else "❌"))

        # Print period details
        logger.info(f"\nPeriod Details:")
        for i, period in enumerate(results.periods, 1):
            logger.info(f"\n  Period {i}:")
            logger.info(f"    IS: {period.is_start_date.strftime('%Y-%m-%d')} to {period.is_end_date.strftime('%Y-%m-%d')}")
            logger.info(f"    OOS: {period.oos_start_date.strftime('%Y-%m-%d')} to {period.oos_end_date.strftime('%Y-%m-%d')}")
            logger.info(f"    Optimal Params: {period.optimal_parameters}")
            logger.info(f"    IS Sharpe:  {period.is_performance.get('sharpe_ratio', 0):.3f}")
            logger.info(f"    OOS Sharpe: {period.oos_performance.get('sharpe_ratio', 0):.3f}")
            wfe = period.oos_performance.get('sharpe_ratio', 0) / max(period.is_performance.get('sharpe_ratio', 0.01), 0.01)
            logger.info(f"    WFE: {wfe:.2%}")

        # Save results
        results_path = project_root / 'backtesting' / 'results' / f'bnb_walkforward_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        results_path.parent.mkdir(parents=True, exist_ok=True)

        with open(results_path, 'w') as f:
            json.dump(results.to_dict(), f, indent=2, default=str)

        logger.info(f"\n💾 Results saved to: {results_path}")

        # Final recommendation
        logger.info("\n" + "="*80)
        if results.is_strategy_robust():
            logger.info("✅ STRATEGY IS ROBUST FOR LIVE TRADING!")
            logger.info("="*80)
            logger.info("\nRecommended Action:")
            logger.info("1. Proceed to Phase 1.2: Monte Carlo simulation")
            logger.info("2. Run risk-of-ruin analysis")
            logger.info("3. If all checks pass, begin paper trading")
        else:
            logger.info("❌ STRATEGY FAILED ROBUSTNESS CRITERIA")
            logger.info("="*80)
            logger.info("\nRecommended Action:")
            logger.info("1. Review parameter space - may need adjustment")
            logger.info("2. Consider different strategy approach")
            logger.info("3. Analyze which periods failed and why")

        return 0

    except Exception as e:
        logger.error(f"\n❌ Optimization failed: {e}")
        logger.exception("Full traceback:")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
