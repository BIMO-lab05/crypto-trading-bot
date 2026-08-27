"""
ADX and Enhanced SQZMOM must vote; Volume must NOT vote.

All three are computed in this service and exposed as endpoints, but
get_aggregated_signal consulted only RSI, MACD and TrendFilter.

Volume is deliberately not a voter: its labels are CONFIRM/REJECT, which
would KeyError signal_weights[sig] into an HTTP 500, and it is directionally
agnostic - high volume confirms a breakdown as much as a breakout. The
trading-engine models it as a post-vote confidence multiplier
(aggregation/validator.py); this mirrors that.

Patching note: these tests MUST patch the calculators in the
app.handlers.analysis namespace. The fixture frame is 10 rows, below ADX's
29-bar minimum, SQZMOM's 25-bar minimum and Volume's 20-bar period, and
those failure defaults are NOT neutral: ADX returns ("HOLD", 0.3) and
VolumeConfirmation returns _reject_response() with volume_ratio 0.0. An
unpatched leg would therefore cast a real vote / apply a real penalty and
the test would be measuring the wrong thing.

Gating tests (TA-AGG-01 residue, 2026-08-26): the three cases below pin the
gates the handler applies BEFORE the generic weight > 0.0 filter. Each was
written against an observable that changes when its gate is deleted - see
each docstring for which one and why, because two of the three gates are
invisible in the response payload on their own.
"""

import logging
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest


def _make_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [100.0] * 10,
            "high": [101.0] * 10,
            "low": [99.0] * 10,
            "close": [100.0] * 10,
            "volume": [1000.0] * 10,
        },
        index=pd.DatetimeIndex([datetime(2026, 1, 1, i) for i in range(10)]),
    )


def _signal_enum(value: str):
    m = MagicMock()
    m.value = value
    return m


def _sqz_frame(signal: str, confidence: float) -> pd.DataFrame:
    return pd.DataFrame({"sqz_signal": [signal], "sqz_confidence": [confidence]})


def _patched(
    adx=("BUY", 0.8),
    sqz=("BUY", 0.9),
    volume_confirmed=True,
    volume_strength="STRONG",
    volume_ratio=1.6,
    capture=None,
):
    """Patch every leg so only the ones under test carry weight.

    `volume_ratio` is parametrized (2026-08-26) rather than pinned at 1.6:
    the handler reads it to tell ABSENCE of volume information from
    disconfirmation, and with a hardcoded 1.6 the absence branch was
    unreachable from this fixture. 1.6 remains the default so every test
    written before that change keeps the reading it was authored against.

    `capture`, when handed a dict, is filled with the CLASS mocks and the
    fetcher before the patcher is returned. patch.multiple treats a concrete
    MagicMock value as `new` rather than as a spec, so it is NOT yielded
    into the `with` target and a constructor's call_args would otherwise be
    unreachable. The return value stays the patcher itself, so every
    existing `with _patched(...):` call site is untouched.
    """
    fetcher = AsyncMock()
    fetcher.get_klines_as_dataframe = AsyncMock(return_value=_make_df())

    rsi_inst = MagicMock()
    rsi_inst.calculate.return_value = None
    macd_inst = MagicMock()
    macd_inst.calculate.return_value = None
    trend_inst = MagicMock()
    trend_inst.calculate.return_value = None

    adx_inst = MagicMock()
    adx_inst.calculate_with_signal.return_value = ({"adx": 30.0}, adx[0], adx[1])
    sqz_inst = MagicMock()
    sqz_inst.calculate.return_value = _sqz_frame(sqz[0], sqz[1])
    vol_inst = MagicMock()
    vol_inst.calculate.return_value = {
        "confirmed": volume_confirmed,
        "strength": volume_strength,
        "volume_ratio": volume_ratio,
        "confidence": 1.0,
    }

    class_mocks = {
        "RSICalculator": MagicMock(return_value=rsi_inst),
        "MACDCalculator": MagicMock(return_value=macd_inst),
        "TrendFilter": MagicMock(return_value=trend_inst),
        "ADXCalculator": MagicMock(return_value=adx_inst),
        "EnhancedSqueezeMomentum": MagicMock(return_value=sqz_inst),
        "VolumeConfirmation": MagicMock(return_value=vol_inst),
    }

    if capture is not None:
        capture.clear()
        capture.update(class_mocks)
        capture["get_fetcher_result"] = fetcher

    return patch.multiple(
        "app.handlers.analysis",
        get_fetcher=MagicMock(return_value=fetcher),
        **class_mocks,
    )


