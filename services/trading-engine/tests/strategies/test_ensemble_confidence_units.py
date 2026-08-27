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
        _agg_signal(SignalAction.BUY, 0.36), current_price=100.0, capital=None
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
        _agg_signal(SignalAction.BUY, 0.60), current_price=100.0, capital=None
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
        _agg_signal(SignalAction.BUY, 0.60), current_price=100.0, capital=None
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
        _agg_signal(SignalAction.BUY, 0.36), current_price=100.0, capital=None
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
        _agg_signal(SignalAction.BUY, 1.0), current_price=100.0, capital=None
    )

    assert out is not None
    assert 0.0 <= out.confidence <= 1.0, f"confidence out of range: {out.confidence}"


def test_min_agreeing_legs_still_enforced(ensemble_module, monkeypatch):
    """Renormalising must not weaken the agreement requirement."""
    _silence_legs(monkeypatch)
    ens = ensemble_module.MultiStrategyEnsemble()
    monkeypatch.setattr(ens, "MIN_AGREEING_LEGS", 2, raising=False)

    out = ens.generate_signal(
        _agg_signal(SignalAction.BUY, 0.90), current_price=100.0, capital=None
    )

    assert out is None, "one firing leg must not satisfy MIN_AGREEING_LEGS=2"


def test_aggregation_threshold_still_enforced(ensemble_module, monkeypatch):
    """A genuinely weak lone signal must still be rejected."""
    _silence_legs(monkeypatch)
    ens = ensemble_module.MultiStrategyEnsemble()

    out = ens.generate_signal(
        _agg_signal(SignalAction.BUY, 0.05), current_price=100.0, capital=None
    )

    assert out is None, (
        "conviction 0.05 is below AGGREGATION_THRESHOLD=0.10 and must not emit"
    )


# ---------------------------------------------------------------------------
# Phase 21 threshold lock (Plan 21-05, Task 1)
#
# Landed BEFORE any gating change in Plans 21-05 / 21-06 so every later change
# is measured against a floor that was observed green first.
# ---------------------------------------------------------------------------


def test_threshold_lock_lone_multi_indicator_leg_at_the_conviction_floor_emits(
    ensemble_module, monkeypatch
):
    """LOCK: one directional leg at conviction 0.30 must still produce a signal.

    What this locks
    ---------------
    The *effective* gate on ensemble admission -- not the constants that spell it
    out. ``21-CONTEXT.md`` locks three values for the whole of Phase 21:

        min_signal_confidence = 0.30   (app/config.py:506)
        AGGREGATION_THRESHOLD = 0.10   (multi_strategy_ensemble.py:239)
        MIN_AGREEING_LEGS     = 1      (multi_strategy_ensemble.py:242)

    behind the Phase-3 verdict: **no threshold change** -- IS/OOS rankings invert,
    so tuning them fits noise.

    Which plans would break it
    --------------------------
    Plan 21-05 gates every ensemble leg on an MTF demote-to-HOLD. Plan 21-06 adds
    a leg source-diversity guard so ``simple_rsi`` and ``mean_reversion``
    co-firing on the same RSI print stop counting as independent confirmation.
    Both are wiring fixes; neither may move the floor.

    A category-diversity guard is ``MIN_AGREEING_LEGS = 2`` wearing a different
    hat: it leaves all three constants untouched while making this exact payload
    -- the lone ``multi_indicator`` leg -- stop emitting. An over-broad
    ``action == HOLD`` suppression does the same. That is precisely why the
    load-bearing assertion here is BEHAVIORAL, and why the constants companion
    below is explicitly not sufficient on its own: a constants-only test passes
    in both worlds.

    The single-leg case is reachable at all only because the 2026-08-23 fix
    normalises the weighted score over the legs that took a *directional* side.
    Before it a lone leg was capped at 1/3 of its conviction and could never
    clear 0.30, so the two knobs contradicted each other.
    """
    from app.config import get_settings

    _silence_legs(monkeypatch)
    ens = ensemble_module.MultiStrategyEnsemble()

    floor = get_settings().min_signal_confidence

    out = ens.generate_signal(
        _agg_signal(SignalAction.BUY, floor), current_price=100.0, capital=None
    )

    assert out is not None, (
        "THRESHOLD LOCK BROKEN: a lone multi_indicator leg at conviction "
        f"{floor} no longer emits. No threshold value has to change for this to "
        "regress -- a diversity guard or an over-broad HOLD gate suppresses the "
        "same payload while MIN_AGREEING_LEGS, AGGREGATION_THRESHOLD and "
        "min_signal_confidence still read 1 / 0.10 / 0.30. Re-read "
        "21-CONTEXT.md's locked constraint before changing this."
    )
    assert out.action == SignalAction.BUY
    assert out.confidence == pytest.approx(floor, abs=1e-9), (
        f"conviction must survive undiluted: expected {floor}, got {out.confidence}"
    )
    assert out.confidence >= floor, (
        "the emitted conviction must still clear the downstream "
        "min_signal_confidence floor that "
        "auto_trader._ensemble_passes_signal_gates applies"
    )


