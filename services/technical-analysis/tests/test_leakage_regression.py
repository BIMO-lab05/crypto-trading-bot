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

import ast
from pathlib import Path
from unittest.mock import AsyncMock, patch

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


# ============================================================================
# TIER 2 -- scalar / dict entry points.
#
# These describe the LAST supplied bar, so `f(df[:t+1])` vs `f(df_full)` is a
# category error and `f(df[:t+1])` vs itself is a tautology. Three falsifiable
# families replace it:
#
#   (a) scalar-to-series agreement -- pins each scalar path to a series path
#       already proven leakage-free in tier 1, and would catch a scalar path
#       that secretly reads iloc[-1] of a whole-frame transform;
#   (b) suffix-independence -- the answer for bars <= t must not depend on
#       what came after, nor on what a previous call to the same instance saw;
#   (c) two module-specific positive claims (Ichimoku Senkou provenance,
#       rsi_divergence pivot stability), stated as things that MUST hold
#       rather than as exemptions.
# ============================================================================

# Wall-clock fields are a property of WHEN the call happened, not of the bars
# supplied. adx, atr, stochastic, trend_filter and volume_confirmation all
# stamp int(pd.Timestamp.now().timestamp() * 1000) into their payloads;
# leaving it in would make every comparison below red for a reason that has
# nothing to do with leakage.
_WALLCLOCK_KEYS = frozenset({"timestamp"})


def _canonical(payload):
    """Normalise an indicator payload so two of them compare exactly.

    Recurses into the tuple that `ADXCalculator.calculate_with_signal`
    returns. NaN becomes a sentinel so that warm-up NaN on both sides reads
    as agreement; no numeric tolerance is introduced anywhere.
    """
    if isinstance(payload, dict):
        return {
            key: _canonical(value)
            for key, value in payload.items()
            if key not in _WALLCLOCK_KEYS
        }
    if isinstance(payload, (list, tuple)):
        return type(payload)(_canonical(value) for value in payload)
    if isinstance(payload, np.floating):
        payload = float(payload)
    if isinstance(payload, float) and np.isnan(payload):
        return "<nan>"
    return payload


def _poisoned_prefix(df: pd.DataFrame, t: int) -> pd.DataFrame:
    """Bars <= t byte-identical to `df`; everything after is a different walk.

    Returned already truncated at t+1, so the callee is handed a frame whose
    parent object carries a different future. Any answer that differs from the
    clean prefix's answer came from somewhere other than the bars supplied.
    """
    poison = _synthetic_ohlcv(seed=1337)
    joined = pd.concat([df.iloc[: t + 1], poison.iloc[t + 1 :]])
    assert joined.iloc[: t + 1].equals(df.iloc[: t + 1]), "poison leaked backwards"
    assert not joined.iloc[t + 1 :].equals(df.iloc[t + 1 :]), "tail is not poisoned"
    return joined.iloc[: t + 1]


# ---------------------------------------------------------------------------
# (a) scalar-to-series agreement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("t", PROBE_TS)
def test_rsi_scalar_path_agrees_with_leakage_free_series(t: int):
    """RSICalculator.calculate(df[:t+1]) == calculate_series(df).iloc[t]."""
    from app.indicators.rsi import RSICalculator

    df = _synthetic_ohlcv()
    calc = RSICalculator(period=SETTINGS.default_rsi_period)
    scalar = calc.calculate(df.iloc[: t + 1])
    series = calc.calculate_series(df).iloc[t]
    assert _same(scalar, series), (
        f"RSI scalar path at t={t} disagrees with the leakage-free series: "
        f"{scalar!r} vs {series!r}"
    )


@pytest.mark.parametrize("t", PROBE_TS)
def test_macd_scalar_path_agrees_with_leakage_free_series(t: int):
    """Every shared MACD component must match the series value at t."""
    from app.indicators.macd import MACDCalculator

    df = _synthetic_ohlcv()
    calc = MACDCalculator(
        fast_period=SETTINGS.default_macd_fast,
        slow_period=SETTINGS.default_macd_slow,
        signal_period=SETTINGS.default_macd_signal,
    )
    scalar = calc.calculate(df.iloc[: t + 1])
    row = calc.calculate_series(df).iloc[t]
    for field in ("macd_line", "signal_line", "histogram"):
        assert _same(scalar[field], row[field]), (
            f"MACD {field} at t={t}: scalar {scalar[field]!r} vs series "
            f"{row[field]!r}"
        )


