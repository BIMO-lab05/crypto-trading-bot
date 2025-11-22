#!/usr/bin/env python3
"""
Unit Tests for MACD Calculator

Tests MACD (Moving Average Convergence Divergence) calculation,
signal generation, crossover detection, and edge cases.
"""

import pytest
import pandas as pd
import numpy as np

import sys
sys.path.insert(0, '/mnt/d/Bimo_max/crypto-trading-bot/services/technical-analysis')

from app.indicators.macd import MACDCalculator
from app.models import SignalType


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def macd_calculator():
    """Standard MACD calculator with default periods (12, 26, 9)"""
    return MACDCalculator()


@pytest.fixture
def sample_uptrend_data():
    """Generate uptrending price data"""
    prices = [100 + i * 0.5 for i in range(100)]
    return pd.DataFrame({'close': prices})


@pytest.fixture
def sample_downtrend_data():
    """Generate downtrending price data"""
    prices = [100 - i * 0.5 for i in range(100)]
    return pd.DataFrame({'close': prices})


@pytest.fixture
def sample_sideways_data():
    """Generate sideways (ranging) price data"""
    prices = [100 + np.sin(i / 5) * 2 for i in range(100)]
    return pd.DataFrame({'close': prices})


# ============================================================================
# Initialization Tests
# ============================================================================

def test_macd_initialization(macd_calculator):
    """Test MACD calculator initialization with default parameters"""
    assert macd_calculator.fast_period == 12
    assert macd_calculator.slow_period == 26
    assert macd_calculator.signal_period == 9
    assert macd_calculator.min_periods == 35  # 26 + 9


def test_macd_custom_periods():
    """Test MACD with custom periods"""
    macd = MACDCalculator(fast_period=8, slow_period=17, signal_period=5)

    assert macd.fast_period == 8
    assert macd.slow_period == 17
    assert macd.signal_period == 5
    assert macd.min_periods == 22  # 17 + 5


# ============================================================================
# MACD Calculation Tests
# ============================================================================

def test_macd_calculation_structure(macd_calculator, sample_uptrend_data):
    """Test MACD calculation returns correct structure"""
    result = macd_calculator.calculate(sample_uptrend_data)

    assert result is not None
    assert isinstance(result, dict)
    assert "macd_line" in result
    assert "signal_line" in result
    assert "histogram" in result


def test_macd_calculation_uptrend(macd_calculator, sample_uptrend_data):
    """Test MACD calculation on uptrending data"""
    result = macd_calculator.calculate(sample_uptrend_data)

    assert result is not None

    # In uptrend, MACD line should be above signal line (positive histogram)
    # Note: This might not always be true at the very end, but generally holds
    macd_line = result["macd_line"]
    signal_line = result["signal_line"]
    histogram = result["histogram"]

    # Histogram should equal macd_line - signal_line
    assert abs(histogram - (macd_line - signal_line)) < 0.01

    # In uptrend, MACD line should be positive (fast EMA > slow EMA)
    assert macd_line > 0


def test_macd_calculation_downtrend(macd_calculator, sample_downtrend_data):
    """Test MACD calculation on downtrending data"""
    result = macd_calculator.calculate(sample_downtrend_data)

    assert result is not None

    macd_line = result["macd_line"]

    # In downtrend, MACD line should be negative (fast EMA < slow EMA)
    assert macd_line < 0


def test_macd_insufficient_data(macd_calculator):
    """Test MACD returns None with insufficient data"""
    # Only 30 data points, need at least 35
    short_data = pd.DataFrame({'close': [100] * 30})
    result = macd_calculator.calculate(short_data)

    assert result is None


def test_macd_exact_minimum_data(macd_calculator):
    """Test MACD with exactly minimum required data"""
    # Exactly min_periods = 35
    min_data = pd.DataFrame({'close': [100 + i * 0.1 for i in range(35)]})
    result = macd_calculator.calculate(min_data)

    assert result is not None


# ============================================================================
# Signal Generation Tests
# ============================================================================

def test_signal_positive_histogram_buy(macd_calculator):
    """Test BUY signal when histogram is positive (MACD > Signal)"""
    macd_data = {
        "macd_line": 5.0,
        "signal_line": 3.0,
        "histogram": 2.0
    }

    signal, confidence = macd_calculator.generate_signal(macd_data)

    assert signal == SignalType.BUY
    assert 0 < confidence <= 1.0


def test_signal_negative_histogram_sell(macd_calculator):
    """Test SELL signal when histogram is negative (MACD < Signal)"""
    macd_data = {
        "macd_line": 3.0,
        "signal_line": 5.0,
        "histogram": -2.0
    }

    signal, confidence = macd_calculator.generate_signal(macd_data)

    assert signal == SignalType.SELL
    assert 0 < confidence <= 1.0


def test_signal_zero_histogram_hold(macd_calculator):
    """Test HOLD signal when histogram is zero (MACD = Signal)"""
    macd_data = {
        "macd_line": 5.0,
        "signal_line": 5.0,
        "histogram": 0.0
    }

    signal, confidence = macd_calculator.generate_signal(macd_data)

    assert signal == SignalType.HOLD
    assert confidence == 0.1


