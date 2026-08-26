"""The funnel must answer where a candidate actually died, and count cycles.

Measured 2026-08-22/23 (.planning/evidence/hold-funnel-2026-08-22.md):

- `reject()` incremented `_terminal_stage` on EVERY rejection, so
  terminal_stage[X] was identically stages[X].rejected and the total ran about
  4.8x the population (5,735 across 1,195 evaluations + 3,600 aggregations).
  Nothing recorded where a candidate actually died -- the one question the
  field exists to answer. The aggregation legs are AND-ed with no
  short-circuit, so every one of them is evaluated on every pass.
- `start_cycle()` had zero call sites, so `cycles` was permanently 0 and no
  funnel count could be normalised to a per-cycle rate.
"""

import pytest

from app.monitoring.signal_funnel import SignalFunnel, STAGES


@pytest.fixture
def funnel():
    return SignalFunnel()


def _two_stages():
    """Two real stage names, so the test does not depend on a hardcoded one."""
    return STAGES[0], STAGES[1]


def test_non_terminal_rejections_are_excluded_from_attribution(funnel):
    a, b = _two_stages()
    funnel.gate(a, False, reason="leg_a_failed", symbol="SOLUSDT", terminal=False)
    funnel.gate(b, False, reason="leg_b_failed", symbol="SOLUSDT", terminal=False)

    snap = funnel.snapshot()
    assert sum(snap["terminal_stage"].values()) == 0, (
        "AND-ed legs that do not short-circuit must not claim to have "
        "terminated anything"
    )


def test_terminal_rejection_is_attributed(funnel):
    a, b = _two_stages()
    funnel.gate(a, False, reason="leg_failed", symbol="SOLUSDT", terminal=False)
    funnel.gate(b, False, reason="died_here", symbol="SOLUSDT")

    snap = funnel.snapshot()
    assert snap["terminal_stage"] == {b: 1}, snap["terminal_stage"]


def test_terminal_total_does_not_exceed_rejections(funnel):
    """The regression: terminal_stage summing above the population."""
    a, b = _two_stages()
    for _ in range(5):
        funnel.gate(a, False, reason="leg_failed", terminal=False)
        funnel.gate(b, False, reason="died_here")

    snap = funnel.snapshot()
    rejected = sum(s["rejected"] for s in snap["stages"])
    terminal = sum(snap["terminal_stage"].values())
    assert terminal == 5
    assert terminal < rejected, (
        f"terminal ({terminal}) must be a strict subset of rejections "
        f"({rejected}) once any non-terminal leg exists"
    )


def test_per_symbol_attribution_follows_the_terminal_flag(funnel):
    a, b = _two_stages()
    funnel.gate(a, False, reason="leg_failed", symbol="SOLUSDT", terminal=False)
    funnel.gate(b, False, reason="died_here", symbol="SOLUSDT")

    snap = funnel.snapshot()
    by_symbol = snap.get("terminal_stage_by_symbol", {})
    assert by_symbol.get("SOLUSDT") == {b: 1}, by_symbol


def test_passing_gates_are_unaffected_by_terminal(funnel):
    a, _ = _two_stages()
    assert funnel.gate(a, True, symbol="SOLUSDT", terminal=False) is True
    snap = funnel.snapshot()
    assert sum(snap["terminal_stage"].values()) == 0


def test_start_cycle_increments_cycles(funnel):
    assert funnel.snapshot()["cycles"] == 0
    funnel.start_cycle()
    funnel.start_cycle()
    assert funnel.snapshot()["cycles"] == 2


def test_start_cycle_is_called_by_the_trading_loop():
    """Guards the defect directly: the method existed with zero call sites."""
    import inspect

    from app.auto_trader import AutoTrader

    src = inspect.getsource(AutoTrader._trading_loop)
    assert "start_cycle()" in src, (
        "the autonomous loop must tick the funnel, or `cycles` stays 0 forever"
    )