@pytest.mark.asyncio
async def test_adx_alone_can_carry_the_signal():
    """With RSI/MACD/trend dead, an ADX BUY must still produce BUY."""
    from app.handlers.analysis import get_aggregated_signal

    with _patched(adx=("BUY", 0.8), sqz=("HOLD", 0.0)):
        result = await get_aggregated_signal(symbol="SOLUSDT", interval="60")

    assert result["signal"] == "BUY", (
        f"ADX did not reach the vote; got {result['signal']!r}"
    )
    assert result["adx"]["signal"] == "BUY"


@pytest.mark.asyncio
async def test_sqzmom_alone_can_carry_the_signal():
    from app.handlers.analysis import get_aggregated_signal

    with _patched(adx=("HOLD", 0.0), sqz=("SELL", 0.9)):
        result = await get_aggregated_signal(symbol="SOLUSDT", interval="60")

    assert result["signal"] == "SELL", (
        f"SQZMOM did not reach the vote; got {result['signal']!r}"
    )
    assert result["sqzmom"]["signal"] == "SELL"


@pytest.mark.asyncio
async def test_unconfirmed_volume_penalizes_but_does_not_vote():
    """Volume must move confidence, never the label - and never KeyError."""
    from app.handlers.analysis import get_aggregated_signal

    with _patched(
        adx=("BUY", 0.8),
        sqz=("BUY", 0.9),
        volume_confirmed=True,
        volume_strength="STRONG",
    ):
        confirmed = await get_aggregated_signal(symbol="SOLUSDT", interval="60")

    with _patched(
        adx=("BUY", 0.8),
        sqz=("BUY", 0.9),
        volume_confirmed=False,
        volume_strength="WEAK",
    ):
        unconfirmed = await get_aggregated_signal(symbol="SOLUSDT", interval="60")

    assert confirmed["signal"] == unconfirmed["signal"] == "BUY", (
        "volume changed the direction - it must only scale confidence"
    )
    assert unconfirmed["confidence"] < confirmed["confidence"], (
        f"unconfirmed volume did not penalize confidence: "
        f"{unconfirmed['confidence']} vs {confirmed['confidence']}"
    )
    assert unconfirmed["volume"]["confirmed"] is False


@pytest.mark.asyncio
async def test_empty_vote_still_holds_with_the_new_legs_present():
    """Task 1's neutral fallback must survive the added legs."""
    from app.handlers.analysis import get_aggregated_signal

    with _patched(adx=("HOLD", 0.0), sqz=("HOLD", 0.0)):
        result = await get_aggregated_signal(symbol="SOLUSDT", interval="60")

    assert result["signal"] == "HOLD"
    assert result["confidence"] == 0.5


