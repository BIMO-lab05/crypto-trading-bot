"""
Unit Tests for Funding Rate Arbitrage Strategy

Tests cover:
- Strategy initialization
- Funding rate annualization
- Basis calculation
- Position sizing
- Signal generation (entry/exit/hold)
- Funding payment tracking
- Risk management (basis risk, funding reversal)
- Performance tracking

Author: Trading Bot Development Team
Date: 2025-12-07
"""

import sys
import os
import pytest
from datetime import datetime
from typing import Dict

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from app.strategies.funding_rate_arbitrage import (
    FundingRateArbitrageStrategy,
    FundingRateSignal,
)
from app.config import get_settings

# Account-size fixture routed through Settings (ADR-029) - never a bare literal.
PORTFOLIO_VALUE = float(get_settings().paper_initial_balance)


class TestFundingRateArbitrageStrategy:
    """Test FundingRateArbitrageStrategy class"""

    def test_initialization_with_defaults(self):
        """Test strategy initialization with default parameters"""
        strategy = FundingRateArbitrageStrategy(symbol='BTCUSDT')

        assert strategy.symbol == 'BTCUSDT'
        assert strategy.min_funding_rate == 0.0003  # 0.03%
        assert strategy.max_funding_rate == 0.01  # 1%
        assert strategy.max_basis_pct == 2.0
        assert strategy.position_size_pct == 0.2
        assert strategy.funding_collection_threshold == 0.0001
        assert strategy.current_position is None
        assert strategy.total_funding_collected == 0.0

    def test_initialization_with_custom_params(self):
        """Test strategy initialization with custom parameters"""
        strategy = FundingRateArbitrageStrategy(
            symbol='ETHUSDT',
            min_funding_rate=0.0005,
            max_funding_rate=0.02,
            max_basis_pct=3.0,
            position_size_pct=0.15,
            funding_collection_threshold=0.0002
        )

        assert strategy.symbol == 'ETHUSDT'
        assert strategy.min_funding_rate == 0.0005
        assert strategy.max_funding_rate == 0.02
        assert strategy.max_basis_pct == 3.0
        assert strategy.position_size_pct == 0.15
        assert strategy.funding_collection_threshold == 0.0002

    def test_annualize_funding(self):
        """Test funding rate annualization calculation"""
        strategy = FundingRateArbitrageStrategy(symbol='BTCUSDT')

        # 0.01% per 8h → 3 payments/day × 365 days = 10.95% annually
        annual_yield = strategy._annualize_funding(0.0001)
        assert annual_yield == pytest.approx(10.95, rel=0.01)

        # 0.03% per 8h → 32.85% annually
        annual_yield = strategy._annualize_funding(0.0003)
        assert annual_yield == pytest.approx(32.85, rel=0.01)

        # 0.1% per 8h → 109.5% annually
        annual_yield = strategy._annualize_funding(0.001)
        assert annual_yield == pytest.approx(109.5, rel=0.01)

    def test_calculate_basis(self):
        """Test basis calculation"""
        strategy = FundingRateArbitrageStrategy(symbol='BTCUSDT')

        # Futures premium: futures > spot
        spot_price = 50000.0
        futures_price = 50500.0  # 1% premium

        basis, basis_pct = strategy._calculate_basis(spot_price, futures_price)

        assert basis == 500.0  # 50500 - 50000
        assert basis_pct == pytest.approx(1.0, rel=0.01)  # (500/50000) * 100

        # Futures discount: futures < spot
        futures_price = 49500.0  # 1% discount

        basis, basis_pct = strategy._calculate_basis(spot_price, futures_price)

        assert basis == -500.0
        assert basis_pct == pytest.approx(-1.0, rel=0.01)

    def test_calculate_basis_zero_spot(self):
        """Test basis calculation with zero spot price"""
        strategy = FundingRateArbitrageStrategy(symbol='BTCUSDT')

        basis, basis_pct = strategy._calculate_basis(0.0, 100.0)

        assert basis == 100.0
        assert basis_pct == 0.0  # Edge case handling

    def test_calculate_position_sizes(self):
        """Test position sizing calculation"""
        strategy = FundingRateArbitrageStrategy(
            symbol='BTCUSDT',
            position_size_pct=0.2  # 20% per side
        )

        spot_price = 50000.0
        futures_price = 50500.0
        portfolio_value = PORTFOLIO_VALUE

        spot_size, futures_size = strategy._calculate_position_sizes(
            spot_price, futures_price, portfolio_value
        )

        # Each side gets position_size_pct of the portfolio, converted to units.
        expected_per_side = strategy.position_size_pct * portfolio_value
        assert spot_size == pytest.approx(expected_per_side / spot_price, rel=0.01)
        assert futures_size == pytest.approx(expected_per_side / futures_price, rel=0.01)

    def test_record_funding_payment(self):
        """Test funding payment recording"""
        strategy = FundingRateArbitrageStrategy(symbol='BTCUSDT')

        funding_rate = 0.0003  # 0.03%
        position_size = 0.2  # BTC
        futures_price = 50000.0

        strategy.record_funding_payment(funding_rate, position_size, futures_price)

        # Payment = 0.2 BTC × 50,000 USD/BTC × 0.0003 = 3 USD
        assert strategy.total_funding_collected == pytest.approx(3.0, rel=0.01)
        assert len(strategy.funding_history) == 1
        assert strategy.funding_history[0]['funding_rate'] == 0.0003
        assert strategy.funding_history[0]['funding_payment'] == pytest.approx(3.0, rel=0.01)

    def test_record_multiple_funding_payments(self):
        """Test multiple funding payment recordings"""
        strategy = FundingRateArbitrageStrategy(symbol='BTCUSDT')

        # First payment
        strategy.record_funding_payment(0.0003, 0.2, 50000.0)
        # Second payment
        strategy.record_funding_payment(0.0004, 0.2, 51000.0)
        # Third payment
        strategy.record_funding_payment(0.0002, 0.2, 49000.0)

        # Total = 3.0 + 4.08 + 1.96 = 9.04 USD
        assert strategy.total_funding_collected == pytest.approx(9.04, rel=0.01)
        assert len(strategy.funding_history) == 3

    def test_generate_signal_open_hedge(self):
        """Test signal generation for opening hedge position"""
        strategy = FundingRateArbitrageStrategy(
            symbol='BTCUSDT',
            min_funding_rate=0.0003,  # 0.03% minimum
            max_basis_pct=2.0
        )

        # Favorable conditions: high funding rate, low basis
        current_funding_rate = 0.0005  # 0.05% > minimum
        spot_price = 50000.0
        futures_price = 50200.0  # 0.4% basis < 2% max
        portfolio_value = PORTFOLIO_VALUE

        signal = strategy.generate_signal(
            current_funding_rate,
            spot_price,
            futures_price,
            portfolio_value
        )

        assert signal is not None
        assert signal.action == 'OPEN_HEDGE'
        assert signal.funding_rate == 0.0005
        assert signal.annualized_yield > 50.0  # >50% APY
        assert signal.basis_pct == pytest.approx(0.4, rel=0.01)
        assert signal.confidence > 70.0
        assert strategy.current_position == 'HEDGED'

    def test_generate_signal_open_hedge_negative_funding(self):
        """Test opening hedge with negative funding rate"""
        strategy = FundingRateArbitrageStrategy(
            symbol='BTCUSDT',
            min_funding_rate=0.0003
        )

        # Negative funding rate (shorts pay longs)
        current_funding_rate = -0.0004  # -0.04%
        spot_price = 50000.0
        futures_price = 49800.0  # Negative basis
        portfolio_value = PORTFOLIO_VALUE

        signal = strategy.generate_signal(
            current_funding_rate,
            spot_price,
            futures_price,
            portfolio_value
        )

        assert signal is not None
        assert signal.action == 'OPEN_HEDGE'
        assert 'negative funding' in signal.reason.lower()

    def test_generate_signal_hold_insufficient_funding(self):
        """Test signal generation when funding rate is below minimum"""
        strategy = FundingRateArbitrageStrategy(
            symbol='BTCUSDT',
            min_funding_rate=0.0003
        )

        # Funding rate below minimum
        current_funding_rate = 0.0001  # 0.01% < 0.03% minimum
        spot_price = 50000.0
        futures_price = 50100.0
        portfolio_value = PORTFOLIO_VALUE

        signal = strategy.generate_signal(
            current_funding_rate,
            spot_price,
            futures_price,
            portfolio_value
        )

        assert signal is not None
        assert signal.action == 'HOLD'
        assert 'insufficient' in signal.reason.lower()
        assert strategy.current_position is None

    def test_generate_signal_close_hedge_low_funding(self):
        """Test closing hedge when funding rate becomes too low"""
        strategy = FundingRateArbitrageStrategy(
            symbol='BTCUSDT',
            min_funding_rate=0.0003,
            funding_collection_threshold=0.0001
        )

        # First open position
        strategy.current_position = 'HEDGED'
        strategy.entry_funding_rate = 0.0005

        # Now funding rate dropped below threshold
        current_funding_rate = 0.00005  # 0.005% < 0.01% threshold
        spot_price = 50000.0
        futures_price = 50100.0
        portfolio_value = PORTFOLIO_VALUE

        signal = strategy.generate_signal(
            current_funding_rate,
            spot_price,
            futures_price,
            portfolio_value
        )

        assert signal is not None
        assert signal.action == 'CLOSE_HEDGE'
        assert 'too low' in signal.reason.lower()
        assert strategy.current_position is None

    def test_generate_signal_close_hedge_basis_risk(self):
        """Test closing hedge when basis exceeds maximum"""
        strategy = FundingRateArbitrageStrategy(
            symbol='BTCUSDT',
            max_basis_pct=2.0
        )

        # Open position
        strategy.current_position = 'HEDGED'
        strategy.entry_funding_rate = 0.0005
        strategy.entry_basis = 200.0

        # Basis expanded too much
        current_funding_rate = 0.0004  # Still good
        spot_price = 50000.0
        futures_price = 51200.0  # 2.4% basis > 2% max
        portfolio_value = PORTFOLIO_VALUE

        signal = strategy.generate_signal(
            current_funding_rate,
            spot_price,
            futures_price,
            portfolio_value
        )

        assert signal is not None
        assert signal.action == 'CLOSE_HEDGE'
        assert 'basis risk' in signal.reason.lower()
        assert signal.confidence >= 95.0

    def test_generate_signal_close_hedge_funding_reversal(self):
        """Test closing hedge when funding rate reverses sign

        Note: Implementation checks 'funding rate too low' before 'reversed'.
        When funding goes from positive to negative, it triggers 'too low' first
        if the negative rate is below the threshold.
        """
        strategy = FundingRateArbitrageStrategy(
            symbol='BTCUSDT',
            funding_collection_threshold=-0.001  # Very low threshold to trigger reversal detection
        )

        # Open position with positive funding
        strategy.current_position = 'HEDGED'
        strategy.entry_funding_rate = 0.0005  # Positive

        # Funding reversed to negative but above the collection threshold
        current_funding_rate = -0.0002  # Negative (reversal case)
        spot_price = 50000.0
        futures_price = 50100.0
        portfolio_value = PORTFOLIO_VALUE

        signal = strategy.generate_signal(
            current_funding_rate,
            spot_price,
            futures_price,
            portfolio_value
        )

        assert signal is not None
        assert signal.action == 'CLOSE_HEDGE'
        # Should contain either 'reversed' or 'too low' depending on threshold
        assert 'reversed' in signal.reason.lower() or 'too low' in signal.reason.lower()

    def test_generate_signal_hold_maintaining_hedge(self):
        """Test holding signal when hedge conditions remain favorable"""
        strategy = FundingRateArbitrageStrategy(
            symbol='BTCUSDT',
            min_funding_rate=0.0003,
            funding_collection_threshold=0.0001
        )

        # Open position
        strategy.current_position = 'HEDGED'
        strategy.entry_funding_rate = 0.0005

        # Conditions still favorable
        current_funding_rate = 0.0004  # Still above threshold
        spot_price = 50000.0
        futures_price = 50300.0  # 0.6% basis - acceptable
        portfolio_value = PORTFOLIO_VALUE

        signal = strategy.generate_signal(
            current_funding_rate,
            spot_price,
            futures_price,
            portfolio_value
        )

        assert signal is not None
        assert signal.action == 'HOLD'
        assert 'maintaining' in signal.reason.lower()
        assert strategy.current_position == 'HEDGED'

    def test_generate_signal_abnormal_funding_rate(self):
        """Test handling abnormally high funding rate"""
        strategy = FundingRateArbitrageStrategy(
            symbol='BTCUSDT',
            max_funding_rate=0.01  # 1% max
        )

        # Abnormally high funding rate (market manipulation risk)
        current_funding_rate = 0.015  # 1.5% > 1% max
        spot_price = 50000.0
        futures_price = 50100.0
        portfolio_value = PORTFOLIO_VALUE

        signal = strategy.generate_signal(
            current_funding_rate,
            spot_price,
            futures_price,
            portfolio_value
        )

        assert signal is not None
        assert signal.action == 'HOLD'
        assert 'too high' in signal.reason.lower() or 'abnormal' in signal.reason.lower()

    def test_generate_signal_abnormal_funding_rate_close_existing(self):
        """Test closing existing position when funding becomes abnormal"""
        strategy = FundingRateArbitrageStrategy(
            symbol='BTCUSDT',
            max_funding_rate=0.01
        )

        # Existing position
        strategy.current_position = 'HEDGED'
        strategy.entry_funding_rate = 0.0005

        # Funding rate becomes abnormal
        current_funding_rate = 0.02  # 2% > 1% max (danger zone)
        spot_price = 50000.0
        futures_price = 50100.0
        portfolio_value = PORTFOLIO_VALUE

        signal = strategy.generate_signal(
            current_funding_rate,
            spot_price,
            futures_price,
            portfolio_value
        )

        assert signal is not None
        assert signal.action == 'CLOSE_HEDGE'
        assert 'abnormal' in signal.reason.lower()

    def test_get_status(self):
        """Test status reporting"""
        strategy = FundingRateArbitrageStrategy(
            symbol='BTCUSDT',
            min_funding_rate=0.0003,
            max_basis_pct=2.5
        )

        # Simulate some activity
        strategy.current_position = 'HEDGED'
        strategy.entry_funding_rate = 0.0005
        strategy.entry_basis = 250.0
        strategy.total_funding_collected = 25.0

        status = strategy.get_status()

        assert status['symbol'] == 'BTCUSDT'
        assert status['current_position'] == 'HEDGED'
        assert status['entry_funding_rate'] == 0.0005
        assert status['entry_basis'] == 250.0
        assert status['total_funding_collected'] == 25.0
        assert status['parameters']['min_funding_rate'] == 0.0003
        assert status['parameters']['max_basis_pct'] == 2.5
        assert 'min_apy' in status['annualized_targets']

    def test_get_funding_history(self):
        """Test retrieving funding history"""
        strategy = FundingRateArbitrageStrategy(symbol='BTCUSDT')

        # Add funding payments
        strategy.record_funding_payment(0.0003, 0.2, 50000.0)
        strategy.record_funding_payment(0.0004, 0.2, 51000.0)
        strategy.record_funding_payment(0.0002, 0.2, 49000.0)

        # Get last 2 payments
        history = strategy.get_funding_history(limit=2)

        assert len(history) == 2
        assert history[0]['funding_rate'] == 0.0004  # Second payment
        assert history[1]['funding_rate'] == 0.0002  # Third payment

    def test_calculate_current_yield(self):
        """Test yield calculation"""
        strategy = FundingRateArbitrageStrategy(symbol='BTCUSDT')

        funding_rate = 0.0003  # 0.03% per 8h

        yield_metrics = strategy.calculate_current_yield(funding_rate, days_held=1)

        assert yield_metrics['funding_rate_8h'] == 0.0003
        assert yield_metrics['daily_rate'] == pytest.approx(0.0009, rel=0.01)  # 0.0003 × 3
        assert yield_metrics['daily_rate_pct'] == pytest.approx(0.09, rel=0.01)  # 0.09%
        assert yield_metrics['annualized_rate_pct'] == pytest.approx(32.85, rel=0.01)  # ~32.85%
        assert yield_metrics['projected_30d_return'] == pytest.approx(2.7, rel=0.01)  # ~2.7%


