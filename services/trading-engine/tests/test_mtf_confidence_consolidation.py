"""The consolidated signal's confidence must describe the action it carries.

signal_aggregator took ``adjusted_confidence`` from the PRIMARY (60m) timeframe
while overwriting ``action`` with ``mtf_analysis.consensus_action`` -- a blend of
all three timeframes' raw PRE-GATE scores (multi_timeframe.py:189-211, which
never reads the gated action). Two different quantities glued onto one object.

Worse, aggregator_core forces ``action = HOLD`` on gate failure but leaves
``confidence`` at the directional value that just failed, so a rejected signal
re-entered the pipeline as a trade candidate carrying its rejected confidence.

Measured over 8h of live logs, of 231 directional MTF consensuses:
  152 (65.8%) had ZERO timeframe whose gated action matched the consensus
   43         had exactly one
   36         had two, and those 36 are precisely the ones that emitted

So requiring at least one agreeing timeframe removes 152 laundered artifacts at
zero cost to real signals.

See .planning/evidence/hold-funnel-2026-08-22.md
"""

import pytest

from app.aggregation.multi_timeframe import (
    AlignmentStrength,
    MultiTimeframeAnalysis,
    TimeframeSignal,
)
from app.models import SignalAction
from app.signal_aggregator import consolidate_mtf_confidence


def _tf(interval, action, confidence, weight, score=0.0):
    return TimeframeSignal(
        interval=interval,
        action=action,
        confidence=confidence,
        score=score,
        weight=weight,
    )


def _analysis(tfs, consensus, modifier=1.0):
    return MultiTimeframeAnalysis(
        primary_action=tfs.get("60").action if "60" in tfs else SignalAction.HOLD,
        consensus_action=consensus,
        alignment_strength=AlignmentStrength.MODERATE,
        confidence_modifier=modifier,
        timeframe_signals=tfs,
        agreement_pct=0.0,
        reasoning="test",
    )


def test_confidence_is_weighted_over_agreeing_timeframes():
    tfs = {
        "15": _tf("15", SignalAction.BUY, 0.40, 0.20),
        "60": _tf("60", SignalAction.BUY, 0.60, 0.50),
        "240": _tf("240", SignalAction.HOLD, 0.90, 0.30),
    }
    action, conf = consolidate_mtf_confidence(
        _analysis(tfs, SignalAction.BUY), primary_confidence=0.60
    )
    # (0.40*0.20 + 0.60*0.50) / (0.20 + 0.50) = 0.38 / 0.70
    assert action == SignalAction.BUY
    assert conf == pytest.approx(0.38 / 0.70, abs=1e-9)


def test_hold_timeframe_is_excluded_from_the_blend():
    """A HOLD timeframe at high confidence must not inflate a directional signal."""
    tfs = {
        "15": _tf("15", SignalAction.BUY, 0.40, 0.20),
        "60": _tf("60", SignalAction.HOLD, 0.99, 0.50),
        "240": _tf("240", SignalAction.HOLD, 0.99, 0.30),
    }
    action, conf = consolidate_mtf_confidence(
        _analysis(tfs, SignalAction.BUY), primary_confidence=0.99
    )
    assert action == SignalAction.BUY
    assert conf == pytest.approx(0.40, abs=1e-9), (
        "only the agreeing 15m leg may set the confidence"
    )


def test_consensus_with_no_agreeing_timeframe_is_forced_to_hold():
    """The laundering case: 152 of 231 directional consensuses in the live window.

    Consensus is computed from pre-gate scores, so it can read BUY while every
    timeframe's gated action is HOLD. Nothing downstream should treat that as a
    tradeable direction.
    """
    tfs = {
        "15": _tf("15", SignalAction.HOLD, 0.24, 0.20),
        "60": _tf("60", SignalAction.HOLD, 0.11, 0.50),
        "240": _tf("240", SignalAction.HOLD, 0.24, 0.30),
    }
    action, conf = consolidate_mtf_confidence(
        _analysis(tfs, SignalAction.BUY), primary_confidence=0.11
    )
    assert action == SignalAction.HOLD, (
        "a consensus no timeframe's gated action supports must not stay directional"
    )


def test_hold_consensus_keeps_primary_confidence():
    tfs = {
        "60": _tf("60", SignalAction.HOLD, 0.42, 0.50),
    }
    action, conf = consolidate_mtf_confidence(
        _analysis(tfs, SignalAction.HOLD, modifier=0.90), primary_confidence=0.42
    )
    assert action == SignalAction.HOLD
    assert conf == pytest.approx(0.42 * 0.90, abs=1e-9)


def test_modifier_is_applied():
    tfs = {"60": _tf("60", SignalAction.BUY, 0.50, 0.50)}
    _, conf = consolidate_mtf_confidence(
        _analysis(tfs, SignalAction.BUY, modifier=1.15), primary_confidence=0.50
    )
    assert conf == pytest.approx(0.575, abs=1e-9)


def test_confidence_is_clamped_to_one():
    """TradingSignal declares confidence le=1.0 but assignment bypasses validation."""
    tfs = {"60": _tf("60", SignalAction.BUY, 0.95, 0.50)}
    _, conf = consolidate_mtf_confidence(
        _analysis(tfs, SignalAction.BUY, modifier=1.15), primary_confidence=0.95
    )
    assert conf <= 1.0, f"confidence escaped [0, 1]: {conf}"
    assert conf == pytest.approx(1.0, abs=1e-9)


def test_zero_total_weight_falls_back_to_primary():
    tfs = {"60": _tf("60", SignalAction.BUY, 0.50, 0.0)}
    action, conf = consolidate_mtf_confidence(
        _analysis(tfs, SignalAction.BUY), primary_confidence=0.33
    )
    assert action == SignalAction.BUY
    assert conf == pytest.approx(0.33, abs=1e-9)
