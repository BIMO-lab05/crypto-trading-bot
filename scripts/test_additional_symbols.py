#!/usr/bin/env python3
"""
Test Simple RSI on Additional Symbols
Purpose: Find symbols where Simple RSI shows robust performance
Date: 2025-12-06

After discovering BNB/SOL/ADA all fail walk-forward validation,
test on major cryptocurrencies to find robust opportunities.
"""

import sys
from pathlib import Path
import pandas as pd
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backtesting.backtest_engine import BacktestEngine
from backtesting.optimizers.walk_forward_optimizer import WalkForwardOptimizer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)
logger = logging.getLogger(__name__)


def create_simple_rsi_strategy():
    """Create Simple RSI strategy function"""
    def calc_rsi(data, period=14):
        close = data['close']
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def strategy_func(row, position, idx, data):
        if idx < 14:
            return None

        data_subset = data.reset_index(drop=True).iloc[:idx+1] if isinstance(data.index, pd.DatetimeIndex) else data.iloc[:idx+1]
        rsi = calc_rsi(data_subset).iloc[-1]

        if pd.isna(rsi):
            return None

        if position is None:
            if rsi < 30:
                return {'action': 'BUY', 'stop_loss_pct': 2.0, 'take_profit_pct': 4.0}
            elif rsi > 70:
                return {'action': 'SELL', 'stop_loss_pct': 2.0, 'take_profit_pct': 4.0}
        else:
            if position.order_type.value == 'BUY' and rsi > 70:
                return {'action': 'HOLD'}
            elif position.order_type.value == 'SELL' and rsi < 30:
                return {'action': 'HOLD'}

        return None

    return strategy_func


def test_symbol_walkforward(symbol: str):
    """Test symbol with walk-forward optimization"""
    logger.info(f"\n{'='*80}")
    logger.info(f"TESTING {symbol} WITH WALK-FORWARD OPTIMIZATION")
    logger.info(f"{'='*80}")

    # Load data
    data_path = project_root / f'backtesting/data/{symbol}_60m_90d_bybit.csv'

    if not data_path.exists():
        logger.warning(f"Data file not found: {data_path}")
        logger.info(f"Skipping {symbol}")
        return None

    data = pd.read_csv(data_path)
    data['timestamp'] = pd.to_datetime(data['timestamp'])
    data = data.set_index('timestamp').sort_index()

    logger.info(f"Data: {len(data)} candles from {data.index[0]} to {data.index[-1]}")

    # Initialize backtest engine
    engine = BacktestEngine(initial_capital=10000.0, commission=0.001, slippage=0.0005)

    # Create strategy
    strategy = create_simple_rsi_strategy()

    # Define parameter grid for optimization
    param_grid = {
        'rsi_period': [10, 14, 20],
        'oversold': [25, 30, 35],
        'overbought': [65, 70, 75]
    }

    # Initialize walk-forward optimizer
    optimizer = WalkForwardOptimizer(
        backtest_engine=engine,
        data=data,
        strategy_name="Simple RSI",
        num_periods=5,
        is_oos_ratio=0.65  # 65% in-sample, 35% out-of-sample
    )

    # Run walk-forward optimization
    results = optimizer.optimize(
        param_grid=param_grid,
        strategy_factory=lambda params: create_simple_rsi_with_params(params)
    )

    # Save results
    results_path = project_root / f'backtesting/results/{symbol}_walkforward_{pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")}.json'
    optimizer.save_results(str(results_path))

    logger.info(f"\n{symbol} RESULTS:")
    logger.info(f"  Average WFE: {results['average_wfe']:.2f}%")
    logger.info(f"  OOS Sharpe:  {results['oos_sharpe']:.3f}")
    logger.info(f"  OOS Profit:  {results['oos_total_return_pct']:.2f}%")
    logger.info(f"  Robust:      {'YES ✅' if results['is_robust'] else 'NO ❌'}")
    logger.info(f"  Saved to: {results_path}")

    return results