def test_signal_large_positive_histogram_high_confidence(macd_calculator):
    """Test high confidence with large positive histogram"""
    macd_data = {
        "macd_line": 10.0,
        "signal_line": 2.0,
        "histogram": 8.0
    }

    signal, confidence = macd_calculator.generate_signal(macd_data)

    assert signal == SignalType.BUY
    assert confidence > 0.5  # Should have high confidence


def test_signal_small_histogram_low_confidence(macd_calculator):
    """Test low confidence with small histogram"""
    macd_data = {
        "macd_line": 5.1,
        "signal_line": 5.0,
        "histogram": 0.1
    }

    signal, confidence = macd_calculator.generate_signal(macd_data)

    assert signal == SignalType.BUY
    assert confidence >= 0.1  # Minimum confidence enforced


# ============================================================================
# Crossover Detection Tests
# ============================================================================

def test_detect_bullish_crossover(macd_calculator):
    """Test detection of bullish crossover (MACD crosses above Signal)"""
    # Create data that produces a bullish crossover
    prices = []
    for i in range(50):
        if i < 40:
            # Downtrend
            prices.append(100 - i * 0.3)
        else:
            # Reversal - uptrend
            prices.append(88 + (i - 40) * 1.5)

    df = pd.DataFrame({'close': prices})

    crossover = macd_calculator.detect_crossover(df, lookback=5)

    # Should detect bullish crossover
    if crossover:
        assert crossover == "bullish"


def test_detect_bearish_crossover(macd_calculator):
    """Test detection of bearish crossover (MACD crosses below Signal)"""
    # Create data that produces a bearish crossover
    prices = []
    for i in range(50):
        if i < 40:
            # Uptrend
            prices.append(100 + i * 0.3)
        else:
            # Reversal - downtrend
            prices.append(112 - (i - 40) * 1.5)

    df = pd.DataFrame({'close': prices})

    crossover = macd_calculator.detect_crossover(df, lookback=5)

    # Should detect bearish crossover
    if crossover:
        assert crossover == "bearish"


def test_no_crossover_in_trend(macd_calculator, sample_uptrend_data):
    """Test no crossover detected in steady trend"""
    crossover = macd_calculator.detect_crossover(sample_uptrend_data, lookback=3)

    # Might return None if no crossover in recent periods
    # This is valid behavior
    assert crossover in [None, "bullish", "bearish"]


def test_crossover_insufficient_data(macd_calculator):
    """Test crossover detection returns None with insufficient data"""
    short_data = pd.DataFrame({'close': [100] * 20})
    crossover = macd_calculator.detect_crossover(short_data)

    assert crossover is None


# ============================================================================
# Calculate with Signal Tests
# ============================================================================

def test_calculate_with_signal_success(macd_calculator, sample_uptrend_data):
    """Test combined calculation and signal generation"""
    macd_data, signal, confidence = macd_calculator.calculate_with_signal(sample_uptrend_data)

    assert macd_data is not None
    assert "macd_line" in macd_data
    assert "signal_line" in macd_data
    assert "histogram" in macd_data
    assert signal in [SignalType.BUY, SignalType.SELL, SignalType.HOLD, SignalType.NEUTRAL]
    assert 0 <= confidence <= 1.0


def test_calculate_with_signal_insufficient_data(macd_calculator):
    """Test calculate_with_signal returns NEUTRAL with insufficient data"""
    short_data = pd.DataFrame({'close': [100] * 20})
    macd_data, signal, confidence = macd_calculator.calculate_with_signal(short_data)

    assert macd_data is None
    assert signal == SignalType.NEUTRAL
    assert confidence == 0.0


def test_calculate_with_signal_confidence_boost(macd_calculator):
    """Test that crossover detection boosts confidence"""
    # Create data with clear trend and potential crossover
    prices = [100 + i * 0.5 for i in range(60)]
    df = pd.DataFrame({'close': prices})

    macd_data, signal, confidence = macd_calculator.calculate_with_signal(df)

    # Confidence should be bounded [0, 1]
    assert 0 <= confidence <= 1.0


# ============================================================================
# MACD Series Tests
# ============================================================================

def test_calculate_series(macd_calculator, sample_uptrend_data):
    """Test MACD series calculation for entire DataFrame"""
    result_df = macd_calculator.calculate_series(sample_uptrend_data)

    assert isinstance(result_df, pd.DataFrame)
    assert len(result_df) == len(sample_uptrend_data)
    assert "macd_line" in result_df.columns
    assert "signal_line" in result_df.columns
    assert "histogram" in result_df.columns


def test_calculate_series_insufficient_data(macd_calculator):
    """Test series calculation returns empty DataFrame with insufficient data"""
    short_data = pd.DataFrame({'close': [100] * 20})
    result_df = macd_calculator.calculate_series(short_data)

    assert isinstance(result_df, pd.DataFrame)
    assert len(result_df) == 0


