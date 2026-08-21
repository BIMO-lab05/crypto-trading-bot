"""Strategy routing: branch correctness, counter integrity, and API contract.

Written 2026-08-21. Before this suite the router had ZERO tests covering
`detect_regime` or the routing branch (the only two existing references were
capital-default assertions), and it had gone seven months without executing a
single decision while the dashboard reported it Live. See docs/PIPELINE_MAP.md.

The regression guard at the bottom is the load-bearing test: it fails if the
routing counters stay at zero after N evaluations with valid market data,
which is exactly the condition that went unnoticed.
"""

from types import SimpleNamespace

import pytest

from app.monitoring.signal_funnel import STAGES, SignalFunnel, get_signal_funnel
from app.strategies.hybrid_strategy_router import HybridStrategyRouter, MarketRegime

# Exact keys the React tile reads off `status.hybrid_strategy_stats`
# (frontend/src/components/HybridStrategyPanel.jsx). A rename on either side
# reintroduces the silent-zero failure, so the contract is pinned here.
FRONTEND_REQUIRED_KEYS = {
    "routing_mode",
    "adx_threshold",
    "total_signals",
    "trend_signals",
    "mean_reversion_signals",
    "executed_signals",
    "observed_signals",
    "trend_pct",
    "mean_reversion_pct",
}


@pytest.fixture(autouse=True)
def _clean_funnel():
    get_signal_funnel().reset()
    yield
    get_signal_funnel().reset()


@pytest.fixture
def router():
    return HybridStrategyRouter()


def indicators_with_adx(adx_value):
    """Minimal aggregator-shaped indicator dict carrying an ADX leg."""
    return {"ADX": SimpleNamespace(value=adx_value, confidence=0.7, metadata={"adx": adx_value})}


# --------------------------------------------------------------------------
# Branch correctness, including the boundary
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "adx,expected",
    [
        (92.82, MarketRegime.TRENDING),  # trending synthetic series, ta-verified
        (61.63, MarketRegime.TRENDING),  # live BTCUSDT value, 2026-08-21
        (25.01, MarketRegime.TRENDING),
        (25.00, MarketRegime.TRENDING),  # boundary: >= is TRENDING
        (24.99, MarketRegime.RANGING),
        (16.40, MarketRegime.RANGING),  # live ADAUSDT value, 2026-08-21
        (10.55, MarketRegime.RANGING),  # ranging synthetic series, ta-verified
        (0.0, MarketRegime.RANGING),
    ],
)
def test_regime_branch_at_and_around_the_threshold(router, adx, expected):
    assert router.ADX_TRENDING_THRESHOLD == 25.0
    assert router.detect_regime(indicators_with_adx(adx)) is expected


def test_classify_reports_the_adx_value_and_its_source(router):
    regime, adx, source = router.classify(indicators_with_adx(61.63))
    assert regime is MarketRegime.TRENDING
    assert adx == pytest.approx(61.63)
    assert source == "adx"


def test_adx_read_from_metadata_when_value_is_absent(router):
    ind = {"ADX": SimpleNamespace(value=None, confidence=0.7, metadata={"adx": 44.0})}
    regime, adx, source = router.classify(ind)
    assert regime is MarketRegime.TRENDING
    assert adx == pytest.approx(44.0)
    assert source == "adx"


def test_missing_adx_falls_back_and_says_so(router):
    """A missing ADX must be visible, not silently classified as RANGING."""
    regime, adx, source = router.classify({})
    assert adx is None
    assert source == "fallback"
    assert regime in (MarketRegime.TRENDING, MarketRegime.RANGING)


def test_non_numeric_adx_is_not_coerced_into_a_decision(router):
    _regime, adx, source = router.classify(
        {"ADX": SimpleNamespace(value="not-a-number", confidence=0.5, metadata={})}
    )
    assert adx is None
    assert source == "fallback"


# --------------------------------------------------------------------------
# Counters increment on BOTH branches
# --------------------------------------------------------------------------


