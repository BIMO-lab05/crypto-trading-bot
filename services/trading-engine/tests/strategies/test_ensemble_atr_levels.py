"""The ensemble's multi-indicator leg must read the aggregator's REAL ATR payload.

Defect (found 2026-08-08, TA audit): `multi_strategy_ensemble` read
`metadata["atr_stop_loss"]` / `metadata["atr_take_profit"]` — flat keys that
no production code has ever written. The aggregator files its ATR payload
NESTED, at `metadata["atr"]`, keyed `stop_loss_long` / `stop_loss_short` /
`take_profit_long` / `take_profit_short` (`aggregator_core._build_metadata`,
fed by `signal_aggregator.fetch_atr`). Both `.get()` defaults therefore fired
on every signal and the LEG_MULTI stop landed on `current_price` — a
zero-width stop, R undefined.

Since Stage 0 the ensemble applies its own levels via `set_position_stops`,
guarded by `AutoTrader._ensemble_stops_are_consistent`, which rejects
`stop == entry` both pre- and post-fill. So every multi-indicator-dominant
entry either silently kept the risk-manager 2%/4% default or was rejected
outright. These tests pin the payload shape the two sides must agree on.
"""

import importlib

import pytest

from app.models.enums import SignalAction
from app.models.signal import TradingSignal

PRICE = 72.68


@pytest.fixture
def ensemble_module():
    """Fresh class binding per test (the module holds a weights singleton)."""
    import app.strategies.multi_strategy_ensemble as mod

    importlib.reload(mod)
    return mod


@pytest.fixture
def guard():
    from app.auto_trader import AutoTrader

    return AutoTrader._ensemble_stops_are_consistent


def _atr_payload(price: float = PRICE) -> dict:
    """The dict `signal_aggregator.fetch_atr` returns, verbatim in shape."""
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


