"""SHORT positions must fall back to ``short_stop_loss_pct``, not the LONG default.

``short_stop_loss_pct`` (config.py, added 2026-01-19) declared a tighter 1.5%
stop for SHORT and no code ever read it: ``calculate_stop_loss`` fell back to
``default_stop_loss_pct`` for both sides, so every SHORT opened by
``position_manager.open_position`` (which passes ``side`` and no explicit stop)
sat at the 2.0% LONG distance. Audit finding 6, 2026-08-12.

The ladder in ``position_manager`` derives TP1/TP2/TP3 from |entry - stop|, so
the stop distance is also the R multiple for every SHORT partial exit.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from app.config import Settings
from app.models import PositionSide
from app.risk_manager import RiskManager


@pytest.fixture
def risk_manager():
    """RiskManager on the real config defaults (conftest pins env_file=None)."""
    with patch("app.risk_manager.get_settings", return_value=Settings()):
        return RiskManager()


def test_short_stop_uses_short_stop_loss_pct(risk_manager):
    """SHORT with stop_loss_pct=None → short_stop_loss_pct above entry."""
    entry = Decimal("50000.00")
    settings = risk_manager.settings

    stop_loss = risk_manager.calculate_stop_loss(entry, PositionSide.SHORT)

    expected = entry * (Decimal("1") + Decimal(str(settings.short_stop_loss_pct / 100)))
    assert stop_loss == expected
    # Guard against the field being edited to match the LONG default, which
    # would make this test pass while the side-aware branch is gone.
    assert settings.short_stop_loss_pct < settings.default_stop_loss_pct
    assert stop_loss < entry * (
        Decimal("1") + Decimal(str(settings.default_stop_loss_pct / 100))
    )


def test_long_stop_still_uses_default_stop_loss_pct(risk_manager):
    """LONG fallback is unchanged — default_stop_loss_pct below entry."""
    entry = Decimal("50000.00")
    settings = risk_manager.settings

    stop_loss = risk_manager.calculate_stop_loss(entry, PositionSide.LONG)

    expected = entry * (
        Decimal("1") - Decimal(str(settings.default_stop_loss_pct / 100))
    )
    assert stop_loss == expected


def test_explicit_stop_pct_overrides_side_default(risk_manager):
    """A caller-supplied stop distance wins for SHORT — no side lookup."""
    entry = Decimal("50000.00")

    stop_loss = risk_manager.calculate_stop_loss(
        entry, PositionSide.SHORT, stop_loss_pct=5.0
    )

    assert stop_loss == entry * Decimal("1.05")
