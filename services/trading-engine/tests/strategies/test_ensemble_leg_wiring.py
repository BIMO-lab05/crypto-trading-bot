"""
Tests for MultiStrategyEnsemble leg wiring (audit 2026-07-30, finding F-1).

Goal: all three ensemble legs must actually read the indicator payload the
engine produces. `SignalAggregator` puts an indicator's numeric reading on the
`IndicatorSignal.value` field; both the `simple_rsi` and `mean_reversion` legs
used to read `metadata["value"]`, which is never populated.

Consequences observed live before the fix (6h window, paper mode):

    $ docker compose logs --since 6h trading-engine \
        | grep -oE "legs=\\{[^}]*\\}" | sort | uniq -c
        126 legs={'multi_indicator': 'BUY'}

126/126 fired signals came from one leg. `simple_rsi` returned None on every
call; `mean_reversion` silently substituted neutral defaults (RSI 50.0, Bollinger
position 0.5) and so never reached a threshold. At the time of the audit ADAUSDT
was at RSI(9)=77.95 — overbought — and the bot took a BUY.

These tests pin the payload shape, not the strategy's opinion.
"""

import importlib

import pytest

from app.models.enums import SignalAction
from app.models.signal import IndicatorSignal, TradingSignal


# --- payload builders: shaped exactly like SignalAggregator's output ---------


def _atr_payload(price: float) -> dict:
    """The dict `signal_aggregator.fetch_atr` returns, which
    `aggregator_core._build_metadata` files under metadata["atr"].

    This test used to build flat "atr_stop_loss"/"atr_take_profit" keys —
    a shape no production writer has ever produced (2026-08-08 fix).
    """
    return {
        "atr": price * 0.02,
        "atr_pct": 2.0,
        "stop_loss_long": price * 0.98,
        "stop_loss_short": price * 1.02,
        "take_profit_long": price * 1.04,
        "take_profit_short": price * 0.96,
        "volatility": "NORMAL",
        "confidence": 0.7,
        "risk_reward_ratio": 2.0,
    }


def _rsi(value: float, action: SignalAction = SignalAction.SELL, confidence=0.52):
    """RSI as `signal_aggregator.fetch_rsi` actually builds it: numeric reading on
    `.value`, metadata carrying only period + aggregation weight."""
    return IndicatorSignal(
        name="RSI",
        signal=action,
        confidence=confidence,
        value=value,
        metadata={"period": 9, "weight": 1.0},
    )


def _bollinger(price: float, upper: float, lower: float):
    """Bollinger as the aggregator builds it — bands in metadata, no `position` key."""
    return IndicatorSignal(
        name="BOLLINGER_BANDS",
        signal=SignalAction.HOLD,
        confidence=0.3,
        value=price,
        metadata={
            "upper_band": upper,
            "middle_band": (upper + lower) / 2,
            "lower_band": lower,
            "weight": 1.0,
        },
    )


def _sma(value: float, current_price: float):
    return IndicatorSignal(
        name="SMA",
        signal=SignalAction.HOLD,
        confidence=0.3,
        value=value,
        metadata={"current_price": current_price, "period": 21, "weight": 0.8},
    )


def _atr(value: float, atr_pct: float = None, atr_fraction: float = None):
    """ATR as `multi_strategy_ensemble._atr_indicator` builds it.

    `.value` is the ABSOLUTE ATR (what `mean_reversion` reads through
    `numeric_value()`); the units live in metadata. `atr_pct` is a PERCENT,
    verbatim from the wire (`technical-analysis/app/indicators/atr.py:91`
    computes `(atr / current_price) * 100`); `atr_fraction` is that percent
    divided by 100 and is what `simple_rsi` multiplies against price.

    Both metadata keys are optional so the pre-P21-1 call sites in this file
    (which only ever needed `.value`) keep working unchanged.
    """
    metadata = {"weight": 1.0}
    if atr_pct is not None:
        metadata["atr_pct"] = atr_pct
    if atr_fraction is not None:
        metadata["atr_fraction"] = atr_fraction
    return IndicatorSignal(
        name="ATR",
        signal=SignalAction.HOLD,
        confidence=0.3,
        value=value,
        metadata=metadata,
    )


