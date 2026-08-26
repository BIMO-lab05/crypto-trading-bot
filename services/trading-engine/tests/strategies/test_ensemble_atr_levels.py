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
from app.models.signal import IndicatorSignal, TradingSignal

# Imported at MODULE level, not inside the `guard` fixture, on purpose.
# tests/conftest.py's autouse mock_database_connection uses
# `patch.dict("sys.modules", ...)`, which restores the whole sys.modules
# mapping on teardown and therefore EVICTS any module first imported inside a
# test. app.auto_trader pulls in app.services.indicator_registry, which
# registers a Prometheus gauge at import; a second import after eviction
# raises "Duplicated timeseries in CollectorRegistry". Importing here happens
# at collection, before any fixture snapshot, so the module is never evicted.
from app.auto_trader import AutoTrader

PRICE = 72.68


@pytest.fixture
def ensemble_module():
    """Fresh class binding per test (the module holds a weights singleton)."""
    import app.strategies.multi_strategy_ensemble as mod

    importlib.reload(mod)
    return mod


@pytest.fixture
def guard():
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

    monkeypatch.setattr(SimpleRSIStrategy, "generate_signal", lambda self, *a, **kw: None)
    monkeypatch.setattr(MeanReversionStrategy, "generate_signal", lambda self, *a, **kw: None)
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
    # `capital` deliberately omitted — it resolves from
    # Settings.paper_initial_balance (P21-8). Never write a balance literal.
    out = ensemble_module.MultiStrategyEnsemble().generate_signal(
        _signal(action, metadata), current_price=PRICE
    )

    assert out is not None, "MULTI leg alone must clear the aggregation threshold"
    assert out.action == action
    assert out.stop_loss == pytest.approx(expected_sl)
    assert out.take_profit == pytest.approx(expected_tp)
    assert out.stop_loss != out.entry_price, "zero-width stop — the original defect"
    assert guard(out.action, out.entry_price, out.stop_loss, out.take_profit) is True


def test_missing_atr_reaches_the_guard_as_a_rejection(ensemble_module, guard, monkeypatch):
    """No ATR payload: the leg still votes, but the entry cannot be taken.

    That is deliberate. The alternative — fabricating a level — hides from the
    operator that the aggregator produced no ATR data at all.
    """
    metadata = _aggregator_metadata(None)
    assert "atr" not in metadata

    _multi_leg_only(monkeypatch, ensemble_module)
    out = ensemble_module.MultiStrategyEnsemble().generate_signal(
        _signal(SignalAction.BUY, metadata), current_price=PRICE
    )

    assert out is not None
    assert out.stop_loss == ensemble_module.UNUSABLE_LEVEL
    assert guard(out.action, out.entry_price, out.stop_loss, out.take_profit) is False
    assert any("ATR levels unavailable" in r for r in out.reasoning), (
        "the rejection must be traceable to its cause in the signal's own reasoning"
    )


# ---------------------------------------------------------------------------
# P21-1 consequence tests: what threading the ATR actually CHANGES.
#
# The tests above pin the mechanics of _atr_levels. These pin the effects on
# the two legs that were structurally ATR-blind, across all three ATR states
# the wire can present:
#
#   (a) a usable payload            -> mean_reversion's SMA-deviation
#                                      sub-signals become reachable
#   (b) metadata["atr"] absent      -> every leg falls back to its own
#                                      documented 2%, none fabricates a level
#   (c) atr.py::_default_response() -> UNUSABLE_LEVEL everywhere, and the
#                                      entry is rejected pre-fill
# ---------------------------------------------------------------------------

MR_PRICE = 100.0


def _atr_failure_payload(price: float = MR_PRICE) -> dict:
    """`technical-analysis/app/indicators/atr.py::_default_response()`, verbatim.

    The trap this pins: the failure payload is NOT empty. `atr` and `atr_pct`
    are 0.0, but stop_loss_long/short are POPULATED at a hardcoded 3%.
    """
    return {
        "atr": 0.0,
        "atr_pct": 0.0,
        "stop_loss_long": float(price * 0.97),
        "stop_loss_short": float(price * 1.03),
        "take_profit_long": float(price * 1.06),
        "take_profit_short": float(price * 0.94),
        "volatility": "UNKNOWN",
        "confidence": 0.3,
        "description": "Insufficient data - using default 3% SL",
        "risk_reward_ratio": 2.0,
        "timestamp": 0,
    }


def _rsi(value: float):
    """RSI as signal_aggregator.fetch_rsi builds it — reading on `.value`."""
    return IndicatorSignal(
        name="RSI",
        signal=SignalAction.HOLD,
        confidence=0.5,
        value=value,
        metadata={"period": 9, "weight": 1.0},
    )


def _sma(value: float):
    return IndicatorSignal(
        name="SMA",
        signal=SignalAction.HOLD,
        confidence=0.3,
        value=value,
        metadata={"period": 21, "weight": 0.8},
    )


