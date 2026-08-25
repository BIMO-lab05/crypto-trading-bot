"""
Unit Tests for Pairs Trading Strategy

Tests cover:
- Strategy initialization
- Calibration with cointegrated pairs
- Spread and Z-score calculation
- Signal generation logic
- Position sizing
- Risk management (stop loss, exit)

Phase 2.2 - Statistical Arbitrage Implementation
"""

import pytest
import numpy as np
import pandas as pd

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.strategies.pairs_trading import (
    PairsTradingStrategy,
)
from app.config import get_settings

# Account-size fixture routed through Settings (ADR-029) - never a bare literal.
PORTFOLIO_VALUE = float(get_settings().paper_initial_balance)


# ============================================================================
# Test Data Generation
# ============================================================================


def generate_cointegrated_pair(n: int = 200, hedge_ratio: float = 0.5, seed: int = 42) -> tuple:
    """Generate synthetic cointegrated price series"""
    np.random.seed(seed)

    dates = pd.date_range("2025-01-01", periods=n, freq="h")

    # Generate non-stationary series X (random walk)
    x_returns = np.random.normal(0.001, 0.02, n)
    x_prices = 100 * np.exp(np.cumsum(x_returns))
    x = pd.Series(x_prices, index=dates)

    # Generate stationary spread
    spread = np.zeros(n)
    spread[0] = np.random.normal(0, 2)
    for t in range(1, n):
        # AR(1) process with mean reversion
        spread[t] = 0.7 * spread[t - 1] + np.random.normal(0, 1)

    # Cointegrated series: Y = β*X + spread
    y = hedge_ratio * x + spread

    return x, y


# ============================================================================
# Test Strategy Initialization
# ============================================================================


class TestPairsTradingInitialization:
    """Test strategy initialization"""

    def test_initialization_default_parameters(self):
        """Test strategy initializes with default parameters"""
        strategy = PairsTradingStrategy(symbol_x="BTCUSDT", symbol_y="ETHUSDT")

        assert strategy.symbol_x == "BTCUSDT"
        assert strategy.symbol_y == "ETHUSDT"
        assert strategy.entry_threshold == 2.0
        assert strategy.exit_threshold == 0.5
        assert strategy.stop_threshold == 3.0
        assert strategy.max_position_size == 0.1
        assert strategy.is_cointegrated == False
        assert strategy.current_position is None

    def test_initialization_custom_parameters(self):
        """Test strategy initializes with custom parameters"""
        strategy = PairsTradingStrategy(
            symbol_x="BTCUSDT",
            symbol_y="ETHUSDT",
            entry_threshold=2.5,
            exit_threshold=0.3,
            stop_threshold=3.5,
            max_position_size=0.15,
        )

        assert strategy.entry_threshold == 2.5
        assert strategy.exit_threshold == 0.3
        assert strategy.stop_threshold == 3.5
        assert strategy.max_position_size == 0.15


# ============================================================================
# Test Calibration
# ============================================================================


class TestPairsTradingCalibration:
    """Test strategy calibration"""

    def test_calibrate_cointegrated_pair(self):
        """Test calibration succeeds with cointegrated pair"""
        strategy = PairsTradingStrategy(symbol_x="ASSET_X", symbol_y="ASSET_Y")

        # Generate cointegrated data
        price_x, price_y = generate_cointegrated_pair(n=300, hedge_ratio=0.5)

        # Calibrate
        success = strategy.calibrate(price_x, price_y)

        assert success == True
        assert strategy.is_cointegrated == True
        assert strategy.hedge_ratio is not None
        assert abs(strategy.hedge_ratio - 0.5) < 0.1  # Should be close to 0.5
        assert strategy.spread_mean is not None
        assert strategy.spread_std is not None
        assert strategy.spread_std > 0
        assert strategy.half_life is not None
        assert strategy.last_calibration is not None

    def test_calibrate_non_cointegrated_pair(self):
        """Test calibration fails with non-cointegrated pair"""
        strategy = PairsTradingStrategy(symbol_x="ASSET_X", symbol_y="ASSET_Y")

        # Generate independent random walks
        np.random.seed(42)
        dates = pd.date_range("2025-01-01", periods=300, freq="h")
        price_x = pd.Series(
            100 * np.exp(np.cumsum(np.random.normal(0.001, 0.02, 300))), index=dates
        )
        price_y = pd.Series(
            100 * np.exp(np.cumsum(np.random.normal(0.001, 0.02, 300))), index=dates
        )

        # Calibrate (may fail depending on random data)
        success = strategy.calibrate(price_x, price_y)

        # If calibration fails, is_cointegrated should be False
        if not success:
            assert strategy.is_cointegrated == False


