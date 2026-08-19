"""
Market Data Service - Data Fetcher
Purpose: Fetch market data from Bybit Connector service
         Supports proper pagination for historical data retrieval

Fixed: 2025-12-11 - Added start/end time parameters and proper pagination
       for fetching data ranges > 1000 candles (Bybit API limit)
"""

import httpx
import asyncio
import logging
import time
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from app.config import get_settings
from app.circuit_breaker import bybit_connector_retry

logger = logging.getLogger(__name__)

# Bybit API constants
MAX_CANDLES_PER_REQUEST = 1000  # Bybit V5 API limit per request
RATE_LIMIT_DELAY = 0.2  # Delay between API calls to avoid rate limiting (seconds)


def get_interval_minutes(interval: str) -> int:
    """
    Convert Bybit interval string to minutes

    Args:
        interval: Bybit interval string (1, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M)

    Returns:
        Number of minutes for the interval
    """
    # Numeric intervals are already in minutes
    if interval.isdigit():
        return int(interval)

    # Special interval mappings
    interval_map = {
        'D': 1440,      # Daily = 24 * 60 minutes
        'W': 10080,     # Weekly = 7 * 24 * 60 minutes
        'M': 43200,     # Monthly = 30 * 24 * 60 minutes (approximate)
    }

    return interval_map.get(interval.upper(), 60)  # Default to hourly


