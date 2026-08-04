"""
Portfolio CRUD Endpoint Handlers
Extracted from main.py - Responsibility: Portfolio retrieval and management

Handles portfolio queries, balance information, and holdings.
"""

import logging
from decimal import Decimal
from fastapi import HTTPException

from app.models import (
    PortfolioResponse,
    PortfolioListResponse,
    BalanceResponse,
    HoldingsResponse
)
from app.services import PortfolioManager

logger = logging.getLogger(__name__)


def get_portfolio_manager() -> PortfolioManager:
    """Get portfolio manager instance (from global state)"""
    from app.main import portfolio_manager
    if portfolio_manager is None:
        raise HTTPException(status_code=503, detail="Portfolio Manager not initialized")
    return portfolio_manager


async def get_portfolio(portfolio_id: str = "default") -> PortfolioResponse:
    """
    Get portfolio details

    Fetches complete portfolio snapshot including:
    - Portfolio metadata
    - All holdings
    - Current market values
    - P&L calculations

    Args:
        portfolio_id: Portfolio identifier (default: "default")

    Returns:
        PortfolioResponse with snapshot data

    Raises:
        HTTPException: 404 if portfolio not found
    """
    manager = get_portfolio_manager()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

    # FIX 2026-07-29: mirror the authoritative trading-engine book before
    # returning, rather than the old update_prices() path. update_prices
    # recomputed equity with a SPOT formula (cash + full notional) and depended
    # on a flaky market-data ticker fetch that, when it returned 0, collapsed
    # total_value to cash alone — producing the phantom -84% return. sync pulls
    # correct side-aware P&L, cash, and equity straight from the engine.
    synced = await manager.sync_with_trading_engine(portfolio_id)
    if not synced:
        # Best-effort fallback: refresh prices locally so we still return
        # something rather than erroring the dashboard.
        await manager.update_prices(portfolio_id)

    snapshot = manager.get_snapshot(portfolio_id)

    return PortfolioResponse(
        success=True,
        portfolio=snapshot,
        message="Portfolio retrieved successfully"
    )


async def list_portfolios() -> PortfolioListResponse:
    """
    List all portfolios

    Returns list of all portfolio snapshots managed by this service.

    Returns:
        PortfolioListResponse with list of portfolios
    """
    manager = get_portfolio_manager()

    snapshots = []
    for portfolio in manager.list_portfolios():
        snapshot = manager.get_snapshot(portfolio.portfolio_id)
        if snapshot:
            snapshots.append(snapshot)

    return PortfolioListResponse(
        success=True,
        portfolios=snapshots,
        count=len(snapshots)
    )


async def get_balance(portfolio_id: str = "default") -> BalanceResponse:
    """
    Get portfolio balance information

    Returns financial summary:
    - Cash balance
    - Total portfolio value
    - Unrealized P&L (open positions)
    - Realized P&L (closed positions)
    - Total P&L
    - Total return percentage

    Args:
        portfolio_id: Portfolio identifier (default: "default")

    Returns:
        BalanceResponse with balance data

    Raises:
        HTTPException: 404 if portfolio not found
    """
    manager = get_portfolio_manager()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

    # Update prices
    await manager.update_prices(portfolio_id)

    return BalanceResponse(
        success=True,
        portfolio_id=portfolio.portfolio_id,
        cash_balance=str(portfolio.cash_balance),
        total_value=str(portfolio.total_value),
        unrealized_pnl=str(portfolio.unrealized_pnl),
        realized_pnl=str(portfolio.realized_pnl),
        total_pnl=str(portfolio.total_pnl),
        total_return_pct=str(portfolio.total_return_pct)
    )


async def get_holdings(portfolio_id: str = "default") -> HoldingsResponse:
    """
    Get portfolio holdings

    Returns detailed list of all holdings:
    - Symbol
    - Quantity
    - Average cost
    - Current price
    - Current value
    - Unrealized P&L
    - Allocation percentage

    Args:
        portfolio_id: Portfolio identifier (default: "default")

    Returns:
        HoldingsResponse with holdings list

    Raises:
        HTTPException: 404 if portfolio not found
    """
    manager = get_portfolio_manager()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

    # Update prices
    await manager.update_prices(portfolio_id)

    snapshot = manager.get_snapshot(portfolio_id)

    total_value = sum(Decimal(h.current_value) for h in snapshot.holdings)

    return HoldingsResponse(
        success=True,
        portfolio_id=portfolio_id,
        holdings=snapshot.holdings,
        total_value=str(total_value),
        count=len(snapshot.holdings)
    )


async def sync_with_trading_engine(portfolio_id: str = "default"):
    """
    Sync portfolio with Trading Engine positions

    Updates portfolio holdings to match actual positions
    in the Trading Engine service.

    Args:
        portfolio_id: Portfolio identifier (default: "default")

    Returns:
        Dict with success status

    Raises:
        HTTPException: 404 if portfolio not found, 500 if sync fails
    """
    manager = get_portfolio_manager()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

    success = await manager.sync_with_trading_engine(portfolio_id)

    if success:
        return {"success": True, "message": "Portfolio synced successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to sync with Trading Engine")
