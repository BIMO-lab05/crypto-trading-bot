"""P21-2: agreement across ensemble legs must span more than one SOURCE.

The defect
----------
``MultiStrategyEnsemble.generate_signal`` counted "agreeing legs" without
asking what each leg had actually read. ``simple_rsi`` reads exactly one
indicator key -- ``indicators.get("RSI")`` -- so it is structurally a
MOMENTUM-only leg, and ``mean_reversion``'s cheapest firing route also starts
from the same RSI print. Two legs echoing one RSI reading were presented
downstream as independent multi-leg confirmation.

Why it matters NOW
------------------
Before 2026-08-23 the weighted score was normalised over ALL THREE legs'
weight, so a lone leg was capped at 1/3 of its conviction and could not clear
the 0.30 downstream floor whatever it believed. The fix that normalises over
*directional* legs only (multi_strategy_ensemble.py, "Denominator = the weight
of the legs that actually took a side") made single-leg admission reachable --
which is exactly what turns single-source agreement into a live trade.

What must NOT change
--------------------
``21-CONTEXT.md`` locks ``MIN_AGREEING_LEGS = 1``, ``AGGREGATION_THRESHOLD =
0.10`` and ``min_signal_confidence = 0.30``. A category guard is
``MIN_AGREEING_LEGS = 2`` wearing a different hat *unless* it diverges on the
one case that separates them:

    | agreeing legs             | categories | diversity guard | MIN_LEGS = 2 |
    |---------------------------|------------|-----------------|--------------|
    | simple_rsi alone          | {MOMENTUM} | block           | block        |
    | simple_rsi + mean_rev     | 2          | pass            | pass         |
    | multi_indicator alone     | >= 2 (ctor)| PASS            | block        |

The third row is the load-bearing assertion in this file, and it is the same
claim as Plan 21-05's ``threshold_lock`` test. ``multi_indicator`` carries the
full nine-voter gate stack and has ALREADY cleared ``CoreAggregator``'s own
``check_category_diversity(..., min_categories=2)``; blocking it would be
double jeopardy on the strongest leg.

Task 2 (rejection telemetry) is tested in the second half of this file.

"""

import importlib
import pathlib
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.enums import SignalAction
from app.models.signal import TradingSignal


@pytest.fixture
def ensemble_module():
    """Fresh class binding per test (the module holds a weights singleton)."""
    import app.strategies.multi_strategy_ensemble as mod

    importlib.reload(mod)
    return mod


PRICE = 100.0


def _atr_payload(price: float = PRICE) -> dict:
    """`signal_aggregator.fetch_atr`'s payload, as metadata['atr']."""
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


def _agg_signal(action, confidence, price: float = PRICE, indicators=None):
    return TradingSignal(
        symbol="SOLUSDT",
        timestamp=0,
        action=action,
        confidence=confidence,
        aggregated_score=confidence if action == SignalAction.BUY else -confidence,
        consensus_count=5,
        indicators=indicators or {},
        metadata={"atr": _atr_payload(price)},
    )


def _rsi_leg(action, confidence, price: float = PRICE):
    """Duck-type of SimpleRSISignal as the ensemble reads it."""
    return SimpleNamespace(
        action=action,
        confidence=confidence,
        stop_loss=price * 0.98,
        take_profit=price * 1.04,
        reasoning=["stub simple_rsi leg"],
    )


def _mean_reversion_leg(action, confidence, indicators_aligned, price: float = PRICE):
    """Duck-type of MeanReversionSignal INCLUDING `indicators_aligned`.

    The field is not decorative here: it is the only honest source for which
    indicators this leg consumed, and the guard is written against it rather
    than against an assumption that Bollinger is always present.
    """
    return SimpleNamespace(
        action=action,
        confidence=confidence,
        stop_loss=price * 0.98,
        target=price * 1.04,
        indicators_aligned=list(indicators_aligned),
        reasoning=["stub mean_reversion leg"],
    )


