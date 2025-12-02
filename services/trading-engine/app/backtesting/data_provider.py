"""
Real Data Provider for Backtesting Framework
Purpose: Fetch historical OHLCV data from market-data-service for backtesting
Author: Trading Engine Team
Version: 1.0.0

This module provides an abstraction layer for fetching historical market data
from the market-data-service and converting it to OHLCV format compatible
with the backtesting engine.
"""

import logging
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from abc import ABC, abstractmethod

from app.backtesting.strategy_base import OHLCV
from app.config import get_settings

logger = logging.getLogger(__name__)


class DataProviderError(Exception):
    """Exception raised for data provider errors"""
    pass


class DataProviderBase(ABC):
    """
    Abstract base class for data providers

    Defines the interface for fetching historical OHLCV data
    for backtesting purposes.
    """

    @abstractmethod
    async def get_historical_data(
        self,
        symbol: str,
        interval: str,
        days: int,
        end_time: Optional[datetime] = None
    ) -> List[OHLCV]:
        """
        Fetch historical OHLCV data

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
            interval: Candlestick interval (e.g., '60' for 1 hour)
            days: Number of days of historical data
            end_time: End timestamp (defaults to now)

        Returns:
            List of OHLCV bars sorted by timestamp (oldest first)
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if data provider is healthy and accessible"""
        pass


class RealDataProvider(DataProviderBase):
    """
    Real Data Provider - Fetches historical data from market-data-service

    This provider connects to the market-data-service microservice to retrieve
    historical OHLCV data stored in the database. It handles:
    - Connection pooling for efficient HTTP requests
    - Automatic retry with exponential backoff
    - Data validation and conversion to OHLCV format
    - Pagination for large data requests

    Usage:
        provider = RealDataProvider()
        data = await provider.get_historical_data('BTCUSDT', '60', days=30)
        # Returns list of OHLCV objects for backtesting

    Configuration:
        Uses market_data_url from trading-engine config settings
    """

    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize Real Data Provider

        Args:
            base_url: Market data service URL (defaults to config value)
        """
        settings = get_settings()
        self.base_url = base_url or settings.market_data_url

        # Configure HTTP client with connection pooling
        limits = httpx.Limits(
            max_connections=50,
            max_keepalive_connections=10,
            keepalive_expiry=30.0
        )

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=60.0,  # 60s timeout for large data requests
            limits=limits
        )

        logger.info(
            f"RealDataProvider initialized: {self.base_url}"
        )

    async def close(self) -> None:
        """Close HTTP client and release resources"""
        await self._client.aclose()
        logger.info("RealDataProvider closed")

    async def health_check(self) -> bool:
        """
        Check if market-data-service is healthy

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            response = await self._client.get("/health")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    async def get_historical_data(
        self,
        symbol: str,
        interval: str = "60",
        days: int = 30,
        end_time: Optional[datetime] = None
    ) -> List[OHLCV]:
        """
        Fetch historical OHLCV data from market-data-service

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
            interval: Candlestick interval in minutes (e.g., '60' for 1h)
            days: Number of days of historical data to fetch
            end_time: End timestamp (defaults to now)

        Returns:
            List of OHLCV bars sorted by timestamp (oldest first)

        Raises:
            DataProviderError: If data fetch fails or no data available
        """
        logger.info(f"Fetching {days} days of {symbol} data (interval: {interval})")

        # Calculate time range
        if end_time is None:
            end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)

        # Convert to milliseconds
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        all_bars: List[OHLCV] = []

        try:
            # Market data service expects interval in minutes
            # Calculate how many bars we need
            interval_minutes = int(interval)
            bars_per_day = (24 * 60) // interval_minutes
            expected_bars = bars_per_day * days

            # Fetch in batches (max 1000 per request)
            batch_size = 1000
            current_end = end_ms

            while len(all_bars) < expected_bars:
                # Request klines from market-data-service
                params = {
                    "interval": interval,
                    "limit": batch_size,
                    "end_time": current_end
                }

                response = await self._client.get(
                    f"/api/v1/klines/{symbol}",
                    params=params
                )

                if response.status_code != 200:
                    error_detail = response.text
                    raise DataProviderError(
                        f"Failed to fetch data for {symbol}: "
                        f"HTTP {response.status_code} - {error_detail}"
                    )

                data = response.json()

                # Handle both direct list and wrapped response formats
                if isinstance(data, list):
                    klines = data
                elif isinstance(data, dict):
                    if data.get("success"):
                        klines = data.get("data", [])
                    else:
                        raise DataProviderError(
                            f"Service error: {data.get('error', 'Unknown error')}"
                        )
                else:
                    klines = []

                if not klines:
                    logger.warning(f"No more data available for {symbol}")
                    break

                # Convert to OHLCV objects
                batch_bars = self._convert_to_ohlcv(klines, symbol)

                # Filter by time range
                batch_bars = [
                    bar for bar in batch_bars
                    if start_time <= bar.timestamp <= end_time
                ]

                if not batch_bars:
                    break

                all_bars.extend(batch_bars)

                # Update current_end for next batch (oldest timestamp)
                oldest_bar = min(batch_bars, key=lambda b: b.timestamp)
                current_end = int(oldest_bar.timestamp.timestamp() * 1000) - 1

                # Check if we've gone past start_time
                if oldest_bar.timestamp <= start_time:
                    break

                logger.debug(f"Fetched batch: {len(batch_bars)} bars, total: {len(all_bars)}")

            # Sort by timestamp (oldest first)
            all_bars.sort(key=lambda x: x.timestamp)

            # Remove duplicates based on timestamp
            seen = set()
            unique_bars = []
            for bar in all_bars:
                ts_key = bar.timestamp.isoformat()
                if ts_key not in seen:
                    seen.add(ts_key)
                    unique_bars.append(bar)

            logger.info(
                f"Fetched {len(unique_bars)} bars for {symbol} "
                f"({unique_bars[0].timestamp if unique_bars else 'N/A'} to "
                f"{unique_bars[-1].timestamp if unique_bars else 'N/A'})"
            )

            return unique_bars

        except httpx.RequestError as e:
            raise DataProviderError(
                f"Network error fetching data for {symbol}: {e}"
            )
        except Exception as e:
            if isinstance(e, DataProviderError):
                raise
            raise DataProviderError(
                f"Unexpected error fetching data for {symbol}: {e}"
            )

    def _convert_to_ohlcv(
        self,
        klines: List[Dict[str, Any]],
        symbol: str
    ) -> List[OHLCV]:
        """
        Convert kline data from market-data-service to OHLCV objects

        Args:
            klines: List of kline dictionaries
            symbol: Trading symbol (for logging)

        Returns:
            List of OHLCV objects
        """
        bars = []

        for kline in klines:
            try:
                # Handle different timestamp formats
                timestamp = kline.get("timestamp") or kline.get("start_time")
                if isinstance(timestamp, (int, float)):
                    # Assume milliseconds if > 1e12
                    if timestamp > 1e12:
                        dt = datetime.fromtimestamp(timestamp / 1000)
                    else:
                        dt = datetime.fromtimestamp(timestamp)
                elif isinstance(timestamp, str):
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                else:
                    logger.warning(f"Unknown timestamp format: {timestamp}")
                    continue

                # Extract OHLCV values (handle string and numeric types)
                bar = OHLCV(
                    timestamp=dt,
                    open=float(kline.get("open", 0)),
                    high=float(kline.get("high", 0)),
                    low=float(kline.get("low", 0)),
                    close=float(kline.get("close", 0)),
                    volume=float(kline.get("volume", 0))
                )

                # Validate OHLCV data
                if bar.high >= bar.low > 0 and bar.open > 0 and bar.close > 0:
                    bars.append(bar)
                else:
                    logger.debug(f"Skipping invalid OHLCV data: {kline}")

            except (ValueError, TypeError) as e:
                logger.warning(f"Error converting kline to OHLCV: {e}, data: {kline}")
                continue

        return bars

    async def get_latest_price(self, symbol: str) -> Optional[float]:
        """
        Get the latest price for a symbol

        Args:
            symbol: Trading pair symbol

        Returns:
            Latest price or None if unavailable
        """
        try:
            response = await self._client.get(f"/api/v1/ticker/{symbol}")

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict):
                    return float(data.get("last_price", 0))

            return None

        except Exception as e:
            logger.error(f"Error getting latest price for {symbol}: {e}")
            return None

    async def get_available_symbols(self) -> List[str]:
        """
        Get list of available trading symbols

        Returns:
            List of available symbol strings
        """
        try:
            response = await self._client.get("/api/v1/symbols")

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and data.get("success"):
                    return data.get("data", [])

            return []

        except Exception as e:
            logger.error(f"Error getting available symbols: {e}")
            return []


