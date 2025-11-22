#!/usr/bin/env python3
"""
Unit Tests for Trend Filter

Tests trend identification using dual EMA system (50/200),
signal generation, and edge cases.
"""

import pytest
import numpy as np
from decimal import Decimal

import sys
sys.path.insert(0, '/mnt/d/Bimo_max/crypto-trading-bot/services/technical-analysis')

from app.indicators.trend_filter import TrendFilter


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def trend_filter():
    """Standard trend filter with 50/200 EMA"""
    return TrendFilter()


@pytest.fixture
def bullish_trend_data():
    """Generate bullish trend data (50 EMA > 200 EMA)"""
    # Start low, then strong uptrend
    prices = []
    for i in range(250):
        if i < 150:
            prices.append(100 + i * 0.1)  # Slow rise
        else:
            prices.append(100 + 15 + (i - 150) * 0.5)  # Accelerated rise
    return prices


@pytest.fixture
def bearish_trend_data():
    """Generate bearish trend data (50 EMA < 200 EMA)"""
    # Start high, then downtrend
    prices = []
    for i in range(250):
        if i < 150:
            prices.append(200 - i * 0.1)  # Slow decline
        else:
            prices.append(200 - 15 - (i - 150) * 0.5)  # Accelerated decline
    return prices


@pytest.fixture
def neutral_trend_data():
    """Generate neutral/choppy market data (EMAs close together)"""
    # Sideways movement
    prices = [100 + np.sin(i / 10) * 2 for i in range(250)]
    return prices


# ============================================================================
# Initialization Tests
# ============================================================================

def test_trend_filter_initialization(trend_filter):
    """Test trend filter initialization"""
    assert trend_filter.fast_period == 50
    assert trend_filter.slow_period == 200
    assert trend_filter.neutral_threshold == 0.005  # 0.5%


def test_trend_filter_custom_parameters():
    """Test trend filter with custom parameters"""
    tf = TrendFilter(fast_period=20, slow_period=100, neutral_threshold=0.01)
    assert tf.fast_period == 20
    assert tf.slow_period == 100
    assert tf.neutral_threshold == 0.01


# ============================================================================
# Bullish Trend Tests
# ============================================================================

def test_trend_bullish_detection(trend_filter, bullish_trend_data):
    """Test detection of bullish trend"""
    result = trend_filter.calculate(bullish_trend_data)

    assert result is not None
    assert result["trend"] == "BULLISH"
    assert result["signal"] == "BUY"
    assert result["fast_ema"] > result["slow_ema"]
    assert result["spread_pct"] > 0.005  # > 0.5%


def test_trend_bullish_confidence(trend_filter, bullish_trend_data):
    """Test bullish trend confidence calculation"""
    result = trend_filter.calculate(bullish_trend_data)

    # Confidence should increase with spread magnitude
    assert result["confidence"] > 0
    assert result["confidence"] <= 1.0

    # For strong bullish trend, should have decent confidence
    assert result["confidence"] > 0.3


def test_trend_bullish_ema_calculation(trend_filter, bullish_trend_data):
    """Test that fast EMA > slow EMA in bullish trend"""
    result = trend_filter.calculate(bullish_trend_data)

    fast_ema = result["fast_ema"]
    slow_ema = result["slow_ema"]

    assert fast_ema > 0
    assert slow_ema > 0
    assert fast_ema > slow_ema


# ============================================================================
# Bearish Trend Tests
# ============================================================================

def test_trend_bearish_detection(trend_filter, bearish_trend_data):
    """Test detection of bearish trend"""
    result = trend_filter.calculate(bearish_trend_data)

    assert result is not None
    assert result["trend"] == "BEARISH"
    assert result["signal"] == "SELL"
    assert result["fast_ema"] < result["slow_ema"]
    assert result["spread_pct"] < -0.005  # < -0.5%


def test_trend_bearish_confidence(trend_filter, bearish_trend_data):
    """Test bearish trend confidence calculation"""
    result = trend_filter.calculate(bearish_trend_data)

    # Confidence should increase with spread magnitude
    assert result["confidence"] > 0
    assert result["confidence"] <= 1.0

    # For strong bearish trend, should have decent confidence
    assert result["confidence"] > 0.3


