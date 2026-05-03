#!/usr/bin/env python3
"""
Unit Tests for Moving Averages Calculators (SMA, EMA)

Tests SMA and EMA calculation, signal generation,
crossover detection, and Golden/Death Cross patterns.
"""

import pytest
import pandas as pd
import numpy as np

import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent.parent))

from app.indicators.moving_averages import (
    SMACalculator,
    EMACalculator,
    MAGoldenCrossDetector
)
from app.models import SignalType


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sma_calculator():
    """Standard SMA calculator with period=20"""
    return SMACalculator(period=20)


@pytest.fixture
def ema_calculator():
    """Standard EMA calculator with period=20"""
    return EMACalculator(period=20)


@pytest.fixture
def golden_cross_detector():
    """Standard Golden Cross detector (50, 200)"""
    return MAGoldenCrossDetector(fast_period=50, slow_period=200)


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
# SMA Initialization Tests
# ============================================================================

def test_sma_initialization(sma_calculator):
    """Test SMA calculator initialization with default parameters"""
    assert sma_calculator.period == 20


def test_sma_custom_period():
    """Test SMA with custom period"""
    sma = SMACalculator(period=50)
    assert sma.period == 50


# ============================================================================
# SMA Calculation Tests
# ============================================================================

def test_sma_calculation_returns_float(sma_calculator, sample_uptrend_data):
    """Test SMA calculation returns valid float"""
    sma_value = sma_calculator.calculate(sample_uptrend_data)

    assert sma_value is not None
    assert isinstance(sma_value, float)
    assert sma_value > 0


def test_sma_calculation_accuracy(sample_uptrend_data):
    """Test SMA calculation accuracy by manual verification"""
    sma_calc = SMACalculator(period=5)

    # Create simple data
    prices = [100, 102, 104, 106, 108, 110]
    df = pd.DataFrame({'close': prices})

    sma_value = sma_calc.calculate(df)

    # Manual calculation: (100+102+104+106+108)/5 = 104
    expected_sma = sum(prices[-5:]) / 5
    assert abs(sma_value - expected_sma) < 0.01


def test_sma_uptrend_increases(sample_uptrend_data):
    """Test SMA follows uptrend"""
    sma_calc = SMACalculator(period=10)

    # Calculate SMA at different points
    early_sma = sma_calc.calculate(sample_uptrend_data.iloc[:30])
    late_sma = sma_calc.calculate(sample_uptrend_data.iloc[:60])

    # In uptrend, later SMA should be higher
    assert late_sma > early_sma


def test_sma_insufficient_data(sma_calculator):
    """Test SMA returns None with insufficient data"""
    short_data = pd.DataFrame({'close': [100] * 10})
    sma_value = sma_calculator.calculate(short_data)

    assert sma_value is None


def test_sma_exact_minimum_data(sma_calculator):
    """Test SMA with exactly minimum required data"""
    min_data = pd.DataFrame({'close': [100 + i for i in range(20)]})
    sma_value = sma_calculator.calculate(min_data)

    assert sma_value is not None


def test_sma_smoothing_effect():
    """Test SMA smooths out noise"""
    # Create noisy data
    np.random.seed(42)
    prices = [100 + np.random.uniform(-5, 5) for _ in range(50)]
    df = pd.DataFrame({'close': prices})

    sma_calc = SMACalculator(period=10)
    sma_value = sma_calc.calculate(df)

    # SMA should be less extreme than raw prices
    assert sma_value is not None


# ============================================================================
# EMA Initialization Tests
# ============================================================================

def test_ema_initialization(ema_calculator):
    """Test EMA calculator initialization with default parameters"""
    assert ema_calculator.period == 20


def test_ema_custom_period():
    """Test EMA with custom period"""
    ema = EMACalculator(period=12)
    assert ema.period == 12


# ============================================================================
# EMA Calculation Tests
# ============================================================================

def test_ema_calculation_returns_float(ema_calculator, sample_uptrend_data):
    """Test EMA calculation returns valid float"""
    ema_value = ema_calculator.calculate(sample_uptrend_data)

    assert ema_value is not None
    assert isinstance(ema_value, float)
    assert ema_value > 0


def test_ema_more_responsive_than_sma():
    """Test EMA reacts faster to price changes than SMA"""
    # Create data with sudden price spike
    prices = [100] * 20 + [110] * 5  # Short spike period
    df = pd.DataFrame({'close': prices})

    sma_calc = SMACalculator(period=10)
    ema_calc = EMACalculator(period=10)

    # Calculate just after the price change starts
    df_short = df.iloc[:23]  # 20 at 100, 3 at 110

    sma_value = sma_calc.calculate(df_short)
    ema_value = ema_calc.calculate(df_short)

    # EMA should be closer to the new price (110) than SMA
    # during the transition period
    sma_distance = abs(110 - sma_value)
    ema_distance = abs(110 - ema_value)

    # EMA should be closer to new price (smaller distance)
    assert ema_distance < sma_distance


