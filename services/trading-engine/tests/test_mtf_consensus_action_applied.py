"""Multi-timeframe consensus must reach the returned signal's action.

Investigation 2026-08-22 (`docs/FUNNEL_ROOT_CAUSE_2026-08-22.md`): the live funnel
emitted `Ensemble signal emitted 0/146`. Decomposed, 100% of ensemble exits were
`no legs fired`, because `LEG_MULTI` is guarded on
`aggregator_signal.action != HOLD` and the action it receives was **always** HOLD.

Cause: `get_trading_signal_multi_timeframe` computed
`MultiTimeframeAnalysis.consensus_action` (multi_timeframe.py, via
`_calculate_weighted_consensus`) and wrote it into
`metadata["multi_timeframe"]["consensus_action"]` — and nothing ever read it back.
The function returned `primary_signal` (the 60m timeframe) with only its
*confidence* rescaled by the alignment modifier, so the action was whatever the
primary timeframe said. Measured over 2,820 live evaluations the 60m timeframe was
HOLD 100% of the time, so LEG_MULTI could never fire.

These tests pin the wiring: whatever the analyzer concludes as the consensus is
the action the caller receives.

NOTE ON SCOPE — deliberately not a trade-unblocking change. Recomputed over 90
live cycles with the shipped weights (15m=0.20, 60m=0.50, 240m=0.30) and the
shipped +/-0.2 consensus band, `consensus_action` resolves to HOLD in 90/90 cases
(max consensus score +0.106). Wiring it removes dead code and makes the metadata
honest; it does not by itself produce signals. The reason the funnel is empty is
that the voting set cancels (trend voters pinned bullish, oscillators pinned
bearish, both correct) — see the doc. Do not "fix" that by loosening thresholds.
"""

import pytest

from app.models.enums import SignalAction
from app.models.signal import TradingSignal


def _signal(action: SignalAction, score: float, conf: float) -> TradingSignal:
    """A TradingSignal shaped like SignalAggregator.get_trading_signal output."""
    return TradingSignal(
        symbol="BTCUSDT",
        timestamp=1787400000000,
        action=action,
        confidence=conf,
        indicators={},
        aggregated_score=score,
        consensus_count=4,
    )


class _StubAnalysis:
    """Stands in for MultiTimeframeAnalysis — only the fields the caller reads."""

    def __init__(self, consensus_action: SignalAction, timeframe_signals: dict):
        self.consensus_action = consensus_action
        self.primary_action = SignalAction.HOLD
        self.confidence_modifier = 1.0
        self.agreement_pct = 66.0
        self.reasoning = "stub"
        self.timeframe_signals = timeframe_signals

        class _Strength:
            value = "WEAK"

        self.alignment_strength = _Strength()


class _StubTFSignal:
    """Test double for multi_timeframe.TimeframeSignal.

    ``weight`` added 2026-08-23: the real dataclass has carried it since the
    module was written, and consolidate_mtf_confidence() now weight-averages
    confidence over the agreeing timeframes, so a double without it no longer
    stands in for the real thing. Values are the shipped weights
    (15m=0.20, 60m=0.50, 240m=0.30).
    """

    def __init__(self, action, confidence, score, weight=0.0):
        self.action = action
        self.confidence = confidence
        self.score = score
        self.weight = weight


@pytest.fixture
def aggregator(monkeypatch):
    """SignalAggregator with the per-timeframe fetch and the analyzer stubbed."""
    from app.signal_aggregator import SignalAggregator

    agg = SignalAggregator()

    # 15m and 60m flat/HOLD, 240m strongly BUY — the shape measured live.
    per_tf = {
        "15": _signal(SignalAction.HOLD, -0.14, 0.43),
        "60": _signal(SignalAction.HOLD, -0.09, 0.45),
        "240": _signal(SignalAction.BUY, 0.41, 0.46),
    }

    async def fake_get_trading_signal(symbol, interval):
        return per_tf[interval]

    monkeypatch.setattr(agg, "get_trading_signal", fake_get_trading_signal)
    return agg, per_tf


async def _run(agg, consensus: SignalAction, per_tf, monkeypatch):
    """Invoke the MTF path with the analyzer forced to a known consensus."""
    shipped_weights = {"15": 0.20, "60": 0.50, "240": 0.30}
    tf_signals = {
        k: _StubTFSignal(
            v.action, v.confidence, v.aggregated_score, shipped_weights.get(k, 0.0)
        )
        for k, v in per_tf.items()
    }
    analysis = _StubAnalysis(consensus, tf_signals)

    class _Analyzer:
        async def analyze_timeframes(self, signals, primary_signal):
            return analysis

    import app.aggregation as aggregation_pkg

    monkeypatch.setattr(aggregation_pkg, "get_multi_timeframe_analyzer", lambda: _Analyzer())
    return await agg.get_trading_signal_multi_timeframe(
        "BTCUSDT", primary_interval="60", timeframes=["15", "60", "240"]
    )


@pytest.mark.asyncio
async def test_consensus_buy_overrides_hold_primary(aggregator, monkeypatch):
    """Primary (60m) says HOLD, consensus says BUY -> caller must see BUY.

    This is the exact live shape that produced `no legs fired` 146/146.
    """
    agg, per_tf = aggregator
    result = await _run(agg, SignalAction.BUY, per_tf, monkeypatch)
    assert result.action == SignalAction.BUY, (
        "MTF consensus_action was computed but discarded — the caller still sees "
        "the primary timeframe's HOLD, so LEG_MULTI can never fire."
    )


@pytest.mark.asyncio
async def test_consensus_hold_is_respected(aggregator, monkeypatch):
    """Consensus HOLD must stay HOLD even when a single timeframe is BUY.

    Guards the opposite error: we must not start trading off the 240m leg alone.
    Live, the 240m printed BUY 2,408 times and SELL zero times in 16h — promoting
    it would hard-wire a permanent long bias.
    """
    agg, per_tf = aggregator
    result = await _run(agg, SignalAction.HOLD, per_tf, monkeypatch)
    assert result.action == SignalAction.HOLD


@pytest.mark.asyncio
async def test_consensus_action_matches_metadata(aggregator, monkeypatch):
    """The action and the metadata the dashboard reads must not disagree."""
    agg, per_tf = aggregator
    result = await _run(agg, SignalAction.BUY, per_tf, monkeypatch)
    meta = result.metadata["multi_timeframe"]
    assert meta["consensus_action"] == result.action.value, (
        "metadata reported one consensus while the signal carried another"
    )
