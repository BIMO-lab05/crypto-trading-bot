"""
Tests for MultiStrategyEnsemble position sizing.

Goal: ensemble must honor settings.max_risk_per_trade as the per-trade cap and
settings.ensemble_min_position_pct as the floor, scaling between by
settings.ensemble_confidence_size_multiplier × confidence × cap.

Background: ADR-010 raised paper max_risk_per_trade 2% -> 10%. The ensemble
hard-coded MAX_POSITION_PCT=0.10 + a 1.5x multiplier on confidence + a 1% floor,
which made trades cluster at 1-3% notional (per typical observed conf 0.05-0.20)
instead of approaching the 10% cap operator approved.

The fix: bind sizing to settings; expose floor + multiplier so the cascade is
explicit and tunable. Defaults pick a multiplier such that confidence at the
documented ensemble ceiling (~0.27) sizes the trade to the cap.
"""

import importlib

import pytest

from app.models.signal import TradingSignal
from app.models.enums import SignalAction


@pytest.fixture
def ensemble_module():
    """Re-import the module so we get a fresh class binding per test."""
    import app.strategies.multi_strategy_ensemble as mod

    importlib.reload(mod)
    return mod


def _build_aggregator_signal(
    action: SignalAction, confidence: float, price: float = 100.0
):
    """Build a minimal TradingSignal that the ensemble's MULTI leg accepts."""
    return TradingSignal(
        symbol="ADAUSDT",
        timestamp=0,
        action=action,
        confidence=confidence,
        aggregated_score=confidence if action == SignalAction.BUY else -confidence,
        consensus_count=3,
        indicators={},
        metadata={
            "atr_stop_loss": price * 0.98,
            "atr_take_profit": price * 1.03,
        },
    )


def _stub_legs(monkeypatch, ensemble_module, agg_signal):
    """Force only the MULTI leg to fire by stubbing the other two to return None,
    and weight the MULTI leg at 1.0 so weighted_score == confidence (otherwise
    the 1/3 weight + 0.10 aggregation threshold throws away the signal before
    sizing math runs).
    """
    from app.strategies.simple_rsi_strategy import SimpleRSIStrategy
    from app.strategies.mean_reversion_strategy import MeanReversionStrategy

    monkeypatch.setattr(
        SimpleRSIStrategy, "generate_signal", lambda self, *a, **kw: None
    )
    monkeypatch.setattr(
        MeanReversionStrategy, "generate_signal", lambda self, *a, **kw: None
    )
    # Pin weights so weighted_score == confidence regardless of EMA history.
    LEG_RSI = ensemble_module.LEG_RSI
    LEG_MULTI = ensemble_module.LEG_MULTI
    LEG_MEAN_REV = ensemble_module.LEG_MEAN_REV
    pinned = {LEG_RSI: 0.0, LEG_MULTI: 1.0, LEG_MEAN_REV: 0.0}
    weights_obj = ensemble_module.get_ensemble_weights()
    monkeypatch.setattr(
        weights_obj, "normalized_weights", lambda: pinned, raising=False
    )


def test_ensemble_reads_cap_from_settings(ensemble_module, monkeypatch):
    """MAX_POSITION_PCT must come from settings.max_risk_per_trade, not a hard-coded 0.10."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "max_risk_per_trade", 0.15, raising=False)
    monkeypatch.setattr(settings, "ensemble_min_position_pct", 0.05, raising=False)
    monkeypatch.setattr(
        settings, "ensemble_confidence_size_multiplier", 3.7, raising=False
    )

    ens = ensemble_module.MultiStrategyEnsemble()

    # Confidence well above (1 / 3.7) ≈ 0.27 — formula clamps to cap.
    agg = _build_aggregator_signal(SignalAction.BUY, confidence=0.99)
    _stub_legs(monkeypatch, ensemble_module, agg)
    out = ens.generate_signal(agg, current_price=100.0, capital=100.0)

    assert out is not None, "ensemble must fire on high-conf BUY"
    assert out.position_size_pct == pytest.approx(0.15), (
        f"size should hit cap from settings (0.15), got {out.position_size_pct}"
    )


def test_ensemble_floor_from_settings(ensemble_module, monkeypatch):
    """At low confidence, sizing falls back to settings.ensemble_min_position_pct, not 0.01."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "max_risk_per_trade", 0.10, raising=False)
    monkeypatch.setattr(settings, "ensemble_min_position_pct", 0.05, raising=False)
    monkeypatch.setattr(
        settings, "ensemble_confidence_size_multiplier", 3.7, raising=False
    )

    ens = ensemble_module.MultiStrategyEnsemble()

    # Confidence 0.11 (typical live value) → 0.11 × 0.10 × 3.7 = 0.0407 < floor 0.05
    agg = _build_aggregator_signal(SignalAction.BUY, confidence=0.11)
    _stub_legs(monkeypatch, ensemble_module, agg)
    out = ens.generate_signal(agg, current_price=100.0, capital=100.0)

    assert out is not None
    assert out.position_size_pct == pytest.approx(0.05), (
        f"size should hit floor from settings (0.05), got {out.position_size_pct}"
    )


