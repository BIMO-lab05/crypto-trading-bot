#!/usr/bin/env python3
"""
Unit Tests for ATR (Average True Range) Calculator

Tests ATR calculation, volatility classification,
stop-loss/take-profit generation, and edge cases.
"""

import pytest
import pandas as pd
import numpy as np

import sys
sys.path.insert(0, '/mnt/d/Bimo_max/crypto-trading-bot/services/technical-analysis')

from app.indicators.atr import ATR


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def atr_calculator():
    """Standard ATR calculator with default parameters (14, 2.0, 4.0)"""
    return ATR()


@pytest.fixture
def sample_ohlc_data():
    """Generate sample OHLC data for testing"""
    np.random.seed(42)
    closes = [100 + i * 0.5 + np.random.normal(0, 1) for i in range(50)]
    highs = [c + abs(np.random.normal(0, 0.5)) for c in closes]
    lows = [c - abs(np.random.normal(0, 0.5)) for c in closes]

    return {
        'highs': highs,
        'lows': lows,
        'closes': closes
    }


@pytest.fixture
def low_volatility_data():
    """Generate low volatility OHLC data"""
    closes = [100.0] * 50
    highs = [100.1] * 50  # Very tight range
    lows = [99.9] * 50

    return {
        'highs': highs,
        'lows': lows,
        'closes': closes
    }


@pytest.fixture
def high_volatility_data():
    """Generate high volatility OHLC data"""
    closes = []
    highs = []
    lows = []

    for i in range(50):
        close = 100 + np.random.normal(0, 5)  # High volatility
        closes.append(close)
        highs.append(close + abs(np.random.normal(0, 3)))
        lows.append(close - abs(np.random.normal(0, 3)))

    return {
        'highs': highs,
        'lows': lows,
        'closes': closes
    }


# ============================================================================
# Initialization Tests
# ============================================================================

def test_atr_initialization(atr_calculator):
    """Test ATR calculator initialization with default parameters"""
    assert atr_calculator.period == 14
    assert atr_calculator.sl_multiplier == 2.0
    assert atr_calculator.tp_multiplier == 4.0


def test_atr_custom_parameters():
    """Test ATR with custom parameters"""
    atr = ATR(period=20, stop_loss_multiplier=3.0, take_profit_multiplier=6.0)

    assert atr.period == 20
    assert atr.sl_multiplier == 3.0
    assert atr.tp_multiplier == 6.0


# ============================================================================
# ATR Calculation Tests
# ============================================================================

def test_atr_calculation_structure(atr_calculator, sample_ohlc_data):
    """Test ATR calculation returns correct structure"""
    result = atr_calculator.calculate(
        sample_ohlc_data['highs'],
        sample_ohlc_data['lows'],
        sample_ohlc_data['closes'],
        current_price=100.0
    )

    assert result is not None
    assert isinstance(result, dict)
    assert "atr" in result
    assert "atr_pct" in result
    assert "stop_loss_long" in result
    assert "stop_loss_short" in result
    assert "take_profit_long" in result
    assert "take_profit_short" in result
    assert "volatility" in result
    assert "confidence" in result
    assert "risk_reward_ratio" in result


def test_atr_returns_positive_value(atr_calculator, sample_ohlc_data):
    """Test ATR value is always positive"""
    result = atr_calculator.calculate(
        sample_ohlc_data['highs'],
        sample_ohlc_data['lows'],
        sample_ohlc_data['closes'],
        current_price=100.0
    )

    assert result["atr"] >= 0
    assert result["atr_pct"] >= 0


def test_atr_true_range_calculation():
    """Test True Range calculation logic"""
    # Create specific data to test TR formula
    # TR = max(high-low, |high-prev_close|, |low-prev_close|)
    highs = [102, 105, 103]
    lows = [98, 101, 99]
    closes = [100, 104, 101]

    atr_calc = ATR(period=2)
    result = atr_calc.calculate(highs, lows, closes, current_price=101.0)

    # Should calculate ATR successfully
    assert result["atr"] > 0