def create_simple_rsi_with_params(params):
    """Create Simple RSI strategy with custom parameters"""
    rsi_period = params.get('rsi_period', 14)
    oversold = params.get('oversold', 30)
    overbought = params.get('overbought', 70)

    def calc_rsi(data, period=rsi_period):
        close = data['close']
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def strategy_func(row, position, idx, data):
        if idx < rsi_period:
            return None

        data_subset = data.reset_index(drop=True).iloc[:idx+1] if isinstance(data.index, pd.DatetimeIndex) else data.iloc[:idx+1]
        rsi = calc_rsi(data_subset).iloc[-1]

        if pd.isna(rsi):
            return None

        if position is None:
            if rsi < oversold:
                return {'action': 'BUY', 'stop_loss_pct': 2.0, 'take_profit_pct': 4.0}
            elif rsi > overbought:
                return {'action': 'SELL', 'stop_loss_pct': 2.0, 'take_profit_pct': 4.0}
        else:
            if position.order_type.value == 'BUY' and rsi > overbought:
                return {'action': 'HOLD'}
            elif position.order_type.value == 'SELL' and rsi < oversold:
                return {'action': 'HOLD'}

        return None

    return strategy_func


def main():
    """Test Simple RSI on additional major cryptocurrencies"""

    # Symbols to test (in order of market cap)
    test_symbols = [
        'BTCUSDT',   # Bitcoin - largest market cap
        'ETHUSDT',   # Ethereum - 2nd largest
        'XRPUSDT',   # XRP - major altcoin
        'DOGEUSDT',  # Dogecoin - meme coin with volume
    ]

    logger.info("="*80)
    logger.info("TESTING SIMPLE RSI ON ADDITIONAL SYMBOLS")
    logger.info("Searching for robust strategy/symbol combinations")
    logger.info("="*80)

    results_summary = []

    for symbol in test_symbols:
        try:
            result = test_symbol_walkforward(symbol)
            if result:
                results_summary.append({
                    'symbol': symbol,
                    'wfe': result['average_wfe'],
                    'oos_sharpe': result['oos_sharpe'],
                    'oos_return': result['oos_total_return_pct'],
                    'robust': result['is_robust']
                })
        except Exception as e:
            logger.error(f"Error testing {symbol}: {e}")
            continue

    # Print summary
    logger.info("\n" + "="*80)
    logger.info("FINAL SUMMARY - SIMPLE RSI ACROSS ALL SYMBOLS")
    logger.info("="*80)

    if results_summary:
        logger.info("\n{:<12} {:<15} {:<12} {:<12} {:<10}".format(
            "Symbol", "WFE", "OOS Sharpe", "OOS Return", "Robust"
        ))
        logger.info("-"*80)

        robust_found = False
        for r in results_summary:
            status = "✅" if r['robust'] else "❌"
            logger.info("{:<12} {:<15.2f}% {:<12.3f} {:<12.2f}% {:<10}".format(
                r['symbol'], r['wfe'], r['oos_sharpe'], r['oos_return'], status
            ))
            if r['robust']:
                robust_found = True

        logger.info("="*80)

        if robust_found:
            logger.info("\n✅ FOUND ROBUST STRATEGY/SYMBOL COMBINATIONS!")
            logger.info("Symbols with WFE > 40% and positive OOS returns can be traded.")
        else:
            logger.info("\n❌ NO ROBUST COMBINATIONS FOUND")
            logger.info("Simple RSI strategy does not show robust performance on any tested symbols.")
            logger.info("\nRECOMMENDATION:")
            logger.info("1. Test other strategies (multi-indicator, ML, sentiment)")
            logger.info("2. Try different timeframes (15m, 4H, 1D)")
            logger.info("3. Consider market regime detection")
            logger.info("4. Explore ensemble approaches")
    else:
        logger.error("No results collected. Check data files.")

    logger.info("\n" + "="*80)


if __name__ == "__main__":
    main()
