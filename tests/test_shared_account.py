"""Tests for `shared/account.py`, the declaration of record for capital.

The regression this file exists to prevent is the unit bug (audit finding F2):
an earlier draft compared `MAX_RISK_PER_TRADE` (a FRACTION, 0.10) against
`MAX_DAILY_LOSS` (a PERCENT, 5.0) with `>`, so `0.10 > 5.0` was False and the
single most consequential finding in the capital audit — that one max-size trade
can blow through the daily circuit breaker — would have silently never fired.
`test_risk_cap_conflict_warning_fires_at_defaults` is the guard against that.
"""

from __future__ import annotations

import importlib
import warnings
from decimal import Decimal

import pytest

import shared.account as account


@pytest.fixture(autouse=True)
def _restore_module_state():
    """Reload `shared.account` after any test that mutates env + reloads it.

    Module constants are resolved at import time, so an env-override test has to
    reload the module. Without this teardown the mutated values would leak into
    every subsequent test in the same pytest session.
    """
    yield
    importlib.reload(account)


# ---------------------------------------------------------------------------
# Declared defaults
# ---------------------------------------------------------------------------


def test_declared_defaults_match_the_real_env_keys_and_units():
    """DEFAULTS is env-independent and mirrors trading-engine config.py."""
    assert account.DEFAULTS["PAPER_INITIAL_BALANCE"] == 10000.0  # USD -- ADR-029
    assert account.DEFAULTS["MAX_RISK_PER_TRADE"] == 0.10  # fraction
    assert account.DEFAULTS["MAX_DAILY_LOSS_PCT"] == 12.0  # percent -- ADR-028
    assert account.DEFAULTS["MAX_POSITION_SIZE_PCT"] == 10.0  # percent
    assert account.DEFAULTS["MIN_NOTIONAL_USD"] == 5.0  # USD
    assert account.DEFAULTS["TAKER_FEE_PER_SIDE"] == 0.00055  # fraction


def test_constants_resolve_to_the_declared_defaults_with_no_env_set(monkeypatch):
    for key in account.DEFAULTS:
        monkeypatch.delenv(key, raising=False)
    reloaded = importlib.reload(account)

    assert reloaded.PAPER_INITIAL_BALANCE == 10000.0
    assert reloaded.MAX_RISK_PER_TRADE == 0.10
    assert reloaded.MAX_DAILY_LOSS_PCT == 12.0  # ADR-028
    assert reloaded.MAX_POSITION_SIZE_PCT == 10.0


def test_account_equity_alias_is_the_same_value_not_a_second_knob():
    assert account.ACCOUNT_EQUITY_USD == account.PAPER_INITIAL_BALANCE


def test_live_cap_is_two_percent_and_has_no_env_key(monkeypatch):
    """CLAUDE.md: the 2% LIVE per-trade cap is non-negotiable."""
    monkeypatch.setenv("LIVE_MAX_RISK_PER_TRADE", "0.99")
    reloaded = importlib.reload(account)
    assert reloaded.LIVE_MAX_RISK_PER_TRADE == 0.02


# ---------------------------------------------------------------------------
# Env override
# ---------------------------------------------------------------------------


def test_env_override_is_honoured(monkeypatch):
    monkeypatch.setenv("PAPER_INITIAL_BALANCE", "250.0")
    monkeypatch.setenv("MAX_DAILY_LOSS_PCT", "7.5")
    reloaded = importlib.reload(account)

    assert reloaded.PAPER_INITIAL_BALANCE == 250.0
    assert reloaded.MAX_DAILY_LOSS_PCT == 7.5
    # DEFAULTS stays env-independent — this is what the sync test compares to.
    assert reloaded.DEFAULTS["PAPER_INITIAL_BALANCE"] == 10000.0


def test_non_numeric_env_value_is_loud(monkeypatch):
    monkeypatch.setenv("PAPER_INITIAL_BALANCE", "one hundred")
    with pytest.raises(ValueError, match="PAPER_INITIAL_BALANCE"):
        importlib.reload(account)


# ---------------------------------------------------------------------------
# Unit normalisation
# ---------------------------------------------------------------------------


def test_unit_conversion_helpers():
    assert account.max_daily_loss_fraction() == pytest.approx(0.12)  # ADR-028
    assert account.max_position_size_fraction() == pytest.approx(0.10)


def test_risk_budget_usd_at_defaults():
    assert account.risk_budget_usd() == Decimal("1000.00")


def test_risk_budget_usd_live_uses_the_two_percent_cap():
    assert account.risk_budget_usd(live=True) == Decimal("200.00")