@pytest.mark.parametrize("t", PROBE_TS)
def test_bollinger_bands_scalar_path_agrees_with_leakage_free_series(t: int):
    """Bands and bandwidth are computed twice in the module; pin them equal."""
    from app.indicators.bollinger_bands import BollingerBandsCalculator

    df = _synthetic_ohlcv()
    calc = BollingerBandsCalculator(
        period=SETTINGS.default_bb_period, std_dev=SETTINGS.default_bb_std
    )
    scalar = calc.calculate(df.iloc[: t + 1])
    row = calc.calculate_series(df).iloc[t]
    for field in ("upper_band", "middle_band", "lower_band", "bandwidth"):
        assert _same(scalar[field], row[field]), (
            f"BB {field} at t={t}: scalar {scalar[field]!r} vs series "
            f"{row[field]!r}"
        )


@pytest.mark.parametrize("t", PROBE_TS)
def test_ichimoku_scalar_path_agrees_with_leakage_free_series(t: int):
    """Tenkan/Kijun/Chikou read bar t; the Senkou spans read further back.

    `IchimokuCalculator.calculate` takes the cloud in force NOW from
    `iloc[-displacement]` of the unshifted span series. On a frame of length
    t+1 that is positional index `t + 1 - displacement` -- a strictly backward
    read, and the exact index the Senkou provenance test below pins.
    """
    from app.indicators.ichimoku import IchimokuCalculator

    df = _synthetic_ohlcv()
    calc = IchimokuCalculator(
        tenkan_period=SETTINGS.default_ichimoku_tenkan,
        kijun_period=SETTINGS.default_ichimoku_kijun,
        senkou_b_period=SETTINGS.default_ichimoku_senkou_b,
    )
    displacement = calc.displacement
    scalar = calc.calculate(df.iloc[: t + 1])
    series = calc.calculate_series(df)

    for field in ("tenkan_sen", "kijun_sen", "chikou_span"):
        assert _same(scalar[field], series.iloc[t][field]), (
            f"Ichimoku {field} at t={t}: scalar {scalar[field]!r} vs series "
            f"{series.iloc[t][field]!r}"
        )

    cloud_bar = t + 1 - displacement
    assert cloud_bar < t, "the cloud in force must be computed strictly before t"
    for field in ("senkou_span_a", "senkou_span_b"):
        assert _same(scalar[field], series.iloc[cloud_bar][field]), (
            f"Ichimoku {field} at t={t} does not match the span computed at "
            f"bar {cloud_bar}: {scalar[field]!r} vs "
            f"{series.iloc[cloud_bar][field]!r}"
        )


# ---------------------------------------------------------------------------
# (b) suffix-independence
# ---------------------------------------------------------------------------


def _make_rsi():
    from app.indicators.rsi import RSICalculator

    calc = RSICalculator(period=SETTINGS.default_rsi_period)
    return lambda frame: calc.calculate(frame)


def _make_macd():
    from app.indicators.macd import MACDCalculator

    calc = MACDCalculator(
        fast_period=SETTINGS.default_macd_fast,
        slow_period=SETTINGS.default_macd_slow,
        signal_period=SETTINGS.default_macd_signal,
    )
    return lambda frame: calc.calculate(frame)


def _make_bollinger_bands():
    from app.indicators.bollinger_bands import BollingerBandsCalculator

    calc = BollingerBandsCalculator(
        period=SETTINGS.default_bb_period, std_dev=SETTINGS.default_bb_std
    )
    return lambda frame: calc.calculate(frame)


def _make_sma():
    from app.indicators.moving_averages import SMACalculator

    calc = SMACalculator(period=SETTINGS.default_sma_period)
    return lambda frame: calc.calculate(frame)


def _make_ema():
    from app.indicators.moving_averages import EMACalculator

    calc = EMACalculator(period=SETTINGS.default_ema_period)
    return lambda frame: calc.calculate(frame)


def _make_ichimoku():
    from app.indicators.ichimoku import IchimokuCalculator

    calc = IchimokuCalculator(
        tenkan_period=SETTINGS.default_ichimoku_tenkan,
        kijun_period=SETTINGS.default_ichimoku_kijun,
        senkou_b_period=SETTINGS.default_ichimoku_senkou_b,
    )
    return lambda frame: calc.calculate(frame)