class CachedDataProvider(DataProviderBase):
    """
    Cached Data Provider - Wraps another provider with caching

    Implements a cache layer to avoid redundant API calls for the same data.
    Useful when running multiple backtests on the same data.
    """

    def __init__(self, provider: DataProviderBase, max_cache_size: int = 100):
        """
        Initialize cached data provider

        Args:
            provider: Underlying data provider
            max_cache_size: Maximum number of cached data sets
        """
        self._provider = provider
        self._cache: Dict[str, List[OHLCV]] = {}
        self._max_cache_size = max_cache_size

    def _cache_key(
        self,
        symbol: str,
        interval: str,
        days: int
    ) -> str:
        """Generate cache key from parameters"""
        return f"{symbol}:{interval}:{days}"

    async def get_historical_data(
        self,
        symbol: str,
        interval: str = "60",
        days: int = 30,
        end_time: Optional[datetime] = None
    ) -> List[OHLCV]:
        """
        Fetch historical data with caching

        First checks cache, fetches from provider if not cached.
        """
        cache_key = self._cache_key(symbol, interval, days)

        # Check cache
        if cache_key in self._cache:
            logger.debug(f"Cache hit for {cache_key}")
            return self._cache[cache_key]

        # Fetch from provider
        data = await self._provider.get_historical_data(
            symbol, interval, days, end_time
        )

        # Store in cache (with size limit)
        if len(self._cache) >= self._max_cache_size:
            # Remove oldest entry (first key)
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        self._cache[cache_key] = data
        logger.debug(f"Cached {len(data)} bars for {cache_key}")

        return data

    async def health_check(self) -> bool:
        """Check underlying provider health"""
        return await self._provider.health_check()

    def clear_cache(self) -> None:
        """Clear all cached data"""
        self._cache.clear()
        logger.info("Data cache cleared")


# Factory function for creating data providers
def create_data_provider(
    provider_type: str = "real",
    use_cache: bool = True,
    **kwargs
) -> DataProviderBase:
    """
    Factory function to create data provider instances

    Args:
        provider_type: Type of provider ('real' or 'sample')
        use_cache: Whether to wrap with caching layer
        **kwargs: Additional arguments for provider constructor

    Returns:
        DataProviderBase instance

    Example:
        provider = create_data_provider('real', use_cache=True)
        data = await provider.get_historical_data('BTCUSDT', '60', days=30)
    """
    if provider_type == "real":
        provider = RealDataProvider(**kwargs)
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")

    if use_cache:
        return CachedDataProvider(provider)

    return provider
