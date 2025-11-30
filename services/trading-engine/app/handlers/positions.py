"""
Position Endpoint Handlers
Extracted from main.py - Responsibility: Position management endpoints

Handles position querying and retrieval.

UPDATED 2025-11-28: Fetch live prices from market-data-service
- Positions now include real-time current_price from market-data-service
- unrealized_pnl is recalculated with live prices before returning

UPDATED 2025-11-30: Fixed httpx client connection issues
- Removed global client to prevent connection pool deadlocks
- Use context manager for proper connection cleanup
- Parallel fetching with asyncio.gather for better performance
"""

import logging
import time
import asyncio
import httpx
from decimal import Decimal
from typing import Dict, Tuple
from uuid import UUID
from fastapi import HTTPException

from app.position_manager import get_position_manager
from app.models import PositionListResponse, PositionResponse
from app.config import get_settings

logger = logging.getLogger(__name__)


async def fetch_single_price(
    client: httpx.AsyncClient, symbol: str, base_url: str
) -> Tuple[str, Decimal | None]:
    """
    Fetch live price for a single symbol using shared client

    Args:
        client: Shared httpx AsyncClient
        symbol: Trading symbol (e.g., 'BTCUSDT')
        base_url: Market data service base URL

    Returns:
        Tuple of (symbol, price) where price is None on error
    """
    try:
        url = f"{base_url}/api/v1/latest/{symbol}"
        response = await client.get(url)

        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("data"):
                close_price = data["data"].get("close")
                if close_price is not None:
                    logger.debug(f"Fetched live price for {symbol}: {close_price}")
                    return (symbol, Decimal(str(close_price)))
        else:
            logger.warning(f"Failed to fetch price for {symbol}: HTTP {response.status_code}")
    except (asyncio.TimeoutError, httpx.TimeoutException) as e:
        logger.warning(f"Timeout fetching price for {symbol}: {type(e).__name__}")
    except httpx.RequestError as e:
        logger.warning(f"Request error fetching price for {symbol}: {type(e).__name__}: {e}")
    except Exception as e:
        logger.warning(f"Error fetching live price for {symbol}: {type(e).__name__}: {e}")

    return (symbol, None)


async def fetch_live_prices(symbols: list[str]) -> Dict[str, Decimal]:
    """
    Fetch live prices for multiple symbols from market-data-service in parallel

    Uses a shared httpx client for efficient connection pooling.

    Args:
        symbols: List of trading symbols (e.g., ['BTCUSDT', 'ETHUSDT'])

    Returns:
        Dict mapping symbol to current price
    """
    if not symbols:
        return {}

    settings = get_settings()
    base_url = settings.market_data_url

    # Use a shared client with connection pooling for efficient parallel requests
    timeout = httpx.Timeout(15.0, connect=5.0, read=10.0)
    limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        # Fetch all prices in parallel using asyncio.gather
        tasks = [fetch_single_price(client, symbol, base_url) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    prices: Dict[str, Decimal] = {}
    for result in results:
        if isinstance(result, tuple) and result[1] is not None:
            prices[result[0]] = result[1]

    logger.info(f"Fetched {len(prices)}/{len(symbols)} live prices")
    return prices


async def get_positions(status: str = "all") -> PositionListResponse:
    """
    Get positions with optional status filter

    Args:
        status: Filter by status (all, open, closed)

    Returns:
        PositionListResponse with list of positions (with live prices!)

    Raises:
        HTTPException: If position retrieval fails
    """
    try:
        position_manager = get_position_manager()

        if status == "open":
            positions = position_manager.get_open_positions()
        elif status == "closed":
            positions = position_manager.get_closed_positions()
        else:
            positions = position_manager.get_all_positions()

        # Get unique symbols from open positions
        open_positions = [p for p in positions if p.status.value == "OPEN"]
        symbols = list(set(p.symbol for p in open_positions))

        # Fetch live prices for all symbols
        if symbols:
            live_prices = await fetch_live_prices(symbols)

            # Update each position with live price and recalculate PnL
            for position in open_positions:
                if position.symbol in live_prices:
                    current_price = live_prices[position.symbol]
                    position.update_pnl(current_price)
                    logger.debug(
                        f"Updated {position.symbol} position: "
                        f"price={current_price}, pnl={position.unrealized_pnl}"
                    )

        return PositionListResponse(
            success=True,
            positions=positions,
            count=len(positions),
            timestamp=int(time.time() * 1000)
        )

    except Exception as e:
        logger.error(f"Error getting positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_position(position_id: str) -> PositionResponse:
    """
    Get specific position by ID

    Args:
        position_id: UUID of the position

    Returns:
        PositionResponse with position details (with live price!)

    Raises:
        HTTPException: If position not found or ID invalid
    """
    try:
        position_manager = get_position_manager()
        position = position_manager.get_position(UUID(position_id))

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        # Fetch live price for this position if it's open
        if position.status.value == "OPEN":
            live_prices = await fetch_live_prices([position.symbol])
            if position.symbol in live_prices:
                position.update_pnl(live_prices[position.symbol])

        return PositionResponse(
            success=True,
            position=position,
            timestamp=int(time.time() * 1000)
        )

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid position ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting position {position_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