def test_threshold_lock_constants_are_unchanged(ensemble_module):
    """The cheap companion to the behavioral lock above -- keep BOTH.

    This one alone proves nothing. Any effective-gate change (a diversity guard,
    a broad ``action == HOLD`` suppression, an MTF gate that swallows the
    single-leg case) leaves every constant byte-identical. It is here to catch
    the blunt edit and to name the approval requirement in its failure message.
    """
    from app.config import get_settings

    approval = (
        "Changing this value requires EXPLICIT OPERATOR APPROVAL -- CLAUDE.md "
        "section 5 (risk caps are non-negotiable) and 21-CONTEXT.md's locked "
        "constraint 'NO changes to threshold values'. The Phase-3 verdict "
        "stands: no threshold change, IS/OOS rankings invert."
    )

    ens_cls = ensemble_module.MultiStrategyEnsemble

    assert ens_cls.MIN_AGREEING_LEGS == 1, (
        f"MIN_AGREEING_LEGS is {ens_cls.MIN_AGREEING_LEGS}, expected 1. {approval}"
    )
    assert ens_cls.AGGREGATION_THRESHOLD == 0.10, (
        f"AGGREGATION_THRESHOLD is {ens_cls.AGGREGATION_THRESHOLD}, expected "
        f"0.10. {approval}"
    )
    assert get_settings().min_signal_confidence == 0.30, (
        f"min_signal_confidence is {get_settings().min_signal_confidence}, "
        f"expected 0.30. {approval}"
    )


# ---------------------------------------------------------------------------
# P21-3 (Plan 21-05, Task 3): an MTF demote-to-HOLD must suppress ALL legs.
#
# signal_aggregator applies the demoted action to `primary_signal.action`, and
# the `multi_indicator` leg honours it only incidentally -- its
# `action != HOLD and confidence > 0` guard happens to see it. `simple_rsi` and
# `mean_reversion` are dispatched off the INDICATOR DICT and never read
# `.action`, so they traded straight past a decision the system already made.
#
# The gate below is keyed on the narrow `demoted_to_hold` flag added in Task 2,
# NOT on `aggregator_signal.action == HOLD`. The broad reading would also
# swallow the regime hard-block and the upstream requirements gate, which
# 21-CONTEXT does not authorise.
# ---------------------------------------------------------------------------


def _mtf_block(demoted, consolidated="HOLD", consensus="BUY"):
    """metadata['multi_timeframe'] as signal_aggregator writes it post-Task-2."""
    return {
        "enabled": True,
        "timeframes": ["15", "60", "240"],
        "consensus_action": consensus,
        "consolidated_action": consolidated,
        "demoted_to_hold": demoted,
        "alignment_strength": "MODERATE",
        "confidence_modifier": 1.0,
        "agreement_pct": 0.0,
        "reasoning": "test",
        "timeframe_signals": {},
    }