def _make_adx():
    from app.indicators.adx import ADXCalculator

    calc = ADXCalculator(period=SETTINGS.default_adx_period)
    return lambda frame: calc.calculate_with_signal(
        frame["high"].tolist(), frame["low"].tolist(), frame["close"].tolist()
    )


def _make_atr():
    from app.indicators.atr import ATR

    calc = ATR(period=SETTINGS.default_atr_period)
    return lambda frame: calc.calculate(
        frame["high"].tolist(),
        frame["low"].tolist(),
        frame["close"].tolist(),
        float(frame["close"].iloc[-1]),
    )


def _make_stochastic():
    from app.indicators.stochastic import Stochastic

    calc = Stochastic(
        period=SETTINGS.default_stochastic_period,
        smooth_k=SETTINGS.default_stochastic_smooth_k,
        smooth_d=SETTINGS.default_stochastic_smooth_d,
    )
    return lambda frame: calc.calculate(
        frame["high"].tolist(), frame["low"].tolist(), frame["close"].tolist()
    )


def _make_trend_filter():
    from app.indicators.trend_filter import TrendFilter

    calc = TrendFilter(
        fast_period=SETTINGS.default_trend_fast_period,
        slow_period=SETTINGS.default_trend_slow_period,
    )
    return lambda frame: calc.calculate(frame["close"].tolist())


def _make_volume_confirmation():
    from app.indicators.volume_confirmation import VolumeConfirmation

    calc = VolumeConfirmation(period=SETTINGS.default_volume_period)
    return lambda frame: calc.calculate(
        frame["volume"].tolist(), SETTINGS.default_volume_signal_type
    )


def _make_rsi_divergence():
    from app.indicators.rsi_divergence import RSIDivergenceCalculator

    calc = RSIDivergenceCalculator(
        rsi_period=SETTINGS.default_rsi_divergence_period,
        lookback=SETTINGS.default_rsi_divergence_lookback,
    )
    return lambda frame: calc.calculate(frame)


# Every tier-2 entry point in the service. Input shapes differ deliberately:
# adx/atr/stochastic take three price lists, atr also a current price,
# trend_filter a price list, volume_confirmation a volume list plus a signal
# type. Each factory returns a closure over ONE calculator instance, so the
# two calls in the test below also exercise instance-level state carry-over
# (EnhancedSqueezeMomentum, for one, keeps _squeeze_history on self).
TIER2_ENTRY_POINTS = (
    ("rsi.calculate", _make_rsi),
    ("macd.calculate", _make_macd),
    ("bollinger_bands.calculate", _make_bollinger_bands),
    ("moving_averages.SMACalculator.calculate", _make_sma),
    ("moving_averages.EMACalculator.calculate", _make_ema),
    ("ichimoku.calculate", _make_ichimoku),
    ("adx.calculate_with_signal", _make_adx),
    ("atr.calculate", _make_atr),
    ("stochastic.calculate", _make_stochastic),
    ("trend_filter.calculate", _make_trend_filter),
    ("volume_confirmation.calculate", _make_volume_confirmation),
    ("rsi_divergence.calculate", _make_rsi_divergence),
)


@pytest.mark.parametrize("t", PROBE_TS)
@pytest.mark.parametrize(
    "name,factory", TIER2_ENTRY_POINTS, ids=[n for n, _ in TIER2_ENTRY_POINTS]
)
def test_tier2_entry_point_ignores_a_poisoned_future_tail(name, factory, t: int):
    """Bars after t must not reach the answer, by any route.

    Trivially true for a correct implementation -- which is the point: it
    fails loudly if a function closes over an outer frame, caches globally,
    carries state on the instance between calls, or mutates its input. All
    real hazards in a service that fans out twelve indicator calls behind a
    30-second kline cache.
    """
    df = _synthetic_ohlcv()
    clean = df.iloc[: t + 1]
    poisoned = _poisoned_prefix(df, t)
    before = clean.copy(deep=True)

    invoke = factory()
    first = _canonical(invoke(clean))
    second = _canonical(invoke(poisoned))

    assert first == second, (
        f"{name} at t={t} answered differently for two frames that are "
        f"identical through bar t. Bars after t reached the result:\n"
        f"  clean:    {first!r}\n  poisoned: {second!r}"
    )
    assert clean.equals(before), (
        f"{name} mutated the DataFrame it was given. A shared frame is fanned "
        "out to twelve indicators in this service; in-place edits corrupt "
        "every later leg."
    )