def _stub_legs(monkeypatch, rsi=None, mean_rev=None):
    """Stub the two dict-dispatched legs. Weights are deliberately NOT pinned."""
    from app.strategies.mean_reversion_strategy import MeanReversionStrategy
    from app.strategies.simple_rsi_strategy import SimpleRSIStrategy

    monkeypatch.setattr(SimpleRSIStrategy, "generate_signal", lambda self, *a, **kw: rsi)
    monkeypatch.setattr(MeanReversionStrategy, "generate_signal", lambda self, *a, **kw: mean_rev)


# ===========================================================================
# Task 1 -- the guard's behaviour
# ===========================================================================


def test_simple_rsi_alone_is_blocked_as_single_source(ensemble_module, monkeypatch, caplog):
    """The P21-2 case. One MOMENTUM-only leg is not multi-leg confirmation.

    `simple_rsi` reads exactly one indicator key, so however strong its
    conviction it can never be corroboration of itself.
    """
    _stub_legs(monkeypatch, rsi=_rsi_leg(SignalAction.BUY, 0.80))
    ens = ensemble_module.MultiStrategyEnsemble()
    caplog.set_level("INFO")

    out = ens.generate_signal(
        _agg_signal(SignalAction.HOLD, 0.0), current_price=PRICE, capital=None
    )

    assert out is None, (
        "simple_rsi at conviction 0.80 clears every threshold, so only a "
        "source-diversity rule can stop it -- and it must"
    )
    assert "diversity" in caplog.text.lower(), "the rejection must name its cause in the log stream"


def test_multi_indicator_alone_at_the_conviction_floor_still_emits(ensemble_module, monkeypatch):
    """LOAD-BEARING: no double jeopardy on the leg that already passed.

    This is the row where a category rule and ``MIN_AGREEING_LEGS = 2``
    diverge, and it is the same claim as Plan 21-05's
    ``test_threshold_lock_lone_multi_indicator_leg_at_the_conviction_floor_emits``.

    If this fails, the guard was implemented as a leg count rather than a
    category rule. Revert and re-derive -- do NOT relax the assertion.
    """
    from app.config import get_settings

    _stub_legs(monkeypatch)
    ens = ensemble_module.MultiStrategyEnsemble()
    floor = get_settings().min_signal_confidence

    out = ens.generate_signal(
        _agg_signal(SignalAction.BUY, floor), current_price=PRICE, capital=None
    )

    assert out is not None, (
        "DOUBLE JEOPARDY: the multi_indicator leg has already cleared "
        "CoreAggregator's check_category_diversity(min_categories=2). Blocking "
        "it here re-runs a gate it passed and silences the strongest leg."
    )
    assert out.action == SignalAction.BUY


def test_rsi_plus_mean_reversion_with_bollinger_passes(ensemble_module, monkeypatch):
    """{MOMENTUM} union {MOMENTUM, VOLATILITY} = 2 categories -> pass."""
    _stub_legs(
        monkeypatch,
        rsi=_rsi_leg(SignalAction.BUY, 0.60),
        mean_rev=_mean_reversion_leg(SignalAction.BUY, 0.45, ["RSI_OVERSOLD", "BB_LOWER"]),
    )
    ens = ensemble_module.MultiStrategyEnsemble()

    out = ens.generate_signal(
        _agg_signal(SignalAction.HOLD, 0.0), current_price=PRICE, capital=None
    )

    assert out is not None, (
        "a Bollinger co-signal is genuinely independent information -- "
        "MOMENTUM + VOLATILITY must pass"
    )
    assert out.action == SignalAction.BUY