def _atr_failure_payload(price: float) -> dict:
    """`technical-analysis/app/indicators/atr.py::_default_response()`, verbatim.

    The failure payload is NOT empty: `atr` and `atr_pct` are both 0.0 while
    `stop_loss_long`/`stop_loss_short` are POPULATED at a 3% default nobody
    chose. That asymmetry is the whole reason `_atr_is_usable` exists — read
    naively, one payload gives three different answers about whether ATR is
    present.
    """
    return {
        "atr": 0.0,
        "atr_pct": 0.0,
        "stop_loss_long": float(price * 0.97),
        "stop_loss_short": float(price * 1.03),
        "take_profit_long": float(price * 1.06),
        "take_profit_short": float(price * 0.94),
        "volatility": "UNKNOWN",
        "confidence": 0.3,
        "description": "Insufficient data - using default 3% SL",
        "risk_reward_ratio": 2.0,
        "timestamp": 0,
    }


@pytest.fixture
def ensemble_module():
    import app.strategies.multi_strategy_ensemble as mod

    importlib.reload(mod)
    return mod


# --- F-1a: the RSI leg must read `.value` -----------------------------------


def test_simple_rsi_leg_fires_on_live_shaped_payload():
    """The exact ADAUSDT payload from the audit must produce a SELL, not None."""
    from app.strategies.simple_rsi_strategy import SimpleRSIStrategy

    indicators = {"RSI": _rsi(77.95)}

    out = SimpleRSIStrategy().generate_signal(indicators, current_price=0.1723)

    assert out is not None, (
        "RSI leg returned None on a live-shaped payload — it is reading "
        "metadata['value'] instead of the .value field"
    )
    assert out.action == SignalAction.SELL, f"RSI 77.95 is overbought, got {out.action}"
    assert out.confidence > 0.45


def test_simple_rsi_leg_still_reads_metadata_value_if_producer_uses_it():
    """Backward compatibility: a producer that writes the reading into metadata
    must keep working."""
    from app.strategies.simple_rsi_strategy import SimpleRSIStrategy

    sig = IndicatorSignal(
        name="RSI",
        signal=SignalAction.BUY,
        confidence=0.5,
        value=None,
        metadata={"value": 12.0, "period": 9},
    )

    out = SimpleRSIStrategy().generate_signal({"RSI": sig}, current_price=100.0)

    assert out is not None
    assert out.action == SignalAction.BUY, "RSI 12 is extreme oversold"


def test_simple_rsi_leg_returns_none_when_reading_absent():
    """No reading anywhere → None. Must not invent a neutral value."""
    from app.strategies.simple_rsi_strategy import SimpleRSIStrategy

    sig = IndicatorSignal(
        name="RSI", signal=SignalAction.HOLD, confidence=0.3, value=None, metadata={}
    )

    assert SimpleRSIStrategy().generate_signal({"RSI": sig}, current_price=100.0) is None


# --- F-1b: mean reversion must not fabricate neutral inputs -----------------


def test_mean_reversion_reads_value_field_and_fires_when_overbought():
    """Overbought RSI + price above the upper Bollinger band must produce a SELL."""
    from app.strategies.mean_reversion_strategy import MeanReversionStrategy

    price = 110.0
    indicators = {
        "RSI": _rsi(82.0),
        "BOLLINGER_BANDS": _bollinger(price, upper=108.0, lower=92.0),
        "SMA": _sma(100.0, price),
        "ATR": _atr(2.0),
    }

    out = MeanReversionStrategy().generate_signal(indicators, current_price=price)

    assert out is not None, (
        "mean-reversion leg returned None on a clearly overbought payload — "
        "it is reading metadata['value'] / metadata['position'] instead of the "
        "fields the aggregator emits"
    )
    assert out.action == SignalAction.SELL


def test_mean_reversion_returns_none_when_rsi_reading_absent():
    """Missing RSI reading must fail closed, not default to a neutral 50.0.

    The pre-fix code substituted 50.0 silently, so a broken payload scored as a
    calm market instead of surfacing as an error.
    """
    from app.strategies.mean_reversion_strategy import MeanReversionStrategy

    price = 110.0
    blank_rsi = IndicatorSignal(
        name="RSI", signal=SignalAction.HOLD, confidence=0.3, value=None, metadata={}
    )
    indicators = {
        "RSI": blank_rsi,
        "BOLLINGER_BANDS": _bollinger(price, upper=108.0, lower=92.0),
        "SMA": _sma(100.0, price),
        "ATR": _atr(2.0),
    }

    out = MeanReversionStrategy().generate_signal(indicators, current_price=price)

    assert out is None, "absent RSI reading must return None, not assume RSI=50"