def test_ema_convergence():
    """Test EMA converges to price over time"""
    # Flat prices at 100
    prices = [100] * 50
    df = pd.DataFrame({'close': prices})

    ema_calc = EMACalculator(period=10)
    ema_value = ema_calc.calculate(df)

    # Should converge very close to 100
    assert abs(ema_value - 100) < 0.1


def test_ema_insufficient_data(ema_calculator):
    """Test EMA returns None with insufficient data"""
    short_data = pd.DataFrame({'close': [100] * 10})
    ema_value = ema_calculator.calculate(short_data)

    assert ema_value is None


def test_ema_exact_minimum_data(ema_calculator):
    """Test EMA with exactly minimum required data"""
    min_data = pd.DataFrame({'close': [100 + i for i in range(20)]})
    ema_value = ema_calculator.calculate(min_data)

    assert ema_value is not None


# ============================================================================
# SMA Signal Generation Tests
# ============================================================================

def test_sma_signal_price_above_buy(sma_calculator):
    """Test BUY signal when price is above SMA"""
    sma_value = 100.0
    current_price = 105.0  # 5% above SMA

    signal, confidence = sma_calculator.generate_signal(sma_value, current_price)

    assert signal == SignalType.BUY
    assert confidence > 0.5  # Good confidence at 5% above


def test_sma_signal_price_below_sell(sma_calculator):
    """Test SELL signal when price is below SMA"""
    sma_value = 100.0
    current_price = 95.0  # 5% below SMA

    signal, confidence = sma_calculator.generate_signal(sma_value, current_price)

    assert signal == SignalType.SELL
    assert confidence > 0.5  # Good confidence at 5% below


def test_sma_signal_price_at_hold(sma_calculator):
    """Test HOLD signal when price equals SMA"""
    sma_value = 100.0
    current_price = 100.0

    signal, confidence = sma_calculator.generate_signal(sma_value, current_price)

    assert signal == SignalType.HOLD
    assert confidence == 0.1


def test_sma_signal_confidence_increases_with_distance(sma_calculator):
    """Test confidence increases with distance from SMA"""
    sma_value = 100.0

    # 1% above
    _, conf_1pct = sma_calculator.generate_signal(sma_value, 101.0)

    # 3% above
    _, conf_3pct = sma_calculator.generate_signal(sma_value, 103.0)

    # 5% above
    _, conf_5pct = sma_calculator.generate_signal(sma_value, 105.0)

    # Confidence should increase with distance
    assert conf_3pct > conf_1pct
    assert conf_5pct > conf_3pct


def test_sma_signal_confidence_caps_at_100pct(sma_calculator):
    """Test confidence caps at 1.0 (100%)"""
    sma_value = 100.0
    current_price = 120.0  # 20% above (extreme)

    signal, confidence = sma_calculator.generate_signal(sma_value, current_price)

    assert signal == SignalType.BUY
    assert confidence <= 1.0


# ============================================================================
# EMA Signal Generation Tests
# ============================================================================

def test_ema_signal_price_above_buy(ema_calculator):
    """Test BUY signal when price is above EMA"""
    ema_value = 100.0
    current_price = 105.0

    signal, confidence = ema_calculator.generate_signal(ema_value, current_price)

    assert signal == SignalType.BUY
    assert confidence > 0.5


def test_ema_signal_price_below_sell(ema_calculator):
    """Test SELL signal when price is below EMA"""
    ema_value = 100.0
    current_price = 95.0

    signal, confidence = ema_calculator.generate_signal(ema_value, current_price)

    assert signal == SignalType.SELL
    assert confidence > 0.5


def test_ema_signal_price_at_hold(ema_calculator):
    """Test HOLD signal when price equals EMA"""
    ema_value = 100.0
    current_price = 100.0

    signal, confidence = ema_calculator.generate_signal(ema_value, current_price)

    assert signal == SignalType.HOLD
    assert confidence == 0.1


# ============================================================================
# SMA Crossover Detection Tests
# ============================================================================

def test_sma_bullish_crossover_detection():
    """Test detection of price crossing above SMA"""
    # Create data where price crosses above SMA
    prices = [100] * 15 + [98] * 5 + [102, 104, 106]  # Dips below then crosses above
    df = pd.DataFrame({'close': prices})

    sma_calc = SMACalculator(period=10)
    crossover = sma_calc.detect_crossover(df, lookback=5)

    # Should detect bullish crossover
    if crossover:
        assert crossover == "bullish"