def test_rsi_plus_mean_reversion_with_sma_deviation_passes(ensemble_module, monkeypatch):
    """{MOMENTUM} union {MOMENTUM, TREND} = 2 categories -> pass.

    This is the SECOND mean_reversion firing route, and it exists only since
    Plan 21-03 threaded a real ATR into the leg -- the SMA-deviation branch is
    gated on ``atr_value > 0`` and was dead code before. A guard written
    against "Bollinger is always there" would wrongly block it.
    """
    _stub_legs(
        monkeypatch,
        rsi=_rsi_leg(SignalAction.BUY, 0.60),
        mean_rev=_mean_reversion_leg(SignalAction.BUY, 0.35, ["RSI_OVERSOLD", "PRICE_BELOW_SMA"]),
    )
    ens = ensemble_module.MultiStrategyEnsemble()

    out = ens.generate_signal(
        _agg_signal(SignalAction.HOLD, 0.0), current_price=PRICE, capital=None
    )

    assert out is not None, (
        "RSI + SMA-deviation is MOMENTUM + TREND. Post-21-03 this is a real "
        "firing route and must not be blocked."
    )


def test_rsi_only_agreement_between_two_legs_is_still_blocked(ensemble_module, monkeypatch):
    """must_have truth #1, stated literally.

    Two legs both reading the same RSI print span ONE category and must not
    count as independent confirmation. ``mean_reversion`` cannot reach this
    shape in production today (``MIN_INDICATORS_ALIGNED = 2`` needs a
    Bollinger or SMA co-signal), so this pins the RULE rather than a currently
    reachable payload -- if that constant ever moves, the guard is already
    right.
    """
    _stub_legs(
        monkeypatch,
        rsi=_rsi_leg(SignalAction.BUY, 0.60),
        mean_rev=_mean_reversion_leg(SignalAction.BUY, 0.50, ["RSI_EXTREME"]),
    )
    ens = ensemble_module.MultiStrategyEnsemble()

    out = ens.generate_signal(
        _agg_signal(SignalAction.HOLD, 0.0), current_price=PRICE, capital=None
    )

    assert out is None, (
        "both legs read the SAME RSI print; two echoes of one number are not "
        "two independent confirmations"
    )


def test_hold_outcome_short_circuits_the_guard(ensemble_module, monkeypatch, caplog):
    """Mirrors ``voter.check_category_diversity``: HOLD needs no diversity.

    Equal and opposite legs net the weighted score to exactly zero, so no leg
    "agrees" and the proposed action is HOLD. The guard must abstain and let
    the MIN_AGREEING_LEGS check own the rejection -- otherwise every
    zero-score evaluation would be mis-attributed to diversity in the funnel
    and the 21-09 ablation would read a delta that never happened.
    """
    _stub_legs(
        monkeypatch,
        rsi=_rsi_leg(SignalAction.BUY, 0.60),
        mean_rev=_mean_reversion_leg(SignalAction.SELL, 0.60, ["RSI_OVERBOUGHT", "BB_UPPER"]),
    )
    ens = ensemble_module.MultiStrategyEnsemble()
    caplog.set_level("INFO")

    out = ens.generate_signal(
        _agg_signal(SignalAction.HOLD, 0.0), current_price=PRICE, capital=None
    )

    assert out is None
    assert "legs agree" in caplog.text, (
        "a zero-score HOLD outcome must be rejected by the agreement gate"
    )
    assert "diversity" not in caplog.text.lower(), (
        "the diversity guard must abstain on a HOLD outcome; attributing this "
        "rejection to diversity would corrupt the 21-09 ablation's per-cause "
        f"counts. Log was: {caplog.text}"
    )


