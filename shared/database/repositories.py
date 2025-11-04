"""
Database Repositories
Provides clean data access layer for database operations
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict
from uuid import UUID

from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from .models import Portfolio, Position, Trade, PortfolioSnapshot, NotificationHistory


# ==========================================
# PORTFOLIO REPOSITORY
# ==========================================
class PortfolioRepository:
    """Repository for portfolio operations"""

    @staticmethod
    async def get_by_id(session: AsyncSession, portfolio_id: str) -> Optional[Portfolio]:
        """Get portfolio by ID"""
        result = await session.execute(
            select(Portfolio).where(Portfolio.portfolio_id == portfolio_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_active_portfolios(session: AsyncSession) -> List[Portfolio]:
        """Get all active portfolios"""
        result = await session.execute(
            select(Portfolio).where(Portfolio.is_active == True)
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(session: AsyncSession, **kwargs) -> Portfolio:
        """Create new portfolio"""
        portfolio = Portfolio(**kwargs)
        session.add(portfolio)
        await session.commit()
        await session.refresh(portfolio)
        return portfolio

    @staticmethod
    async def update_balance(
        session: AsyncSession,
        portfolio_id: str,
        cash_balance: Decimal,
        realized_pnl: Decimal,
        unrealized_pnl: Decimal
    ) -> Portfolio:
        """Update portfolio balances and P&L"""
        portfolio = await PortfolioRepository.get_by_id(session, portfolio_id)
        if portfolio:
            portfolio.cash_balance = cash_balance
            portfolio.realized_pnl = realized_pnl
            portfolio.unrealized_pnl = unrealized_pnl
            portfolio.total_pnl = realized_pnl + unrealized_pnl
            await session.commit()
            await session.refresh(portfolio)
        return portfolio


# ==========================================
# POSITION REPOSITORY
# ==========================================
class PositionRepository:
    """Repository for position operations"""

    @staticmethod
    async def get_by_id(session: AsyncSession, position_id: UUID) -> Optional[Position]:
        """Get position by ID"""
        result = await session.execute(
            select(Position).where(Position.position_id == position_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_open_positions(
        session: AsyncSession,
        portfolio_id: str,
        symbol: Optional[str] = None
    ) -> List[Position]:
        """Get open positions for portfolio"""
        query = select(Position).where(
            and_(
                Position.portfolio_id == portfolio_id,
                Position.status == 'OPEN'
            )
        )

        if symbol:
            query = query.where(Position.symbol == symbol)

        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_closed_positions(
        session: AsyncSession,
        portfolio_id: str,
        limit: int = 100
    ) -> List[Position]:
        """Get closed positions for portfolio"""
        result = await session.execute(
            select(Position)
            .where(
                and_(
                    Position.portfolio_id == portfolio_id,
                    Position.status == 'CLOSED'
                )
            )
            .order_by(desc(Position.closed_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(session: AsyncSession, **kwargs) -> Position:
        """Create new position"""
        position = Position(**kwargs)
        session.add(position)
        await session.commit()
        await session.refresh(position)
        return position

    @staticmethod
    async def update_price(
        session: AsyncSession,
        position_id: UUID,
        current_price: Decimal
    ) -> Position:
        """Update position current price and unrealized P&L"""
        position = await PositionRepository.get_by_id(session, position_id)
        if position:
            position.current_price = current_price

            # Calculate unrealized P&L
            if position.side == 'LONG':
                position.unrealized_pnl = (current_price - position.entry_price) * position.quantity
            else:  # SHORT
                position.unrealized_pnl = (position.entry_price - current_price) * position.quantity

            await session.commit()
            await session.refresh(position)
        return position

    @staticmethod
    async def close_position(
        session: AsyncSession,
        position_id: UUID,
        exit_price: Decimal,
        realized_pnl: Decimal,
        exit_reason: str
    ) -> Position:
        """Close a position"""
        position = await PositionRepository.get_by_id(session, position_id)
        if position:
            position.status = 'CLOSED'
            position.exit_price = exit_price
            position.realized_pnl = realized_pnl
            position.exit_reason = exit_reason
            position.closed_at = datetime.utcnow()
            await session.commit()
            await session.refresh(position)
        return position


# ==========================================
# TRADE REPOSITORY
# ==========================================
class TradeRepository:
    """Repository for trade operations"""

    @staticmethod
    async def get_by_id(session: AsyncSession, trade_id: UUID) -> Optional[Trade]:
        """Get trade by ID"""
        result = await session.execute(
            select(Trade).where(Trade.trade_id == trade_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_recent_trades(
        session: AsyncSession,
        portfolio_id: str,
        limit: int = 100
    ) -> List[Trade]:
        """Get recent trades for portfolio"""
        result = await session.execute(
            select(Trade)
            .where(Trade.portfolio_id == portfolio_id)
            .order_by(desc(Trade.executed_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_trades_by_symbol(
        session: AsyncSession,
        portfolio_id: str,
        symbol: str,
        limit: int = 100
    ) -> List[Trade]:
        """Get trades for specific symbol"""
        result = await session.execute(
            select(Trade)
            .where(
                and_(
                    Trade.portfolio_id == portfolio_id,
                    Trade.symbol == symbol
                )
            )
            .order_by(desc(Trade.executed_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_daily_trades(
        session: AsyncSession,
        portfolio_id: str,
        date: datetime
    ) -> List[Trade]:
        """Get all trades for a specific date"""
        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = date.replace(hour=23, minute=59, second=59, microsecond=999999)

        result = await session.execute(
            select(Trade)
            .where(
                and_(
                    Trade.portfolio_id == portfolio_id,
                    Trade.executed_at >= start_of_day,
                    Trade.executed_at <= end_of_day
                )
            )
            .order_by(desc(Trade.executed_at))
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(session: AsyncSession, **kwargs) -> Trade:
        """Create new trade record"""
        trade = Trade(**kwargs)
        session.add(trade)
        await session.commit()
        await session.refresh(trade)
        return trade

    @staticmethod
    async def get_performance_stats(
        session: AsyncSession,
        portfolio_id: str
    ) -> Dict:
        """Get performance statistics for portfolio"""
        result = await session.execute(
            select(
                func.count(Trade.trade_id).label('total_trades'),
                func.sum(func.case((Trade.realized_pnl > 0, 1), else_=0)).label('winning_trades'),
                func.sum(func.case((Trade.realized_pnl < 0, 1), else_=0)).label('losing_trades'),
                func.sum(Trade.realized_pnl).label('total_pnl'),
                func.avg(Trade.realized_pnl).label('avg_pnl'),
                func.max(Trade.realized_pnl).label('max_profit'),
                func.min(Trade.realized_pnl).label('max_loss'),
            )
            .where(
                and_(
                    Trade.portfolio_id == portfolio_id,
                    Trade.realized_pnl.isnot(None)
                )
            )
        )

        row = result.first()

        total_trades = row.total_trades or 0
        winning_trades = row.winning_trades or 0
        losing_trades = row.losing_trades or 0

        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': winning_trades / total_trades if total_trades > 0 else 0,
            'total_pnl': float(row.total_pnl) if row.total_pnl else 0,
            'avg_pnl': float(row.avg_pnl) if row.avg_pnl else 0,
            'max_profit': float(row.max_profit) if row.max_profit else 0,
            'max_loss': float(row.max_loss) if row.max_loss else 0,
        }


# ==========================================
# SNAPSHOT REPOSITORY
# ==========================================
class SnapshotRepository:
    """Repository for portfolio snapshot operations"""

    @staticmethod
    async def create(session: AsyncSession, **kwargs) -> PortfolioSnapshot:
        """Create portfolio snapshot"""
        snapshot = PortfolioSnapshot(**kwargs)
        session.add(snapshot)
        await session.commit()
        await session.refresh(snapshot)
        return snapshot

    @staticmethod
    async def get_latest(
        session: AsyncSession,
        portfolio_id: str
    ) -> Optional[PortfolioSnapshot]:
        """Get latest snapshot for portfolio"""
        result = await session.execute(
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.portfolio_id == portfolio_id)
            .order_by(desc(PortfolioSnapshot.snapshot_time))
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_historical(
        session: AsyncSession,
        portfolio_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[PortfolioSnapshot]:
        """Get historical snapshots for time range"""
        result = await session.execute(
            select(PortfolioSnapshot)
            .where(
                and_(
                    PortfolioSnapshot.portfolio_id == portfolio_id,
                    PortfolioSnapshot.snapshot_time >= start_time,
                    PortfolioSnapshot.snapshot_time <= end_time
                )
            )
            .order_by(PortfolioSnapshot.snapshot_time)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_daily_snapshots(
        session: AsyncSession,
        portfolio_id: str,
        days: int = 30
    ) -> List[PortfolioSnapshot]:
        """Get daily snapshots for last N days"""
        # Get one snapshot per day
        result = await session.execute(
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.portfolio_id == portfolio_id)
            .order_by(desc(PortfolioSnapshot.snapshot_time))
            .limit(days)
        )
        return list(result.scalars().all())


# ==========================================
# NOTIFICATION REPOSITORY
# ==========================================
class NotificationRepository:
    """Repository for notification history operations"""

    @staticmethod
    async def create(session: AsyncSession, **kwargs) -> NotificationHistory:
        """Create notification history record"""
        notification = NotificationHistory(**kwargs)
        session.add(notification)
        await session.commit()
        await session.refresh(notification)
        return notification

    @staticmethod
    async def get_recent(
        session: AsyncSession,
        portfolio_id: Optional[str] = None,
        limit: int = 100
    ) -> List[NotificationHistory]:
        """Get recent notifications"""
        query = select(NotificationHistory)

        if portfolio_id:
            query = query.where(NotificationHistory.portfolio_id == portfolio_id)

        query = query.order_by(desc(NotificationHistory.sent_at)).limit(limit)

        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_by_type(
        session: AsyncSession,
        notification_type: str,
        limit: int = 100
    ) -> List[NotificationHistory]:
        """Get notifications by type"""
        result = await session.execute(
            select(NotificationHistory)
            .where(NotificationHistory.notification_type == notification_type)
            .order_by(desc(NotificationHistory.sent_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_failed_notifications(
        session: AsyncSession,
        limit: int = 100
    ) -> List[NotificationHistory]:
        """Get failed notifications"""
        result = await session.execute(
            select(NotificationHistory)
            .where(NotificationHistory.status == 'FAILED')
            .order_by(desc(NotificationHistory.sent_at))
            .limit(limit)
        )
        return list(result.scalars().all())