# ---------------------------------------------------------------------------
# Gating (TA-AGG-01 residue) - the three behaviours CONTEXT requires pinned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adx_zero_confidence_is_rejected_before_the_weight_filter(caplog):
    """A BUY label at confidence 0.0 is a dead calculator, not a weak opinion.

    ADX's failure default is ("HOLD", 0.3) rather than a neutral zero
    (adx.py:436-439). That is exactly why the handler cannot lean on the
    generic `weight > 0.0` filter at analysis.py:130 to keep a dead ADX out:
    it gates on the label being directional AND the confidence being strictly
    greater than zero, at analysis.py:114, before the tuple is ever appended.

    Asserting on the response alone would be TAUTOLOGICAL. Both filters
    produce the same HOLD/0.5 payload, so a payload-only test stays green
    with the :114 confidence clause deleted. The observable that
    discriminates is the AGGREGATOR_CONFIDENCE_FILTER log line, which fires
    only when a zero-confidence tuple actually entered the aggregation list
    and was then dropped. Silence proves the :114 gate ran first. The
    positive control at the end of this test proves the silence is
    meaningful rather than a log that never fires at all.
    """
    from app.handlers.analysis import get_aggregated_signal

    caplog.set_level(logging.INFO, logger="app.handlers.analysis")

    with _patched(adx=("BUY", 0.0), sqz=("HOLD", 0.0)):
        result = await get_aggregated_signal(symbol="SOLUSDT", interval="60")

    assert result["adx"] == {"signal": "BUY", "confidence": 0.0, "adx": 30.0}, (
        "the ADX leg did not run as configured, so this test is measuring "
        f"something other than the gate: {result['adx']!r}"
    )
    assert result["signal"] == "HOLD", (
        f"a zero-confidence ADX BUY carried the vote; got {result['signal']!r}"
    )
    assert result["confidence"] == 0.5, (
        "0.5 is the empty-vote neutral fallback; anything else means the "
        f"dead ADX contributed: {result['confidence']}"
    )
    assert "AGGREGATOR_CONFIDENCE_FILTER" not in caplog.text, (
        "the zero-confidence ADX tuple reached the aggregation list and was "
        "only caught by the generic weight filter at analysis.py:130 - the "
        "directional-and-conf>0 gate at analysis.py:114 did not run. "
        f"Log: {caplog.text!r}"
    )

    # Positive control. The assertion above is worth nothing unless
    # AGGREGATOR_CONFIDENCE_FILTER can fire at all, so drive a
    # zero-confidence directional vote through TrendFilter, which has no
    # such gate, and require the log. This patch is applied after
    # _patched()'s, so it wins on TrendFilter.
    trend_zero = MagicMock()
    trend_zero.calculate.return_value = {
        "trend": "BULLISH",
        "signal": "BUY",
        "confidence": 0.0,
    }
    caplog.clear()
    with (
        _patched(adx=("HOLD", 0.0), sqz=("HOLD", 0.0)),
        patch(
            "app.handlers.analysis.TrendFilter",
            MagicMock(return_value=trend_zero),
        ),
    ):
        await get_aggregated_signal(symbol="SOLUSDT", interval="60")

    assert "AGGREGATOR_CONFIDENCE_FILTER" in caplog.text, (
        "positive control failed: the drop-log never fires under any input, "
        "so its absence above proves nothing about the ADX gate"
    )


@pytest.mark.asyncio
async def test_sqzmom_hold_is_suppressed_however_confident_it_is():
    """Only directional SQZMOM labels vote; a 0.9 HOLD must stay out.

    SQZMOM's HOLD is a flat 0.25 by construction
    (sqzmom_enhanced.py:687-688), so its confidence carries no information
    about whether the leg is alive. The handler therefore gates on the label
    alone at analysis.py:120 - unlike ADX, there is no confidence clause,
    and adding one would be wrong.

    With every other leg dead this IS falsifiable through the payload.
    Gated, the empty vote reaches the neutral HOLD fallback of 0.5. Ungated,
    a HOLD weight of 0.9 clears the weight > 0.0 filter and HOLD's
    share-of-total formula at analysis.py:169 returns 1.0. Note the case
    only stays falsifiable while no directional voter is present: HOLD is
    excluded from the directional denominator at analysis.py:160, so a leak
    would be invisible alongside a BUY.
    """
    from app.handlers.analysis import get_aggregated_signal

    with _patched(adx=("HOLD", 0.0), sqz=("HOLD", 0.9)):
        result = await get_aggregated_signal(symbol="SOLUSDT", interval="60")

    assert result["sqzmom"] == {"signal": "HOLD", "confidence": 0.9}, (
        "the SQZMOM leg did not run as configured, so this test is "
        f"measuring something other than the gate: {result['sqzmom']!r}"
    )
    assert result["signal"] == "HOLD"
    assert result["confidence"] == 0.5, (
        "a high-confidence SQZMOM HOLD entered the vote: confidence is "
        f"{result['confidence']} (0.5 is the empty-vote fallback; 1.0 is a "
        "HOLD that voted)"
    )


