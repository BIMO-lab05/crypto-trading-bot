"""MACD belongs to TREND, not MOMENTUM.

MACD is a moving-average crossover, so counting it as MOMENTUM let the
category-diversity gate believe it had trend + momentum confirmation when both
agreeing voters were trend-followers. Measured over 8h of live logs it was the
sole non-TREND agreeing voter on 712 of 1,924 diversity passes.

See .planning/evidence/hold-funnel-2026-08-22.md
"""

import pytest

from app.aggregation.voter import INDICATOR_CATEGORIES, SignalVoter
from app.models.enums import SignalAction
from app.models.signal import IndicatorSignal


@pytest.fixture
def voter():
    return SignalVoter()


def test_macd_is_a_trend_indicator(voter):
    assert voter.get_indicator_category("MACD") == "TREND"


def test_macd_not_left_in_momentum():
    assert "MACD" not in INDICATOR_CATEGORIES["MOMENTUM"], (
        "MACD must not be counted in two buckets"
    )


def test_every_live_voter_is_categorised(voter):
    """No live voter may fall through to OTHER -- that silently inflates diversity."""
    live = [
        "RSI", "MACD", "STOCHASTIC", "SMA", "EMA",
        "ICHIMOKU", "ADX", "BOLLINGER_BANDS", "SQZMOM_ENHANCED",
    ]
    uncategorised = [n for n in live if voter.get_indicator_category(n) == "OTHER"]
    assert not uncategorised, f"uncategorised live voters: {uncategorised}"


def _sig(name: str, action: SignalAction) -> IndicatorSignal:
    return IndicatorSignal(
        name=name, signal=action, confidence=0.9, value=0.0, metadata={}
    )


def test_trend_plus_macd_alone_is_one_category(voter):
    """The case the old map got wrong: four trend-followers reading as two categories."""
    indicators = {
        "SMA": _sig("SMA", SignalAction.BUY),
        "EMA": _sig("EMA", SignalAction.BUY),
        "MACD": _sig("MACD", SignalAction.BUY),
        "RSI": _sig("RSI", SignalAction.SELL),
        "SQZMOM_ENHANCED": _sig("SQZMOM_ENHANCED", SignalAction.HOLD),
    }
    passes, count, _ = voter.check_category_diversity(
        indicators, SignalAction.BUY, min_categories=2
    )
    assert count == 1, f"SMA+EMA+MACD are all trend-followers, got {count} categories"
    assert not passes


def test_trend_plus_volatility_still_passes(voter):
    """The shape every real pass in the measured window had -- must keep passing."""
    indicators = {
        "SMA": _sig("SMA", SignalAction.BUY),
        "EMA": _sig("EMA", SignalAction.BUY),
        "MACD": _sig("MACD", SignalAction.BUY),
        "SQZMOM_ENHANCED": _sig("SQZMOM_ENHANCED", SignalAction.BUY),
        "RSI": _sig("RSI", SignalAction.SELL),
    }
    passes, count, _ = voter.check_category_diversity(
        indicators, SignalAction.BUY, min_categories=2
    )
    assert count == 2, f"TREND + VOLATILITY should be 2 categories, got {count}"
    assert passes
