#!/usr/bin/env python3
"""
Portfolio Engine Test Suite
Created: 2025-12-06
Purpose: Test PortfolioBacktestEngine and StrategyAllocator

Tests portfolio backtesting with multiple strategies and various
allocation optimization methods.
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

from backtesting.portfolio.portfolio_backtest import PortfolioBacktestEngine, PortfolioMetrics
from backtesting.portfolio.strategy_allocation import StrategyAllocator, AllocationResult

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def calculate_rsi(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate RSI indicator"""
    close = data['close']
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def create_rsi_strategy(rsi_period: int, oversold: int, overbought: int):
    """Create RSI-based strategy function"""
    def strategy_func(row, position, idx, data):
        if idx < rsi_period:
            return None

        if isinstance(data.index, pd.DatetimeIndex):
            data_for_calc = data.reset_index(drop=True).iloc[:idx+1]
        else:
            data_for_calc = data.iloc[:idx+1]

        rsi_values = calculate_rsi(data_for_calc, period=rsi_period)
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


def test_portfolio_backtest():
    """Test 1: Portfolio backtesting with multiple strategies"""
    logger.info("\n" + "="*80)
    logger.info("TEST 1: PORTFOLIO BACKTESTING")
    logger.info("="*80)

    try:
        # Load data for 3 symbols
        symbols = ['BNBUSDT', 'SOLUSDT', 'ADAUSDT']
        data_dict = {}

        for symbol in symbols:
            data_path = project_root / 'backtesting' / 'data' / f'{symbol}_60m_90d_bybit.csv'
            if not data_path.exists():
                logger.warning(f"Data file not found: {data_path}")
                continue

            data = pd.read_csv(data_path)
            data['timestamp'] = pd.to_datetime(data['timestamp'])
            data = data.set_index('timestamp').sort_index()
            data_dict[symbol] = data
            logger.info(f"Loaded {symbol}: {len(data)} candles")

        if not data_dict:
            logger.error("No data loaded, skipping test")
            return False

        # Create portfolio engine
        portfolio = PortfolioBacktestEngine(
            initial_capital=10000.0,
            commission=0.001,
            slippage=0.0005
        )

        # Add strategies with equal allocation
        allocation_per_strategy = 100.0 / len(data_dict)

        for symbol in data_dict.keys():
            # Use different RSI parameters for each strategy
            if symbol == 'BNBUSDT':
                strategy_func = create_rsi_strategy(rsi_period=14, oversold=30, overbought=70)
            elif symbol == 'SOLUSDT':
                strategy_func = create_rsi_strategy(rsi_period=20, oversold=25, overbought=75)
            else:  # ADAUSDT
                strategy_func = create_rsi_strategy(rsi_period=10, oversold=35, overbought=65)

            portfolio.add_strategy(
                name=f"{symbol}_RSI",
                symbol=symbol,
                strategy_func=strategy_func,
                allocation_pct=allocation_per_strategy
            )

        # Run portfolio backtest
        logger.info("\nRunning portfolio backtest...")
        metrics = portfolio.run_backtest(data_dict=data_dict)

        # Validate results
        logger.info("\n" + "="*80)
        logger.info("PORTFOLIO BACKTEST RESULTS")
        logger.info("="*80)
        logger.info(f"Total Return:     {metrics.total_return:>10.2f}%")
        logger.info(f"Sharpe Ratio:     {metrics.sharpe_ratio:>10.2f}")
        logger.info(f"Max Drawdown:     {metrics.max_drawdown:>10.2f}%")
        logger.info(f"Win Rate:         {metrics.win_rate:>10.2f}%")
        logger.info(f"Total Trades:     {metrics.total_trades:>10d}")

        logger.info("\nPer-Strategy Performance:")
        for strategy_name in metrics.strategy_returns.keys():
            logger.info(f"  {strategy_name}:")
            logger.info(f"    Return: {metrics.strategy_returns[strategy_name]:>8.2f}%")
            logger.info(f"    Sharpe: {metrics.strategy_sharpe[strategy_name]:>8.2f}")
            logger.info(f"    Trades: {metrics.strategy_trades[strategy_name]:>8d}")

        logger.info("\n✅ TEST 1 PASSED: Portfolio backtest completed successfully")
        return True

    except Exception as e:
        logger.error(f"❌ TEST 1 FAILED: {e}", exc_info=True)
        return False


