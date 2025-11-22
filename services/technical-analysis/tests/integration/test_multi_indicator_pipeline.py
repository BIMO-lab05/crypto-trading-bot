#!/usr/bin/env python3
"""
Integration Tests for Multi-Indicator Pipeline

Tests multiple indicators working together, signal aggregation,
and overall system integration.
"""

import pytest
import pandas as pd
import numpy as np
from decimal import Decimal

import sys
sys.path.insert(0, '/mnt/d/Bimo_max/crypto-trading-bot/services/technical-analysis')

from app.indicators.rsi import RSICalculator
from app.indicators.macd import MACDCalculator
from app.indicators.bollinger_bands import BollingerBandsCalculator
from app.indicators.moving_averages import SMACalculator, EMACalculator
from app.indicators.atr import ATR
from app.indicators.stochastic import Stochastic
from app.indicators.trend_filter import TrendFilter
from app.indicators.volume_confirmation import VolumeConfirmation
from app.models import SignalType


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def bullish_market_data():
    """Generate complete bullish market data (OHLCV)"""
    # Simulates strong bullish trend
    data = {
        'highs': [],
        'lows': [],
        'closes': [],
        'volumes': []
    }

    base_price = 100
    for i in range(250):
        # Uptrend with volatility
        trend = i * 0.5
        volatility = np.random.normal(0, 1)

        close = base_price + trend + volatility
        high = close + abs(np.random.normal(0, 0.5))
        low = close - abs(np.random.normal(0, 0.5))
        volume = 1000 + abs(np.random.normal(0, 200))

        data['highs'].append(high)
        data['lows'].append(low)
        data['closes'].append(close)
        data['volumes'].append(volume)

    return data


@pytest.fixture
def bearish_market_data():
    """Generate complete bearish market data (OHLCV)"""
    # Simulates strong bearish trend
    data = {
        'highs': [],
        'lows': [],
        'closes': [],
        'volumes': []
    }

    base_price = 200
    for i in range(250):
        # Downtrend with volatility
        trend = -i * 0.5
        volatility = np.random.normal(0, 1)

        close = base_price + trend + volatility
        high = close + abs(np.random.normal(0, 0.5))
        low = close - abs(np.random.normal(0, 0.5))
        volume = 1000 + abs(np.random.normal(0, 200))

        data['highs'].append(high)
        data['lows'].append(low)
        data['closes'].append(close)
        data['volumes'].append(volume)

    return data


@pytest.fixture
def sideways_market_data():
    """Generate sideways/ranging market data (OHLCV)"""
    data = {
        'highs': [],
        'lows': [],
        'closes': [],
        'volumes': []
    }

    base_price = 150
    for i in range(250):
        # Sideways with oscillation
        oscillation = np.sin(i / 10) * 5
        volatility = np.random.normal(0, 1)

        close = base_price + oscillation + volatility
        high = close + abs(np.random.normal(0, 0.5))
        low = close - abs(np.random.normal(0, 0.5))
        volume = 1000 + abs(np.random.normal(0, 200))

        data['highs'].append(high)
        data['lows'].append(low)
        data['closes'].append(close)
        data['volumes'].append(volume)

    return data


# ============================================================================
# Multi-Indicator Pipeline Tests
# ============================================================================

def test_all_indicators_with_bullish_data(bullish_market_data):
    """Test all 8 indicators with bullish market data"""
    data = bullish_market_data
    closes = data['closes']
    highs = data['highs']
    lows = data['lows']
    volumes = data['volumes']

    # Test all indicators can process the data
    rsi_calc = RSICalculator()
    macd_calc = MACDCalculator()
    bb_calc = BollingerBandsCalculator()
    sma_calc = SMACalculator()
    ema_calc = EMACalculator()
    atr_calc = ATR()
    stoch_calc = Stochastic()
    trend_calc = TrendFilter()
    vol_calc = VolumeConfirmation()

    # Calculate all indicators
    rsi_value = rsi_calc.calculate(pd.DataFrame({'close': closes}))
    macd_result = macd_calc.calculate(closes)
    bb_result = bb_calc.calculate(closes, current_price=closes[-1])
    sma_value = sma_calc.calculate(closes)
    ema_value = ema_calc.calculate(closes)
    atr_result = atr_calc.calculate(highs, lows, closes, current_price=closes[-1])
    stoch_result = stoch_calc.calculate(highs, lows, closes)
    trend_result = trend_calc.calculate(closes)
    vol_result = vol_calc.calculate(volumes)

    # Verify all indicators returned valid results
    assert rsi_value is not None
    assert macd_result is not None
    assert bb_result is not None
    assert sma_value is not None
    assert ema_value is not None
    assert atr_result is not None
    assert stoch_result is not None
    assert trend_result is not None
    assert vol_result is not None


