"""
Transaction Endpoint Handlers
Extracted from main.py - Responsibility: Buy and sell transaction execution

Handles asset buying and selling with price fetching, validation,
and rate limiting.
"""

import logging
import uuid
from typing import Optional
from fastapi import HTTPException, Request, Query

from app.models import TransactionResponse
from app.services import PortfolioManager
from app.config import settings
from app.utils import check_rate_limit, parse_decimal

logger = logging.getLogger(__name__)

# FIX 11 (2026-08-12): the portfolio is a read-only mirror of the
# trading-engine book — the engine sync overwrites local state within 60s,
# so a manual fill here is fake and guaranteed to drift before vanishing.
# Mutating spot paths are gated off; transaction history stays readable.
MANUAL_TRANSACTIONS_DISABLED_DETAIL = (
    "manual spot transactions disabled: portfolio mirrors the trading-engine "
    "book; local trades are overwritten by sync within 60s"
)


def get_portfolio_manager() -> PortfolioManager:
    """Get portfolio manager instance (from global state)"""
    from app.main import portfolio_manager

    if portfolio_manager is None:
        raise HTTPException(status_code=503, detail="Portfolio Manager not initialized")
    return portfolio_manager


async def buy_asset(
    request: Request,
    portfolio_id: str = "default",
    symbol: str = Query(..., description="Asset symbol"),
    quantity: str = Query(..., description="Quantity to buy"),
    price: Optional[str] = Query(None, description="Price (fetch if not provided)"),
) -> TransactionResponse:
    """
    Execute buy transaction

    Purchases specified quantity of an asset at current market price
    (or specified price). Updates portfolio holdings and cash balance.

    Process:
    1. Validate inputs and check rate limit
    2. Fetch current price (if not provided)
    3. Calculate total cost
    4. Check sufficient cash balance
    5. Execute transaction
    6. Update portfolio

    Args:
        request: FastAPI request (for rate limiting)
        portfolio_id: Portfolio identifier (default: "default")
        symbol: Asset symbol (e.g., "BTCUSDT")
        quantity: Quantity to purchase
        price: Price per unit (optional, fetched if not provided)

    Returns:
        TransactionResponse with transaction details

    Raises:
        HTTPException: 409 always — manual spot transactions are disabled
                      (portfolio mirrors the trading-engine book)
    """
    raise HTTPException(status_code=409, detail=MANUAL_TRANSACTIONS_DISABLED_DETAIL)

    # Check rate limit
    check_rate_limit(request, settings.rate_limit_transactions_per_minute)

    manager = get_portfolio_manager()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(
            status_code=404, detail=f"Portfolio {portfolio_id} not found"
        )

    # Validate quantity
    qty = parse_decimal(quantity, "quantity")

    # Serialize the price-fetch + execute window per portfolio so a concurrent
    # SELL/BUY can't interleave around the await and overdraw the cash balance.
    async with manager.get_transaction_lock(portfolio_id):
        # Get price if not provided
        if price is None:
            current_price = await manager._fetch_current_price(symbol)
            if current_price == 0:
                raise HTTPException(
                    status_code=503,
                    detail=f"Could not fetch current price for {symbol}. Market Data service may be unavailable.",
                )
        else:
            current_price = parse_decimal(price, "price")

        # Execute transaction
        success, message, _ = manager.execute_transaction(
            portfolio_id=portfolio_id,
            symbol=symbol,
            action="BUY",
            quantity=qty,
            price=current_price,
        )

    if not success:
        raise HTTPException(status_code=400, detail=message)

    total_cost = qty * current_price

    return TransactionResponse(
        success=True,
        transaction_id=str(uuid.uuid4()),
        symbol=symbol,
        action="BUY",
        quantity=str(qty),
        price=str(current_price),
        total_cost=str(total_cost),
        message=message,
    )


async def sell_asset(
    request: Request,
    portfolio_id: str = "default",
    symbol: str = Query(..., description="Asset symbol"),
    quantity: str = Query(..., description="Quantity to sell"),
    price: Optional[str] = Query(None, description="Price (fetch if not provided)"),
) -> TransactionResponse:
    """
    Execute sell transaction

    Sells specified quantity of an asset at current market price
    (or specified price). Updates portfolio holdings, cash balance,
    and calculates realized P&L.

    Process:
    1. Validate inputs and check rate limit
    2. Fetch current price (if not provided)
    3. Check sufficient holdings
    4. Execute transaction
    5. Calculate realized P&L
    6. Update portfolio

    Args:
        request: FastAPI request (for rate limiting)
        portfolio_id: Portfolio identifier (default: "default")
        symbol: Asset symbol (e.g., "BTCUSDT")
        quantity: Quantity to sell
        price: Price per unit (optional, fetched if not provided)

    Returns:
        TransactionResponse with transaction details and realized P&L

    Raises:
        HTTPException: 409 always — manual spot transactions are disabled
                      (portfolio mirrors the trading-engine book)
    """
    raise HTTPException(status_code=409, detail=MANUAL_TRANSACTIONS_DISABLED_DETAIL)

    # Check rate limit
    check_rate_limit(request, settings.rate_limit_transactions_per_minute)

    manager = get_portfolio_manager()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(
            status_code=404, detail=f"Portfolio {portfolio_id} not found"
        )

    # Validate quantity
    qty = parse_decimal(quantity, "quantity")

    # Serialize the price-fetch + execute window per portfolio so a concurrent
    # BUY/SELL can't interleave around the await and corrupt holdings/cash.
    async with manager.get_transaction_lock(portfolio_id):
        # Get price if not provided
        if price is None:
            current_price = await manager._fetch_current_price(symbol)
            if current_price == 0:
                raise HTTPException(
                    status_code=503,
                    detail=f"Could not fetch current price for {symbol}. Market Data service may be unavailable.",
                )
        else:
            current_price = parse_decimal(price, "price")

        # Execute transaction
        success, message, realized_pnl = manager.execute_transaction(
            portfolio_id=portfolio_id,
            symbol=symbol,
            action="SELL",
            quantity=qty,
            price=current_price,
        )

    if not success:
        raise HTTPException(status_code=400, detail=message)

    total_proceeds = qty * current_price

    return TransactionResponse(
        success=True,
        transaction_id=str(uuid.uuid4()),
        symbol=symbol,
        action="SELL",
        quantity=str(qty),
        price=str(current_price),
        total_cost=str(total_proceeds),
        realized_pnl=str(realized_pnl) if realized_pnl else None,
        message=message,
    )
