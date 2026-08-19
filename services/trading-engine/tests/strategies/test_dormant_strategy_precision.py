"""Price-domain rounding in the dormant strategy layer collapses ADA-scale ladders.

Defect (Task 13, parity with PRICE-01/research_optimized_strategy.py): four files
in the strategy layer round stop-losses, take-profit ladders, EMAs, ATRs, and S/R
zone bounds to 2dp before returning them. None of these four files has a runtime
caller in ``app/`` today (DORMANT) -- they are exercised only by tests -- but the
precision bug is real and identical in shape to the shipped PRICE-01 fix: at ADA
scale (entry ~$0.35, ATR ~$0.004) a 2dp round collapses adjacent ladder rungs onto
the same trigger, and a rounded 1%-floor stop distorts risk-based position sizing.

A second, related defect lives in ``support_resistance_strategy._calculate_atr``:
rounding a small-but-real ATR (~$0.002 at ADA scale) to 2dp truncates it to
exactly 0.0. That zero then flows into ``_calculate_partial_exits``, where
``np.float64(x) / np.float64(0.0)`` is ``inf`` (a RuntimeWarning, not a crash),
pinning TP1/TP2 exactly at entry and leaving TP3's ``atr_multiple`` at ``inf`` --
an instant fee-burning exit. The vacuous "skip if target too close" guard at
``support_resistance_strategy.py:653`` is hardened to also catch a genuinely
non-positive ATR (a truly flat candle window), which independently produces the
same pinned-at-entry / ``atr_multiple=inf`` degeneracy.
"""

import math

import numpy as np
import pandas as pd
import pytest

from app.strategies.momentum_breakout_strategy import (
    BreakoutDirection,
    MomentumBreakoutStrategy,
)
from app.strategies.support_resistance_strategy import SupportResistanceStrategy
from app.strategies.trend_following_strategy import (
    TrendAnalysis,
    TrendDirection,
    TrendFollowingStrategy,
    TrendStrength,
)
from app.utils.support_resistance_detector import SupportResistanceDetector

# ADA/USDT-scale fixtures -- the exact regime PRICE-01 broke on.
ADA_ENTRY = 0.3512
ADA_ATR = 0.004


@pytest.fixture
def momentum_strategy():
    return MomentumBreakoutStrategy()


@pytest.fixture
def trend_strategy():
    return TrendFollowingStrategy()


@pytest.fixture
def sr_strategy():
    return SupportResistanceStrategy()


@pytest.fixture
def detector():
    return SupportResistanceDetector()


# =============================================================================
# Momentum breakout ladder
# =============================================================================


@pytest.mark.parametrize("is_long", [True, False], ids=["long", "short"])
def test_momentum_ladder_rungs_are_distinct_at_ada_scale(momentum_strategy, is_long):
    """TP1/TP2/TP3 must be three distinct triggers, not two.

    ``final_target`` is 0.02 away from entry -- comfortably over the
    ``atr * 2`` (0.008) skip threshold, so the ladder is not vacuously empty.
    """
    direction = BreakoutDirection.BULLISH if is_long else BreakoutDirection.BEARISH
    final_target = ADA_ENTRY + 0.02 if is_long else ADA_ENTRY - 0.02

    levels = momentum_strategy._calculate_partial_exits(
        ADA_ENTRY, ADA_ATR, direction, final_target
    )

    assert len(levels) == 3, "ladder should not skip -- final_target clears atr*2"
    prices = [lv.price for lv in levels]
    assert len(set(prices)) == 3, f"collapsed ladder: {prices}"