# ---------------------------------------------------------------------------
# (c) module-specific positive claims
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("t", PROBE_TS)
def test_ichimoku_senkou_spans_derive_only_from_bars_before_t(t: int):
    """The Senkou forward shift is a CALLER-side projection, not an input.

    CONTEXT records the Senkou forward-shift as intentional. That is satisfied
    here as a positive, falsifiable claim rather than an exemption:
    `calculate_series` states in its own docstring that spans are "not shifted
    forward. Apply .shift(displacement) for actual", i.e. it returns each span
    aligned to the bar that computed it. `calculate` then reads
    `iloc[-displacement]`, a strictly BACKWARD read, and the private detectors
    apply `.shift(+displacement)`, which moves values later in time -- also
    backward-looking.

    So the cloud reported for a frame ending at t must be reproducible from a
    frame that ends `displacement - 1` bars earlier and has never seen bar t.
    """
    from app.indicators.ichimoku import IchimokuCalculator

    df = _synthetic_ohlcv()
    calc = IchimokuCalculator(
        tenkan_period=SETTINGS.default_ichimoku_tenkan,
        kijun_period=SETTINGS.default_ichimoku_kijun,
        senkou_b_period=SETTINGS.default_ichimoku_senkou_b,
    )
    displacement = calc.displacement
    reported = calc.calculate(df.iloc[: t + 1])

    # A frame of length t+1 takes its cloud from positional index
    # t + 1 - displacement, so the provenance frame must END on that bar.
    provenance_end = t + 2 - displacement
    assert provenance_end <= t, "provenance frame must not contain bar t"
    provenance = calc.calculate_series(df.iloc[:provenance_end]).iloc[-1]

    for field in ("senkou_span_a", "senkou_span_b"):
        assert _same(reported[field], provenance[field]), (
            f"Ichimoku {field} reported for bar t={t} is NOT reproducible "
            f"from bars <= {provenance_end - 1}: {reported[field]!r} vs "
            f"{provenance[field]!r}. That would mean a future bar fed the "
            "cloud in force now."
        )

    # Chikou's comparison price is likewise a plain backward read.
    assert _same(
        reported["chikou_comparison_price"],
        float(df["close"].iloc[t - displacement]),
    ), "chikou_comparison_price must be the close displacement bars before t"


@pytest.mark.parametrize("t", PROBE_TS)
def test_rsi_divergence_pivots_are_confirmed_lagged_not_repainted(t: int):
    """The one real repainting-shaped site in the service -- and it is sound.

    `_find_pivot_lows` / `_find_pivot_highs` confirm a pivot at index i using
    `series.iloc[i+1:i+threshold+1]` -- bars AFTER i. Within a single
    `f(df[:t+1])` call every one of those bars is still <= t, and the loop
    bound `range(threshold, len(series) - threshold)` means the newest
    `threshold` bars are never reported. The signal is therefore LAGGED, not
    leaky, which is correct behaviour.

    Two assertions make that a claim rather than an excuse:
      (a) pivots at indices <= t - threshold are identical between the prefix
          and the full series. A failure here IS leakage.
      (b) no pivot at an index in (t - threshold, t] appears in the prefix
          result -- the calculator never claims a pivot it cannot yet confirm.

    Context for whoever reads a future failure: this module is deliberately
    disabled as a voter (trading-engine signal_aggregator.py:809), so a
    finding here is correctness debt, not a live trading defect. Do not
    escalate it as one. Nothing in this file is disabled or tolerated as an
    expected failure; both assertions are live.
    """
    from app.indicators.rsi_divergence import RSIDivergenceCalculator

    df = _synthetic_ohlcv()
    calc = RSIDivergenceCalculator(
        rsi_period=SETTINGS.default_rsi_divergence_period,
        lookback=SETTINGS.default_rsi_divergence_lookback,
    )
    threshold = calc.pivot_threshold
    rsi_full = calc._calculate_rsi(df)
    rsi_prefix = calc._calculate_rsi(df.iloc[: t + 1])

    for finder, label in (
        (calc._find_pivot_lows, "pivot lows"),
        (calc._find_pivot_highs, "pivot highs"),
    ):
        full_pivots = finder(rsi_full, threshold)
        prefix_pivots = finder(rsi_prefix, threshold)

        confirmed_full = [i for i in full_pivots if i <= t - threshold]
        confirmed_prefix = [i for i in prefix_pivots if i <= t - threshold]
        assert confirmed_prefix, (
            f"{label}: no confirmed pivots at t={t} -- the fixture is not "
            "exercising this code path, so the test would be vacuous"
        )
        assert confirmed_full == confirmed_prefix, (
            f"{label} at or before t-{threshold} moved when future bars "
            f"arrived (t={t}). That IS look-ahead leakage:\n"
            f"  full:   {confirmed_full}\n  prefix: {confirmed_prefix}"
        )

        unconfirmable = [i for i in prefix_pivots if t - threshold < i <= t]
        assert not unconfirmable, (
            f"{label}: the prefix ending at t={t} reported pivot(s) at "
            f"{unconfirmable}, which cannot be confirmed without bars after "
            "t. Reporting them would be repainting."
        )


