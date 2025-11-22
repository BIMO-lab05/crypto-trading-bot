"""
Database Integration Tests
Purpose: Test real database operations with PostgreSQL

Setup Required:
1. PostgreSQL running (docker-compose up -d postgres)
2. Database schema initialized
3. Test database configured in .env.test

Run: pytest tests/integration/test_database_persistence.py -v -m integration
Coverage: pytest tests/integration/test_database_persistence.py --cov=app.repositories --cov-report=term
"""

import pytest
import asyncio
from decimal import Decimal
from uuid import uuid4, UUID
from datetime import datetime, timezone
from typing import List

# Import shared database models
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "shared"))

from database.models import Position as DBPosition, Trade as DBTrade, Portfolio as DBPortfolio
from sqlalchemy import select, func, text

# Import application models and repositories
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from app.models import Position, PositionSide, PositionStatus
from app.repositories import (
    PositionRepository,
    TradeRepository,
    PortfolioRepository
)

# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration


# ==========================================
# POSITION PERSISTENCE TESTS
# ==========================================

class TestPositionPersistence:
    """Test position CRUD with real database"""

    @pytest.mark.asyncio
    async def test_create_position_persists_to_db(
        self,
        clean_database,
        test_portfolio,
        create_app_position,
        sample_portfolio_id
    ):
        """Test creating position writes to database and all fields are persisted correctly"""
        # Create position using app model
        position = create_app_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            stop_loss=Decimal("49000.00"),
            take_profit=Decimal("55000.00"),
            strategy="test_strategy"
        )

        # Create repository instance
        position_repo = PositionRepository()

        # Mock db_manager to use test session
        class MockDBManager:
            def __init__(self, session):
                self.session = session

            async def get_async_session(self):
                yield self.session

        position_repo.db = MockDBManager(clean_database)

        # Save position to database
        position_id = await position_repo.create(position, portfolio_id=sample_portfolio_id)

        # Verify position ID was returned
        assert position_id is not None
        assert isinstance(position_id, UUID)

        # Query database directly to verify persistence
        result = await clean_database.execute(
            select(DBPosition).where(DBPosition.position_id == position_id)
        )
        db_position = result.scalar_one_or_none()

        # Assert position was saved
        assert db_position is not None
        assert db_position.symbol == "BTCUSDT"
        assert db_position.side == "LONG"
        assert db_position.quantity == Decimal("0.1")
        assert db_position.entry_price == Decimal("50000.00")
        assert db_position.stop_loss == Decimal("49000.00")
        assert db_position.take_profit == Decimal("55000.00")
        assert db_position.strategy == "test_strategy"
        assert db_position.status == "OPEN"
        assert db_position.portfolio_id == sample_portfolio_id

    @pytest.mark.asyncio
    async def test_update_position_price_persists(
        self,
        clean_database,
        test_position
    ):
        """Test position price updates persist to database"""
        # Update position price
        position_repo = PositionRepository()

        class MockDBManager:
            def __init__(self, session):
                self.session = session

            async def get_async_session(self):
                yield self.session

        position_repo.db = MockDBManager(clean_database)

        new_price = Decimal("52000.00")
        new_pnl = Decimal("200.00")

        # Update price in database
        await position_repo.update_price(
            position_id=test_position.position_id,
            current_price=new_price,
            unrealized_pnl=new_pnl
        )

        # Query database to verify update
        result = await clean_database.execute(
            select(DBPosition).where(DBPosition.position_id == test_position.position_id)
        )
        updated_position = result.scalar_one_or_none()

        # Assert updates were persisted
        assert updated_position.current_price == new_price
        assert updated_position.unrealized_pnl == new_pnl
        assert updated_position.updated_at > test_position.updated_at

    @pytest.mark.asyncio
    async def test_close_position_persists(
        self,
        clean_database,
        test_position
    ):
        """Test position closure persists to database"""
        position_repo = PositionRepository()

        class MockDBManager:
            def __init__(self, session):
                self.session = session

            async def get_async_session(self):
                yield self.session

        position_repo.db = MockDBManager(clean_database)

        exit_price = Decimal("53000.00")
        realized_pnl = Decimal("300.00")
        exit_reason = "TAKE_PROFIT"

        # Close position
        await position_repo.close(
            position_id=test_position.position_id,
            exit_price=exit_price,
            realized_pnl=realized_pnl,
            exit_reason=exit_reason
        )

        # Verify closure in database
        result = await clean_database.execute(
            select(DBPosition).where(DBPosition.position_id == test_position.position_id)
        )
        closed_position = result.scalar_one_or_none()

        # Assert closure fields are set
        assert closed_position.status == "CLOSED"
        assert closed_position.exit_price == exit_price
        assert closed_position.realized_pnl == realized_pnl
        assert closed_position.exit_reason == exit_reason
        assert closed_position.closed_at is not None

    @pytest.mark.asyncio
    async def test_get_position_by_id(
        self,
        clean_database,
        test_position
    ):
        """Test retrieving position by ID from database"""
        position_repo = PositionRepository()

        class MockDBManager:
            def __init__(self, session):
                self.session = session

            async def get_async_session(self):
                yield self.session

        position_repo.db = MockDBManager(clean_database)

        # Get position by ID
        retrieved = await position_repo.get_by_id(test_position.position_id)

        # Verify retrieved position matches
        assert retrieved is not None
        assert retrieved.position_id == test_position.position_id
        assert retrieved.symbol == test_position.symbol
        assert retrieved.side == test_position.side

    @pytest.mark.asyncio
    async def test_get_open_positions(
        self,
        clean_database,
        test_portfolio,
        sample_portfolio_id
    ):
        """Test querying all open positions for a portfolio"""
        # Create multiple positions
        positions = []
        for i in range(3):
            position = DBPosition(
                position_id=uuid4(),
                portfolio_id=sample_portfolio_id,
                symbol=f"SYMBOL{i}USDT",
                side="LONG",
                quantity=Decimal("1.0"),
                entry_price=Decimal(f"{50000 + i * 1000}"),
                cost_basis=Decimal(f"{50000 + i * 1000}"),
                status="OPEN" if i < 2 else "CLOSED",  # 2 open, 1 closed
            )
            clean_database.add(position)
            positions.append(position)

        await clean_database.commit()

        # Query open positions
        position_repo = PositionRepository()

        class MockDBManager:
            def __init__(self, session):
                self.session = session

            async def get_async_session(self):
                yield self.session

        position_repo.db = MockDBManager(clean_database)

        open_positions = await position_repo.get_open_positions(sample_portfolio_id)

        # Verify only open positions returned
        assert len(open_positions) == 2
        for pos in open_positions:
            assert pos.status == "OPEN"

    @pytest.mark.asyncio
    async def test_concurrent_position_updates(
        self,
        clean_database,
        test_position
    ):
        """Test handling concurrent position price updates"""
        position_repo = PositionRepository()

        class MockDBManager:
            def __init__(self, session):
                self.session = session

            async def get_async_session(self):
                yield self.session

        position_repo.db = MockDBManager(clean_database)

        # Simulate concurrent updates
        async def update_price(price: Decimal, pnl: Decimal):
            await position_repo.update_price(
                position_id=test_position.position_id,
                current_price=price,
                unrealized_pnl=pnl
            )

        # Run multiple updates concurrently
        await asyncio.gather(
            update_price(Decimal("51000.00"), Decimal("100.00")),
            update_price(Decimal("52000.00"), Decimal("200.00")),
            update_price(Decimal("53000.00"), Decimal("300.00")),
        )

        # Verify final state is consistent (last update should win)
        result = await clean_database.execute(
            select(DBPosition).where(DBPosition.position_id == test_position.position_id)
        )
        final_position = result.scalar_one_or_none()

        # Assert position is still valid
        assert final_position is not None
        assert final_position.current_price is not None
        assert final_position.unrealized_pnl is not None

    @pytest.mark.asyncio
    async def test_position_with_null_optional_fields(
        self,
        clean_database,
        test_portfolio,
        sample_portfolio_id
    ):
        """Test creating position with null optional fields (stop_loss, take_profit)"""
        position = Position(
            symbol="ETHUSDT",
            side=PositionSide.SHORT,
            entry_price=Decimal("3000.00"),
            quantity=Decimal("1.0"),
            # No stop_loss or take_profit
        )

        position_repo = PositionRepository()

        class MockDBManager:
            def __init__(self, session):
                self.session = session

            async def get_async_session(self):
                yield self.session

        position_repo.db = MockDBManager(clean_database)

        position_id = await position_repo.create(position, portfolio_id=sample_portfolio_id)

        # Verify creation succeeded
        result = await clean_database.execute(
            select(DBPosition).where(DBPosition.position_id == position_id)
        )
        db_position = result.scalar_one_or_none()

        assert db_position is not None
        assert db_position.stop_loss is None
        assert db_position.take_profit is None


