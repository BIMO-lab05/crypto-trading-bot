"""
Unit Tests for Triangular Arbitrage Strategy

Tests cover:
- Path discovery
- Arbitrage profit calculation
- Signal generation
- Latency estimation
- Performance tracking
- Edge cases and error handling

Author: Trading Bot Development Team
Date: 2025-12-07
"""

import sys
import os
import pytest
from datetime import datetime
from typing import Dict, List

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from app.strategies.triangular_arbitrage import (
    TriangularArbitrageStrategy,
    TriangularPath,
    TriangularArbitrageSignal,
)


class TestTriangularPath:
    """Test TriangularPath dataclass"""

    def test_path_initialization(self):
        """Test TriangularPath creation"""
        path = TriangularPath(
            symbols=['USDT', 'BTC', 'ETH'],
            pairs=['BTCUSDT', 'ETHBTC', 'ETHUSDT'],
            directions=['buy', 'buy', 'sell'],
            start_asset='USDT'
        )

        assert path.symbols == ['USDT', 'BTC', 'ETH']
        assert path.pairs == ['BTCUSDT', 'ETHBTC', 'ETHUSDT']
        assert path.directions == ['buy', 'buy', 'sell']
        assert path.start_asset == 'USDT'

    def test_path_string_representation(self):
        """Test TriangularPath __str__ method"""
        path = TriangularPath(
            symbols=['USDT', 'BTC', 'ETH'],
            pairs=['BTCUSDT', 'ETHBTC', 'ETHUSDT'],
            directions=['buy', 'buy', 'sell'],
            start_asset='USDT'
        )

        path_str = str(path)
        assert 'USDT' in path_str
        assert 'BTC' in path_str
        assert 'ETH' in path_str
        assert 'start: USDT' in path_str