def test_ensemble_multiplier_scales_size_between_floor_and_cap(
    ensemble_module, monkeypatch
):
    """Mid-confidence: size = confidence × cap × multiplier (between floor and cap)."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "max_risk_per_trade", 0.10, raising=False)
    monkeypatch.setattr(settings, "ensemble_min_position_pct", 0.05, raising=False)
    monkeypatch.setattr(
        settings, "ensemble_confidence_size_multiplier", 3.7, raising=False
    )

    ens = ensemble_module.MultiStrategyEnsemble()

    # Confidence 0.20 → 0.20 × 0.10 × 3.7 = 0.074 (between 0.05 and 0.10)
    agg = _build_aggregator_signal(SignalAction.BUY, confidence=0.20)
    _stub_legs(monkeypatch, ensemble_module, agg)
    out = ens.generate_signal(agg, current_price=100.0, capital=100.0)

    assert out is not None
    assert out.position_size_pct == pytest.approx(0.074, abs=1e-6), (
        f"size should be 0.20 × 0.10 × 3.7 = 0.074, got {out.position_size_pct}"
    )


def test_ensemble_default_settings_hit_cap_at_documented_ceiling(
    ensemble_module, monkeypatch
):
    """Default multiplier must be calibrated so confidence at documented ensemble ceiling
    (~0.27 per ADR-013) sizes the trade to the configured cap. This is the operator-intent
    contract: when ensemble fires near its real-world ceiling, the trade is at the cap.
    """
    from app.config import get_settings

    settings = get_settings()
    # Use *defaults* — do not override.
    cap = settings.max_risk_per_trade
    mult = settings.ensemble_confidence_size_multiplier
    floor = settings.ensemble_min_position_pct

    # 1 / mult is the confidence at which formula equals cap.
    cap_confidence = 1.0 / mult
    assert cap_confidence <= 0.30, (
        f"default multiplier {mult} requires conf {cap_confidence:.2f} to hit cap; "
        f"per ADR-013 ensemble caps at ~0.27 — formula must reach cap by 0.27 not 0.67"
    )
    assert floor <= cap, "floor must not exceed cap"
    assert mult > 1.5, (
        "multiplier must be raised above legacy 1.5 to honor ADR-010 intent"
    )


def test_ensemble_cap_from_settings_overrides_class_constant(
    ensemble_module, monkeypatch
):
    """Class no longer carries a frozen MAX_POSITION_PCT=0.10 — sizing must follow live setting."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(
        settings, "max_risk_per_trade", 0.02, raising=False
    )  # LIVE-mode cap
    monkeypatch.setattr(settings, "ensemble_min_position_pct", 0.005, raising=False)
    monkeypatch.setattr(
        settings, "ensemble_confidence_size_multiplier", 3.7, raising=False
    )

    ens = ensemble_module.MultiStrategyEnsemble()

    agg = _build_aggregator_signal(SignalAction.BUY, confidence=0.99)
    _stub_legs(monkeypatch, ensemble_module, agg)
    out = ens.generate_signal(agg, current_price=100.0, capital=100.0)

    assert out is not None
    assert out.position_size_pct == pytest.approx(0.02), (
        f"LIVE-mode 2% cap from settings must be honored, got {out.position_size_pct}"
    )