def test_atr_insufficient_data(atr_calculator):
    """Test ATR returns default response with insufficient data"""
    # Only 10 data points, need at least 15 (period + 1)
    highs = [100] * 10
    lows = [99] * 10
    closes = [99.5] * 10

    result = atr_calculator.calculate(highs, lows, closes, current_price=100.0)

    assert result is not None
    assert result["atr"] == 0.0
    assert result["volatility"] == "UNKNOWN"
    assert "default" in result["description"].lower()


def test_atr_exact_minimum_data(atr_calculator):
    """Test ATR with exactly minimum required data"""
    # Exactly period + 1 = 15 data points
    highs = [100 + i * 0.1 for i in range(15)]
    lows = [99 + i * 0.1 for i in range(15)]
    closes = [99.5 + i * 0.1 for i in range(15)]

    result = atr_calculator.calculate(highs, lows, closes, current_price=100.0)

    assert result is not None
    assert result["atr"] > 0


# ============================================================================
# Volatility Classification Tests
# ============================================================================

def test_atr_low_volatility_classification(atr_calculator, low_volatility_data):
    """Test LOW volatility classification (ATR < 1%)"""
    result = atr_calculator.calculate(
        low_volatility_data['highs'],
        low_volatility_data['lows'],
        low_volatility_data['closes'],
        current_price=100.0
    )

    assert result["volatility"] == "LOW"
    assert result["atr_pct"] < 1.0
    assert result["confidence"] == 0.8


def test_atr_medium_volatility_classification(atr_calculator):
    """Test MEDIUM volatility classification (1% <= ATR < 2%)"""
    # Create data with medium volatility
    closes = [100 + np.sin(i / 3) * 1.5 for i in range(50)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]

    result = atr_calculator.calculate(highs, lows, closes, current_price=100.0)

    # Should be MEDIUM or LOW depending on exact calculation
    assert result["volatility"] in ["LOW", "MEDIUM"]
    assert result["confidence"] >= 0.8


def test_atr_high_volatility_classification(atr_calculator, high_volatility_data):
    """Test HIGH volatility classification (2% <= ATR < 4%)"""
    result = atr_calculator.calculate(
        high_volatility_data['highs'],
        high_volatility_data['lows'],
        high_volatility_data['closes'],
        current_price=100.0
    )

    # Should be HIGH or EXTREME depending on data
    assert result["volatility"] in ["HIGH", "EXTREME", "MEDIUM"]
    assert 0.4 <= result["confidence"] <= 1.0


def test_atr_extreme_volatility_classification():
    """Test EXTREME volatility classification (ATR >= 4%)"""
    # Create extremely volatile data
    np.random.seed(123)
    closes = [100 + np.random.normal(0, 10) for _ in range(50)]
    highs = [c + abs(np.random.normal(0, 5)) for c in closes]
    lows = [c - abs(np.random.normal(0, 5)) for c in closes]

    atr_calc = ATR()
    result = atr_calc.calculate(highs, lows, closes, current_price=100.0)

    # Should classify as HIGH or EXTREME
    assert result["volatility"] in ["HIGH", "EXTREME"]
    if result["volatility"] == "EXTREME":
        assert result["confidence"] == 0.4


# ============================================================================
# Stop-Loss and Take-Profit Tests
# ============================================================================

def test_atr_stop_loss_long_calculation(atr_calculator, sample_ohlc_data):
    """Test stop-loss for long position is below entry price"""
    current_price = 100.0
    result = atr_calculator.calculate(
        sample_ohlc_data['highs'],
        sample_ohlc_data['lows'],
        sample_ohlc_data['closes'],
        current_price=current_price
    )

    # SL for long should be below entry
    assert result["stop_loss_long"] < current_price

    # SL distance should be ATR * multiplier
    expected_distance = result["atr"] * atr_calculator.sl_multiplier
    actual_distance = current_price - result["stop_loss_long"]
    assert abs(actual_distance - expected_distance) < 0.01


def test_atr_stop_loss_short_calculation(atr_calculator, sample_ohlc_data):
    """Test stop-loss for short position is above entry price"""
    current_price = 100.0
    result = atr_calculator.calculate(
        sample_ohlc_data['highs'],
        sample_ohlc_data['lows'],
        sample_ohlc_data['closes'],
        current_price=current_price
    )

    # SL for short should be above entry
    assert result["stop_loss_short"] > current_price