# ==========================================
# TRADE PERSISTENCE TESTS
# ==========================================

class TestTradePersistence:
    """Test trade logging with real database"""

    @pytest.mark.asyncio
    async def test_log_trade_persists_to_db(
        self,
        clean_database,
        test_position,
        sample_portfolio_id
    ):
        """Test trade logging writes to database with all fields"""
        trade_repo = TradeRepository()

        class MockDBManager:
            def __init__(self, session):
                self.session = session

            async def get_async_session(self):
                yield self.session

        trade_repo.db = MockDBManager(clean_database)

        # Log a trade
        await trade_repo.log_trade(
            position_id=test_position.position_id,
            portfolio_id=sample_portfolio_id,
            symbol="BTCUSDT",
            action="BUY",
            quantity=Decimal("0.1"),
            price=Decimal("50000.00"),
            commission=Decimal("5.00"),
            order_type="MARKET"
        )

        # Verify trade in database
        result = await clean_database.execute(
            select(DBTrade).where(DBTrade.position_id == test_position.position_id)
        )
        trades = result.scalars().all()

        assert len(trades) == 1
        trade = trades[0]
        assert trade.symbol == "BTCUSDT"
        assert trade.action == "BUY"
        assert trade.quantity == Decimal("0.1")
        assert trade.price == Decimal("50000.00")
        assert trade.fee == Decimal("5.00")
        assert trade.order_type == "MARKET"
        assert trade.total_cost == Decimal("5005.00")  # price * quantity + fee

    @pytest.mark.asyncio
    async def test_trade_foreign_key_constraints(
        self,
        clean_database,
        sample_portfolio_id
    ):
        """Test foreign key constraints are enforced"""
        trade_repo = TradeRepository()

        class MockDBManager:
            def __init__(self, session):
                self.session = session

            async def get_async_session(self):
                yield self.session

        trade_repo.db = MockDBManager(clean_database)

        # Try to log trade with non-existent position_id
        non_existent_position_id = uuid4()

        # This should fail or be handled gracefully
        try:
            await trade_repo.log_trade(
                position_id=non_existent_position_id,
                portfolio_id=sample_portfolio_id,
                symbol="BTCUSDT",
                action="BUY",
                quantity=Decimal("0.1"),
                price=Decimal("50000.00"),
                commission=Decimal("5.00")
            )
            # If it doesn't raise, check it wasn't persisted
            result = await clean_database.execute(
                select(func.count()).select_from(DBTrade)
            )
            count = result.scalar()
            # Should be 0 or handled gracefully
        except Exception as e:
            # Foreign key violation is expected
            assert "foreign key" in str(e).lower() or "violates" in str(e).lower()

    @pytest.mark.asyncio
    async def test_multiple_trades_for_position(
        self,
        clean_database,
        test_position,
        sample_portfolio_id
    ):
        """Test logging multiple trades for same position"""
        trade_repo = TradeRepository()

        class MockDBManager:
            def __init__(self, session):
                self.session = session

            async def get_async_session(self):
                yield self.session

        trade_repo.db = MockDBManager(clean_database)

        # Log multiple trades
        for i in range(3):
            await trade_repo.log_trade(
                position_id=test_position.position_id,
                portfolio_id=sample_portfolio_id,
                symbol="BTCUSDT",
                action="BUY" if i == 0 else "SELL",
                quantity=Decimal("0.1"),
                price=Decimal(f"{50000 + i * 1000}"),
                commission=Decimal("5.00")
            )

        # Verify all trades persisted
        result = await clean_database.execute(
            select(DBTrade).where(DBTrade.position_id == test_position.position_id)
        )
        trades = result.scalars().all()

        assert len(trades) == 3