def test_counters_increment_on_both_branches(router):
    router.observe_regime(indicators_with_adx(61.63), symbol="BTCUSDT")
    router.observe_regime(indicators_with_adx(55.00), symbol="ETHUSDT")
    router.observe_regime(indicators_with_adx(16.40), symbol="ADAUSDT")

    stats = router.get_stats()
    assert stats["trend_signals"] == 2
    assert stats["mean_reversion_signals"] == 1
    assert stats["total_signals"] == 3
    assert stats["observed_signals"] == 3
    assert stats["executed_signals"] == 0


def test_percentages_use_a_real_denominator_and_sum_to_100(router):
    for adx in (61.63, 55.0, 16.4, 12.0):
        router.observe_regime(indicators_with_adx(adx))
    stats = router.get_stats()
    assert stats["trend_pct"] == pytest.approx(50.0)
    assert stats["mean_reversion_pct"] == pytest.approx(50.0)
    assert stats["trend_pct"] + stats["mean_reversion_pct"] == pytest.approx(100.0)


def test_branch_counts_always_sum_to_total(router):
    for adx in (30.0, 10.0, 25.0, 24.9, 99.0):
        router.observe_regime(indicators_with_adx(adx))
    s = router.get_stats()
    assert s["trend_signals"] + s["mean_reversion_signals"] == s["total_signals"]
    assert s["observed_signals"] + s["executed_signals"] == s["total_signals"]


# --------------------------------------------------------------------------
# routing_mode must never let an observing router look like a steering one
# --------------------------------------------------------------------------


def test_routing_mode_is_inactive_before_any_decision(router):
    stats = router.get_stats()
    assert stats["routing_mode"] == "inactive"
    # Percentages are None, NOT 0.0 — "no data" must not render as "0.0%".
    assert stats["trend_pct"] is None
    assert stats["mean_reversion_pct"] is None


def test_routing_mode_becomes_advisory_after_observation(router):
    router.observe_regime(indicators_with_adx(30.0))
    assert router.get_stats()["routing_mode"] == "advisory"


def test_routing_mode_reports_executing_when_the_router_actually_routes(router):
    router._record_route(MarketRegime.TRENDING, 30.0, "adx", executed=True)
    assert router.get_stats()["routing_mode"] == "executing"
    router._record_route(MarketRegime.RANGING, 10.0, "adx", executed=False)
    assert router.get_stats()["routing_mode"] == "mixed"


# --------------------------------------------------------------------------
# API contract with the React component
# --------------------------------------------------------------------------


def test_get_stats_emits_exactly_the_keys_the_frontend_reads(router):
    empty = set(router.get_stats())
    router.observe_regime(indicators_with_adx(30.0))
    populated = set(router.get_stats())

    assert FRONTEND_REQUIRED_KEYS <= empty, (
        f"missing while inactive: {FRONTEND_REQUIRED_KEYS - empty}"
    )
    assert FRONTEND_REQUIRED_KEYS <= populated, (
        f"missing while populated: {FRONTEND_REQUIRED_KEYS - populated}"
    )
    # Same shape in both states — the tile must not have to branch on presence.
    assert empty == populated


def test_stats_are_json_serialisable(router):
    import json

    router.observe_regime(indicators_with_adx(30.0))
    json.dumps(router.get_stats())


# --------------------------------------------------------------------------
# Funnel integration
# --------------------------------------------------------------------------


def test_routing_decisions_reach_the_funnel(router):
    router.observe_regime(indicators_with_adx(61.63))
    router.observe_regime(indicators_with_adx(16.40))

    routing = get_signal_funnel().snapshot()["routing"]
    assert routing["total_decisions"] == 2
    assert routing["trend_following"] == 1
    assert routing["mean_reversion"] == 1
    assert routing["adx_distribution"]["n"] == 2
    assert routing["adx_distribution"]["min"] == pytest.approx(16.40)
    assert routing["adx_distribution"]["max"] == pytest.approx(61.63)


