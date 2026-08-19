"""
Final review (2026-08-08): no ensemble position may exit at a level derived
from ``default_stop_loss_pct``.

Task 8 gave the ensemble path its own stop and target but touched only
``stop_loss`` / ``take_profit``. ``create_position`` had already auto-derived
TP1/TP2/TP3 from ``|entry - stop|`` at INSERT time (position_manager.py:252),
and the stop known at INSERT time on that path is the risk-manager default —
so every ensemble position arrived carrying a ladder of +-1.6% / +-2.6% /
+-4.0% off entry. ``check_all_exit_conditions`` tests partial exits at step 3,
BEFORE the legacy take-profit at step 4, and a TP3 hit returns a FULL close
that ``_exit_kind_for`` stamps ``TAKE_PROFIT``. The exit-attribution table this
programme exists to build would therefore have recorded "ensemble target hit"
for an exit that hit a stale default.

The fix clears the ladder outright rather than re-deriving it from the
ensemble's own stop: re-deriving keeps the property below true, but a TP3 at 2R
still force-closes ahead of the ensemble's target whenever that target sits
further out than 2R. The ensemble emits exactly one stop and one target.

These tests assert the *behaviour*, not just that three fields are None: the
position must produce NO exit at any level the stale ladder would have fired
at, and must close at the ensemble's own target.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.enums import PositionSide

ENTRY = Decimal("72.68")

# The ensemble's own (ATR-derived) levels. The target deliberately sits FURTHER
# out than 2R from the ensemble stop, which is the case that discriminates
# between clearing the ladder and re-deriving it:
#   R                = 72.68 - 69.05 = 3.63
#   2R (old TP3 rule)= 72.68 + 7.26  = 79.94
#   ensemble target  =                 87.20   <- further out than 2R
ENS_STOP_LONG = Decimal("69.05")
ENS_TARGET_LONG = Decimal("87.20")


def _mock_repo():
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.update_stops = AsyncMock()
    repo.update_price = AsyncMock()
    repo.close = AsyncMock()
    return repo


@pytest.fixture
def manager():
    """PositionManager with stubbed repos but the REAL RiskManager.

    The default ladder under test is a function of ``default_stop_loss_pct``,
    so the risk manager must not be mocked away — otherwise the test asserts
    against numbers it invented itself.
    """
    from app.position_manager import PositionManager

    with (
        patch(
            "app.position_manager.get_position_repository", return_value=_mock_repo()
        ),
        patch(
            "app.position_manager.get_portfolio_repository", return_value=MagicMock()
        ),
    ):
        return PositionManager()


def _default_stop(manager, entry: Decimal, side: PositionSide) -> Decimal:
    return manager.risk_manager.calculate_stop_loss(entry, side)


def test_create_position_really_does_build_a_default_derived_ladder(manager):
    """The defect this file guards against — proven, not assumed."""
    pos = manager.create_position(
        symbol="SOLUSDT",
        side=PositionSide.LONG,
        entry_price=ENTRY,
        quantity=Decimal("0.3"),
    )

    default_sl = _default_stop(manager, ENTRY, PositionSide.LONG)
    risk = ENTRY - default_sl

    assert pos.stop_loss == default_sl
    assert pos.take_profit_1 == ENTRY + risk * Decimal("0.8")
    assert pos.take_profit_3 == ENTRY + risk * Decimal("2.0")
    # 2.0 x a 2% stop distance is +4% off entry: the stale full-exit level.
    assert float(pos.take_profit_3) == pytest.approx(float(ENTRY) * 1.04, rel=1e-9)


def test_long_ensemble_position_never_exits_at_a_default_derived_level(manager):
    pos = manager.create_position(
        symbol="SOLUSDT",
        side=PositionSide.LONG,
        entry_price=ENTRY,
        quantity=Decimal("0.3"),
    )
    stale_tp1 = pos.take_profit_1
    stale_tp3 = pos.take_profit_3

    manager.set_position_stops(
        position_id=pos.id,
        stop_loss=ENS_STOP_LONG,
        take_profit=ENS_TARGET_LONG,
        enable_trailing=False,
        clear_partial_levels=True,
    )

    assert pos.take_profit_1 is None
    assert pos.take_profit_2 is None
    assert pos.take_profit_3 is None

    # Every level the stale ladder would have fired at must now do nothing.
    for price in (stale_tp1, stale_tp3, ENTRY * Decimal("1.04")):
        should_exit, reason, info = manager.check_all_exit_conditions(pos.id, price)
        assert should_exit is False, f"exited at {price} — reason {reason!r}"
        assert info is None
        assert reason == "No exit conditions met"

    # 2R off the ENSEMBLE stop — the level a re-derived ladder would have
    # force-closed at, ahead of the ensemble's own target.
    two_r = ENTRY + (ENTRY - ENS_STOP_LONG) * Decimal("2.0")
    assert two_r < ENS_TARGET_LONG
    should_exit, reason, _ = manager.check_all_exit_conditions(pos.id, two_r)
    assert should_exit is False, f"force-closed at 2R ({two_r}) — reason {reason!r}"

    # The ensemble's own target is the only thing that closes it in profit.
    should_exit, reason, info = manager.check_all_exit_conditions(
        pos.id, ENS_TARGET_LONG
    )
    assert should_exit is True
    assert reason == "Take profit triggered"
    assert info is None

    # ...and its own stop is the only thing that closes it at a loss.
    should_exit, reason, _ = manager.check_all_exit_conditions(pos.id, ENS_STOP_LONG)
    assert should_exit is True
    assert reason == "Stop loss triggered"


def test_short_ensemble_position_never_exits_at_a_default_derived_level(manager):
    entry = Decimal("602.69")
    ens_stop = Decimal("631.00")  # above entry for a SHORT
    ens_target = Decimal("520.00")  # further out than 2R (= 546.07)

    pos = manager.create_position(
        symbol="BNBUSDT",
        side=PositionSide.SHORT,
        entry_price=entry,
        quantity=Decimal("0.05"),
    )
    stale_tp1 = pos.take_profit_1
    stale_tp3 = pos.take_profit_3
    # Derived from the SHORT default stop, not from a literal: SHORT falls back
    # to short_stop_loss_pct (2026-08-12), so a hardcoded 2R-off-2% level here
    # would only be re-asserting the LONG distance.
    default_sl = _default_stop(manager, entry, PositionSide.SHORT)
    assert stale_tp3 == entry - (default_sl - entry) * Decimal("2.0")

    manager.set_position_stops(
        position_id=pos.id,
        stop_loss=ens_stop,
        take_profit=ens_target,
        enable_trailing=False,
        clear_partial_levels=True,
    )

    assert (pos.take_profit_1, pos.take_profit_2, pos.take_profit_3) == (
        None,
        None,
        None,
    )

    for price in (stale_tp1, stale_tp3):
        should_exit, reason, _ = manager.check_all_exit_conditions(pos.id, price)
        assert should_exit is False, f"exited at {price} — reason {reason!r}"

    two_r = entry - (ens_stop - entry) * Decimal("2.0")
    assert two_r > ens_target
    should_exit, reason, _ = manager.check_all_exit_conditions(pos.id, two_r)
    assert should_exit is False, f"force-closed at 2R ({two_r}) — reason {reason!r}"

    should_exit, reason, _ = manager.check_all_exit_conditions(pos.id, ens_target)
    assert should_exit is True
    assert reason == "Take profit triggered"


def test_clearing_is_opt_in_so_the_atr_path_keeps_its_ladder(manager):
    """auto_trader.py:2383 passes tp1/tp2/tp3 deliberately — do not break it."""
    pos = manager.create_position(
        symbol="SOLUSDT",
        side=PositionSide.LONG,
        entry_price=ENTRY,
        quantity=Decimal("0.3"),
    )

    manager.set_position_stops(
        position_id=pos.id,
        stop_loss=ENS_STOP_LONG,
        take_profit=ENS_TARGET_LONG,
        tp1=Decimal("75.00"),
        tp2=Decimal("78.00"),
        tp3=Decimal("81.00"),
    )

    assert pos.take_profit_1 == Decimal("75.00")
    assert pos.take_profit_3 == Decimal("81.00")

    # The ladder is walked in order, so a price past all three still reports
    # TP1 first — that it fires at all is the point: this path keeps scaling
    # out, the ensemble path no longer does.
    should_exit, reason, info = manager.check_all_exit_conditions(
        pos.id, Decimal("81.50")
    )
    assert should_exit is False
    assert reason == "TP1 - Partial exit"
    assert info is not None and info["level"] == "TP1"


def test_passing_none_cannot_clear_the_ladder(manager):
    """Why clear_partial_levels exists at all: the tpN sets are truthy-gated."""
    pos = manager.create_position(
        symbol="SOLUSDT",
        side=PositionSide.LONG,
        entry_price=ENTRY,
        quantity=Decimal("0.3"),
    )
    stale_tp3 = pos.take_profit_3

    manager.set_position_stops(
        position_id=pos.id,
        stop_loss=ENS_STOP_LONG,
        take_profit=ENS_TARGET_LONG,
        tp1=None,
        tp2=None,
        tp3=None,
    )

    assert pos.take_profit_3 == stale_tp3
