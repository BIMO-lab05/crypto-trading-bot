"""
Performance Endpoint Handlers
Extracted from main.py - Responsibility: Performance metrics endpoints

Handles performance metrics calculation and reporting.

UPDATED 2025-11-30: Fixed to calculate realized PnL from database
instead of in-memory position manager. This ensures metrics persist
across service restarts.
"""

import logging
import time
from decimal import Decimal
from fastapi import HTTPException

from app.paper_trading import get_paper_engine
from app.repositories import get_position_repository
from app.models import PerformanceResponse, PerformanceMetrics

logger = logging.getLogger(__name__)


async def get_performance() -> PerformanceResponse:
    """
    Get performance metrics with accurate realized P&L from database

    Calculates and returns:
    - Total trades (winning/losing) from database
    - Total P&L (realized from DB + unrealized from memory)
    - Win rate
    - Current vs initial balance
    - ROI (Return on Investment)

    Returns:
        PerformanceResponse with calculated metrics

    Raises:
        HTTPException: If performance calculation fails
    """
    try:
        paper_engine = get_paper_engine()
        position_repo = get_position_repository()

        # SQL aggregate over EVERY closed position. Summing a limited row query
        # truncated realized P&L, and portfolio-manager mirrors this endpoint
        # as its authoritative cash + realized P&L — a DB failure must reach
        # the caller as 500, never as zeroed metrics with success=True.
        stats = await position_repo.get_closed_pnl_stats(portfolio_id="paper_trading")

        realized_pnl = stats.realized_pnl
        winning_trades = stats.winning_trades
        losing_trades = stats.losing_trades
        total_trades = stats.total_trades
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        logger.info(
            f"Performance from DB: {total_trades} trades, realized P&L: ${realized_pnl:.2f}"
        )

        # Get unrealized P&L from memory (current open positions)
        summary = paper_engine.get_performance_summary()
        unrealized_pnl = Decimal(str(summary.get("unrealized_pnl", 0)))

        # Total P&L = realized (from DB) + unrealized (from memory)
        total_pnl = realized_pnl + unrealized_pnl

        # Calculate balance: initial + realized P&L
        initial_balance = Decimal(str(summary["initial_balance"]))
        current_balance = initial_balance + realized_pnl

        # ROI based on realized P&L
        roi = (
            float(realized_pnl / initial_balance * 100) if initial_balance > 0 else 0.0
        )

        # Create metrics object with database-accurate values
        metrics = PerformanceMetrics(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            total_pnl=total_pnl,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            win_rate=win_rate,
            current_balance=current_balance,
            initial_balance=initial_balance,
            roi=roi,
        )

        # Calculate additional metrics (avg win/loss, profit factor, etc.)
        metrics.calculate_metrics()

        return PerformanceResponse(
            success=True, metrics=metrics, timestamp=int(time.time() * 1000)
        )

    except Exception as e:
        logger.error(f"Error getting performance: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