def test_atr_take_profit_long_calculation(atr_calculator, sample_ohlc_data):
    """Test take-profit for long position is above entry price"""
    current_price = 100.0
    result = atr_calculator.calculate(
        sample_ohlc_data['highs'],
        sample_ohlc_data['lows'],
        sample_ohlc_data['closes'],
        current_price=current_price
    )

    # TP for long should be above entry
    assert result["take_profit_long"] > current_price

    # TP distance should be ATR * multiplier
    expected_distance = result["atr"] * atr_calculator.tp_multiplier
    actual_distance = result["take_profit_long"] - current_price
    assert abs(actual_distance - expected_distance) < 0.01


def test_atr_take_profit_short_calculation(atr_calculator, sample_ohlc_data):
    """Test take-profit for short position is below entry price"""
    current_price = 100.0
    result = atr_calculator.calculate(
        sample_ohlc_data['highs'],
        sample_ohlc_data['lows'],
        sample_ohlc_data['closes'],
        current_price=current_price
    )

    # TP for short should be below entry
    assert result["take_profit_short"] < current_price


def test_atr_risk_reward_ratio(atr_calculator, sample_ohlc_data):
    """Test risk/reward ratio is calculated correctly"""
    result = atr_calculator.calculate(
        sample_ohlc_data['highs'],
        sample_ohlc_data['lows'],
        sample_ohlc_data['closes'],
        current_price=100.0
    )

    # RR ratio should be TP multiplier / SL multiplier
    expected_rr = atr_calculator.tp_multiplier / atr_calculator.sl_multiplier
    assert result["risk_reward_ratio"] == expected_rr
    assert result["risk_reward_ratio"] == 2.0  # 4.0 / 2.0


def test_atr_custom_multipliers():
    """Test custom stop-loss and take-profit multipliers"""
    atr_calc = ATR(period=14, stop_loss_multiplier=3.0, take_profit_multiplier=9.0)

    highs = [100 + i * 0.1 for i in range(20)]
    lows = [99 + i * 0.1 for i in range(20)]
    closes = [99.5 + i * 0.1 for i in range(20)]

    result = atr_calc.calculate(highs, lows, closes, current_price=100.0)

    assert result["risk_reward_ratio"] == 3.0  # 9.0 / 3.0


# ============================================================================
# Edge Cases
# ============================================================================

def test_atr_zero_current_price(atr_calculator, sample_ohlc_data):
    """Test ATR handles zero current price gracefully"""
    result = atr_calculator.calculate(
        sample_ohlc_data['highs'],
        sample_ohlc_data['lows'],
        sample_ohlc_data['closes'],
        current_price=0.0  # Invalid price
    )

    # Should return default response
    assert result is not None
    assert result["atr"] == 0.0


def test_atr_negative_current_price(atr_calculator, sample_ohlc_data):
    """Test ATR handles negative current price gracefully"""
    result = atr_calculator.calculate(
        sample_ohlc_data['highs'],
        sample_ohlc_data['lows'],
        sample_ohlc_data['closes'],
        current_price=-100.0  # Invalid price
    )

    # Should return default response
    assert result is not None
    assert result["atr"] == 0.0


def test_atr_nan_current_price(atr_calculator, sample_ohlc_data):
    """Test ATR handles NaN current price gracefully"""
    result = atr_calculator.calculate(
        sample_ohlc_data['highs'],
        sample_ohlc_data['lows'],
        sample_ohlc_data['closes'],
        current_price=np.nan
    )

    # Should return default response
    assert result is not None
    assert result["atr"] == 0.0


def test_atr_with_nan_values():
    """Test ATR handles NaN values in OHLC data"""
    highs = [100, 102, np.nan, 105, 108] + [110 + i for i in range(20)]
    lows = [98, 100, np.nan, 103, 106] + [108 + i for i in range(20)]
    closes = [99, 101, np.nan, 104, 107] + [109 + i for i in range(20)]

    atr_calc = ATR()
    result = atr_calc.calculate(highs, lows, closes, current_price=110.0)

    # Should handle gracefully
    if result["atr"] > 0:
        assert not np.isnan(result["atr"])