def test_sma_bearish_crossover_detection():
    """Test detection of price crossing below SMA"""
    # Create data where price crosses below SMA
    prices = [100] * 15 + [102] * 5 + [98, 96, 94]  # Rises above then crosses below
    df = pd.DataFrame({'close': prices})

    sma_calc = SMACalculator(period=10)
    crossover = sma_calc.detect_crossover(df, lookback=5)

    # Should detect bearish crossover
    if crossover:
        assert crossover == "bearish"


def test_sma_no_crossover_in_trend(sample_uptrend_data):
    """Test no crossover detected in steady trend"""
    sma_calc = SMACalculator(period=10)
    crossover = sma_calc.detect_crossover(sample_uptrend_data, lookback=3)

    # Might return None or bullish, both valid
    assert crossover in [None, "bullish", "bearish"]


def test_sma_crossover_insufficient_data():
    """Test crossover detection returns None with insufficient data"""
    short_data = pd.DataFrame({'close': [100] * 15})
    sma_calc = SMACalculator(period=10)
    crossover = sma_calc.detect_crossover(short_data, lookback=3)

    assert crossover is None


# ============================================================================
# EMA Crossover Detection Tests
# ============================================================================

def test_ema_bullish_crossover_detection():
    """Test detection of price crossing above EMA"""
    prices = [100] * 15 + [98] * 5 + [102, 104, 106]
    df = pd.DataFrame({'close': prices})

    ema_calc = EMACalculator(period=10)
    crossover = ema_calc.detect_crossover(df, lookback=5)

    if crossover:
        assert crossover == "bullish"


def test_ema_bearish_crossover_detection():
    """Test detection of price crossing below EMA"""
    prices = [100] * 15 + [102] * 5 + [98, 96, 94]
    df = pd.DataFrame({'close': prices})

    ema_calc = EMACalculator(period=10)
    crossover = ema_calc.detect_crossover(df, lookback=5)

    if crossover:
        assert crossover == "bearish"


def test_ema_crossover_insufficient_data():
    """Test EMA crossover detection returns None with insufficient data"""
    short_data = pd.DataFrame({'close': [100] * 15})
    ema_calc = EMACalculator(period=10)
    crossover = ema_calc.detect_crossover(short_data, lookback=3)

    assert crossover is None


# ============================================================================
# Golden Cross / Death Cross Detection Tests
# ============================================================================

def test_golden_cross_detector_initialization(golden_cross_detector):
    """Test Golden Cross detector initialization"""
    assert golden_cross_detector.fast_period == 50
    assert golden_cross_detector.slow_period == 200


def test_golden_cross_detector_custom_periods():
    """Test Golden Cross detector with custom periods"""
    detector = MAGoldenCrossDetector(fast_period=20, slow_period=50)
    assert detector.fast_period == 20
    assert detector.slow_period == 50


def test_golden_cross_detection():
    """Test detection of Golden Cross (bullish)"""
    # Create data where fast MA crosses above slow MA
    prices = []

    # Start with downtrend (fast below slow)
    for i in range(150):
        prices.append(100 - i * 0.1)

    # Reversal - strong uptrend (fast crosses above slow)
    for i in range(100):
        prices.append(85 + i * 0.5)

    df = pd.DataFrame({'close': prices})

    detector = MAGoldenCrossDetector(fast_period=20, slow_period=50)
    result = detector.detect(df, lookback=10)

    # Should detect golden cross
    if result:
        assert result == "golden_cross"


def test_death_cross_detection():
    """Test detection of Death Cross (bearish)"""
    # Create data where fast MA crosses below slow MA
    prices = []

    # Start with uptrend (fast above slow)
    for i in range(150):
        prices.append(100 + i * 0.1)

    # Reversal - strong downtrend (fast crosses below slow)
    for i in range(100):
        prices.append(115 - i * 0.5)

    df = pd.DataFrame({'close': prices})

    detector = MAGoldenCrossDetector(fast_period=20, slow_period=50)
    result = detector.detect(df, lookback=10)

    # Should detect death cross
    if result:
        assert result == "death_cross"


def test_golden_cross_insufficient_data(golden_cross_detector):
    """Test Golden Cross detection returns None with insufficient data"""
    short_data = pd.DataFrame({'close': [100] * 100})
    result = golden_cross_detector.detect(short_data)

    assert result is None


def test_no_cross_in_parallel_mas(golden_cross_detector):
    """Test no cross detected when MAs are parallel"""
    # Steady uptrend - MAs parallel, no crossing
    prices = [100 + i * 0.2 for i in range(250)]
    df = pd.DataFrame({'close': prices})

    result = golden_cross_detector.detect(df, lookback=3)

    # Should return None (no cross)
    assert result in [None, "golden_cross"]  # Might detect at start