def test_mean_reversion_skips_bollinger_when_bands_absent():
    """No bands and no explicit position → the BB checks contribute nothing.

    Pre-fix, `metadata.get('position', 0.5)` scored a fabricated mid-band reading.
    Here RSI alone is overbought but below the leg's alignment requirement, so the
    absence of BB input must leave the leg silent rather than tipping it either way.
    """
    from app.strategies.mean_reversion_strategy import MeanReversionStrategy

    bare_bb = IndicatorSignal(
        name="BOLLINGER_BANDS",
        signal=SignalAction.HOLD,
        confidence=0.3,
        value=None,
        metadata={"weight": 1.0},
    )
    indicators = {"RSI": _rsi(72.0), "BOLLINGER_BANDS": bare_bb}

    out = MeanReversionStrategy().generate_signal(indicators, current_price=110.0)

    assert out is None


def test_mean_reversion_does_not_raise_when_sma_atr_missing():
    """Latent UnboundLocalError: `sma_value` / `atr_value` were read at the
    signal-construction site but assigned only inside a conditional. Unreachable
    while the leg was dead; reachable as soon as it fires."""
    from app.strategies.mean_reversion_strategy import MeanReversionStrategy

    price = 110.0
    indicators = {
        "RSI": _rsi(85.0),
        "BOLLINGER_BANDS": _bollinger(price, upper=105.0, lower=95.0),
    }

    out = MeanReversionStrategy().generate_signal(indicators, current_price=price)

    assert out is not None
    assert out.action == SignalAction.SELL


# --- F-1c: end to end, the ensemble must invert on the audit's payload ------


def test_ensemble_votes_sell_when_rsi_leg_opposes_a_weak_multi_buy(ensemble_module):
    """The ADAUSDT case from the audit.

    Live: multi_indicator voted BUY at 0.174 and, with both other legs dead, the
    bot bought — while RSI(9) sat at 77.95. With the legs wired up the RSI leg
    votes SELL at ~0.69, the weighted score goes negative and clears the 0.10
    aggregation threshold, so the ensemble sells instead.
    """
    price = 0.1723
    agg = TradingSignal(
        symbol="ADAUSDT",
        timestamp=0,
        action=SignalAction.BUY,
        confidence=0.174,
        aggregated_score=0.174,
        consensus_count=3,
        indicators={
            "RSI": _rsi(77.95),
            "BOLLINGER_BANDS": _bollinger(price, upper=0.1765, lower=0.1558),
            "SMA": _sma(0.1659, price),
        },
        metadata={"atr": _atr_payload(price)},
    )

    out = ensemble_module.MultiStrategyEnsemble().generate_signal(
        agg, current_price=price, capital=100.0
    )

    assert out is not None, "ensemble must fire — the RSI leg alone clears the threshold"
    assert out.action == SignalAction.SELL, (
        f"RSI 77.95 SELL must outweigh a 0.174 multi-indicator BUY, got {out.action}"
    )
    assert ensemble_module.LEG_RSI in out.leg_contributions, (
        "RSI leg must appear in the attribution dict so PerformanceTracker can "
        "actually learn its weight"
    )


# --- P21-1: the ATR unit contract -------------------------------------------
#
# `indicators["ATR"]` was NEVER written, so the block at
# simple_rsi_strategy.py:60-69 was dead in production. It guessed the unit with
# `if atr_pct > 1.0: atr_pct /= 100`. The TA service emits `atr_pct` as a
# PERCENT (atr.py:91), and a sub-1% hourly ATR is an explicitly modelled regime
# (atr.py:94 buckets `atr_pct < 1.0` as LOW volatility) — so the guess is wrong
# for exactly the calm markets it is most likely to see.
#
# Measured against the running TA service on 2026-08-26 (60m):
#
#   BTCUSDT 0.6658  -> guessed 0.666  -> 133% stop -> NEGATIVE stop price
#   ETHUSDT 0.8376  -> guessed 0.838  -> 168% stop -> NEGATIVE stop price
#   BNBUSDT 0.7182  -> guessed 0.718  -> 144% stop -> NEGATIVE stop price
#   SOLUSDT 1.1065  -> guessed 0.01107 -> 2.2%  (correct by luck of the branch)
#   ADAUSDT 1.4043  -> guessed 0.01404 -> 2.8%  (correct by luck of the branch)
#
# Three of the five tradeable symbols were in the broken branch, and they are
# the three largest by notional. Threading real ATR without this contract ships
# negative stop-losses. These tests pin the contract, not the guess.