@pytest.mark.asyncio
async def test_volume_absence_is_not_disconfirmation():
    """volume_ratio == 0.0 passes through; a genuine weak read penalizes.

    A ratio of exactly 0.0 is VolumeConfirmation._reject_response()
    (volume_confirmation.py:129-140) - fewer than `period` bars, or an
    exception swallowed upstream. That is ABSENCE of information, and the
    trading-engine's validator ladder documents it as pass-through 1.0. A
    genuine sub-1.0 reading is a real measurement and takes the 0.5 penalty
    (volume_confirmation.py:108-111 classifies anything below 1.0 as
    INSUFFICIENT / not confirmed).

    Both runs must return the SAME label. Volume is not a voter; it may only
    scale confidence. The penalty field is asserted directly so the test
    pins WHICH ladder arm ran, not merely that some number moved.
    """
    from app.handlers.analysis import get_aggregated_signal

    with _patched(
        volume_confirmed=False,
        volume_strength="INSUFFICIENT",
        volume_ratio=0.0,
    ):
        absent = await get_aggregated_signal(symbol="SOLUSDT", interval="60")

    with _patched(
        volume_confirmed=False,
        volume_strength="INSUFFICIENT",
        volume_ratio=0.6,
    ):
        disconfirming = await get_aggregated_signal(symbol="SOLUSDT", interval="60")

    assert absent["signal"] == disconfirming["signal"] == "BUY", (
        "volume changed the direction - it must only scale confidence: "
        f"absent={absent['signal']!r} disconfirming={disconfirming['signal']!r}"
    )
    assert absent["volume"]["penalty"] == 1.0, (
        "volume_ratio 0.0 is absence and must pass through at 1.0; got "
        f"{absent['volume']['penalty']}"
    )
    assert disconfirming["volume"]["penalty"] == 0.5, (
        "a genuine sub-1.0 reading must take the 0.5 penalty; got "
        f"{disconfirming['volume']['penalty']}"
    )
    assert disconfirming["confidence"] < absent["confidence"], (
        "absence was penalized like disconfirmation: "
        f"{disconfirming['confidence']} vs {absent['confidence']}"
    )


# ---------------------------------------------------------------------------
# P21-6 - every aggregate-path parameter resolves from TA Settings
# ---------------------------------------------------------------------------
#
# These read the CLASS mock's call_args and compare against
# getattr(settings, field), never against a literal, so a canonical-value
# change in config.py stays auto-covered instead of turning this file red.
# The shape is borrowed from test_endpoint_defaults_from_settings.py's
# WIRED_* drift tables; the difference is that a constructor argument is not
# visible in the OpenAPI schema, so it has to be captured at call time.


async def _run_aggregate(**kwargs):
    """Drive the aggregate handler once and hand back the class mocks."""
    from app.handlers.analysis import get_aggregated_signal

    mocks = {}
    with _patched(capture=mocks, **kwargs):
        await get_aggregated_signal(symbol="SOLUSDT", interval="60")
    return mocks


async def _run_multi_timeframe(**kwargs):
    """Drive the multi-timeframe handler once and hand back the class mocks."""
    from app.handlers.analysis import get_multi_timeframe_analysis

    mocks = {}
    with _patched(capture=mocks, **kwargs):
        await get_multi_timeframe_analysis(symbol="SOLUSDT", timeframes="60")
    return mocks


def _assert_from_settings(call, label, pairs):
    """Assert a captured constructor call sourced every kwarg from Settings."""
    from app.handlers.analysis import settings

    assert call is not None, (
        f"{label} was never constructed - the handler no longer builds it, "
        "or the capture wiring in _patched() broke"
    )
    for kwarg, field in pairs:
        assert kwarg in call.kwargs, (
            f"{label} was constructed without {kwarg}=, so the call site "
            f"re-declares what settings.{field} already owns. "
            f"Captured call: {call!r}"
        )
        expected = getattr(settings, field)
        assert call.kwargs[kwarg] == expected, (
            f"{label}({kwarg}=) is {call.kwargs[kwarg]!r} but "
            f"settings.{field} is {expected!r} - the two have drifted"
        )


@pytest.mark.asyncio
async def test_trend_filter_is_constructed_from_settings():
    mocks = await _run_aggregate()
    _assert_from_settings(
        mocks["TrendFilter"].call_args,
        "TrendFilter",
        (
            ("fast_period", "default_trend_fast_period"),
            ("slow_period", "default_trend_slow_period"),
        ),
    )


@pytest.mark.asyncio
async def test_adx_calculator_is_constructed_from_settings():
    """All four ADX knobs, not just the period.

    The three thresholds decide the regime label the response publishes, so
    leaving them on constructor defaults would keep a second declaration
    alive next to settings.default_adx_*_threshold.
    """
    mocks = await _run_aggregate()
    _assert_from_settings(
        mocks["ADXCalculator"].call_args,
        "ADXCalculator",
        (
            ("period", "default_adx_period"),
            ("trending_threshold", "default_adx_trending_threshold"),
            ("weak_trend_threshold", "default_adx_weak_trend_threshold"),
            ("strong_trend_threshold", "default_adx_strong_trend_threshold"),
        ),
    )


