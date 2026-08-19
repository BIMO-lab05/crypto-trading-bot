"""
Unit Tests for Database Repositories
Tests CRUD operations for Position, Trade, and Portfolio repositories
"""

import pytest
from decimal import Decimal
from datetime import datetime, UTC
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import Mock, AsyncMock, patch, MagicMock

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "shared"))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.repositories import PositionRepository, TradeRepository, PortfolioRepository
from app.database.models import Position as DBPosition
from app.models import Position, PositionStatus, PositionSide


class TestPositionRepository:
    """Test suite for PositionRepository"""

    @pytest.fixture
    def position_repo(self):
        """Create PositionRepository instance"""
        return PositionRepository()

    @pytest.fixture
    def sample_position(self):
        """Create a sample Position model"""
        return Position(
            id=uuid4(),
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000.00"),
            current_price=Decimal("50000.00"),
            unrealized_pnl=Decimal("0.00"),
            stop_loss=Decimal("49000.00"),
            take_profit=Decimal("52000.00"),
            status=PositionStatus.OPEN,
            strategy="test_strategy",
            opened_at=datetime.now(UTC),  # Fixed: was entry_time
        )

    @pytest.mark.asyncio
    async def test_create_position_success(self, position_repo, sample_position):
        """Test creating a position in database"""
        # Mock database session
        with patch.object(position_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_async_session

            # Execute
            result = await position_repo.create(sample_position)

            # Verify
            assert result == sample_position.id
            mock_async_session.add.assert_called_once()
            mock_async_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_position_failure(self, position_repo, sample_position):
        """Test create position handling database errors"""
        with patch.object(position_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            mock_async_session.commit.side_effect = Exception("DB Error")
            mock_session.return_value.__aenter__.return_value = mock_async_session

            # Execute and verify exception is raised
            with pytest.raises(Exception) as exc_info:
                await position_repo.create(sample_position)

            assert "DB Error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_price_success(self, position_repo):
        """Test updating position price"""
        position_id = uuid4()
        new_price = Decimal("51000.00")
        new_pnl = Decimal("100.00")

        with patch.object(position_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_async_session

            # Execute
            await position_repo.update_price(position_id, new_price, new_pnl)

            # Verify
            mock_async_session.execute.assert_called_once()
            mock_async_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_position_success(self, position_repo):
        """Test closing a position"""
        position_id = uuid4()
        exit_price = Decimal("52000.00")
        realized_pnl = Decimal("200.00")
        exit_reason = "Take Profit Hit"

        with patch.object(position_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_async_session

            # Execute
            await position_repo.close(
                position_id, exit_price, realized_pnl, exit_reason
            )

            # Verify
            mock_async_session.execute.assert_called_once()
            mock_async_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_success(self, position_repo):
        """Test retrieving position by ID"""
        position_id = uuid4()

        with patch.object(position_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            # mock_result should be a regular Mock, not AsyncMock, since scalar_one_or_none() is not async
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = MagicMock(
                position_id=position_id, symbol="BTCUSDT", quantity=Decimal("0.1")
            )
            # execute() is async, so we set return_value for the awaited result
            mock_async_session.execute.return_value = mock_result
            mock_session.return_value.__aenter__.return_value = mock_async_session

            # Execute
            result = await position_repo.get_by_id(position_id)

            # Verify
            assert result is not None
            assert result.position_id == position_id

    @pytest.mark.asyncio
    async def test_get_open_positions_success(self, position_repo):
        """Test retrieving all open positions"""
        with patch.object(position_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            # mock_result should be a regular Mock since scalars() is not async
            mock_result = Mock()
            mock_scalars = Mock()
            mock_scalars.all.return_value = [
                MagicMock(symbol="BTCUSDT", quantity=Decimal("0.1")),
                MagicMock(symbol="ETHUSDT", quantity=Decimal("1.0")),
            ]
            mock_result.scalars.return_value = mock_scalars
            mock_async_session.execute.return_value = mock_result
            mock_session.return_value.__aenter__.return_value = mock_async_session

            # Execute
            result = await position_repo.get_open_positions("paper_trading")

            # Verify
            assert len(result) == 2
            assert result[0].symbol == "BTCUSDT"
            assert result[1].symbol == "ETHUSDT"


class TestClosedPnLStats:
    """Realized-P&L aggregate over closed positions.

    Backed by a real (in-memory) table rather than a mocked session: the
    defect guarded here is a row LIMIT inside the query, which a mocked
    session cannot see.
    """

    @pytest.fixture
    def position_repo(self):
        return PositionRepository()

    @pytest.fixture
    async def sqlite_sessions(self):
        """async_sessionmaker over an in-memory positions table"""
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(DBPosition.__table__.create)
        yield async_sessionmaker(engine, expire_on_commit=False)
        await engine.dispose()

    @staticmethod
    def _closed(realized_pnl, portfolio_id="paper_trading", status="CLOSED"):
        return DBPosition(
            position_id=uuid4(),
            portfolio_id=portfolio_id,
            symbol="BTCUSDT",
            side="LONG",
            quantity=Decimal("0.001"),
            entry_price=Decimal("50000"),
            cost_basis=Decimal("50"),
            realized_pnl=realized_pnl,
            status=status,
            closed_at=datetime.now(UTC),
        )

    @pytest.mark.asyncio
    async def test_aggregates_every_closed_row_past_the_query_limit(
        self, position_repo, sqlite_sessions
    ):
        """1200 closed rows: the row-by-row handler truncated at 1000."""
        rows = [self._closed(Decimal("0.10")) for _ in range(1200)]
        rows += [self._closed(Decimal("-0.40")) for _ in range(5)]
        rows.append(self._closed(None))  # never closed with a P&L write
        rows.append(self._closed(Decimal("0")))  # scratch
        rows.append(self._closed(Decimal("99"), status="OPEN"))
        rows.append(self._closed(Decimal("99"), portfolio_id="other"))

        async with sqlite_sessions() as session:
            session.add_all(rows)
            await session.commit()

        with patch.object(position_repo.db, "get_async_session", sqlite_sessions):
            stats = await position_repo.get_closed_pnl_stats("paper_trading")

        # Denominator is every CLOSED row, including the NULL and the scratch —
        # that is what the old len(positions) counted.
        assert stats.total_trades == 1207
        assert stats.winning_trades == 1200
        assert stats.losing_trades == 5
        assert stats.realized_pnl == Decimal("118.00")
        assert stats.gross_profit == Decimal("120.00")
        assert stats.gross_loss == Decimal("-2.00")
        assert isinstance(stats.realized_pnl, Decimal)

    @pytest.mark.asyncio
    async def test_flat_book_coalesces_to_zero(self, position_repo, sqlite_sessions):
        """No closed positions: zeros, not None"""
        with patch.object(position_repo.db, "get_async_session", sqlite_sessions):
            stats = await position_repo.get_closed_pnl_stats("paper_trading")

        assert stats.total_trades == 0
        assert stats.winning_trades == 0
        assert stats.losing_trades == 0
        assert stats.realized_pnl == Decimal("0")
        assert stats.gross_profit == Decimal("0")
        assert stats.gross_loss == Decimal("0")


class TestTradeRepository:
    """Test suite for TradeRepository"""

    @pytest.fixture
    def trade_repo(self):
        """Create TradeRepository instance"""
        return TradeRepository()

    @pytest.mark.asyncio
    async def test_log_trade_success(self, trade_repo):
        """Test logging a trade to database via raw SQL execute."""
        with patch.object(trade_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_async_session

            await trade_repo.log_trade(
                portfolio_id="paper_trading",
                symbol="BTCUSDT",
                side="BUY",
                quantity=Decimal("0.1"),
                price=Decimal("50000.00"),
                commission=Decimal("5.00"),
                position_id=uuid4(),
                order_type="MARKET",
            )

            mock_async_session.execute.assert_called_once()
            mock_async_session.commit.assert_called_once()
            params = mock_async_session.execute.call_args[0][1]
            assert params["side"] == "BUY"
            assert params["symbol"] == "BTCUSDT"
            assert params["fee"] == Decimal("5.00")

    @pytest.mark.asyncio
    async def test_log_trade_with_pnl(self, trade_repo):
        """Test logging a SELL close trade with realized PnL persisted."""
        with patch.object(trade_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_async_session

            await trade_repo.log_trade(
                portfolio_id="paper_trading",
                symbol="BTCUSDT",
                side="SELL",
                quantity=Decimal("0.1"),
                price=Decimal("52000.00"),
                commission=Decimal("5.20"),
                realized_pnl=Decimal("194.80"),
                strategy="ensemble",
            )

            mock_async_session.execute.assert_called_once()
            params = mock_async_session.execute.call_args[0][1]
            assert params["side"] == "SELL"
            assert params["realized_pnl"] == Decimal("194.80")
            assert params["strategy"] == "ensemble"

    @pytest.mark.asyncio
    async def test_log_trade_failure(self, trade_repo):
        """Errors must be swallowed — execution path must not break on DB failure."""
        with patch.object(trade_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            mock_async_session.commit.side_effect = Exception("DB Error")
            mock_session.return_value.__aenter__.return_value = mock_async_session

            await trade_repo.log_trade(
                portfolio_id="paper_trading",
                symbol="BTCUSDT",
                side="BUY",
                quantity=Decimal("0.1"),
                price=Decimal("50000.00"),
                commission=Decimal("5.00"),
            )
            # No exception raised → test passes.


class TestPortfolioRepository:
    """Test suite for PortfolioRepository"""

    @pytest.fixture
    def portfolio_repo(self):
        """Create PortfolioRepository instance"""
        return PortfolioRepository()

    @pytest.mark.asyncio
    async def test_get_or_create_new_portfolio(self, portfolio_repo):
        """Test creating a new portfolio"""
        with patch.object(portfolio_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            # mock_result should be regular Mock since scalar_one_or_none() is not async
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = (
                None  # Portfolio doesn't exist
            )
            mock_async_session.execute.return_value = mock_result
            mock_session.return_value.__aenter__.return_value = mock_async_session

            # Execute
            result = await portfolio_repo.get_or_create(
                portfolio_id="new_portfolio",
                name="New Portfolio",
                initial_balance=Decimal("100.00"),
            )

            # Verify - can't check result directly since it's from the method, but can verify calls
            mock_async_session.add.assert_called_once()
            mock_async_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_or_create_seeds_risk_columns_from_settings(self, portfolio_repo):
        """RES-04: a new PAPER row carries ADR-010/ADR-028 values.

        Settings are deliberately NON-DEFAULT (0.07 / 9.0). The real defaults
        0.10 / 12.0 are close enough that a missing or wrong transform could
        pass by luck; 9.0 PERCENT -> Decimal("0.09") FRACTION is the assertion
        that actually pins the divide-by-100.
        """
        fake_settings = SimpleNamespace(
            paper_initial_balance=100.0,
            max_risk_per_trade=0.07,
            max_daily_loss_pct=9.0,
        )

        with (
            patch.object(portfolio_repo.db, "get_async_session") as mock_session,
            patch("app.repositories.get_settings", return_value=fake_settings),
        ):
            mock_async_session = AsyncMock()
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = None
            mock_async_session.execute.return_value = mock_result
            mock_session.return_value.__aenter__.return_value = mock_async_session

            await portfolio_repo.get_or_create(portfolio_id="paper_trading")

            mock_async_session.add.assert_called_once()
            created = mock_async_session.add.call_args[0][0]

            # Assert on VALUES, not on the call: with mocks there is no DB to
            # reject an out-of-range write, so a percent leaking into the
            # DECIMAL(5,4) fraction column would pass silently here and only
            # surface as a numeric overflow against the real schema.
            assert created.risk_per_trade == Decimal("0.07")
            assert created.max_daily_loss == Decimal("0.09")
            assert created.trading_mode == "PAPER"

    @pytest.mark.asyncio
    async def test_get_or_create_existing_portfolio(self, portfolio_repo):
        """Test retrieving existing portfolio"""
        existing_portfolio = MagicMock(
            portfolio_id="existing",
            name="Existing Portfolio",
            cash_balance=Decimal("100.00"),
        )

        with patch.object(portfolio_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            # mock_result should be regular Mock since scalar_one_or_none() is not async
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = existing_portfolio
            mock_async_session.execute.return_value = mock_result
            mock_session.return_value.__aenter__.return_value = mock_async_session

            # Execute
            result = await portfolio_repo.get_or_create(
                portfolio_id="existing",
                name="Existing Portfolio",
                initial_balance=Decimal("100.00"),
            )

            # Verify
            assert result == existing_portfolio
            # Should NOT add or commit since it already exists
            mock_async_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_balance(self, portfolio_repo):
        """Test updating portfolio balance"""
        with patch.object(portfolio_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_async_session

            # Execute - Fixed parameters to match actual signature
            await portfolio_repo.update_balance(
                portfolio_id="test_portfolio",
                cash_balance=Decimal("120.00"),
                realized_pnl=Decimal("30.00"),
            )

            # Verify
            mock_async_session.execute.assert_called_once()
            mock_async_session.commit.assert_called_once()

    @staticmethod
    def _updated_columns(stmt) -> set:
        """Column names carried by an UPDATE statement's SET clause.

        Asserting on key PRESENCE rather than generated SQL text: the exact
        rendering of a scalar subquery is a SQLAlchemy implementation detail,
        the set of maintained columns is the contract.
        """
        return {col.name for col in stmt._values.keys()}

    @pytest.mark.asyncio
    async def test_record_position_close_maintains_display_columns(
        self, portfolio_repo
    ):
        """RES-03: the display trio moves in the SAME UPDATE as cash_balance.

        Split across two statements they could disagree; that is exactly how
        total_value / total_pnl / unrealized_pnl drifted from cash for months.
        """
        with patch.object(portfolio_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            mock_result = Mock()
            mock_result.rowcount = 1
            mock_async_session.execute.return_value = mock_result
            mock_session.return_value.__aenter__.return_value = mock_async_session

            await portfolio_repo.record_position_close(
                portfolio_id="paper_trading",
                cash_balance=Decimal("100.00"),
                realized_pnl_delta=Decimal("1.50"),
            )

            mock_async_session.execute.assert_called_once()
            stmt = mock_async_session.execute.call_args[0][0]
            assert {
                "cash_balance",
                "realized_pnl",
                "unrealized_pnl",
                "total_value",
                "total_pnl",
            } <= self._updated_columns(stmt)

    @pytest.mark.asyncio
    async def test_update_balance_preserves_realized_pnl_overwrite_semantics(
        self, portfolio_repo
    ):
        """RES-03 guard: the aggregates are maintained WITHOUT realized_pnl
        becoming an unconditional write.

        update_balance OVERWRITES realized_pnl when the param is supplied, so
        writing the key on calls that omit it would clobber the accumulated
        ledger with a stale value on every partial exit and scale-in.
        """
        aggregates = {"cash_balance", "unrealized_pnl", "total_value", "total_pnl"}

        # Param omitted -> realized_pnl must NOT be in the SET clause
        with patch.object(portfolio_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_async_session

            await portfolio_repo.update_balance(
                portfolio_id="test_portfolio",
                cash_balance=Decimal("120.00"),
            )

            stmt = mock_async_session.execute.call_args[0][0]
            columns = self._updated_columns(stmt)
            assert aggregates <= columns
            assert "realized_pnl" not in columns

        # Param supplied -> realized_pnl IS written (overwrite semantics)
        with patch.object(portfolio_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_async_session

            await portfolio_repo.update_balance(
                portfolio_id="test_portfolio",
                cash_balance=Decimal("120.00"),
                realized_pnl=Decimal("30.00"),
            )

            stmt = mock_async_session.execute.call_args[0][0]
            columns = self._updated_columns(stmt)
            assert aggregates <= columns
            assert "realized_pnl" in columns

    # Note: get_performance_metrics() method doesn't exist in PortfolioRepository
    # Removed test_get_performance_metrics as it tested a non-existent method


class TestRepositoryExceptionHandling:
    """Test exception handling in repository methods"""

    @pytest.fixture
    def position_repo(self):
        """Create PositionRepository instance"""
        return PositionRepository()

    @pytest.mark.asyncio
    async def test_position_update_price_exception(self, position_repo):
        """Test update_price with database exception"""
        with patch.object(position_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            mock_async_session.execute.side_effect = Exception("Database error")
            mock_session.return_value.__aenter__.return_value = mock_async_session

            with pytest.raises(Exception, match="Database error"):
                await position_repo.update_price(
                    uuid4(), Decimal("50000.00"), Decimal("100.00")
                )

    @pytest.mark.asyncio
    async def test_position_close_exception(self, position_repo):
        """Test close with database exception"""
        with patch.object(position_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            mock_async_session.execute.side_effect = Exception("Close failed")
            mock_session.return_value.__aenter__.return_value = mock_async_session

            with pytest.raises(Exception, match="Close failed"):
                await position_repo.close(
                    uuid4(), Decimal("50000.00"), Decimal("100.00")
                )

    @pytest.mark.asyncio
    async def test_position_get_by_id_exception(self, position_repo):
        """Test get_by_id with database exception"""
        with patch.object(position_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            mock_async_session.execute.side_effect = Exception("Get failed")
            mock_session.return_value.__aenter__.return_value = mock_async_session

            result = await position_repo.get_by_id(uuid4())
            assert result is None

    @pytest.mark.asyncio
    async def test_position_get_open_positions_exception(self, position_repo):
        """get_open_positions must raise: it feeds startup hydration, where an
        empty list is indistinguishable from a flat book (2026-08-12)."""
        with patch.object(position_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            mock_async_session.execute.side_effect = Exception("Query failed")
            mock_session.return_value.__aenter__.return_value = mock_async_session

            with pytest.raises(Exception, match="Query failed"):
                await position_repo.get_open_positions()

    @pytest.mark.asyncio
    async def test_position_get_open_positions_or_empty_exception(self, position_repo):
        """The lenient display wrapper still degrades to []"""
        with patch.object(position_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            mock_async_session.execute.side_effect = Exception("Query failed")
            mock_session.return_value.__aenter__.return_value = mock_async_session

            result = await position_repo.get_open_positions_or_empty()
            assert result == []

    @pytest.mark.asyncio
    async def test_position_get_closed_pnl_stats_exception(self, position_repo):
        """get_closed_pnl_stats must raise: zeroed realized P&L is
        indistinguishable from a flat book to the portfolio-manager mirror."""
        with patch.object(position_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            mock_async_session.execute.side_effect = Exception("Query failed")
            mock_session.return_value.__aenter__.return_value = mock_async_session

            with pytest.raises(Exception, match="Query failed"):
                await position_repo.get_closed_pnl_stats()


class TestPortfolioRepositoryExceptionHandling:
    """Test exception handling in PortfolioRepository methods"""

    @pytest.fixture
    def portfolio_repo(self):
        """Create PortfolioRepository instance"""
        return PortfolioRepository()

    @pytest.mark.asyncio
    async def test_get_or_create_exception(self, portfolio_repo):
        """Test get_or_create with database exception"""
        with patch.object(portfolio_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            mock_async_session.execute.side_effect = Exception(
                "Database connection failed"
            )
            mock_session.return_value.__aenter__.return_value = mock_async_session

            with pytest.raises(Exception, match="Database connection failed"):
                await portfolio_repo.get_or_create(
                    portfolio_id="test", name="Test", initial_balance=Decimal("100.00")
                )

    @pytest.mark.asyncio
    async def test_update_balance_exception(self, portfolio_repo):
        """Test update_balance with database exception"""
        with patch.object(portfolio_repo.db, "get_async_session") as mock_session:
            mock_async_session = AsyncMock()
            mock_async_session.execute.side_effect = Exception("Update failed")
            mock_session.return_value.__aenter__.return_value = mock_async_session

            with pytest.raises(Exception, match="Update failed"):
                await portfolio_repo.update_balance(
                    portfolio_id="test",
                    cash_balance=Decimal("5000.00"),
                    realized_pnl=Decimal("500.00"),
                )


class TestRepositorySingletons:
    """Test repository singleton pattern"""

    def test_get_position_repository_singleton(self):
        """Test that get_position_repository returns same instance"""
        from app.repositories import (
            get_position_repository,
        )

        repo1 = get_position_repository()
        repo2 = get_position_repository()

        # Should return same instance
        assert repo1 is repo2

    def test_get_trade_repository_singleton(self):
        """Test that get_trade_repository returns same instance"""
        from app.repositories import get_trade_repository

        repo1 = get_trade_repository()
        repo2 = get_trade_repository()

        # Should return same instance
        assert repo1 is repo2

    def test_get_portfolio_repository_singleton(self):
        """Test that get_portfolio_repository returns same instance"""
        from app.repositories import get_portfolio_repository

        repo1 = get_portfolio_repository()
        repo2 = get_portfolio_repository()

        # Should return same instance
        assert repo1 is repo2


# Test configuration
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
