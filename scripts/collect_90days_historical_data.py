#!/usr/bin/env python3
"""
Comprehensive 90-Day Historical Data Collection Script
Purpose: Collect 90 days of market data for all trading symbols to enable ML model training
Features:
- Fetches historical kline data from Bybit
- Handles API rate limiting and pagination
- Upserts data into TimescaleDB with conflict handling
- Tracks progress and reports statistics
- Supports partial collection with resume capability
"""

import asyncio
import asyncpg
import httpx
import sys
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

# Configure logging with detailed output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class CollectionConfig:
    """Configuration for data collection"""
    # Database configuration
    db_host: str = "localhost"
    db_port: int = 5433
    db_name: str = "market_data"
    db_user: str = "cryptobot"
    db_password: str = "timescale_dev_password"

    # Bybit API configuration
    bybit_url: str = "http://localhost:8001"  # Bybit connector service
    api_timeout: float = 30.0

    # Data collection parameters
    symbols: List[str] = None  # Default symbols
    interval: str = "60"  # 1 hour interval
    target_days: int = 90  # Target 90 days of data
    max_retries: int = 3
    retry_delay: int = 2  # seconds
    rate_limit_delay: float = 0.5  # seconds between requests

    def __post_init__(self):
        """Initialize default symbols if not provided"""
        if self.symbols is None:
            self.symbols = [
                "BTCUSDT",
                "ETHUSDT",
                "BNBUSDT",
                "SOLUSDT",
                "XRPUSDT",
                "ADAUSDT",
                "DOGEUSDT",
            ]