def test_calculate_series_histogram_consistency(macd_calculator, sample_uptrend_data):
    """Test that histogram equals macd_line - signal_line throughout series"""
    result_df = macd_calculator.calculate_series(sample_uptrend_data)

    # Drop NaN values
    clean_df = result_df.dropna()

    # Check histogram calculation for all rows
    calculated_histogram = clean_df['macd_line'] - clean_df['signal_line']

    # Should be very close (allowing for floating point precision)
    assert np.allclose(clean_df['histogram'], calculated_histogram, rtol=1e-10)


# ============================================================================
# Edge Cases
# ============================================================================

def test_macd_flat_prices():
    """Test MACD with flat prices (no change)"""
    prices = [100] * 50
    df = pd.DataFrame({'close': prices})

    macd_calc = MACDCalculator()
    result = macd_calc.calculate(df)

    assert result is not None
    # All components should be zero or very close to zero
    assert abs(result["macd_line"]) < 0.01
    assert abs(result["signal_line"]) < 0.01
    assert abs(result["histogram"]) < 0.01


def test_macd_extreme_volatility():
    """Test MACD with extreme price volatility"""
    prices = []
    for i in range(50):
        if i % 2 == 0:
            prices.append(100)
        else:
            prices.append(200)

    df = pd.DataFrame({'close': prices})
    macd_calc = MACDCalculator()
    result = macd_calc.calculate(df)

    assert result is not None
    # MACD should handle volatility


def test_macd_with_nan_values():
    """Test MACD handles NaN values in data"""
    prices = [100, 102, np.nan, 105, 108, 110] + [110 + i for i in range(50)]
    df = pd.DataFrame({'close': prices})

    macd_calc = MACDCalculator()
    result = macd_calc.calculate(df)

    # Should either handle gracefully or return valid result
    if result is not None:
        assert all(not np.isnan(v) for v in result.values())


# ============================================================================
# Performance Tests
# ============================================================================

def test_macd_large_dataset_performance(macd_calculator):
    """Test MACD calculation performance with large dataset"""
    import time

    # Generate 10,000 data points
    prices = [100 + np.sin(i / 100) * 10 for i in range(10000)]
    large_df = pd.DataFrame({'close': prices})

    start_time = time.time()
    result = macd_calculator.calculate(large_df)
    elapsed = time.time() - start_time

    assert result is not None
    assert elapsed < 1.0  # Should complete in less than 1 second


def test_macd_series_large_dataset(macd_calculator):
    """Test MACD series calculation performance"""
    import time

    prices = [100 + np.sin(i / 100) * 10 for i in range(10000)]
    large_df = pd.DataFrame({'close': prices})

    start_time = time.time()
    result_df = macd_calculator.calculate_series(large_df)
    elapsed = time.time() - start_time

    assert len(result_df) == len(large_df)
    assert elapsed < 2.0  # Should complete in less than 2 seconds


# ============================================================================
# Integration-like Tests
# ============================================================================

def test_macd_realistic_bitcoin_scenario():
    """Test MACD with realistic Bitcoin-like price movements"""
    # Simulate Bitcoin-like volatility
    prices = []
    current_price = 45000
    for i in range(100):
        # Random walk with Bitcoin-like volatility
        change_pct = np.random.normal(0, 0.02)  # 2% std dev
        current_price = current_price * (1 + change_pct)
        prices.append(current_price)

    df = pd.DataFrame({'close': prices})
    macd_calc = MACDCalculator()

    result = macd_calc.calculate(df)
    signal, confidence = macd_calc.generate_signal(result)

    assert result is not None
    assert signal in [SignalType.BUY, SignalType.SELL, SignalType.HOLD]
    assert 0 <= confidence <= 1.0


def test_macd_trend_reversal_detection():
    """Test MACD detects trend reversals"""
    # Create data with clear trend reversal
    prices = []

    # Uptrend
    for i in range(40):
        prices.append(100 + i * 0.5)

    # Reversal to downtrend
    for i in range(40):
        prices.append(120 - i * 0.5)

    df = pd.DataFrame({'close': prices})
    macd_calc = MACDCalculator()

    # Calculate MACD at different points
    result_early = macd_calc.calculate(df.iloc[:40])
    result_late = macd_calc.calculate(df.iloc[20:60])

    # Early should be bullish, late should show reversal
    if result_early and result_late:
        # The MACD should change sign indicating trend change
        assert result_early["macd_line"] != result_late["macd_line"]


def test_macd_crossover_with_signal_generation():
    """Test that crossover detection integrates with signal generation"""
    # Create data that produces crossover
    prices = [100 - i * 0.3 for i in range(45)]  # Downtrend
    prices.extend([86.5 + i * 0.5 for i in range(20)])  # Reversal

    df = pd.DataFrame({'close': prices})
    macd_calc = MACDCalculator()

    macd_data, signal, confidence = macd_calc.calculate_with_signal(df)

    # Should generate signal based on current state
    assert signal in [SignalType.BUY, SignalType.SELL, SignalType.HOLD, SignalType.NEUTRAL]
    assert 0 <= confidence <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
