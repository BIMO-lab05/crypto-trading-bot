"""
Tests for app.services.indicator_registry
==========================================
Per-indicator rolling-confidence telemetry + re-enablement gate.

Covers:
* record() + rolling_average() boundaries (<30, =30, =200, >200).
* assert_eligible() raises below threshold, passes above.
* Concurrent record() under asyncio.gather — no data loss, deque capped.
* IndicatorBelowThresholdError carries structured attributes.
* Prometheus gauge updated on record().
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.indicator_registry import (
    DEFAULT_THRESHOLD,
    DEFAULT_WINDOW,
    INDICATOR_ROLLING_CONFIDENCE,
    MIN_SAMPLES_FOR_AVG,
    IndicatorBelowThresholdError,
    IndicatorRegistry,
    get_indicator_registry,
    reset_indicator_registry,
)


@pytest.fixture(autouse=True)
def _isolate_registry_singleton():
    """Drop the module-level singleton between tests for isolation."""
    reset_indicator_registry()
    yield
    reset_indicator_registry()


# ---------------------------------------------------------------------------
# rolling_average() boundary cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rolling_average_returns_none_below_min_samples():
    registry = IndicatorRegistry()
    for _ in range(MIN_SAMPLES_FOR_AVG - 1):
        await registry.record("RSI", 0.8, was_voted=True)
    assert await registry.rolling_average("RSI") is None


@pytest.mark.asyncio
async def test_rolling_average_returns_value_at_min_samples_boundary():
    registry = IndicatorRegistry()
    for _ in range(MIN_SAMPLES_FOR_AVG):
        await registry.record("RSI", 0.7, was_voted=True)
    avg = await registry.rolling_average("RSI")
    assert avg is not None
    assert avg == pytest.approx(0.7, abs=1e-9)


@pytest.mark.asyncio
async def test_rolling_average_at_window_boundary():
    """Exactly DEFAULT_WINDOW samples — buffer full, no eviction yet."""
    registry = IndicatorRegistry()
    for i in range(DEFAULT_WINDOW):
        # Linearly varying confidences in [0, 1).
        await registry.record("MACD", i / DEFAULT_WINDOW, was_voted=True)
    avg = await registry.rolling_average("MACD")
    expected = sum(i / DEFAULT_WINDOW for i in range(DEFAULT_WINDOW)) / DEFAULT_WINDOW
    assert avg == pytest.approx(expected, abs=1e-9)
    assert await registry.sample_count("MACD") == DEFAULT_WINDOW


@pytest.mark.asyncio
async def test_rolling_average_sliding_window_after_overflow():
    """Beyond DEFAULT_WINDOW — earliest samples evicted, avg reflects tail."""
    registry = IndicatorRegistry()
    # First 50 samples at 0.0, then 200 samples at 1.0.
    # After the 250th record, only the last 200 (all 1.0) remain.
    for _ in range(50):
        await registry.record("EMA", 0.0, was_voted=True)
    for _ in range(DEFAULT_WINDOW):
        await registry.record("EMA", 1.0, was_voted=True)
    assert await registry.sample_count("EMA") == DEFAULT_WINDOW
    assert await registry.rolling_average("EMA") == pytest.approx(1.0, abs=1e-9)


@pytest.mark.asyncio
async def test_record_clamps_out_of_range_confidence():
    """Out-of-range upstream values must not corrupt the rolling stats."""
    registry = IndicatorRegistry()
    # 30 samples of clamped 1.0 (came in as 1.5).
    for _ in range(MIN_SAMPLES_FOR_AVG):
        await registry.record("STOCH", 1.5, was_voted=True)
    assert await registry.rolling_average("STOCH") == pytest.approx(1.0, abs=1e-9)

    registry2 = IndicatorRegistry()
    for _ in range(MIN_SAMPLES_FOR_AVG):
        await registry2.record("STOCH", -0.2, was_voted=True)
    assert await registry2.rolling_average("STOCH") == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# assert_eligible()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assert_eligible_passes_above_threshold():
    registry = IndicatorRegistry()
    for _ in range(MIN_SAMPLES_FOR_AVG):
        await registry.record("ICHIMOKU", 0.80, was_voted=True)
    # Should not raise.
    await registry.assert_eligible("ICHIMOKU", threshold=DEFAULT_THRESHOLD)


@pytest.mark.asyncio
async def test_assert_eligible_raises_below_threshold():
    registry = IndicatorRegistry()
    for _ in range(MIN_SAMPLES_FOR_AVG):
        await registry.record("RSI_DIVERGENCE", 0.20, was_voted=True)
    with pytest.raises(IndicatorBelowThresholdError) as exc_info:
        await registry.assert_eligible("RSI_DIVERGENCE", threshold=0.55)
    err = exc_info.value
    assert err.name == "RSI_DIVERGENCE"
    assert err.current_avg == pytest.approx(0.20, abs=1e-9)
    assert err.threshold == 0.55


@pytest.mark.asyncio
async def test_assert_eligible_raises_when_no_samples():
    """No samples = ineligible (current_avg attribute is None)."""
    registry = IndicatorRegistry()
    with pytest.raises(IndicatorBelowThresholdError) as exc_info:
        await registry.assert_eligible("UNTOUCHED", threshold=0.55)
    assert exc_info.value.current_avg is None
    assert exc_info.value.threshold == 0.55


@pytest.mark.asyncio
async def test_assert_eligible_raises_when_below_min_samples():
    """Even a high observed avg fails the gate if <30 samples."""
    registry = IndicatorRegistry()
    for _ in range(MIN_SAMPLES_FOR_AVG - 1):
        await registry.record("SQZMOM_ENHANCED", 0.95, was_voted=True)
    with pytest.raises(IndicatorBelowThresholdError):
        await registry.assert_eligible("SQZMOM_ENHANCED", threshold=0.55)


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_record_no_data_loss_and_capped():
    """Many tasks recording in parallel — buffer capped at maxlen, no torn reads."""
    registry = IndicatorRegistry()
    # 500 concurrent appends — 2.5x the window, so eviction kicks in.
    n = 500
    await asyncio.gather(
        *[registry.record("BOLL", 0.6, was_voted=True) for _ in range(n)]
    )
    count = await registry.sample_count("BOLL")
    assert count == DEFAULT_WINDOW, f"expected cap at {DEFAULT_WINDOW}, got {count}"
    avg = await registry.rolling_average("BOLL")
    assert avg == pytest.approx(0.6, abs=1e-9)


@pytest.mark.asyncio
async def test_concurrent_record_mixed_indicators():
    """Independent indicators must not bleed into each other under concurrency."""
    registry = IndicatorRegistry()
    tasks = []
    for _ in range(100):
        tasks.append(registry.record("A", 0.9, was_voted=True))
        tasks.append(registry.record("B", 0.1, was_voted=True))
    await asyncio.gather(*tasks)
    assert await registry.sample_count("A") == 100
    assert await registry.sample_count("B") == 100
    assert await registry.rolling_average("A") == pytest.approx(0.9, abs=1e-9)
    assert await registry.rolling_average("B") == pytest.approx(0.1, abs=1e-9)


# ---------------------------------------------------------------------------
# Shadow-mode hook surface
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shadow_observations_tracked_separately():
    """was_voted=False must count as shadow, was_voted=True as vote."""
    registry = IndicatorRegistry()
    for _ in range(15):
        await registry.record("X", 0.5, was_voted=True)
    for _ in range(20):
        await registry.record("X", 0.5, was_voted=False)
    stats = await registry.stats("X")
    assert stats["votes_counted"] == 15
    assert stats["shadow_observations"] == 20
    # Both contribute to the rolling buffer regardless of was_voted.
    assert stats["sample_count"] == 35
    assert stats["rolling_avg"] == pytest.approx(0.5, abs=1e-9)


# ---------------------------------------------------------------------------
# Singleton + Prometheus gauge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_indicator_registry_returns_singleton():
    a = get_indicator_registry()
    b = get_indicator_registry()
    assert a is b


@pytest.mark.asyncio
async def test_prometheus_gauge_updates_after_min_samples():
    """Gauge should reflect the latest rolling-mean once we cross the floor."""
    registry = IndicatorRegistry()
    label = "GAUGE_TEST_INDICATOR"
    # Below floor: gauge unchanged (no .set() call).
    for _ in range(MIN_SAMPLES_FOR_AVG - 1):
        await registry.record(label, 0.42, was_voted=True)
    # One more record crosses the floor and should set the gauge.
    await registry.record(label, 0.42, was_voted=True)
    sample = INDICATOR_ROLLING_CONFIDENCE.labels(indicator=label)._value.get()
    assert sample == pytest.approx(0.42, abs=1e-9)


# ---------------------------------------------------------------------------
# Defensive
# ---------------------------------------------------------------------------


def test_window_must_be_positive():
    with pytest.raises(ValueError):
        IndicatorRegistry(window=0)
    with pytest.raises(ValueError):
        IndicatorRegistry(window=-1)
