"""
Trade History Endpoint Handlers
Purpose: Trade history retrieval and statistics

Provides:
- Closed trades history from database (persistent)
- Win/loss statistics
- Profit factor calculation
- Average win/loss metrics

UPDATED 2025-11-30: Fixed to query database instead of in-memory position manager.
This ensures trade history persists across service restarts.
"""

import logging
import time
from decimal import Decimal
from fastapi import HTTPException

from app.repositories import get_position_repository
from app.models import (
    TradeHistoryResponse,
    TradeHistoryStats,
    Position,
    PositionStatus,
    PositionSide,
)
from app.models.enums import ExitKind


logger = logging.getLogger(__name__)


def db_position_to_app_position(db_pos) -> Position:
    """
    Convert database Position model to app Position model

    Args:
        db_pos: Database Position object from SQLAlchemy

    Returns:
        Position: App model Position object
    """
    return Position(
        id=db_pos.position_id,
        symbol=db_pos.symbol,
        side=PositionSide(db_pos.side),
        quantity=Decimal(str(db_pos.quantity)),
        entry_price=Decimal(str(db_pos.entry_price)),
        current_price=Decimal(str(db_pos.current_price))
        if db_pos.current_price
        else Decimal(str(db_pos.entry_price)),
        stop_loss=Decimal(str(db_pos.stop_loss)) if db_pos.stop_loss else None,
        take_profit=Decimal(str(db_pos.take_profit)) if db_pos.take_profit else None,
        status=PositionStatus(db_pos.status),
        strategy=db_pos.strategy,
        opened_at=db_pos.opened_at,
        closed_at=db_pos.closed_at,
        unrealized_pnl=Decimal(str(db_pos.unrealized_pnl))
        if db_pos.unrealized_pnl
        else Decimal("0"),
        realized_pnl=Decimal(str(db_pos.realized_pnl))
        if db_pos.realized_pnl
        else Decimal("0"),
        exit_price=Decimal(str(db_pos.exit_price)) if db_pos.exit_price else None,
        exit_reason=db_pos.exit_reason,
        posted_margin=Decimal(str(db_pos.posted_margin))
        if db_pos.posted_margin is not None
        else Decimal("0"),
        leverage=Decimal(str(db_pos.leverage))
        if db_pos.leverage is not None
        else Decimal("1"),
        exit_kind=ExitKind(db_pos.exit_kind) if db_pos.exit_kind else None,
    )


async def get_trade_history(limit: int = 50) -> TradeHistoryResponse:
    """
    Get closed trades history with statistics from DATABASE

    This function queries the PostgreSQL database for closed positions,
    ensuring trade history persists across service restarts.

    Args:
        limit: Maximum number of trades to return (default 50)

    Returns:
        TradeHistoryResponse with closed trades and statistics

    Raises:
        HTTPException: If trade history retrieval fails
    """
    try:
        # Get position repository for database access
        position_repo = get_position_repository()

        # Query closed positions from database (already sorted by closed_at desc)
        db_closed_positions = await position_repo.get_closed_positions(
            portfolio_id="paper_trading", limit=limit
        )

        logger.info(
            f"Retrieved {len(db_closed_positions)} closed positions from database"
        )

        # Convert DB positions to app model positions
        closed_positions = [
            db_position_to_app_position(db_pos) for db_pos in db_closed_positions
        ]

        # Calculate statistics
        stats = calculate_trade_stats(closed_positions)

        return TradeHistoryResponse(
            success=True,
            trades=closed_positions,
            stats=stats,
            count=len(closed_positions),
            timestamp=int(time.time() * 1000),
        )

    except Exception as e:
        logger.error(f"Error getting trade history from database: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def calculate_trade_stats(trades: list) -> TradeHistoryStats:
    """
    Calculate statistics from closed trades

    Args:
        trades: List of closed Position objects

    Returns:
        TradeHistoryStats with calculated metrics
    """
    if not trades:
        return TradeHistoryStats(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            total_realized_pnl=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            best_trade=0.0,
            worst_trade=0.0,
            profit_factor=0.0,
        )

    # Separate winning and losing trades
    winning = [t for t in trades if float(t.realized_pnl) > 0]
    losing = [t for t in trades if float(t.realized_pnl) < 0]
    breakeven = [t for t in trades if float(t.realized_pnl) == 0]

    total_trades = len(trades)
    winning_trades = len(winning)
    losing_trades = len(losing)

    # Calculate win rate
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

    # Calculate total P&L
    total_pnl = sum(float(t.realized_pnl) for t in trades)

    # Calculate averages
    avg_win = (
        sum(float(t.realized_pnl) for t in winning) / len(winning) if winning else 0.0
    )
    avg_loss = (
        sum(float(t.realized_pnl) for t in losing) / len(losing) if losing else 0.0
    )

    # Find best and worst trades
    all_pnls = [float(t.realized_pnl) for t in trades]
    best_trade = max(all_pnls) if all_pnls else 0.0
    worst_trade = min(all_pnls) if all_pnls else 0.0

    # Calculate profit factor (gross wins / gross losses)
    gross_wins = sum(float(t.realized_pnl) for t in winning)
    gross_losses = abs(sum(float(t.realized_pnl) for t in losing))
    profit_factor = (
        gross_wins / gross_losses
        if gross_losses > 0
        else (float("inf") if gross_wins > 0 else 0.0)
    )

    return TradeHistoryStats(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=round(win_rate, 2),
        total_realized_pnl=round(total_pnl, 2),
        avg_win=round(avg_win, 2),
        avg_loss=round(avg_loss, 2),
        best_trade=round(best_trade, 2),
        worst_trade=round(worst_trade, 2),
        profit_factor=round(profit_factor, 2)
        if profit_factor != float("inf")
        else 999.99,
    )