@pytest.mark.asyncio
async def test_enhanced_sqzmom_is_constructed_from_settings():
    """Note the name mismatch: bb_length <- default_sqzmom_bb_period.

    EnhancedSqueezeMomentum spells its windows `*_length` while Settings
    spells them `*_period`, and momentum_length maps to mom_period. A
    plausible-looking `bb_period=` keyword would raise TypeError, so the
    mapping is pinned here rather than left to memory.
    """
    mocks = await _run_aggregate()
    _assert_from_settings(
        mocks["EnhancedSqueezeMomentum"].call_args,
        "EnhancedSqueezeMomentum",
        (
            ("bb_length", "default_sqzmom_bb_period"),
            ("bb_mult", "default_sqzmom_bb_mult"),
            ("kc_length", "default_sqzmom_kc_period"),
            ("kc_mult", "default_sqzmom_kc_mult"),
            ("momentum_length", "default_sqzmom_mom_period"),
        ),
    )


@pytest.mark.asyncio
async def test_volume_confirmation_period_and_signal_type_come_from_settings():
    """The signal type is an argument to .calculate(), not the constructor.

    It selects which volume band counts as confirmation, so a literal there
    is the same class of drift as a literal period - it just lives one call
    deeper.
    """
    from app.handlers.analysis import settings

    mocks = await _run_aggregate()
    _assert_from_settings(
        mocks["VolumeConfirmation"].call_args,
        "VolumeConfirmation",
        (("period", "default_volume_period"),),
    )

    calculate_call = mocks["VolumeConfirmation"].return_value.calculate.call_args
    assert calculate_call is not None, "VolumeConfirmation.calculate was not called"
    passed = (
        calculate_call.kwargs["signal_type"]
        if "signal_type" in calculate_call.kwargs
        else calculate_call.args[1]
    )
    assert passed == settings.default_volume_signal_type, (
        f"VolumeConfirmation.calculate got signal_type {passed!r} but "
        f"settings.default_volume_signal_type is "
        f"{settings.default_volume_signal_type!r}"
    )


@pytest.mark.asyncio
async def test_rsi_and_macd_stay_settings_sourced():
    """Regression guard on the two legs that were already correct.

    They are the shape the other four adopted; if the rewire had reached
    for a literal here the drift would be silent.
    """
    mocks = await _run_aggregate()
    _assert_from_settings(
        mocks["RSICalculator"].call_args,
        "RSICalculator",
        (("period", "default_rsi_period"),),
    )
    _assert_from_settings(
        mocks["MACDCalculator"].call_args,
        "MACDCalculator",
        (
            ("fast_period", "default_macd_fast"),
            ("slow_period", "default_macd_slow"),
            ("signal_period", "default_macd_signal"),
        ),
    )


@pytest.mark.asyncio
async def test_aggregate_kline_window_comes_from_settings(monkeypatch):
    """The window is floor-validated in config.py; a literal bypasses it.

    settings.default_aggregate_limit carries a cross-field validator that
    rejects a window too short to warm up the slowest leg. A `limit=200`
    literal at the call site would keep asking for 200 bars no matter what
    the operator sets, so the validator would guard nothing.

    NUMERIC AGREEMENT IS NOT ROUTING. The literal this replaced was itself
    200, so an equality check against the setting stays green over a
    hardcoded window - it pins the value, not the wiring. The second half of
    this test moves the setting and requires the request to follow, which is
    the assertion that actually fails on a regression to a literal.
    """
    from app.handlers.analysis import settings

    mocks = await _run_aggregate()
    call = mocks["get_fetcher_result"].get_klines_as_dataframe.call_args
    assert call.kwargs.get("limit") == settings.default_aggregate_limit, (
        f"aggregate kline fetch asked for limit={call.kwargs.get('limit')!r} "
        f"but settings.default_aggregate_limit is "
        f"{settings.default_aggregate_limit!r}"
    )

    monkeypatch.setattr(settings, "default_aggregate_limit", 250)
    moved = await _run_aggregate()
    moved_call = moved["get_fetcher_result"].get_klines_as_dataframe.call_args
    assert moved_call.kwargs.get("limit") == 250, (
        "the aggregate kline window did not follow "
        "settings.default_aggregate_limit, so it is still declared at the "
        f"call site (asked for {moved_call.kwargs.get('limit')!r})"
    )


