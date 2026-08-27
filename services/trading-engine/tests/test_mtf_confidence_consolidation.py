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


# ---------------------------------------------------------------------------
# P21-3 (Plan 21-05, Task 2): the demotion must be OBSERVABLE downstream.
#
# consolidate_mtf_confidence() above is a pure function and is already pinned by
# test_consensus_with_no_agreeing_timeframe_is_forced_to_hold. What was NOT
# pinned -- and not even expressible -- is whether anything downstream can TELL
# that a demotion happened. metadata["multi_timeframe"]["consensus_action"]
# stores the PRE-demotion value, so a demoted consensus and a genuinely-HOLD
# consensus were indistinguishable in the metadata.
#
# These tests therefore drive the real writer, `get_trading_signal_multi_timeframe`,
# end to end with the per-timeframe fetch and the analyzer stubbed. The harness
# is modelled on tests/test_mtf_consensus_action_applied.py::_run, but feeds the
# REAL MultiTimeframeAnalysis through the _analysis() builder above rather than a
# duck-typed stand-in.
# ---------------------------------------------------------------------------

from types import SimpleNamespace  # noqa: E402

from app.models import TradingSignal  # noqa: E402


def _tf_trading_signal(tf) -> TradingSignal:
    """The per-timeframe TradingSignal that get_trading_signal() would return."""
    return TradingSignal(
        symbol="BTCUSDT",
        timestamp=1787400000000,
        action=tf.action,
        confidence=tf.confidence,
        aggregated_score=tf.score,
        consensus_count=4,
        indicators={},
    )


def _blocking_regime_analysis():
    """Minimal stand-in for RegimeAnalysis -- only the fields the writer reads.

    signal_aggregator.py:1183-1193 copies these nine attributes into
    metadata["market_regime"]; nothing else about the object is touched on this
    path because apply_regime_adjustment is stubbed by the caller.
    """
    return SimpleNamespace(
        regime=SimpleNamespace(value="RANGING"),
        direction=SimpleNamespace(value="NEUTRAL"),
        adx=12.0,
        plus_di=18.0,
        minus_di=19.0,
        confidence=0.55,
        confidence_modifier=1.0,
        description="stub regime",
        strategy_recommendation="stub recommendation",
    )


async def _run_mtf(
    monkeypatch,
    tfs,
    consensus,
    modifier=1.0,
    regime_analysis=None,
    regime_blocked=False,
):
    """Drive the real metadata writer with the network stubbed out."""
    import app.aggregation as aggregation_pkg
    from app.signal_aggregator import SignalAggregator

    agg = SignalAggregator()

    per_tf = {interval: _tf_trading_signal(tf) for interval, tf in tfs.items()}

    async def fake_get_trading_signal(symbol, interval):
        return per_tf[interval]

    monkeypatch.setattr(agg, "get_trading_signal", fake_get_trading_signal)

    analysis = _analysis(tfs, consensus, modifier)

    class _Analyzer:
        async def analyze_timeframes(self, signals, primary_signal):
            return analysis

    monkeypatch.setattr(
        aggregation_pkg, "get_multi_timeframe_analyzer", lambda: _Analyzer()
    )

    if regime_analysis is not None:
        monkeypatch.setattr(
            agg.core_aggregator.regime_detector,
            "apply_regime_adjustment",
            lambda action, confidence, ra: (
                confidence,
                "stub regime reason",
                regime_blocked,
            ),
        )

    return await agg.get_trading_signal_multi_timeframe(
        "BTCUSDT",
        primary_interval="60",
        timeframes=list(tfs.keys()),
        regime_analysis=regime_analysis,
    )


@pytest.mark.asyncio
async def test_demotion_to_hold_is_recorded_in_metadata(monkeypatch):
    """The P21-3 case: a directional consensus no timeframe supports.

    This is the demotion that signal_aggregator already applies to
    ``primary_signal.action`` and that only the ensemble's ``multi_indicator``
    leg honours (via its ``action != HOLD`` guard). ``simple_rsi`` and
    ``mean_reversion`` never read ``.action`` at all, so they trade straight
    past it. They cannot be gated on something they cannot observe -- hence
    this key.
    """
    tfs = {
        "15": _tf("15", SignalAction.HOLD, 0.24, 0.20),
        "60": _tf("60", SignalAction.HOLD, 0.11, 0.50),
        "240": _tf("240", SignalAction.HOLD, 0.24, 0.30),
    }
    result = await _run_mtf(monkeypatch, tfs, SignalAction.BUY)
    meta = result.metadata["multi_timeframe"]

    assert meta["demoted_to_hold"] is True, (
        "a directional consensus demoted to HOLD must be observable downstream; "
        "otherwise the ensemble legs cannot honour a decision the system "
        "already made"
    )
    assert meta["consolidated_action"] == SignalAction.HOLD.value
    assert result.action == SignalAction.HOLD
    assert meta["consensus_action"] == SignalAction.BUY.value, (
        "consensus_action must keep carrying the PRE-demotion blend -- "
        "changing its meaning to fix an observability gap would trade one "
        "silent defect for another"
    )