def test_unresolvable_leg_sources_fail_open(ensemble_module, monkeypatch, caplog):
    """Fail OPEN when a leg's sources cannot be read -- and say so loudly.

    Why this is defensible rather than convenient: ``simple_rsi`` is hardcoded
    to ``{"RSI"}`` and is ALWAYS resolvable, so the guard's actual target can
    never take this path; and ``mean_reversion`` cannot be single-source at all
    (``MIN_INDICATORS_ALIGNED = 2``). Failing open therefore cannot defeat the
    guard's stated purpose, while failing CLOSED on a malformed leg object
    would turn one upstream shape change into a silent halt of the whole
    trading path -- the same doctrine Plan 21-05 applied to
    ``demoted_to_hold``.
    """
    broken = SimpleNamespace(
        action=SignalAction.BUY,
        confidence=0.50,
        stop_loss=PRICE * 0.98,
        target=PRICE * 1.04,
        reasoning=["no indicators_aligned at all"],
    )
    _stub_legs(monkeypatch, rsi=_rsi_leg(SignalAction.BUY, 0.60), mean_rev=broken)
    ens = ensemble_module.MultiStrategyEnsemble()
    caplog.set_level("WARNING")

    out = ens.generate_signal(
        _agg_signal(SignalAction.HOLD, 0.0), current_price=PRICE, capital=None
    )

    assert out is not None, (
        "an unresolvable leg must degrade to the pre-guard behaviour, never to a silent global halt"
    )
    assert "diversity" in caplog.text.lower(), (
        "failing open without a WARNING is how a guard quietly stops guarding"
    )


# ---------------------------------------------------------------------------
# Taxonomy completeness -- the analog of
# tests/aggregation/test_indicator_categories.py::test_every_live_voter_is_categorised
# ---------------------------------------------------------------------------

# Every sub-signal `MeanReversionStrategy` can append, read from its source.
MEAN_REVERSION_SUB_SIGNALS = (
    "RSI_EXTREME",
    "RSI_OVERSOLD",
    "RSI_OVERBOUGHT",
    "BB_LOWER",
    "BB_NEAR_LOWER",
    "BB_UPPER",
    "BB_NEAR_UPPER",
    "PRICE_EXTREME_BELOW_SMA",
    "PRICE_BELOW_SMA",
    "PRICE_EXTREME_ABOVE_SMA",
    "PRICE_ABOVE_SMA",
)


def test_no_firing_leg_source_falls_through_to_other(ensemble_module):
    """An uncategorised source would silently INFLATE diversity, not reduce it.

    Note this file's deliberate divergence from
    ``voter.calculate_category_consensus``, which counts ``"OTHER"`` as an
    agreeing category. Here an unmapped name is dropped instead, because at
    the leg level "OTHER" would hand a single-source leg a free second
    category and switch the guard off without any test going red.
    """
    mod = ensemble_module
    uncategorised = []
    for token in MEAN_REVERSION_SUB_SIGNALS:
        name = mod._mean_reversion_source(token)
        if name is None or mod._indicator_category(name) == "OTHER":
            uncategorised.append(token)

    assert not uncategorised, f"uncategorised mean_reversion sources: {uncategorised}"
    assert mod._indicator_category("RSI") != "OTHER", "simple_rsi's only source must be categorised"


def test_every_sub_signal_in_the_source_file_is_mapped(ensemble_module):
    """Drift guard: scan the REAL leg for sub-signals this file has not seen.

    A new sub-signal added to ``mean_reversion_strategy.py`` without a mapping
    here would be dropped from the category union, quietly making the guard
    stricter than intended -- or, if OTHER were counted, quietly switching it
    off. Either way the failure is invisible without this scan.
    """
    import app.strategies.mean_reversion_strategy as mr_mod

    src = pathlib.Path(mr_mod.__file__).read_text()
    tokens = set(re.findall(r'_signals\.append\(\s*"([A-Z_]+)"\s*\)', src))

    assert tokens, (
        "the scanner matched nothing -- the regex has drifted from the source "
        "and this guard is now vacuous"
    )
    assert tokens == set(MEAN_REVERSION_SUB_SIGNALS), (
        f"MEAN_REVERSION_SUB_SIGNALS is stale. In source but not listed: "
        f"{sorted(tokens - set(MEAN_REVERSION_SUB_SIGNALS))}; listed but gone "
        f"from source: {sorted(set(MEAN_REVERSION_SUB_SIGNALS) - tokens)}"
    )
    unmapped = sorted(t for t in tokens if ensemble_module._mean_reversion_source(t) is None)
    assert not unmapped, f"unmapped mean_reversion sub-signals: {unmapped}"


