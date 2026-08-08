"""
Stage 0: one mapping from the producers' reason strings to ExitKind.

Today TWO predicates read one string and they disagree:
  auto_trader.py:2883  -> "stop" or "loss"                (limit vs market close)
  auto_trader.py:3073  -> "stop" or "loss" or "max_hold"  (SL cooldown)

Producers (position_manager.py:731-776, auto_trader.py:2583-2595):
  "Stop loss triggered"   "Trailing stop triggered"   -> both match :2883
  "Take profit triggered" "TP3 - Full exit"           -> neither matches
  "MAX_HOLD_TIME_EXCEEDED (49.0h > 48h)"              -> matches :3073 only
"""

import pytest

from app.models.enums import ExitKind


@pytest.fixture
def mapper():
    from app.auto_trader import AutoTrader

    return AutoTrader._exit_kind_for


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("Stop loss triggered", ExitKind.HARD_STOP),
        ("stop_loss", ExitKind.HARD_STOP),
        ("stop_loss (limit order @ $97.90)", ExitKind.HARD_STOP),
        ("Trailing stop triggered", ExitKind.TRAILING_STOP),
        ("Take profit triggered", ExitKind.TAKE_PROFIT),
        ("TP3 - Full exit", ExitKind.TAKE_PROFIT),
        ("MAX_HOLD_TIME_EXCEEDED (49.0h > 48h)", ExitKind.MAX_HOLD),
        ("manual", ExitKind.MANUAL),
    ],
)
def test_every_live_producer_string_maps(mapper, reason, expected):
    assert mapper(reason) == expected


def test_trailing_is_not_swallowed_by_the_hard_stop_predicate(mapper):
    """'Trailing stop triggered' contains 'stop'. Order of tests matters."""
    assert mapper("Trailing stop triggered") == ExitKind.TRAILING_STOP


def test_non_exit_diagnostics_do_not_map(mapper):
    """check_all_exit_conditions returns these for NON-exits (:752, :755, :776).
    An ExitKind cannot model them and must not invent one."""
    for reason in ("Position not found", "Position not open", "No exit conditions met"):
        assert mapper(reason) is None


def test_unknown_reason_maps_to_none_not_a_guess(mapper):
    assert mapper("something nobody has written yet") is None
