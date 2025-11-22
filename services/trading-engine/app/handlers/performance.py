"""
Performance Endpoint Handlers
Extracted from main.py - Responsibility: Performance metrics endpoints

Handles performance metrics calculation and reporting.
"""

import logging
import time
from decimal import Decimal
from fastapi import HTTPException

from app.paper_trading import get_paper_engine
from app.models import PerformanceResponse, PerformanceMetrics

logger = logging.getLogger(__name__)


async def get_performance() -> PerformanceResponse:
    """
    Get performance metrics

    Calculates and returns:
    - Total trades (winning/losing)
    - Total P&L
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
        summary = paper_engine.get_performance_summary()

        # Create metrics object
        metrics = PerformanceMetrics(
            total_trades=summary["total_trades"],
            winning_trades=summary["winning_trades"],
            losing_trades=summary["losing_trades"],
            total_pnl=Decimal(str(summary["total_pnl"])),
            win_rate=summary["win_rate"],
            current_balance=Decimal(str(summary["current_balance"])),
            initial_balance=Decimal(str(summary["initial_balance"])),
            roi=summary["roi"]
        )

        # Calculate additional metrics
        metrics.calculate_metrics()

        return PerformanceResponse(
            success=True,
            metrics=metrics,
            timestamp=int(time.time() * 1000)
        )

    except Exception as e:
        logger.error(f"Error getting performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))
