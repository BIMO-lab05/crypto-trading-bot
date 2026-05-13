"""
Tests for the trading-engine DynamicRiskBudget manager's daily_pnl_pct field.

Plan 06-02 Task 2: extend manager.get_current_budget()['utilization'] to
include `daily_pnl_pct` (signed; the manager owns the math — single source
of truth, no parallel calc on the api-gateway).

Truth from 06-RESEARCH.md (F-02):
- utilization dict has total_budget_usd, used_budget_usd, available_budget_usd,
  utilization_pct ONLY today. No daily_pnl_pct key.
- Formula: (manager._daily_pnl / manager._current_equity) * 100.0 when
  _current_equity > 0, else 0.0. SIGN PRESERVED.
- The kill-switch trip check at risk module line ~1157 uses abs(); UI cell
  needs the signed value (negative = losing, positive = winning).

This test set uses get_risk_budget_manager() + reset_risk_budget_manager()
to get a fresh manager per test.
"""

import pytest

from app.risk.dynamic_risk_budget import (
    get_risk_budget_manager,
    reset_risk_budget_manager,
)


@pytest.fixture(autouse=True)
def _fresh_manager():
    """Ensure each test starts with a fresh manager."""
    reset_risk_budget_manager()
    yield
    reset_risk_budget_manager()


def test_daily_pnl_pct_negative_sign_preserved():
    """Losing day: _daily_pnl=-3.2 on equity=100.0 → -3.2 (NOT abs()=3.2)."""
    manager = get_risk_budget_manager()
    manager._current_equity = 100.0
    manager._daily_pnl = -3.2

    state = manager.get_current_budget()
    assert "utilization" in state, "utilization sub-dict must exist"
    assert "daily_pnl_pct" in state["utilization"], (
        "daily_pnl_pct must be present under utilization"
    )
    assert state["utilization"]["daily_pnl_pct"] == pytest.approx(-3.2), (
        "negative P&L sign must be preserved (UI displays signed value)"
    )


def test_daily_pnl_pct_positive_passthrough():
    """Winning day: _daily_pnl=5.0 on equity=100.0 → 5.0."""
    manager = get_risk_budget_manager()
    manager._current_equity = 100.0
    manager._daily_pnl = 5.0

    state = manager.get_current_budget()
    assert state["utilization"]["daily_pnl_pct"] == pytest.approx(5.0)


def test_daily_pnl_pct_zero_equity_guard_no_divide_by_zero():
    """Degenerate equity=0.0 must yield 0.0, not raise ZeroDivisionError."""
    manager = get_risk_budget_manager()
    manager._current_equity = 0.0
    manager._daily_pnl = 1.5

    state = manager.get_current_budget()
    # The contract is "no ZeroDivisionError escapes" + return 0.0.
    assert state["utilization"]["daily_pnl_pct"] == pytest.approx(0.0)


def test_current_budget_response_pydantic_validates_with_new_key():
    """CurrentBudgetResponse model still validates with the new utilization key.
    utilization is Dict[str, Any], so a new key cannot break the schema."""
    from app.handlers.risk_budget import CurrentBudgetResponse
    from datetime import datetime, timezone

    manager = get_risk_budget_manager()
    manager._current_equity = 200.0
    manager._daily_pnl = -8.4
    state = manager.get_current_budget()

    # Build the response model — same way handlers/risk_budget.py
    # get_current_budget does at line 402.
    resp = CurrentBudgetResponse(
        success=True,
        budget=state["budget"],
        utilization=state["utilization"],
        emergency_mode=state["emergency_mode"],
        config=state["config"],
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    # Pydantic accepts the extra key inside utilization (Dict[str, Any]).
    assert resp.utilization["daily_pnl_pct"] == pytest.approx(-4.2)
