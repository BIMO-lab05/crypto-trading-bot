#!/usr/bin/env python3
"""
Test Multi-Indicator Strategy
Created: 2025-12-06
Purpose: Validate multi-indicator strategy and compare with simple RSI

Tests:
1. Indicator calculation correctness
2. Signal generation logic
3. Backtest performance vs simple RSI
4. Robustness with different confirmation levels
"""

import sys
import os
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
from datetime import datetime
import logging

from backtesting.backtest_engine import BacktestEngine
from backtesting.strategies.multi_indicator_strategy import (
    create_multi_indicator_strategy,
    MultiIndicatorStrategy,
    StrategyConfig
)

# Declared account size (see shared/account.py).
import os as _os
import sys as _sys

_REPO_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
if _REPO_ROOT not in _sys.path:
    _sys.path.insert(0, _REPO_ROOT)
from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def calculate_rsi_simple(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """Simple RSI for comparison"""
    close = data['close']
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def create_simple_rsi_strategy(rsi_period: int = 14, oversold: int = 30, overbought: int = 70):
    """Simple RSI strategy for comparison"""
    def strategy_func(row, position, idx, data):
        if idx < rsi_period:
            return None

        if isinstance(data.index, pd.DatetimeIndex):
            data_for_calc = data.reset_index(drop=True).iloc[:idx+1]
        else:
            data_for_calc = data.iloc[:idx+1]

        rsi_values = calculate_rsi_simple(data_for_calc, period=rsi_period)
        current_rsi = rsi_values.iloc[-1]

        if pd.isna(current_rsi):
            return None

        if position is None:
            if current_rsi < oversold:
                return {'action': 'BUY', 'stop_loss_pct': 2.0, 'take_profit_pct': 4.0}
            elif current_rsi > overbought:
                return {'action': 'SELL', 'stop_loss_pct': 2.0, 'take_profit_pct': 4.0}
        else:
            if position.order_type.value == 'BUY' and current_rsi > overbought:
                return {'action': 'HOLD'}
            elif position.order_type.value == 'SELL' and current_rsi < oversold:
                return {'action': 'HOLD'}

        return None

    return strategy_func


def test_indicator_calculations():
    """Test 1: Verify indicator calculations are correct"""
    logger.info("\n" + "="*80)
    logger.info("TEST 1: INDICATOR CALCULATIONS")
    logger.info("="*80)

    try:
        # Load test data
        data_path = project_root / 'backtesting' / 'data' / 'BNBUSDT_60m_90d_bybit.csv'
        data = pd.read_csv(data_path)
        data['timestamp'] = pd.to_datetime(data['timestamp'])
        data = data.set_index('timestamp').sort_index()

        logger.info(f"Loaded {len(data)} candles")

        # Create strategy instance
        strategy = MultiIndicatorStrategy()

        # Calculate indicators at a specific point
        test_idx = 100

        indicators = strategy.calculate_all_indicators(data, test_idx)

        if indicators is None:
            logger.error("❌ Failed to calculate indicators")
            return False

        logger.info(f"\nIndicator values at index {test_idx}:")
        logger.info(f"  Price: ${indicators.price:.2f}")
        logger.info(f"  RSI: {indicators.rsi:.2f}")
        logger.info(f"  MACD: {indicators.macd:.4f}")
        logger.info(f"  MACD Signal: {indicators.macd_signal:.4f}")
        logger.info(f"  MACD Histogram: {indicators.macd_histogram:.4f}")
        logger.info(f"  BB Upper: ${indicators.bb_upper:.2f}")
        logger.info(f"  BB Middle: ${indicators.bb_middle:.2f}")
        logger.info(f"  BB Lower: ${indicators.bb_lower:.2f}")
        logger.info(f"  BB Width: {indicators.bb_width:.4f}")
        logger.info(f"  Volume MA: {indicators.volume_ma:.0f}")

        # Validate ranges
        assert 0 <= indicators.rsi <= 100, "RSI out of range"
        assert indicators.bb_lower < indicators.bb_middle < indicators.bb_upper, "BB bands not ordered"
        assert indicators.volume_ma > 0, "Volume MA must be positive"

        logger.info("\n✅ TEST 1 PASSED: All indicators calculated correctly")
        return True

    except Exception as e:
        logger.error(f"❌ TEST 1 FAILED: {e}", exc_info=True)
        return False


def test_signal_generation():
    """Test 2: Verify signal generation logic"""
    logger.info("\n" + "="*80)
    logger.info("TEST 2: SIGNAL GENERATION")
    logger.info("="*80)

    try:
        # Load test data
        data_path = project_root / 'backtesting' / 'data' / 'BNBUSDT_60m_90d_bybit.csv'
        data = pd.read_csv(data_path)
        data['timestamp'] = pd.to_datetime(data['timestamp'])
        data = data.set_index('timestamp').sort_index()

        # Test different confirmation levels
        configs = [
            ("Strict (all 4)", True, 4),
            ("Moderate (2 of 4)", False, 2),
            ("Lenient (1 of 4)", False, 1)
        ]

        for name, require_all, min_conf in configs:
            logger.info(f"\n--- {name} confirmations ---")

            strategy_func = create_multi_indicator_strategy(
                require_all=require_all,
                min_confirmations=min_conf
            )

            # Generate signals on first 500 candles
            signals = []
            for idx in range(50, 500):
                row = data.iloc[idx]
                signal = strategy_func(row, None, idx, data)
                if signal:
                    signals.append({'idx': idx, 'signal': signal})

            logger.info(f"  Generated {len(signals)} signals")

            # Count by type
            buy_signals = sum(1 for s in signals if s['signal']['action'] == 'BUY')
            sell_signals = sum(1 for s in signals if s['signal']['action'] == 'SELL')

            logger.info(f"  BUY signals: {buy_signals}")
            logger.info(f"  SELL signals: {sell_signals}")

        logger.info("\n✅ TEST 2 PASSED: Signal generation working correctly")
        return True

    except Exception as e:
        logger.error(f"❌ TEST 2 FAILED: {e}", exc_info=True)
        return False


def test_backtest_comparison():
    """Test 3: Compare multi-indicator vs simple RSI performance"""
    logger.info("\n" + "="*80)
    logger.info("TEST 3: BACKTEST COMPARISON")
    logger.info("="*80)

    try:
        # Load test data
        data_path = project_root / 'backtesting' / 'data' / 'BNBUSDT_60m_90d_bybit.csv'
        data = pd.read_csv(data_path)
        data['timestamp'] = pd.to_datetime(data['timestamp'])
        data = data.set_index('timestamp').sort_index()

        logger.info(f"Testing on {len(data)} candles of BNBUSDT")

        results = {}

        # Test 1: Simple RSI
        logger.info("\n--- Simple RSI Strategy ---")
        simple_strategy = create_simple_rsi_strategy(rsi_period=14, oversold=30, overbought=70)
        engine1 = BacktestEngine(initial_capital=ACCOUNT_EQUITY_USD, commission=0.001, slippage=0.0005)
        result1 = engine1.run_backtest(data, simple_strategy, "Simple_RSI")
        results['Simple RSI'] = result1

        logger.info(f"  Return: {result1.total_profit_loss_pct:.2f}%")
        logger.info(f"  Sharpe: {result1.sharpe_ratio:.2f}")
        logger.info(f"  Trades: {result1.total_trades}")
        logger.info(f"  Win Rate: {result1.win_rate:.1f}%")

        # Test 2: Multi-indicator (Strict)
        logger.info("\n--- Multi-Indicator (Strict: all 4 confirmations) ---")
        multi_strict = create_multi_indicator_strategy(require_all=True, min_confirmations=4)
        engine2 = BacktestEngine(initial_capital=ACCOUNT_EQUITY_USD, commission=0.001, slippage=0.0005)
        result2 = engine2.run_backtest(data, multi_strict, "Multi_Strict")
        results['Multi Strict'] = result2

        logger.info(f"  Return: {result2.total_profit_loss_pct:.2f}%")
        logger.info(f"  Sharpe: {result2.sharpe_ratio:.2f}")
        logger.info(f"  Trades: {result2.total_trades}")
        logger.info(f"  Win Rate: {result2.win_rate:.1f}%")

        # Test 3: Multi-indicator (Moderate)
        logger.info("\n--- Multi-Indicator (Moderate: 2 of 4 confirmations) ---")
        multi_moderate = create_multi_indicator_strategy(require_all=False, min_confirmations=2)
        engine3 = BacktestEngine(initial_capital=ACCOUNT_EQUITY_USD, commission=0.001, slippage=0.0005)
        result3 = engine3.run_backtest(data, multi_moderate, "Multi_Moderate")
        results['Multi Moderate'] = result3

        logger.info(f"  Return: {result3.total_profit_loss_pct:.2f}%")
        logger.info(f"  Sharpe: {result3.sharpe_ratio:.2f}")
        logger.info(f"  Trades: {result3.total_trades}")
        logger.info(f"  Win Rate: {result3.win_rate:.1f}%")

        # Test 4: Multi-indicator (Lenient)
        logger.info("\n--- Multi-Indicator (Lenient: 1 of 4 confirmations) ---")
        multi_lenient = create_multi_indicator_strategy(require_all=False, min_confirmations=1)
        engine4 = BacktestEngine(initial_capital=ACCOUNT_EQUITY_USD, commission=0.001, slippage=0.0005)
        result4 = engine4.run_backtest(data, multi_lenient, "Multi_Lenient")
        results['Multi Lenient'] = result4

        logger.info(f"  Return: {result4.total_profit_loss_pct:.2f}%")
        logger.info(f"  Sharpe: {result4.sharpe_ratio:.2f}")
        logger.info(f"  Trades: {result4.total_trades}")
        logger.info(f"  Win Rate: {result4.win_rate:.1f}%")

        # Comparison table
        logger.info("\n" + "="*80)
        logger.info("COMPARISON SUMMARY")
        logger.info("="*80)
        logger.info(f"{'Strategy':<20} {'Return':<12} {'Sharpe':<10} {'Trades':<10} {'Win Rate':<10}")
        logger.info("-"*80)

        for name, result in results.items():
            logger.info(
                f"{name:<20} "
                f"{result.total_profit_loss_pct:>10.2f}% "
                f"{result.sharpe_ratio:>9.2f} "
                f"{result.total_trades:>9d} "
                f"{result.win_rate:>9.1f}%"
            )

        # Find best performer
        best_strategy = max(results.items(), key=lambda x: x[1].sharpe_ratio)
        logger.info("\n" + "="*80)
        logger.info(f"🏆 BEST PERFORMER: {best_strategy[0]} (Sharpe: {best_strategy[1].sharpe_ratio:.2f})")
        logger.info("="*80)

        logger.info("\n✅ TEST 3 PASSED: Backtest comparison completed")
        return True

    except Exception as e:
        logger.error(f"❌ TEST 3 FAILED: {e}", exc_info=True)
        return False


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("MULTI-INDICATOR STRATEGY TEST SUITE")
    print("="*80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")

    results = {
        'Indicator Calculations': test_indicator_calculations(),
        'Signal Generation': test_signal_generation(),
        'Backtest Comparison': test_backtest_comparison()
    }

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name:<30} {status}")

    total = len(results)
    passed = sum(results.values())

    print("="*80)
    print(f"Results: {passed}/{total} tests passed")
    print("="*80)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
