"""ADX parity against an independent reference implementation.

Written 2026-08-21 as part of the Hybrid Strategy Routing repair. The routing
branch is `ADX >= adx_trending_threshold`, so a wrong or always-NaN ADX would
make one branch unreachable and the routing counters structurally lopsided.
This test proves the ADX the router consumes is the real Wilder ADX.

**Reference provenance.** The golden values below were produced by the
`ta` package (`ta.trend.ADXIndicator`, window=14, fillna=False) on the exact
series `make_series()` generates here, executed 2026-08-21. `ta` is NOT a
repo dependency and is deliberately not imported: baking the numbers in keeps
CI dependency-free and pins the expectation against a specific third-party
result rather than against whatever version happens to be installed. To
regenerate:

    python -m venv /tmp/taenv && /tmp/taenv/bin/pip install ta 'pandas<3'
    # feed make_series() output to ta.trend.ADXIndicator(...).adx().iloc[-1]

The series generator is a pure-Python LCG with no numpy/pandas randomness, so
it is byte-identical across platforms and library versions.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.indicators.adx import ADXCalculator, MarketRegime  # noqa: E402


def _lcg(seed: int):
    state = seed

    def rand() -> float:
        nonlocal state
        state = (1103515245 * state + 12345) % (2**31)
        return state / (2**31)

    return rand


def make_series(n: int, mode: str, seed: int):
    """Deterministic OHLC. `trend` drifts up; `range` mean-reverts to 100."""
    rand = _lcg(seed)
    highs, lows, closes = [], [], []
    price = 100.0
    for _ in range(n):
        if mode == "trend":
            price += 0.35 + (rand() - 0.5) * 1.2
        else:
            price += (100.0 - price) * 0.35 + (rand() - 0.5) * 2.0
        rng = 0.6 + rand() * 0.8
        highs.append(round(price + rng / 2, 4))
        lows.append(round(price - rng / 2, 4))
        closes.append(round(price, 4))
    return highs, lows, closes


# Golden values from `ta.trend.ADXIndicator(window=14, fillna=False)`.
REFERENCE = {
    "trend": {
        "adx": 92.81816683543182,
        "plus_di": 41.447526217120306,
        "minus_di": 0.47227131828285707,
        "seed": 12345,
    },
    "range": {
        "adx": 10.548820158362377,
        "plus_di": 24.159533435210655,
        "minus_di": 22.555881247536796,
        "seed": 777,
    },
}

# The service rounds its output to 2dp, so parity is asserted at that
# resolution. A real formula divergence (SMA instead of Wilder smoothing,
# wrong DM tie-breaking, off-by-one on the shift) moves ADX by whole points,
# not by hundredths — this tolerance is tight enough to catch every one of
# them and loose enough to survive float ordering.
TOLERANCE = 0.01


@pytest.mark.parametrize("mode", ["trend", "range"])
def test_adx_matches_ta_library_reference(mode):
    ref = REFERENCE[mode]
    highs, lows, closes = make_series(400, mode, ref["seed"])

    result = ADXCalculator(period=14).calculate(highs, lows, closes)

    assert result["adx"] == pytest.approx(ref["adx"], abs=TOLERANCE), (
        f"{mode}: service ADX {result['adx']} diverges from the ta-library "
        f"reference {ref['adx']:.4f}. The routing branch depends on this value."
    )
    assert result["plus_di"] == pytest.approx(ref["plus_di"], abs=TOLERANCE)
    assert result["minus_di"] == pytest.approx(ref["minus_di"], abs=TOLERANCE)


def test_adx_is_numeric_not_nan_on_both_regimes():
    """The 'always-NaN ADX' failure mode would make ADX >= 25 unreachable."""
    for mode in ("trend", "range"):
        highs, lows, closes = make_series(400, mode, REFERENCE[mode]["seed"])
        adx = ADXCalculator(period=14).calculate(highs, lows, closes)["adx"]
        assert isinstance(adx, float)
        assert adx == adx, f"{mode}: ADX is NaN"
        assert 0.0 <= adx <= 100.0, f"{mode}: ADX {adx} out of range"


def test_synthetic_series_straddle_the_routing_threshold():
    """Both routing branches must be reachable from real ADX values.

    If this fails the integration tests downstream are vacuous — they would be
    exercising one branch twice.
    """
    trend_adx = ADXCalculator(period=14).calculate(
        *make_series(400, "trend", REFERENCE["trend"]["seed"])
    )["adx"]
    range_adx = ADXCalculator(period=14).calculate(
        *make_series(400, "range", REFERENCE["range"]["seed"])
    )["adx"]

    assert trend_adx >= 25.0, f"trending series only reached ADX {trend_adx}"
    assert range_adx < 25.0, f"ranging series reached ADX {range_adx}"


def test_regime_classification_boundaries():
    """`_classify_regime` ladder, including the exact boundary values."""
    calc = ADXCalculator(
        period=14,
        weak_trend_threshold=20.0,
        trending_threshold=25.0,
        strong_trend_threshold=30.0,
    )
    assert calc._classify_regime(30.0) == MarketRegime.STRONG_TREND
    assert calc._classify_regime(29.999) == MarketRegime.TRENDING
    assert calc._classify_regime(25.0) == MarketRegime.TRENDING
    assert calc._classify_regime(24.999) == MarketRegime.WEAK_TREND
    assert calc._classify_regime(20.0) == MarketRegime.WEAK_TREND
    assert calc._classify_regime(19.999) == MarketRegime.RANGING
    assert calc._classify_regime(0.0) == MarketRegime.RANGING