def _mr_signal(action: SignalAction, indicators: dict, metadata: dict):
    """An aggregator signal carrying a real indicator dict for the legs."""
    return TradingSignal(
        symbol="SOLUSDT",
        timestamp=0,
        action=action,
        confidence=0.30,
        aggregated_score=0.30 if action == SignalAction.BUY else -0.30,
        consensus_count=3,
        indicators=indicators,
        metadata=metadata,
    )


def _spy_on_mean_reversion(monkeypatch):
    """Capture the mean_reversion leg's REAL output as the ensemble dispatches it.

    Wrapping rather than stubbing is the point: it proves the ensemble hands
    the leg the ATR, instead of proving the leg works when a test hands it one.
    """
    from app.strategies.mean_reversion_strategy import MeanReversionStrategy

    captured = {}
    real = MeanReversionStrategy.generate_signal

    def wrapper(self, indicators, current_price, capital=None):
        out = real(self, indicators, current_price, capital)
        captured["indicators"] = indicators
        captured["signal"] = out
        return out

    monkeypatch.setattr(MeanReversionStrategy, "generate_signal", wrapper)
    return captured


SMA_DEVIATION_SIGNALS = {
    "PRICE_BELOW_SMA",
    "PRICE_EXTREME_BELOW_SMA",
    "PRICE_ABOVE_SMA",
    "PRICE_EXTREME_ABOVE_SMA",
}


def test_mean_reversion_sma_deviation_fires_when_a_usable_atr_is_threaded(
    ensemble_module, monkeypatch
):
    """The unlock. `atr_value` was ALWAYS None, so this branch was dead code.

    mean_reversion_strategy.py:169 gates the SMA-deviation sub-signals on
    `sma_value and atr_value and atr_value > 0`, and `atr_value` comes from
    `indicators["ATR"]` — a key nothing ever wrote. The branch was
    unreachable in production for the lifetime of the leg.

    Fixture: price 100 sits 5.0 below a 105.0 SMA against a 2.0 ATR, i.e. a
    2.5x deviation, past MEAN_DEVIATION_THRESHOLD = 2.0. RSI 25 supplies the
    second aligned indicator MIN_INDICATORS_ALIGNED = 2 requires.
    """
    captured = _spy_on_mean_reversion(monkeypatch)
    indicators = {"RSI": _rsi(25.0), "SMA": _sma(105.0)}

    ensemble_module.MultiStrategyEnsemble().generate_signal(
        _mr_signal(SignalAction.BUY, indicators, {"atr": _atr_payload(MR_PRICE)}),
        current_price=MR_PRICE,
    )

    assert "ATR" in captured["indicators"], (
        "the ensemble did not hand the mean_reversion leg an ATR at all"
    )
    mr = captured["signal"]
    assert mr is not None, (
        "RSI_OVERSOLD + PRICE_BELOW_SMA is 2 aligned indicators at confidence "
        "0.35 — the leg must fire"
    )
    assert mr.action == SignalAction.BUY
    assert "PRICE_BELOW_SMA" in mr.indicators_aligned, (
        f"the SMA-deviation sub-signal is still unreachable: {mr.indicators_aligned}"
    )


def test_mean_reversion_sma_deviation_mirrors_for_sell(ensemble_module, monkeypatch):
    """The ABOVE-SMA branch must behave symmetrically."""
    captured = _spy_on_mean_reversion(monkeypatch)
    indicators = {"RSI": _rsi(75.0), "SMA": _sma(95.0)}

    ensemble_module.MultiStrategyEnsemble().generate_signal(
        _mr_signal(SignalAction.SELL, indicators, {"atr": _atr_payload(MR_PRICE)}),
        current_price=MR_PRICE,
    )

    mr = captured["signal"]
    assert mr is not None
    assert mr.action == SignalAction.SELL
    assert "PRICE_ABOVE_SMA" in mr.indicators_aligned, (
        f"expected the mirrored deviation sub-signal, got {mr.indicators_aligned}"
    )


def test_mean_reversion_sma_deviation_is_unreachable_without_atr(ensemble_module, monkeypatch):
    """State (b): no metadata['atr'] at all.

    Identical fixture to the unlock test above, minus the ATR. The leg must
    fall silent rather than fabricate a deviation — this is the OLD behavior,
    pinned so the contrast is measured and not assumed.
    """
    captured = _spy_on_mean_reversion(monkeypatch)
    indicators = {"RSI": _rsi(25.0), "SMA": _sma(105.0)}

    ensemble_module.MultiStrategyEnsemble().generate_signal(
        _mr_signal(SignalAction.BUY, indicators, {"buy_count": 3}),
        current_price=MR_PRICE,
    )

    assert "ATR" not in captured["indicators"], (
        "no ATR payload was published — none may be invented"
    )
    mr = captured["signal"]
    assert mr is None, (
        "with only RSI_OVERSOLD aligned the leg is below "
        "MIN_INDICATORS_ALIGNED=2 and must stay silent"
    )