# ---------------------------------------------------------------------------
# Aggregate endpoint path
# ---------------------------------------------------------------------------


async def _aggregate(frame: pd.DataFrame) -> dict:
    """Drive the handler with a mocked fetcher. No HTTP, no database.

    Patch target is `app.handlers.analysis.get_fetcher` and nothing else. The
    calculators are bound into that namespace at import time, and their
    failure defaults are NOT neutral -- ADX returns ("HOLD", 0.3), a SQZMOM
    HOLD is a flat 0.25, and VolumeConfirmation._reject_response() returns
    volume_ratio 0.0 -- so a patched leg would still cast a real vote and the
    test would measure the mock instead of the math. Every leg here runs on
    the real 400-bar frame.
    """
    from app.handlers.analysis import get_aggregated_signal

    fetcher = AsyncMock()
    fetcher.get_klines_as_dataframe = AsyncMock(return_value=frame)
    with patch("app.handlers.analysis.get_fetcher", return_value=fetcher):
        return await get_aggregated_signal(symbol="SOLUSDT", interval="60")


@pytest.mark.asyncio
@pytest.mark.parametrize("t", PROBE_TS)
async def test_aggregate_endpoint_ignores_a_poisoned_future_tail(t: int):
    """The whole twelve-leg funnel, end to end, must ignore bars after t.

    A prefix-vs-FULL comparison is not available here and would be wrong:
    `get_aggregated_signal` describes the last bar it is handed, so the full
    400-bar frame describes bar 399, not bar t. The falsifiable form is
    suffix-independence -- two frames identical through bar t must produce
    the same answer, including the derived confidence after the volume
    penalty ladder.
    """
    df = _synthetic_ohlcv()
    clean = await _aggregate(df.iloc[: t + 1])
    poisoned = await _aggregate(_poisoned_prefix(df, t))

    assert _canonical(clean) == _canonical(poisoned), (
        f"the aggregate endpoint answered differently at t={t} for two "
        f"frames identical through bar t:\n  clean:    {clean!r}\n"
        f"  poisoned: {poisoned!r}"
    )
    assert clean["signal"] in ("BUY", "SELL", "HOLD")


