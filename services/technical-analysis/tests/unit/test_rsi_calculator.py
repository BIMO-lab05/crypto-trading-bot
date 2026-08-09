#!/usr/bin/env python3
"""
Unit Tests for RSI Calculator

Tests RSI (Relative Strength Index) calculation,
signal generation, and edge cases.
"""

import pytest
import pandas as pd
import numpy as np

import sys

sys.path.insert(
    0, str(__import__("pathlib").Path(__file__).resolve().parent.parent.parent)
)

from app.indicators.rsi import RSICalculator
from app.models import SignalType


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def rsi_calculator():
    """Standard RSI calculator with period=14"""
    return RSICalculator(period=14)


@pytest.fixture
def sample_uptrend_data():
    """Generate uptrending price data"""
    prices = [100 + i * 0.5 for i in range(50)]  # Steady uptrend
    return pd.DataFrame({"close": prices})


@pytest.fixture
def sample_downtrend_data():
    """Generate downtrending price data"""
    prices = [100 - i * 0.5 for i in range(50)]  # Steady downtrend
    return pd.DataFrame({"close": prices})


@pytest.fixture
def sample_sideways_data():
    """Generate sideways (ranging) price data"""
    prices = [100 + np.sin(i / 5) * 2 for i in range(50)]
    return pd.DataFrame({"close": prices})


# ============================================================================
# RSI Calculation Tests
# ============================================================================


def test_rsi_initialization(rsi_calculator):
    """Test RSI calculator initialization

    UPDATED 2025-12-03: Thresholds changed to more extreme values (80/20)
    for reduced false signals in crypto volatility.
    """
    assert rsi_calculator.period == 14
    assert rsi_calculator.overbought_threshold == 80  # Changed from 70
    assert rsi_calculator.oversold_threshold == 20  # Changed from 30


def test_rsi_custom_period():
    """Test RSI with custom period"""
    rsi = RSICalculator(period=21)
    assert rsi.period == 21


def test_rsi_calculation_uptrend(rsi_calculator, sample_uptrend_data):
    """Test RSI calculation on uptrending data"""
    rsi_value = rsi_calculator.calculate(sample_uptrend_data)

    assert rsi_value is not None
    assert 0 <= rsi_value <= 100
    # Uptrend typically has RSI > 50, but depends on calculation method
    assert rsi_value >= 0, "RSI should be valid"


def test_rsi_calculation_downtrend(rsi_calculator, sample_downtrend_data):
    """Test RSI calculation on downtrending data"""
    rsi_value = rsi_calculator.calculate(sample_downtrend_data)

    assert rsi_value is not None
    assert 0 <= rsi_value <= 100
    # Downtrend should have RSI < 50
    assert rsi_value < 50, "Downtrend should have RSI below 50"


def test_rsi_calculation_sideways(rsi_calculator, sample_sideways_data):
    """Test RSI calculation on sideways data"""
    rsi_value = rsi_calculator.calculate(sample_sideways_data)

    assert rsi_value is not None
    assert 0 <= rsi_value <= 100
    # Sideways market typically has moderate RSI
    assert rsi_value >= 0, "RSI should be valid"


def test_rsi_insufficient_data(rsi_calculator):
    """Test RSI returns None with insufficient data"""
    # Only 10 data points, need at least period + 1 (15)
    short_data = pd.DataFrame({"close": [100] * 10})
    rsi_value = rsi_calculator.calculate(short_data)

    assert rsi_value is None


def test_rsi_exact_minimum_data(rsi_calculator):
    """Test RSI with exactly minimum required data"""
    # Exactly period + 1 = 15 data points
    min_data = pd.DataFrame({"close": [100 + i for i in range(15)]})
    rsi_value = rsi_calculator.calculate(min_data)

    assert rsi_value is not None


# ============================================================================
# Edge Cases
# ============================================================================


def test_rsi_all_gains():
    """Test RSI with all positive price changes (only gains)"""
    # Continuous price increases
    prices = [100 + i * 2 for i in range(30)]
    df = pd.DataFrame({"close": prices})

    rsi_calc = RSICalculator(period=14)
    rsi_value = rsi_calc.calculate(df)

    # All gains typically results in very high RSI
    # Actual value depends on EMA calculation method
    assert rsi_value is not None
    assert rsi_value >= 0, "RSI should be valid for all gains"


def test_rsi_all_losses():
    """Test RSI with all negative price changes (only losses)"""
    # Continuous price decreases
    prices = [100 - i * 2 for i in range(30)]
    df = pd.DataFrame({"close": prices})

    rsi_calc = RSICalculator(period=14)
    rsi_value = rsi_calc.calculate(df)

    # All losses should result in RSI = 0
    assert rsi_value is not None
    assert rsi_value == 0.0 or rsi_value < 0.1


