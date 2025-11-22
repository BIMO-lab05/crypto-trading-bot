"""
Database Repositories
Purpose: Data access layer for persisting trading data
"""

import logging
from typing import List, Optional
from decimal import Decimal
from uuid import UUID
from datetime import datetime, timezone

# Import shared database infrastructure
import sys
from pathlib import Path
# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))

from database.connection import db_manager
from database.models import Position as DBPosition, Trade as DBTrade, Portfolio as DBPortfolio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Position, PositionStatus, PositionSide

logger = logging.getLogger(__name__)


class PositionRepository:
    """
    Repository for Position database operations

    Responsibilities:
    - Create positions in database
    - Update position prices and P&L
    - Close positions
    - Query positions by various criteria
    """

    def __init__(self):
        """Initialize position repository"""
        self.db = db_manager
        logger.info("PositionRepository initialized")

    async def create(self, position: Position, portfolio_id: str = "paper_trading") -> UUID:
        """
        Create a new position in database

        Args:
            position: Position object from app.models
            portfolio_id: Portfolio ID (default: paper_trading)

        Returns:
            Position ID (UUID)
        """
        try:
            async with self.db.get_async_session() as session:
                # Convert app Position model to DB Position model
                db_position = DBPosition(
                    position_id=position.id,
                    portfolio_id=portfolio_id,
                    symbol=position.symbol,
                    side=position.side.value,
                    quantity=position.quantity,
                    entry_price=position.entry_price,
                    current_price=position.current_price,
                    cost_basis=position.entry_price * position.quantity,
                    unrealized_pnl=position.unrealized_pnl,
                    stop_loss=position.stop_loss,
                    take_profit=position.take_profit,
                    status=position.status.value,
                    strategy=position.strategy,
                    opened_at=position.opened_at  # Fixed: was entry_time
                )

                session.add(db_position)
                await session.commit()

                logger.info(f"✓ Position saved to database: {position.id}")
                return position.id

        except Exception as e:
            logger.error(f"Failed to create position in database: {e}")
            raise

    async def update_price(
        self,
        position_id: UUID,
        current_price: Decimal,
        unrealized_pnl: Decimal
    ):
        """
        Update position price and P&L

        Args:
            position_id: Position UUID
            current_price: Current market price
            unrealized_pnl: Updated unrealized P&L
        """
        try:
            async with self.db.get_async_session() as session:
                stmt = (
                    update(DBPosition)
                    .where(DBPosition.position_id == position_id)
                    .values(
                        current_price=current_price,
                        unrealized_pnl=unrealized_pnl,
                        updated_at=datetime.now(timezone.utc)
                    )
                )

                await session.execute(stmt)
                await session.commit()

                logger.debug(f"Position {position_id} price updated in database")

        except Exception as e:
            logger.error(f"Failed to update position price in database: {e}")
            raise

    async def close(
        self,
        position_id: UUID,
        exit_price: Decimal,
        realized_pnl: Decimal,
        exit_reason: Optional[str] = None
    ):
        """
        Close a position in database

        Args:
            position_id: Position UUID
            exit_price: Exit price
            realized_pnl: Realized P&L
            exit_reason: Reason for closing (optional)
        """
        try:
            async with self.db.get_async_session() as session:
                stmt = (
                    update(DBPosition)
                    .where(DBPosition.position_id == position_id)
                    .values(
                        status='CLOSED',
                        exit_price=exit_price,
                        realized_pnl=realized_pnl,
                        exit_reason=exit_reason,
                        closed_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc)
                    )
                )

                await session.execute(stmt)
                await session.commit()

                logger.info(f"✓ Position {position_id} closed in database (P&L: ${realized_pnl})")

        except Exception as e:
            logger.error(f"Failed to close position in database: {e}")
            raise

    async def get_by_id(self, position_id: UUID) -> Optional[DBPosition]:
        """Get position by ID from database"""
        try:
            async with self.db.get_async_session() as session:
                result = await session.execute(
                    select(DBPosition).where(DBPosition.position_id == position_id)
                )
                return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get position from database: {e}")
            return None

    async def get_open_positions(self, portfolio_id: str = "paper_trading") -> List[DBPosition]:
        """Get all open positions for a portfolio"""
        try:
            async with self.db.get_async_session() as session:
                result = await session.execute(
                    select(DBPosition)
                    .where(DBPosition.portfolio_id == portfolio_id)
                    .where(DBPosition.status == 'OPEN')
                )
                return result.scalars().all()
        except Exception as e:
            logger.error(f"Failed to get open positions from database: {e}")
            return []


