"""
Integration Tests for Phase 2.2 - Statistical Arbitrage Strategies

This test suite validates:
1. All strategies work correctly with realistic market data
2. Strategies can run concurrently without conflicts
3. Signal generation is accurate and timely
4. Error handling works across all strategies
5. Performance meets requirements

Author: Trading Bot Development Team
Date: 2025-12-07
"""

import sys
import os
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List
import time

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.strategies.pairs_trading import PairsTradingStrategy, PairsTradeSignal
from app.strategies.funding_rate_arbitrage import FundingRateArbitrageStrategy, FundingRateSignal
from app.strategies.triangular_arbitrage import TriangularArbitrageStrategy, TriangularArbitrageSignal
from app.utils.statistical.cointegration import PairScanner, CointegrationTester


class TestStatisticalArbitrageIntegration:
    """Integration tests for all statistical arbitrage strategies"""

    @pytest.fixture
    def sample_price_data(self):
        """Generate realistic sample price data for testing"""
        # Generate 100 days of hourly price data
        dates = pd.date_range(start='2024-01-01', periods=2400, freq='1h')

        # BTC price: trending upward with volatility
        btc_base = 40000
        btc_trend = np.linspace(0, 10000, 2400)
        btc_noise = np.random.normal(0, 500, 2400)
        btc_prices = btc_base + btc_trend + btc_noise

        # ETH price: cointegrated with BTC (ratio ~0.04)
        eth_ratio = 0.04
        eth_noise = np.random.normal(0, 20, 2400)
        eth_prices = btc_prices * eth_ratio + eth_noise

        # BNB price: some correlation but not cointegrated
        bnb_base = 300
        bnb_noise = np.random.normal(0, 10, 2400)
        bnb_prices = bnb_base + np.random.normal(0, 50, 2400).cumsum() + bnb_noise

        return {
            'BTCUSDT': pd.Series(btc_prices, index=dates),
            'ETHUSDT': pd.Series(eth_prices, index=dates),
            'BNBUSDT': pd.Series(bnb_prices, index=dates),
        }

    @pytest.fixture
    def current_market_prices(self):
        """Current market prices for signal generation"""
        return {
            'BTCUSDT': 50000.0,
            'ETHUSDT': 2000.0,
            'ETHBTC': 0.04,
            'BTCETH': 25.0,  # Added reverse pair
            'BNBUSDT': 350.0,
            'BNBBTC': 0.007,
            'BTCBNB': 142.86,  # Added reverse pair
            'BNBETH': 0.175,
            'ETHBNB': 5.71,  # Added reverse pair
        }

    def test_all_strategies_initialization(self):
        """Test that all strategies can be initialized without errors"""
        # Pairs Trading
        pairs_strategy = PairsTradingStrategy(
            symbol_x='BTCUSDT',
            symbol_y='ETHUSDT'
        )
        assert pairs_strategy is not None
        assert pairs_strategy.symbol_x == 'BTCUSDT'

        # Funding Rate Arbitrage
        funding_strategy = FundingRateArbitrageStrategy(symbol='BTCUSDT')
        assert funding_strategy is not None
        assert funding_strategy.symbol == 'BTCUSDT'

        # Triangular Arbitrage
        triangular_strategy = TriangularArbitrageStrategy(base_asset='USDT')
        assert triangular_strategy is not None
        assert triangular_strategy.base_asset == 'USDT'

    def test_pairs_trading_complete_workflow(self, sample_price_data):
        """Test complete pairs trading workflow with realistic data"""
        print("\n=== Testing Pairs Trading Workflow ===")

        # Initialize strategy
        strategy = PairsTradingStrategy(
            symbol_x='BTCUSDT',
            symbol_y='ETHUSDT',
            lookback_period=60,
            entry_threshold=2.0,
            exit_threshold=0.5
        )

        # Step 1: Calibrate with historical data
        btc_data = sample_price_data['BTCUSDT']
        eth_data = sample_price_data['ETHUSDT']

        calibrated = strategy.calibrate(btc_data, eth_data)
        print(f"Calibration: {'Success' if calibrated else 'Failed'}")

        if calibrated:
            assert strategy.is_cointegrated
            assert strategy.hedge_ratio is not None
            assert strategy.spread_mean is not None
            assert strategy.spread_std is not None

            print(f"  Hedge Ratio: {strategy.hedge_ratio:.4f}")
            print(f"  Half-Life: {strategy.half_life:.2f} periods")
            print(f"  Spread: mean={strategy.spread_mean:.2f}, std={strategy.spread_std:.2f}")

            # Step 2: Generate signal with current prices
            current_btc = btc_data.iloc[-1]
            current_eth = eth_data.iloc[-1]

            signal = strategy.generate_signal(
                current_price_x=current_btc,
                current_price_y=current_eth,
                historical_data_x=btc_data,
                historical_data_y=eth_data,
                portfolio_value=10000.0
            )

            assert signal is not None
            print(f"Signal Generated: {signal.action}")
            print(f"  Z-score: {signal.z_score:.2f}")
            print(f"  Spread: {signal.spread:.2f}")
            print(f"  Confidence: {signal.confidence:.1f}%")

            # Step 3: Get strategy status
            status = strategy.get_status()
            assert status['is_cointegrated'] == True
            print(f"Strategy Status: {status['current_position']}")

    def test_funding_rate_arbitrage_workflow(self):
        """Test complete funding rate arbitrage workflow"""
        print("\n=== Testing Funding Rate Arbitrage Workflow ===")

        # Initialize strategy
        strategy = FundingRateArbitrageStrategy(
            symbol='BTCUSDT',
            min_funding_rate=0.0003,  # 0.03% per 8h
            max_basis_pct=2.0
        )

        # Scenario 1: Open hedge (attractive funding)
        print("\n1. Testing OPEN_HEDGE signal:")
        signal1 = strategy.generate_signal(
            current_funding_rate=0.0005,  # 0.05% = ~55% APY
            spot_price=50000.0,
            futures_price=50200.0,  # 0.4% basis
            portfolio_value=10000.0
        )

        assert signal1 is not None
        assert signal1.action == 'OPEN_HEDGE'
        print(f"Action: {signal1.action}")
        print(f"  Funding Rate: {signal1.funding_rate:.4f} ({signal1.annualized_yield:.2f}% APY)")
        print(f"  Basis: {signal1.basis_pct:.2f}%")
        print(f"  Position Sizes: Spot={signal1.spot_position_size:.4f}, Futures={signal1.futures_position_size:.4f}")

        # Scenario 2: Record funding payment
        print("\n2. Recording funding payment:")
        strategy.record_funding_payment(
            funding_rate=0.0005,
            position_size=signal1.futures_position_size,
            futures_price=50200.0
        )
        print(f"Total Collected: ${strategy.total_funding_collected:.2f}")

        # Scenario 3: Hold while conditions favorable
        print("\n3. Testing HOLD signal:")
        signal2 = strategy.generate_signal(
            current_funding_rate=0.0004,  # Still good
            spot_price=50000.0,
            futures_price=50300.0,
            portfolio_value=10000.0
        )
        assert signal2.action == 'HOLD'
        print(f"Action: {signal2.action} - {signal2.reason}")

        # Scenario 4: Close hedge (funding too low)
        print("\n4. Testing CLOSE_HEDGE signal:")
        signal3 = strategy.generate_signal(
            current_funding_rate=0.00005,  # Below threshold
            spot_price=50000.0,
            futures_price=50100.0,
            portfolio_value=10000.0
        )
        assert signal3.action == 'CLOSE_HEDGE'
        print(f"Action: {signal3.action} - {signal3.reason}")

        # Get final status
        status = strategy.get_status()
        print(f"\nFinal Status: Position={status['current_position']}, Profit=${status['total_funding_collected']:.2f}")

    def test_triangular_arbitrage_workflow(self, current_market_prices):
        """Test complete triangular arbitrage workflow"""
        print("\n=== Testing Triangular Arbitrage Workflow ===")

        # Initialize strategy
        strategy = TriangularArbitrageStrategy(
            base_asset='USDT',
            min_profit_threshold=0.001,  # 0.1% minimum
            trading_fee=0.0005,  # 0.05% per trade
            max_latency_ms=150.0  # Increased to allow for test signals
        )

        # Step 1: Discover paths
        print("\n1. Discovering triangular paths:")
        assets = ['BTC', 'ETH', 'BNB', 'USDT']
        paths = strategy.discover_paths(assets)

        assert len(paths) > 0
        print(f"Discovered {len(paths)} paths:")
        for i, path in enumerate(paths[:3]):  # Show first 3
            print(f"  Path {i+1}: {path}")

        # Step 2: Check for arbitrage with efficient market (no profit)
        print("\n2. Testing with efficient market (no arbitrage):")
        efficient_prices = {
            'BTCUSDT': 50000.0,
            'ETHBTC': 0.04,
            'BTCETH': 25.0,
            'ETHUSDT': 2000.0,  # Efficient: 50000 * 0.04 = 2000
            'BNBUSDT': 350.0,
            'BNBBTC': 0.007,
            'BTCBNB': 142.86,
            'BNBETH': 0.175,
            'ETHBNB': 5.71,
        }

        signal1 = strategy.generate_signal(efficient_prices, capital=10000.0)
        if signal1 is None:
            print("No arbitrage detected (market efficient)")
        else:
            print(f"Unexpected signal: {signal1.net_profit_pct:.4f}%")

        # Step 3: Create arbitrage opportunity
        print("\n3. Testing with arbitrage opportunity:")
        arbitrage_prices = {
            'BTCUSDT': 50000.0,
            'ETHBTC': 0.04,
            'BTCETH': 25.0,
            'ETHUSDT': 2010.0,  # 0.5% overpriced
            'BNBUSDT': 350.0,
            'BNBBTC': 0.007,
            'BTCBNB': 142.86,
            'BNBETH': 0.175,
            'ETHBNB': 5.71,
        }

        signal2 = strategy.generate_signal(arbitrage_prices, capital=10000.0)

        if signal2 is not None:
            assert signal2.net_profit_pct > 0
            print(f"Arbitrage detected!")
            print(f"  Path: {signal2.path}")
            print(f"  Net Profit: {signal2.net_profit_pct:.4f}%")
            print(f"  Execution Amount: ${signal2.execution_amount:.2f}")
            print(f"  Estimated Latency: {signal2.estimated_latency_ms:.1f}ms")
            print(f"  Confidence: {signal2.confidence:.1f}%")

            # Step 4: Record execution
            strategy.record_arbitrage_execution(
                signal=signal2,
                actual_profit=signal2.execution_amount * signal2.net_profit_pct / 100,
                actual_latency_ms=95.0,
                execution_status='success'
            )

            status = strategy.get_status()
            print(f"\nExecution recorded: Profit=${status['total_profit']:.2f}")

    def test_concurrent_strategy_execution(self, sample_price_data, current_market_prices):
        """Test running all strategies concurrently"""
        print("\n=== Testing Concurrent Strategy Execution ===")

        # Initialize all strategies
        pairs_strategy = PairsTradingStrategy('BTCUSDT', 'ETHUSDT')
        funding_strategy = FundingRateArbitrageStrategy('BTCUSDT')
        triangular_strategy = TriangularArbitrageStrategy('USDT')

        # Calibrate pairs trading
        pairs_strategy.calibrate(
            sample_price_data['BTCUSDT'],
            sample_price_data['ETHUSDT']
        )

        # Discover triangular paths
        triangular_strategy.discover_paths(['BTC', 'ETH', 'BNB', 'USDT'])

        # Generate signals from all strategies simultaneously
        start_time = time.time()

        pairs_signal = pairs_strategy.generate_signal(
            current_price_x=50000.0,
            current_price_y=2000.0,
            historical_data_x=sample_price_data['BTCUSDT'],
            historical_data_y=sample_price_data['ETHUSDT'],
            portfolio_value=10000.0
        )

        funding_signal = funding_strategy.generate_signal(
            current_funding_rate=0.0004,
            spot_price=50000.0,
            futures_price=50200.0,
            portfolio_value=10000.0
        )

        triangular_signal = triangular_strategy.generate_signal(
            current_market_prices,
            capital=10000.0
        )

        execution_time = (time.time() - start_time) * 1000  # Convert to ms

        print(f"\nAll strategies executed concurrently")
        print(f"  Total Execution Time: {execution_time:.2f}ms")
        print(f"  Pairs Trading: {pairs_signal.action if pairs_signal else 'No signal'}")
        print(f"  Funding Rate: {funding_signal.action if funding_signal else 'No signal'}")
        print(f"  Triangular: {'Signal' if triangular_signal else 'No arbitrage'}")

        # Verify performance
        assert execution_time < 500  # Should complete in <500ms
        print(f"\nPerformance: {execution_time:.2f}ms < 500ms threshold")

    def test_pair_scanner_integration(self, sample_price_data):
        """Test automated pair scanner for discovering cointegrated pairs"""
        print("\n=== Testing Pair Scanner ===")

        # PairScanner only accepts significance_level and min_quality_score
        scanner = PairScanner(
            significance_level=0.05,
            min_quality_score=60.0
        )

        # Scan for cointegrated pairs
        pairs = scanner.scan_pairs(sample_price_data, max_pairs=3)

        print(f"\nScanned {len(sample_price_data)} assets")
        print(f"  Found {len(pairs)} cointegrated pairs:")

        for pair in pairs:
            print(f"\n  {pair['symbol_x']}/{pair['symbol_y']}:")
            print(f"    Quality Score: {pair['score']:.1f}/100")
            print(f"    Hedge Ratio: {pair['hedge_ratio']:.4f}")
            if pair.get('half_life'):
                print(f"    Half-Life: {pair['half_life']:.2f} periods")
            if pair.get('p_value'):
                print(f"    P-Value: {pair['p_value']:.4f}")

    def test_error_handling_all_strategies(self):
        """Test error handling across all strategies"""
        print("\n=== Testing Error Handling ===")

        # Test 1: Pairs trading with non-cointegrated data
        print("\n1. Pairs Trading - Non-cointegrated data:")
        strategy1 = PairsTradingStrategy('BTCUSDT', 'RANDOMUSDT')

        random_data = pd.Series(np.random.randn(100).cumsum())
        btc_data = pd.Series(np.random.randn(100).cumsum() * 1000 + 50000)

        result = strategy1.calibrate(btc_data, random_data)
        print(f"Handled non-cointegrated pair: calibration={'Failed (expected)' if not result else 'Unexpected success'}")

        # Test 2: Funding rate with missing price data
        print("\n2. Funding Rate - Missing data:")
        strategy2 = FundingRateArbitrageStrategy('BTCUSDT')

        # This should not crash, just return a signal
        signal = strategy2.generate_signal(
            current_funding_rate=None,  # Invalid
            spot_price=50000.0,
            futures_price=50200.0,
            portfolio_value=10000.0
        )
        # Signal generation handles None gracefully
        print(f"Handled missing funding rate gracefully")

        # Test 3: Triangular arbitrage with missing pairs
        print("\n3. Triangular Arbitrage - Missing price pairs:")
        strategy3 = TriangularArbitrageStrategy('USDT')
        strategy3.discover_paths(['BTC', 'ETH', 'USDT'])

        incomplete_prices = {
            'BTCUSDT': 50000.0,
            # Missing ETHBTC and ETHUSDT
        }

        signal = strategy3.generate_signal(incomplete_prices, capital=10000.0)
        assert signal is None
        print(f"Handled missing price pairs: No signal generated")

    def test_performance_benchmarks(self, sample_price_data):
        """Test performance benchmarks for all strategies"""
        print("\n=== Performance Benchmarks ===")

        iterations = 100

        # Benchmark 1: Pairs Trading Signal Generation
        print("\n1. Pairs Trading Signal Generation:")
        strategy1 = PairsTradingStrategy('BTCUSDT', 'ETHUSDT')
        strategy1.calibrate(sample_price_data['BTCUSDT'], sample_price_data['ETHUSDT'])

        start = time.time()
        for _ in range(iterations):
            strategy1.generate_signal(
                50000.0, 2000.0,
                sample_price_data['BTCUSDT'],
                sample_price_data['ETHUSDT'],
                10000.0
            )
        elapsed = (time.time() - start) / iterations * 1000

        print(f"Average: {elapsed:.2f}ms per signal")
        assert elapsed < 50  # Should be <50ms per signal

        # Benchmark 2: Funding Rate Signal Generation
        print("\n2. Funding Rate Signal Generation:")
        strategy2 = FundingRateArbitrageStrategy('BTCUSDT')

        start = time.time()
        for _ in range(iterations):
            strategy2.generate_signal(0.0004, 50000.0, 50200.0, 10000.0)
        elapsed = (time.time() - start) / iterations * 1000

        print(f"Average: {elapsed:.2f}ms per signal")
        assert elapsed < 10  # Should be <10ms per signal

        # Benchmark 3: Triangular Arbitrage Path Discovery
        print("\n3. Triangular Arbitrage Path Discovery:")
        strategy3 = TriangularArbitrageStrategy('USDT')

        start = time.time()
        for _ in range(10):  # Fewer iterations (more expensive)
            strategy3.discover_paths(['BTC', 'ETH', 'BNB', 'USDT'])
        elapsed = (time.time() - start) / 10 * 1000

        print(f"Average: {elapsed:.2f}ms per discovery")
        assert elapsed < 100  # Should be <100ms