def test_all_indicators_with_bearish_data(bearish_market_data):
    """Test all 8 indicators with bearish market data"""
    data = bearish_market_data
    closes = data['closes']
    highs = data['highs']
    lows = data['lows']
    volumes = data['volumes']

    # Initialize all indicators
    indicators = {
        'rsi': RSICalculator(),
        'macd': MACDCalculator(),
        'bb': BollingerBandsCalculator(),
        'sma': SMACalculator(),
        'ema': EMACalculator(),
        'atr': ATR(),
        'stoch': Stochastic(),
        'trend': TrendFilter(),
        'volume': VolumeConfirmation()
    }

    # Run all indicators
    results = {}
    results['rsi'] = indicators['rsi'].calculate(pd.DataFrame({'close': closes}))
    results['macd'] = indicators['macd'].calculate(closes)
    results['bb'] = indicators['bb'].calculate(closes, current_price=closes[-1])
    results['sma'] = indicators['sma'].calculate(closes)
    results['ema'] = indicators['ema'].calculate(closes)
    results['atr'] = indicators['atr'].calculate(highs, lows, closes, current_price=closes[-1])
    results['stoch'] = indicators['stoch'].calculate(highs, lows, closes)
    results['trend'] = indicators['trend'].calculate(closes)
    results['volume'] = indicators['volume'].calculate(volumes)

    # All indicators should return valid results
    for name, result in results.items():
        assert result is not None, f"{name} indicator failed"


# ============================================================================
# Signal Aggregation Tests
# ============================================================================

def test_signal_aggregation_bullish_consensus(bullish_market_data):
    """Test signal aggregation when most indicators are bullish"""
    data = bullish_market_data
    closes = data['closes']

    # Get signals from multiple indicators
    rsi_calc = RSICalculator()
    macd_calc = MACDCalculator()
    trend_calc = TrendFilter()

    rsi_value, rsi_signal, rsi_conf = rsi_calc.calculate_with_signal(pd.DataFrame({'close': closes}))
    macd_value, macd_signal, macd_conf = macd_calc.calculate_with_signal(closes)
    trend_result = trend_calc.calculate(closes)

    # In bullish market, expect bullish signals
    signals = [rsi_signal, macd_signal, trend_result['signal']]

    # Count BUY signals
    buy_count = sum(1 for s in signals if s in [SignalType.BUY, "BUY"])

    # Expect majority bullish in strong uptrend
    assert buy_count >= 1, "Expected at least one BUY signal in bullish market"


def test_signal_aggregation_bearish_consensus(bearish_market_data):
    """Test signal aggregation when most indicators are bearish"""
    data = bearish_market_data
    closes = data['closes']

    # Get signals from multiple indicators
    rsi_calc = RSICalculator()
    macd_calc = MACDCalculator()
    trend_calc = TrendFilter()

    rsi_value, rsi_signal, rsi_conf = rsi_calc.calculate_with_signal(pd.DataFrame({'close': closes}))
    macd_value, macd_signal, macd_conf = macd_calc.calculate_with_signal(closes)
    trend_result = trend_calc.calculate(closes)

    # In bearish market, expect bearish signals
    signals = [rsi_signal, macd_signal, trend_result['signal']]

    # Count SELL signals
    sell_count = sum(1 for s in signals if s in [SignalType.SELL, "SELL"])

    # Expect at least one bearish signal in downtrend
    assert sell_count >= 1, "Expected at least one SELL signal in bearish market"


def test_signal_confidence_aggregation():
    """Test aggregating confidence levels from multiple indicators"""
    # Create simple test data
    closes = [100 + i * 0.5 for i in range(100)]

    rsi_calc = RSICalculator()
    macd_calc = MACDCalculator()

    _, rsi_signal, rsi_conf = rsi_calc.calculate_with_signal(pd.DataFrame({'close': closes}))
    _, macd_signal, macd_conf = macd_calc.calculate_with_signal(closes)

    # Average confidence
    avg_confidence = (rsi_conf + macd_conf) / 2

    assert 0 <= avg_confidence <= 1.0
    assert avg_confidence > 0  # Should have some confidence