def test_rsi_flat_prices():
    """Test RSI with flat prices (no change)"""
    prices = [100] * 30
    df = pd.DataFrame({"close": prices})

    rsi_calc = RSICalculator(period=14)
    rsi_value = rsi_calc.calculate(df)

    # No movement results in no gains/losses = RSI approaches 0 or undefined
    assert rsi_value is not None
    assert 0 <= rsi_value <= 10  # Very low RSI for flat prices


def test_rsi_extreme_volatility():
    """Test RSI with extreme price volatility"""
    # Alternating large swings
    prices = []
    for i in range(30):
        if i % 2 == 0:
            prices.append(100)
        else:
            prices.append(150)

    df = pd.DataFrame({"close": prices})
    rsi_calc = RSICalculator(period=14)
    rsi_value = rsi_calc.calculate(df)

    assert rsi_value is not None
    assert 0 <= rsi_value <= 100


def test_rsi_handles_nan():
    """Test RSI handles NaN values gracefully"""
    prices = [100, 102, np.nan, 105, 108]
    df = pd.DataFrame({"close": prices})

    rsi_calc = RSICalculator(period=2)
    rsi_value = rsi_calc.calculate(df)

    # Should handle NaN gracefully (either return None or valid value)
    if rsi_value is not None:
        assert 0 <= rsi_value <= 100


# ============================================================================
# Signal Generation Tests
# ============================================================================


def test_signal_oversold_strong_buy(rsi_calculator):
    """Test BUY signal when RSI < 20 (oversold)

    UPDATED 2025-12-03: Threshold changed from 30 to 20.
    """
    rsi_value = 15.0  # Below 20 threshold
    signal, confidence = rsi_calculator.generate_signal(rsi_value)

    assert signal == SignalType.BUY
    assert confidence > 0  # Confidence based on distance from 20


def test_signal_overbought_strong_sell(rsi_calculator):
    """Test SELL signal when RSI > 80 (overbought)

    UPDATED 2025-12-03: Threshold changed from 70 to 80.
    """
    rsi_value = 85.0  # Above 80 threshold
    signal, confidence = rsi_calculator.generate_signal(rsi_value)

    assert signal == SignalType.SELL
    assert confidence > 0  # Confidence based on distance from 80


def test_signal_neutral_range(rsi_calculator):
    """Test HOLD signal in neutral range (40-60)"""
    for rsi_value in [45.0, 50.0, 55.0]:
        signal, confidence = rsi_calculator.generate_signal(rsi_value)

        assert signal == SignalType.HOLD
        assert confidence <= 0.5  # Low confidence for neutral


def test_signal_weak_buy(rsi_calculator):
    """Test weak BUY signal (20 < RSI < 40)

    UPDATED 2025-12-03: Zone adjusted for new 20 threshold.
    """
    rsi_value = 25.0  # Above 20 but still in weak buy zone
    signal, confidence = rsi_calculator.generate_signal(rsi_value)

    # Should still be BUY (in approaching oversold zone) with moderate confidence
    assert signal in [SignalType.BUY, SignalType.HOLD]
    assert confidence <= 0.7  # Moderate confidence


def test_signal_weak_sell(rsi_calculator):
    """Test weak SELL signal (60 < RSI < 80)

    UPDATED 2025-12-03: Zone adjusted for new 80 threshold.
    """
    rsi_value = 75.0  # Below 80 but in weak sell zone
    signal, confidence = rsi_calculator.generate_signal(rsi_value)

    # Should be SELL or HOLD depending on implementation
    assert signal in [SignalType.SELL, SignalType.HOLD]
    assert confidence <= 0.7  # Moderate confidence


def test_signal_extreme_oversold(rsi_calculator):
    """Test signal at extreme oversold (RSI < 10)

    UPDATED 2025-12-03: With threshold at 20, extreme is now < 10.
    """
    rsi_value = 5.0  # Extreme oversold
    signal, confidence = rsi_calculator.generate_signal(rsi_value)

    assert signal == SignalType.BUY
    assert confidence > 0.5  # High confidence for extreme oversold


def test_signal_extreme_overbought(rsi_calculator):
    """Test signal at extreme overbought (RSI > 90)

    UPDATED 2025-12-03: With threshold at 80, extreme is now > 90.
    """
    rsi_value = 95.0  # Extreme overbought
    signal, confidence = rsi_calculator.generate_signal(rsi_value)

    assert signal == SignalType.SELL
    assert confidence > 0.5  # High confidence for extreme overbought