@pytest.mark.parametrize(
    "symbol,atr_pct,expected_fraction",
    [
        ("BTCUSDT", 0.6658, 0.006658),
        ("ETHUSDT", 0.8376, 0.008376),
        ("BNBUSDT", 0.7182, 0.007182),
        ("SOLUSDT", 1.1065, 0.011065),
        ("ADAUSDT", 1.4043, 0.014043),
    ],
)
def test_atr_percent_resolves_to_a_fraction_never_a_percent(symbol, atr_pct, expected_fraction):
    """`atr_pct` is a percent on the wire; the consumer must divide by 100.

    The pre-fix `if atr_pct > 1.0` heuristic left 0.6658 as 0.666 — a 66.6%
    ATR, which at the 2.0x stop multiplier is a 133% stop distance and a
    negative stop price.
    """
    from app.strategies.simple_rsi_strategy import SimpleRSIStrategy

    resolved = SimpleRSIStrategy._resolve_atr_fraction(_atr(1.0, atr_pct=atr_pct))

    assert resolved == pytest.approx(expected_fraction, rel=1e-9), (
        f"{symbol}: atr_pct={atr_pct} is a PERCENT and must resolve to "
        f"{expected_fraction}, got {resolved} "
        f"({'the >1.0 unit guess is still present' if resolved > 0.1 else 'wrong scale'})"
    )


@pytest.mark.parametrize(
    "atr_pct,expected_fraction",
    [(0.6658, 0.006658), (1.1065, 0.011065)],
)
def test_sub_one_percent_atr_produces_a_sub_one_percent_stop_distance(atr_pct, expected_fraction):
    """End-to-end through the leg: the derived stop distance stays sane.

    Asserted as a RATIO of entry, deliberately — not against the 4-decimal
    SL/TP rounding at simple_rsi_strategy.py:121-122, which Phase 22 rewrites.
    """
    from app.strategies.simple_rsi_strategy import SimpleRSIStrategy

    price = 100.0
    indicators = {"RSI": _rsi(15.0), "ATR": _atr(price * atr_pct / 100.0, atr_pct=atr_pct)}

    out = SimpleRSIStrategy().generate_signal(indicators, current_price=price)

    assert out is not None and out.action == SignalAction.BUY
    stop_distance_ratio = (price - out.stop_loss) / price
    assert stop_distance_ratio < 0.05, (
        f"atr_pct={atr_pct} produced a {stop_distance_ratio:.2%} stop distance — "
        f"the percent was consumed as a fraction (100x too wide)"
    )
    assert stop_distance_ratio == pytest.approx(
        expected_fraction * SimpleRSIStrategy.ATR_STOP_MULT, rel=1e-6
    )
    assert out.stop_loss > 0, "a negative stop price is the failure this test exists for"


def test_out_of_range_atr_fraction_falls_back_to_the_named_default(caplog):
    """A fraction outside (0, 1) must not size a trade. Fall back, and say so.

    4.2 is not a plausible ATR fraction under any unit convention; silently
    using it would place the stop 840% away from entry.
    """
    from app.strategies.simple_rsi_strategy import SimpleRSIStrategy

    with caplog.at_level("WARNING"):
        resolved = SimpleRSIStrategy._resolve_atr_fraction(_atr(1.0, atr_fraction=4.2))

    assert resolved == SimpleRSIStrategy.DEFAULT_ATR_FRACTION
    assert "4.2" in caplog.text, (
        "the unusable payload must be named in the log, not silently swallowed"
    )


def test_absent_atr_falls_back_to_the_named_default_without_inventing_one():
    """No ATR indicator at all → the documented default, not a fabricated value."""
    from app.strategies.simple_rsi_strategy import SimpleRSIStrategy

    assert SimpleRSIStrategy._resolve_atr_fraction(None) == (SimpleRSIStrategy.DEFAULT_ATR_FRACTION)


def test_absolute_atr_on_value_is_never_read_as_a_fraction(caplog):
    """The `or`-chain fall-through to numeric_value() is gone.

    `.value` is the ABSOLUTE ATR (BTC ~522). The old code fell through to it
    whenever `metadata['atr_pct']` was falsy — and 0.0 is exactly what
    atr.py:136 writes on FAILURE. That is the second route into the same 100x
    trap: 522 > 1.0 so the heuristic "corrected" it to 5.22, a 522% stop.
    """
    from app.strategies.simple_rsi_strategy import SimpleRSIStrategy

    with caplog.at_level("WARNING"):
        resolved = SimpleRSIStrategy._resolve_atr_fraction(_atr(522.0, atr_pct=0.0))

    assert resolved == SimpleRSIStrategy.DEFAULT_ATR_FRACTION, (
        f"atr_pct=0.0 is a FAILURE marker, not a reading; the leg must fall back "
        f"to its named default rather than read the absolute ATR, got {resolved}"
    )


# --- P21-1: the synthetic ATR indicator and the non-mutation guard -----------


