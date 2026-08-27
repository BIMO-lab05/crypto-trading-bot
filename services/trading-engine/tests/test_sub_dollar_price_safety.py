"""
Sub-$1 price precision on the LIVE ensemble path (PRICE-01).

round(price, 4) is the 487d1bd defect class one order of magnitude down.
ADAUSDT trades near $0.61 against a 0.0001 tick, so four decimals quantize a
stop onto exactly ONE tick: every sub-tick component of the ATR stop offset is
destroyed before the value reaches the order layer. SimpleRSIStrategy is leg 1
of MultiStrategyEnsemble, so its stop_loss / take_profit become the orders the
paper engine fills - nothing downstream re-derives them.

The assertions are two-sided on purpose. Exact equality alone would pass the
moment someone reintroduced rounding at a coarser scale, so each directional
case also asserts the served value is NOT equal to its own 4dp rounding.

Tick-aware quantization belongs at order time (app/costs.py quantize_price),
never at the signal layer.
"""

from app.models.enums import SignalAction
from app.models.signal import IndicatorSignal
from app.strategies.simple_rsi_strategy import SimpleRSISignal, SimpleRSIStrategy

# Measured ADAUSDT 60m readings, quoted in _resolve_atr_fraction's docstring.
ADA_ATR_PCT = 1.4043
ADA_PRICE = 0.6137


def _atr_signal() -> IndicatorSignal:
    """ATR payload in the producer's declared unit: atr_pct is a PERCENT."""
    return IndicatorSignal(
        name="ATR",
        signal=SignalAction.HOLD,
        confidence=0.5,
        metadata={"atr_pct": ADA_ATR_PCT},
    )


def _rsi_signal(reading: float) -> IndicatorSignal:
    """RSI reading on .value, where SignalAggregator puts it (audit F-1)."""
    return IndicatorSignal(
        name="RSI",
        signal=SignalAction.HOLD,
        confidence=0.5,
        value=reading,
    )


def _expected_stop_distance() -> float:
    """Rebuild the strategy's stop distance bit-for-bit.

    The fraction is taken from _resolve_atr_fraction rather than typed as a
    decimal literal: the strategy derives it by dividing the percent reading,
    and the nearest double to that quotient is NOT the nearest double to the
    hand-typed decimal. A copied constant would make exact equality
    unreachable for reasons that have nothing to do with rounding.

    Multiplication order matches simple_rsi_strategy.py:198 exactly; float
    multiplication is not associative, so reordering breaks bit-equality.
    """
    fraction = SimpleRSIStrategy._resolve_atr_fraction(_atr_signal())
    return ADA_PRICE * fraction * SimpleRSIStrategy.ATR_STOP_MULT


def _signal(rsi_reading: float) -> SimpleRSISignal:
    """A directional signal at ADA scale, or a loud failure."""
    strategy = SimpleRSIStrategy()
    indicators = {"RSI": _rsi_signal(rsi_reading), "ATR": _atr_signal()}
    signal = strategy.generate_signal(indicators, ADA_PRICE)
    assert signal is not None, (
        f"RSI {rsi_reading} produced no signal; every assertion below would be vacuous"
    )
    return signal


def test_buy_stop_and_target_equal_the_unrounded_computation():
    """BUY stop_loss / take_profit must survive at full float precision."""
    signal = _signal(25.0)
    stop_distance = _expected_stop_distance()

    assert signal.action == SignalAction.BUY, (
        f"expected a BUY from an oversold reading, got {signal.action}"
    )

    expected_stop = ADA_PRICE - stop_distance
    assert signal.stop_loss == expected_stop, (
        f"stop_loss {signal.stop_loss!r} != unrounded {expected_stop!r}; "
        "round(price, 4) quantized the ADA stop onto a single tick"
    )

    expected_target = ADA_PRICE + stop_distance * SimpleRSIStrategy.REWARD_RISK
    assert signal.take_profit == expected_target, (
        f"take_profit {signal.take_profit!r} != unrounded "
        f"{expected_target!r}; round(price, 4) quantized the ADA target"
    )


def test_buy_stop_and_target_are_not_quantized_to_the_ada_tick():
    """The two-sided half: a coarser reintroduction must also fail here."""
    signal = _signal(25.0)

    assert signal.stop_loss != round(signal.stop_loss, 4), (
        f"stop_loss {signal.stop_loss!r} is still quantized to 4dp - exactly the ADAUSDT tick"
    )
    assert signal.take_profit != round(signal.take_profit, 4), (
        f"take_profit {signal.take_profit!r} is still quantized to 4dp"
    )


def test_sell_stop_and_target_survive_at_full_precision():
    """SELL inverts both legs; the precision requirement does not change."""
    signal = _signal(75.0)
    stop_distance = _expected_stop_distance()

    assert signal.action == SignalAction.SELL, (
        f"expected a SELL from an overbought reading, got {signal.action}"
    )

    expected_stop = ADA_PRICE + stop_distance
    assert signal.stop_loss == expected_stop, (
        f"stop_loss {signal.stop_loss!r} != unrounded {expected_stop!r} on the short side"
    )

    expected_target = ADA_PRICE - stop_distance * SimpleRSIStrategy.REWARD_RISK
    assert signal.take_profit == expected_target, (
        f"take_profit {signal.take_profit!r} != unrounded {expected_target!r} on the short side"
    )

    assert signal.stop_loss != round(signal.stop_loss, 4), (
        f"short stop_loss {signal.stop_loss!r} is still quantized to 4dp"
    )
    assert signal.take_profit != round(signal.take_profit, 4), (
        f"short take_profit {signal.take_profit!r} is still quantized to 4dp"
    )


def test_four_decimal_rounding_is_a_real_loss_not_float_noise():
    """Witness the defect class: the 4dp loss dwarfs representation error.

    Independent of the fix - it holds before and after - so it pins the
    premise the other three tests rest on. If this ever stops holding, the
    fixture drifted to a scale where 4dp is harmless and the regression
    stopped testing anything.
    """
    stop_distance = _expected_stop_distance()
    exact_stop = ADA_PRICE - stop_distance
    lost = abs(exact_stop - round(exact_stop, 4))

    assert lost > 1e-6, (
        f"4dp rounding of stop_loss {exact_stop!r} moves it by only {lost!r}; "
        "the fixture is no longer at a scale where this defect bites"
    )
