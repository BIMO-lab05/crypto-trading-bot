"""
Boot-time position hydration must fail loud.

Regression target (2026-08-12): load_positions_from_db wrapped the whole
rebuild in `except Exception: return 0`, PositionRepository.get_open_positions
swallowed every query error and returned [], and the init_data phase logged
"Continuing without database persistence". One unreachable DB or one malformed
row and the engine booted believing the book was empty: nothing monitored,
nothing stopped, and paper cash reconstructed against zero open positions.

A book we cannot read is a book we do not trade — hydration failure aborts boot.
The dashboard read path stays lenient: a display endpoint may degrade to an
empty list, the trading path may not.
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# Pre-import so the deferred `from app.main import database_health` inside
# init_data finds the module already in sys.modules — importing it lazily
# during a test re-runs prometheus Counter registration and trips
# "Duplicated timeseries in CollectorRegistry".
import app.main  # noqa: F401
from app.position_manager import PositionHydrationError, PositionManager
from app.repositories import PositionRepository


@pytest.fixture
def failing_position_repo():
    """Position repository whose open-position query is down."""
    repo = MagicMock()
    repo.get_open_positions = AsyncMock(
        side_effect=RuntimeError("connection refused: could not connect to server")
    )
    return repo


@pytest.fixture
def manager_on_failing_repo(failing_position_repo):
    """PositionManager wired to the failing repository."""
    with (
        patch("app.position_manager.get_risk_manager", return_value=MagicMock()),
        patch(
            "app.position_manager.get_position_repository",
            return_value=failing_position_repo,
        ),
        patch(
            "app.position_manager.get_portfolio_repository", return_value=MagicMock()
        ),
    ):
        return PositionManager()


class TestHydrationRaises:
    """load_positions_from_db must raise, never report zero."""

    async def test_db_error_raises_and_does_not_return_zero(
        self, manager_on_failing_repo
    ):
        with pytest.raises(PositionHydrationError) as excinfo:
            await manager_on_failing_repo.load_positions_from_db()

        # The original failure stays attached so the boot log names the cause.
        assert isinstance(excinfo.value.__cause__, RuntimeError)
        assert "connection refused" in str(excinfo.value.__cause__)
        assert manager_on_failing_repo.positions == {}

    async def test_malformed_row_raises(self, failing_position_repo):
        """A row missing a mapped column must abort, not truncate the book.

        SimpleNamespace has no MagicMock fallback attribute, so this is the
        pre-migration-008 row shape that previously vanished into `return 0`.
        """
        malformed = SimpleNamespace(
            position_id=uuid4(),
            symbol="SOLUSDT",
            side="LONG",
            entry_price=Decimal("72.68"),
            quantity=Decimal("0.30"),
        )
        failing_position_repo.get_open_positions = AsyncMock(return_value=[malformed])

        with (
            patch("app.position_manager.get_risk_manager", return_value=MagicMock()),
            patch(
                "app.position_manager.get_position_repository",
                return_value=failing_position_repo,
            ),
            patch(
                "app.position_manager.get_portfolio_repository",
                return_value=MagicMock(),
            ),
        ):
            manager = PositionManager()

        with pytest.raises(PositionHydrationError):
            await manager.load_positions_from_db()


class TestInitDataAbortsBoot:
    """The data lifespan phase must not swallow a hydration failure."""

    async def test_hydration_failure_propagates_out_of_init_data(self, monkeypatch):
        from app.lifespan import data as data_mod

        fake_db = MagicMock()
        fake_db.init_async_engine = MagicMock()
        fake_db.health_check = MagicMock(return_value=True)
        fake_db.close = AsyncMock()
        monkeypatch.setattr(data_mod, "db_manager", fake_db)

        portfolio_repo = MagicMock()
        portfolio_repo.get_or_create = AsyncMock()
        monkeypatch.setattr(
            data_mod, "get_portfolio_repository", lambda: portfolio_repo
        )

        position_manager = MagicMock()
        position_manager.load_positions_from_db = AsyncMock(
            side_effect=PositionHydrationError("open-position query failed")
        )
        monkeypatch.setattr(data_mod, "get_position_manager", lambda: position_manager)

        with pytest.raises(PositionHydrationError):
            async with data_mod.init_data():
                pytest.fail("init_data yielded despite an unverified position book")

    async def test_portfolio_load_stays_lenient(self, monkeypatch):
        """Non-critical init failures keep the pre-existing leniency."""
        from app.lifespan import data as data_mod

        fake_db = MagicMock()
        fake_db.init_async_engine = MagicMock()
        fake_db.health_check = MagicMock(return_value=True)
        fake_db.close = AsyncMock()
        monkeypatch.setattr(data_mod, "db_manager", fake_db)

        portfolio_repo = MagicMock()
        portfolio_repo.get_or_create = AsyncMock(side_effect=RuntimeError("no table"))
        monkeypatch.setattr(
            data_mod, "get_portfolio_repository", lambda: portfolio_repo
        )

        entered = False
        async with data_mod.init_data():
            entered = True
        assert entered


class TestDashboardReadStaysLenient:
    """The trade-history display path degrades to an empty list."""

    async def test_repository_lenient_read_returns_empty(self):
        repo = PositionRepository()
        repo.db = MagicMock()
        repo.db.get_async_session = MagicMock(side_effect=RuntimeError("db down"))

        assert await repo.get_open_positions_or_empty("paper_trading") == []

    async def test_trade_history_endpoint_returns_empty_on_db_error(self):
        from app.handlers import performance_dashboard

        repo = PositionRepository()
        repo.db = MagicMock()
        repo.db.get_async_session = MagicMock(side_effect=RuntimeError("db down"))

        with patch.object(
            performance_dashboard, "get_position_repository", return_value=repo
        ):
            response = await performance_dashboard.get_trade_history_endpoint(
                limit=100, offset=0, status="OPEN"
            )

        assert response.success is True
        assert response.trades == []
        assert response.total_count == 0