def test_absent_atr_leaves_every_leg_on_its_documented_default(ensemble_module, monkeypatch):
    """State (b), all three legs: fall back, never fabricate.

    simple_rsi reports its named 2% default in its own reasoning; the
    multi-indicator leg reports the UNUSABLE_LEVEL sentinel; the synthetic
    indicator is not built at all.
    """
    from app.strategies.simple_rsi_strategy import SimpleRSIStrategy

    agg = _mr_signal(SignalAction.BUY, {"RSI": _rsi(25.0)}, {"buy_count": 3})

    assert ensemble_module.MultiStrategyEnsemble._atr_indicator(agg) is None
    assert ensemble_module.MultiStrategyEnsemble._atr_levels(agg) == (
        ensemble_module.UNUSABLE_LEVEL,
        ensemble_module.UNUSABLE_LEVEL,
    )

    rsi_leg = SimpleRSIStrategy().generate_signal({"RSI": _rsi(25.0)}, current_price=MR_PRICE)
    assert rsi_leg is not None
    expected_pct = SimpleRSIStrategy.DEFAULT_ATR_FRACTION * 100
    assert any(f"ATR-based stop {expected_pct:.2f}%" in r for r in rsi_leg.reasoning), (
        f"the leg must report its NAMED default, got {rsi_leg.reasoning}"
    )


def test_failure_payload_is_rejected_rather_than_traded_at_an_undeclared_3pct(
    ensemble_module, guard, monkeypatch, caplog
):
    """State (c): `atr.py::_default_response()` — the loud-failure path.

    DISCRETIONARY MECHANISM CHOICE, not an application of the locked wording.
    CONTEXT's P21-1 clause says "fallback 2% only when ATR is genuinely
    absent". That describes a FALLBACK. What lands here is a full-signal
    REJECTION, which has a larger blast radius, so it is recorded under
    CONTEXT's Claude's-Discretion clause ("exact mechanism for ATR threading
    ... pick the one with the smallest blast radius and best testability")
    and 21-RESEARCH.md Option 1, and it is surfaced for operator sign-off at
    the 21-09 checkpoint decision list.

    The tradeoff, stated so a reviewer can overturn it deliberately:

      * REJECTION (chosen) fails safe and makes the fetch failure visible.
        Before this change the same payload silently traded a 3% stop nobody
        chose, presented downstream as if it were a real ATR level.
      * A 2%-FALLBACK alternative would preserve trade admission but re-hide
        the failure behind a plausible number — the exact failure mode the
        UNUSABLE_LEVEL sentinel doctrine exists to prevent.

    Admission therefore DECREASES on ATR fetch failure. That reduction
    originates in P21-1 and belongs to the "+ATR" arm of the 21-09 ablation,
    not the "+gates" arm.
    """
    failure = _atr_failure_payload()
    assert failure["stop_loss_long"] > 0 and failure["stop_loss_short"] > 0, (
        "the populated 3% stops are the whole reason this payload is dangerous"
    )

    agg = _mr_signal(SignalAction.BUY, {}, {"atr": failure})

    with caplog.at_level("ERROR"):
        sl, tp = ensemble_module.MultiStrategyEnsemble._atr_levels(agg)

    assert (sl, tp) == (
        ensemble_module.UNUSABLE_LEVEL,
        ensemble_module.UNUSABLE_LEVEL,
    ), "the 3% failure default must not be presented as an ATR level"
    assert ensemble_module._atr_is_usable(failure) is False
    assert ensemble_module.MultiStrategyEnsemble._atr_indicator(agg) is None

    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert error_records, "an ATR fetch failure must be loud, not swallowed"
    assert "FAILURE" in caplog.text and "SOLUSDT" in caplog.text

    assert guard(SignalAction.BUY, MR_PRICE, sl, tp) is False, (
        "the sentinel must reach the pre-fill guard as a rejection"
    )


def test_failure_payload_reaches_the_guard_as_a_rejection_end_to_end(
    ensemble_module, guard, monkeypatch
):
    """State (c) through generate_signal: the entry is refused, not resized."""
    _multi_leg_only(monkeypatch, ensemble_module)

    out = ensemble_module.MultiStrategyEnsemble().generate_signal(
        _signal(SignalAction.BUY, {"atr": _atr_failure_payload(PRICE)}),
        current_price=PRICE,
    )

    assert out is not None, "the leg still votes — only its levels are unusable"
    assert out.stop_loss == ensemble_module.UNUSABLE_LEVEL
    assert guard(out.action, out.entry_price, out.stop_loss, out.take_profit) is False, (
        "before P21-1 this payload's populated 3% stop passed the guard and was traded"
    )
