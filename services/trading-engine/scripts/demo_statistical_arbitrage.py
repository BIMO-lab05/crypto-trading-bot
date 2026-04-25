#!/usr/bin/env python3
"""
Statistical Arbitrage Strategies Demonstration Script

Demonstrates all Phase 2.2 statistical arbitrage strategies in action:
- Pairs Trading (BTCUSDT/ETHUSDT)
- Funding Rate Arbitrage (BTCUSDT, ETHUSDT)
- Triangular Arbitrage (BTC/ETH/BNB/USDT)

Shows complete workflow:
1. Manager initialization with capital allocation
2. Strategy setup and calibration
3. Signal generation
4. Trade execution simulation
5. Performance monitoring

Author: Trading Bot Development Team
Date: 2025-12-07
"""

import sys
import os
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List
import logging

# Import Phase 2.2 components
from app.managers import (
    StatisticalArbitrageManager,
    StrategyAllocation,
    PortfolioPerformance
)
from app.strategies.pairs_trading import PairsTradeSignal
from app.strategies.funding_rate_arbitrage import FundingRateSignal
from app.strategies.triangular_arbitrage import TriangularArbitrageSignal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MarketDataSimulator:
    """Simulates realistic market data for demonstration"""

    def __init__(self, seed: int = 42):
        """Initialize simulator with random seed for reproducibility"""
        np.random.seed(seed)
        self.current_time = datetime.now()

        # Base prices
        self.btc_price = 50000.0
        self.eth_price = 2000.0
        self.bnb_price = 300.0

        logger.info("Market data simulator initialized")

    def generate_historical_prices(
        self,
        symbol: str,
        days: int = 100
    ) -> pd.Series:
        """
        Generate historical price series with realistic patterns

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            days: Number of days of historical data

        Returns:
            Pandas Series with datetime index and prices
        """
        # Base parameters by symbol
        params = {
            'BTCUSDT': {'base': 50000, 'volatility': 0.02, 'trend': 0.0001},
            'ETHUSDT': {'base': 2000, 'volatility': 0.025, 'trend': 0.00012},
            'BNBUSDT': {'base': 300, 'volatility': 0.03, 'trend': 0.00015},
        }

        config = params.get(symbol, params['BTCUSDT'])

        # Generate price series with geometric Brownian motion
        dates = pd.date_range(
            end=self.current_time,
            periods=days,
            freq='1D'
        )

        returns = np.random.normal(
            config['trend'],
            config['volatility'],
            days
        )

        prices = config['base'] * np.exp(np.cumsum(returns))

        return pd.Series(prices, index=dates)

    def get_current_prices(self) -> Dict[str, float]:
        """Get current spot prices for all symbols"""
        # Add small random movements
        btc_move = np.random.normal(0, 0.001)
        eth_move = np.random.normal(0, 0.0012)
        bnb_move = np.random.normal(0, 0.0015)

        self.btc_price *= (1 + btc_move)
        self.eth_price *= (1 + eth_move)
        self.bnb_price *= (1 + bnb_move)

        return {
            'BTCUSDT': self.btc_price,
            'ETHUSDT': self.eth_price,
            'BNBUSDT': self.bnb_price,
        }

    def get_funding_data(self, symbol: str) -> Dict[str, float]:
        """
        Generate funding rate data

        Args:
            symbol: Trading symbol

        Returns:
            Dictionary with funding_rate, spot_price, futures_price
        """
        spot_price = self.get_current_prices()[symbol]

        # Generate realistic funding rate (-0.1% to 0.1%)
        funding_rate = np.random.normal(0.0001, 0.0003)

        # Futures price with small basis (0-1%)
        basis_pct = np.random.uniform(0.0, 0.01)
        futures_price = spot_price * (1 + basis_pct)

        return {
            'funding_rate': funding_rate,
            'spot_price': spot_price,
            'futures_price': futures_price
        }

    def get_triangular_prices(self) -> Dict[str, float]:
        """
        Get prices for triangular arbitrage paths

        Returns:
            Dictionary with all trading pair prices
        """
        prices = self.get_current_prices()

        # Calculate cross rates with small inefficiencies
        btc_eth_rate = prices['BTCUSDT'] / prices['ETHUSDT']
        btc_bnb_rate = prices['BTCUSDT'] / prices['BNBUSDT']
        eth_bnb_rate = prices['ETHUSDT'] / prices['BNBUSDT']

        # Add small pricing inefficiencies (0-0.2%)
        inefficiency = lambda: 1 + np.random.uniform(-0.002, 0.002)

        return {
            'BTCUSDT': prices['BTCUSDT'],
            'ETHUSDT': prices['ETHUSDT'],
            'BNBUSDT': prices['BNBUSDT'],
            'BTCETH': btc_eth_rate * inefficiency(),
            'BTCBNB': btc_bnb_rate * inefficiency(),
            'ETHBNB': eth_bnb_rate * inefficiency(),
        }