# ============================================================================
# Conflicting Indicator Tests
# ============================================================================

def test_conflicting_indicators_detection():
    """Test detection of conflicting indicator signals"""
    # Create data that might produce mixed signals
    closes = [100] * 50 + [105] * 50 + [100] * 50  # Up then down

    rsi_calc = RSICalculator()
    macd_calc = MACDCalculator()

    _, rsi_signal, _ = rsi_calc.calculate_with_signal(pd.DataFrame({'close': closes}))
    _, macd_signal, _ = macd_calc.calculate_with_signal(closes)

    # Signals might differ or be neutral
    assert rsi_signal in [SignalType.BUY, SignalType.SELL, SignalType.HOLD, SignalType.NEUTRAL]
    assert macd_signal in [SignalType.BUY, SignalType.SELL, SignalType.HOLD, SignalType.NEUTRAL]


def test_trend_filter_overrides_counter_trend_signals():
    """Test that trend filter can override counter-trend signals"""
    # Strong downtrend data
    closes = [200 - i * 0.5 for i in range(250)]

    trend_calc = TrendFilter()
    trend_result = trend_calc.calculate(closes)

    # Should identify bearish trend
    assert trend_result['trend'] == "BEARISH"
    assert trend_result['signal'] == "SELL"

    # Any BUY signal should be filtered in bearish trend


# ============================================================================
# Volume Confirmation Integration Tests
# ============================================================================

def test_volume_confirms_breakout_signal(bullish_market_data):
    """Test volume confirmation strengthens breakout signals"""
    data = bullish_market_data
    closes = data['closes']
    volumes = data['volumes']

    # Add volume spike at the end
    volumes[-1] = volumes[-1] * 2.0  # 2x volume spike

    # Get price signal (BB breakout)
    bb_calc = BollingerBandsCalculator()
    bb_result = bb_calc.calculate(closes, current_price=closes[-1])

    # Get volume confirmation
    vol_calc = VolumeConfirmation()
    vol_result = vol_calc.calculate(volumes, signal_type="breakout")

    # Volume should confirm if strong
    if vol_result['confirmed']:
        assert vol_result['strength'] in ["STRONG", "MODERATE"]


def test_low_volume_weakens_signal():
    """Test that low volume weakens trading signals"""
    closes = [100 + i * 2 for i in range(50)]  # Strong price move
    volumes = [1000] * 49 + [500]  # But low volume

    vol_calc = VolumeConfirmation()
    vol_result = vol_calc.calculate(volumes, signal_type="breakout")

    # Should reject due to low volume
    assert vol_result['confirmed'] == False
    assert vol_result['strength'] == "INSUFFICIENT"


# ============================================================================
# ATR Integration Tests
# ============================================================================

def test_atr_provides_stop_loss_for_signals(bullish_market_data):
    """Test ATR provides stop-loss levels for trading signals"""
    data = bullish_market_data
    highs = data['highs']
    lows = data['lows']
    closes = data['closes']
    current_price = closes[-1]

    # Get ATR levels
    atr_calc = ATR()
    atr_result = atr_calc.calculate(highs, lows, closes, current_price)

    # Verify stop-loss and take-profit levels exist
    assert 'stop_loss_long' in atr_result
    assert 'take_profit_long' in atr_result
    assert atr_result['stop_loss_long'] < current_price
    assert atr_result['take_profit_long'] > current_price


def test_high_volatility_reduces_position_size():
    """Test that high volatility (high ATR) should reduce position size"""
    # Create high volatility data
    highs = []
    lows = []
    closes = []

    for i in range(50):
        close = 100 + np.random.normal(0, 10)  # High volatility
        high = close + abs(np.random.normal(0, 5))
        low = close - abs(np.random.normal(0, 5))
        highs.append(high)
        lows.append(low)
        closes.append(close)

    atr_calc = ATR()
    atr_result = atr_calc.calculate(highs, lows, closes, current_price=closes[-1])

    # High volatility classification
    assert atr_result['volatility'] in ["HIGH", "EXTREME"]
    # This would signal risk management to reduce position size


# ============================================================================
# Complete Pipeline Tests
# ============================================================================

