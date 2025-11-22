"""
Utility Helper Functions
Extracted from main.py - Responsibility: Common utilities and validation

Contains:
- Service health checking with retry logic
- Rate limiting (sliding window)
- Decimal validation for financial calculations
- Historical price fetching from Market Data Service
"""

import logging
import time
import asyncio
import httpx
import pandas as pd
from decimal import Decimal, InvalidOperation
from collections import defaultdict, deque
from typing import List, Dict
from datetime import datetime, timedelta
from fastapi import HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)

# In-memory rate limiter storage (for production, use Redis)
rate_limiter_storage: Dict[str, deque] = defaultdict(deque)


async def check_service_health(url: str) -> bool:
    """
    Check if external service is healthy with retry logic

    Args:
        url: Service base URL

    Returns:
        bool: True if service is healthy, False otherwise
    """
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
                response = await client.get(f"{url}/health")
                if response.status_code == 200:
                    return True
        except httpx.TimeoutException:
            logger.warning(f"Health check timeout for {url} (attempt {attempt + 1}/3)")
        except httpx.ConnectError:
            logger.warning(f"Connection error for {url} (attempt {attempt + 1}/3)")
        except Exception as e:
            logger.error(f"Health check error for {url}: {str(e)}")

        # Wait before retry (except on last attempt)
        if attempt < 2:
            await asyncio.sleep(1)

    return False


def check_rate_limit(request: Request, limit_per_minute: int) -> None:
    """
    Simple sliding window rate limiter

    Args:
        request: FastAPI request object
        limit_per_minute: Maximum requests allowed per minute

    Raises:
        HTTPException: 429 if rate limit exceeded
    """
    if not settings.enable_rate_limiting:
        return

    # Get client identifier (IP address)
    client_id = request.client.host if request.client else "unknown"

    # Get current timestamp
    current_time = time.time()
    window_start = current_time - 60  # 60 seconds window

    # Get or create deque for this client
    timestamps = rate_limiter_storage[client_id]

    # Remove timestamps outside the window
    while timestamps and timestamps[0] < window_start:
        timestamps.popleft()

    # Check if limit exceeded
    if len(timestamps) >= limit_per_minute:
        logger.warning(f"Rate limit exceeded for client {client_id}: {len(timestamps)}/{limit_per_minute}")
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Maximum {limit_per_minute} requests per minute allowed."
        )

    # Add current request timestamp
    timestamps.append(current_time)

    # Cleanup old client records periodically (keep last 1000 clients)
    if len(rate_limiter_storage) > 1000:
        # Remove oldest entries
        oldest_clients = sorted(
            rate_limiter_storage.items(),
            key=lambda x: x[1][-1] if x[1] else 0
        )[:100]
        for client, _ in oldest_clients:
            del rate_limiter_storage[client]


def parse_decimal(value: str, field_name: str) -> Decimal:
    """
    Safely parse decimal with validation

    Args:
        value: String value to convert to Decimal
        field_name: Name of the field (for error messages)

    Returns:
        Decimal: Validated decimal value

    Raises:
        HTTPException: If value is invalid or negative
    """
    try:
        result = Decimal(value)
        if result < 0:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid {field_name}: {value}. Must be a positive number."
            )
        return result
    except (InvalidOperation, ValueError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}: {value}. Must be a valid number."
        )


async def fetch_historical_prices(
    symbols: List[str],
    lookback_days: int
) -> pd.DataFrame:
    """
    Fetch historical price data from Market Data Service

    Args:
        symbols: List of asset symbols
        lookback_days: Number of days of historical data

    Returns:
        DataFrame with symbols as columns and timestamps as index
    """
    try:
        # Calculate start and end timestamps
        end_time = datetime.now()
        start_time = end_time - timedelta(days=lookback_days)

        # Initialize DataFrame
        price_data = pd.DataFrame()

        # Fetch data for each symbol
        async with httpx.AsyncClient(timeout=30.0) as client:
            for symbol in symbols:
                # Call Market Data Service API
                response = await client.get(
                    f"{settings.market_data_url}/api/v1/historical/klines",
                    params={
                        "symbol": symbol,
                        "interval": "1h",  # Hourly data
                        "start_time": int(start_time.timestamp() * 1000),
                        "end_time": int(end_time.timestamp() * 1000),
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("success") and data.get("klines"):
                        # Extract close prices
                        klines = data["klines"]
                        timestamps = [k["timestamp"] for k in klines]
                        closes = [float(k["close"]) for k in klines]

                        # Add to DataFrame
                        df = pd.DataFrame({
                            "timestamp": timestamps,
                            symbol: closes
                        })
                        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                        df.set_index("timestamp", inplace=True)

                        if price_data.empty:
                            price_data = df
                        else:
                            price_data = price_data.join(df, how="outer")

                else:
                    logger.warning(f"Failed to fetch historical data for {symbol}: {response.status_code}")

        # Forward fill missing values
        price_data.fillna(method="ffill", inplace=True)

        # Drop any remaining NaN values
        price_data.dropna(inplace=True)

        logger.info(f"Fetched {len(price_data)} historical data points for {len(symbols)} symbols")

        return price_data

    except Exception as e:
        logger.error(f"Error fetching historical prices: {str(e)}", exc_info=True)
        return pd.DataFrame()