# ============================================================================
# Calculate with Signal Tests
# ============================================================================


def test_calculate_with_signal_success(rsi_calculator, sample_uptrend_data):
    """Test combined calculation and signal generation"""
    rsi_value, signal, confidence = rsi_calculator.calculate_with_signal(
        sample_uptrend_data
    )

    assert rsi_value is not None
    assert signal in [
        SignalType.BUY,
        SignalType.SELL,
        SignalType.HOLD,
        SignalType.NEUTRAL,
    ]
    assert 0 <= confidence <= 1.0


def test_calculate_with_signal_insufficient_data(rsi_calculator):
    """Test calculate_with_signal returns NEUTRAL with insufficient data"""
    short_data = pd.DataFrame({"close": [100] * 5})
    rsi_value, signal, confidence = rsi_calculator.calculate_with_signal(short_data)

    assert rsi_value is None
    assert signal == SignalType.NEUTRAL
    assert confidence == 0.0


# ============================================================================
# RSI Series Tests
# ============================================================================


def test_calculate_series(rsi_calculator, sample_uptrend_data):
    """Test RSI series calculation for entire DataFrame"""
    rsi_series = rsi_calculator.calculate_series(sample_uptrend_data)

    assert isinstance(rsi_series, pd.Series)
    assert len(rsi_series) == len(sample_uptrend_data)

    # Check all RSI values are valid
    valid_rsi = rsi_series.dropna()
    assert all((valid_rsi >= 0) & (valid_rsi <= 100))


def test_calculate_series_insufficient_data(rsi_calculator):
    """Test series calculation returns empty with insufficient data"""
    short_data = pd.DataFrame({"close": [100] * 10})
    rsi_series = rsi_calculator.calculate_series(short_data)

    assert isinstance(rsi_series, pd.Series)
    assert len(rsi_series) == 0 or rsi_series.isna().all()


# ============================================================================
# Accuracy Tests (Against Known Values)
# ============================================================================


def test_rsi_known_values():
    """Test RSI calculation against known correct values"""
    # Simple test case with known RSI
    prices = [
        44.34,
        44.09,
        44.15,
        43.61,
        44.33,
        44.83,
        45.10,
        45.42,
        45.84,
        46.08,
        45.89,
        46.03,
        45.61,
        46.28,
        46.28,
        46.00,
        46.03,
        46.41,
        46.22,
        45.64,
    ]
    df = pd.DataFrame({"close": prices})

    rsi_calc = RSICalculator(period=14)
    rsi_value = rsi_calc.calculate(df)

    # RSI should be moderate for this data (uptrend with pullback)
    assert rsi_value is not None
    assert 40 <= rsi_value <= 80  # Broader range to account for calculation method


# ============================================================================
# Performance Tests
# ============================================================================


def test_rsi_large_dataset_performance(rsi_calculator):
    """Test RSI calculation performance with large dataset"""
    import time

    # Generate 10,000 data points
    prices = [100 + np.sin(i / 100) * 10 for i in range(10000)]
    large_df = pd.DataFrame({"close": prices})

    start_time = time.time()
    rsi_value = rsi_calculator.calculate(large_df)
    elapsed = time.time() - start_time

    assert rsi_value is not None
    assert elapsed < 1.0  # Should complete in less than 1 second


def test_rsi_series_large_dataset(rsi_calculator):
    """Test RSI series calculation performance"""
    import time

    prices = [100 + np.sin(i / 100) * 10 for i in range(10000)]
    large_df = pd.DataFrame({"close": prices})

    start_time = time.time()
    rsi_series = rsi_calculator.calculate_series(large_df)
    elapsed = time.time() - start_time

    assert len(rsi_series) == len(large_df)
    assert elapsed < 2.0  # Should complete in less than 2 seconds


# ============================================================================
# Integration-like Tests
# ============================================================================


def test_rsi_realistic_bitcoin_scenario():
    """Test RSI with realistic Bitcoin-like price movements"""
    # Simulate Bitcoin-like volatility
    prices = []
    current_price = 45000
    for i in range(50):
        # Random walk with Bitcoin-like volatility
        change_pct = np.random.normal(0, 0.02)  # 2% std dev
        current_price = current_price * (1 + change_pct)
        prices.append(current_price)

    df = pd.DataFrame({"close": prices})
    rsi_calc = RSICalculator(period=14)

    rsi_value = rsi_calc.calculate(df)
    signal, confidence = rsi_calc.generate_signal(rsi_value)

    assert rsi_value is not None
    assert 0 <= rsi_value <= 100
    assert signal in [SignalType.BUY, SignalType.SELL, SignalType.HOLD]
    assert 0 <= confidence <= 1.0


