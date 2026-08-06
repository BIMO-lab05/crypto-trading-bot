"""Known-bug preservation (spec §3.3/§7.3): these tests pin DEPLOYED behavior.

A failure here means the engine changed — update the offline replay
consciously, then re-baseline. Never 'fix' these to green silently.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

SA = REPO / "services" / "trading-engine" / "app" / "signal_aggregator.py"
MSE = (
    REPO
    / "services"
    / "trading-engine"
    / "app"
    / "strategies"
    / "multi_strategy_ensemble.py"
)
SRS = (
    REPO
    / "services"
    / "trading-engine"
    / "app"
    / "strategies"
    / "simple_rsi_strategy.py"
)


def test_atr_never_reinjected_into_indicators():
    src = SA.read_text()
    # fetch_all_indicators routes ATR out to atr_data; nothing assigns indicators["ATR"]
    assert 'indicators["ATR"]' not in src.replace(" ", "")


def test_simple_rsi_atr_pct_fallback_is_002():
    src = SRS.read_text()
    assert re.search(r"atr_pct\s*=\s*0\.02", src), "hardcoded 0.02 fallback changed"


def test_no_producer_for_atr_stop_loss_metadata():
    te_app = REPO / "services" / "trading-engine" / "app"
    producers = [
        p
        for p in te_app.rglob("*.py")
        if re.search(r"""metadata\[["']atr_stop_loss["']\]\s*=""", p.read_text())
    ]
    assert producers == [], f"atr_stop_loss now has producer(s): {producers}"


def test_mtf_consensus_action_not_applied():
    src = SA.read_text()
    # the merge mutates confidence only; consensus_action lands in metadata
    assert "primary_signal.confidence" in src
    assert not re.search(r"primary_signal\.action\s*=\s*consensus", src)


def test_ensemble_constants_pinned():
    src = MSE.read_text()
    assert re.search(r"AGGREGATION_THRESHOLD\s*=\s*\(?\s*0\.10", src)
    assert re.search(r"MIN_AGREEING_LEGS\s*=\s*\(?\s*1", src)


def test_voting_weights_canary():
    """Snapshot of client-side metadata weights in fetch_* (the live table).

    RESEARCH_WEIGHTS in voter.py is dead code; THIS is what votes. Measured
    2026-08-05: 9 weight literals summing 9.7 — the ACTIVE set (total 8.1:
    five 1.0s incl. ADX, SMA 0.8, Ichimoku 1.3, ...) plus two literals inside
    the DISABLED fetch_rsi_divergence (1.2) and fetch_enhanced_sqzmom (1.4)
    functions, which fetch_all_indicators does not call. If this fails, the
    live weight table moved — update the snapshot AND re-run any standing H4
    verdict.
    """
    src = SA.read_text()
    weights = re.findall(r'"weight":\s*([0-9.]+)', src)
    assert len(weights) == 9, f"weight-literal count changed: {len(weights)} (was 9)"
    total = sum(float(w) for w in weights)
    assert abs(total - 9.7) < 0.01, f"total weight literals changed: {total} (was 9.7)"


def test_confidence_can_exceed_one():
    """Spec §3.3 bullet 5: TradingSignal has no validate_assignment, so the MTF
    x1.2 modifier can push confidence past the le=1.0 field bound after
    construction. Pin it: if a future fix adds validate_assignment, this fails
    and the replay must be consciously re-baselined."""
    import importlib.util
    import sys
    import types

    te_app = REPO / "services" / "trading-engine" / "app"

    def _load(name, path):
        spec = importlib.util.spec_from_file_location(name, str(path))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    created_app = "app" not in sys.modules
    if created_app:
        sys.modules["app"] = types.ModuleType("app")
    prior_models = sys.modules.get("app.models")
    prior_enums = sys.modules.get("app.models.enums")
    try:
        enums = _load("app.models.enums", te_app / "models" / "enums.py")
        models_stub = types.ModuleType("app.models")
        models_stub.enums = enums
        sys.modules["app.models"] = models_stub
        signal_mod = _load("_preservation_signal", te_app / "models" / "signal.py")
        sig = signal_mod.TradingSignal(
            symbol="BTCUSDT",
            timestamp=1,
            action=enums.SignalAction.BUY,
            confidence=0.9,
            indicators={},
            aggregated_score=0.5,
            consensus_count=3,
        )
        sig.confidence = 1.08  # must NOT raise, must stick (no validate_assignment)
        assert sig.confidence == 1.08
    finally:
        if prior_models is not None:
            sys.modules["app.models"] = prior_models
        else:
            sys.modules.pop("app.models", None)
        if prior_enums is not None:
            sys.modules["app.models.enums"] = prior_enums
        else:
            sys.modules.pop("app.models.enums", None)
        if created_app:
            sys.modules.pop("app", None)