def test_strategy_allocator():
    """Test 2: Strategy allocation optimization"""
    logger.info("\n" + "="*80)
    logger.info("TEST 2: STRATEGY ALLOCATION OPTIMIZATION")
    logger.info("="*80)

    try:
        # Create allocator
        allocator = StrategyAllocator(
            min_allocation=0.10,  # 10% minimum
            max_allocation=0.60   # 60% maximum
        )

        # Mock strategy metrics
        strategy_metrics = {
            'BNB_RSI': {
                'sharpe': 1.8,
                'return': 0.25,
                'volatility': 0.15,
                'win_rate': 0.65,
                'avg_win': 0.04,
                'avg_loss': 0.02
            },
            'SOL_RSI': {
                'sharpe': 1.5,
                'return': 0.20,
                'volatility': 0.18,
                'win_rate': 0.60,
                'avg_win': 0.03,
                'avg_loss': 0.02
            },
            'ADA_RSI': {
                'sharpe': 1.2,
                'return': 0.15,
                'volatility': 0.12,
                'win_rate': 0.58,
                'avg_win': 0.025,
                'avg_loss': 0.015
            }
        }

        # Test 2.1: Equal weight allocation
        logger.info("\n--- Test 2.1: Equal Weight ---")
        equal_result = allocator.equal_weight(list(strategy_metrics.keys()))
        logger.info(f"Weights: {equal_result.weights}")
        logger.info(f"Diversification: {equal_result.diversification_ratio:.2f}")
        assert abs(sum(equal_result.weights.values()) - 1.0) < 0.01, "Weights don't sum to 1"
        logger.info("✅ Equal weight allocation passed")

        # Test 2.2: Sharpe weighted allocation
        logger.info("\n--- Test 2.2: Sharpe Weighted ---")
        sharpe_result = allocator.sharpe_weighted(strategy_metrics)
        logger.info(f"Weights: {sharpe_result.weights}")
        logger.info(f"Expected Return: {sharpe_result.expected_return:.2%}")
        logger.info(f"Expected Sharpe: {sharpe_result.expected_sharpe:.2f}")
        assert abs(sum(sharpe_result.weights.values()) - 1.0) < 0.01, "Weights don't sum to 1"
        # BNB should have highest weight (highest Sharpe)
        assert sharpe_result.weights['BNB_RSI'] > sharpe_result.weights['SOL_RSI'], "BNB should have higher weight"
        logger.info("✅ Sharpe weighted allocation passed")

        # Test 2.3: Risk parity allocation
        logger.info("\n--- Test 2.3: Risk Parity ---")
        risk_result = allocator.risk_parity(strategy_metrics)
        logger.info(f"Weights: {risk_result.weights}")
        logger.info(f"Diversification: {risk_result.diversification_ratio:.2f}")
        assert abs(sum(risk_result.weights.values()) - 1.0) < 0.01, "Weights don't sum to 1"
        logger.info("✅ Risk parity allocation passed")

        # Test 2.4: Kelly optimal allocation
        logger.info("\n--- Test 2.4: Kelly Optimal ---")
        kelly_result = allocator.kelly_optimal(strategy_metrics)
        logger.info(f"Weights: {kelly_result.weights}")
        logger.info(f"Expected Return: {kelly_result.expected_return:.2%}")
        assert abs(sum(kelly_result.weights.values()) - 1.0) < 0.01, "Weights don't sum to 1"
        logger.info("✅ Kelly optimal allocation passed")

        # Test 2.5: Allocation comparison
        logger.info("\n--- Test 2.5: Allocation Comparison ---")
        comparison = allocator.compare_allocations(strategy_metrics)
        logger.info(f"\nComparison Table:\n{comparison.to_string()}")
        assert len(comparison) >= 4, "Should have at least 4 allocation methods"
        logger.info("✅ Allocation comparison passed")

        logger.info("\n✅ TEST 2 PASSED: All allocation methods work correctly")
        return True

    except Exception as e:
        logger.error(f"❌ TEST 2 FAILED: {e}", exc_info=True)
        return False