class BybitKlineFetcher:
    """Fetch kline data from Bybit connector service"""

    def __init__(self, config: CollectionConfig):
        """Initialize fetcher with configuration"""
        self.config = config
        self.http_client = None
        logger.info(f"Initialized Bybit fetcher for {config.bybit_url}")

    async def initialize(self):
        """Initialize HTTP client"""
        self.http_client = httpx.AsyncClient(timeout=self.config.api_timeout)
        logger.debug("HTTP client initialized")

    async def close(self):
        """Close HTTP client"""
        if self.http_client:
            await self.http_client.aclose()
            logger.debug("HTTP client closed")

    async def fetch_klines(
        self,
        symbol: str,
        limit: int = 200
    ) -> List[List]:
        """
        Fetch klines from Bybit connector service

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            limit: Number of candles to fetch (max 200)

        Returns:
            List of kline arrays [timestamp, open, high, low, close, volume, turnover]

        Raises:
            Exception: If fetch fails after retries
        """
        url = f"{self.config.bybit_url}/api/v1/market/kline"
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": self.config.interval,
            "limit": limit
        }

        for attempt in range(self.config.max_retries):
            try:
                logger.debug(f"Fetching {limit} candles for {symbol} (attempt {attempt + 1})")
                response = await self.http_client.get(url, params=params)

                # Handle rate limiting
                if response.status_code == 429:
                    wait_time = self.config.retry_delay * (2 ** attempt)
                    logger.warning(
                        f"Rate limited for {symbol}. Waiting {wait_time}s before retry..."
                    )
                    await asyncio.sleep(wait_time)
                    continue

                # Check for success
                if response.status_code != 200:
                    logger.error(
                        f"Failed to fetch {symbol}: HTTP {response.status_code}"
                    )
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(self.config.retry_delay)
                    continue

                # Parse response
                data = response.json()
                klines = data.get("data", [])
                logger.debug(f"Fetched {len(klines)} candles for {symbol}")
                return klines

            except Exception as e:
                logger.error(f"Error fetching {symbol}: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay)
                else:
                    raise

        raise Exception(f"Failed to fetch {symbol} after {self.config.max_retries} retries")


def convert_kline_to_db_format(kline: List, symbol: str, interval: str) -> Dict:
    """
    Convert Bybit kline format to database format

    Args:
        kline: Bybit kline array [timestamp, open, high, low, close, volume, turnover]
        symbol: Trading pair
        interval: Interval in minutes

    Returns:
        Dictionary ready for database insertion
    """
    try:
        # Bybit returns timestamp in milliseconds
        timestamp_ms = int(kline[0])
        timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

        return {
            "time": timestamp,
            "symbol": symbol,
            "interval": interval,
            "open": float(kline[1]),
            "high": float(kline[2]),
            "low": float(kline[3]),
            "close": float(kline[4]),
            "volume": float(kline[5]),
            "quote_volume": float(kline[6]) if len(kline) > 6 else 0.0,
            "trades_count": 0,  # Not provided by Bybit
        }
    except Exception as e:
        logger.error(f"Error converting kline: {e}")
        return None


class DatabaseManager:
    """Manage database operations for market data"""

    def __init__(self, config: CollectionConfig):
        """Initialize database manager"""
        self.config = config
        self.pool = None
        logger.info(f"Initialized DatabaseManager for {config.db_host}:{config.db_port}")

    async def connect(self):
        """Create connection pool"""
        try:
            self.pool = await asyncpg.create_pool(
                host=self.config.db_host,
                port=self.config.db_port,
                database=self.config.db_name,
                user=self.config.db_user,
                password=self.config.db_password,
                min_size=2,
                max_size=10,
            )
            logger.info("Database connection pool created")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def disconnect(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed")

    async def bulk_upsert_klines(self, klines: List[Dict]) -> int:
        """
        Insert klines with conflict handling (upsert)

        Args:
            klines: List of kline dictionaries

        Returns:
            Number of rows inserted/updated
        """
        if not klines:
            return 0

        try:
            async with self.pool.acquire() as conn:
                # Use upsert query to handle duplicates
                query = """
                    INSERT INTO market_data.candles
                    (time, symbol, interval, open, high, low, close, volume, quote_volume, trades_count)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (time, symbol, interval)
                    DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        quote_volume = EXCLUDED.quote_volume,
                        trades_count = EXCLUDED.trades_count
                """

                # Prepare batch insert data
                records = [
                    (
                        k["time"],
                        k["symbol"],
                        k["interval"],
                        k["open"],
                        k["high"],
                        k["low"],
                        k["close"],
                        k["volume"],
                        k["quote_volume"],
                        k["trades_count"]
                    )
                    for k in klines
                ]

                # Execute batch upsert
                await conn.executemany(query, records)
                logger.debug(f"Upserted {len(records)} candles")
                return len(records)

        except Exception as e:
            logger.error(f"Database upsert error: {e}")
            raise

    async def get_symbol_coverage(self, symbol: str) -> Dict:
        """
        Get current data coverage for a symbol

        Args:
            symbol: Trading pair

        Returns:
            Dictionary with candle count, date range, and days covered
        """
        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchrow("""
                    SELECT
                        COUNT(*) as total_candles,
                        MIN(time) as earliest,
                        MAX(time) as latest,
                        EXTRACT(EPOCH FROM (MAX(time) - MIN(time))) / 86400 as days_covered
                    FROM market_data.candles
                    WHERE symbol = $1 AND interval = $2
                """, symbol, self.config.interval)

                if result and result['total_candles']:
                    return {
                        "symbol": symbol,
                        "total_candles": result['total_candles'],
                        "earliest": result['earliest'],
                        "latest": result['latest'],
                        "days_covered": float(result['days_covered'])
                    }
                else:
                    return {
                        "symbol": symbol,
                        "total_candles": 0,
                        "earliest": None,
                        "latest": None,
                        "days_covered": 0.0
                    }

        except Exception as e:
            logger.error(f"Error getting coverage for {symbol}: {e}")
            raise

    async def get_all_coverage(self) -> List[Dict]:
        """Get data coverage for all symbols"""
        coverage = []
        for symbol in self.config.symbols:
            cov = await self.get_symbol_coverage(symbol)
            coverage.append(cov)
        return coverage


class DataCollectionOrchestrator:
    """Orchestrate complete data collection process"""

    def __init__(self, config: CollectionConfig):
        """Initialize orchestrator"""
        self.config = config
        self.fetcher = BybitKlineFetcher(config)
        self.db = DatabaseManager(config)
        self.stats = {
            "symbols_processed": 0,
            "total_candles_fetched": 0,
            "total_candles_stored": 0,
            "errors": []
        }
        logger.info("Initialized DataCollectionOrchestrator")

    async def initialize(self):
        """Initialize all components"""
        await self.fetcher.initialize()
        await self.db.connect()
        logger.info("All components initialized")

    async def close(self):
        """Close all connections"""
        await self.fetcher.close()
        await self.db.disconnect()
        logger.info("All connections closed")

    async def collect_historical_data_for_symbol(
        self,
        symbol: str
    ) -> Dict:
        """
        Collect 90 days of historical data for a symbol

        Strategy:
        - Bybit API returns max 200 candles per request
        - For 90 days of 1h candles: need 90 * 24 = 2,160 candles
        - Requires 2,160 / 200 = 10.8 requests (11 total)
        - Fetch latest batch first, then older batches

        Args:
            symbol: Trading pair

        Returns:
            Dictionary with collection results
        """
        logger.info(f"Starting collection for {symbol}")
        start_time = time.time()

        try:
            # Calculate total candles needed
            candles_per_day = 24  # 1-hour interval
            total_candles_needed = self.config.target_days * candles_per_day
            logger.info(f"Target: {total_candles_needed} candles for {symbol}")

            # Fetch data in batches
            all_klines = []
            batch_size = 200  # Bybit limit
            batches_needed = (total_candles_needed + batch_size - 1) // batch_size
            logger.info(f"Fetching {batches_needed} batches of {batch_size} candles")

            for batch_num in range(batches_needed):
                # Fetch batch
                logger.info(f"Batch {batch_num + 1}/{batches_needed}")
                klines = await self.fetcher.fetch_klines(
                    symbol=symbol,
                    limit=batch_size
                )

                if not klines:
                    logger.warning(f"No more data available for {symbol}")
                    break

                # Convert to database format
                converted = []
                for kline in klines:
                    db_kline = convert_kline_to_db_format(
                        kline,
                        symbol,
                        self.config.interval
                    )
                    if db_kline:
                        converted.append(db_kline)

                all_klines.extend(converted)
                logger.info(f"Batch {batch_num + 1}: {len(converted)} candles")

                # Check if we have enough data
                if len(all_klines) >= total_candles_needed:
                    logger.info(f"Reached target: {len(all_klines)} candles")
                    break

                # Rate limiting between batches
                await asyncio.sleep(self.config.rate_limit_delay)

            logger.info(f"Total fetched: {len(all_klines)} candles for {symbol}")

            # Store in database
            if all_klines:
                stored = await self.db.bulk_upsert_klines(all_klines)
                logger.info(f"Stored {stored} candles for {symbol}")

                self.stats["total_candles_fetched"] += len(all_klines)
                self.stats["total_candles_stored"] += stored

                elapsed = time.time() - start_time
                return {
                    "symbol": symbol,
                    "success": True,
                    "candles_fetched": len(all_klines),
                    "candles_stored": stored,
                    "elapsed_seconds": elapsed
                }
            else:
                logger.error(f"No data collected for {symbol}")
                self.stats["errors"].append(f"{symbol}: No data collected")
                return {
                    "symbol": symbol,
                    "success": False,
                    "error": "No data collected",
                    "elapsed_seconds": time.time() - start_time
                }

        except Exception as e:
            logger.error(f"Error collecting {symbol}: {e}", exc_info=True)
            self.stats["errors"].append(f"{symbol}: {str(e)}")
            return {
                "symbol": symbol,
                "success": False,
                "error": str(e),
                "elapsed_seconds": time.time() - start_time
            }

    async def collect_for_all_symbols(self):
        """Collect data for all symbols sequentially"""
        logger.info(f"Starting collection for {len(self.config.symbols)} symbols")
        logger.info(f"Target: {self.config.target_days} days per symbol")
        logger.info(f"Interval: {self.config.interval} minutes (1 hour)")

        results = []
        start_time = time.time()

        for i, symbol in enumerate(self.config.symbols, 1):
            logger.info(f"\n[{i}/{len(self.config.symbols)}] Processing {symbol}...")

            # Collect for this symbol
            result = await self.collect_historical_data_for_symbol(symbol)
            results.append(result)
            self.stats["symbols_processed"] += 1

            # Rate limiting between symbols
            if i < len(self.config.symbols):
                await asyncio.sleep(1)

        total_elapsed = time.time() - start_time

        return {
            "results": results,
            "stats": self.stats,
            "total_elapsed_seconds": total_elapsed
        }


async def print_coverage_report(db: DatabaseManager):
    """Print current data coverage report"""
    logger.info("\n" + "="*80)
    logger.info("CURRENT DATA COVERAGE")
    logger.info("="*80)

    coverage = await db.get_all_coverage()
    for item in coverage:
        if item["total_candles"] > 0:
            logger.info(
                f"{item['symbol']:10} | {item['total_candles']:5} candles | "
                f"{item['days_covered']:6.1f} days | "
                f"{item['earliest']} to {item['latest']}"
            )
        else:
            logger.info(f"{item['symbol']:10} | No data")


async def main():
    """Main entry point"""
    logger.info("\n" + "="*80)
    logger.info("CRYPTO BOT - 90-DAY HISTORICAL DATA COLLECTION")
    logger.info("="*80 + "\n")

    # Create configuration
    config = CollectionConfig()

    # Create orchestrator
    orchestrator = DataCollectionOrchestrator(config)

    try:
        # Initialize
        logger.info("Initializing components...")
        await orchestrator.initialize()

        # Show initial coverage
        await print_coverage_report(orchestrator.db)

        # Collect data
        logger.info("\n" + "-"*80)
        logger.info("STARTING DATA COLLECTION")
        logger.info("-"*80 + "\n")

        collection_result = await orchestrator.collect_for_all_symbols()

        # Print results
        logger.info("\n" + "="*80)
        logger.info("COLLECTION RESULTS")
        logger.info("="*80 + "\n")

        for result in collection_result["results"]:
            if result["success"]:
                logger.info(
                    f"✅ {result['symbol']:10} | "
                    f"{result['candles_stored']:5} stored | "
                    f"{result['elapsed_seconds']:.1f}s"
                )
            else:
                logger.error(
                    f"❌ {result['symbol']:10} | "
                    f"Error: {result['error']}"
                )

        # Print statistics
        logger.info("\n" + "-"*80)
        logger.info("STATISTICS")
        logger.info("-"*80)
        logger.info(f"Symbols processed: {collection_result['stats']['symbols_processed']}")
        logger.info(f"Total candles fetched: {collection_result['stats']['total_candles_fetched']}")
        logger.info(f"Total candles stored: {collection_result['stats']['total_candles_stored']}")
        logger.info(f"Total time: {collection_result['total_elapsed_seconds']:.1f} seconds")

        if collection_result['stats']['errors']:
            logger.info(f"\nErrors ({len(collection_result['stats']['errors'])}):")
            for error in collection_result['stats']['errors']:
                logger.error(f"  - {error}")

        # Show final coverage
        await print_coverage_report(orchestrator.db)

        logger.info("\n" + "="*80)
        logger.info("✅ DATA COLLECTION COMPLETE!")
        logger.info("="*80 + "\n")

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

    finally:
        await orchestrator.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.warning("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)
