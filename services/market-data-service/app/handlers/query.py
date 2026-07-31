"""
Data Query Endpoint Handlers
Extracted from main.py - Responsibility: Query stored market data

Handles:
- Kline (candlestick) data retrieval
- Ticker data retrieval with caching
- Latest kline data retrieval with caching
"""

import re
import time
import logging
from typing import Optional, Tuple
from fastapi import HTTPException, Query, Depends, Request

from app.repository import KlineRepository, TickerRepository
from app.cache import cache_get, cache_set
from app.config import get_settings

logger = logging.getLogger(__name__)


def ticker_age_seconds(ticker_dict: dict) -> Optional[float]:
    """
    Age of a stored ticker row in seconds, or None if it carries no usable
    timestamp. `timestamp` and `created_at` are epoch milliseconds.
    """
    raw = ticker_dict.get("timestamp") or ticker_dict.get("created_at")
    if raw in (None, ""):
        return None
    try:
        return max(0.0, time.time() - (float(raw) / 1000.0))
    except (TypeError, ValueError):
        return None


def assess_freshness(ticker_dict: dict) -> Tuple[Optional[float], bool]:
    """
    Return (age_seconds, is_stale).

    A row with no usable timestamp is treated as stale: we cannot prove it is
    current, and the whole point of this guard is to stop presenting unproven
    data as fact.
    """
    age = ticker_age_seconds(ticker_dict)
    if age is None:
        return None, True
    return age, age > get_settings().market_data_staleness_seconds


# Valid Bybit V5 kline intervals. Reject anything else up front so a bad
# `interval` doesn't silently return an empty series (which downstream
# consumers can misread as "no data available" rather than "bad request").
VALID_INTERVALS = {
    "1",
    "3",
    "5",
    "15",
    "30",
    "60",
    "120",
    "240",
    "360",
    "720",
    "D",
    "W",
    "M",
}


def _validate_interval(interval: str) -> None:
    if interval not in VALID_INTERVALS:
        raise HTTPException(status_code=400, detail="Invalid interval")


def get_fetcher(request: Request):
    """Get fetcher instance from app state"""
    return request.app.state.fetcher


async def get_klines(
    symbol: str,
    interval: str = "60",
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int = Query(default=100, ge=1, le=10000),
    mainnet_only: bool = Query(default=True),
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
        mainnet_only: If True (default), exclude rows tagged from
            Bybit testnet. Default-True is the audit-aligned safe
            behaviour after the 2026-04-25 testnet→mainnet flip left
            mixed history in the table.

    Returns:
        dict: Query result with kline data

    Raises:
        HTTPException: 400 if invalid symbol, 500 if query fails
    """
    try:
        # Validate inputs
        symbol = symbol.upper()
        if not re.match(r"^[A-Z]{6,20}$", symbol):
            raise HTTPException(status_code=400, detail="Invalid symbol format")
        _validate_interval(interval)

        klines = await KlineRepository.get_klines(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            mainnet_only=mainnet_only,
        )

        # Convert to dict
        data = [k.to_dict() for k in klines]

        return {"success": True, "count": len(data), "data": data}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving klines for {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve data")


async def get_ticker(symbol: str, fetcher=Depends(get_fetcher)) -> dict:
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
        if not re.match(r"^[A-Z]{6,20}$", symbol):
            raise HTTPException(status_code=400, detail="Invalid symbol format")

        # Try cache first (REDUCED TTL to 2 seconds for real-time prices)
        cache_key = f"ticker:{symbol}"
        cached_data = await cache_get(cache_key)
        if cached_data:
            logger.debug(f"Cache hit for ticker {symbol}")
            return {"success": True, "data": cached_data, "source": "cache"}

        # Cache miss - try database
        ticker = await TickerRepository.get_latest_ticker(symbol)

        stored_dict = ticker.to_dict() if ticker else None
        stored_age, stored_is_stale = (
            assess_freshness(stored_dict) if stored_dict else (None, True)
        )

        # A stored row that is too old is treated as a MISS, not a hit.
        #
        # Previously the live-fetch fallback below fired only when there was no
        # row at all, so any row -- however ancient -- short-circuited it. That
        # made a stale row a poison pill: both the wrong answer and the reason
        # the right answer was never fetched. When ingest stalled for 17 hours
        # (audit DL-1) every read kept returning the same 17-hour-old price as
        # current. Falling through here means that outage self-heals on the
        # first read instead of persisting until someone notices.
        if stored_dict is None or stored_is_stale:
            if stored_dict is not None:
                budget = get_settings().market_data_staleness_seconds
                reason = (
                    f"age={stored_age:.0f}s exceeds budget={budget}s"
                    if stored_age is not None
                    else "row carries no usable timestamp"
                )
                logger.warning(
                    f"Stored ticker for {symbol} rejected as stale "
                    f"({reason}); re-fetching live"
                )

            ticker_data = await fetcher.get_ticker(symbol)
            if ticker_data:
                await TickerRepository.save_ticker(ticker_data)
                # Cache for 2 seconds (REDUCED from 5s for real-time prices)
                await cache_set(cache_key, ticker_data, ttl=2)
                live_age, live_is_stale = assess_freshness(ticker_data)
                return {
                    "success": True,
                    "data": ticker_data,
                    "source": "live",
                    "age_seconds": live_age,
                    "is_stale": live_is_stale,
                }

            if stored_dict is None:
                raise HTTPException(status_code=404, detail="Ticker not found")

            # Live fetch failed and all we have is a stale row. Serve it rather
            # than 500 -- but never silently: the caller is told exactly how old
            # it is, and the operator gets an ERROR.
            logger.error(
                f"Serving STALE ticker for {symbol}: live re-fetch failed and "
                f"stored row is {stored_age if stored_age is not None else '?'}s old"
            )
            return {
                "success": True,
                "data": stored_dict,
                "source": "database",
                "age_seconds": stored_age,
                "is_stale": True,
            }

        # Cache the database result for 2 seconds (REDUCED from 5s)
        await cache_set(cache_key, stored_dict, ttl=2)

        return {
            "success": True,
            "data": stored_dict,
            "source": "database",
            "age_seconds": stored_age,
            "is_stale": False,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving ticker for {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve ticker")


async def get_latest_kline(symbol: str, interval: str = "60") -> dict:
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
        if not re.match(r"^[A-Z]{6,20}$", symbol):
            raise HTTPException(status_code=400, detail="Invalid symbol format")
        _validate_interval(interval)

        # Try cache first
        cache_key = f"latest_kline:{symbol}:{interval}"
        cached_data = await cache_get(cache_key)
        if cached_data:
            logger.debug(f"Cache hit for latest kline {symbol} ({interval})")
            return {"success": True, "data": cached_data, "source": "cache"}

        # Cache miss - fetch from database
        kline = await KlineRepository.get_latest_kline(symbol, interval)

        if not kline:
            raise HTTPException(status_code=404, detail="No kline data found")

        # Cache for 60 seconds (klines change less frequently than tickers)
        kline_dict = kline.to_dict()
        await cache_set(cache_key, kline_dict, ttl=60)

        return {"success": True, "data": kline_dict, "source": "database"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving latest kline for {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve data")