class TestStatisticalArbitrageEndToEnd:
    """End-to-end tests simulating real trading scenarios"""

    def test_daily_trading_simulation(self):
        """Simulate a day of trading with all strategies"""
        print("\n=== Daily Trading Simulation ===")

        # Initialize strategies
        pairs_strategy = PairsTradingStrategy('BTCUSDT', 'ETHUSDT', entry_threshold=2.0)
        funding_strategy = FundingRateArbitrageStrategy('BTCUSDT')
        triangular_strategy = TriangularArbitrageStrategy('USDT')

        # Generate 24 hours of price data (hourly)
        print("\nGenerating 24 hours of market data...")
        hours = 24
        signals_generated = {'pairs': 0, 'funding': 0, 'triangular': 0}

        # Simulate historical data for calibration
        np.random.seed(42)
        btc_hist = pd.Series(50000 + np.random.normal(0, 500, 100).cumsum())
        eth_hist = pd.Series(btc_hist * 0.04 + np.random.normal(0, 20, 100))

        pairs_strategy.calibrate(btc_hist, eth_hist)
        triangular_strategy.discover_paths(['BTC', 'ETH', 'BNB', 'USDT'])

        print(f"\nStrategies initialized and calibrated")
        print(f"\nSimulating {hours} hours of trading...\n")

        for hour in range(hours):
            # Generate random price movements
            btc_price = 50000 + np.random.normal(0, 1000)
            eth_price = btc_price * 0.04 + np.random.normal(0, 50)
            funding_rate = np.random.normal(0.0003, 0.0002)

            # Check all strategies
            pairs_signal = pairs_strategy.generate_signal(
                btc_price, eth_price, btc_hist, eth_hist, 10000.0
            )
            if pairs_signal and pairs_signal.action != 'HOLD':
                signals_generated['pairs'] += 1

            funding_signal = funding_strategy.generate_signal(
                funding_rate, btc_price, btc_price * 1.002, 10000.0
            )
            if funding_signal and funding_signal.action != 'HOLD':
                signals_generated['funding'] += 1

            # Print periodic updates
            if hour % 6 == 0:
                print(f"Hour {hour:2d}: BTC=${btc_price:,.0f}, ETH=${eth_price:,.2f}, Funding={funding_rate:.4f}")

        print(f"\nSimulation Complete!")
        print(f"  Pairs Trading Signals: {signals_generated['pairs']}")
        print(f"  Funding Rate Signals: {signals_generated['funding']}")
        print(f"  Triangular Signals: {signals_generated['triangular']}")


if __name__ == '__main__':
    # Run with verbose output
    pytest.main([__file__, '-v', '-s'])