@pytest.mark.asyncio
async def test_multi_timeframe_handler_is_settings_sourced_too(monkeypatch):
    """analyze_timeframe is the second copy of the same construction block.

    It builds its own TrendFilter and its own kline fetch, so fixing only
    get_aggregated_signal would leave half the defect in place.
    """
    from app.handlers.analysis import settings

    mocks = await _run_multi_timeframe()
    _assert_from_settings(
        mocks["TrendFilter"].call_args,
        "TrendFilter (multi-timeframe)",
        (
            ("fast_period", "default_trend_fast_period"),
            ("slow_period", "default_trend_slow_period"),
        ),
    )
    call = mocks["get_fetcher_result"].get_klines_as_dataframe.call_args
    assert call.kwargs.get("limit") == settings.default_aggregate_limit, (
        f"multi-timeframe kline fetch asked for "
        f"limit={call.kwargs.get('limit')!r} but "
        f"settings.default_aggregate_limit is "
        f"{settings.default_aggregate_limit!r}"
    )

    # Same routing proof as the aggregate path - see that test's docstring.
    monkeypatch.setattr(settings, "default_aggregate_limit", 250)
    moved = await _run_multi_timeframe()
    moved_call = moved["get_fetcher_result"].get_klines_as_dataframe.call_args
    assert moved_call.kwargs.get("limit") == 250, (
        "the multi-timeframe kline window did not follow "
        "settings.default_aggregate_limit, so it is still declared at the "
        f"call site (asked for {moved_call.kwargs.get('limit')!r})"
    )


@pytest.mark.asyncio
async def test_every_voter_parameter_follows_a_moved_setting(monkeypatch):
    """The equality assertions above cannot see a hardcoded-but-equal value.

    Every settings default this handler reads currently EQUALS the
    constructor default it replaced, so `assert kwargs[x] == settings.field`
    stays green against a hardcoded `ADXCalculator(period=14)`. That is the
    inversion trap CLAUDE.md names for the account size: a literal that
    agrees numerically is still unrouted, and it decouples silently the next
    time the declaration moves. Verified, not assumed - regressing the
    volume signal type to its literal left the per-field test green, and
    only this test caught it.

    So move every field to a value nothing else in the service carries and
    require each constructor to follow. Exact-dict equality is deliberate:
    it also catches a stray argument that Settings does not own.
    """
    from app.handlers.analysis import settings

    moved = {
        "default_trend_fast_period": 37,
        "default_trend_slow_period": 173,
        "default_adx_period": 11,
        "default_adx_trending_threshold": 27.5,
        "default_adx_weak_trend_threshold": 17.5,
        "default_adx_strong_trend_threshold": 33.5,
        "default_sqzmom_bb_period": 23,
        "default_sqzmom_bb_mult": 2.3,
        "default_sqzmom_kc_period": 19,
        "default_sqzmom_kc_mult": 1.7,
        "default_sqzmom_mom_period": 15,
        "default_volume_period": 26,
        "default_volume_signal_type": "continuation",
        "default_rsi_period": 13,
        "default_macd_fast": 7,
        "default_macd_slow": 31,
        "default_macd_signal": 4,
    }
    for field, value in moved.items():
        monkeypatch.setattr(settings, field, value)

    mocks = await _run_aggregate()

    expected = {
        "TrendFilter": {"fast_period": 37, "slow_period": 173},
        "ADXCalculator": {
            "period": 11,
            "trending_threshold": 27.5,
            "weak_trend_threshold": 17.5,
            "strong_trend_threshold": 33.5,
        },
        "EnhancedSqueezeMomentum": {
            "bb_length": 23,
            "bb_mult": 2.3,
            "kc_length": 19,
            "kc_mult": 1.7,
            "momentum_length": 15,
        },
        "VolumeConfirmation": {"period": 26},
        "RSICalculator": {"period": 13},
        "MACDCalculator": {
            "fast_period": 7,
            "slow_period": 31,
            "signal_period": 4,
        },
    }
    for label, kwargs in expected.items():
        call = mocks[label].call_args
        assert call.kwargs == kwargs, (
            f"{label} did not follow the moved settings: got {call.kwargs!r}, "
            f"expected {kwargs!r}. A parameter is still declared at the call "
            "site, or a new one was added without a Settings field."
        )

    calculate_call = mocks["VolumeConfirmation"].return_value.calculate.call_args
    passed = (
        calculate_call.kwargs["signal_type"]
        if "signal_type" in calculate_call.kwargs
        else calculate_call.args[1]
    )
    assert passed == "continuation", (
        f"the volume signal type did not follow settings: {passed!r}"
    )
