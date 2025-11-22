"""
Position Manager
Purpose: Track and manage trading positions
Enhanced: Database persistence for positions
"""

import logging
from typing import List, Optional
from decimal import Decimal
from uuid import UUID
from datetime import datetime, timezone
from app.models import Position, PositionCreate, PositionStatus, PositionSide
from app.risk_manager import get_risk_manager
from app.repositories import get_position_repository

logger = logging.getLogger(__name__)


class PositionManager:
    """
    Manages trading positions

    Responsibilities:
    1. Track all open and closed positions
    2. Calculate P&L
    3. Check stop-loss and take-profit
    4. Update position prices
    """

    def __init__(self):
        """Initialize position manager with database persistence"""
        self.positions: dict[UUID, Position] = {}
        self.risk_manager = get_risk_manager()
        self.position_repo = get_position_repository()
        logger.info("PositionManager initialized with database persistence")

    def create_position(
        self,
        symbol: str,
        side: PositionSide,
        entry_price: Decimal,
        quantity: Decimal,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
        strategy: Optional[str] = None
    ) -> Position:
        """
        Create a new position

        Args:
            symbol: Trading symbol
            side: Position side (LONG/SHORT)
            entry_price: Entry price
            quantity: Position quantity
            stop_loss: Optional stop loss price
            take_profit: Optional take profit price
            strategy: Strategy name

        Returns:
            Created position
        """
        # Calculate stop-loss and take-profit if not provided
        if stop_loss is None:
            stop_loss = self.risk_manager.calculate_stop_loss(entry_price, side)

        if take_profit is None:
            take_profit = self.risk_manager.calculate_take_profit(entry_price, side)

        # Create position
        position = Position(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            current_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            strategy=strategy,
            status=PositionStatus.OPEN
        )

        # Store position in memory
        self.positions[position.id] = position

        logger.info(
            f"✓ Position created: {position.id} | "
            f"{symbol} {side.value} {quantity} @ {entry_price} | "
            f"SL: {stop_loss} | TP: {take_profit}"
        )

        # Persist to database (async, non-blocking)
        import asyncio
        try:
            asyncio.create_task(
                self.position_repo.create(position, portfolio_id="paper_trading")
            )
        except Exception as e:
            logger.warning(f"Failed to persist position to database: {e}")

        return position

    def get_position(self, position_id: UUID) -> Optional[Position]:
        """Get position by ID"""
        return self.positions.get(position_id)

    def get_all_positions(self) -> List[Position]:
        """Get all positions"""
        return list(self.positions.values())

    def get_open_positions(self) -> List[Position]:
        """Get all open positions"""
        return [pos for pos in self.positions.values() if pos.status == PositionStatus.OPEN]

    def get_closed_positions(self) -> List[Position]:
        """Get all closed positions"""
        return [pos for pos in self.positions.values() if pos.status == PositionStatus.CLOSED]

    def update_position_price(
        self,
        position_id: UUID,
        current_price: Decimal
    ) -> Position:
        """
        Update position with current price and recalculate P&L

        Args:
            position_id: Position ID
            current_price: Current market price

        Returns:
            Updated position
        """
        position = self.positions.get(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")

        # Update P&L
        position.update_pnl(current_price)

        logger.debug(
            f"Position {position_id} updated: "
            f"price={current_price}, unrealized_pnl={position.unrealized_pnl} "
            f"({position.pnl_percentage:+.2f}%)"
        )

        # Update price in database (async, non-blocking)
        import asyncio
        try:
            asyncio.create_task(
                self.position_repo.update_price(
                    position_id, current_price, position.unrealized_pnl
                )
            )
        except Exception as e:
            logger.warning(f"Failed to update position price in database: {e}")

        return position

    def check_position_exit(
        self,
        position_id: UUID,
        current_price: Decimal
    ) -> tuple[bool, Optional[str]]:
        """
        Check if position should be closed

        Args:
            position_id: Position ID
            current_price: Current market price

        Returns:
            Tuple of (should_close, reason)
        """
        position = self.positions.get(position_id)
        if not position:
            return False, "Position not found"

        if position.status != PositionStatus.OPEN:
            return False, "Position not open"

        return self.risk_manager.should_close_position(position, current_price)

    def close_position(
        self,
        position_id: UUID,
        close_price: Decimal,
        reason: Optional[str] = None
    ) -> Position:
        """
        Close a position

        Args:
            position_id: Position ID
            close_price: Closing price
            reason: Reason for closing

        Returns:
            Closed position
        """
        position = self.positions.get(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")

        if position.status != PositionStatus.OPEN:
            raise ValueError(f"Position {position_id} is not open")

        # Update P&L with closing price
        position.update_pnl(close_price)

        # Mark as closed
        position.realized_pnl = position.unrealized_pnl
        position.unrealized_pnl = Decimal("0")
        position.status = PositionStatus.CLOSED
        position.closed_at = datetime.now(timezone.utc)

        # Update risk manager daily P&L
        self.risk_manager.update_daily_pnl(position.realized_pnl)

        logger.info(
            f"✓ Position closed: {position_id} | "
            f"{position.symbol} at {close_price} | "
            f"P&L: {position.realized_pnl} ({position.pnl_percentage:+.2f}%) | "
            f"Reason: {reason or 'Manual'}"
        )

        # Close position in database (async, non-blocking)
        import asyncio
        try:
            asyncio.create_task(
                self.position_repo.close(
                    position_id,
                    close_price,
                    position.realized_pnl,
                    exit_reason=reason
                )
            )
        except Exception as e:
            logger.warning(f"Failed to close position in database: {e}")

        return position

    def get_total_exposure(self) -> Decimal:
        """Calculate total exposure from open positions"""
        return sum(
            pos.entry_price * pos.quantity
            for pos in self.get_open_positions()
        )

    def get_total_unrealized_pnl(self) -> Decimal:
        """Calculate total unrealized P&L from open positions"""
        return sum(pos.unrealized_pnl for pos in self.get_open_positions())

    def get_total_realized_pnl(self) -> Decimal:
        """Calculate total realized P&L from closed positions"""
        return sum(pos.realized_pnl for pos in self.get_closed_positions())

    def get_position_count(self) -> dict:
        """Get position counts by status"""
        return {
            "total": len(self.positions),
            "open": len(self.get_open_positions()),
            "closed": len(self.get_closed_positions())
        }


# Global position manager instance
_position_manager: Optional[PositionManager] = None


def get_position_manager() -> PositionManager:
    """Get or create position manager instance"""
    global _position_manager
    if _position_manager is None:
        _position_manager = PositionManager()
    return _position_manager