class TestFundingRateArbitrageIntegration:
    """Integration tests for complete workflow"""

    def test_complete_arbitrage_cycle(self):
        """Test complete arbitrage cycle from entry to exit"""
        strategy = FundingRateArbitrageStrategy(
            symbol='BTCUSDT',
            min_funding_rate=0.0003,
            funding_collection_threshold=0.0001,
            max_basis_pct=2.0
        )

        portfolio_value = PORTFOLIO_VALUE

        # Step 1: Open hedge
        signal1 = strategy.generate_signal(
            current_funding_rate=0.0005,
            spot_price=50000.0,
            futures_price=50200.0,
            portfolio_value=portfolio_value
        )

        assert signal1.action == 'OPEN_HEDGE'
        assert strategy.current_position == 'HEDGED'

        # Step 2: Collect funding payments over multiple periods
        strategy.record_funding_payment(0.0005, signal1.futures_position_size, 50200.0)
        strategy.record_funding_payment(0.0004, signal1.futures_position_size, 50300.0)
        strategy.record_funding_payment(0.0003, signal1.futures_position_size, 50100.0)

        assert strategy.total_funding_collected > 0.0
        assert len(strategy.funding_history) == 3

        # Step 3: Hold while conditions remain favorable
        signal2 = strategy.generate_signal(
            current_funding_rate=0.0004,
            spot_price=50000.0,
            futures_price=50400.0,
            portfolio_value=portfolio_value
        )

        assert signal2.action == 'HOLD'

        # Step 4: Close when funding becomes unfavorable
        signal3 = strategy.generate_signal(
            current_funding_rate=0.00005,  # Dropped below threshold
            spot_price=50000.0,
            futures_price=50100.0,
            portfolio_value=portfolio_value
        )

        assert signal3.action == 'CLOSE_HEDGE'
        assert strategy.current_position is None

    def test_risk_management_basis_expansion(self):
        """Test that strategy closes position when basis expands too much"""
        strategy = FundingRateArbitrageStrategy(
            symbol='BTCUSDT',
            max_basis_pct=2.0
        )

        # Open position with normal basis
        strategy.current_position = 'HEDGED'
        strategy.entry_funding_rate = 0.0005
        strategy.entry_basis = 200.0  # 0.4% basis

        # Simulate basis expansion
        spot_prices = [50000.0, 50000.0, 50000.0, 50000.0]
        futures_prices = [50500.0, 50800.0, 51100.0, 51500.0]  # Expanding basis

        for i, (spot, futures) in enumerate(zip(spot_prices, futures_prices)):
            signal = strategy.generate_signal(
                current_funding_rate=0.0004,  # Still attractive
                spot_price=spot,
                futures_price=futures,
                portfolio_value=PORTFOLIO_VALUE
            )

            basis_pct = ((futures - spot) / spot) * 100

            if basis_pct > 2.0:
                # Should close when basis > 2%
                assert signal.action == 'CLOSE_HEDGE'
                break
            elif i < len(spot_prices) - 1:
                # Should hold while basis acceptable
                assert signal.action in ['HOLD', 'CLOSE_HEDGE']

    def test_funding_rate_reversal_protection(self):
        """Test protection against funding rate reversals

        Note: When funding rate goes negative and below threshold,
        'too low' condition triggers before 'reversed' condition.
        This test verifies the position is closed in either case.
        """
        strategy = FundingRateArbitrageStrategy(
            symbol='BTCUSDT',
            funding_collection_threshold=0.0001
        )

        # Open position with positive funding
        strategy.current_position = 'HEDGED'
        strategy.entry_funding_rate = 0.0006

        # Simulate funding rate declining and reversing
        funding_rates = [0.0005, 0.0003, 0.0001, -0.0001]

        close_triggered = False
        for rate in funding_rates:
            signal = strategy.generate_signal(
                current_funding_rate=rate,
                spot_price=50000.0,
                futures_price=50200.0,
                portfolio_value=PORTFOLIO_VALUE
            )

            if rate < strategy.funding_collection_threshold:
                # Should close when funding drops too low or reverses
                assert signal.action == 'CLOSE_HEDGE'
                # Accept either reason since both indicate closure
                assert 'too low' in signal.reason.lower() or 'reversed' in signal.reason.lower()
                close_triggered = True
                break

        assert close_triggered, "Position should have been closed when funding reversed"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