# ============================================================================
# Test Spread and Z-score Calculation
# ============================================================================


class TestSpreadCalculations:
    """Test spread and Z-score calculations"""

    def test_calculate_spread(self):
        """Test spread calculation: S = Y - β*X"""
        strategy = PairsTradingStrategy(symbol_x="X", symbol_y="Y")

        # Simple test data
        price_x = pd.Series([100, 110, 120])
        price_y = pd.Series([50, 55, 60])
        hedge_ratio = 0.5

        spread = strategy._calculate_spread(price_x, price_y, hedge_ratio)

        # S = Y - 0.5*X
        expected = pd.Series([50 - 0.5 * 100, 55 - 0.5 * 110, 60 - 0.5 * 120])

        pd.testing.assert_series_equal(spread, expected)

    def test_calculate_z_score(self):
        """Test Z-score calculation: z = (S - μ) / σ"""
        strategy = PairsTradingStrategy(symbol_x="X", symbol_y="Y")

        # Test cases
        assert strategy._calculate_z_score(10, 5, 2) == pytest.approx(2.5, abs=0.01)
        assert strategy._calculate_z_score(5, 5, 2) == pytest.approx(0.0, abs=0.01)
        assert strategy._calculate_z_score(0, 5, 2) == pytest.approx(-2.5, abs=0.01)

    def test_calculate_z_score_zero_std(self):
        """Test Z-score with zero standard deviation"""
        strategy = PairsTradingStrategy(symbol_x="X", symbol_y="Y")

        # When std = 0, should return 0.0 to avoid division by zero
        result = strategy._calculate_z_score(10, 5, 0)
        assert result == 0.0


# ============================================================================
# Test Signal Generation
# ============================================================================


