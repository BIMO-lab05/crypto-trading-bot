"""
Market Data Service - Data Fetcher
Purpose: Fetch market data from Bybit Connector service
"""

import httpx
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from app.config import get_settings

logger = logging.getLogger(__name__)


class BybitDataFetcher:
    """
    Fetches market data from Bybit Connector service
    Acts as a client to the Bybit Connector microservice
    """
    
    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize data fetcher
        
        Args:
            base_url: Bybit Connector service URL (defaults to config)
        """
        settings = get_settings()
        self.base_url = base_url or settings.bybit_connector_url
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=30.0
        )
        logger.info(f"Initialized BybitDataFetcher: {self.base_url}")
    
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
    
    async def get_kline(
        self,
        symbol: str,
        interval: str,
        limit: int = 200,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch kline/candlestick data
        
        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Candlestick interval (1, 5, 15, 30, 60, etc.)
            limit: Number of candles to fetch (max 1000)
            start_time: Start timestamp in milliseconds
            end_time: End timestamp in milliseconds
        
        Returns:
            List of kline data dictionaries
        
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
        """
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit, 1000)
        }
        
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
                        "turnover": k[6]
                    })

                logger.info(f"Fetched {len(klines)} klines for {symbol} ({interval})")
                return klines
            else:
                logger.error(f"Failed to fetch klines: {data}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching klines for {symbol}: {e}")
            return []
    
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
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical klines for specified number of days
        
        Args:
            symbol: Trading pair
            interval: Candlestick interval
            days: Number of days of history
        
        Returns:
            List of all klines
        """
        all_klines = []
        
        # Calculate time range
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        logger.info(f"Fetching {days} days of {symbol} klines ({interval})")
        
        # Fetch in batches (max 1000 per request)
        current_time = start_time
        batch_count = 0
        
        while current_time < end_time:
            # Fetch batch
            klines = await self.get_kline(
                symbol=symbol,
                interval=interval,
                limit=1000
            )
            
            if not klines:
                break
            
            all_klines.extend(klines)
            batch_count += 1
            
            # Update time for next batch
            # Get oldest timestamp from this batch
            if klines:
                oldest_ts = min(k["timestamp"] for k in klines)
                current_time = datetime.fromtimestamp(oldest_ts / 1000)
            
            # Safety limit
            if batch_count >= 100:
                logger.warning(f"Reached batch limit for {symbol}")
                break
        
        logger.info(f"Fetched total {len(all_klines)} klines for {symbol}")
        return all_klines


# Convenience function
def create_fetcher() -> BybitDataFetcher:
    """Create data fetcher instance"""
    return BybitDataFetcher()
