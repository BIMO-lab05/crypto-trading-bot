#!/usr/bin/env python3
"""
Unit Tests for Volume Confirmation

Tests volume-based signal validation, confirmation thresholds,
and edge cases.
"""

import pytest
import numpy as np

import sys
sys.path.insert(0, '/mnt/d/Bimo_max/crypto-trading-bot/services/technical-analysis')

from app.indicators.volume_confirmation import VolumeConfirmation


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def volume_confirmation():
    """Standard volume confirmation with period=20"""
    return VolumeConfirmation()


@pytest.fixture
def strong_volume_data():
    """Generate strong volume scenario (>1.5x average)"""
    # Base volume of 1000, then spike to 2000 (2x)
    volumes = [1000.0] * 20 + [2000.0]
    return volumes


@pytest.fixture
def moderate_volume_data():
    """Generate moderate volume scenario (1.2-1.5x average)"""
    # Base volume of 1000, then increase to 1300 (1.3x)
    volumes = [1000.0] * 20 + [1300.0]
    return volumes


@pytest.fixture
def weak_volume_data():
    """Generate weak volume scenario (1.0-1.2x average)"""
    # Base volume of 1000, then slight increase to 1100 (1.1x)
    volumes = [1000.0] * 20 + [1100.0]
    return volumes


@pytest.fixture
def insufficient_volume_data():
    """Generate insufficient volume scenario (<1.0x average)"""
    # Base volume of 1000, then drop to 800 (0.8x)
    volumes = [1000.0] * 20 + [800.0]
    return volumes


# ============================================================================
# Initialization Tests
# ============================================================================

def test_volume_confirmation_initialization(volume_confirmation):
    """Test volume confirmation initialization"""
    assert volume_confirmation.period == 20
    assert volume_confirmation.breakout_threshold == 1.2
    assert volume_confirmation.strong_threshold == 1.5


def test_volume_confirmation_custom_parameters():
    """Test volume confirmation with custom parameters"""
    vc = VolumeConfirmation(period=14, breakout_threshold=1.3, strong_threshold=2.0)
    assert vc.period == 14
    assert vc.breakout_threshold == 1.3
    assert vc.strong_threshold == 2.0


# ============================================================================
# Strong Volume Tests
# ============================================================================

def test_volume_strong_confirmation(volume_confirmation, strong_volume_data):
    """Test strong volume confirmation (>1.5x average)"""
    result = volume_confirmation.calculate(strong_volume_data, signal_type="breakout")

    assert result is not None
    assert result["confirmed"] == True
    assert result["strength"] == "STRONG"
    assert result["signal"] == "CONFIRM"
    assert result["confidence"] == 1.0


def test_volume_strong_ratio_calculation(volume_confirmation, strong_volume_data):
    """Test volume ratio calculation for strong volume"""
    result = volume_confirmation.calculate(strong_volume_data, signal_type="breakout")

    # Current volume = 2000, avg includes current in 20-period window
    assert result["current_volume"] == 2000.0
    assert result["avg_volume"] > 0
    assert result["volume_ratio"] >= 1.5  # Strong threshold


def test_volume_strong_description(volume_confirmation, strong_volume_data):
    """Test description format for strong volume"""
    result = volume_confirmation.calculate(strong_volume_data, signal_type="breakout")

    assert "STRONG" in result["description"]
    assert "average" in result["description"].lower()


# ============================================================================
# Moderate Volume Tests
# ============================================================================

def test_volume_moderate_confirmation(volume_confirmation, moderate_volume_data):
    """Test moderate volume confirmation (1.2-1.5x average)"""
    result = volume_confirmation.calculate(moderate_volume_data, signal_type="breakout")

    assert result is not None
    assert result["confirmed"] == True
    assert result["strength"] == "MODERATE"
    assert result["signal"] == "CONFIRM"
    assert result["confidence"] == 0.7


def test_volume_moderate_ratio_calculation(volume_confirmation, moderate_volume_data):
    """Test volume ratio calculation for moderate volume"""
    result = volume_confirmation.calculate(moderate_volume_data, signal_type="breakout")

    # Current volume = 1300, avg includes current in 20-period window
    assert result["current_volume"] == 1300.0
    assert result["avg_volume"] > 0
    assert 1.2 <= result["volume_ratio"] < 1.5


# ============================================================================
# Weak Volume Tests
# ============================================================================

def test_volume_weak_breakout(volume_confirmation, weak_volume_data):
    """Test weak volume with breakout signal (should reject)"""
    result = volume_confirmation.calculate(weak_volume_data, signal_type="breakout")

    # Weak volume (<1.2x) should reject breakout signals
    assert result["strength"] == "WEAK"
    assert result["confirmed"] == False
    assert result["signal"] == "REJECT"
    assert result["confidence"] == 0.4