class TestTriangularArbitrageStrategy:
    """Test TriangularArbitrageStrategy class"""

    def test_initialization_with_defaults(self):
        """Test strategy initialization with default parameters"""
        strategy = TriangularArbitrageStrategy()

        assert strategy.base_asset == 'USDT'
        assert strategy.min_profit_threshold == 0.001  # 0.1%
        assert strategy.trading_fee == 0.0005  # 0.05%
        assert strategy.max_latency_ms == 100.0
        assert strategy.execution_amount_pct == 0.1
        assert strategy.total_arbitrages_executed == 0
        assert strategy.total_profit == 0.0

    def test_initialization_with_custom_params(self):
        """Test strategy initialization with custom parameters"""
        strategy = TriangularArbitrageStrategy(
            base_asset='BTC',
            min_profit_threshold=0.002,
            trading_fee=0.001,
            max_latency_ms=50.0,
            execution_amount_pct=0.2
        )

        assert strategy.base_asset == 'BTC'
        assert strategy.min_profit_threshold == 0.002
        assert strategy.trading_fee == 0.001
        assert strategy.max_latency_ms == 50.0
        assert strategy.execution_amount_pct == 0.2

    def test_discover_paths_basic(self):
        """Test basic path discovery with 3 assets"""
        strategy = TriangularArbitrageStrategy(base_asset='USDT')
        assets = ['BTC', 'ETH', 'USDT']

        paths = strategy.discover_paths(assets)

        # With 3 assets including base, expect 2 paths
        # USDT -> BTC -> ETH -> USDT
        # USDT -> ETH -> BTC -> USDT
        assert len(paths) == 2
        assert all(isinstance(p, TriangularPath) for p in paths)
        assert all(p.start_asset == 'USDT' for p in paths)
        assert all(len(p.symbols) == 3 for p in paths)

    def test_discover_paths_four_assets(self):
        """Test path discovery with 4 assets"""
        strategy = TriangularArbitrageStrategy(base_asset='USDT')
        assets = ['BTC', 'ETH', 'BNB', 'USDT']

        paths = strategy.discover_paths(assets)

        # With 4 assets including base, expect 6 paths (3 choose 2 x 2)
        assert len(paths) == 6
        assert all(p.start_asset == 'USDT' for p in paths)

    def test_discover_paths_adds_base_asset(self):
        """Test that base asset is added if not in list"""
        strategy = TriangularArbitrageStrategy(base_asset='USDT')
        assets = ['BTC', 'ETH']  # USDT not included

        paths = strategy.discover_paths(assets)

        assert len(paths) == 2
        assert all(p.start_asset == 'USDT' for p in paths)

    def test_calculate_arbitrage_profit_no_opportunity(self):
        """Test arbitrage calculation with efficient market (no profit)"""
        strategy = TriangularArbitrageStrategy(
            base_asset='USDT',
            trading_fee=0.0  # No fees for simplicity
        )

        path = TriangularPath(
            symbols=['USDT', 'BTC', 'ETH'],
            pairs=['BTCUSDT', 'ETHBTC', 'ETHUSDT'],
            directions=['buy', 'buy', 'sell'],
            start_asset='USDT'
        )

        # Efficient market: no arbitrage
        # BTC/USDT = 50,000, ETH/BTC = 0.04, ETH/USDT = 2,000
        prices = {
            'BTCUSDT': 50000.0,
            'ETHBTC': 0.04,
            'ETHUSDT': 2000.0,
        }

        gross_profit, net_profit, rates = strategy._calculate_arbitrage_profit(
            path, prices, capital=10000.0
        )

        # Should be close to 0% (no arbitrage)
        assert abs(net_profit) < 0.01  # Within 0.01%

    def test_calculate_arbitrage_profit_with_opportunity(self):
        """Test arbitrage calculation with profitable opportunity"""
        strategy = TriangularArbitrageStrategy(
            base_asset='USDT',
            trading_fee=0.0  # No fees for simplicity
        )

        path = TriangularPath(
            symbols=['USDT', 'BTC', 'ETH'],
            pairs=['BTCUSDT', 'ETHBTC', 'ETHUSDT'],
            directions=['buy', 'buy', 'sell'],
            start_asset='USDT'
        )

        # Inefficient market: arbitrage opportunity
        prices = {
            'BTCUSDT': 50000.0,
            'ETHBTC': 0.04,
            'ETHUSDT': 2010.0,
        }

        gross_profit, net_profit, rates = strategy._calculate_arbitrage_profit(
            path, prices, capital=10000.0
        )

        # Should have ~0.5% profit
        assert net_profit > 0.4  # At least 0.4%
        assert net_profit < 0.6  # Less than 0.6%
        assert rates['BTCUSDT'] == 50000.0
        assert rates['ETHBTC'] == 0.04
        assert rates['ETHUSDT'] == 2010.0

    def test_calculate_arbitrage_profit_with_fees(self):
        """Test that trading fees reduce profit"""
        strategy = TriangularArbitrageStrategy(
            base_asset='USDT',
            trading_fee=0.001  # 0.1% per trade
        )

        path = TriangularPath(
            symbols=['USDT', 'BTC', 'ETH'],
            pairs=['BTCUSDT', 'ETHBTC', 'ETHUSDT'],
            directions=['buy', 'buy', 'sell'],
            start_asset='USDT'
        )

        prices = {
            'BTCUSDT': 50000.0,
            'ETHBTC': 0.04,
            'ETHUSDT': 2010.0,
        }

        gross_profit, net_profit, rates = strategy._calculate_arbitrage_profit(
            path, prices, capital=10000.0
        )

        # Fees reduce profit
        assert net_profit > 0.1  # At least 0.1%
        assert net_profit < 0.3  # Less than 0.3%

    def test_calculate_arbitrage_profit_missing_price(self):
        """Test handling of missing price data"""
        strategy = TriangularArbitrageStrategy()

        path = TriangularPath(
            symbols=['USDT', 'BTC', 'ETH'],
            pairs=['BTCUSDT', 'ETHBTC', 'ETHUSDT'],
            directions=['buy', 'buy', 'sell'],
            start_asset='USDT'
        )

        # Missing ETHUSDT price
        prices = {
            'BTCUSDT': 50000.0,
            'ETHBTC': 0.04,
        }

        gross_profit, net_profit, rates = strategy._calculate_arbitrage_profit(
            path, prices, capital=10000.0
        )

        assert gross_profit == 0.0
        assert net_profit == 0.0
        assert rates == {}

    def test_estimate_execution_latency(self):
        """Test execution latency estimation"""
        strategy = TriangularArbitrageStrategy()

        path = TriangularPath(
            symbols=['USDT', 'BTC', 'ETH'],
            pairs=['BTCUSDT', 'ETHBTC', 'ETHUSDT'],
            directions=['buy', 'buy', 'sell'],
            start_asset='USDT'
        )

        prices = {
            'BTCUSDT': 50000.0,
            'ETHBTC': 0.04,
            'ETHUSDT': 2000.0,
        }

        latency_ms = strategy._estimate_execution_latency(path, prices)

        # Should estimate ~30ms per order x 3 + 20ms network = ~110ms
        assert latency_ms > 80  # At least 80ms
        assert latency_ms < 150  # Less than 150ms

    def test_generate_signal_no_paths(self):
        """Test signal generation without discovered paths"""
        strategy = TriangularArbitrageStrategy()

        prices = {
            'BTCUSDT': 50000.0,
            'ETHBTC': 0.04,
            'ETHUSDT': 2000.0,
        }

        signal = strategy.generate_signal(prices, capital=10000.0)

        assert signal is None

    def test_generate_signal_no_opportunity(self):
        """Test signal generation with no arbitrage opportunity"""
        strategy = TriangularArbitrageStrategy(
            base_asset='USDT',
            min_profit_threshold=0.001,  # 0.1% minimum
            max_latency_ms=150.0  # Allow for latency
        )

        # Discover paths
        strategy.discover_paths(['BTC', 'ETH', 'USDT'])

        # Efficient market prices (no arbitrage)
        prices = {
            'BTCUSDT': 50000.0,
            'ETHBTC': 0.04,
            'BTCETH': 25.0,  # 1/0.04 = 25
            'ETHUSDT': 2000.0,
        }

        signal = strategy.generate_signal(prices, capital=10000.0)

        # Should not generate signal (profit below threshold)
        assert signal is None

    def test_generate_signal_with_opportunity(self):
        """Test signal generation with profitable opportunity

        Note: The path discovery generates pair names based on direction.
        We need to provide prices for all generated pairs.
        """
        strategy = TriangularArbitrageStrategy(
            base_asset='USDT',
            min_profit_threshold=0.001,  # 0.1% minimum
            trading_fee=0.0,  # No fees for simplicity
            max_latency_ms=150.0  # Allow for estimated ~110ms latency
        )

        # Discover paths
        paths = strategy.discover_paths(['BTC', 'ETH', 'USDT'])

        # Inefficient market with arbitrage opportunity
        prices = {
            'BTCUSDT': 50000.0,
            'ETHBTC': 0.04,
            'BTCETH': 25.0,
            'ETHUSDT': 2010.0,  # 0.5% overpriced - creates arbitrage
        }

        signal = strategy.generate_signal(prices, capital=10000.0)

        assert signal is not None
        assert isinstance(signal, TriangularArbitrageSignal)
        assert signal.net_profit_pct > 0.3  # At least 0.3% profit after path calculation
        assert signal.confidence > 50.0
        assert signal.execution_amount == 10000.0 * 0.1  # 10% of capital
        assert signal.estimated_latency_ms < 150

    def test_generate_signal_rejects_high_latency(self):
        """Test that high latency opportunities are rejected"""
        strategy = TriangularArbitrageStrategy(
            base_asset='USDT',
            min_profit_threshold=0.001,
            max_latency_ms=50.0,  # Very strict latency requirement
            trading_fee=0.0
        )

        strategy.discover_paths(['BTC', 'ETH', 'USDT'])

        # Good arbitrage opportunity but latency will be ~110ms
        prices = {
            'BTCUSDT': 50000.0,
            'ETHBTC': 0.04,
            'BTCETH': 25.0,
            'ETHUSDT': 2010.0,
        }

        signal = strategy.generate_signal(prices, capital=10000.0)

        # Should reject due to latency exceeding 50ms
        assert signal is None

    def test_generate_signal_selects_best_opportunity(self):
        """Test that strategy selects best among multiple opportunities"""
        strategy = TriangularArbitrageStrategy(
            base_asset='USDT',
            min_profit_threshold=0.001,
            trading_fee=0.0,
            max_latency_ms=150.0  # Allow for estimated ~110ms latency
        )

        # Discover paths with 3 assets (2 paths)
        strategy.discover_paths(['BTC', 'ETH', 'USDT'])

        # Provide prices for both possible paths
        prices = {
            'BTCUSDT': 50000.0,
            'ETHBTC': 0.04,
            'BTCETH': 25.0,  # For reverse path
            'ETHUSDT': 2010.0,  # ~0.5% arbitrage via first path
        }

        signal = strategy.generate_signal(prices, capital=10000.0)

        assert signal is not None
        # Should select the profitable path
        assert signal.net_profit_pct > 0.3

    def test_record_arbitrage_execution_success(self):
        """Test recording successful arbitrage execution"""
        strategy = TriangularArbitrageStrategy()

        path = TriangularPath(
            symbols=['USDT', 'BTC', 'ETH'],
            pairs=['BTCUSDT', 'ETHBTC', 'ETHUSDT'],
            directions=['buy', 'buy', 'sell'],
            start_asset='USDT'
        )

        signal = TriangularArbitrageSignal(
            timestamp=datetime.now(),
            path=path,
            profit_pct=0.5,
            net_profit_pct=0.48,
            exchange_rates={'BTCUSDT': 50000, 'ETHBTC': 0.04, 'ETHUSDT': 2010},
            execution_amount=1000.0,
            estimated_latency_ms=100.0,
            confidence=80.0,
            reason='Arbitrage opportunity'
        )

        strategy.record_arbitrage_execution(
            signal=signal,
            actual_profit=48.0,
            actual_latency_ms=105.0,
            execution_status='success'
        )

        assert strategy.total_arbitrages_executed == 1
        assert strategy.total_profit == 48.0
        assert strategy.average_latency_ms == 105.0
        assert len(strategy.arbitrage_history) == 1

    def test_record_arbitrage_execution_failure(self):
        """Test recording failed arbitrage execution"""
        strategy = TriangularArbitrageStrategy()

        path = TriangularPath(
            symbols=['USDT', 'BTC', 'ETH'],
            pairs=['BTCUSDT', 'ETHBTC', 'ETHUSDT'],
            directions=['buy', 'buy', 'sell'],
            start_asset='USDT'
        )

        signal = TriangularArbitrageSignal(
            timestamp=datetime.now(),
            path=path,
            profit_pct=0.5,
            net_profit_pct=0.48,
            exchange_rates={'BTCUSDT': 50000, 'ETHBTC': 0.04, 'ETHUSDT': 2010},
            execution_amount=1000.0,
            estimated_latency_ms=100.0,
            confidence=80.0,
            reason='Arbitrage opportunity'
        )

        strategy.record_arbitrage_execution(
            signal=signal,
            actual_profit=-10.0,  # Loss
            actual_latency_ms=200.0,
            execution_status='failed'
        )

        assert strategy.total_arbitrages_executed == 0  # Not incremented on failure
        assert strategy.total_profit == 0.0  # Not added on failure
        assert len(strategy.arbitrage_history) == 1  # Still recorded
        assert strategy.arbitrage_history[0]['status'] == 'failed'

    def test_get_status(self):
        """Test status reporting"""
        strategy = TriangularArbitrageStrategy(
            base_asset='USDT',
            min_profit_threshold=0.002
        )

        strategy.discover_paths(['BTC', 'ETH', 'USDT'])

        status = strategy.get_status()

        assert status['base_asset'] == 'USDT'
        assert status['num_paths_discovered'] == 2
        assert status['total_arbitrages_executed'] == 0
        assert status['total_profit'] == 0.0
        assert status['parameters']['min_profit_threshold'] == 0.002
        assert len(status['paths']) == 2

    def test_get_arbitrage_history(self):
        """Test retrieving arbitrage history"""
        strategy = TriangularArbitrageStrategy()

        # Add some history
        strategy.arbitrage_history = [
            {'timestamp': datetime.now(), 'profit': 10.0},
            {'timestamp': datetime.now(), 'profit': 20.0},
            {'timestamp': datetime.now(), 'profit': 30.0},
        ]

        history = strategy.get_arbitrage_history(limit=2)

        assert len(history) == 2
        assert history[0]['profit'] == 20.0  # Second most recent
        assert history[1]['profit'] == 30.0  # Most recent

    def test_calculate_potential_daily_profit(self):
        """Test daily profit projection calculation"""
        strategy = TriangularArbitrageStrategy(
            execution_amount_pct=0.1  # 10% per trade
        )

        projections = strategy.calculate_potential_daily_profit(
            average_opportunities_per_day=10,
            average_profit_pct=0.2,  # 0.2% per opportunity
            capital=10000.0
        )

        assert projections['execution_amount'] == 1000.0  # 10% of 10,000
        assert projections['profit_per_opportunity'] == 2.0  # 1000 x 0.002
        assert projections['opportunities_per_day'] == 10
        assert projections['daily_profit'] == 20.0  # 2.0 x 10
        assert projections['daily_return_pct'] == 0.2  # 20 / 10,000 x 100
        assert projections['annual_return_pct'] == pytest.approx(73.0, rel=1)  # 0.2 x 365