def test_the_guard_reuses_the_voter_taxonomy_rather_than_restating_it(
    ensemble_module,
):
    """One taxonomy, not two.

    MACD's 2026-08-23 move from MOMENTUM to TREND is the measured precedent:
    a second map drifts, and the drift reported "trend + momentum" when it had
    trend + trend. This asserts object identity against the voter's map so a
    copy cannot be introduced without going red.
    """
    from app.aggregation.voter import INDICATOR_CATEGORIES

    assert ensemble_module.INDICATOR_CATEGORIES is INDICATOR_CATEGORIES, (
        "the ensemble must reference voter.INDICATOR_CATEGORIES itself, not a copy"
    )
    assert ensemble_module._indicator_category("RSI") == "MOMENTUM"
    assert ensemble_module._indicator_category("BOLLINGER_BANDS") == "VOLATILITY"
    assert ensemble_module._indicator_category("SMA") == "TREND"


def test_locked_thresholds_are_untouched_by_the_guard(ensemble_module):
    """The guard must not be a smuggled MIN_AGREEING_LEGS = 2."""
    from app.config import get_settings

    cls = ensemble_module.MultiStrategyEnsemble
    assert cls.MIN_AGREEING_LEGS == 1
    assert cls.AGGREGATION_THRESHOLD == 0.10
    assert get_settings().min_signal_confidence == 0.30
    assert cls.MIN_LEG_CATEGORIES == 2, (
        "the leg guard mirrors CoreAggregator's own "
        "check_category_diversity(min_categories=2) -- it is not a new knob"
    )


# ===========================================================================
# Task 2 -- structured rejection cause
# ===========================================================================


def _mtf_block(demoted, consolidated="HOLD", consensus="BUY"):
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


def test_mtf_demotion_reports_its_own_cause(ensemble_module, monkeypatch):
    _stub_legs(monkeypatch, rsi=_rsi_leg(SignalAction.BUY, 0.60))
    ens = ensemble_module.MultiStrategyEnsemble()
    sig = _agg_signal(SignalAction.HOLD, 0.0)
    sig.metadata["multi_timeframe"] = _mtf_block(True)

    assert ens.generate_signal(sig, current_price=PRICE, capital=None) is None
    assert ens.last_rejection.cause == "mtf_demoted"
    assert ens.last_rejection.detail, "a cause without a detail is half a log line"


def test_no_directional_legs_reports_its_own_cause(ensemble_module, monkeypatch):
    _stub_legs(monkeypatch)
    ens = ensemble_module.MultiStrategyEnsemble()

    assert (
        ens.generate_signal(_agg_signal(SignalAction.HOLD, 0.0), current_price=PRICE, capital=None)
        is None
    )
    assert ens.last_rejection.cause == "no_directional_legs"


def test_diversity_block_reports_its_own_cause(ensemble_module, monkeypatch):
    _stub_legs(monkeypatch, rsi=_rsi_leg(SignalAction.BUY, 0.80))
    ens = ensemble_module.MultiStrategyEnsemble()

    assert (
        ens.generate_signal(_agg_signal(SignalAction.HOLD, 0.0), current_price=PRICE, capital=None)
        is None
    )
    assert ens.last_rejection.cause == "insufficient_category_diversity"


def test_insufficient_agreeing_legs_reports_its_own_cause(
    ensemble_module, monkeypatch
):
    """The HOLD-outcome path, now attributed rather than merely logged.

    Equal and opposite legs net the weighted score to exactly zero, so nothing
    agrees with the (non-existent) winning side. The diversity guard abstains
    on a HOLD outcome, which is what lets this rejection land in its own
    bucket instead of diversity's.
    """
    _stub_legs(
        monkeypatch,
        rsi=_rsi_leg(SignalAction.BUY, 0.60),
        mean_rev=_mean_reversion_leg(
            SignalAction.SELL, 0.60, ["RSI_OVERBOUGHT", "BB_UPPER"]
        ),
    )
    ens = ensemble_module.MultiStrategyEnsemble()

    assert (
        ens.generate_signal(
            _agg_signal(SignalAction.HOLD, 0.0), current_price=PRICE, capital=None
        )
        is None
    )
    assert ens.last_rejection.cause == "insufficient_agreeing_legs"