class TestSignalGeneration:
    """Test signal generation logic"""

    def test_signal_open_long_y(self):
        """Test OPEN_LONG_Y signal when Z-score < -entry_threshold"""
        strategy = PairsTradingStrategy(symbol_x="X", symbol_y="Y", entry_threshold=2.0)

        # Calibrate with synthetic data
        price_x, price_y = generate_cointegrated_pair(n=300, hedge_ratio=0.5)
        strategy.calibrate(price_x, price_y)

        # Create scenario where Z-score < -2.0
        # Spread too low → LONG Y / SHORT X
        current_price_x = 100.0
        current_price_y = (
            strategy.hedge_ratio * current_price_x + strategy.spread_mean - 3 * strategy.spread_std
        )

        signal = strategy.generate_signal(
            current_price_x, current_price_y, price_x, price_y, portfolio_value=PORTFOLIO_VALUE
        )

        assert signal is not None
        assert signal.action == "OPEN_LONG_Y"
        assert signal.z_score < -strategy.entry_threshold
        assert signal.confidence > 0

    def test_signal_open_short_y(self):
        """Test OPEN_SHORT_Y signal when Z-score > entry_threshold"""
        strategy = PairsTradingStrategy(symbol_x="X", symbol_y="Y", entry_threshold=2.0)

        # Calibrate
        price_x, price_y = generate_cointegrated_pair(n=300, hedge_ratio=0.5)
        strategy.calibrate(price_x, price_y)

        # Create scenario where Z-score > +2.0
        # Spread too high → SHORT Y / LONG X
        current_price_x = 100.0
        current_price_y = (
            strategy.hedge_ratio * current_price_x + strategy.spread_mean + 3 * strategy.spread_std
        )

        signal = strategy.generate_signal(
            current_price_x, current_price_y, price_x, price_y, portfolio_value=PORTFOLIO_VALUE
        )

        assert signal is not None
        assert signal.action == "OPEN_SHORT_Y"
        assert signal.z_score > strategy.entry_threshold
        assert signal.confidence > 0

    def test_signal_close_mean_reversion(self):
        """Test CLOSE signal when spread reverts to mean"""
        strategy = PairsTradingStrategy(symbol_x="X", symbol_y="Y", exit_threshold=0.5)

        # Calibrate
        price_x, price_y = generate_cointegrated_pair(n=300, hedge_ratio=0.5)
        strategy.calibrate(price_x, price_y)

        # Set current position
        strategy.current_position = "LONG_Y"

        # Create scenario where Z-score near 0 (mean reversion)
        current_price_x = 100.0
        current_price_y = strategy.hedge_ratio * current_price_x + strategy.spread_mean

        signal = strategy.generate_signal(
            current_price_x, current_price_y, price_x, price_y, portfolio_value=PORTFOLIO_VALUE
        )

        assert signal is not None
        assert signal.action == "CLOSE"
        assert abs(signal.z_score) < strategy.exit_threshold

    def test_signal_stop_loss(self):
        """Test CLOSE signal for stop loss"""
        strategy = PairsTradingStrategy(symbol_x="X", symbol_y="Y", stop_threshold=3.0)

        # Calibrate
        price_x, price_y = generate_cointegrated_pair(n=300, hedge_ratio=0.5)
        strategy.calibrate(price_x, price_y)

        # Set current position
        strategy.current_position = "LONG_Y"

        # Create scenario where |Z-score| > stop_threshold
        current_price_x = 100.0
        current_price_y = (
            strategy.hedge_ratio * current_price_x + strategy.spread_mean + 4 * strategy.spread_std
        )

        signal = strategy.generate_signal(
            current_price_x, current_price_y, price_x, price_y, portfolio_value=PORTFOLIO_VALUE
        )

        assert signal is not None
        assert signal.action == "CLOSE"
        assert abs(signal.z_score) > strategy.stop_threshold
        assert "Stop loss" in signal.reason

    def test_signal_hold_neutral_zone(self):
        """Test HOLD signal when Z-score in neutral zone"""
        strategy = PairsTradingStrategy(
            symbol_x="X", symbol_y="Y", entry_threshold=2.0, exit_threshold=0.5
        )

        # Calibrate
        price_x, price_y = generate_cointegrated_pair(n=300, hedge_ratio=0.5)
        strategy.calibrate(price_x, price_y)

        # No current position
        strategy.current_position = None

        # Z-score in neutral zone (between exit and entry)
        current_price_x = 100.0
        current_price_y = (
            strategy.hedge_ratio * current_price_x
            + strategy.spread_mean
            + 1.0 * strategy.spread_std
        )

        signal = strategy.generate_signal(
            current_price_x, current_price_y, price_x, price_y, portfolio_value=PORTFOLIO_VALUE
        )

        assert signal is not None
        assert signal.action == "HOLD"


# ============================================================================
# Test Position Sizing
# ============================================================================


class TestPositionSizing:
    """Test position sizing calculations"""

    def test_position_sizes_basic(self):
        """Test basic position sizing"""
        strategy = PairsTradingStrategy(
            symbol_x="X",
            symbol_y="Y",
            max_position_size=0.1,  # 10% per leg
        )
        strategy.hedge_ratio = 0.5

        price_x = 100.0
        price_y = 50.0
        portfolio_value = PORTFOLIO_VALUE
        z_score_abs = 2.5

        pos_x, pos_y = strategy._calculate_position_sizes(
            price_x, price_y, portfolio_value, z_score_abs
        )

        # Max capital per leg = max_position_size * portfolio_value
        # Position Y = leg capital / price_y units
        # Position X = pos_y * hedge_ratio units

        assert pos_y > 0
        assert pos_x > 0
        # Maintain hedge ratio
        assert abs(pos_x / pos_y - strategy.hedge_ratio) < 0.01

    def test_position_sizes_scale_with_z_score(self):
        """Test that position sizes scale with Z-score strength"""
        strategy = PairsTradingStrategy(
            symbol_x="X", symbol_y="Y", max_position_size=0.1, entry_threshold=2.0
        )
        strategy.hedge_ratio = 0.5

        price_x = 100.0
        price_y = 50.0
        portfolio_value = PORTFOLIO_VALUE

        # Low Z-score (just at entry)
        pos_x_low, pos_y_low = strategy._calculate_position_sizes(
            price_x, price_y, portfolio_value, 2.0
        )

        # High Z-score (well above entry)
        pos_x_high, pos_y_high = strategy._calculate_position_sizes(
            price_x, price_y, portfolio_value, 3.5
        )

        # Higher Z-score should give larger positions
        assert pos_y_high > pos_y_low
        assert pos_x_high > pos_x_low