def test_risk_budget_usd_accepts_an_explicit_equity():
    assert account.risk_budget_usd(250.0) == Decimal("25.00")


# ---------------------------------------------------------------------------
# Warnings and sanity assert
# ---------------------------------------------------------------------------


def test_no_risk_cap_conflict_at_defaults():
    """ADR-028 reconciled the caps: 10%/trade against a 12%/day breaker.

    Before ADR-028 the defaults were 10% vs 5%, so a single maximally-sized
    loser tripped the daily breaker and this warning fired at rest. It must now
    be silent — an always-on warning trains the operator to ignore the channel.
    """
    conflict = [p for p in account.capital_config_warnings() if p.startswith("RISK CAP CONFLICT")]
    assert not conflict, f"caps are reconciled per ADR-028, got {conflict}"


def test_risk_cap_conflict_warning_fires_when_caps_actually_conflict(monkeypatch):
    """THE F2 REGRESSION GUARD. Do not delete.

    `MAX_RISK_PER_TRADE` is a FRACTION (0.10) and `MAX_DAILY_LOSS_PCT` is a
    PERCENT (12.0). They must be normalised to a common unit before comparison.
    If somebody "simplifies" this back to
    `MAX_RISK_PER_TRADE > MAX_DAILY_LOSS_PCT` the comparison becomes
    `0.15 > 4.0` -> False, the warning goes silent, and this test goes red.

    Uses an explicitly conflicting config rather than the shipped defaults so
    the guard survives future risk-policy changes (it broke once already, when
    ADR-028 moved the default from 5.0 to 12.0).
    """
    monkeypatch.setenv("MAX_RISK_PER_TRADE", "0.15")  # fraction -> 15%
    monkeypatch.setenv("MAX_DAILY_LOSS_PCT", "4.0")  # percent  -> 4%
    reloaded = importlib.reload(account)

    conflict = [p for p in reloaded.capital_config_warnings() if p.startswith("RISK CAP CONFLICT")]
    assert len(conflict) == 1, f"expected exactly one conflict warning, got {conflict}"
    assert "15.0%" in conflict[0]
    assert "4.0%" in conflict[0]


def test_conflict_warning_clears_when_the_caps_are_reconciled(monkeypatch):
    """Proves the check is live in both directions, not a constant True."""
    monkeypatch.setenv("MAX_RISK_PER_TRADE", "0.02")
    reloaded = importlib.reload(account)
    assert not [p for p in reloaded.capital_config_warnings() if p.startswith("RISK CAP CONFLICT")]


def test_assert_capital_is_sane_does_not_raise_at_current_defaults():
    """Capital-config problems WARN. They must never be a boot blocker.

    A raise here would change trading behaviour by refusing to boot the engine.
    Post-ADR-028 the risk-cap conflict is resolved, so the surviving warning at
    defaults is FEE DRAG — which is a standing fact about Bybit's fee schedule,
    not a misconfiguration, and must not escalate either.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        account.assert_capital_is_sane()  # must not raise

    messages = [str(w.message) for w in caught]
    assert not any("RISK CAP CONFLICT" in m for m in messages), (
        f"caps are reconciled per ADR-028; got {messages}"
    )
    # The warning channel must still be wired — proven by the FEE DRAG notice.
    assert any("FEE DRAG" in m for m in messages), f"expected FEE DRAG, got {messages}"


def test_assert_capital_is_sane_still_warns_on_a_real_conflict(monkeypatch):
    """A genuinely conflicting config must warn — and still not raise."""
    monkeypatch.setenv("MAX_RISK_PER_TRADE", "0.15")
    monkeypatch.setenv("MAX_DAILY_LOSS_PCT", "4.0")
    reloaded = importlib.reload(account)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        reloaded.assert_capital_is_sane()  # must not raise

    assert any("RISK CAP CONFLICT" in str(w.message) for w in caught)


@pytest.mark.parametrize(
    "key,bad_value",
    [
        ("PAPER_INITIAL_BALANCE", "50.0"),  # config.py ge=100.0
        ("MAX_RISK_PER_TRADE", "0.9"),  # config.py le=0.5 (fraction)
        ("MAX_DAILY_LOSS_PCT", "0.10"),  # config.py ge=1.0 (percent!)
        ("MAX_POSITION_SIZE_PCT", "99.0"),  # config.py le=50.0 (percent)
    ],
)
def test_assert_capital_is_sane_raises_outside_config_py_bounds(monkeypatch, key, bad_value):
    monkeypatch.setenv(key, bad_value)
    reloaded = importlib.reload(account)
    with pytest.raises(ValueError, match=key):
        reloaded.assert_capital_is_sane()