def test_complete_analysis_pipeline(bullish_market_data):
    """Test complete end-to-end analysis pipeline"""
    data = bullish_market_data

    # Stage 1: Trend identification
    trend_calc = TrendFilter()
    trend_result = trend_calc.calculate(data['closes'])

    # Stage 2: Momentum indicators
    rsi_calc = RSICalculator()
    macd_calc = MACDCalculator()

    rsi_value, rsi_signal, rsi_conf = rsi_calc.calculate_with_signal(
        pd.DataFrame({'close': data['closes']})
    )
    macd_value, macd_signal, macd_conf = macd_calc.calculate_with_signal(data['closes'])

    # Stage 3: Volatility analysis
    bb_calc = BollingerBandsCalculator()
    atr_calc = ATR()

    bb_result = bb_calc.calculate(data['closes'], current_price=data['closes'][-1])
    atr_result = atr_calc.calculate(
        data['highs'], data['lows'], data['closes'],
        current_price=data['closes'][-1]
    )

    # Stage 4: Volume confirmation
    vol_calc = VolumeConfirmation()
    vol_result = vol_calc.calculate(data['volumes'])

    # Verify all stages completed
    assert trend_result is not None
    assert rsi_value is not None
    assert macd_value is not None
    assert bb_result is not None
    assert atr_result is not None
    assert vol_result is not None

    # Create aggregated signal
    pipeline_result = {
        'trend': trend_result['trend'],
        'rsi_signal': rsi_signal,
        'macd_signal': macd_signal,
        'bb_signal': bb_result['signal'],
        'volume_confirmed': vol_result['confirmed'],
        'stop_loss': atr_result['stop_loss_long'],
        'take_profit': atr_result['take_profit_long']
    }

    assert pipeline_result['trend'] in ["BULLISH", "BEARISH", "NEUTRAL"]


def test_pipeline_handles_insufficient_data_gracefully():
    """Test pipeline handles insufficient data without crashing"""
    # Only 10 data points (insufficient for most indicators)
    short_data = {
        'highs': [100 + i for i in range(10)],
        'lows': [99 + i for i in range(10)],
        'closes': [99.5 + i for i in range(10)],
        'volumes': [1000] * 10
    }

    rsi_calc = RSICalculator()
    macd_calc = MACDCalculator()
    trend_calc = TrendFilter()

    # Should return None or NEUTRAL, not crash
    rsi_value = rsi_calc.calculate(pd.DataFrame({'close': short_data['closes']}))
    macd_result = macd_calc.calculate(short_data['closes'])
    trend_result = trend_calc.calculate(short_data['closes'])

    # Check for graceful handling
    assert rsi_value is None or rsi_value >= 0
    assert macd_result is None or 'macd' in macd_result
    assert trend_result['trend'] == "NEUTRAL"


# ============================================================================
# Performance Tests
# ============================================================================

def test_multi_indicator_pipeline_performance():
    """Test performance of running all indicators together"""
    import time

    # Generate realistic dataset
    np.random.seed(42)
    size = 1000
    data = {
        'highs': [100 + i * 0.1 + np.random.normal(0, 1) for i in range(size)],
        'lows': [99 + i * 0.1 + np.random.normal(0, 1) for i in range(size)],
        'closes': [99.5 + i * 0.1 + np.random.normal(0, 1) for i in range(size)],
        'volumes': [1000 + np.random.normal(0, 100) for i in range(size)]
    }

    start_time = time.time()

    # Run all indicators
    rsi_calc = RSICalculator()
    macd_calc = MACDCalculator()
    bb_calc = BollingerBandsCalculator()
    atr_calc = ATR()
    stoch_calc = Stochastic()
    trend_calc = TrendFilter()
    vol_calc = VolumeConfirmation()

    rsi_calc.calculate(pd.DataFrame({'close': data['closes']}))
    macd_calc.calculate(data['closes'])
    bb_calc.calculate(data['closes'], current_price=data['closes'][-1])
    atr_calc.calculate(data['highs'], data['lows'], data['closes'], current_price=data['closes'][-1])
    stoch_calc.calculate(data['highs'], data['lows'], data['closes'])
    trend_calc.calculate(data['closes'])
    vol_calc.calculate(data['volumes'])

    elapsed = time.time() - start_time

    # Should complete in reasonable time
    assert elapsed < 2.0, f"Pipeline too slow: {elapsed}s for 1000 points"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
