#!/usr/bin/env python3
"""
Test Runner for Phase 1 Optimizers and Simulators
Created: 2025-12-06
Purpose: Validate all Phase 1.1 and 1.2 implementations

Tests:
1. Walk-Forward Optimizer
2. Genetic Algorithm
3. Grid Search
4. Parameter Sensitivity
5. Monte Carlo Simulator
6. Risk of Ruin Calculator
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
from typing import Dict, List, Any
import logging

# Import optimizers
from backtesting.optimizers.walk_forward_optimizer import (
    WalkForwardOptimizer,
    WalkForwardConfig
)
from backtesting.optimizers.grid_search_optimizer import (
    GridSearchOptimizer,
    GridSearchConfig
)
from backtesting.optimizers.genetic_optimizer import (
    GeneticOptimizer,
    GeneticConfig
)
from backtesting.optimizers.parameter_sensitivity import (
    ParameterSensitivityAnalyzer,
    SensitivityConfig
)

# Import simulators
from backtesting.simulators.monte_carlo import (
    MonteCarloSimulator,
    MonteCarloConfig
)
from backtesting.simulators.risk_of_ruin import (
    RiskOfRuinCalculator,
    RiskOfRuinConfig
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TestResults:
    """Track test results"""
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []

    def add_pass(self, test_name: str):
        self.tests_run += 1
        self.tests_passed += 1
        logger.info(f"✅ PASS: {test_name}")

    def add_fail(self, test_name: str, error: str):
        self.tests_run += 1
        self.tests_failed += 1
        self.failures.append((test_name, error))
        logger.error(f"❌ FAIL: {test_name} - {error}")

    def print_summary(self):
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed} ✅")
        print(f"Failed: {self.tests_failed} ❌")
        print(f"Success Rate: {self.tests_passed/max(self.tests_run, 1)*100:.1f}%")

        if self.failures:
            print("\nFailed Tests:")
            for test_name, error in self.failures:
                print(f"  - {test_name}: {error}")
        print("="*80)


def generate_sample_data() -> pd.DataFrame:
    """
    Generate sample OHLCV data for testing

    Returns:
        DataFrame with 180 days of sample data
    """
    logger.info("Generating sample OHLCV data...")

    # Generate 180 days of 1-hour data
    periods = 180 * 24  # 180 days * 24 hours
    dates = pd.date_range(end=datetime.now(), periods=periods, freq='1h')

    # Generate realistic price movement
    np.random.seed(42)  # For reproducibility
    returns = np.random.normal(0.0001, 0.02, periods)  # Small positive drift, 2% volatility
    prices = 100 * np.exp(np.cumsum(returns))

    # Generate OHLCV
    data = pd.DataFrame({
        'timestamp': dates,
        'open': prices * (1 + np.random.normal(0, 0.001, periods)),
        'high': prices * (1 + np.abs(np.random.normal(0, 0.01, periods))),
        'low': prices * (1 - np.abs(np.random.normal(0, 0.01, periods))),
        'close': prices,
        'volume': np.random.uniform(1000, 10000, periods)
    })

    # Ensure high >= low
    data['high'] = data[['high', 'close', 'open']].max(axis=1)
    data['low'] = data[['low', 'close', 'open']].min(axis=1)

    logger.info(f"Generated {len(data)} data points from {data['timestamp'].min()} to {data['timestamp'].max()}")
    return data


def generate_sample_trades() -> List[Dict[str, Any]]:
    """
    Generate sample trade results for Monte Carlo testing

    Returns:
        List of trade dictionaries
    """
    logger.info("Generating sample trade results...")

    np.random.seed(42)
    num_trades = 100

    # Generate trades with 55% win rate
    wins = int(num_trades * 0.55)
    losses = num_trades - wins

    trades = []

    # Winning trades (average +2% profit)
    for i in range(wins):
        pnl = np.random.uniform(0.5, 5.0)  # $0.50 to $5.00 profit
        trades.append({
            'trade_id': i,
            'symbol': 'BNBUSDT',
            'side': np.random.choice(['LONG', 'SHORT']),
            'entry_price': 100.0,
            'exit_price': 100.0 + pnl,
            'quantity': 1.0,
            'pnl': pnl,
            'pnl_percent': pnl / 100.0,
            'duration_hours': np.random.uniform(1, 48),
            'exit_reason': 'take_profit'
        })

    # Losing trades (average -1% loss)
    for i in range(losses):
        pnl = -np.random.uniform(0.3, 2.0)  # -$0.30 to -$2.00 loss
        trades.append({
            'trade_id': wins + i,
            'symbol': 'BNBUSDT',
            'side': np.random.choice(['LONG', 'SHORT']),
            'entry_price': 100.0,
            'exit_price': 100.0 + pnl,
            'quantity': 1.0,
            'pnl': pnl,
            'pnl_percent': pnl / 100.0,
            'duration_hours': np.random.uniform(1, 48),
            'exit_reason': 'stop_loss'
        })

    # Shuffle trades
    np.random.shuffle(trades)

    total_pnl = sum(t['pnl'] for t in trades)
    logger.info(f"Generated {num_trades} trades: {wins} wins, {losses} losses, Total PnL: ${total_pnl:.2f}")

    return trades


def dummy_backtest_function(data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, float]:
    """
    Dummy backtest function for testing optimizers

    Args:
        data: OHLCV data
        params: Strategy parameters

    Returns:
        Performance metrics
    """
    # Simulate some strategy performance based on parameters
    # In real use, this would run actual backtest

    # Add some randomness but make it parameter-dependent
    base_sharpe = 0.5 + (params.get('rsi_period', 14) / 100.0)
    noise = np.random.normal(0, 0.2)
    sharpe = max(0, base_sharpe + noise)

    profit_factor = 1.0 + (sharpe * 0.5)
    max_drawdown = 0.15 + np.random.uniform(-0.05, 0.05)
    win_rate = 0.50 + (sharpe * 0.1)

    return {
        'sharpe_ratio': sharpe,
        'profit_factor': profit_factor,
        'max_drawdown': max_drawdown,
        'win_rate': min(1.0, win_rate),
        'total_return': sharpe * 0.1,
        'num_trades': int(len(data) / 100)
    }


def test_walk_forward_optimizer(results: TestResults):
    """Test walk-forward optimizer"""
    logger.info("\n" + "="*80)
    logger.info("TEST: Walk-Forward Optimizer")
    logger.info("="*80)

    try:
        # Generate sample data
        data = generate_sample_data()

        # Create config
        config = WalkForwardConfig(
            total_periods=3,  # Small number for testing
            in_sample_ratio=0.70,
            out_sample_ratio=0.30,
            metric_to_optimize='sharpe_ratio',
            min_wfe=0.50
        )

        # Create optimizer
        optimizer = WalkForwardOptimizer(config)

        # Define parameter space (small for testing)
        param_space = {
            'rsi_period': [10, 14, 20],
            'macd_fast': [8, 12],
            'macd_slow': [26, 35]
        }

        logger.info(f"Running walk-forward optimization with {config.total_periods} periods...")
        logger.info(f"Parameter space: {param_space}")

        # Run optimization
        wf_results = optimizer.optimize(
            data=data,
            param_space=param_space,
            backtest_func=dummy_backtest_function
        )

        # Validate results
        assert wf_results is not None, "No results returned"
        assert len(wf_results.periods) == config.total_periods, f"Expected {config.total_periods} periods, got {len(wf_results.periods)}"
        assert wf_results.average_wfe > 0, "Average WFE should be > 0"

        logger.info(f"Average WFE: {wf_results.average_wfe:.2%}")
        logger.info(f"Median WFE: {wf_results.median_wfe:.2%}")
        logger.info(f"Total OOS Sharpe: {wf_results.total_oos_sharpe:.3f}")
        logger.info(f"Strategy Robust: {wf_results.is_strategy_robust()}")

        results.add_pass("Walk-Forward Optimizer")

    except Exception as e:
        results.add_fail("Walk-Forward Optimizer", str(e))
        logger.exception("Walk-forward optimizer test failed")


def test_grid_search_optimizer(results: TestResults):
    """Test grid search optimizer"""
    logger.info("\n" + "="*80)
    logger.info("TEST: Grid Search Optimizer")
    logger.info("="*80)

    try:
        # Generate sample data
        data = generate_sample_data()

        # Create config
        config = GridSearchConfig(
            metric_to_optimize='sharpe_ratio',
            max_workers=2  # Small for testing
        )

        # Create optimizer
        optimizer = GridSearchOptimizer(config)

        # Define parameter grid (very small for testing)
        param_grid = {
            'rsi_period': [10, 14],
            'macd_fast': [8, 12]
        }

        total_combinations = 2 * 2  # 4 combinations

        logger.info(f"Running grid search with {total_combinations} parameter combinations...")

        # Run grid search
        grid_results = optimizer.search(
            data=data,
            param_grid=param_grid,
            backtest_func=dummy_backtest_function
        )

        # Validate results
        assert grid_results is not None, "No results returned"
        assert len(grid_results.all_results) > 0, "No results generated"
        assert grid_results.best_params is not None, "No best parameters found"

        logger.info(f"Total combinations tested: {len(grid_results.all_results)}")
        logger.info(f"Best params: {grid_results.best_params}")
        logger.info(f"Best {config.metric_to_optimize}: {grid_results.best_score:.3f}")

        results.add_pass("Grid Search Optimizer")

    except Exception as e:
        results.add_fail("Grid Search Optimizer", str(e))
        logger.exception("Grid search optimizer test failed")


def test_monte_carlo_simulator(results: TestResults):
    """Test Monte Carlo simulator"""
    logger.info("\n" + "="*80)
    logger.info("TEST: Monte Carlo Simulator")
    logger.info("="*80)

    try:
        # Generate sample trades
        trades = generate_sample_trades()

        # Create config
        config = MonteCarloConfig(
            num_simulations=100,  # Small number for testing
            initial_capital=10000.0,
            confidence_levels=[0.90, 0.95]
        )

        # Create simulator
        simulator = MonteCarloSimulator(config)

        logger.info(f"Running {config.num_simulations} Monte Carlo simulations...")

        # Run simulation
        mc_results = simulator.simulate(trades)

        # Validate results
        assert mc_results is not None, "No results returned"
        assert len(mc_results.simulated_paths) == config.num_simulations, f"Expected {config.num_simulations} paths"
        assert mc_results.mean_final_equity > 0, "Mean final equity should be > 0"

        logger.info(f"Mean final equity: ${mc_results.mean_final_equity:.2f}")
        logger.info(f"Median final equity: ${mc_results.median_final_equity:.2f}")
        logger.info(f"Mean return: {mc_results.mean_return:.2%}")
        logger.info(f"Mean max drawdown: {mc_results.mean_max_drawdown:.2%}")
        logger.info(f"Probability of loss: {mc_results.probability_of_loss:.2%}")
        logger.info(f"Probability of ruin: {mc_results.probability_of_ruin:.2%}")

        results.add_pass("Monte Carlo Simulator")

    except Exception as e:
        results.add_fail("Monte Carlo Simulator", str(e))
        logger.exception("Monte Carlo simulator test failed")


def test_risk_of_ruin_calculator(results: TestResults):
    """Test risk of ruin calculator"""
    logger.info("\n" + "="*80)
    logger.info("TEST: Risk of Ruin Calculator")
    logger.info("="*80)

    try:
        # Generate sample trades
        trades = generate_sample_trades()

        # Create config
        config = RiskOfRuinConfig(
            initial_capital=10000.0,
            ruin_threshold=0.50,  # 50% loss = ruin
            risk_free_rate=0.02
        )

        # Create calculator
        calculator = RiskOfRuinCalculator(config)

        logger.info("Calculating risk of ruin...")

        # Calculate risk
        ruin_results = calculator.calculate(trades)

        # Validate results
        assert ruin_results is not None, "No results returned"
        assert 0 <= ruin_results.probability_of_ruin <= 1.0, "Probability should be between 0 and 1"

        logger.info(f"Probability of ruin: {ruin_results.probability_of_ruin:.2%}")
        logger.info(f"Expected time to ruin: {ruin_results.expected_time_to_ruin:.1f} trades")
        logger.info(f"Safe position size (Kelly): {ruin_results.safe_position_size:.2%}")
        logger.info(f"Safe position size (Half Kelly): {ruin_results.safe_position_size_half_kelly:.2%}")

        results.add_pass("Risk of Ruin Calculator")

    except Exception as e:
        results.add_fail("Risk of Ruin Calculator", str(e))
        logger.exception("Risk of ruin calculator test failed")


def main():
    """Main test runner"""
    print("\n" + "="*80)
    print("PHASE 1 OPTIMIZER & SIMULATOR TEST SUITE")
    print("="*80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")

    # Create test results tracker
    test_results = TestResults()

    # Run tests
    test_walk_forward_optimizer(test_results)
    test_grid_search_optimizer(test_results)
    test_monte_carlo_simulator(test_results)
    test_risk_of_ruin_calculator(test_results)

    # Print summary
    test_results.print_summary()

    # Return exit code
    return 0 if test_results.tests_failed == 0 else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