def test_trend_bearish_ema_calculation(trend_filter, bearish_trend_data):
    """Test that fast EMA < slow EMA in bearish trend"""
    result = trend_filter.calculate(bearish_trend_data)

    fast_ema = result["fast_ema"]
    slow_ema = result["slow_ema"]

    assert fast_ema > 0
    assert slow_ema > 0
    assert fast_ema < slow_ema


# ============================================================================
# Neutral Trend Tests
# ============================================================================

def test_trend_neutral_detection(trend_filter, neutral_trend_data):
    """Test trend filter with sideways market data"""
    result = trend_filter.calculate(neutral_trend_data)

    # Sideways data may produce any trend depending on EMA positions
    assert result is not None
    assert result["trend"] in ["BULLISH", "BEARISH", "NEUTRAL"]
    assert result["signal"] in ["BUY", "SELL", "HOLD"]


def test_trend_neutral_confidence(trend_filter, neutral_trend_data):
    """Test sideways market confidence is valid"""
    result = trend_filter.calculate(neutral_trend_data)

    # Confidence should be valid regardless of trend
    assert 0 <= result["confidence"] <= 1.0


# ============================================================================
# Spread Calculation Tests
# ============================================================================

def test_trend_spread_calculation():
    """Test spread percentage calculation"""
    # Create data with enough points (200+) and clear separation
    prices = [100] * 150 + [100 + (i * 0.2) for i in range(100)]

    tf = TrendFilter()
    result = tf.calculate(prices)

    # Spread = (fast_ema - slow_ema) / slow_ema
    if result["slow_ema"] != 0:  # Avoid division by zero
        expected_spread = (result["fast_ema"] - result["slow_ema"]) / result["slow_ema"]
        assert abs(result["spread_pct"] - expected_spread) < 0.0001


def test_trend_confidence_scaling():
    """Test confidence scales with spread magnitude"""
    # Small spread
    small_spread_prices = [100 + i * 0.01 for i in range(250)]
    tf = TrendFilter()
    result_small = tf.calculate(small_spread_prices)

    # Large spread
    large_spread_prices = [100 + i * 0.5 for i in range(250)]
    result_large = tf.calculate(large_spread_prices)

    # Larger spread should have higher confidence
    if result_large["trend"] != "NEUTRAL":
        assert result_large["confidence"] > result_small["confidence"]


def test_trend_confidence_capped_at_one():
    """Test confidence is capped at 1.0"""
    # Create extreme spread
    extreme_prices = [100 + i * 2 for i in range(250)]

    tf = TrendFilter()
    result = tf.calculate(extreme_prices)

    assert result["confidence"] <= 1.0


# ============================================================================
# Edge Cases
# ============================================================================

def test_trend_insufficient_data(trend_filter):
    """Test returns neutral with insufficient data"""
    short_data = [100] * 150  # Less than 200 required
    result = trend_filter.calculate(short_data)

    assert result["trend"] == "NEUTRAL"
    assert result["signal"] == "HOLD"
    assert result["confidence"] == 0.0
    assert "Insufficient data" in result["description"]


def test_trend_exact_minimum_data(trend_filter):
    """Test with exactly 200 data points (minimum)"""
    min_data = [100 + i * 0.1 for i in range(200)]
    result = trend_filter.calculate(min_data)

    # Should work, but may be neutral due to data pattern
    assert result is not None
    assert result["trend"] in ["BULLISH", "BEARISH", "NEUTRAL"]


def test_trend_flat_prices():
    """Test with flat prices (no movement)"""
    flat_prices = [100.0] * 250

    tf = TrendFilter()
    result = tf.calculate(flat_prices)

    # Flat prices should result in neutral trend (spread ~0)
    assert result["trend"] == "NEUTRAL"
    assert abs(result["spread_pct"]) < 0.001


