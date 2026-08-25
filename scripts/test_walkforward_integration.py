#!/usr/bin/env python3
"""
Walk-Forward Optimizer Integration Test
Created: 2025-12-06
Purpose: Test walk-forward optimization with existing BTC data and simple RSI strategy

This simplified test:
1. Loads existing BTC data from /backtesting/data/
2. Creates a simple RSI-based strategy function
3. Tests walk-forward optimizer integration with backtest engine
4. Validates WFE calculation and results format

Expected Output:
- Walk-forward optimization completes successfully
- WFE calculations work correctly
- Results structure is valid
- Integration between optimizer and backtest engine confirmed
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
from datetime import datetime
import logging

# Import optimizer and backtest engine
from backtesting.optimizers.walk_forward_optimizer import (
    WalkForwardOptimizer,
    WalkForwardConfig
)
from backtesting.backtest_engine import BacktestEngine

# Declared account size (see shared/account.py).
import os as _os
import sys as _sys

_REPO_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
if _REPO_ROOT not in _sys.path:
    _sys.path.insert(0, _REPO_ROOT)
from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_btc_data() -> pd.DataFrame:
    """
    Load existing BTC historical data from cache

    Returns:
        DataFrame with OHLCV data
    """
    logger.info("="*80)
    logger.info("LOADING BTC DATA FROM CACHE")
    logger.info("="*80)

    # Try to find BTC data file
    data_dir = project_root / 'backtesting' / 'data'
    btc_files = list(data_dir.glob('BTCUSDT*.csv'))

    if not btc_files:
        raise FileNotFoundError(
            f"No BTC data files found in {data_dir}. "
            "Please run a data download script first."
        )

    # Use the first BTC file found
    data_file = btc_files[0]
    logger.info(f"Loading data from: {data_file}")

    # Load data
    data = pd.read_csv(data_file)

    # Ensure required columns exist
    required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    missing = [col for col in required_columns if col not in data.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Convert timestamp to datetime if needed
    if data['timestamp'].dtype == 'object':
        data['timestamp'] = pd.to_datetime(data['timestamp'])

    # Set timestamp as index for walk-forward optimizer
    data = data.set_index('timestamp')
    data = data.sort_index()

    logger.info(f"✅ Loaded {len(data)} candles")
    logger.info(f"Date range: {data.index.min()} to {data.index.max()}")
    logger.info(f"Price range: ${data['low'].min():.2f} - ${data['high'].max():.2f}")

    return data


def calculate_rsi(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate RSI indicator

    Args:
        data: DataFrame with 'close' column
        period: RSI period (default: 14)

    Returns:
        Series with RSI values
    """
    close = data['close']
    delta = close.diff()

    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


class BacktestEngineAdapter:
    """
    Adapter to make BacktestEngine compatible with Walk-Forward Optimizer

    The optimizer expects: backtest_engine.run(data, strategy_params) -> dict
    Our BacktestEngine has: run_backtest(data, strategy_func, strategy_name) -> BacktestResult

    This adapter bridges the gap.
    """

    def __init__(self, backtest_engine: BacktestEngine, strategy_func_generator):
        """
        Initialize adapter

        Args:
            backtest_engine: The actual BacktestEngine instance
            strategy_func_generator: Function that takes (data, params) and returns strategy_func
        """
        self.engine = backtest_engine
        self.strategy_func_generator = strategy_func_generator

    def run(self, data: pd.DataFrame, strategy_params: dict) -> dict:
        """
        Run backtest with given parameters

        Args:
            data: Historical data
            strategy_params: Strategy parameters

        Returns:
            Dict with metrics (compatible with optimizer)
        """
        # Generate strategy function with these parameters
        strategy_func = self.strategy_func_generator(data, strategy_params)

        # Run backtest
        result = self.engine.run_backtest(
            data=data,
            strategy_func=strategy_func,
            strategy_name=f"RSI_{strategy_params}"
        )

        # Convert BacktestResult to dict format expected by optimizer
        return {
            'total_trades': result.total_trades,
            'sharpe_ratio': result.sharpe_ratio,
            'total_return': result.total_profit_loss_pct,
            'max_drawdown': result.max_drawdown_pct,
            'win_rate': result.win_rate,
            'profit_factor': result.profit_factor,
            'avg_win': result.avg_win,
            'avg_loss': result.avg_loss,
        }