def _signal(action: SignalAction, metadata: dict, confidence: float = 0.30):
    return TradingSignal(
        symbol="SOLUSDT",
        timestamp=0,
        action=action,
        confidence=confidence,
        aggregated_score=confidence if action == SignalAction.BUY else -confidence,
        consensus_count=3,
        indicators={},
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# _atr_levels: side-awareness and the fallback
# ---------------------------------------------------------------------------


def test_buy_reads_the_long_keys(ensemble_module):
    sl, tp = ensemble_module.MultiStrategyEnsemble._atr_levels(
        _signal(SignalAction.BUY, {"atr": _atr_payload()})
    )
    assert sl == pytest.approx(PRICE * 0.98)
    assert tp == pytest.approx(PRICE * 1.04)


def test_sell_reads_the_short_keys(ensemble_module):
    """A SELL taking the long stop would put the stop BELOW entry — inverted."""
    sl, tp = ensemble_module.MultiStrategyEnsemble._atr_levels(
        _signal(SignalAction.SELL, {"atr": _atr_payload()})
    )
    assert sl == pytest.approx(PRICE * 1.02)
    assert tp == pytest.approx(PRICE * 0.96)


def test_atr_absent_yields_the_unusable_sentinel(ensemble_module, caplog):
    """No ATR payload at all — the aggregator's fetch_atr failed."""
    with caplog.at_level("WARNING"):
        sl, tp = ensemble_module.MultiStrategyEnsemble._atr_levels(
            _signal(SignalAction.BUY, {"buy_count": 3})
        )
    assert (sl, tp) == (
        ensemble_module.UNUSABLE_LEVEL,
        ensemble_module.UNUSABLE_LEVEL,
    )
    assert "SOLUSDT" in caplog.text and "no metadata['atr']" in caplog.text


def test_atr_none_yields_the_unusable_sentinel(ensemble_module):
    sl, tp = ensemble_module.MultiStrategyEnsemble._atr_levels(
        _signal(SignalAction.BUY, {"atr": None})
    )
    assert (sl, tp) == (
        ensemble_module.UNUSABLE_LEVEL,
        ensemble_module.UNUSABLE_LEVEL,
    )


def test_atr_present_but_needed_key_missing(ensemble_module, caplog):
    """Short keys present, long keys gone — a BUY must not silently borrow them."""
    payload = _atr_payload()
    del payload["stop_loss_long"]
    with caplog.at_level("WARNING"):
        sl, tp = ensemble_module.MultiStrategyEnsemble._atr_levels(
            _signal(SignalAction.BUY, {"atr": payload})
        )
    assert (sl, tp) == (
        ensemble_module.UNUSABLE_LEVEL,
        ensemble_module.UNUSABLE_LEVEL,
    )
    assert "present but unusable" in caplog.text


def test_atr_key_present_but_not_a_number(ensemble_module):
    payload = _atr_payload()
    payload["take_profit_long"] = "n/a"
    sl, tp = ensemble_module.MultiStrategyEnsemble._atr_levels(
        _signal(SignalAction.BUY, {"atr": payload})
    )
    assert (sl, tp) == (
        ensemble_module.UNUSABLE_LEVEL,
        ensemble_module.UNUSABLE_LEVEL,
    )


def test_sentinel_is_rejected_by_the_consistency_guard(ensemble_module, guard):
    """The fallback must FAIL the guard — that is the whole point of choosing it.

    A fabricated level (entry x 0.98) would pass here and be indistinguishable
    downstream from a real ATR stop.
    """
    unusable = ensemble_module.UNUSABLE_LEVEL
    assert guard(SignalAction.BUY, PRICE, unusable, unusable) is False
    assert guard(SignalAction.SELL, PRICE, unusable, unusable) is False


# ---------------------------------------------------------------------------
# End-to-end: the real aggregator metadata shape, through generate_signal,
# into the guard that decides whether the entry is allowed.
# ---------------------------------------------------------------------------


def _multi_leg_only(monkeypatch, ensemble_module):
    """Silence the other two legs and pin LEG_MULTI's weight to 1.0.

    Without the weight pin the 1/3 default weight puts a 0.30-confidence
    signal at 0.10 — right on AGGREGATION_THRESHOLD — and the test would be
    measuring the threshold, not the stop wiring.
    """
    from app.strategies.mean_reversion_strategy import MeanReversionStrategy
    from app.strategies.simple_rsi_strategy import SimpleRSIStrategy

    monkeypatch.setattr(
        SimpleRSIStrategy, "generate_signal", lambda self, *a, **kw: None
    )
    monkeypatch.setattr(
        MeanReversionStrategy, "generate_signal", lambda self, *a, **kw: None
    )
    monkeypatch.setattr(
        ensemble_module.StrategyPerformanceWeights,
        "normalized_weights",
        lambda self: {
            ensemble_module.LEG_RSI: 0.0,
            ensemble_module.LEG_MULTI: 1.0,
            ensemble_module.LEG_MEAN_REV: 0.0,
        },
    )


def _aggregator_metadata(atr_data):
    """Metadata built by the REAL producer — aggregator_core._build_metadata.

    Constructing the dict by hand in the test would prove only that the test
    and the consumer agree. Calling the producer proves the consumer agrees
    with the code that actually ships.
    """
    from app.aggregation.aggregator_core import CoreAggregator

    core = CoreAggregator(enable_market_regime=False)
    return core._build_metadata(
        buy_count=3,
        sell_count=0,
        hold_count=1,
        voting_indicators={},
        meets_requirements=True,
        trend_blocked=False,
        trend_reason="",
        volume_penalty=1.0,
        volume_reason="",
        atr_data=atr_data,
    )


@pytest.mark.parametrize(
    "action,expected_sl,expected_tp",
    [
        (SignalAction.BUY, PRICE * 0.98, PRICE * 1.04),
        (SignalAction.SELL, PRICE * 1.02, PRICE * 0.96),
    ],
)
def test_real_aggregator_metadata_yields_a_usable_stop(
    ensemble_module, guard, monkeypatch, action, expected_sl, expected_tp
):
    """The wiring proof: producer -> ensemble -> guard, no hand-built shapes.

    Before the fix this produced stop == take_profit == current_price and the
    guard rejected it, so the position kept the risk-manager default.
    """
    metadata = _aggregator_metadata(_atr_payload())
    assert "atr" in metadata, "producer shape changed — the fix targets the wrong key"

    _multi_leg_only(monkeypatch, ensemble_module)
    out = ensemble_module.MultiStrategyEnsemble().generate_signal(
        _signal(action, metadata), current_price=PRICE, capital=100.0
    )

    assert out is not None, "MULTI leg alone must clear the aggregation threshold"
    assert out.action == action
    assert out.stop_loss == pytest.approx(expected_sl)
    assert out.take_profit == pytest.approx(expected_tp)
    assert out.stop_loss != out.entry_price, "zero-width stop — the original defect"
    assert guard(out.action, out.entry_price, out.stop_loss, out.take_profit) is True


def test_missing_atr_reaches_the_guard_as_a_rejection(
    ensemble_module, guard, monkeypatch
):
    """No ATR payload: the leg still votes, but the entry cannot be taken.

    That is deliberate. The alternative — fabricating a level — hides from the
    operator that the aggregator produced no ATR data at all.
    """
    metadata = _aggregator_metadata(None)
    assert "atr" not in metadata

    _multi_leg_only(monkeypatch, ensemble_module)
    out = ensemble_module.MultiStrategyEnsemble().generate_signal(
        _signal(SignalAction.BUY, metadata), current_price=PRICE, capital=100.0
    )

    assert out is not None
    assert out.stop_loss == ensemble_module.UNUSABLE_LEVEL
    assert guard(out.action, out.entry_price, out.stop_loss, out.take_profit) is False
    assert any("ATR levels unavailable" in r for r in out.reasoning), (
        "the rejection must be traceable to its cause in the signal's own reasoning"
    )
