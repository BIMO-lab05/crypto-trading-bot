"""Ensemble confidence must be conviction-scaled, not vote-share-scaled.

Background (measured 2026-08-22/23, .planning/evidence/hold-funnel-2026-08-22.md):
``generate_signal`` summed ``sign * conf * weights.get(leg_id, 0.0)`` where
``normalized_weights()`` spans ALL THREE legs even when only one fires. The
result was then handed to ``auto_trader._ensemble_passes_signal_gates``, which
compares it against ``min_signal_confidence`` -- a CONVICTION floor, the same
constant ``RiskManager.validate_signal`` applies to an aggregator confidence on
the REST path.

Live evidence: SOLUSDT 2026-08-23 01:00-01:23, post-MTF conviction 0.36 was
reported as ``conf=11.90%`` (0.36 / 3) and rejected against the 0.30 floor,
36 times. Two knobs contradicted each other: MIN_AGREEING_LEGS = 1 says one leg
suffices, while the /3 denominator capped a lone leg at 0.3333 and so demanded
post-MTF conviction >= 0.90 to clear 0.30.

The fix normalises over the weights of the legs that actually took a
directional side, so a single firing leg passes its own confidence through
unchanged. No threshold value changes.
"""

import importlib
from types import SimpleNamespace

import pytest

from app.models.enums import SignalAction
from app.models.signal import TradingSignal


@pytest.fixture
def ensemble_module():
    import app.strategies.multi_strategy_ensemble as mod

    importlib.reload(mod)
    return mod


def _atr_payload(price: float) -> dict:
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


def _agg_signal(action: SignalAction, confidence: float, price: float = 100.0):
    return TradingSignal(
        symbol="SOLUSDT",
        timestamp=0,
        action=action,
        confidence=confidence,
        aggregated_score=confidence if action == SignalAction.BUY else -confidence,
        consensus_count=5,
        indicators={},
        metadata={"atr": _atr_payload(price)},
    )


def _leg_stub(action: SignalAction, confidence: float, price: float = 100.0):
    """Duck-type of SimpleRSISignal / MeanReversionSignal as the ensemble reads them."""
    return SimpleNamespace(
        action=action,
        confidence=confidence,
        stop_loss=price * 0.98,
        take_profit=price * 1.04,
        target=price * 1.04,
        reasoning=["stub leg"],
    )


def _silence_legs(monkeypatch, rsi=None, mean_rev=None):
    """Stub the two non-aggregator legs. Weights are deliberately NOT pinned --
    the whole point is that the real 1/3-each weighting must not dilute."""
    from app.strategies.simple_rsi_strategy import SimpleRSIStrategy
    from app.strategies.mean_reversion_strategy import MeanReversionStrategy

    monkeypatch.setattr(
        SimpleRSIStrategy, "generate_signal", lambda self, *a, **kw: rsi
    )
    monkeypatch.setattr(
        MeanReversionStrategy, "generate_signal", lambda self, *a, **kw: mean_rev
    )


def test_single_firing_leg_passes_its_confidence_through(
    ensemble_module, monkeypatch
):
    """A lone leg must not be divided by the weight of legs that said nothing.

    This is the live SOLUSDT case: conviction 0.36 was reported as 0.119.
    """
    _silence_legs(monkeypatch)
    ens = ensemble_module.MultiStrategyEnsemble()

    out = ens.generate_signal(
        _agg_signal(SignalAction.BUY, 0.36), current_price=100.0, capital=100.0
    )

    assert out is not None, (
        "lone multi_indicator leg at conviction 0.36 must clear "
        "AGGREGATION_THRESHOLD=0.10; it was being diluted to 0.12"
    )
    assert out.confidence == pytest.approx(0.36, abs=1e-9), (
        f"expected conviction 0.36 to survive intact, got {out.confidence} "
        "(0.12 means the all-legs denominator is still being applied)"
    )


def test_two_agreeing_legs_blend_by_weight(ensemble_module, monkeypatch):
    """Two firing legs at equal weight average their convictions."""
    _silence_legs(monkeypatch, rsi=_leg_stub(SignalAction.BUY, 0.40))
    ens = ensemble_module.MultiStrategyEnsemble()

    out = ens.generate_signal(
        _agg_signal(SignalAction.BUY, 0.60), current_price=100.0, capital=100.0
    )

    assert out is not None
    assert out.confidence == pytest.approx(0.50, abs=1e-9), (
        f"two equal-weight BUY legs at 0.60 and 0.40 must blend to 0.50, "
        f"got {out.confidence}"
    )


def test_opposing_legs_cancel_to_hold(ensemble_module, monkeypatch):
    """Equal and opposite convictions net to zero and must not emit."""
    _silence_legs(monkeypatch, rsi=_leg_stub(SignalAction.SELL, 0.60))
    ens = ensemble_module.MultiStrategyEnsemble()

    out = ens.generate_signal(
        _agg_signal(SignalAction.BUY, 0.60), current_price=100.0, capital=100.0
    )

    assert out is None, "opposing equal-conviction legs must net to HOLD"


def test_abstaining_leg_does_not_dilute(ensemble_module, monkeypatch):
    """A leg that returns HOLD abstains; it must not drag the blend toward zero.

    ``simple_rsi`` cannot currently emit HOLD (every returning path sets BUY or
    SELL), but ``multi_strategy_ensemble`` adds it without the ``!= HOLD`` guard
    its sibling leg carries, so the path is reachable by construction.
    """
    _silence_legs(monkeypatch, rsi=_leg_stub(SignalAction.HOLD, 0.90))
    ens = ensemble_module.MultiStrategyEnsemble()

    out = ens.generate_signal(
        _agg_signal(SignalAction.BUY, 0.36), current_price=100.0, capital=100.0
    )

    assert out is not None
    assert out.confidence == pytest.approx(0.36, abs=1e-9), (
        f"a HOLD leg abstains and must not enter the denominator, "
        f"got {out.confidence}"
    )


def test_confidence_never_exceeds_one(ensemble_module, monkeypatch):
    """Renormalising must not let confidence escape [0, 1]."""
    _silence_legs(monkeypatch, rsi=_leg_stub(SignalAction.BUY, 1.0))
    ens = ensemble_module.MultiStrategyEnsemble()

    out = ens.generate_signal(
        _agg_signal(SignalAction.BUY, 1.0), current_price=100.0, capital=100.0
    )

    assert out is not None
    assert 0.0 <= out.confidence <= 1.0, f"confidence out of range: {out.confidence}"


def test_min_agreeing_legs_still_enforced(ensemble_module, monkeypatch):
    """Renormalising must not weaken the agreement requirement."""
    _silence_legs(monkeypatch)
    ens = ensemble_module.MultiStrategyEnsemble()
    monkeypatch.setattr(ens, "MIN_AGREEING_LEGS", 2, raising=False)

    out = ens.generate_signal(
        _agg_signal(SignalAction.BUY, 0.90), current_price=100.0, capital=100.0
    )

    assert out is None, "one firing leg must not satisfy MIN_AGREEING_LEGS=2"


def test_aggregation_threshold_still_enforced(ensemble_module, monkeypatch):
    """A genuinely weak lone signal must still be rejected."""
    _silence_legs(monkeypatch)
    ens = ensemble_module.MultiStrategyEnsemble()

    out = ens.generate_signal(
        _agg_signal(SignalAction.BUY, 0.05), current_price=100.0, capital=100.0
    )

    assert out is None, (
        "conviction 0.05 is below AGGREGATION_THRESHOLD=0.10 and must not emit"
    )