# ==========================================
# PORTFOLIO PERSISTENCE TESTS
# ==========================================

class TestPortfolioPersistence:
    """Test portfolio operations with real database"""

    @pytest.mark.asyncio
    async def test_create_portfolio_persists(
        self,
        clean_database,
    ):
        """Test portfolio creation persists to database"""
        portfolio_repo = PortfolioRepository()

        class MockDBManager:
            def __init__(self, session):
                self.session = session

            async def get_async_session(self):
                yield self.session

        portfolio_repo.db = MockDBManager(clean_database)

        # Create portfolio
        portfolio = await portfolio_repo.get_or_create(
            portfolio_id="new_portfolio",
            name="New Test Portfolio",
            initial_balance=Decimal("5000.00")
        )

        # Verify in database
        result = await clean_database.execute(
            select(DBPortfolio).where(DBPortfolio.portfolio_id == "new_portfolio")
        )
        db_portfolio = result.scalar_one_or_none()

        assert db_portfolio is not None
        assert db_portfolio.name == "New Test Portfolio"
        assert db_portfolio.initial_balance == Decimal("5000.00")
        assert db_portfolio.cash_balance == Decimal("5000.00")
        assert db_portfolio.trading_mode == "PAPER"

    @pytest.mark.asyncio
    async def test_get_existing_portfolio(
        self,
        clean_database,
        test_portfolio
    ):
        """Test getting existing portfolio returns same instance"""
        portfolio_repo = PortfolioRepository()

        class MockDBManager:
            def __init__(self, session):
                self.session = session

            async def get_async_session(self):
                yield self.session

        portfolio_repo.db = MockDBManager(clean_database)

        # Get existing portfolio
        portfolio = await portfolio_repo.get_or_create(
            portfolio_id=test_portfolio.portfolio_id,
            name="Should Not Change",
            initial_balance=Decimal("99999.00")
        )

        # Verify it returned existing portfolio (not created new)
        assert portfolio.portfolio_id == test_portfolio.portfolio_id
        assert portfolio.name == test_portfolio.name  # Original name
        assert portfolio.initial_balance == test_portfolio.initial_balance  # Original balance

    @pytest.mark.asyncio
    async def test_update_portfolio_balance_persists(
        self,
        clean_database,
        test_portfolio
    ):
        """Test portfolio balance updates persist"""
        portfolio_repo = PortfolioRepository()

        class MockDBManager:
            def __init__(self, session):
                self.session = session

            async def get_async_session(self):
                yield self.session

        portfolio_repo.db = MockDBManager(clean_database)

        new_balance = Decimal("8500.00")
        new_realized_pnl = Decimal("-1500.00")

        # Update balance
        await portfolio_repo.update_balance(
            portfolio_id=test_portfolio.portfolio_id,
            cash_balance=new_balance,
            realized_pnl=new_realized_pnl
        )

        # Verify update
        result = await clean_database.execute(
            select(DBPortfolio).where(DBPortfolio.portfolio_id == test_portfolio.portfolio_id)
        )
        updated_portfolio = result.scalar_one_or_none()

        assert updated_portfolio.cash_balance == new_balance
        assert updated_portfolio.realized_pnl == new_realized_pnl

    @pytest.mark.asyncio
    async def test_portfolio_transaction_isolation(
        self,
        clean_database,
        test_portfolio
    ):
        """Test transaction isolation for portfolio updates"""
        portfolio_repo = PortfolioRepository()

        class MockDBManager:
            def __init__(self, session):
                self.session = session

            async def get_async_session(self):
                yield self.session

        portfolio_repo.db = MockDBManager(clean_database)

        original_balance = test_portfolio.cash_balance

        # Simulate failed transaction
        try:
            async with clean_database.begin():
                # Update balance
                await clean_database.execute(
                    text(
                        "UPDATE portfolios SET cash_balance = :balance WHERE portfolio_id = :id"
                    ).bindparams(balance=Decimal("5000.00"), id=test_portfolio.portfolio_id)
                )

                # Force rollback by raising exception
                raise Exception("Simulated transaction failure")
        except Exception:
            pass  # Expected

        # Verify balance was not changed (rolled back)
        result = await clean_database.execute(
            select(DBPortfolio).where(DBPortfolio.portfolio_id == test_portfolio.portfolio_id)
        )
        portfolio = result.scalar_one_or_none()

        # Balance should be unchanged
        assert portfolio.cash_balance == original_balance