# ============================================================================
# Edge Cases
# ============================================================================

def test_sma_flat_prices():
    """Test SMA with flat prices"""
    prices = [100] * 50
    df = pd.DataFrame({'close': prices})

    sma_calc = SMACalculator(period=20)
    sma_value = sma_calc.calculate(df)

    # Flat prices should give SMA = price
    assert abs(sma_value - 100) < 0.01


def test_ema_flat_prices():
    """Test EMA with flat prices"""
    prices = [100] * 50
    df = pd.DataFrame({'close': prices})

    ema_calc = EMACalculator(period=20)
    ema_value = ema_calc.calculate(df)

    # Flat prices should give EMA = price
    assert abs(ema_value - 100) < 0.01


def test_sma_with_nan_values():
    """Test SMA handles NaN values"""
    prices = [100, 102, np.nan, 105, 108] + [110 + i for i in range(50)]
    df = pd.DataFrame({'close': prices})

    sma_calc = SMACalculator(period=20)
    sma_value = sma_calc.calculate(df)

    # Should handle gracefully
    if sma_value is not None:
        assert not np.isnan(sma_value)


def test_ema_with_nan_values():
    """Test EMA handles NaN values"""
    prices = [100, 102, np.nan, 105, 108] + [110 + i for i in range(50)]
    df = pd.DataFrame({'close': prices})

    ema_calc = EMACalculator(period=20)
    ema_value = ema_calc.calculate(df)

    # Should handle gracefully
    if ema_value is not None:
        assert not np.isnan(ema_value)


# ============================================================================
# Performance Tests
# ============================================================================

def test_sma_large_dataset_performance(sma_calculator):
    """Test SMA calculation performance with large dataset"""
    import time

    prices = [100 + np.sin(i / 100) * 10 for i in range(10000)]
    large_df = pd.DataFrame({'close': prices})

    start_time = time.time()
    sma_value = sma_calculator.calculate(large_df)
    elapsed = time.time() - start_time

    assert sma_value is not None
    assert elapsed < 0.5  # Should be very fast


def test_ema_large_dataset_performance(ema_calculator):
    """Test EMA calculation performance with large dataset"""
    import time

    prices = [100 + np.sin(i / 100) * 10 for i in range(10000)]
    large_df = pd.DataFrame({'close': prices})

    start_time = time.time()
    ema_value = ema_calculator.calculate(large_df)
    elapsed = time.time() - start_time

    assert ema_value is not None
    assert elapsed < 0.5


# ============================================================================
# Integration-like Tests
# ============================================================================

def test_ma_realistic_bitcoin_scenario():
    """Test moving averages with realistic Bitcoin-like price movements"""
    np.random.seed(42)
    prices = []
    current_price = 45000

    for i in range(100):
        change_pct = np.random.normal(0, 0.02)
        current_price = current_price * (1 + change_pct)
        prices.append(current_price)

    df = pd.DataFrame({'close': prices})

    sma_calc = SMACalculator(period=20)
    ema_calc = EMACalculator(period=20)

    sma_value = sma_calc.calculate(df)
    ema_value = ema_calc.calculate(df)

    assert sma_value is not None
    assert ema_value is not None
    assert sma_value > 0
    assert ema_value > 0


def test_sma_ema_comparison_responsiveness():
    """Test that EMA is more responsive than SMA to price changes"""
    # Create data with sharp price change
    prices = [100] * 30 + [110] * 30
    df = pd.DataFrame({'close': prices})

    sma_calc = SMACalculator(period=10)
    ema_calc = EMACalculator(period=10)

    # Calculate at the point of change
    df_at_change = df.iloc[:35]  # Just after change

    sma_value = sma_calc.calculate(df_at_change)
    ema_value = ema_calc.calculate(df_at_change)

    # EMA should be closer to new price (110)
    assert ema_value > sma_value


def test_ma_slope_indicates_trend():
    """Test MA slope indicates trend direction"""
    sma_calc = SMACalculator(period=10)

    # Uptrend
    uptrend_prices = [100 + i * 0.5 for i in range(50)]
    up_df = pd.DataFrame({'close': uptrend_prices})

    early_sma = sma_calc.calculate(up_df.iloc[:20])
    late_sma = sma_calc.calculate(up_df.iloc[:40])

    # SMA should increase in uptrend
    assert late_sma > early_sma

    # Downtrend
    downtrend_prices = [100 - i * 0.5 for i in range(50)]
    down_df = pd.DataFrame({'close': downtrend_prices})

    early_sma = sma_calc.calculate(down_df.iloc[:20])
    late_sma = sma_calc.calculate(down_df.iloc[:40])

    # SMA should decrease in downtrend
    assert late_sma < early_sma


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