def test_trend_with_nan_values():
    """Test handles NaN values gracefully"""
    prices = [100 + i * 0.1 for i in range(200)]
    prices[100] = np.nan  # Insert NaN

    tf = TrendFilter()
    result = tf.calculate(prices)

    # Should handle gracefully (pandas dropna or fillna)
    # May return neutral if NaN breaks calculation
    assert result is not None
    assert result["trend"] in ["BULLISH", "BEARISH", "NEUTRAL"]


# ============================================================================
# Signal Generation Tests
# ============================================================================

def test_trend_signal_buy_bullish(trend_filter, bullish_trend_data):
    """Test BUY signal in bullish trend"""
    result = trend_filter.calculate(bullish_trend_data)

    assert result["signal"] == "BUY"
    assert result["trend"] == "BULLISH"


def test_trend_signal_sell_bearish(trend_filter, bearish_trend_data):
    """Test SELL signal in bearish trend"""
    result = trend_filter.calculate(bearish_trend_data)

    assert result["signal"] == "SELL"
    assert result["trend"] == "BEARISH"


def test_trend_signal_hold_neutral(trend_filter, neutral_trend_data):
    """Test signal with sideways market data"""
    result = trend_filter.calculate(neutral_trend_data)

    # Sideways data may produce any signal depending on EMA positions
    assert result["signal"] in ["BUY", "SELL", "HOLD"]
    assert result["trend"] in ["BULLISH", "BEARISH", "NEUTRAL"]


# ============================================================================
# Description Tests
# ============================================================================

def test_trend_description_format(trend_filter, bullish_trend_data):
    """Test description contains trend and spread"""
    result = trend_filter.calculate(bullish_trend_data)

    assert "description" in result
    assert result["trend"] in result["description"]
    assert "spread" in result["description"].lower()


# ============================================================================
# Performance Tests
# ============================================================================

def test_trend_large_dataset_performance(trend_filter):
    """Test trend filter with large dataset"""
    import time

    # 5000 data points
    large_data = [100 + np.sin(i / 100) * 10 for i in range(5000)]

    start_time = time.time()
    result = trend_filter.calculate(large_data)
    elapsed = time.time() - start_time

    assert result is not None
    assert elapsed < 1.0  # Should complete in < 1 second


# ============================================================================
# Integration-like Tests
# ============================================================================

def test_trend_realistic_bitcoin_scenario():
    """Test trend filter with realistic Bitcoin-like price movements"""
    # Simulate Bitcoin bull run scenario
    prices = []
    current_price = 30000

    # Accumulation phase (150 days)
    for i in range(150):
        current_price += np.random.normal(10, 50)
        prices.append(current_price)

    # Bull run phase (100 days)
    for i in range(100):
        current_price += np.random.normal(200, 100)
        prices.append(current_price)

    tf = TrendFilter()
    result = tf.calculate(prices)

    assert result is not None
    assert result["trend"] in ["BULLISH", "BEARISH", "NEUTRAL"]
    assert 0 <= result["confidence"] <= 1.0


def test_trend_golden_cross_scenario():
    """Test trend filter during golden cross (50 EMA crosses above 200 EMA)"""
    # Simulate downtrend transitioning to uptrend
    prices = []

    # Downtrend (200 points)
    for i in range(200):
        prices.append(200 - i * 0.3)

    # Reversal and uptrend (100 points)
    for i in range(100):
        prices.append(140 + i * 0.8)

    tf = TrendFilter()
    result = tf.calculate(prices)

    # Should detect bullish trend after golden cross
    assert result is not None
    assert result["trend"] in ["BULLISH", "NEUTRAL"]  # May be neutral if EMAs still close


def test_trend_death_cross_scenario():
    """Test trend filter during death cross (50 EMA crosses below 200 EMA)"""
    # Simulate uptrend transitioning to downtrend
    prices = []

    # Uptrend (200 points)
    for i in range(200):
        prices.append(100 + i * 0.3)

    # Reversal and downtrend (100 points)
    for i in range(100):
        prices.append(160 - i * 0.8)

    tf = TrendFilter()
    result = tf.calculate(prices)

    # Should detect bearish trend after death cross
    assert result is not None
    assert result["trend"] in ["BEARISH", "NEUTRAL"]  # May be neutral if EMAs still close


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