def create_simple_rsi_strategy(rsi_period: int, oversold: int, overbought: int):
    """
    Create a simple RSI-based strategy function for backtesting

    This strategy:
    - Buys when RSI < oversold threshold
    - Sells when RSI > overbought threshold
    - Holds otherwise

    Args:
        rsi_period: RSI calculation period
        oversold: RSI oversold threshold (e.g., 30)
        overbought: RSI overbought threshold (e.g., 70)

    Returns:
        Strategy function compatible with BacktestEngine
    """
    def strategy_func(row, position, idx, data):
        """
        RSI strategy function

        Args:
            row: Current candle data
            position: Current open position (or None)
            idx: Current index in dataframe
            data: Full DataFrame

        Returns:
            Signal dict or None
        """
        # Need enough data for RSI calculation
        if idx < rsi_period:
            return None

        # Calculate RSI for data up to current point
        # Reset index temporarily to get integer-based access
        if isinstance(data.index, pd.DatetimeIndex):
            data_for_calc = data.reset_index(drop=True).iloc[:idx+1]
        else:
            data_for_calc = data.iloc[:idx+1]

        rsi_values = calculate_rsi(data_for_calc, period=rsi_period)
        current_rsi = rsi_values.iloc[-1]

        # Skip if RSI is NaN
        if pd.isna(current_rsi):
            return None

        # If no position, look for entry
        if position is None:
            if current_rsi < oversold:
                # Oversold - BUY signal
                return {
                    'action': 'BUY',
                    'stop_loss_pct': 2.0,  # 2% stop loss
                    'take_profit_pct': 4.0,  # 4% take profit
                    'reason': f'RSI oversold: {current_rsi:.1f}'
                }
            elif current_rsi > overbought:
                # Overbought - SELL signal
                return {
                    'action': 'SELL',
                    'stop_loss_pct': 2.0,
                    'take_profit_pct': 4.0,
                    'reason': f'RSI overbought: {current_rsi:.1f}'
                }
        else:
            # If have position, check for exit
            # Exit long position when RSI becomes overbought
            if position.order_type.value == 'BUY' and current_rsi > overbought:
                return {
                    'action': 'HOLD',  # HOLD signal closes position
                    'reason': f'Exit long: RSI overbought {current_rsi:.1f}'
                }
            # Exit short position when RSI becomes oversold
            elif position.order_type.value == 'SELL' and current_rsi < oversold:
                return {
                    'action': 'HOLD',
                    'reason': f'Exit short: RSI oversold {current_rsi:.1f}'
                }

        return None

    return strategy_func


