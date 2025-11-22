"""
Data Collection Endpoint Handlers
Extracted from main.py - Responsibility: Historical and real-time data collection

Handles:
- Kline (candlestick) data collection
- Ticker data collection
- Bulk data collection for multiple symbols
"""

import re
import logging
from typing import Optional, List
from fastapi import HTTPException, Request, Query, Depends

from app.config import get_settings
from app.repository import KlineRepository, TickerRepository
from app.auth import verify_api_key
from app.utils.metrics import (
    data_collection_total,
    data_records_stored,
    bybit_connector_calls_total,
    database_operations_total
)

logger = logging.getLogger(__name__)


def get_fetcher(request: Request):
    """Get fetcher instance from app state"""
    return request.app.state.fetcher


async def collect_kline_data(
    symbol: str,
    interval: str = "60",
    days: int = Query(default=7, ge=1, le=30),
    fetcher=Depends(get_fetcher),
    api_key: str = Depends(verify_api_key)
) -> dict:
    """
    Fetch and store historical kline data

    Fetches candlestick data from Bybit Connector and stores it in the database.
    Supports historical data collection up to 30 days.

    Args:
        symbol: Trading pair (e.g., BTCUSDT)
        interval: Candlestick interval (default: "60" for 1 hour)
        days: Number of days to fetch (max 30)
        fetcher: Data fetcher instance (injected)
        api_key: API key for authentication (injected)

    Returns:
        dict: Collection result with success status and count

    Raises:
        HTTPException: 400 if invalid symbol, 500 if collection fails
    """
    try:
        # Validate symbol
        symbol = symbol.upper()
        if not re.match(r'^[A-Z]{6,20}$', symbol):
            raise HTTPException(status_code=400, detail="Invalid symbol format")

        logger.info(f"Collecting {days} days of {symbol} klines ({interval})")

        # Track metric
        bybit_connector_calls_total.labels(endpoint='kline', status='attempt').inc()

        # Fetch data from Bybit Connector
        klines = await fetcher.get_historical_klines(
            symbol=symbol,
            interval=interval,
            days=days
        )

        if not klines:
            data_collection_total.labels(symbol=symbol, data_type='kline', status='no_data').inc()
            return {"success": False, "message": "No data fetched", "count": 0}

        bybit_connector_calls_total.labels(endpoint='kline', status='success').inc()

        # Add symbol and interval to each kline
        for k in klines:
            k['symbol'] = symbol
            k['interval'] = interval

        # Store in database
        database_operations_total.labels(operation='bulk_upsert', status='attempt').inc()
        count = await KlineRepository.bulk_upsert(klines)
        database_operations_total.labels(operation='bulk_upsert', status='success').inc()

        # Track metrics
        data_collection_total.labels(symbol=symbol, data_type='kline', status='success').inc()
        data_records_stored.labels(symbol=symbol, data_type='kline').inc(count)

        return {
            "success": True,
            "message": f"Collected and stored {count} klines",
            "symbol": symbol,
            "interval": interval,
            "count": count
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error collecting kline data for {symbol}: {e}")
        data_collection_total.labels(symbol=symbol, data_type='kline', status='error').inc()
        bybit_connector_calls_total.labels(endpoint='kline', status='error').inc()
        raise HTTPException(status_code=500, detail="Failed to collect data")


async def collect_ticker_data(
    symbol: str,
    fetcher=Depends(get_fetcher),
    api_key: str = Depends(verify_api_key)
) -> dict:
    """
    Fetch and store current ticker data

    Fetches real-time ticker data (price, volume, etc.) from Bybit Connector
    and stores it in the database.

    Args:
        symbol: Trading pair (e.g., BTCUSDT)
        fetcher: Data fetcher instance (injected)
        api_key: API key for authentication (injected)

    Returns:
        dict: Collection result with ticker data

    Raises:
        HTTPException: 400 if invalid symbol, 500 if collection fails
    """
    try:
        # Validate symbol
        symbol = symbol.upper()
        if not re.match(r'^[A-Z]{6,20}$', symbol):
            raise HTTPException(status_code=400, detail="Invalid symbol format")

        # Fetch ticker
        ticker = await fetcher.get_ticker(symbol)

        if not ticker:
            data_collection_total.labels(symbol=symbol, data_type='ticker', status='no_data').inc()
            return {"success": False, "message": "No ticker data available"}

        # Store in database
        await TickerRepository.save_ticker(ticker)

        # Track metrics
        data_collection_total.labels(symbol=symbol, data_type='ticker', status='success').inc()
        data_records_stored.labels(symbol=symbol, data_type='ticker').inc()

        return {
            "success": True,
            "message": "Ticker data saved",
            "data": ticker
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error collecting ticker for {symbol}: {e}")
        data_collection_total.labels(symbol=symbol, data_type='ticker', status='error').inc()
        raise HTTPException(status_code=500, detail="Failed to collect ticker")


async def collect_bulk_data(
    symbols: Optional[List[str]] = None,
    interval: str = "60",
    days: int = Query(default=7, ge=1, le=30),
    fetcher=Depends(get_fetcher),
    api_key: str = Depends(verify_api_key)
) -> dict:
    """
    Collect data for multiple symbols (max 10)

    Fetches and stores kline data for multiple trading pairs in a single request.
    Limits to 10 symbols per request to prevent abuse.

    Args:
        symbols: List of trading pairs (defaults to config symbols, max 10)
        interval: Candlestick interval (default: "60")
        days: Number of days to fetch (max 30)
        fetcher: Data fetcher instance (injected)
        api_key: API key for authentication (injected)

    Returns:
        dict: Bulk collection results with per-symbol status

    Raises:
        HTTPException: 400 if too many symbols requested
    """
    settings = get_settings()
    target_symbols = symbols or settings.symbols_list

    # Enforce maximum symbols limit
    MAX_SYMBOLS = 10
    if len(target_symbols) > MAX_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_SYMBOLS} symbols allowed per request"
        )

    results = []

    for symbol in target_symbols:
        try:
            symbol = symbol.upper()

            # Fetch klines
            klines = await fetcher.get_historical_klines(
                symbol=symbol,
                interval=interval,
                days=days
            )

            if klines:
                # Add metadata
                for k in klines:
                    k['symbol'] = symbol
                    k['interval'] = interval

                # Store
                count = await KlineRepository.bulk_upsert(klines)
                results.append({
                    "symbol": symbol,
                    "success": True,
                    "count": count
                })

                # Track metrics
                data_collection_total.labels(symbol=symbol, data_type='kline', status='success').inc()
                data_records_stored.labels(symbol=symbol, data_type='kline').inc(count)
            else:
                results.append({
                    "symbol": symbol,
                    "success": False,
                    "error": "No data fetched"
                })

        except Exception as e:
            logger.error(f"Error collecting data for {symbol}: {e}")
            results.append({
                "symbol": symbol,
                "success": False,
                "error": str(e)
            })

    return {
        "success": True,
        "results": results,
        "total_symbols": len(target_symbols),
        "successful": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"])
    }