@pytest.mark.asyncio
@pytest.mark.parametrize("t", PROBE_TS)
async def test_aggregate_endpoint_fields_match_their_leakage_free_sources(t: int):
    """Transitively pin the endpoint to the tier-1-proven series values.

    `rsi` must be the leakage-free RSI series at bar t, and `sqzmom.confidence`
    must be the Enhanced SQZMOM confidence for bar t. The second is the
    highest-value assertion in this file: that leg is exactly where a
    whole-frame normaliser produced a retroactively inflated confidence, so a
    regression there would show up as a live signal-path defect, not just a
    backtest one.
    """
    from app.indicators.rsi import RSICalculator
    from app.indicators.sqzmom_enhanced import EnhancedSqueezeMomentum

    df = _synthetic_ohlcv()
    prefix = df.iloc[: t + 1]
    result = await _aggregate(prefix)

    rsi_series = RSICalculator(period=SETTINGS.default_rsi_period).calculate_series(df)
    assert result["rsi"] == round(float(rsi_series.iloc[t]), 2), (
        f"aggregate rsi at t={t} is {result['rsi']!r}, but the leakage-free "
        f"series says {round(float(rsi_series.iloc[t]), 2)!r}"
    )

    sqz = EnhancedSqueezeMomentum(
        bb_length=SETTINGS.default_sqzmom_bb_period,
        bb_mult=SETTINGS.default_sqzmom_bb_mult,
        kc_length=SETTINGS.default_sqzmom_kc_period,
        kc_mult=SETTINGS.default_sqzmom_kc_mult,
        momentum_length=SETTINGS.default_sqzmom_mom_period,
    ).calculate(prefix)
    expected_conf = round(float(sqz.iloc[-1]["sqz_confidence"]), 3)
    assert result["sqzmom"]["confidence"] == expected_conf, (
        f"aggregate sqzmom confidence at t={t} is "
        f"{result['sqzmom']['confidence']!r}, indicator says {expected_conf!r}"
    )

    # The endpoint must describe bar t, not some later bar. Derived from
    # df.index, not the wall clock, so it is safe to assert exactly.
    assert result["timestamp"] == int(df.index[t].timestamp() * 1000)


# ============================================================================
# TIER 3 -- AST structural guard over app/indicators/.
#
# Tiers 1 and 2 prove the indicators are clean TODAY, on one synthetic frame,
# at four probe bars. They cannot prove that the NEXT forward read will land
# on a bar the fixture happens to probe. This guard closes that gap by banning
# the constructs themselves.
#
# It exists because look-ahead leakage is silent: it never raises, never logs,
# and makes every backtest look better. Disabling this guard to make a build
# green is not an option -- if a new construct trips it, either the construct
# is a genuine forward read (fix it) or it is audited-safe (mark that ONE line
# and record the justification in the allowlist block below).
#
# Written fresh rather than copied from tests/test_price_rounding_invariant.py:
# that guard matches round() calls and inspects an integer ndigits, a
# completely different node shape. What IS copied, deliberately, is the shape
# of the discipline -- an explicit append-only file tuple, exactly one
# per-line escape comment, and failure messages that name file:line.
# ============================================================================

# This file lives in services/technical-analysis/tests/, so the indicator
# package is one level up. Do NOT copy the rounding guard's
# `REPO_ROOT = parents[1]`: that works because it sits at repo-root tests/,
# and here it would point at the service root instead.
INDICATORS_DIR = Path(__file__).resolve().parents[1] / "app" / "indicators"

# Every indicator module. Append only, alongside a fresh audit: adding a file
# here is a commitment that it is clean NOW. Never remove a file to make this
# pass, and never add one you have not just read.
SCANNED_FILES: tuple[str, ...] = (
    "adx.py",
    "atr.py",
    "bollinger_bands.py",
    "ichimoku.py",
    "macd.py",
    "moving_averages.py",
    "rsi.py",
    "rsi_divergence.py",
    "squeeze_momentum.py",
    "sqzmom_enhanced.py",
    "stochastic.py",
    "trend_filter.py",
    "volume_confirmation.py",
)

# The ONE line-level opt-out. Defining a second escape mechanism is how guards
# get disabled instead of obeyed, so there is exactly one and it is per line:
# marking one site never silences the next.
#
# ALLOWLIST -- audited 2026-08-27, two distinct justifications. They are NOT
# interchangeable; do not read one as precedent for the other.
#
#   rsi_divergence.py:181, :220 -- `series.iloc[i+1:i+threshold+1]` is a pivot
#     CONFIRMATION window. It reads bars after i, but the loop bound
#     `range(threshold, len(series) - threshold)` keeps every one of them
#     inside the frame the caller supplied, so the signal LAGS by `threshold`
#     bars rather than leaking. Pinned by the divergence test above.
#
#   ichimoku.py:506, :507 -- `senkou_a.shift(self.displacement)` is a POSITIVE
#     shift, which moves values LATER in time and is therefore backward
#     looking. It is marked only because the offset is an attribute rather
#     than a literal, so this guard cannot prove its sign; `displacement` is a
#     constructor parameter defaulting to 26 and a negative value would be a
#     configuration error, not a code path.
#
# Any NEW forward read must earn its own entry here, with its own reason.
ALLOW_MARKER = "# audited-forward-read"