@pytest.mark.parametrize("is_long", [True, False], ids=["long", "short"])
def test_momentum_ladder_preserves_atr_geometry_at_ada_scale(
    momentum_strategy, is_long
):
    """Each rung must sit exactly its own ``atr_multiple`` from entry."""
    direction = BreakoutDirection.BULLISH if is_long else BreakoutDirection.BEARISH
    final_target = ADA_ENTRY + 0.02 if is_long else ADA_ENTRY - 0.02

    levels = momentum_strategy._calculate_partial_exits(
        ADA_ENTRY, ADA_ATR, direction, final_target
    )

    for level in levels:
        distance = (level.price - ADA_ENTRY) if is_long else (ADA_ENTRY - level.price)
        assert distance / ADA_ATR == pytest.approx(level.atr_multiple, rel=1e-6), (
            f"{level.label} at {level.price} is {distance / ADA_ATR:.3f}x ATR, "
            f"not {level.atr_multiple}x"
        )


# =============================================================================
# Trend-following Fibonacci ladder
# =============================================================================


def _trend_analysis(direction: TrendDirection) -> TrendAnalysis:
    return TrendAnalysis(
        direction=direction,
        strength=TrendStrength.STRONG,
        ema_fast=0.352,
        ema_medium=0.350,
        ema_slow=0.347,
        ema_aligned=True,
        adx_value=28.0,
        price_above_emas=3 if direction == TrendDirection.BULLISH else 0,
        trend_duration=10,
    )


@pytest.mark.parametrize(
    "direction,entry,swing_low,swing_high",
    [
        (TrendDirection.BULLISH, 0.3560, 0.3490, 0.3512),
        (TrendDirection.BEARISH, 0.3460, 0.3490, 0.3512),
    ],
    ids=["long", "short"],
)
def test_trend_ladder_rungs_are_distinct_at_ada_scale(
    trend_strategy, direction, entry, swing_low, swing_high
):
    """A tight ADA-scale swing range must not collapse TP1/TP2/TP3 onto one rung."""
    trend = _trend_analysis(direction)

    _, _, levels = trend_strategy._calculate_stops_and_targets(
        entry, trend, ADA_ATR, swing_low, swing_high
    )

    assert len(levels) == 3
    prices = [lv.price for lv in levels]
    assert len(set(prices)) == 3, f"collapsed ladder: {prices}"


def test_trend_ladder_preserves_fib_geometry_at_ada_scale(trend_strategy):
    """Each rung's distance from the swing extreme must equal
    ``swing_range * (fib_level - 1)`` exactly (BULLISH case)."""
    entry, swing_low, swing_high = 0.3560, 0.3490, 0.3512
    swing_range = swing_high - swing_low
    trend = _trend_analysis(TrendDirection.BULLISH)

    _, _, levels = trend_strategy._calculate_stops_and_targets(
        entry, trend, ADA_ATR, swing_low, swing_high
    )

    for level in levels:
        expected_distance = swing_range * (level.fib_level - 1)
        actual_distance = level.price - swing_high
        assert actual_distance == pytest.approx(expected_distance, rel=1e-9), (
            f"{level.label} at {level.price} is {actual_distance} from swing_high, "
            f"not the expected {expected_distance}"
        )


# =============================================================================
# Support/Resistance ladder, stop-distance floor, and zero-ATR degeneracy
# =============================================================================


def test_sr_ladder_rungs_are_distinct_at_ada_scale(sr_strategy):
    final_target = ADA_ENTRY + 0.02

    levels = sr_strategy._calculate_partial_exits(
        ADA_ENTRY, ADA_ATR, True, final_target
    )

    assert len(levels) == 3
    prices = [lv.price for lv in levels]
    assert len(set(prices)) == 3, f"collapsed ladder: {prices}"


def test_sr_stop_distance_survives_the_one_percent_floor(sr_strategy):
    """With ATR small enough that the ATR-based stop undercuts the 1% floor,
    the returned stop must actually sit ~1% from entry -- not collapse to
    ~0.34% because the stop price got rounded to a 2dp grid coarser than the
    intended distance (currently ~0.0034 at this scale)."""
    small_atr = 0.001  # atr * ATR_STOP_MULTIPLIER(2.5) = 0.0025 < entry * 1%

    stop_loss, _, _ = sr_strategy._calculate_stops_and_targets(
        ADA_ENTRY, small_atr, True, [], []
    )

    assert abs(ADA_ENTRY - stop_loss) / ADA_ENTRY == pytest.approx(0.01, rel=1e-3)