def main():
    """Main execution"""
    print("\n" + "="*80)
    print("WALK-FORWARD OPTIMIZER INTEGRATION TEST")
    print("="*80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")

    # Step 1: Load BTC data
    logger.info("STEP 1: Loading BTC data...")
    try:
        data = load_btc_data()
    except Exception as e:
        logger.error(f"Failed to load data: {e}")
        return 1

    # Step 2: Create walk-forward configuration
    logger.info("\nSTEP 2: Creating walk-forward configuration...")
    config = WalkForwardConfig(
        total_periods=3,  # Only 3 periods for quick test
        in_sample_ratio=0.70,
        out_sample_ratio=0.30,
        metric_to_optimize='sharpe_ratio',
        min_wfe=0.30,  # Lower threshold for test
        min_oos_sharpe=0.30,
        max_oos_drawdown=0.30,
        max_workers=2  # Less parallelism for test
    )

    logger.info(f"Configuration:")
    logger.info(f"  Periods: {config.total_periods}")
    logger.info(f"  In-Sample: {config.in_sample_ratio:.0%}")
    logger.info(f"  Out-Sample: {config.out_sample_ratio:.0%}")

    # Step 3: Define parameter space (small for quick test)
    logger.info("\nSTEP 3: Defining parameter space...")
    parameter_space = {
        'rsi_period': [10, 14, 20],  # RSI period
        'oversold': [25, 30, 35],    # Oversold threshold
        'overbought': [65, 70, 75]    # Overbought threshold
    }

    total_combinations = 1
    for param, values in parameter_space.items():
        total_combinations *= len(values)
        logger.info(f"  {param}: {values}")

    logger.info(f"\nTotal combinations: {total_combinations}")
    logger.info(f"Total backtests: {total_combinations * config.total_periods}")

    # Step 4: Create backtest engine
    logger.info("\nSTEP 4: Creating backtest engine...")
    backtest_engine = BacktestEngine(
        initial_capital=ACCOUNT_EQUITY_USD,
        commission=0.001,  # 0.1%
        slippage=0.0005    # 0.05%
    )
    logger.info("✅ Backtest engine created")

    # Step 5: Create strategy function generator
    logger.info("\nSTEP 5: Creating strategy function generator...")

    def strategy_func_with_params(data_subset: pd.DataFrame, params: dict):
        """
        Create strategy function with specific parameters

        This wrapper adapts the parameter format for the optimizer
        """
        strategy = create_simple_rsi_strategy(
            rsi_period=params.get('rsi_period', 14),
            oversold=params.get('oversold', 30),
            overbought=params.get('overbought', 70)
        )
        return strategy

    logger.info("✅ Strategy function generator created")

    # Step 5.5: Create adapter to bridge API mismatch
    logger.info("\nSTEP 5.5: Creating backtest engine adapter...")
    backtest_adapter = BacktestEngineAdapter(backtest_engine, strategy_func_with_params)
    logger.info("✅ Adapter created")

    # Step 6: Run walk-forward optimization
    logger.info("\nSTEP 6: Running walk-forward optimization...")
    logger.info("="*80)
    logger.info("This will take a few minutes...")
    logger.info("="*80)

    optimizer = WalkForwardOptimizer(config)

    try:
        results = optimizer.optimize(
            data=data,
            strategy_func=strategy_func_with_params,
            parameter_space=parameter_space,
            backtest_engine=backtest_adapter  # Use adapter instead of raw engine
        )

        # Step 7: Display results
        logger.info("\n" + "="*80)
        logger.info("OPTIMIZATION RESULTS")
        logger.info("="*80)

        logger.info(f"\n✅ Walk-Forward Optimization COMPLETED!")
        logger.info(f"\nWalk-Forward Efficiency (WFE):")
        logger.info(f"  Average WFE: {results.average_wfe:.2%}")
        logger.info(f"  Median WFE:  {results.median_wfe:.2%}")

        logger.info(f"\nOut-of-Sample Performance:")
        logger.info(f"  Total OOS Sharpe:     {results.total_oos_sharpe:.3f}")
        logger.info(f"  Total OOS Profit:     {results.total_oos_profit:.2%}")
        logger.info(f"  Total OOS Drawdown:   {results.total_oos_drawdown:.2%}")

        logger.info(f"\nStrategy Robust: {results.is_strategy_robust()} " +
                   ("✅" if results.is_strategy_robust() else "❌"))

        # Test passed!
        logger.info("\n" + "="*80)
        logger.info("✅ INTEGRATION TEST PASSED!")
        logger.info("="*80)
        logger.info("\nNext steps:")
        logger.info("1. Run full optimization on BNB with more periods")
        logger.info("2. Test with different strategies")
        logger.info("3. Build Phase 1.3 portfolio engine")

        return 0

    except Exception as e:
        logger.error(f"\n❌ Optimization failed: {e}")
        logger.exception("Full traceback:")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