def _shift_violation(node: ast.Call) -> str | None:
    """Reason a `.shift(...)` call is a forward read, or None if it is safe.

    `.shift(+n)` moves values LATER in time -- backward-looking, fine.
    `.shift(-n)` moves them EARLIER, pulling a future bar onto bar t. Both the
    literal form `.shift(-1)` (an ast.UnaryOp over a constant) and the
    variable form `.shift(-offset)` are caught.

    A non-literal offset is reported too. That is deliberate: a detector that
    waves through `.shift(offset)` fails GREEN the day `offset` is -1, and a
    guard that passes while a forward read sits in a file it claims to protect
    is worse than no guard. The two audited-positive sites carry ALLOW_MARKER.
    """
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "shift"):
        return None

    argument = None
    for keyword in node.keywords:
        if keyword.arg == "periods":
            argument = keyword.value
    if argument is None and node.args:
        argument = node.args[0]
    if argument is None:
        return None  # bare .shift() defaults to periods=1

    if isinstance(argument, ast.UnaryOp) and isinstance(argument.op, ast.USub):
        return ".shift(-n) pulls a FUTURE bar onto the current one"
    if isinstance(argument, ast.Constant) and isinstance(argument.value, int):
        if argument.value < 0:
            return ".shift() with a negative literal is a forward read"
        return None
    return (
        ".shift() offset is not a non-negative literal, so this guard "
        "cannot prove it is backward-looking"
    )


def _center_violation(node: ast.Call) -> str | None:
    """Reason a call carries `center=True`, or None.

    A centred rolling window straddles the current bar, so half of every
    window lies in the future. It is the quietest way to leak in pandas.
    """
    for keyword in node.keywords:
        if (
            keyword.arg == "center"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
        ):
            return "center=True puts half of every rolling window in the future"
    return None


def _forward_index_violation(node: ast.Subscript) -> str | None:
    """Reason an `.iloc[...]` reads past a loop variable, or None.

    Matches `series.iloc[i + 1]` and `series.iloc[i + 1 : i + k + 1]`, the
    shape of a confirmation window. `.iloc[i - k : i]`, `.iloc[-1]` and
    `.iloc[named_index]` are all backward or neutral and do not match.
    """
    value = node.value
    if not (isinstance(value, ast.Attribute) and value.attr == "iloc"):
        return None
    for inner in ast.walk(node.slice):
        if (
            isinstance(inner, ast.BinOp)
            and isinstance(inner.op, ast.Add)
            and isinstance(inner.left, ast.Name)
        ):
            return (
                f"positional read at an index after the loop variable "
                f"'{inner.left.id}'"
            )
    return None


def find_forward_violations(source: str, filename: str = "<fixture>") -> list[str]:
    """One human-readable violation string per forward-looking construct.

    A construct is exempt when its OWN source line carries ALLOW_MARKER. The
    check is per line, not per file: marking one site never silences another.
    """
    tree = ast.parse(source, filename=filename)
    source_lines = source.splitlines()
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            reason = _shift_violation(node) or _center_violation(node)
        elif isinstance(node, ast.Subscript):
            reason = _forward_index_violation(node)
        else:
            continue
        if reason is None:
            continue

        line = (
            source_lines[node.lineno - 1] if node.lineno <= len(source_lines) else ""
        )
        if ALLOW_MARKER in line:
            continue
        violations.append(
            f"{filename}:{node.lineno}: {reason}. A value published for bar t "
            "must not depend on bars after t -- leakage here is silent and "
            "inflates every backtest downstream. If this construct really is "
            f"backward-looking, append '{ALLOW_MARKER}' to that line AND "
            "record the justification in the allowlist block of "
            "tests/test_leakage_regression.py."
        )

    return sorted(set(violations))


FORWARD_NEGATIVE_FIXTURE = """
prev_close = frame["close"].shift(1)
gapped = frame["close"].shift(periods=2)
bare = series.shift()
filled = squeeze_on.shift(1, fill_value=False)
uncentred = series.rolling(window=20, center=False).mean()
plain_roll = series.rolling(window=20).mean()
backward = series.iloc[i - threshold:i]
newest = series.iloc[-1]
named = senkou_span_a.iloc[cloud_index]
projected = senkou_a.shift(self.displacement)  # audited-forward-read
confirm = series.iloc[i + 1:i + threshold + 1]  # audited-forward-read
"""

