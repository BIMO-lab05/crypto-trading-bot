"""
Allocation Endpoint Handlers
Extracted from main.py - Responsibility: Portfolio allocation and rebalancing

Handles asset allocation queries and rebalancing recommendations.
"""

import logging
from decimal import Decimal
from fastapi import HTTPException

from app.models import AllocationResponse, RebalanceResponse
from app.services import PortfolioManager

logger = logging.getLogger(__name__)


def get_portfolio_manager() -> PortfolioManager:
    """Get portfolio manager instance (from global state)"""
    from app.main import portfolio_manager

    if portfolio_manager is None:
        raise HTTPException(status_code=503, detail="Portfolio Manager not initialized")
    return portfolio_manager


async def get_allocation(portfolio_id: str) -> AllocationResponse:
    """
    Get portfolio allocation

    Returns current asset allocation as percentages:
    - Symbol → Allocation percentage
    - Whether rebalancing is recommended
    - Target allocation (if defined)

    Checks if portfolio drift exceeds threshold and needs rebalancing.

    Args:
        portfolio_id: Portfolio identifier (resolved from settings.default_portfolio_id by the caller)

    Returns:
        AllocationResponse with allocation data

    Raises:
        HTTPException: 404 if portfolio not found
    """
    manager = get_portfolio_manager()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(
            status_code=404, detail=f"Portfolio {portfolio_id} not found"
        )

    # Sync-first (same pattern as portfolio.get_portfolio): update_prices
    # recomputes equity with a SPOT formula (cash + full notional) and must
    # only run as fallback, or it clobbers the engine-mirrored equity.
    synced = await manager.sync_with_trading_engine(portfolio_id)
    if not synced:
        await manager.update_prices(portfolio_id)

    allocations = portfolio.get_asset_allocation()
    allocations_str = {k: str(v) for k, v in allocations.items()}

    needs_rebalancing, _ = manager.check_rebalancing_needed(portfolio_id)

    return AllocationResponse(
        success=True,
        portfolio_id=portfolio_id,
        allocations=allocations_str,
        needs_rebalancing=needs_rebalancing,
    )


async def get_rebalance_recommendations(
    portfolio_id: str,
) -> RebalanceResponse:
    """
    Get rebalancing recommendations

    Calculates required trades to bring portfolio back to target allocation:
    - Identifies assets that need buying/selling
    - Calculates quantities for each trade
    - Estimates trading costs
    - Provides total cost estimate

    Args:
        portfolio_id: Portfolio identifier (resolved from settings.default_portfolio_id by the caller)

    Returns:
        RebalanceResponse with trade recommendations

    Raises:
        HTTPException: 404 if portfolio not found
    """
    manager = get_portfolio_manager()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(
            status_code=404, detail=f"Portfolio {portfolio_id} not found"
        )

    # Sync-first (same pattern as portfolio.get_portfolio): update_prices
    # recomputes equity with a SPOT formula (cash + full notional) and must
    # only run as fallback, or it clobbers the engine-mirrored equity.
    synced = await manager.sync_with_trading_engine(portfolio_id)
    if not synced:
        await manager.update_prices(portfolio_id)

    needs_rebalancing, recommendations = manager.check_rebalancing_needed(portfolio_id)

    total_cost = sum(Decimal(r.estimated_cost) for r in recommendations)

    return RebalanceResponse(
        success=True,
        portfolio_id=portfolio_id,
        needs_rebalancing=needs_rebalancing,
        recommendations=recommendations,
        total_transactions=len(recommendations),
        estimated_total_cost=str(total_cost),
    )
