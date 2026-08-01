"""
Regression tests for audit DL-2 / T-8.

DL-2: a restart used to rebuild cash as `initial_balance - open_position_cost`,
discarding every realized P&L and every commission paid on a closed leg. Across
the 2026-07-31 14:26 restart -- with zero trades in between -- that invented
$2.78 out of nothing and re-armed the kill switch against the fabricated figure.

T-8: `opened_at` was not restored from the database, so every position got a
fresh 48h max-hold window on each restart.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.models import PositionSide, PositionStatus
from app.position_manager import _as_utc


LEVERAGE = Decimal("10")
COMMISSION_PCT = Decimal("0.001")  # 0.1%


def _position(entry_price, quantity, opened_at):
    """Minimal stand-in for an in-memory Position."""
    return SimpleNamespace(
        entry_price=Decimal(str(entry_price)),
        quantity=Decimal(str(quantity)),
        remaining_quantity=None,
        opened_at=opened_at,
        side=PositionSide.LONG,
        status=PositionStatus.OPEN,
    )


def _engine(open_positions, portfolio):
    """A PaperTradingEngine with its collaborators stubbed out."""
    from app.paper_trading import PaperTradingEngine

    engine = PaperTradingEngine.__new__(PaperTradingEngine)
    engine.settings = SimpleNamespace(default_leverage=float(LEVERAGE))
    engine.commission_pct = COMMISSION_PCT
    engine.initial_balance = Decimal("100")
    engine.balance = Decimal("100")
    engine.position_manager = Mock()
    engine.position_manager.get_open_positions.return_value = open_positions
    engine.portfolio_repo = Mock()
    engine.portfolio_repo.get_or_create = AsyncMock(return_value=portfolio)
    return engine


class TestRestartBalanceRestore:
    @pytest.mark.asyncio
    async def test_restores_persisted_ledger_not_initial_balance(self):
        """
        The reproduction of DL-2. A position opened *before* the last persisted
        write is already reflected in cash_balance, so nothing extra is owed and
        the restored balance must equal the stored ledger exactly.

        The old code returned initial_balance - cost. Here that is
        100 - (50/10 + 50*0.001) = 100 - 5.05 = 94.95 -- $14.25 of cash
        invented out of nothing, because the realized losses baked into the
        persisted 80.70 ledger were simply discarded.
        """
        opened = datetime(2026, 7, 29, 20, 0, tzinfo=timezone.utc)
        last_write = datetime(2026, 7, 30, 20, 12, tzinfo=timezone.utc)

        engine = _engine(
            open_positions=[_position("50000", "0.001", opened)],
            portfolio=SimpleNamespace(
                cash_balance=Decimal("80.70266802"), updated_at=last_write
            ),
        )

        await engine.sync_balance_with_positions()

        assert engine.balance == Decimal("80.70266802")
        # Pin the exact number the old par-based reconstruction produced, so a
        # regression to it fails here rather than passing on a near-miss.
        old_formula = engine.initial_balance - Decimal("5.05")
        assert old_formula == Decimal("94.95")
        assert engine.balance != old_formula

    @pytest.mark.asyncio
    async def test_deducts_only_positions_opened_after_last_write(self):
        """
        cash_balance is written only on close, so a position opened after that
        write has had its margin debited in memory but never persisted. Exactly
        that position's cost -- and no other -- must come off the stored figure.
        """
        last_write = datetime(2026, 7, 30, 20, 12, tzinfo=timezone.utc)
        old = _position("50000", "0.001", last_write - timedelta(hours=5))
        new = _position("2000", "0.05", last_write + timedelta(hours=1))

        engine = _engine(
            open_positions=[old, new],
            portfolio=SimpleNamespace(
                cash_balance=Decimal("80"), updated_at=last_write
            ),
        )

        await engine.sync_balance_with_positions()

        # new position: notional 100 -> margin 10, commission 0.1
        assert engine.balance == Decimal("80") - Decimal("10.1")

    @pytest.mark.asyncio
    async def test_falls_back_loudly_when_portfolio_unreadable(self, caplog):
        """
        If the ledger cannot be read we still have to boot, but the fallback
        fabricates cash -- it must never be silent.
        """
        engine = _engine(open_positions=[], portfolio=None)
        engine.portfolio_repo.get_or_create = AsyncMock(
            side_effect=RuntimeError("db down")
        )

        with caplog.at_level("ERROR"):
            await engine.sync_balance_with_positions()

        assert engine.balance == Decimal("100")
        assert any("Falling back" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_naive_db_timestamp_does_not_raise(self):
        """
        `positions.opened_at` and `portfolios.updated_at` are `timestamp without
        time zone`, so SQLAlchemy yields naive datetimes. Comparing those with
        aware ones raises TypeError -- the reason _as_utc exists.
        """
        engine = _engine(
            open_positions=[_position("50000", "0.001", datetime(2026, 7, 29, 20, 0))],
            portfolio=SimpleNamespace(
                cash_balance=Decimal("80"), updated_at=datetime(2026, 7, 30, 20, 12)
            ),
        )

        await engine.sync_balance_with_positions()

        assert engine.balance == Decimal("80")


class TestAsUtc:
    def test_attaches_utc_to_naive(self):
        assert _as_utc(datetime(2026, 7, 29, 20, 0)) == datetime(
            2026, 7, 29, 20, 0, tzinfo=timezone.utc
        )

    def test_preserves_aware(self):
        aware = datetime(2026, 7, 29, 20, 0, tzinfo=timezone.utc)
        assert _as_utc(aware) == aware

    def test_passes_none_through(self):
        assert _as_utc(None) is None


class TestModuleLevelImportsSurvive:
    """
    The repo's autoflake hook has stripped a needed import three times during
    this work. Each time the failure surfaced only at runtime -- once as a
    NameError inside the very balance-restore path these tests cover, which
    silently degraded it to the fabricating fallback in production.

    Grepping for the symbol is not enough: the usage matches even when the
    import is gone. These execute the resolution instead.
    """

    def test_repositories_can_resolve_its_config_default(self):
        import app.repositories as repositories

        # Fails with NameError if `from app.config import get_settings` was
        # stripped -- exactly the production failure of 2026-08-01.
        assert Decimal(str(repositories.get_settings().paper_initial_balance)) > 0

    def test_performance_tracker_can_resolve_its_config_default(self):
        from app.performance_tracker import _default_initial_balance

        assert _default_initial_balance() > 0

    def test_kill_switch_can_resolve_utc_date(self):
        from app.trading_enhancements import kill_switch

        # Fails if `timezone` was stripped from the datetime import.
        assert kill_switch.datetime.now(kill_switch.timezone.utc) is not None
