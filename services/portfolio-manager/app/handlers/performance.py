"""
Performance Endpoint Handlers
Extracted from main.py - Responsibility: Performance metrics calculation and reporting

Handles performance analysis and asset-level performance queries.
Enhanced with historical performance tracking.
"""

import logging
from fastapi import HTTPException

from app.models import PerformanceResponse, AssetPerformanceResponse
from app.services import PortfolioManager, PerformanceCalculator

logger = logging.getLogger(__name__)


def get_portfolio_manager() -> PortfolioManager:
    """Get portfolio manager instance (from global state)"""
    from app.main import portfolio_manager
    if portfolio_manager is None:
        raise HTTPException(status_code=503, detail="Portfolio Manager not initialized")
    return portfolio_manager


def get_performance_calculator() -> PerformanceCalculator:
    """Get performance calculator instance (from global state)"""
    from app.main import performance_calculator
    if performance_calculator is None:
        raise HTTPException(status_code=503, detail="Performance Calculator not initialized")
    return performance_calculator


def get_performance_history():
    """Get performance history service instance (from global state)"""
    from app.main import performance_history
    if performance_history is None:
        raise HTTPException(status_code=503, detail="Performance History not initialized")
    return performance_history


async def get_performance(
    portfolio_id: str = "default",
    include_daily: bool = False,
    include_periods: bool = False
) -> PerformanceResponse:
    """
    Get portfolio performance metrics

    Calculates comprehensive performance metrics:
    - Total return (absolute and percentage)
    - Realized P&L
    - Unrealized P&L
    - Sharpe ratio (if historical data available)
    - Win rate
    - Average win/loss
    - Max drawdown

    Optional:
    - Daily performance history (if include_daily=True)
    - Period performance (week, month, year) (if include_periods=True)

    Args:
        portfolio_id: Portfolio identifier (default: "default")
        include_daily: Include daily performance history
        include_periods: Include period performance stats

    Returns:
        PerformanceResponse with metrics

    Raises:
        HTTPException: 404 if portfolio not found
    """
    manager = get_portfolio_manager()
    calculator = get_performance_calculator()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

    # Update prices
    await manager.update_prices(portfolio_id)

    # Calculate metrics
    metrics = calculator.calculate_metrics(portfolio)

    # Optional: Add daily and period performance
    daily_performance = None
    period_performance = None

    # IMPLEMENTED: Historical tracking for daily/period performance
    try:
        history_service = get_performance_history()

        # Get daily performance history if requested
        if include_daily:
            logger.info(f"Fetching daily performance for {portfolio_id}")
            daily_performance = await history_service.get_daily_performance(
                portfolio_id,
                days=30  # Default to last 30 days
            )
            logger.info(
                f"Retrieved {len(daily_performance) if daily_performance else 0} "
                f"daily records for {portfolio_id}"
            )

        # Get period performance stats if requested
        if include_periods:
            logger.info(f"Calculating period performance for {portfolio_id}")
            period_performance = {}

            # Calculate performance for each period
            for period_name in ['week', 'month', 'year', 'all']:
                period_stats = await history_service.calculate_period_performance(
                    portfolio_id,
                    period_name
                )

                if period_stats:
                    period_performance[period_name] = period_stats
                    logger.debug(
                        f"{period_name} performance: "
                        f"return={period_stats.total_return_pct}%"
                    )
                else:
                    logger.warning(
                        f"No data available for {period_name} period "
                        f"for portfolio {portfolio_id}"
                    )

            logger.info(
                f"Calculated {len(period_performance)} period stats "
                f"for {portfolio_id}"
            )

    except HTTPException:
        # Re-raise HTTP exceptions (service not initialized)
        raise
    except Exception as e:
        # Log error but don't fail the request - historical data is optional
        logger.error(
            f"Failed to retrieve historical performance for {portfolio_id}: {e}",
            exc_info=True
        )
        # Return empty historical data rather than failing
        if include_daily:
            daily_performance = []
        if include_periods:
            period_performance = {}

    return PerformanceResponse(
        success=True,
        portfolio_id=portfolio_id,
        metrics=metrics,
        daily_performance=daily_performance,
        period_performance=period_performance
    )


async def get_asset_performance(portfolio_id: str = "default") -> AssetPerformanceResponse:
    """
    Get performance by asset

    Returns performance breakdown for each asset in the portfolio:
    - Symbol
    - Quantity
    - Average cost
    - Current price
    - Market value
    - Unrealized P&L
    - Return percentage
    - Allocation percentage

    Args:
        portfolio_id: Portfolio identifier (default: "default")

    Returns:
        AssetPerformanceResponse with per-asset metrics

    Raises:
        HTTPException: 404 if portfolio not found
    """
    manager = get_portfolio_manager()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

    # Update prices
    await manager.update_prices(portfolio_id)

    assets = manager.get_asset_performance(portfolio_id)

    return AssetPerformanceResponse(
        success=True,
        portfolio_id=portfolio_id,
        assets=assets
    )
