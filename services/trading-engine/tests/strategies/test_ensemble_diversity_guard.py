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