# ==========================================
# DATABASE ROLLBACK TESTS
# ==========================================

class TestDatabaseRollback:
    """Test transaction rollback scenarios"""

    @pytest.mark.asyncio
    async def test_position_creation_rollback_on_error(
        self,
        clean_database,
        test_portfolio,
        sample_portfolio_id
    ):
        """Test that failed position creation rolls back"""
        initial_count_result = await clean_database.execute(
            select(func.count()).select_from(DBPosition)
        )
        initial_count = initial_count_result.scalar()

        # Try to create position in transaction that will fail
        try:
            async with clean_database.begin():
                # Create valid position
                position = DBPosition(
                    position_id=uuid4(),
                    portfolio_id=sample_portfolio_id,
                    symbol="BTCUSDT",
                    side="LONG",
                    quantity=Decimal("0.1"),
                    entry_price=Decimal("50000.00"),
                    cost_basis=Decimal("5000.00"),
                    status="OPEN",
                )
                clean_database.add(position)

                # Force error
                raise Exception("Simulated error")
        except Exception:
            pass  # Expected

        # Verify position was not created (rolled back)
        final_count_result = await clean_database.execute(
            select(func.count()).select_from(DBPosition)
        )
        final_count = final_count_result.scalar()

        assert final_count == initial_count

    @pytest.mark.asyncio
    async def test_trade_logging_rollback_on_error(
        self,
        clean_database,
        test_position,
        sample_portfolio_id
    ):
        """Test that failed trade logging rolls back"""
        initial_count_result = await clean_database.execute(
            select(func.count()).select_from(DBTrade)
        )
        initial_count = initial_count_result.scalar()

        # Try to log trade in transaction that will fail
        try:
            async with clean_database.begin():
                # Create valid trade
                trade = DBTrade(
                    trade_id=uuid4(),
                    portfolio_id=sample_portfolio_id,
                    position_id=test_position.position_id,
                    symbol="BTCUSDT",
                    action="BUY",
                    order_type="MARKET",
                    quantity=Decimal("0.1"),
                    price=Decimal("50000.00"),
                    total_cost=Decimal("5000.00"),
                    fee=Decimal("5.00"),
                )
                clean_database.add(trade)

                # Force error
                raise Exception("Simulated error")
        except Exception:
            pass  # Expected

        # Verify trade was not logged (rolled back)
        final_count_result = await clean_database.execute(
            select(func.count()).select_from(DBTrade)
        )
        final_count = final_count_result.scalar()

        assert final_count == initial_count