def test_score_below_threshold_reports_its_own_cause(ensemble_module, monkeypatch):
    """The multi leg alone is diverse by construction, so only the score bites."""
    _stub_legs(monkeypatch)
    ens = ensemble_module.MultiStrategyEnsemble()

    assert (
        ens.generate_signal(_agg_signal(SignalAction.BUY, 0.05), current_price=PRICE, capital=None)
        is None
    )
    assert ens.last_rejection.cause == "score_below_threshold"


def test_a_successful_signal_clears_the_cause(ensemble_module, monkeypatch):
    from app.config import get_settings

    _stub_legs(monkeypatch)
    ens = ensemble_module.MultiStrategyEnsemble()

    out = ens.generate_signal(
        _agg_signal(SignalAction.BUY, get_settings().min_signal_confidence),
        current_price=PRICE,
        capital=None,
    )

    assert out is not None
    assert ens.last_rejection is None, (
        "a stale cause beside a live signal is worse than none -- an operator "
        "reads it as the reason the trade was blocked"
    )


def test_the_cause_does_not_carry_over_between_calls(ensemble_module, monkeypatch):
    """T-21-06-05. The ensemble is a process singleton evaluated symbol after
    symbol in one loop; a value left over from BTCUSDT must never be reported
    as ETHUSDT's cause."""
    _stub_legs(monkeypatch)
    ens = ensemble_module.MultiStrategyEnsemble()

    first = _agg_signal(SignalAction.HOLD, 0.0)
    first.metadata["multi_timeframe"] = _mtf_block(True)
    ens.generate_signal(first, current_price=PRICE, capital=None)
    assert ens.last_rejection.cause == "mtf_demoted"

    ens.generate_signal(_agg_signal(SignalAction.BUY, 0.05), current_price=PRICE, capital=None)
    assert ens.last_rejection.cause == "score_below_threshold", (
        "the second call reported the FIRST call's cause -- the reset at the "
        "top of generate_signal is missing or misplaced"
    )


def test_all_four_causes_are_distinct_identifiers(ensemble_module):
    """The 21-09 ablation cannot attribute a delta it cannot separate."""
    mod = ensemble_module
    causes = {
        mod.REJECT_MTF_DEMOTED,
        mod.REJECT_NO_DIRECTIONAL_LEGS,
        mod.REJECT_INSUFFICIENT_DIVERSITY,
        mod.REJECT_INSUFFICIENT_AGREEING_LEGS,
        mod.REJECT_SCORE_BELOW_THRESHOLD,
    }
    assert len(causes) == 5, f"rejection identifiers collide: {causes}"
    assert all(c == c.lower() and " " not in c for c in causes), (
        "identifiers must be stable snake_case so the funnel can group on them"
    )


# ---------------------------------------------------------------------------
# The key link: the cause must actually reach the trade funnel.
# ---------------------------------------------------------------------------


def _wire_auto_trader(monkeypatch, ensemble):
    """Minimal harness for `_check_and_trade_ensemble` up to the ensemble gate.

    Everything after `ensemble_signal_emitted` is unreachable here because the
    stubbed ensemble returns None, which is precisely the path under test.
    """
    from app.auto_trader import AutoTrader

    trader = AutoTrader.__new__(AutoTrader)
    trader.total_signals_checked = 0
    trader.total_trades_rejected = 0
    trader.interval = "60"
    trader.settings = SimpleNamespace(strategy_routing_mode="off")
    trader.hybrid_strategy = MagicMock()

    risk_mgr = MagicMock()
    risk_mgr.should_halt_trading = MagicMock(return_value=False)
    monkeypatch.setattr("app.auto_trader.get_risk_manager", lambda: risk_mgr)

    base_signal = SimpleNamespace(
        confidence=0.42,
        metadata={"atr": _atr_payload()},
        indicators={
            "RSI": SimpleNamespace(metadata={"current_price": PRICE}),
        },
    )
    aggregator = MagicMock()
    aggregator.get_trading_signal_multi_timeframe = AsyncMock(return_value=base_signal)

    async def _fake_get_aggregator():
        return aggregator

    monkeypatch.setattr("app.auto_trader.get_aggregator", _fake_get_aggregator)

    paper_engine = MagicMock()
    paper_engine.get_balance = MagicMock(return_value=1000.0)
    monkeypatch.setattr("app.auto_trader.get_paper_engine", lambda: paper_engine)

    import app.strategies.multi_strategy_ensemble as ens_mod

    monkeypatch.setattr(ens_mod, "get_ensemble", lambda: ensemble)
    return trader