def test_allocation_with_returns_data():
    """Test 3: Advanced allocation methods with returns data"""
    logger.info("\n" + "="*80)
    logger.info("TEST 3: ADVANCED ALLOCATION WITH RETURNS DATA")
    logger.info("="*80)

    try:
        # Generate synthetic returns data
        np.random.seed(42)
        n_days = 100

        returns_data = pd.DataFrame({
            'BNB_RSI': np.random.normal(0.001, 0.02, n_days),
            'SOL_RSI': np.random.normal(0.0008, 0.025, n_days),
            'ADA_RSI': np.random.normal(0.0005, 0.015, n_days)
        })

        logger.info(f"Generated {n_days} days of synthetic returns")
        logger.info(f"Correlation matrix:\n{returns_data.corr()}")

        allocator = StrategyAllocator(min_allocation=0.10, max_allocation=0.60)

        # Test 3.1: Minimum variance
        logger.info("\n--- Test 3.1: Minimum Variance ---")
        min_var_result = allocator.minimum_variance(returns_data)
        logger.info(f"Weights: {min_var_result.weights}")
        logger.info(f"Expected Volatility: {min_var_result.expected_volatility:.2%}")
        assert abs(sum(min_var_result.weights.values()) - 1.0) < 0.01, "Weights don't sum to 1"
        logger.info("✅ Minimum variance allocation passed")

        # Test 3.2: Maximum Sharpe
        logger.info("\n--- Test 3.2: Maximum Sharpe ---")
        max_sharpe_result = allocator.maximum_sharpe(returns_data, risk_free_rate=0.0)
        logger.info(f"Weights: {max_sharpe_result.weights}")
        logger.info(f"Expected Return: {max_sharpe_result.expected_return:.2%}")
        logger.info(f"Expected Sharpe: {max_sharpe_result.expected_sharpe:.2f}")
        assert abs(sum(max_sharpe_result.weights.values()) - 1.0) < 0.01, "Weights don't sum to 1"
        logger.info("✅ Maximum Sharpe allocation passed")

        logger.info("\n✅ TEST 3 PASSED: Advanced allocation methods work correctly")
        return True

    except Exception as e:
        logger.error(f"❌ TEST 3 FAILED: {e}", exc_info=True)
        return False


def test_constraint_handling():
    """Test 4: Allocation constraint handling"""
    logger.info("\n" + "="*80)
    logger.info("TEST 4: CONSTRAINT HANDLING")
    logger.info("="*80)

    try:
        # Create allocator with strict constraints
        allocator = StrategyAllocator(
            min_allocation=0.20,  # 20% minimum
            max_allocation=0.50   # 50% maximum
        )

        strategy_metrics = {
            'Strategy_A': {'sharpe': 3.0, 'return': 0.50},  # Very high Sharpe
            'Strategy_B': {'sharpe': 1.0, 'return': 0.10},
            'Strategy_C': {'sharpe': 0.5, 'return': 0.05}   # Low Sharpe
        }

        # Sharpe weighted should respect max constraint
        result = allocator.sharpe_weighted(strategy_metrics)

        logger.info(f"Weights with constraints: {result.weights}")

        # Verify constraints
        for name, weight in result.weights.items():
            assert weight >= 0.20 - 0.01, f"{name} weight {weight} below minimum 0.20"
            assert weight <= 0.50 + 0.01, f"{name} weight {weight} above maximum 0.50"
            logger.info(f"  {name}: {weight:.2%} (within bounds)")

        # Verify sum to 1
        total = sum(result.weights.values())
        assert abs(total - 1.0) < 0.01, f"Weights sum to {total}, not 1.0"

        logger.info("\n✅ TEST 4 PASSED: Constraints properly enforced")
        return True

    except Exception as e:
        logger.error(f"❌ TEST 4 FAILED: {e}", exc_info=True)
        return False


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("PORTFOLIO ENGINE TEST SUITE")
    print("="*80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")

    results = {
        'Portfolio Backtest': test_portfolio_backtest(),
        'Strategy Allocator': test_strategy_allocator(),
        'Advanced Allocation': test_allocation_with_returns_data(),
        'Constraint Handling': test_constraint_handling()
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