class TradeExecutor:
    """Simulates trade execution and tracks results"""

    def __init__(self):
        """Initialize trade executor"""
        self.executed_trades: List[Dict] = []
        logger.info("Trade executor initialized")

    def execute_pairs_trade(
        self,
        signal: PairsTradeSignal,
        strategy_id: str
    ) -> Dict[str, Any]:
        """
        Simulate pairs trade execution

        Args:
            signal: Pairs trading signal
            strategy_id: Strategy identifier

        Returns:
            Execution result with P&L
        """
        # Simulate execution with small slippage
        slippage = 0.0005  # 0.05%

        # Calculate simulated profit based on position sizes (random for demo)
        total_position = abs(signal.position_size_x) + abs(signal.position_size_y)
        profit = np.random.normal(total_position * 0.005, total_position * 0.002)

        result = {
            'strategy_id': strategy_id,
            'signal': signal,
            'executed_at': datetime.now(),
            'profit': profit,
            'status': 'filled',
            'slippage': slippage
        }

        self.executed_trades.append(result)

        logger.info(
            f"Executed pairs trade {strategy_id}: "
            f"Action={signal.action}, P&L=${profit:.2f}"
        )

        return result

    def execute_funding_trade(
        self,
        signal: FundingRateSignal,
        strategy_id: str
    ) -> Dict[str, Any]:
        """
        Simulate funding rate trade execution

        Args:
            signal: Funding rate signal
            strategy_id: Strategy identifier

        Returns:
            Execution result with P&L
        """
        # Simulate funding collection
        if signal.action == 'OPEN_HEDGE':
            profit = 0.0  # No immediate profit on open
        else:  # CLOSE_HEDGE
            # Simulate collected funding (based on hold time and position size)
            total_position = signal.spot_position_size + signal.futures_position_size
            profit = np.random.normal(total_position * 0.003, total_position * 0.001)

        result = {
            'strategy_id': strategy_id,
            'signal': signal,
            'executed_at': datetime.now(),
            'profit': profit,
            'status': 'filled'
        }

        self.executed_trades.append(result)

        logger.info(
            f"Executed funding trade {strategy_id}: "
            f"Action={signal.action}, P&L=${profit:.2f}"
        )

        return result

    def execute_triangular_trade(
        self,
        signal: TriangularArbitrageSignal
    ) -> Dict[str, Any]:
        """
        Simulate triangular arbitrage execution

        Args:
            signal: Triangular arbitrage signal

        Returns:
            Execution result with P&L
        """
        # Calculate profit based on net profit % and execution amount
        profit = signal.execution_amount * (signal.net_profit_pct / 100.0)

        result = {
            'strategy_id': 'triangular',
            'signal': signal,
            'executed_at': datetime.now(),
            'profit': profit,
            'status': 'filled',
            'path': ' -> '.join(signal.path.symbols)
        }

        self.executed_trades.append(result)

        logger.info(
            f"Executed triangular arbitrage: "
            f"Path={result['path']}, P&L=${profit:.2f}"
        )

        return result

    def get_total_profit(self) -> float:
        """Calculate total profit from all trades"""
        return sum(trade['profit'] for trade in self.executed_trades)