FORWARD_POSITIVE_FIXTURE = """
peek = series.shift(-1)
peek_kw = series.shift(periods=-2)
peek_var = series.shift(-offset)
unproven = senkou_a.shift(self.displacement)
centred = series.rolling(window=20, center=True).mean()
window = series.iloc[i + 1:i + threshold + 1]
"""

# One marked line and one unmarked violation of the SAME shape in the same
# source. The marker must exempt its own line only -- a file-wide or
# first-match-wins skip would report 0 here and the guard would be inert.
FORWARD_MARKER_LEAK_FIXTURE = """
allowed = series.shift(-1)  # audited-forward-read
leaked = series.shift(-1)
"""


def test_forward_guard_has_no_false_positives():
    """Backward and neutral constructs must not trip, marked lines included.

    Parsed in memory so this guarantee cannot drift when the live modules
    change.
    """
    violations = find_forward_violations(
        FORWARD_NEGATIVE_FIXTURE, "negative_fixture.py"
    )
    assert violations == [], "false positives:\n" + "\n".join(violations)


def test_forward_guard_detects_every_banned_shape():
    """All six forward-looking shapes are detected. No line here is marked.

    A detector that misses a shape fails GREEN, so the guard would pass while
    a forward read sat in a file it claims to protect. Each shape is asserted
    individually rather than by count alone.
    """
    violations = find_forward_violations(
        FORWARD_POSITIVE_FIXTURE, "positive_fixture.py"
    )
    rendered = "\n".join(violations)
    assert len(violations) == 6, (
        f"expected 6 violations, got {len(violations)}:\n{rendered}"
    )
    for lineno in range(2, 8):
        assert f"positive_fixture.py:{lineno}:" in rendered, (
            f"line {lineno} was not reported:\n{rendered}"
        )


def test_forward_guard_marker_does_not_leak_to_other_lines():
    """The opt-out is per line. Marking one site must not silence the next."""
    violations = find_forward_violations(
        FORWARD_MARKER_LEAK_FIXTURE, "leak_fixture.py"
    )
    rendered = "\n".join(violations)
    assert len(violations) == 1, (
        f"expected exactly 1 violation, got {len(violations)}:\n{rendered}"
    )
    assert "leak_fixture.py:3" in rendered, (
        f"the unmarked shift on line 3 must be the one reported:\n{rendered}"
    )


@pytest.mark.parametrize("module_name", SCANNED_FILES)
def test_scanned_indicator_module_exists(module_name: str):
    """A rename must not silently shrink this guard's coverage."""
    assert (INDICATORS_DIR / module_name).is_file(), (
        f"{module_name} is in SCANNED_FILES but does not exist under "
        f"{INDICATORS_DIR}. Update the tuple deliberately -- do not let a "
        "rename quietly reduce coverage."
    )


def test_every_indicator_module_is_scanned():
    """A NEW module must not be able to opt out by simply not being listed."""
    on_disk = {
        path.name
        for path in INDICATORS_DIR.glob("*.py")
        if path.name != "__init__.py"
    }
    unscanned = sorted(on_disk - set(SCANNED_FILES))
    assert not unscanned, (
        f"{unscanned} live under app/indicators/ but are not in "
        "SCANNED_FILES. Read them, confirm they are free of forward-looking "
        "constructs, then append them -- coverage is opt-out by default "
        "otherwise, which is how a guard rots."
    )


def test_no_forward_looking_constructs_in_indicators():
    """THE INVARIANT."""
    violations: list[str] = []
    for module_name in SCANNED_FILES:
        path = INDICATORS_DIR / module_name
        if not path.is_file():
            continue
        violations.extend(
            find_forward_violations(path.read_text(encoding="utf-8"), module_name)
        )

    assert not violations, (
        f"{len(violations)} forward-looking construct(s) in app/indicators/. "
        "Every one of these modules feeds a traded signal; a value at bar t "
        "that reads bars after t is look-ahead leakage. Never remove a file "
        "from SCANNED_FILES to make this pass:\n" + "\n".join(violations)
    )