def test_sr_atr_not_rounded_away_to_zero_on_a_choppy_ada_window(sr_strategy):
    """A real, small ADA-scale ATR (~$0.002) must survive ``_calculate_atr``
    instead of being crushed to exactly 0.0 by ``round(atr, 2)``, which then
    pins TP1/TP2 at entry and drives TP3's atr_multiple to inf downstream."""
    np.random.seed(7)
    n = 30
    closes = 0.3512 + np.random.uniform(-0.0005, 0.0005, n)
    highs = closes + np.random.uniform(0.0005, 0.0015, n)
    lows = closes - np.random.uniform(0.0005, 0.0015, n)
    df = pd.DataFrame({"high": highs, "low": lows, "close": closes})

    atr = sr_strategy._calculate_atr(df, period=14)
    assert atr > 0, "real ATR at this window is ~0.002, not exactly zero"

    entry_price = float(closes[-1])
    _, _, levels = sr_strategy._calculate_stops_and_targets(
        entry_price, atr, True, [], []
    )

    assert len(levels) == 3
    prices = [lv.price for lv in levels]
    assert len(set(prices)) == 3, f"collapsed ladder: {prices}"
    assert levels[0].price != entry_price, "TP1 pinned exactly at entry"
    for level in levels:
        assert not math.isinf(level.atr_multiple) and not math.isnan(
            level.atr_multiple
        ), f"{level.label} atr_multiple is degenerate: {level.atr_multiple}"


def test_sr_true_zero_atr_returns_no_partial_exits(sr_strategy):
    """A genuinely flat candle window (true ATR == 0.0, not a rounding
    artifact) must not produce a degenerate ladder pinned at entry with an
    infinite atr_multiple -- the hardened guard should skip it entirely."""
    n = 20
    flat_price = 0.3512
    df = pd.DataFrame(
        {
            "high": [flat_price] * n,
            "low": [flat_price] * n,
            "close": [flat_price] * n,
        }
    )
    atr = sr_strategy._calculate_atr(df, period=14)
    assert atr == 0.0, "sanity: this window really has zero true range"

    levels = sr_strategy._calculate_partial_exits(
        flat_price, atr, True, flat_price + 0.02
    )

    assert levels == [], "zero-ATR guard should skip the ladder, not pin it at entry"


# =============================================================================
# Support/Resistance detector zone bounds
# =============================================================================


def test_detector_support_zones_stay_open_at_ada_scale(detector):
    """``zone_low < zone_high`` is the existing invariant at
    ``test_support_resistance_detector.py:510`` -- it only holds today because
    that fixture uses $95-105 prices. Reproduce it at ADA scale, where a 2dp
    round can put zone_low and zone_high on the same tick."""
    np.random.seed(42)
    dates = pd.date_range(start="2025-01-01", periods=100, freq="1h")
    scale = 300.0  # $95-105 -> ~$0.317-0.35, ADA-ish

    base_prices = []
    for i in range(100):
        if i % 10 < 5:
            base_prices.append(95 + np.random.uniform(0, 5))
        else:
            base_prices.append(100 + np.random.uniform(0, 5))

    df = pd.DataFrame(
        {
            "timestamp": dates,
            "open": [(p + np.random.uniform(-1, 1)) / scale for p in base_prices],
            "high": [(p + np.random.uniform(0, 2)) / scale for p in base_prices],
            "low": [(p - np.random.uniform(0, 2)) / scale for p in base_prices],
            "close": [p / scale for p in base_prices],
            "volume": np.random.uniform(1000, 5000, 100),
        }
    )

    levels = detector.find_support_levels(df, lookback=100)

    assert len(levels) > 0, "should find support levels in the ADA-scaled data"
    for level in levels:
        assert level.zone_low < level.zone_high, (
            f"zone collapsed: low={level.zone_low}, high={level.zone_high}"
        )
