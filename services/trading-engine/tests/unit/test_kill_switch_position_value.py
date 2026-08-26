"""B1 proof: the `max_position_value` kill-switch arm is live, and correctly sized.

BEHAVIOUR CHANGE. `kill_switch.py` used to declare `max_position_value = 100000.0`
and `auto_trader.py` only ever overrode `max_daily_loss_pct`, so on the real
account no position could reach the threshold and this arm was PERMANENTLY DEAD.
It is now derived from equity (equity x max_total_exposure_pct, e.g. 80%).

`should_halt_trading()` gates every entry (`auto_trader.py:908`, `:1700`) and the
auto-trader is armed via the operator's `.env`, so a wrong threshold silently
stops the bot. The two-sided assertion below — a normal max-size trade does NOT
trip, a runaway DOES — is the required proof, and both halves live in this file
deliberately so neither can be deleted without the other becoming conspicuous.

Sizing chain that fixes the "normal" figure (`auto_trader.py`):
    cap_value      = balance x settings.max_risk_per_trade
    position_value = min(sized_notional, cap_value)                <= cap_value
    min-notional gate REJECTS undersized trades, it never uprounds
    kill_switch.update_metrics(position_value=...)            (`:2102`)
The runaway threshold therefore sits (exposure_pct / risk_fraction) times above
any legitimate single position — 8x at the default 80% / 0.10 knobs.

All dollar figures are DERIVED from the declared config (ADR-029) — no bare
account-size literals — so this proof survives future re-scales.
"""

import pytest

from app.config import get_settings
from app.trading_enhancements import kill_switch as kill_switch_module
from app.trading_enhancements.kill_switch import (
    KillSwitch,
    KillSwitchConfig,
    KillSwitchReason,
    get_kill_switch,
)

_SETTINGS = get_settings()

#: The declared paper equity — routed through Settings, never a literal.
EQUITY_USD = float(_SETTINGS.paper_initial_balance)

#: Equity x max_risk_per_trade (fraction). The largest notional the per-trade
#: cap gate will ever hand to the kill switch on the declared account.
NORMAL_MAX_SIZE_TRADE_USD = EQUITY_USD * float(_SETTINGS.max_risk_per_trade)

#: Equity x max_total_exposure_pct (percent). One position consuming the
#: account's entire exposure budget is definitionally a runaway.
DERIVED_THRESHOLD_USD = EQUITY_USD * (float(_SETTINGS.max_total_exposure_pct) / 100.0)

#: A single position at 100% of equity. Unambiguously a runaway.
RUNAWAY_POSITION_USD = EQUITY_USD


@pytest.fixture(autouse=True)
def _reset_singleton():
    """`get_kill_switch()` caches on `_kill_switch is None`; without this reset
    the second test in the module would silently inherit the first's instance
    (and its already-activated state)."""
    kill_switch_module._kill_switch = None
    yield
    kill_switch_module._kill_switch = None


def _switch() -> KillSwitch:
    """A kill switch on the declared account with an EXPLICIT threshold.

    The threshold is passed rather than inherited from ambient settings so the
    B1 proof does not depend on whatever the operator currently has in `.env`.
    `test_default_is_derived_not_hardcoded` separately pins the default itself.
    """
    ks = KillSwitch(KillSwitchConfig(max_position_value=DERIVED_THRESHOLD_USD))
    ks.initialize_balance(EQUITY_USD)
    return ks


# ---------------------------------------------------------------------------
# The two-sided proof
# ---------------------------------------------------------------------------


def test_normal_max_size_trade_does_not_trip():
    """A per-trade-cap-sized trade is the LARGEST permitted. It must not halt."""
    ks = _switch()
    triggered = ks.update_metrics(
        current_balance=EQUITY_USD, position_value=NORMAL_MAX_SIZE_TRADE_USD
    )
    assert "max_position_value" not in triggered, (
        "the normal max-size trade tripped the runaway arm — this threshold "
        "would silently halt the bot on ordinary trading"
    )
    assert not ks.should_halt_trading()


def test_runaway_position_trips():
    """A single position worth the entire account must halt trading."""
    ks = _switch()
    triggered = ks.update_metrics(current_balance=EQUITY_USD, position_value=RUNAWAY_POSITION_USD)
    assert "max_position_value" in triggered, (
        "a position worth the entire account did not trip the arm — it is still "
        "inert, which is the exact defect this change exists to fix"
    )
    assert ks.should_halt_trading()
    assert ks.state.activation_reason is KillSwitchReason.MAX_POSITION_VALUE


def test_threshold_boundary_is_inclusive_at_the_derived_value():
    """`kill_switch.py` checks `>=`. Pin the boundary so a later `>` is caught."""
    ks = _switch()
    assert "max_position_value" in ks.update_metrics(
        current_balance=EQUITY_USD, position_value=DERIVED_THRESHOLD_USD
    )

    kill_switch_module._kill_switch = None
    ks2 = _switch()
    assert "max_position_value" not in ks2.update_metrics(
        current_balance=EQUITY_USD, position_value=DERIVED_THRESHOLD_USD - 0.01
    )


# ---------------------------------------------------------------------------
# The default itself
# ---------------------------------------------------------------------------


def test_default_is_derived_not_hardcoded():
    """`KillSwitchConfig()` with no arguments must carry the derived threshold.

    This is the half that `auto_trader.py`'s explicit argument cannot cover:
    `KillSwitch.__init__` does `config or KillSwitchConfig()`, and other test
    modules construct `KillSwitchConfig()` bare.
    """
    default = KillSwitchConfig().max_position_value
    assert default != 100000.0, "the inert $100,000 default is back"
    assert default == pytest.approx(DERIVED_THRESHOLD_USD), (
        f"expected the declared account's exposure ceiling "
        f"(paper_initial_balance x max_total_exposure_pct), got {default}. If "
        "paper_initial_balance or max_total_exposure_pct changed deliberately, "
        "this derivation should have followed automatically — check the "
        "kill_switch fallbacks against config.py."
    )
    assert default > NORMAL_MAX_SIZE_TRADE_USD, (
        "the threshold must sit above a normal max-size trade or it halts the "
        "bot on ordinary trading"
    )


def test_helper_derivation_matches_the_documented_formula():
    assert kill_switch_module._default_max_position_value() == pytest.approx(
        kill_switch_module._FALLBACK_PAPER_BALANCE_USD
        * (kill_switch_module._FALLBACK_TOTAL_EXPOSURE_PCT / 100.0)
    )


def test_fallback_mirrors_the_declared_config():
    """The in-container fallback constant is a sanctioned literal mirror of
    `paper_initial_balance` — assert it tracks the declared config so a future
    re-scale cannot silently split the two channels."""
    assert kill_switch_module._FALLBACK_PAPER_BALANCE_USD == pytest.approx(EQUITY_USD)
    assert kill_switch_module._FALLBACK_TOTAL_EXPOSURE_PCT == pytest.approx(
        float(_SETTINGS.max_total_exposure_pct)
    )


def test_get_kill_switch_singleton_carries_the_derived_default():
    """The one production caller (`auto_trader.py`) goes through this factory."""
    ks = get_kill_switch()
    assert ks.config.max_position_value == pytest.approx(DERIVED_THRESHOLD_USD)
    assert get_kill_switch() is ks, "factory must keep caching on first build"