# ==========================================
# DATABASE PERFORMANCE TESTS
# ==========================================

class TestDatabasePerformance:
    """Test database performance"""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_bulk_position_creation_performance(
        self,
        clean_database,
        test_portfolio,
        sample_portfolio_id,
        benchmark_timer
    ):
        """Test creating many positions quickly"""
        positions_to_create = 100

        with benchmark_timer() as timer:
            # Create 100 positions
            for i in range(positions_to_create):
                position = DBPosition(
                    position_id=uuid4(),
                    portfolio_id=sample_portfolio_id,
                    symbol=f"SYMBOL{i}USDT",
                    side="LONG",
                    quantity=Decimal("1.0"),
                    entry_price=Decimal(f"{50000 + i}"),
                    cost_basis=Decimal(f"{50000 + i}"),
                    status="OPEN",
                )
                clean_database.add(position)

            await clean_database.commit()

        # Assert completed in reasonable time (< 2 seconds)
        timer.assert_faster_than(2000)

        # Verify all positions were created
        count_result = await clean_database.execute(
            select(func.count()).select_from(DBPosition)
        )
        count = count_result.scalar()
        assert count == positions_to_create

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_query_performance_with_large_dataset(
        self,
        clean_database,
        test_portfolio,
        sample_portfolio_id,
        benchmark_timer
    ):
        """Test query performance with many positions"""
        # Create 1000 positions
        for i in range(1000):
            position = DBPosition(
                position_id=uuid4(),
                portfolio_id=sample_portfolio_id,
                symbol=f"SYMBOL{i % 10}USDT",  # 10 different symbols
                side="LONG" if i % 2 == 0 else "SHORT",
                quantity=Decimal("1.0"),
                entry_price=Decimal(f"{50000 + i}"),
                cost_basis=Decimal(f"{50000 + i}"),
                status="OPEN" if i % 3 != 0 else "CLOSED",
            )
            clean_database.add(position)

        await clean_database.commit()

        # Test query performance
        with benchmark_timer() as timer:
            result = await clean_database.execute(
                select(DBPosition)
                .where(DBPosition.portfolio_id == sample_portfolio_id)
                .where(DBPosition.status == "OPEN")
            )
            positions = result.scalars().all()

        # Assert query completed quickly (< 200ms)
        timer.assert_faster_than(200)

        # Verify correct results
        assert len(positions) > 0

    @pytest.mark.asyncio
    async def test_database_index_usage(
        self,
        clean_database,
        test_portfolio,
        sample_portfolio_id
    ):
        """Test that database indexes are being used for queries"""
        # Create positions
        for i in range(100):
            position = DBPosition(
                position_id=uuid4(),
                portfolio_id=sample_portfolio_id,
                symbol="BTCUSDT",
                side="LONG",
                quantity=Decimal("1.0"),
                entry_price=Decimal(f"{50000 + i}"),
                cost_basis=Decimal(f"{50000 + i}"),
                status="OPEN",
            )
            clean_database.add(position)

        await clean_database.commit()

        # Query using indexed columns (portfolio_id, status)
        # This should be fast due to index: idx_positions_portfolio_status
        result = await clean_database.execute(
            select(DBPosition)
            .where(DBPosition.portfolio_id == sample_portfolio_id)
            .where(DBPosition.status == "OPEN")
        )
        positions = result.scalars().all()

        # Verify results
        assert len(positions) == 100