def test_atr_indicator_carries_absolute_value_and_both_units(ensemble_module):
    """One IndicatorSignal serves both legs.

    `mean_reversion` reads `.value` through `numeric_value()` and needs ABSOLUTE
    price units; `simple_rsi` reads metadata and needs the FRACTION. Publishing
    both on one object is what makes a single synthetic entry sufficient.
    """
    price = 100.0
    agg = TradingSignal(
        symbol="SOLUSDT",
        timestamp=0,
        action=SignalAction.BUY,
        confidence=0.4,
        aggregated_score=0.4,
        consensus_count=3,
        indicators={},
        metadata={"atr": _atr_payload(price)},
    )

    atr_signal = ensemble_module.MultiStrategyEnsemble._atr_indicator(agg)

    assert atr_signal is not None
    assert atr_signal.name == "ATR"
    assert atr_signal.signal == SignalAction.HOLD
    assert atr_signal.numeric_value() == pytest.approx(price * 0.02), (
        "mean_reversion divides by this — it must be ABSOLUTE price units"
    )
    assert atr_signal.metadata["atr_pct"] == pytest.approx(2.0), (
        "atr_pct must be carried verbatim from the wire, still a percent"
    )
    assert atr_signal.metadata["atr_fraction"] == pytest.approx(0.02), (
        "atr_fraction must be atr_pct / 100"
    )
    assert 0.0 <= atr_signal.confidence <= 1.0


def test_generate_signal_does_not_mutate_the_shared_indicator_dict(ensemble_module):
    """The local copy is the ENTIRE safety mechanism — pin it.

    `aggregator_signal.indicators` is the same object handed to
    `hybrid_strategy.observe_regime` (auto_trader.py:4703) and reachable from
    `aggregation/signal_cache.py`, and `fetch_all_indicators` deliberately
    diverts ATR out of the voting dict (signal_aggregator.py:832-841) so it
    never reaches the voter.

    Neither `role` nor `weight: 0.0` would save us if the synthetic entry
    landed in the shared dict: `voter._is_non_voting` returns
    `role in {"GATEKEEPER", "VALIDATOR"}` and a PRESENT role short-circuits the
    NON_VOTING_NAMES fallback, which does not contain "ATR" either.
    """
    price = 0.1723
    shared_indicators = {
        "RSI": _rsi(77.95),
        "BOLLINGER_BANDS": _bollinger(price, upper=0.1765, lower=0.1558),
        "SMA": _sma(0.1659, price),
    }
    agg = TradingSignal(
        symbol="ADAUSDT",
        timestamp=0,
        action=SignalAction.BUY,
        confidence=0.174,
        aggregated_score=0.174,
        consensus_count=3,
        indicators=shared_indicators,
        metadata={"atr": _atr_payload(price)},
    )
    keys_before = set(agg.indicators)

    ensemble_module.MultiStrategyEnsemble().generate_signal(agg, current_price=price)

    assert "ATR" not in agg.indicators, (
        "the synthetic ATR leaked into the aggregator's shared indicator dict — "
        "it is now visible to the voter and to observe_regime"
    )
    assert set(agg.indicators) == keys_before


def test_the_failure_payload_makes_all_three_legs_agree_atr_is_absent(ensemble_module, caplog):
    """`atr.py::_default_response()` must read as ABSENT everywhere.

    One payload used to give three different answers: `_atr_levels` read the
    POPULATED stop_loss_long/short and silently traded an undeclared 3% stop,
    while any leg reading `atr`/`atr_pct` saw 0.0 and used its own 2% default.
    `_atr_is_usable` is the single predicate that resolves the asymmetry.
    """
    price = 100.0
    failure = _atr_failure_payload(price)
    assert failure["stop_loss_long"] > 0, (
        "the failure payload's populated stops are the point of this test"
    )

    agg = TradingSignal(
        symbol="BTCUSDT",
        timestamp=0,
        action=SignalAction.BUY,
        confidence=0.4,
        aggregated_score=0.4,
        consensus_count=3,
        indicators={},
        metadata={"atr": failure},
    )

    with caplog.at_level("ERROR"):
        levels = ensemble_module.MultiStrategyEnsemble._atr_levels(agg)
    indicator = ensemble_module.MultiStrategyEnsemble._atr_indicator(agg)

    assert levels == (
        ensemble_module.UNUSABLE_LEVEL,
        ensemble_module.UNUSABLE_LEVEL,
    ), "the 3% failure default must not present as a real ATR level"
    assert indicator is None, (
        "a zero ATR is not a reading — the synthetic indicator must not be built"
    )
    assert "BTCUSDT" in caplog.text
