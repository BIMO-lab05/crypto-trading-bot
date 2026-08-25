"""
Exposure must be measured on REMAINING quantity, not original.

A position that scaled out via TP1/TP2 occupies only what is left. Counting
its full entry notional overstates exposure and rejects new entries early.
auto_trader._passes_exposure_gate was already fixed this way; before this
change the two gates disagree after any partial exit, and both run on the
paper entry path.
"""

import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))
from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402

BALANCE = Decimal(str(ACCOUNT_EQUITY_USD))

# Entry price chosen so quantity 0.1 puts 90% of the account in one position
# (breaches the 80% exposure cap) at ANY declared balance — the old literal
# "900" encoded 90% of the $100-era account and stopped breaching at $10,000.
ENTRY_PRICE_90PCT = str(BALANCE * Decimal("9"))


def _position(entry_price: str, quantity: str, remaining: str | None = None):
    p = MagicMock()
    p.entry_price = Decimal(entry_price)
    p.quantity = Decimal(quantity)
    p.remaining_quantity = Decimal(remaining) if remaining is not None else None
    p.status = Mock(value="OPEN")
    return p


@pytest.fixture
def risk_manager():
    from app.risk_manager import RiskManager

    settings = Mock()
    settings.max_total_exposure_pct = 80.0
    # The ALLOW path of check_position_limits does not return at the exposure
    # branch - it falls through to should_halt_trading() (risk_manager.py:269),
    # which evaluates
    #   Decimal(str(settings.paper_initial_balance))
    #     * Decimal(str(settings.max_daily_loss_pct / 100))
    # at risk_manager.py:87-89. A bare Mock raises InvalidOperation there, so
    # these two lines are what make the post-fix green state reachable at all.
    # 12.0 is the ADR-028 daily-loss breaker; daily_pnl is Decimal("0") so the
    # branch clears. max_open_positions is NOT read by check_position_limits.
    settings.paper_initial_balance = float(ACCOUNT_EQUITY_USD)
    settings.max_daily_loss_pct = 12.0
    with patch("app.risk_manager.get_settings", return_value=settings):
        yield RiskManager()


def test_scaled_out_position_frees_its_exposure(risk_manager):
    """Original notional breaches the cap; remaining does not."""
    # 90% of the account originally = above the 80% cap.
    # After a 2/3 scale-out only 30% is still open.
    position = _position(ENTRY_PRICE_90PCT, "0.1", remaining="0.0333333")

    allowed, reason = risk_manager.check_position_limits(
        current_positions=[position], account_balance=BALANCE
    )

    assert allowed is True, (
        f"a two-thirds scaled-out position still occupied its full entry notional: {reason}"
    )


def test_unscaled_position_still_breaches(risk_manager):
    """The gate must still bite when nothing has been scaled out."""
    position = _position(ENTRY_PRICE_90PCT, "0.1", remaining="0.1")

    allowed, reason = risk_manager.check_position_limits(
        current_positions=[position], account_balance=BALANCE
    )

    assert allowed is False
    assert "Total exposure" in reason


def test_missing_remaining_quantity_falls_back_to_original(risk_manager):
    """DB-hydrated rows can bypass __init__; None must mean 'use quantity'."""
    position = _position(ENTRY_PRICE_90PCT, "0.1", remaining=None)

    allowed, reason = risk_manager.check_position_limits(
        current_positions=[position], account_balance=BALANCE
    )

    assert allowed is False, "None remaining_quantity must fall back to quantity"
