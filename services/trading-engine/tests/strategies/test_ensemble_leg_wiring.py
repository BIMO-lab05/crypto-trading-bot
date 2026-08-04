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


def _atr(value: float):
    return IndicatorSignal(
        name="ATR",
        signal=SignalAction.HOLD,
        confidence=0.3,
        value=value,
        metadata={"weight": 1.0},
    )


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

    assert (
        SimpleRSIStrategy().generate_signal({"RSI": sig}, current_price=100.0) is None
    )


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
        metadata={"atr_stop_loss": price * 0.98, "atr_take_profit": price * 1.03},
    )

    out = ensemble_module.MultiStrategyEnsemble().generate_signal(
        agg, current_price=price, capital=100.0
    )

    assert out is not None, (
        "ensemble must fire — the RSI leg alone clears the threshold"
    )
    assert out.action == SignalAction.SELL, (
        f"RSI 77.95 SELL must outweigh a 0.174 multi-indicator BUY, got {out.action}"
    )
    assert ensemble_module.LEG_RSI in out.leg_contributions, (
        "RSI leg must appear in the attribution dict so PerformanceTracker can "
        "actually learn its weight"
    )
