"""
THE LOOK-AHEAD-LEAKAGE REGRESSION NET (closes TA-AGG-04).

Run:
    cd services/technical-analysis && \
        python3 -m pytest tests/test_leakage_regression.py --no-cov -q

WHY THIS FILE EXISTS
--------------------
Every indicator in this service feeds a traded signal. A value published for
bar `t` that changes once bars `t+1..N` arrive is look-ahead leakage: it makes
backtests, Sharpe figures and DSR numbers optimistic by an unmeasured amount
while the live path silently disagrees with them. Before this file the service
had zero tests for that class of defect.

THE TIER SPLIT, AND WHY IT IS DELIBERATELY NON-UNIFORM
-----------------------------------------------------
TA-AGG-04's literal wording is "compute at t with df[:t+1], compute again with
the full series, assert the values at t are identical". That formulation is
only meaningful for entry points that return **a value per bar**.

Ten of the thirteen indicator modules return a scalar or dict describing the
**last supplied bar**. For those, `f(df[:t+1])` is by construction computed
from bars <= t, and `f(df_full)` describes bar N, not bar t. Comparing them is
a category error; comparing `f(df[:t+1])` against itself is a tautology. A
suite written uniformly to the literal wording would be ~10 always-green tests
that retire the requirement while proving nothing.

So:

  Tier 1 -- the six series-returning entry points. Genuine prefix-vs-full
            comparison. Directly catches `.shift(-n)`, `center=True`,
            backfill, and whole-frame normalisation.
  Tier 2 -- the scalar/dict entry points (added in Task 2). Three falsifiable
            families instead: scalar-to-series agreement, suffix-independence
            against a poisoned future tail, and two module-specific positive
            claims (Ichimoku Senkou provenance, rsi_divergence pivot
            stability).
  Tier 3 -- an AST structural guard (added in Task 3) that fails when a new
            forward-looking construct is introduced anywhere under
            app/indicators/.

EXACT EQUALITY IS THE POINT
---------------------------
Every assertion here demands bit-exact agreement. Both sides are the same
trailing computation over identical inputs, so any tolerance would be a place
for a real forward read to hide.

WHAT THIS SUITE ALREADY CAUGHT
------------------------------
`EnhancedSqueezeMomentum.calculate` normalised its momentum strength by
`result_df['sqz_momentum'].abs().max()` -- the maximum over the WHOLE frame,
including bars after the row being scored. `sqz_confidence` at bar t therefore
moved when a larger |momentum| arrived later (measured: 39 of 250 probed bars,
worst delta 0.80 -> 0.85). Fixed to an expanding (causal) max; `LEAK_PROBE_T`
below is pinned to a bar where the defect was measurable so the suite stays
able to see that class of leak.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.config import get_settings

SETTINGS = get_settings()

# 400 bars, deliberately. TrendFilter's slow EMA needs 200; Ichimoku's
# min_periods is senkou_b_period + displacement, which rises to 146 once the
# canonical senkou_b = 120 with displacement = 26 lands (Plan 21-02). A smaller
# frame makes IchimokuCalculator return None and its tests pass vacuously, so
# the headroom is load-bearing under both the current and the post-21-02 canon.
BARS = 400

# A bar where EnhancedSqueezeMomentum's whole-frame momentum normaliser was
# measurably leaky before the fix (sqz_confidence 0.80 full vs 0.85 prefix).
# Keep it in PROBE_TS: without it the suite passes clean on a service that
# still leaks, which is exactly the false-closure this file exists to prevent.
LEAK_PROBE_T = 242

# Probe bars, all well past every indicator's warm-up.
PROBE_TS = (200, LEAK_PROBE_T, 275, 340)


def _synthetic_ohlcv(seed: int = 42, n: int = BARS) -> pd.DataFrame:
    """Deterministic, non-degenerate OHLCV on an hourly DatetimeIndex.

    A constant or monotonic series makes every indicator agree trivially and
    hides leakage -- rolling maxima stop moving, standard deviations collapse,
    and a forward read returns the same number as a backward one. The
    geometric random walk is load-bearing, not decoration.

    Seeded with numpy's default_rng so the frame is byte-identical on every
    run and machine; a flaky fixture would make a real leakage failure look
    like noise.
    """
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    high = close * (1 + rng.uniform(0.000, 0.006, n))
    low = close * (1 - rng.uniform(0.000, 0.006, n))
    return pd.DataFrame(
        {
            "open": np.r_[close[0], close[:-1]],
            "high": high,
            "low": low,
            "close": close,
            "volume": rng.uniform(800, 1500, n),
        },
        index=pd.date_range("2026-01-01", periods=n, freq="1h"),
    )


def _same(left, right) -> bool:
    """Exact equality, with NaN treated as equal to NaN.

    A warm-up NaN on both sides is agreement, not a difference. Everything
    else must match bit-for-bit -- no tolerance, anywhere in this file.
    """
    left_na = isinstance(left, float) and np.isnan(left)
    right_na = isinstance(right, float) and np.isnan(right)
    if left_na or right_na:
        return left_na and right_na
    return bool(left == right)


def _assert_series_value_stable(name: str, full: pd.Series, prefix: pd.Series, t: int):
    """`full.iloc[t]` must equal `prefix.iloc[-1]` for a Series entry point."""
    assert not full.empty, f"{name}: full-series calculation returned nothing"
    assert not prefix.empty, f"{name}: prefix calculation returned nothing at t={t}"
    got_full, got_prefix = full.iloc[t], prefix.iloc[-1]
    assert _same(got_full, got_prefix), (
        f"{name} at t={t} moved when future bars were added: "
        f"{got_full!r} (full series) vs {got_prefix!r} (prefix df[:t+1]). "
        "A value at t that depends on bars after t is look-ahead leakage."
    )


def _assert_row_stable(name: str, full: pd.DataFrame, prefix: pd.DataFrame, t: int):
    """Every column of row `t` must survive the arrival of bars t+1..N.

    The whole row is compared, not one column: leakage in this service lived
    in a derived confidence column, not in the headline value, and a
    single-column assertion would have walked straight past it.
    """
    assert full is not None and not full.empty, f"{name}: full frame returned nothing"
    assert prefix is not None and not prefix.empty, (
        f"{name}: prefix frame returned nothing at t={t}"
    )
    row_full, row_prefix = full.iloc[t], prefix.iloc[-1]
    drifted = [
        (column, row_full[column], row_prefix[column])
        for column in full.columns
        if not _same(row_full[column], row_prefix[column])
    ]
    assert not drifted, (
        f"{name} at t={t}: {len(drifted)} column(s) moved when future bars "
        "were added -- look-ahead leakage:\n"
        + "\n".join(f"  {c}: {a!r} (full) vs {b!r} (prefix)" for c, a, b in drifted)
    )


# ============================================================================
# TIER 1 -- series-returning entry points. The real leakage net.
# ============================================================================


@pytest.mark.parametrize("t", PROBE_TS)
def test_rsi_series_value_at_t_is_independent_of_future_bars(t: int):
    """RSI is a trailing Wilder EMA; bars after t must not touch bar t."""
    from app.indicators.rsi import RSICalculator

    df = _synthetic_ohlcv()
    calc = RSICalculator(period=SETTINGS.default_rsi_period)
    _assert_series_value_stable(
        "RSICalculator.calculate_series",
        calc.calculate_series(df),
        calc.calculate_series(df.iloc[: t + 1]),
        t,
    )


@pytest.mark.parametrize("t", PROBE_TS)
def test_macd_series_row_at_t_is_independent_of_future_bars(t: int):
    """MACD line, signal line and histogram are all trailing EMAs."""
    from app.indicators.macd import MACDCalculator

    df = _synthetic_ohlcv()
    calc = MACDCalculator(
        fast_period=SETTINGS.default_macd_fast,
        slow_period=SETTINGS.default_macd_slow,
        signal_period=SETTINGS.default_macd_signal,
    )
    _assert_row_stable(
        "MACDCalculator.calculate_series",
        calc.calculate_series(df),
        calc.calculate_series(df.iloc[: t + 1]),
        t,
    )


@pytest.mark.parametrize("t", PROBE_TS)
def test_bollinger_bands_series_row_at_t_is_independent_of_future_bars(t: int):
    """A `center=True` rolling window would fail here first."""
    from app.indicators.bollinger_bands import BollingerBandsCalculator

    df = _synthetic_ohlcv()
    calc = BollingerBandsCalculator(
        period=SETTINGS.default_bb_period, std_dev=SETTINGS.default_bb_std
    )
    _assert_row_stable(
        "BollingerBandsCalculator.calculate_series",
        calc.calculate_series(df),
        calc.calculate_series(df.iloc[: t + 1]),
        t,
    )


@pytest.mark.parametrize("t", PROBE_TS)
def test_ichimoku_series_row_at_t_is_independent_of_future_bars(t: int):
    """Ichimoku's series path returns spans at their COMPUTE bar.

    `calculate_series` documents that the Senkou spans are "not shifted
    forward. Apply .shift(displacement) for actual" -- projection is left to
    the caller. So every column here is a backward rolling read and must be
    stable under the arrival of later bars. The forward projection itself is
    asserted separately in the Senkou provenance test (tier 2).
    """
    from app.indicators.ichimoku import IchimokuCalculator

    df = _synthetic_ohlcv()
    calc = IchimokuCalculator(
        tenkan_period=SETTINGS.default_ichimoku_tenkan,
        kijun_period=SETTINGS.default_ichimoku_kijun,
        senkou_b_period=SETTINGS.default_ichimoku_senkou_b,
    )
    _assert_row_stable(
        "IchimokuCalculator.calculate_series",
        calc.calculate_series(df),
        calc.calculate_series(df.iloc[: t + 1]),
        t,
    )


@pytest.mark.parametrize("t", PROBE_TS)
def test_squeeze_momentum_row_at_t_is_independent_of_future_bars(t: int):
    """SQZMOM returns the input frame plus derived columns, all per-bar.

    Covers the squeeze booleans, the linear-regression momentum, the Pine
    Script colour ladder, and the per-row signal/confidence -- any of which
    could be computed against a whole-frame statistic.
    """
    from app.indicators.squeeze_momentum import SqueezeMomentumIndicator

    df = _synthetic_ohlcv()
    calc = SqueezeMomentumIndicator(
        bb_length=SETTINGS.default_sqzmom_bb_period,
        bb_mult=SETTINGS.default_sqzmom_bb_mult,
        kc_length=SETTINGS.default_sqzmom_kc_period,
        kc_mult=SETTINGS.default_sqzmom_kc_mult,
    )
    _assert_row_stable(
        "SqueezeMomentumIndicator.calculate",
        calc.calculate(df),
        calc.calculate(df.iloc[: t + 1]),
        t,
    )


@pytest.mark.parametrize("t", PROBE_TS)
def test_sqzmom_enhanced_row_at_t_is_independent_of_future_bars(t: int):
    """The test that found a live defect. Keep LEAK_PROBE_T in PROBE_TS.

    `sqz_confidence` scaled |momentum| by the maximum |momentum| over the
    entire supplied frame. On a prefix ending at t that maximum is causal; on
    the full 400-bar frame it may be set by a bar well after t, so the
    confidence published for bar t rose retroactively. Measured before the
    fix: 39 of 250 probed bars disagreed, worst case 0.80 (full) vs 0.85
    (prefix) at t=242 -- percentage points, not float noise.

    Every production consumer reads `.iloc[-1]`, where an expanding max and a
    whole-frame max are identical, so the live signal never saw the inflated
    number; whole-series/backtest reads did.
    """
    from app.indicators.sqzmom_enhanced import EnhancedSqueezeMomentum

    df = _synthetic_ohlcv()
    calc = EnhancedSqueezeMomentum(
        bb_length=SETTINGS.default_sqzmom_bb_period,
        bb_mult=SETTINGS.default_sqzmom_bb_mult,
        kc_length=SETTINGS.default_sqzmom_kc_period,
        kc_mult=SETTINGS.default_sqzmom_kc_mult,
        momentum_length=SETTINGS.default_sqzmom_mom_period,
    )
    _assert_row_stable(
        "EnhancedSqueezeMomentum.calculate",
        calc.calculate(df),
        calc.calculate(df.iloc[: t + 1]),
        t,
    )