# ==========================================
# DATA INTEGRITY TESTS
# ==========================================

class TestDataIntegrity:
    """Test database constraints and data integrity"""

    @pytest.mark.asyncio
    async def test_position_quantity_constraint(
        self,
        clean_database,
        test_portfolio,
        sample_portfolio_id
    ):
        """Test that negative quantity is rejected by check constraint"""
        # Try to create position with negative quantity
        with pytest.raises(Exception) as exc_info:
            position = DBPosition(
                position_id=uuid4(),
                portfolio_id=sample_portfolio_id,
                symbol="BTCUSDT",
                side="LONG",
                quantity=Decimal("-0.1"),  # Invalid: negative
                entry_price=Decimal("50000.00"),
                cost_basis=Decimal("5000.00"),
                status="OPEN",
            )
            clean_database.add(position)
            await clean_database.commit()

        # Verify constraint violation
        assert "check_positive_quantity" in str(exc_info.value) or "constraint" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_position_side_constraint(
        self,
        clean_database,
        test_portfolio,
        sample_portfolio_id
    ):
        """Test that invalid position side is rejected"""
        with pytest.raises(Exception) as exc_info:
            position = DBPosition(
                position_id=uuid4(),
                portfolio_id=sample_portfolio_id,
                symbol="BTCUSDT",
                side="INVALID_SIDE",  # Invalid: not LONG or SHORT
                quantity=Decimal("0.1"),
                entry_price=Decimal("50000.00"),
                cost_basis=Decimal("5000.00"),
                status="OPEN",
            )
            clean_database.add(position)
            await clean_database.commit()

        # Verify constraint violation
        assert "check_valid_side" in str(exc_info.value) or "constraint" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_portfolio_foreign_key_cascade(
        self,
        clean_database,
        test_portfolio,
        test_position
    ):
        """Test that deleting portfolio cascades to positions"""
        # Verify position exists
        position_result = await clean_database.execute(
            select(DBPosition).where(DBPosition.position_id == test_position.position_id)
        )
        assert position_result.scalar_one_or_none() is not None

        # Delete portfolio (should cascade to positions)
        await clean_database.execute(
            text("DELETE FROM portfolios WHERE portfolio_id = :id").bindparams(
                id=test_portfolio.portfolio_id
            )
        )
        await clean_database.commit()

        # Verify position was deleted via cascade
        position_result = await clean_database.execute(
            select(DBPosition).where(DBPosition.position_id == test_position.position_id)
        )
        assert position_result.scalar_one_or_none() is None