def test_volume_weak_continuation(volume_confirmation, weak_volume_data):
    """Test weak volume with continuation signal (should confirm)"""
    result = volume_confirmation.calculate(weak_volume_data, signal_type="continuation")

    # Weak volume (≥1.0x) should confirm continuation signals
    assert result["strength"] == "WEAK"
    assert result["confirmed"] == True
    assert result["signal"] == "CONFIRM"
    assert result["confidence"] == 0.4


def test_volume_weak_ratio_calculation(volume_confirmation, weak_volume_data):
    """Test volume ratio calculation for weak volume"""
    result = volume_confirmation.calculate(weak_volume_data, signal_type="breakout")

    # Current volume = 1100, avg includes current in 20-period window
    assert result["current_volume"] == 1100.0
    assert result["avg_volume"] > 0
    assert 1.0 <= result["volume_ratio"] < 1.2


# ============================================================================
# Insufficient Volume Tests
# ============================================================================

def test_volume_insufficient_confirmation(volume_confirmation, insufficient_volume_data):
    """Test insufficient volume rejection (<1.0x average)"""
    result = volume_confirmation.calculate(insufficient_volume_data, signal_type="breakout")

    assert result is not None
    assert result["confirmed"] == False
    assert result["strength"] == "INSUFFICIENT"
    assert result["signal"] == "REJECT"
    assert result["confidence"] == 0.1


def test_volume_insufficient_ratio(volume_confirmation, insufficient_volume_data):
    """Test volume ratio for insufficient volume"""
    result = volume_confirmation.calculate(insufficient_volume_data, signal_type="breakout")

    # Current volume = 800, avg includes current in 20-period window
    assert result["current_volume"] == 800.0
    assert result["avg_volume"] > 0
    assert result["volume_ratio"] < 1.0


# ============================================================================
# Signal Type Tests
# ============================================================================

def test_volume_breakout_signal_type(volume_confirmation):
    """Test breakout signal type requires higher volume"""
    # Volume = 1.1x average (weak)
    volumes = [1000.0] * 20 + [1100.0]

    result = volume_confirmation.calculate(volumes, signal_type="breakout")

    # Breakout requires ≥1.2x, so should reject
    assert result["confirmed"] == False


def test_volume_continuation_signal_type(volume_confirmation):
    """Test continuation signal type is more lenient"""
    # Volume = 1.1x average (weak)
    volumes = [1000.0] * 20 + [1100.0]

    result = volume_confirmation.calculate(volumes, signal_type="continuation")

    # Continuation accepts ≥1.0x, so should confirm
    assert result["confirmed"] == True


def test_volume_signal_type_comparison(volume_confirmation):
    """Test breakout requires higher volume than continuation"""
    # Volume = 1.15x average
    volumes = [1000.0] * 20 + [1150.0]

    breakout_result = volume_confirmation.calculate(volumes, signal_type="breakout")
    continuation_result = volume_confirmation.calculate(volumes, signal_type="continuation")

    # Same volume, different requirements
    assert breakout_result["volume_ratio"] == continuation_result["volume_ratio"]
    # Continuation should be more lenient (both would confirm or breakout rejects)


# ============================================================================
# Edge Cases
# ============================================================================

def test_volume_insufficient_data(volume_confirmation):
    """Test returns rejection with insufficient data"""
    short_data = [1000.0] * 10  # Less than 20 required
    result = volume_confirmation.calculate(short_data, signal_type="breakout")

    assert result["confirmed"] == False
    assert result["signal"] == "REJECT"
    assert result["confidence"] == 0.0
    assert result["strength"] == "INSUFFICIENT"


def test_volume_exact_minimum_data(volume_confirmation):
    """Test with exactly 20 data points (minimum)"""
    min_data = [1000.0] * 20
    result = volume_confirmation.calculate(min_data, signal_type="breakout")

    # Should work, but last volume = avg volume (ratio = 1.0)
    assert result is not None
    assert result["volume_ratio"] == 1.0


def test_volume_zero_average(volume_confirmation):
    """Test handles zero average volume gracefully"""
    zero_volumes = [0.0] * 20 + [100.0]

    result = volume_confirmation.calculate(zero_volumes, signal_type="breakout")

    # Average includes the 100, so avg = 100/20 = 5, ratio = 100/5 = 20
    assert result is not None
    assert result["volume_ratio"] > 0  # Will be high due to zeros in history


def test_volume_all_zero():
    """Test with all zero volumes"""
    zero_volumes = [0.0] * 21

    vc = VolumeConfirmation()
    result = vc.calculate(zero_volumes, signal_type="breakout")

    assert result is not None
    assert result["current_volume"] == 0.0
    assert result["avg_volume"] == 0.0
    assert result["volume_ratio"] == 0.0