class TestTriangularArbitrageIntegration:
    """Integration tests for complete workflow"""

    def test_complete_arbitrage_workflow(self):
        """Test complete workflow from path discovery to signal generation"""
        strategy = TriangularArbitrageStrategy(
            base_asset='USDT',
            min_profit_threshold=0.001,
            trading_fee=0.0005,
            max_latency_ms=150.0
        )

        # Step 1: Discover paths
        paths = strategy.discover_paths(['BTC', 'ETH', 'BNB', 'USDT'])
        assert len(paths) == 6

        # Step 2: Generate signal with profitable opportunity
        prices = {
            'BTCUSDT': 50000.0,
            'ETHUSDT': 2010.0,  # Creates arbitrage opportunity
            'BNBUSDT': 300.0,
            'ETHBTC': 0.04,
            'BTCETH': 25.0,
            'BNBBTC': 0.006,
            'BTCBNB': 166.67,
            'BNBETH': 0.15,
            'ETHBNB': 6.67,
        }

        signal = strategy.generate_signal(prices, capital=10000.0)
        assert signal is not None

        # Step 3: Record execution
        strategy.record_arbitrage_execution(
            signal=signal,
            actual_profit=40.0,
            actual_latency_ms=120.0,
            execution_status='success'
        )

        # Step 4: Verify state
        status = strategy.get_status()
        assert status['total_arbitrages_executed'] == 1
        assert status['total_profit'] == 40.0
        assert status['average_latency_ms'] == 120.0

    def test_multiple_opportunities_selection(self):
        """Test that strategy correctly selects among multiple opportunities"""
        strategy = TriangularArbitrageStrategy(
            base_asset='USDT',
            min_profit_threshold=0.0005,
            trading_fee=0.0,
            max_latency_ms=150.0  # Allow for estimated ~110ms latency
        )

        # Discover multiple paths
        strategy.discover_paths(['BTC', 'ETH', 'BNB', 'USDT'])

        # Create prices with different arbitrage opportunities
        prices = {
            'BTCUSDT': 50000.0,
            'ETHUSDT': 2008.0,  # Small 0.4% arbitrage
            'BNBUSDT': 300.0,
            'ETHBTC': 0.04,
            'BTCETH': 25.0,
            'BNBBTC': 0.006,
            'BTCBNB': 166.67,
            'BNBETH': 0.149,  # Slightly different
            'ETHBNB': 6.71,
        }

        signal = strategy.generate_signal(prices, capital=10000.0)

        # Should select best opportunity
        assert signal is not None
        assert signal.net_profit_pct > 0.2  # Better than minimum


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