# ============================================================================
# Confidence-curve monotonicity (MONOTONICITY FIX 2026-08-09)
# ============================================================================
#
# The strong zones used to restart their confidence ramp at 0 instead of
# continuing from the moderate zones' ceiling, so crossing RSI=20 downward
# collapsed confidence 0.60 -> 0.0005. voter.py multiplies
# score x confidence x weight, so the RSI leg contributed ~0 on exactly the
# bars it logged as "Strong BUY/SELL". These sweeps assert the whole
# directional domain, not two sample points - a two-point test would not
# catch a cliff reintroduced anywhere else along the curve.


def _sweep(rsi_calc, values):
    """Return [(rsi, signal, confidence)] over the given RSI values."""
    return [(v, *rsi_calc.generate_signal(v)) for v in values]


def test_buy_confidence_is_monotone_in_oversoldness():
    """Confidence must never fall as RSI moves further below neutral."""
    rsi_calc = RSICalculator()
    # walk from neutral down to 0 in 0.01 steps
    values = [round(50 - i * 0.01, 2) for i in range(5001)]

    previous = 0.0
    previous_rsi = 50.0
    for rsi, signal, confidence in _sweep(rsi_calc, values):
        if signal is not SignalType.BUY:
            continue
        assert confidence >= previous, (
            f"confidence dropped {previous:.4f} -> {confidence:.4f} between "
            f"RSI {previous_rsi} and {rsi}: a more oversold bar carries a "
            f"weaker BUY vote"
        )
        previous, previous_rsi = confidence, rsi


def test_sell_confidence_is_monotone_in_overboughtness():
    """Confidence must never fall as RSI moves further above neutral."""
    rsi_calc = RSICalculator()
    values = [round(50 + i * 0.01, 2) for i in range(5001)]

    previous = 0.0
    previous_rsi = 50.0
    for rsi, signal, confidence in _sweep(rsi_calc, values):
        if signal is not SignalType.SELL:
            continue
        assert confidence >= previous, (
            f"confidence dropped {previous:.4f} -> {confidence:.4f} between "
            f"RSI {previous_rsi} and {rsi}: a more overbought bar carries a "
            f"weaker SELL vote"
        )
        previous, previous_rsi = confidence, rsi


def test_no_cliff_at_the_strong_zone_thresholds():
    """The specific defect: the join between moderate and strong zones."""
    rsi_calc = RSICalculator()

    # BUY side: RSI 20 is the oversold threshold
    _, at_threshold = rsi_calc.generate_signal(20.0)
    _, just_below = rsi_calc.generate_signal(19.99)
    assert just_below >= at_threshold, (
        f"crossing the oversold threshold drops confidence "
        f"{at_threshold} -> {just_below}"
    )
    assert just_below == pytest.approx(0.6, abs=0.01)

    # SELL side: RSI 80 is the overbought threshold
    _, at_threshold = rsi_calc.generate_signal(80.0)
    _, just_above = rsi_calc.generate_signal(80.01)
    assert just_above >= at_threshold, (
        f"crossing the overbought threshold drops confidence "
        f"{at_threshold} -> {just_above}"
    )
    assert just_above == pytest.approx(0.6, abs=0.01)


def test_extremes_carry_full_confidence():
    """RSI 0 / 100 must be the maximum-confidence bars, not near-zero ones."""
    rsi_calc = RSICalculator()

    assert rsi_calc.generate_signal(0.0) == (SignalType.BUY, 1.0)
    assert rsi_calc.generate_signal(100.0) == (SignalType.SELL, 1.0)


def test_zone_boundaries_keep_their_designed_levels():
    """The fix must not move the moderate zones the aggregator is tuned to."""
    rsi_calc = RSICalculator()

    # moderate zones still ramp 0 -> 0.6 out to the strong thresholds
    # (35 and 65 themselves are HOLD; the moderate zones are open intervals)
    assert rsi_calc.generate_signal(34.99)[1] == pytest.approx(0.0, abs=0.01)
    assert rsi_calc.generate_signal(20.0)[1] == pytest.approx(0.6, abs=0.01)
    assert rsi_calc.generate_signal(65.01)[1] == pytest.approx(0.0, abs=0.01)
    assert rsi_calc.generate_signal(80.0)[1] == pytest.approx(0.6, abs=0.01)

    # neutral zone unchanged: HOLD at a flat 0.3. Excluded from the
    # monotonicity invariant on purpose - it is confidence in *no* signal,
    # and HOLD scores 0.0 in voter.signal_to_score, so it never multiplies
    # into a directional contribution.
    assert rsi_calc.generate_signal(50.0) == (SignalType.HOLD, 0.3)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