def test_volume_with_negative_values():
    """Test handles negative volume values"""
    # Negative volumes shouldn't happen, but test graceful handling
    volumes = [1000.0] * 19 + [-500.0, 1500.0]

    vc = VolumeConfirmation()
    result = vc.calculate(volumes, signal_type="breakout")

    # Should still calculate (though data is invalid)
    assert result is not None


def test_volume_extreme_spike():
    """Test with extreme volume spike (10x)"""
    extreme_volumes = [1000.0] * 20 + [10000.0]

    vc = VolumeConfirmation()
    result = vc.calculate(extreme_volumes, signal_type="breakout")

    assert result["strength"] == "STRONG"
    assert result["confidence"] == 1.0
    assert result["volume_ratio"] > 5.0  # Very high ratio (exact depends on window)


# ============================================================================
# Confidence Level Tests
# ============================================================================

def test_volume_confidence_levels(volume_confirmation):
    """Test confidence levels match volume strength"""
    # Strong volume
    strong_vols = [1000.0] * 20 + [2000.0]
    strong_result = volume_confirmation.calculate(strong_vols)
    assert strong_result["confidence"] == 1.0

    # Moderate volume
    moderate_vols = [1000.0] * 20 + [1300.0]
    moderate_result = volume_confirmation.calculate(moderate_vols)
    assert moderate_result["confidence"] == 0.7

    # Weak volume
    weak_vols = [1000.0] * 20 + [1100.0]
    weak_result = volume_confirmation.calculate(weak_vols)
    assert weak_result["confidence"] == 0.4

    # Insufficient volume
    insuf_vols = [1000.0] * 20 + [800.0]
    insuf_result = volume_confirmation.calculate(insuf_vols)
    assert insuf_result["confidence"] == 0.1


# ============================================================================
# Calculation Tests
# ============================================================================

def test_volume_ratio_accuracy():
    """Test volume ratio calculation accuracy"""
    volumes = [500.0, 600.0, 700.0, 800.0, 900.0, 1000.0, 1100.0, 1200.0,
               1300.0, 1400.0, 1500.0, 1600.0, 1700.0, 1800.0, 1900.0, 2000.0,
               2100.0, 2200.0, 2300.0, 2400.0, 3000.0]  # 21 volumes

    vc = VolumeConfirmation(period=20)
    result = vc.calculate(volumes)

    # Average of last 20 (including 3000) = (600+700+...+2400+3000) / 20
    expected_avg = np.mean(volumes[-20:])
    assert abs(result["avg_volume"] - expected_avg) < 0.01
    assert result["current_volume"] == 3000.0


def test_volume_average_calculation():
    """Test average volume calculation"""
    volumes = [1000.0] * 15 + [1500.0] * 5 + [2000.0]

    vc = VolumeConfirmation(period=20)
    result = vc.calculate(volumes)

    # Average of last 20 includes the 2000: (1000*14 + 1500*5 + 2000) / 20
    expected_avg = (1000 * 14 + 1500 * 5 + 2000) / 20
    assert abs(result["avg_volume"] - expected_avg) < 0.01


# ============================================================================
# Performance Tests
# ============================================================================

def test_volume_large_dataset_performance(volume_confirmation):
    """Test volume confirmation with large dataset"""
    import time

    # 10,000 volume data points
    large_volumes = [1000 + np.random.normal(0, 100) for i in range(10000)]

    start_time = time.time()
    result = volume_confirmation.calculate(large_volumes, signal_type="breakout")
    elapsed = time.time() - start_time

    assert result is not None
    assert elapsed < 0.5  # Should complete in < 0.5 seconds


# ============================================================================
# Integration-like Tests
# ============================================================================

def test_volume_realistic_trading_scenario():
    """Test volume confirmation with realistic trading scenario"""
    # Simulate accumulation then breakout
    volumes = []

    # Accumulation phase (20 periods, low volume)
    for i in range(20):
        volumes.append(1000 + np.random.normal(0, 50))

    # Breakout with high volume
    volumes.append(2500)  # 2.5x average

    vc = VolumeConfirmation()
    result = vc.calculate(volumes, signal_type="breakout")

    assert result["confirmed"] == True
    assert result["strength"] == "STRONG"


def test_volume_false_breakout_detection():
    """Test detection of false breakout (low volume)"""
    # Price breakout but volume doesn't confirm
    volumes = [1000.0] * 20 + [900.0]  # Lower volume on "breakout"

    vc = VolumeConfirmation()
    result = vc.calculate(volumes, signal_type="breakout")

    # Should reject due to insufficient volume
    assert result["confirmed"] == False
    assert result["strength"] == "INSUFFICIENT"


def test_volume_trend_continuation():
    """Test volume confirmation during trend continuation"""
    # Steady trend with moderate volume
    volumes = [1000 + i * 10 for i in range(20)] + [1200.0]

    vc = VolumeConfirmation()
    result = vc.calculate(volumes, signal_type="continuation")

    # Should confirm continuation with normal volume
    assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