class TradeRepository:
    """
    Repository for Trade database operations

    Note: Trade logging is currently simplified.
    Full implementation would include order details, execution info, etc.
    """

    def __init__(self):
        """Initialize trade repository"""
        self.db = db_manager
        logger.info("TradeRepository initialized")

    async def log_trade(
        self,
        position_id: UUID,
        portfolio_id: str,
        symbol: str,
        action: str,  # Fixed: was 'side', should be 'action'
        quantity: Decimal,
        price: Decimal,
        commission: Decimal,
        order_type: str = "MARKET"  # Fixed: was 'trade_type', should be 'order_type'
    ):
        """
        Log a trade to database

        Args:
            position_id: Associated position UUID
            portfolio_id: Portfolio ID
            symbol: Trading symbol
            action: Trade action (BUY/SELL)
            quantity: Trade quantity
            price: Execution price
            commission: Commission paid (stored in 'fee' column)
            order_type: Type of order (MARKET/LIMIT)
        """
        try:
            async with self.db.get_async_session() as session:
                total_cost = price * quantity + commission
                db_trade = DBTrade(
                    position_id=position_id,
                    portfolio_id=portfolio_id,
                    symbol=symbol,
                    action=action,  # Fixed: was 'side'
                    quantity=quantity,
                    price=price,
                    total_cost=total_cost,  # Added: required field
                    fee=commission,  # Fixed: was 'commission', should be 'fee'
                    order_type=order_type,  # Fixed: was 'trade_type'
                    executed_at=datetime.now(timezone.utc)
                )

                session.add(db_trade)
                await session.commit()

                logger.info(f"✓ Trade logged to database: {action} {quantity} {symbol} @ ${price}")

        except Exception as e:
            logger.error(f"Failed to log trade to database: {e}")
            # Don't raise - trade logging failure shouldn't break execution
            pass


class PortfolioRepository:
    """
    Repository for Portfolio database operations
    """

    def __init__(self):
        """Initialize portfolio repository"""
        self.db = db_manager
        logger.info("PortfolioRepository initialized")

    async def get_or_create(
        self,
        portfolio_id: str = "paper_trading",
        name: str = "Paper Trading Portfolio",
        initial_balance: Decimal = Decimal("10000")
    ) -> DBPortfolio:
        """
        Get existing portfolio or create if doesn't exist

        Args:
            portfolio_id: Portfolio identifier
            name: Portfolio name
            initial_balance: Initial balance for new portfolio

        Returns:
            Portfolio object
        """
        try:
            async with self.db.get_async_session() as session:
                # Try to get existing portfolio
                result = await session.execute(
                    select(DBPortfolio).where(DBPortfolio.portfolio_id == portfolio_id)
                )
                portfolio = result.scalar_one_or_none()

                if portfolio:
                    logger.info(f"Found existing portfolio: {portfolio_id}")
                    return portfolio

                # Create new portfolio
                portfolio = DBPortfolio(
                    portfolio_id=portfolio_id,
                    name=name,
                    initial_balance=initial_balance,
                    cash_balance=initial_balance,
                    trading_mode='PAPER'
                )

                session.add(portfolio)
                await session.commit()

                logger.info(f"✓ Created new portfolio in database: {portfolio_id}")
                return portfolio

        except Exception as e:
            logger.error(f"Failed to get/create portfolio: {e}")
            raise

    async def update_balance(
        self,
        portfolio_id: str,
        cash_balance: Decimal,
        realized_pnl: Decimal = None
    ):
        """
        Update portfolio balance and P&L

        Args:
            portfolio_id: Portfolio ID
            cash_balance: New cash balance
            realized_pnl: Total realized P&L (optional)
        """
        try:
            async with self.db.get_async_session() as session:
                update_values = {
                    'cash_balance': cash_balance,
                    'updated_at': datetime.now(timezone.utc)
                }

                if realized_pnl is not None:
                    update_values['realized_pnl'] = realized_pnl

                stmt = (
                    update(DBPortfolio)
                    .where(DBPortfolio.portfolio_id == portfolio_id)
                    .values(**update_values)
                )

                await session.execute(stmt)
                await session.commit()

                logger.debug(f"Portfolio {portfolio_id} balance updated in database")

        except Exception as e:
            logger.error(f"Failed to update portfolio balance: {e}")
            raise


# Singleton instances
_position_repo: Optional[PositionRepository] = None
_trade_repo: Optional[TradeRepository] = None
_portfolio_repo: Optional[PortfolioRepository] = None


def get_position_repository() -> PositionRepository:
    """Get position repository singleton"""
    global _position_repo
    if _position_repo is None:
        _position_repo = PositionRepository()
    return _position_repo


def get_trade_repository() -> TradeRepository:
    """Get trade repository singleton"""
    global _trade_repo
    if _trade_repo is None:
        _trade_repo = TradeRepository()
    return _trade_repo


def get_portfolio_repository() -> PortfolioRepository:
    """Get portfolio repository singleton"""
    global _portfolio_repo
    if _portfolio_repo is None:
        _portfolio_repo = PortfolioRepository()
    return _portfolio_repo
