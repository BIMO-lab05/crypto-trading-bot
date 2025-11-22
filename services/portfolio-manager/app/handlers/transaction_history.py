"""
Transaction History Endpoint Handler
Handles retrieval of transaction history for portfolios
"""

import logging
from decimal import Decimal
from typing import Optional
from fastapi import HTTPException, Query

from app.models.transaction import TransactionHistoryResponse
from app.services import PortfolioManager

logger = logging.getLogger(__name__)


def get_portfolio_manager() -> PortfolioManager:
    """Get portfolio manager instance (from global state)"""
    from app.main import portfolio_manager
    if portfolio_manager is None:
        raise HTTPException(status_code=503, detail="Portfolio Manager not initialized")
    return portfolio_manager


async def get_transaction_history(
    portfolio_id: str = "default",
    limit: Optional[int] = Query(None, description="Max number of transactions to return"),
    symbol: Optional[str] = Query(None, description="Filter by symbol")
) -> TransactionHistoryResponse:
    """
    Get transaction history for a portfolio

    Returns historical record of all buy/sell transactions with:
    - Transaction details (symbol, action, quantity, price)
    - Realized P&L for SELL transactions
    - Summary statistics

    Args:
        portfolio_id: Portfolio identifier (default: "default")
        limit: Maximum number of transactions (most recent first)
        symbol: Filter by specific asset symbol

    Returns:
        TransactionHistoryResponse with transaction list and statistics

    Raises:
        HTTPException: 404 if portfolio not found
    """
    manager = get_portfolio_manager()

    # Verify portfolio exists
    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

    # Get transaction history
    transactions = manager.get_transaction_history(
        portfolio_id=portfolio_id,
        limit=limit,
        symbol=symbol
    )

    # Calculate summary statistics
    total_buy_volume = Decimal("0")
    total_sell_volume = Decimal("0")
    total_realized_pnl = Decimal("0")

    for txn in transactions:
        amount = Decimal(txn.total_amount)

        if txn.action == "BUY":
            total_buy_volume += amount
        elif txn.action == "SELL":
            total_sell_volume += amount
            if txn.realized_pnl:
                total_realized_pnl += Decimal(txn.realized_pnl)

    logger.info(
        f"Retrieved {len(transactions)} transactions for portfolio {portfolio_id}"
        + (f" (symbol: {symbol})" if symbol else "")
    )

    return TransactionHistoryResponse(
        success=True,
        portfolio_id=portfolio_id,
        transactions=transactions,
        total_count=len(transactions),
        total_buy_volume=str(total_buy_volume),
        total_sell_volume=str(total_sell_volume),
        total_realized_pnl=str(total_realized_pnl)
    )