def _ensemble_gate_reasons():
    from app.monitoring.signal_funnel import get_signal_funnel

    stages = get_signal_funnel().snapshot()["stages"]
    stage = next(s for s in stages if s["stage"] == "ensemble_signal_emitted")
    return stage["rejection_reasons"]


@pytest.mark.asyncio
async def test_the_funnel_records_the_specific_cause(ensemble_module, monkeypatch):
    """The whole point of Task 2: four causes, four buckets.

    Before this the funnel recorded one fixed ``ensemble_returned_hold`` whose
    detail string named only two of the four causes -- factually wrong for the
    MTF gate (21-05) and for the diversity guard (21-06).
    """
    from app.monitoring.signal_funnel import get_signal_funnel

    get_signal_funnel().reset()

    ensemble = MagicMock()
    ensemble.generate_signal = MagicMock(return_value=None)
    ensemble.last_rejection = ensemble_module.EnsembleRejection(
        cause=ensemble_module.REJECT_INSUFFICIENT_DIVERSITY,
        detail="agreeing legs span 1/2 categories (MOMENTUM)",
    )
    trader = _wire_auto_trader(monkeypatch, ensemble)

    await trader._check_and_trade_ensemble("SOLUSDT")

    reasons = _ensemble_gate_reasons()
    assert "insufficient_category_diversity" in reasons, (
        f"the funnel collapsed the cause into another bucket: {sorted(reasons)}"
    )
    assert "ensemble_returned_hold" not in reasons, (
        "a known cause must not be reported under the generic fallback"
    )
    assert reasons["insufficient_category_diversity"]["examples"], (
        "the detail string is what an operator reads -- it must not be empty"
    )


@pytest.mark.asyncio
async def test_the_funnel_falls_back_when_no_cause_is_set(ensemble_module, monkeypatch):
    """An unhandled return-None path must degrade to today's behaviour."""
    from app.monitoring.signal_funnel import get_signal_funnel

    get_signal_funnel().reset()

    ensemble = MagicMock()
    ensemble.generate_signal = MagicMock(return_value=None)
    ensemble.last_rejection = None
    trader = _wire_auto_trader(monkeypatch, ensemble)

    await trader._check_and_trade_ensemble("SOLUSDT")

    assert "ensemble_returned_hold" in _ensemble_gate_reasons(), (
        "the fallback must survive so an unhandled path logs something rather than crashing"
    )


def test_generate_signal_still_returns_an_optional_ensemble_signal(ensemble_module, monkeypatch):
    """The cause rides on the instance, NOT on the return type.

    Every existing caller and test expects ``Optional[EnsembleSignal]``;
    widening it to a tuple would break them all silently at the call site.
    """
    from app.config import get_settings

    _stub_legs(monkeypatch)
    ens = ensemble_module.MultiStrategyEnsemble()

    out = ens.generate_signal(
        _agg_signal(SignalAction.BUY, get_settings().min_signal_confidence),
        current_price=PRICE,
        capital=None,
    )

    assert isinstance(out, ensemble_module.EnsembleSignal)
    assert (
        ens.generate_signal(_agg_signal(SignalAction.BUY, 0.0), current_price=PRICE, capital=None)
        is None
    )