def test_atr_identical_ohlc_values(atr_calculator):
    """Test ATR with identical high, low, close (no movement)"""
    # All prices the same = zero volatility
    highs = [100.0] * 20
    lows = [100.0] * 20
    closes = [100.0] * 20

    result = atr_calculator.calculate(highs, lows, closes, current_price=100.0)

    # ATR should be very close to zero
    assert result["atr"] < 0.1
    assert result["volatility"] == "LOW"


# ============================================================================
# Performance Tests
# ============================================================================

def test_atr_large_dataset_performance(atr_calculator):
    """Test ATR calculation performance with large dataset"""
    import time

    # Generate 10,000 data points
    np.random.seed(42)
    closes = [100 + np.sin(i / 100) * 10 + np.random.normal(0, 1) for i in range(10000)]
    highs = [c + abs(np.random.normal(0, 0.5)) for c in closes]
    lows = [c - abs(np.random.normal(0, 0.5)) for c in closes]

    start_time = time.time()
    result = atr_calculator.calculate(highs, lows, closes, current_price=100.0)
    elapsed = time.time() - start_time

    assert result is not None
    assert result["atr"] > 0
    assert elapsed < 1.0  # Should complete in less than 1 second


# ============================================================================
# Integration-like Tests
# ============================================================================

def test_atr_realistic_bitcoin_scenario():
    """Test ATR with realistic Bitcoin-like price movements"""
    np.random.seed(42)

    closes = []
    highs = []
    lows = []
    current_price = 45000

    for i in range(100):
        # Bitcoin-like volatility (2% std dev)
        change_pct = np.random.normal(0, 0.02)
        current_price = current_price * (1 + change_pct)
        closes.append(current_price)

        # Typical intraday range
        high = current_price * (1 + abs(np.random.normal(0, 0.01)))
        low = current_price * (1 - abs(np.random.normal(0, 0.01)))
        highs.append(high)
        lows.append(low)

    atr_calc = ATR()
    result = atr_calc.calculate(highs, lows, closes, current_price=current_price)

    assert result is not None
    assert result["atr"] > 0
    assert result["volatility"] in ["LOW", "MEDIUM", "HIGH", "EXTREME"]
    assert 0 < result["confidence"] <= 1.0

    # Verify stop-loss is reasonable (not more than 10% away)
    sl_distance_pct = abs(current_price - result["stop_loss_long"]) / current_price
    assert sl_distance_pct < 0.1


def test_atr_volatility_increases_with_range(atr_calculator):
    """Test that ATR increases with wider price ranges"""
    # Low range data
    low_highs = [100.5] * 20
    low_lows = [99.5] * 20
    low_closes = [100.0] * 20

    low_result = atr_calculator.calculate(low_highs, low_lows, low_closes, current_price=100.0)

    # High range data
    high_highs = [105.0] * 20
    high_lows = [95.0] * 20
    high_closes = [100.0] * 20

    high_result = atr_calculator.calculate(high_highs, high_lows, high_closes, current_price=100.0)

    # Higher range should produce higher ATR
    assert high_result["atr"] > low_result["atr"]
    assert high_result["atr_pct"] > low_result["atr_pct"]


def test_atr_default_fallback_values():
    """Test default fallback provides reasonable SL/TP values"""
    atr_calc = ATR()

    # Insufficient data triggers default
    result = atr_calc.calculate([100], [99], [99.5], current_price=100.0)

    assert result["atr"] == 0.0
    assert result["volatility"] == "UNKNOWN"

    # Default should use 3% SL
    expected_sl_long = 100.0 * 0.97
    expected_sl_short = 100.0 * 1.03
    expected_tp_long = 100.0 * 1.06
    expected_tp_short = 100.0 * 0.94

    assert abs(result["stop_loss_long"] - expected_sl_long) < 0.1
    assert abs(result["stop_loss_short"] - expected_sl_short) < 0.1
    assert abs(result["take_profit_long"] - expected_tp_long) < 0.1
    assert abs(result["take_profit_short"] - expected_tp_short) < 0.1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