def _agg_signal_mtf(action, confidence, mtf_block=None, price: float = 100.0):
    """`_agg_signal` plus an optional metadata['multi_timeframe'] block."""
    sig = _agg_signal(action, confidence, price)
    if mtf_block is not None:
        sig.metadata["multi_timeframe"] = mtf_block
    return sig


def _counting_legs(monkeypatch, rsi=None, mean_rev=None):
    """Like `_silence_legs`, but COUNTS dispatches so suppression is provable.

    Asserting the ensemble returned None is not enough on its own: a payload can
    return None for a dozen unrelated reasons. Zero dispatches proves the gate
    fired BEFORE any leg ran, which is what the plan actually specifies.
    """
    from app.strategies.simple_rsi_strategy import SimpleRSIStrategy
    from app.strategies.mean_reversion_strategy import MeanReversionStrategy

    calls = {"simple_rsi": 0, "mean_reversion": 0}

    def rsi_spy(self, *a, **kw):
        calls["simple_rsi"] += 1
        return rsi

    def mean_rev_spy(self, *a, **kw):
        calls["mean_reversion"] += 1
        return mean_rev

    monkeypatch.setattr(SimpleRSIStrategy, "generate_signal", rsi_spy)
    monkeypatch.setattr(MeanReversionStrategy, "generate_signal", mean_rev_spy)
    return calls


def test_mtf_demotion_suppresses_every_leg(ensemble_module, monkeypatch, caplog):
    """The P21-3 fix. Demotion silences all three legs, before any dispatch.

    The payload is the REALISTIC post-demotion shape: the aggregator's action is
    already HOLD (that is what demotion means), so `multi_indicator` is silenced
    by its own guard and cannot be what emits. The two legs that used to trade
    past the demotion -- `simple_rsi` and `mean_reversion` -- are both firing BUY
    at a conviction that clears AGGREGATION_THRESHOLD comfortably.
    """
    calls = _counting_legs(
        monkeypatch,
        rsi=_leg_stub(SignalAction.BUY, 0.60),
        mean_rev=_leg_stub(SignalAction.BUY, 0.60),
    )
    ens = ensemble_module.MultiStrategyEnsemble()
    caplog.set_level("INFO")

    out = ens.generate_signal(
        _agg_signal_mtf(SignalAction.HOLD, 0.0, _mtf_block(True)),
        current_price=100.0,
        capital=None,
    )

    assert out is None, (
        "multi-timeframe consolidation demoted this consensus to HOLD; no leg "
        "may trade past it"
    )
    assert calls == {"simple_rsi": 0, "mean_reversion": 0}, (
        f"the gate must fire BEFORE any leg is dispatched, got {calls}. A leg "
        "that ran and was discarded later is not suppression -- it is a "
        "coincidence that depends on the score arithmetic."
    )
    assert "demoted" in caplog.text.lower(), (
        "the suppression must be visible in the funnel log, named by cause"
    )


def test_the_same_payload_without_the_flag_still_emits(
    ensemble_module, monkeypatch
):
    """POSITIVE CONTROL for the test above -- do not delete.

    Identical payload minus `demoted_to_hold`. If this did not emit, the
    suppression test would pass vacuously: it would be asserting None against a
    payload that never produced a signal in the first place. This is the
    assertion that makes the pair load-bearing.
    """
    calls = _counting_legs(
        monkeypatch,
        rsi=_leg_stub(SignalAction.BUY, 0.60),
        mean_rev=_leg_stub(SignalAction.BUY, 0.60),
    )
    ens = ensemble_module.MultiStrategyEnsemble()

    out = ens.generate_signal(
        _agg_signal_mtf(SignalAction.HOLD, 0.0, None),
        current_price=100.0,
        capital=None,
    )

    assert out is not None, (
        "without a demotion flag this payload MUST emit -- two BUY legs at 0.60 "
        "clear both MIN_AGREEING_LEGS and AGGREGATION_THRESHOLD. If it does "
        "not, the suppression test above proves nothing."
    )
    assert out.action == SignalAction.BUY
    assert calls == {"simple_rsi": 1, "mean_reversion": 1}