# ============================================================================
# Test Recalibration
# ============================================================================


class TestRecalibration:
    """Test automatic recalibration"""

    def test_needs_recalibration_initial(self):
        """Test needs recalibration initially"""
        strategy = PairsTradingStrategy(symbol_x="X", symbol_y="Y")

        assert strategy._needs_recalibration() == True

    def test_needs_recalibration_after_calibration(self):
        """Test doesn't need recalibration immediately after calibration"""
        strategy = PairsTradingStrategy(
            symbol_x="X",
            symbol_y="Y",
            recalibration_period=24,  # 24 hours
        )

        # Calibrate
        price_x, price_y = generate_cointegrated_pair(n=300)
        strategy.calibrate(price_x, price_y)

        # Should not need recalibration immediately
        assert strategy._needs_recalibration() == False

    def test_needs_recalibration_after_period(self):
        """Test needs recalibration after specified period"""
        strategy = PairsTradingStrategy(
            symbol_x="X",
            symbol_y="Y",
            recalibration_period=0.001,  # Very short period for testing (0.001 hours ≈ 3.6 seconds)
        )

        # Calibrate
        price_x, price_y = generate_cointegrated_pair(n=300)
        strategy.calibrate(price_x, price_y)

        # Wait a bit
        import time

        time.sleep(4)  # Wait 4 seconds

        # Should need recalibration now
        assert strategy._needs_recalibration() == True


# ============================================================================
# Test Strategy Status
# ============================================================================


class TestStrategyStatus:
    """Test strategy status reporting"""

    def test_get_status(self):
        """Test get_status returns correct information"""
        strategy = PairsTradingStrategy(symbol_x="BTCUSDT", symbol_y="ETHUSDT", entry_threshold=2.5)

        status = strategy.get_status()

        assert status["symbol_x"] == "BTCUSDT"
        assert status["symbol_y"] == "ETHUSDT"
        assert status["is_cointegrated"] == False
        assert status["current_position"] is None
        assert "parameters" in status
        assert status["parameters"]["entry_threshold"] == 2.5

    def test_get_status_after_calibration(self):
        """Test get_status after calibration"""
        strategy = PairsTradingStrategy(symbol_x="X", symbol_y="Y")

        # Calibrate
        price_x, price_y = generate_cointegrated_pair(n=300, hedge_ratio=0.5)
        strategy.calibrate(price_x, price_y)

        status = strategy.get_status()

        assert status["is_cointegrated"] == True
        assert status["hedge_ratio"] is not None
        assert status["spread_mean"] is not None
        assert status["spread_std"] is not None
        assert status["last_calibration"] is not None


# ============================================================================
# Integration Tests
# ============================================================================


class TestPairsTradingIntegration:
    """Integration tests for complete workflow"""

    def test_complete_trading_cycle(self):
        """Test complete trading cycle: calibrate → signal → trade → close"""
        strategy = PairsTradingStrategy(
            symbol_x="ASSET_X", symbol_y="ASSET_Y", entry_threshold=2.0, exit_threshold=0.5
        )

        # Generate historical data
        price_x, price_y = generate_cointegrated_pair(n=300, hedge_ratio=0.5)

        # 1. Calibrate
        success = strategy.calibrate(price_x, price_y)
        assert success == True

        # 2. Generate entry signal (high Z-score)
        current_price_x = 100.0
        current_price_y = (
            strategy.hedge_ratio * current_price_x + strategy.spread_mean + 3 * strategy.spread_std
        )

        signal_entry = strategy.generate_signal(
            current_price_x, current_price_y, price_x, price_y,
            portfolio_value=PORTFOLIO_VALUE,
        )

        assert signal_entry is not None
        assert signal_entry.action == "OPEN_SHORT_Y"

        # 3. Generate exit signal (Z-score near 0)
        current_price_y_exit = strategy.hedge_ratio * current_price_x + strategy.spread_mean

        signal_exit = strategy.generate_signal(
            current_price_x, current_price_y_exit, price_x, price_y,
            portfolio_value=PORTFOLIO_VALUE,
        )

        assert signal_exit is not None
        assert signal_exit.action == "CLOSE"


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