def print_header(text: str):
    """Print formatted section header"""
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80 + "\n")


def print_performance_summary(performance: PortfolioPerformance):
    """Print formatted performance summary"""
    print("\n" + "-" * 80)
    print("PORTFOLIO PERFORMANCE SUMMARY")
    print("-" * 80)
    print(f"Total Capital:        ${performance.total_capital:,.2f}")
    print(f"Allocated Capital:    ${performance.allocated_capital:,.2f}")
    print(f"Total Profit:         ${performance.total_profit:,.2f}")
    print(f"Return on Capital:    {(performance.total_profit / performance.total_capital * 100):.2f}%")
    print(f"Total Trades:         {performance.total_trades}")
    print(f"Winning Trades:       {performance.winning_trades}")
    print(f"Losing Trades:        {performance.losing_trades}")
    print(f"Win Rate:             {performance.win_rate:.2f}%")
    print(f"Sharpe Ratio:         {performance.sharpe_ratio or 'N/A'}")
    print(f"Max Drawdown:         {performance.max_drawdown:.2f}%")
    print("-" * 80)


def main():
    """Main demonstration script"""

    print_header("STATISTICAL ARBITRAGE STRATEGIES DEMONSTRATION")

    # ========================================================================
    # STEP 1: Initialize Components
    # ========================================================================
    print_header("STEP 1: Initializing Components")

    # Create custom allocation (40% pairs, 40% funding, 20% triangular)
    allocation = StrategyAllocation(
        pairs_trading=0.4,
        funding_rate=0.4,
        triangular=0.2
    )

    # Initialize manager with $100,000 capital
    manager = StatisticalArbitrageManager(
        total_capital=100000.0,
        allocation=allocation,
        enable_pairs=True,
        enable_funding=True,
        enable_triangular=True
    )

    print(f"✅ Manager initialized with ${manager.total_capital:,.2f}")
    print(f"   Capital Allocation: Pairs={allocation.pairs_trading*100:.0f}%, "
          f"Funding={allocation.funding_rate*100:.0f}%, "
          f"Triangular={allocation.triangular*100:.0f}%")

    # Initialize market data simulator
    simulator = MarketDataSimulator(seed=42)
    print("✅ Market data simulator initialized")

    # Initialize trade executor
    executor = TradeExecutor()
    print("✅ Trade executor initialized")

    # ========================================================================
    # STEP 2: Setup Strategies
    # ========================================================================
    print_header("STEP 2: Setting Up Strategies")

    # Add pairs trading strategies
    print("\n📊 Adding Pairs Trading Strategies:")
    pairs_id_1 = manager.add_pairs_strategy(
        symbol_x='BTCUSDT',
        symbol_y='ETHUSDT',
        entry_threshold=2.0,
        exit_threshold=0.5
    )
    print(f"   ✓ Added: {pairs_id_1}")

    # Add funding rate arbitrage strategies
    print("\n💰 Adding Funding Rate Arbitrage Strategies:")
    funding_id_1 = manager.add_funding_strategy(
        symbol='BTCUSDT',
        min_funding_rate=0.0003,
        max_basis_pct=2.0
    )
    print(f"   ✓ Added: {funding_id_1}")

    funding_id_2 = manager.add_funding_strategy(
        symbol='ETHUSDT',
        min_funding_rate=0.0003,
        max_basis_pct=2.0
    )
    print(f"   ✓ Added: {funding_id_2}")

    # Setup triangular arbitrage
    print("\n🔺 Setting Up Triangular Arbitrage:")
    triangular_setup = manager.setup_triangular_arbitrage(
        assets=['BTC', 'ETH', 'BNB', 'USDT'],
        min_profit_threshold=0.005,  # 0.5% minimum profit
        max_latency_ms=100.0
    )
    print(f"   ✓ Triangular arbitrage: {'Configured' if triangular_setup else 'Failed'}")

    # ========================================================================
    # STEP 3: Calibrate Pairs Strategies
    # ========================================================================
    print_header("STEP 3: Calibrating Pairs Trading Strategies")

    # Generate historical data for calibration
    print("\n📈 Generating historical price data (100 days)...")
    btc_historical = simulator.generate_historical_prices('BTCUSDT', days=100)
    eth_historical = simulator.generate_historical_prices('ETHUSDT', days=100)

    print(f"   BTC: {len(btc_historical)} data points, "
          f"Price range: ${btc_historical.min():.2f} - ${btc_historical.max():.2f}")
    print(f"   ETH: {len(eth_historical)} data points, "
          f"Price range: ${eth_historical.min():.2f} - ${eth_historical.max():.2f}")

    # Calibrate BTCUSDT/ETHUSDT pair
    print(f"\n🔧 Calibrating {pairs_id_1}...")
    calibrated = manager.calibrate_pairs_strategy(
        strategy_id=pairs_id_1,
        historical_data_x=btc_historical,
        historical_data_y=eth_historical
    )

    if calibrated:
        print(f"   ✅ Calibration successful!")
    else:
        print(f"   ⚠️  Calibration failed (pair may not be cointegrated)")

    # ========================================================================
    # STEP 4: Trading Simulation Loop
    # ========================================================================
    print_header("STEP 4: Running Trading Simulation (10 cycles)")

    num_cycles = 10

    for cycle in range(1, num_cycles + 1):
        print(f"\n{'─' * 80}")
        print(f"CYCLE {cycle}/{num_cycles}")
        print(f"{'─' * 80}")

        # Generate current market data
        current_prices = simulator.get_current_prices()
        print(f"\n📊 Current Prices:")
        for symbol, price in current_prices.items():
            print(f"   {symbol}: ${price:,.2f}")

        # Prepare market data for all strategies
        market_data = {
            'pairs_data': {
                pairs_id_1: {
                    'current_price_x': current_prices['BTCUSDT'],
                    'current_price_y': current_prices['ETHUSDT'],
                    'historical_data_x': btc_historical,
                    'historical_data_y': eth_historical
                }
            },
            'funding_data': {
                funding_id_1: simulator.get_funding_data('BTCUSDT'),
                funding_id_2: simulator.get_funding_data('ETHUSDT')
            },
            'triangular_prices': simulator.get_triangular_prices()
        }

        # Generate signals from all strategies
        print(f"\n🎯 Generating signals...")
        signals = manager.generate_all_signals(market_data)

        # Display signals
        total_signals = sum(len(s) for s in signals.values())
        print(f"   Generated {total_signals} signals: "
              f"Pairs={len(signals['pairs'])}, "
              f"Funding={len(signals['funding'])}, "
              f"Triangular={len(signals['triangular'])}")

        # Execute pairs trading signals
        for signal_data in signals['pairs']:
            strategy_id = signal_data['strategy_id']
            signal = signal_data['signal']

            print(f"\n   🔄 Pairs Signal: {strategy_id}")
            print(f"      Action: {signal.action}")
            print(f"      Z-Score: {signal.z_score:.3f}")
            print(f"      Capital: ${signal.capital:,.2f}")

            # Execute trade
            result = executor.execute_pairs_trade(signal, strategy_id)

            # Record execution in manager
            manager.record_trade_execution(
                strategy_type='pairs',
                strategy_id=strategy_id,
                signal=signal,
                execution_result=result
            )

        # Execute funding rate signals
        for signal_data in signals['funding']:
            strategy_id = signal_data['strategy_id']
            signal = signal_data['signal']

            print(f"\n   💰 Funding Signal: {strategy_id}")
            print(f"      Action: {signal.action}")
            print(f"      Annualized Yield: {signal.annualized_yield:.2f}%")
            print(f"      Spot Position: ${signal.spot_position_size:,.2f}")
            print(f"      Futures Position: ${signal.futures_position_size:,.2f}")

            # Execute trade
            result = executor.execute_funding_trade(signal, strategy_id)

            # Record execution in manager
            manager.record_trade_execution(
                strategy_type='funding',
                strategy_id=strategy_id,
                signal=signal,
                execution_result=result
            )

        # Execute triangular arbitrage signals
        for signal_data in signals['triangular']:
            signal = signal_data['signal']

            print(f"\n   🔺 Triangular Signal:")
            print(f"      Path: {' -> '.join(signal.path.symbols)}")
            print(f"      Net Profit: {signal.net_profit_pct:.3f}%")
            print(f"      Execution Amount: ${signal.execution_amount:,.2f}")

            # Execute trade
            result = executor.execute_triangular_trade(signal)

            # Record execution in manager
            manager.record_trade_execution(
                strategy_type='triangular',
                strategy_id='triangular',
                signal=signal,
                execution_result=result
            )

    # ========================================================================
    # STEP 5: Performance Analysis
    # ========================================================================
    print_header("STEP 5: Performance Analysis")

    # Get portfolio performance
    performance = manager.get_portfolio_performance()
    print_performance_summary(performance)

    # Display strategy-specific performance
    print("\n📊 STRATEGY-SPECIFIC PERFORMANCE:\n")

    print("Pairs Trading:")
    for strategy_id, metrics in performance.strategies_performance['pairs'].items():
        print(f"  {strategy_id}:")
        print(f"    Trades:         {metrics['total_trades']}")
        print(f"    Profit:         ${metrics['profit']:,.2f}")
        print(f"    Cointegrated:   {metrics['is_cointegrated']}")
        print(f"    Position:       {metrics['current_position']}")

    print("\nFunding Rate Arbitrage:")
    for strategy_id, metrics in performance.strategies_performance['funding'].items():
        print(f"  {strategy_id}:")
        print(f"    Trades:         {metrics['total_trades']}")
        print(f"    Profit:         ${metrics['profit']:,.2f}")
        print(f"    Funding Payments: {metrics['num_funding_payments']}")
        print(f"    Position:       {metrics['current_position']}")

    if performance.strategies_performance['triangular']:
        print("\nTriangular Arbitrage:")
        metrics = performance.strategies_performance['triangular']
        print(f"  Total Arbitrages: {metrics['total_arbitrages']}")
        print(f"  Profit:           ${metrics['total_profit']:,.2f}")
        print(f"  Avg Latency:      {metrics['average_latency_ms']:.2f}ms")
        print(f"  Active Paths:     {metrics['num_paths']}")

    # ========================================================================
    # STEP 6: Status Summary
    # ========================================================================
    print_header("STEP 6: Final Status Summary")

    status = manager.get_status_summary()

    print("Manager Status:")
    print(f"  Total Capital:      ${status['manager']['total_capital']:,.2f}")
    print(f"  Allocated Capital:  ${status['manager']['allocated_capital']:,.2f}")
    print(f"  Total Profit:       ${status['manager']['total_profit']:,.2f}")
    print(f"  Total Trades:       {status['manager']['total_trades']}")
    print(f"  Win Rate:           {status['manager']['win_rate']:.2f}%")

    print("\nActive Strategies:")
    print(f"  Pairs Trading:      {status['strategies']['pairs']['count']} strategies")
    print(f"  Funding Rate:       {status['strategies']['funding']['count']} strategies")
    print(f"  Triangular:         {'Configured' if status['strategies']['triangular']['configured'] else 'Not configured'}")

    print(f"\nSignals History:      {status['signals_history_count']} total signal events")

    # ========================================================================
    # Summary
    # ========================================================================
    print_header("DEMONSTRATION COMPLETE")

    print("✅ All Phase 2.2 Statistical Arbitrage strategies demonstrated successfully!\n")
    print("Key Takeaways:")
    print("  1. StatisticalArbitrageManager orchestrates all strategies")
    print("  2. Capital allocation: 40% Pairs, 40% Funding, 20% Triangular")
    print("  3. Strategies generate signals independently and concurrently")
    print("  4. Comprehensive performance tracking and reporting")
    print("  5. Production-ready implementation with proper error handling\n")

    print(f"Total Executor Profit: ${executor.get_total_profit():,.2f}")
    print(f"Total Manager Profit:  ${manager.total_profit:,.2f}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Demonstration interrupted by user")
    except Exception as e:
        logger.error(f"Error during demonstration: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        sys.exit(1)
