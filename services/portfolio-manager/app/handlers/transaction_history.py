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
from app.services.trade_history_db import fetch_transactions

logger = logging.getLogger(__name__)

_warned_no_db_pool = False


def get_portfolio_manager() -> PortfolioManager:
    """Get portfolio manager instance (from global state)"""
    from app.main import portfolio_manager

    if portfolio_manager is None:
        raise HTTPException(status_code=503, detail="Portfolio Manager not initialized")
    return portfolio_manager


def get_db_pool():
    """Get the asyncpg pool instance (from global state), or None.

    PM boots without a database by design (fail-soft) — callers must handle
    a None return by falling back to the in-memory transaction history.
    """
    from app.main import db_pool

    return db_pool


async def get_transaction_history(
    portfolio_id: str,
    limit: Optional[int] = Query(None, description="Max number of transactions to return"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
) -> TransactionHistoryResponse:
    """
    Get transaction history for a portfolio

    Returns historical record of all buy/sell transactions with:
    - Transaction details (symbol, action, quantity, price)
    - Realized P&L for SELL transactions
    - Summary statistics

    Args:
        portfolio_id: Portfolio identifier (resolved from settings.default_portfolio_id by the caller)
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

    # Get transaction history — hydrate from the shared trades table when
    # the DB pool is available (RES-09); otherwise fall back to the
    # in-memory history exactly as before (fail-soft, PM boots without a
    # database by design).
    pool = get_db_pool()
    if pool is not None:
        transactions = await fetch_transactions(
            pool, portfolio_id=portfolio_id, limit=limit, symbol=symbol
        )
    else:
        global _warned_no_db_pool
        if not _warned_no_db_pool:
            logger.warning("trades hydration unavailable (no db pool); serving in-memory history")
            _warned_no_db_pool = True
        transactions = manager.get_transaction_history(
            portfolio_id=portfolio_id, limit=limit, symbol=symbol
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
        total_realized_pnl=str(total_realized_pnl),
    )