def test_explicit_false_does_not_suppress(ensemble_module, monkeypatch):
    """`demoted_to_hold: False` is the common case and must be inert."""
    _counting_legs(
        monkeypatch,
        rsi=_leg_stub(SignalAction.BUY, 0.60),
        mean_rev=_leg_stub(SignalAction.BUY, 0.60),
    )
    ens = ensemble_module.MultiStrategyEnsemble()

    out = ens.generate_signal(
        _agg_signal_mtf(SignalAction.HOLD, 0.0, _mtf_block(False)),
        current_price=100.0,
        capital=None,
    )

    assert out is not None, "a consensus that was not demoted must still trade"


@pytest.mark.parametrize(
    "malformed",
    [
        pytest.param("true", id="truthy-string"),
        pytest.param(1, id="int-one"),
        pytest.param("HOLD", id="action-string"),
        pytest.param([True], id="non-empty-list"),
        pytest.param({"demoted": True}, id="nested-dict"),
    ],
)
def test_malformed_demoted_to_hold_value_does_not_suppress(
    ensemble_module, monkeypatch, malformed
):
    """T-21-05-02: a malformed metadata value must not halt ALL trading.

    The check is an IDENTITY test against `True`, not a truthiness test. This
    field is an untyped dict entry that now decides whether any trade is
    produced at all; if a truthy string or a stray `1` could trip it, one
    upstream typo becomes a silent, total denial of service on the trading path
    -- with no error and no log to find it by. Fail OPEN here: a wrong value
    must degrade to the pre-fix behaviour, not to a global halt.

    Note `1 is True` is False in CPython even though `1 == True` is True. That
    distinction is the entire mechanism, so the int case is deliberate.
    """
    _counting_legs(
        monkeypatch,
        rsi=_leg_stub(SignalAction.BUY, 0.60),
        mean_rev=_leg_stub(SignalAction.BUY, 0.60),
    )
    ens = ensemble_module.MultiStrategyEnsemble()

    out = ens.generate_signal(
        _agg_signal_mtf(SignalAction.HOLD, 0.0, _mtf_block(malformed)),
        current_price=100.0,
        capital=None,
    )

    assert out is not None, (
        f"demoted_to_hold={malformed!r} is not the boolean True and must not "
        "suppress. A truthiness check here would let one malformed upstream "
        "value silently kill every signal the engine produces."
    )


@pytest.mark.parametrize(
    "not_a_dict",
    [
        pytest.param("enabled", id="string"),
        pytest.param(["15", "60"], id="list"),
        pytest.param(7, id="int"),
    ],
)
def test_non_dict_multi_timeframe_metadata_does_not_crash(
    ensemble_module, monkeypatch, not_a_dict
):
    """The gate reads an untyped dict entry -- it must not raise on garbage.

    `metadata['multi_timeframe']` is written by signal_aggregator as a dict, but
    nothing enforces that. An AttributeError here would propagate out of
    `generate_signal` on the live signal path.
    """
    _counting_legs(
        monkeypatch,
        rsi=_leg_stub(SignalAction.BUY, 0.60),
        mean_rev=_leg_stub(SignalAction.BUY, 0.60),
    )
    ens = ensemble_module.MultiStrategyEnsemble()

    out = ens.generate_signal(
        _agg_signal_mtf(SignalAction.HOLD, 0.0, not_a_dict),
        current_price=100.0,
        capital=None,
    )

    assert out is not None, (
        "a non-dict multi_timeframe block must degrade to no-suppression, "
        "not raise and not halt trading"
    )
