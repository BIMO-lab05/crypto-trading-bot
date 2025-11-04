"""
Technical Analysis Service - Market Data Fetcher
Purpose: Fetch kline data from Market Data Service
"""

import httpx
import logging
from typing import List, Dict, Any, Optional
import pandas as pd
from app.config import get_settings
from app.models import Kline

logger = logging.getLogger(__name__)


class MarketDataFetcher:
    """Fetches market data from Market Data Service"""

    def __init__(self):
        """Initialize fetcher with Market Data Service URL"""
        self.settings = get_settings()
        self.base_url = self.settings.market_data_url
        self.client = httpx.AsyncClient(timeout=30.0)
        logger.info(f"MarketDataFetcher initialized with base_url: {self.base_url}")

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
        logger.info("MarketDataFetcher closed")

    async def health_check(self) -> bool:
        """
        Check if Market Data Service is healthy

        Returns:
            True if healthy, False otherwise
        """
        try:
            response = await self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    async def get_klines(
        self,
        symbol: str,
        interval: str = "60",
        limit: int = 200
    ) -> List[Kline]:
        """
        Fetch kline data for analysis

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Candlestick interval (default: 60 = 1 hour)
            limit: Number of candles to fetch

        Returns:
            List of Kline objects sorted by timestamp ascending

        Raises:
            Exception if fetch fails
        """
        try:
            params = {
                "interval": interval,
                "limit": limit
            }

            response = await self.client.get(
                f"{self.base_url}/api/v1/klines/{symbol}",
                params=params
            )
            response.raise_for_status()

            data = response.json()
            if data.get("success"):
                klines_data = data.get("data", [])

                # Convert to Kline objects
                klines = [
                    Kline(
                        timestamp=k["timestamp"],
                        open=float(k["open"]),
                        high=float(k["high"]),
                        low=float(k["low"]),
                        close=float(k["close"]),
                        volume=float(k["volume"])
                    )
                    for k in klines_data
                ]

                # Sort by timestamp ascending (oldest first) for TA calculations
                klines.sort(key=lambda x: x.timestamp)

                logger.info(f"Fetched {len(klines)} klines for {symbol} ({interval})")
                return klines
            else:
                logger.error(f"Failed to fetch klines: {data}")
                return []

        except Exception as e:
            logger.error(f"Error fetching klines for {symbol}: {e}")
            raise

    async def get_klines_as_dataframe(
        self,
        symbol: str,
        interval: str = "60",
        limit: int = 200
    ) -> pd.DataFrame:
        """
        Fetch klines and return as pandas DataFrame for analysis

        Args:
            symbol: Trading pair
            interval: Candlestick interval
            limit: Number of candles

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        klines = await self.get_klines(symbol, interval, limit)

        if not klines:
            return pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame([k.model_dump() for k in klines])

        # Set timestamp as index for time-series operations
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('datetime', inplace=True)

        logger.info(f"Created DataFrame with {len(df)} rows for {symbol}")
        return df

    async def get_latest_price(
        self,
        symbol: str,
        interval: str = "60"
    ) -> Optional[float]:
        """
        Get the most recent closing price

        Args:
            symbol: Trading pair
            interval: Candlestick interval

        Returns:
            Latest close price or None
        """
        try:
            klines = await self.get_klines(symbol, interval, limit=1)
            if klines:
                return klines[-1].close
            return None
        except Exception as e:
            logger.error(f"Error getting latest price for {symbol}: {e}")
            return None


# Global fetcher instance
_fetcher: Optional[MarketDataFetcher] = None


def get_fetcher() -> MarketDataFetcher:
    """Get fetcher singleton"""
    global _fetcher
    if _fetcher is None:
        _fetcher = MarketDataFetcher()
    return _fetcher


async def close_fetcher():
    """Close fetcher"""
    global _fetcher
    if _fetcher is not None:
        await _fetcher.close()
        _fetcher = None