class BybitDataFetcher:
    """
    Fetches market data from Bybit Connector service
    Acts as a client to the Bybit Connector microservice

    Supports:
    - Single kline requests with time range
    - Paginated historical data fetching for ranges > 1000 candles
    - Automatic deduplication and sorting
    """

    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize data fetcher

        Args:
            base_url: Bybit Connector service URL (defaults to config)
        """
        settings = get_settings()
        self.base_url = base_url or settings.bybit_connector_url

        # Configure connection pooling for optimal performance
        limits = httpx.Limits(
            max_connections=100,        # Total connection pool size
            max_keepalive_connections=20,  # Keep 20 connections alive for reuse
            keepalive_expiry=30.0       # Keep connections alive for 30 seconds
        )

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=30.0,
            limits=limits
            # Note: http2=True requires httpx[http2] extra package
        )
        logger.info(f"Initialized BybitDataFetcher with connection pooling: {self.base_url}")

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
        logger.info("BybitDataFetcher closed")

    async def health_check(self) -> bool:
        """
        Check if Bybit Connector service is healthy

        Returns:
            True if healthy, False otherwise
        """
        try:
            response = await self.client.get("/health")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    @bybit_connector_retry
    async def get_kline(
        self,
        symbol: str,
        interval: str,
        limit: int = 200,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch kline/candlestick data with optional time range

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Candlestick interval (1, 5, 15, 30, 60, etc.)
            limit: Number of candles to fetch (max 1000)
            start_time: Start timestamp in milliseconds (inclusive)
            end_time: End timestamp in milliseconds (inclusive)

        Returns:
            List of kline data dictionaries sorted by timestamp (oldest first)

        Example response:
            [
                {
                    "timestamp": 1234567890000,
                    "open": "50000.0",
                    "high": "51000.0",
                    "low": "49000.0",
                    "close": "50500.0",
                    "volume": "123.456",
                    "turnover": "6172800.0"
                },
                ...
            ]

        Note:
            Bybit API returns data in descending order (newest first).
            This method converts to ascending order (oldest first) for consistency.
        """
        # Build request parameters
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit, MAX_CANDLES_PER_REQUEST)
        }

        # Add time range parameters if provided (FIX: was missing before)
        if start_time is not None:
            params["start"] = start_time
        if end_time is not None:
            params["end"] = end_time

        try:
            response = await self.client.get("/api/v1/market/kline", params=params)
            response.raise_for_status()

            data = response.json()
            if data.get("success"):
                # Bybit returns: [timestamp, open, high, low, close, volume, turnover]
                # The data can be either a list directly or nested in a dict
                raw_data = data.get("data", [])
                if isinstance(raw_data, dict):
                    raw_klines = raw_data.get("list", [])
                else:
                    raw_klines = raw_data

                # Convert to structured format
                klines = []
                for k in raw_klines:
                    klines.append({
                        "timestamp": int(k[0]),
                        "open": k[1],
                        "high": k[2],
                        "low": k[3],
                        "close": k[4],
                        "volume": k[5],
                        "turnover": k[6] if len(k) > 6 else "0"
                    })

                # Sort by timestamp ascending (oldest first) for consistency
                # Bybit returns newest first, so we reverse the order
                klines.sort(key=lambda x: x["timestamp"])

                # Drop the still-forming (unclosed) candle.
                # Bybit V5 returns klines newest-first, i.e. the current
                # PARTIAL candle is the first element of the raw response;
                # after the ascending sort above it becomes the LAST
                # element. We do not rely on position though — we filter by
                # time: a candle is closed only once
                # `timestamp + interval_duration <= now`. Anything else is
                # still forming and would poison indicators/backtests if
                # persisted, so it is discarded here before storage.
                interval_ms = get_interval_minutes(interval) * 60 * 1000
                now_ms = int(time.time() * 1000)
                closed_klines = [
                    k for k in klines
                    if k["timestamp"] + interval_ms <= now_ms
                ]
                dropped = len(klines) - len(closed_klines)
                if dropped:
                    logger.debug(
                        f"Dropped {dropped} still-forming candle(s) for "
                        f"{symbol} ({interval})"
                    )
                klines = closed_klines

                logger.info(
                    f"Fetched {len(klines)} klines for {symbol} ({interval}) "
                    f"[start={start_time}, end={end_time}]"
                )
                return klines
            else:
                logger.error(f"Failed to fetch klines: {data}")
                return []

        except Exception as e:
            logger.error(f"Error fetching klines for {symbol}: {e}")
            return []

    @bybit_connector_retry
    async def get_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch latest ticker data

        Args:
            symbol: Trading pair

        Returns:
            Ticker data dictionary or None
        """
        params = {
            "category": "linear",
            "symbol": symbol
        }

        try:
            response = await self.client.get("/api/v1/market/ticker", params=params)
            response.raise_for_status()

            data = response.json()
            if data.get("success"):
                ticker_list = data.get("data", {}).get("list", [])
                if ticker_list:
                    ticker = ticker_list[0]
                    logger.info(f"Fetched ticker for {symbol}")
                    return {
                        "symbol": ticker.get("symbol"),
                        "last_price": ticker.get("lastPrice"),
                        "bid_price": ticker.get("bid1Price"),
                        "ask_price": ticker.get("ask1Price"),
                        "high_24h": ticker.get("highPrice24h"),
                        "low_24h": ticker.get("lowPrice24h"),
                        "volume_24h": ticker.get("volume24h"),
                        "turnover_24h": ticker.get("turnover24h"),
                        "price_change_24h": ticker.get("price24hPcnt")
                    }

            logger.warning(f"No ticker data for {symbol}")
            return None

        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol}: {e}")
            return None

    async def get_historical_klines(
        self,
        symbol: str,
        interval: str,
        days: int = 30,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        rate_limit_delay: float = RATE_LIMIT_DELAY
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical klines for specified time range with proper pagination

        This method handles the Bybit API limitation of 1000 candles per request
        by making multiple paginated requests and merging the results.

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Candlestick interval (1, 5, 15, 30, 60, etc.)
            days: Number of days of history (used if start_time not provided)
            start_time: Start datetime (defaults to now - days)
            end_time: End datetime (defaults to now)
            rate_limit_delay: Delay between API calls in seconds

        Returns:
            List of all klines sorted by timestamp (oldest first), deduplicated

        Example:
            # Fetch 180 days of hourly data for BTCUSDT
            klines = await fetcher.get_historical_klines(
                symbol="BTCUSDT",
                interval="60",
                days=180
            )
            # Returns ~4320 candles (180 * 24)
        """
        all_klines = []

        # Calculate time range
        if end_time is None:
            end_time = datetime.utcnow()
        if start_time is None:
            start_time = end_time - timedelta(days=days)

        # Convert to milliseconds (Bybit API uses milliseconds)
        end_ms = int(end_time.timestamp() * 1000)
        target_start_ms = int(start_time.timestamp() * 1000)

        # Calculate expected number of candles for progress tracking
        interval_minutes = get_interval_minutes(interval)
        total_minutes = (end_time - start_time).total_seconds() / 60
        expected_candles = int(total_minutes / interval_minutes)

        logger.info(
            f"Fetching {days} days of {symbol} klines ({interval}m interval). "
            f"Expected ~{expected_candles} candles."
        )

        # Pagination: Bybit returns newest first, so we work backwards from end_time
        # Each batch returns up to 1000 candles
        current_end_ms = end_ms
        batch_count = 0
        max_batches = (expected_candles // MAX_CANDLES_PER_REQUEST) + 10  # Safety margin

        while current_end_ms > target_start_ms and batch_count < max_batches:
            batch_count += 1

            # Fetch batch with proper time range
            # Use target_start_ms as start to ensure we get data from that point
            klines = await self.get_kline(
                symbol=symbol,
                interval=interval,
                limit=MAX_CANDLES_PER_REQUEST,
                start_time=target_start_ms,
                end_time=current_end_ms
            )

            if not klines:
                logger.info(f"No more data available for {symbol}")
                break

            # Add to results
            all_klines.extend(klines)

            # Get oldest timestamp from this batch for next iteration
            oldest_ts = min(k["timestamp"] for k in klines)
            newest_ts = max(k["timestamp"] for k in klines)

            logger.debug(
                f"Batch {batch_count}: {len(klines)} candles "
                f"({datetime.fromtimestamp(oldest_ts / 1000).strftime('%Y-%m-%d %H:%M')} to "
                f"{datetime.fromtimestamp(newest_ts / 1000).strftime('%Y-%m-%d %H:%M')}), "
                f"total: {len(all_klines)}"
            )

            # Check if we've reached our target start time
            if oldest_ts <= target_start_ms:
                logger.info(f"Reached target start date for {symbol}")
                break

            # NOTE: a short batch is NOT an end-of-history signal. get_kline
            # drops the still-forming candle by time filter, so a full page
            # comes back as MAX_CANDLES_PER_REQUEST - 1 rows and the old
            # `len(klines) < MAX_CANDLES_PER_REQUEST -> break` truncated every
            # backfill to a single batch. Termination is still guaranteed by
            # the empty-batch break above, the target-start break above, the
            # max_batches loop guard, and current_end_ms strictly decreasing
            # each iteration (oldest_ts <= current_end_ms always holds).

            # Update end time for next batch (1 ms before oldest to avoid duplicates)
            current_end_ms = oldest_ts - 1

            # Rate limiting to avoid Bybit API throttling
            await asyncio.sleep(rate_limit_delay)

        # Deduplicate by timestamp (in case of overlapping batches)
        unique_klines = {}
        for k in all_klines:
            ts = k["timestamp"]
            if ts not in unique_klines:
                unique_klines[ts] = k

        # Sort by timestamp ascending (oldest first)
        sorted_klines = sorted(unique_klines.values(), key=lambda x: x["timestamp"])

        # Filter to target time range (remove any data outside requested range)
        filtered_klines = [
            k for k in sorted_klines
            if target_start_ms <= k["timestamp"] <= end_ms
        ]

        # Log completion statistics
        if filtered_klines:
            first_ts = filtered_klines[0]["timestamp"]
            last_ts = filtered_klines[-1]["timestamp"]
            first_date = datetime.fromtimestamp(first_ts / 1000)
            last_date = datetime.fromtimestamp(last_ts / 1000)
            coverage = (len(filtered_klines) / expected_candles) * 100 if expected_candles > 0 else 0

            logger.info(
                f"Fetched total {len(filtered_klines)} klines for {symbol} "
                f"({coverage:.1f}% coverage). "
                f"Date range: {first_date.strftime('%Y-%m-%d %H:%M')} to "
                f"{last_date.strftime('%Y-%m-%d %H:%M')}"
            )
        else:
            logger.warning(f"No klines fetched for {symbol}")

        return filtered_klines


# Convenience function
def create_fetcher() -> BybitDataFetcher:
    """Create data fetcher instance"""
    return BybitDataFetcher()