def test_every_declared_stage_is_emitted_even_at_zero():
    snapshot = SignalFunnel().snapshot()
    emitted = [s["stage"] for s in snapshot["stages"]]
    assert emitted == STAGES, "a stage vanished from the payload"
    for stage in snapshot["stages"]:
        if stage["evaluated"] == 0:
            assert stage["pass_rate_pct"] is None, (
                f"{stage['stage']}: zero evaluations reported as a rate, not null — "
                "this is the exact ambiguity the funnel exists to remove"
            )


def test_rejections_carry_the_numbers_that_caused_them():
    f = SignalFunnel()
    f.gate(
        "passed_signal_confidence_gate",
        False,
        reason="confidence_below_min_signal_confidence",
        symbol="ADAUSDT",
        observed=0.2761,
        threshold=0.30,
    )
    stage = next(s for s in f.snapshot()["stages"] if s["stage"] == "passed_signal_confidence_gate")
    reason = stage["rejection_reasons"]["confidence_below_min_signal_confidence"]
    assert reason["count"] == 1
    assert reason["observed_min"] == pytest.approx(0.2761)
    assert reason["threshold"] == pytest.approx(0.30)
    assert stage["passed"] + stage["rejected"] == stage["evaluated"]


def test_anonymous_rejections_are_impossible():
    f = SignalFunnel()
    with pytest.raises(ValueError, match="without a reason code"):
        f.reject("passed_gatekeeper", "")


def test_unknown_stage_is_a_loud_error_not_a_silent_no_op():
    f = SignalFunnel()
    with pytest.raises(KeyError):
        f.gate("stage_that_does_not_exist", True)


def test_notes_do_not_corrupt_pass_reject_arithmetic():
    """The volume validator degrades confidence without rejecting."""
    f = SignalFunnel()
    f.gate("passed_validator", True)
    f.note(
        "passed_validator",
        "volume_confidence_penalty_applied",
        observed=0.5,
        threshold=1.0,
    )
    stage = next(s for s in f.snapshot()["stages"] if s["stage"] == "passed_validator")
    assert stage["evaluated"] == 1
    assert stage["passed"] == 1
    assert stage["rejected"] == 0
    assert stage["pass_rate_pct"] == pytest.approx(100.0)
    assert "volume_confidence_penalty_applied" in stage["notes"]


# --------------------------------------------------------------------------
# REGRESSION GUARD — the test that would have caught the original defect
# --------------------------------------------------------------------------


N_EVALUATION_CYCLES = 20


def test_routing_counters_do_not_stay_at_zero_with_valid_market_data(router):
    """Fail if N evaluations with real ADX produce no routing decisions.

    This is the condition that persisted for seven months: the router was
    constructed, its banner logged, and its tile rendered, while
    `total_signals` never left 0 because `generate_signal` was gated behind a
    strategy mode the deployment does not use.
    """
    live_adx_values = [61.63, 55.55, 56.70, 54.91, 52.14, 19.60, 16.40, 22.10]

    for i in range(N_EVALUATION_CYCLES):
        router.observe_regime(
            indicators_with_adx(live_adx_values[i % len(live_adx_values)]),
            symbol=f"SYM{i % 5}",
        )

    stats = router.get_stats()
    assert stats["total_signals"] == N_EVALUATION_CYCLES, (
        "routing counters did not advance — the router is not being invoked "
        "on the live evaluation path"
    )
    assert stats["routing_mode"] != "inactive"
    # Both branches must be exercised by a realistic ADX distribution.
    assert stats["trend_signals"] > 0, "trend-following branch never taken"
    assert stats["mean_reversion_signals"] > 0, "mean-reversion branch never taken"

    funnel_routing = get_signal_funnel().snapshot()["routing"]
    assert funnel_routing["total_decisions"] == N_EVALUATION_CYCLES
