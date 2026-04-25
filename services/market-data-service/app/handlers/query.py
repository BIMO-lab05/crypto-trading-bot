"""
Data Query Endpoint Handlers
Extracted from main.py - Responsibility: Query stored market data

Handles:
- Kline (candlestick) data retrieval
- Ticker data retrieval with caching
- Latest kline data retrieval with caching
"""

import re
import logging
from typing import Optional
from fastapi import HTTPException, Query, Depends, Request

from app.repository import KlineRepository, TickerRepository
from app.cache import cache_get, cache_set

logger = logging.getLogger(__name__)


def get_fetcher(request: Request):
    """Get fetcher instance from app state"""
    return request.app.state.fetcher


async def get_klines(
    symbol: str,
    interval: str = "60",
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int = Query(default=100, ge=1, le=10000)
) -> dict:
    """
    Get kline data from database

    Retrieves historical candlestick data for a trading pair
    from the database. Supports time range filtering.

    Args:
        symbol: Trading pair (e.g., BTCUSDT)
        interval: Candlestick interval (default: "60")
        start_time: Start timestamp in milliseconds (optional)
        end_time: End timestamp in milliseconds (optional)
        limit: Maximum records to return (default: 100, max: 10000)

    Returns:
        dict: Query result with kline data

    Raises:
        HTTPException: 400 if invalid symbol, 500 if query fails
    """
    try:
        # Validate inputs
        symbol = symbol.upper()
        if not re.match(r'^[A-Z]{6,20}$', symbol):
            raise HTTPException(status_code=400, detail="Invalid symbol format")

        klines = await KlineRepository.get_klines(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )

        # Convert to dict
        data = [k.to_dict() for k in klines]

        return {
            "success": True,
            "count": len(data),
            "data": data
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving klines for {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve data")


async def get_ticker(
    symbol: str,
    fetcher=Depends(get_fetcher)
) -> dict:
    """
    Get latest ticker data (with Redis caching)

    Retrieves the most recent ticker data for a trading pair.
    Uses 3-tier caching strategy: Redis cache → Database → Live fetch.

    Caching strategy:
    1. Check Redis cache (5-second TTL)
    2. If cache miss, check database
    3. If database miss, fetch live from Bybit Connector
    4. Store in database and cache for future requests

    Args:
        symbol: Trading pair (e.g., BTCUSDT)
        fetcher: Data fetcher instance (injected)

    Returns:
        dict: Ticker data with source indicator (cache/database/live)

    Raises:
        HTTPException: 400 if invalid symbol, 404 if not found, 500 if query fails
    """
    try:
        # Validate symbol
        symbol = symbol.upper()
        if not re.match(r'^[A-Z]{6,20}$', symbol):
            raise HTTPException(status_code=400, detail="Invalid symbol format")

        # Try cache first (REDUCED TTL to 2 seconds for real-time prices)
        cache_key = f"ticker:{symbol}"
        cached_data = await cache_get(cache_key)
        if cached_data:
            logger.debug(f"Cache hit for ticker {symbol}")
            return {
                "success": True,
                "data": cached_data,
                "source": "cache"
            }

        # Cache miss - try database
        ticker = await TickerRepository.get_latest_ticker(symbol)

        if not ticker:
            # Database miss - fetch fresh from Bybit Connector
            ticker_data = await fetcher.get_ticker(symbol)
            if ticker_data:
                await TickerRepository.save_ticker(ticker_data)
                # Cache for 2 seconds (REDUCED from 5s for real-time prices)
                await cache_set(cache_key, ticker_data, ttl=2)
                return {
                    "success": True,
                    "data": ticker_data,
                    "source": "live"
                }
            else:
                raise HTTPException(status_code=404, detail="Ticker not found")

        # Cache the database result for 2 seconds (REDUCED from 5s)
        ticker_dict = ticker.to_dict()
        await cache_set(cache_key, ticker_dict, ttl=2)

        return {
            "success": True,
            "data": ticker_dict,
            "source": "database"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving ticker for {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve ticker")


async def get_latest_kline(
    symbol: str,
    interval: str = "60"
) -> dict:
    """
    Get most recent kline for symbol (with Redis caching)

    Retrieves the latest candlestick data for a trading pair.
    Uses Redis caching with 60-second TTL (klines change less frequently than tickers).

    Args:
        symbol: Trading pair (e.g., BTCUSDT)
        interval: Candlestick interval (default: "60")

    Returns:
        dict: Latest kline data with source indicator

    Raises:
        HTTPException: 400 if invalid symbol, 404 if not found, 500 if query fails
    """
    try:
        # Validate symbol
        symbol = symbol.upper()
        if not re.match(r'^[A-Z]{6,20}$', symbol):
            raise HTTPException(status_code=400, detail="Invalid symbol format")

        # Try cache first
        cache_key = f"latest_kline:{symbol}:{interval}"
        cached_data = await cache_get(cache_key)
        if cached_data:
            logger.debug(f"Cache hit for latest kline {symbol} ({interval})")
            return {
                "success": True,
                "data": cached_data,
                "source": "cache"
            }

        # Cache miss - fetch from database
        kline = await KlineRepository.get_latest_kline(symbol, interval)

        if not kline:
            raise HTTPException(status_code=404, detail="No kline data found")

        # Cache for 60 seconds (klines change less frequently than tickers)
        kline_dict = kline.to_dict()
        await cache_set(cache_key, kline_dict, ttl=60)

        return {
            "success": True,
            "data": kline_dict,
            "source": "database"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving latest kline for {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve data")