@pytest.mark.asyncio
async def test_genuine_hold_consensus_is_not_recorded_as_a_demotion(monkeypatch):
    """A consensus that was already HOLD was never demoted.

    Demotion and genuine-HOLD must be DISTINGUISHABLE. If this flag were set
    here too it would degenerate into a restatement of ``action == HOLD``, which
    is exactly the broad reading 21-CONTEXT does not authorise.
    """
    tfs = {
        "15": _tf("15", SignalAction.HOLD, 0.24, 0.20),
        "60": _tf("60", SignalAction.HOLD, 0.42, 0.50),
    }
    result = await _run_mtf(monkeypatch, tfs, SignalAction.HOLD)
    meta = result.metadata["multi_timeframe"]

    assert meta["demoted_to_hold"] is False, (
        "a consensus that was HOLD before consolidation was not demoted"
    )
    assert meta["consolidated_action"] == SignalAction.HOLD.value
    assert meta["consensus_action"] == SignalAction.HOLD.value


@pytest.mark.asyncio
async def test_surviving_directional_consensus_is_not_recorded_as_a_demotion(
    monkeypatch,
):
    """A consensus with an agreeing gated action survives; no demotion."""
    tfs = {
        "15": _tf("15", SignalAction.BUY, 0.40, 0.20),
        "60": _tf("60", SignalAction.BUY, 0.60, 0.50),
        "240": _tf("240", SignalAction.HOLD, 0.90, 0.30),
    }
    result = await _run_mtf(monkeypatch, tfs, SignalAction.BUY)
    meta = result.metadata["multi_timeframe"]

    assert meta["demoted_to_hold"] is False
    assert meta["consolidated_action"] == SignalAction.BUY.value
    assert result.action == SignalAction.BUY, (
        "consolidated_action must equal the action on the signal at the moment "
        "of the write"
    )


@pytest.mark.asyncio
async def test_regime_hard_block_hold_is_not_recorded_as_an_mtf_demotion(monkeypatch):
    """NARROWNESS GUARD (T-21-05-04). Do not widen this key to `action == HOLD`.

    ``action == HOLD`` reaches the ensemble from four distinct upstream causes:
    MTF consensus demoted (this plan), a raw consensus that was genuinely HOLD,
    the regime hard-block at signal_aggregator.py:1206-1214, and a per-timeframe
    requirements gate resolving HOLD inside aggregator_core.

    Here a directional BUY consensus SURVIVES consolidation and is then forced to
    HOLD by the regime hard-block -- which runs AFTER the metadata write. The
    signal's final action is HOLD, yet no MTF demotion occurred. If
    ``demoted_to_hold`` were True here, Plan 21-05's ensemble gate would silently
    start suppressing regime-blocked signals too, which 21-CONTEXT does not
    authorise. The regime hard-block is recorded as a candidate follow-up, not
    fixed.
    """
    tfs = {
        "15": _tf("15", SignalAction.BUY, 0.40, 0.20),
        "60": _tf("60", SignalAction.BUY, 0.60, 0.50),
    }
    result = await _run_mtf(
        monkeypatch,
        tfs,
        SignalAction.BUY,
        regime_analysis=_blocking_regime_analysis(),
        regime_blocked=True,
    )
    meta = result.metadata["multi_timeframe"]

    assert result.action == SignalAction.HOLD, (
        "the regime hard-block must still force HOLD -- this plan does not "
        "touch it"
    )
    assert result.metadata["regime_blocked"] is True
    assert meta["consolidated_action"] == SignalAction.BUY.value, (
        "the MTF write happens BEFORE the regime block, so it records what "
        "consolidation produced"
    )
    assert meta["demoted_to_hold"] is False, (
        "a HOLD produced by the regime hard-block is NOT an MTF demotion; "
        "gating on it is deliberately out of scope for P21-3"
    )
