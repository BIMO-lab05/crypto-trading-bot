#!/usr/bin/env python3
"""
Targeted Data Collection for Rate-Limited Symbols
Purpose: Collect missing 60 days of data for BNBUSDT, SOLUSDT, DOGEUSDT
Features: Increased delays, more retries, skip already-complete symbols
"""

import asyncio
import asyncpg
import httpx
import sys
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from dataclasses import dataclass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for targeted retry collection"""
    db_host: str = "localhost"
    db_port: int = 5433
    db_name: str = "market_data"
    db_user: str = "cryptobot"
    db_password: str = "timescale_dev_password"
    bybit_url: str = "http://localhost:8001"
    api_timeout: float = 30.0

    # Target symbols with rate limit issues
    target_symbols: List[str] = None
    interval: str = "60"
    target_days: int = 90
    max_retries: int = 5  # Increased retries
    retry_delay: int = 5  # Much longer delay
    rate_limit_delay: float = 2.0  # Longer delay between requests
    long_wait_on_429: int = 30  # Wait 30s on rate limit

    def __post_init__(self):
        """Initialize defaults"""
        if self.target_symbols is None:
            self.target_symbols = ["BNBUSDT", "SOLUSDT", "DOGEUSDT"]


class SmartKlineFetcher:
    """Fetch klines with intelligent rate limit handling"""

    def __init__(self, config: RetryConfig):
        self.config = config
        self.http_client = None
        self.rate_limited_count = 0

    async def initialize(self):
        self.http_client = httpx.AsyncClient(timeout=self.config.api_timeout)
        logger.info("HTTP client initialized")

    async def close(self):
        if self.http_client:
            await self.http_client.aclose()

    async def fetch_klines(self, symbol: str, limit: int = 200) -> List[List]:
        """Fetch klines with intelligent backoff"""
        url = f"{self.config.bybit_url}/api/v1/market/kline"
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": self.config.interval,
            "limit": limit
        }

        for attempt in range(self.config.max_retries):
            try:
                response = await self.http_client.get(url, params=params)

                if response.status_code == 429:
                    self.rate_limited_count += 1
                    wait_time = self.config.long_wait_on_429 * (2 ** min(attempt, 2))
                    logger.warning(
                        f"Rate limited (attempt {attempt + 1}/{self.config.max_retries}). "
                        f"Waiting {wait_time}s before retry..."
                    )
                    await asyncio.sleep(wait_time)
                    continue

                if response.status_code != 200:
                    logger.error(f"HTTP {response.status_code}")
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(self.config.retry_delay)
                    continue

                data = response.json()
                klines = data.get("data", [])
                logger.info(f"Fetched {len(klines)} candles")
                return klines

            except Exception as e:
                logger.error(f"Error: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay)

        raise Exception(f"Failed after {self.config.max_retries} retries")


def convert_kline(kline: List, symbol: str, interval: str) -> Dict:
    """Convert Bybit kline to DB format"""
    try:
        timestamp = datetime.fromtimestamp(int(kline[0]) / 1000, tz=timezone.utc)
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
            "trades_count": 0,
        }
    except Exception as e:
        logger.error(f"Error converting kline: {e}")
        return None


class RetryOrchestrator:
    """Orchestrate retry collection for rate-limited symbols"""

    def __init__(self, config: RetryConfig):
        self.config = config
        self.fetcher = SmartKlineFetcher(config)
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            host=self.config.db_host,
            port=self.config.db_port,
            database=self.config.db_name,
            user=self.config.db_user,
            password=self.config.db_password,
            min_size=2,
            max_size=10,
        )
        logger.info("Database connected")

    async def disconnect(self):
        if self.pool:
            await self.pool.close()

    async def get_symbol_coverage(self, symbol: str) -> Dict:
        """Get current coverage"""
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
            return {
                "symbol": symbol,
                "total_candles": 0,
                "days_covered": 0.0
            }

    async def bulk_upsert(self, klines: List[Dict]) -> int:
        """Upsert klines"""
        if not klines:
            return 0

        async with self.pool.acquire() as conn:
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
                    volume = EXCLUDED.volume
            """

            records = [
                (
                    k["time"], k["symbol"], k["interval"],
                    k["open"], k["high"], k["low"], k["close"],
                    k["volume"], k["quote_volume"], k["trades_count"]
                )
                for k in klines
            ]

            await conn.executemany(query, records)
            return len(records)

    async def collect_symbol(self, symbol: str) -> Dict:
        """Collect data for one symbol"""
        logger.info(f"\nCollecting {symbol}...")
        start_time = time.time()

        try:
            # Check current coverage
            coverage = await self.get_symbol_coverage(symbol)
            logger.info(f"Current: {coverage['total_candles']} candles, {coverage['days_covered']:.1f} days")

            # Calculate need
            candles_needed = self.config.target_days * 24
            if coverage['total_candles'] >= candles_needed:
                logger.info(f"Already has sufficient data")
                return {
                    "symbol": symbol,
                    "success": True,
                    "status": "already_complete",
                    "candles_stored": 0
                }

            # Fetch all batches
            all_klines = []
            batches_needed = (candles_needed + 199) // 200
            logger.info(f"Fetching {batches_needed} batches...")

            for batch_num in range(batches_needed):
                klines = await self.fetcher.fetch_klines(symbol)
                if not klines:
                    logger.warning("No more data available")
                    break

                converted = [convert_kline(k, symbol, self.config.interval) for k in klines]
                converted = [k for k in converted if k]
                all_klines.extend(converted)

                logger.info(f"Batch {batch_num + 1}: {len(converted)} candles (total: {len(all_klines)})")

                if len(all_klines) >= candles_needed:
                    logger.info(f"Reached target")
                    break

                # Rate limiting
                await asyncio.sleep(self.config.rate_limit_delay)

            # Store
            stored = await self.bulk_upsert(all_klines)
            elapsed = time.time() - start_time

            logger.info(f"Stored {stored} candles in {elapsed:.1f}s")

            return {
                "symbol": symbol,
                "success": True,
                "candles_fetched": len(all_klines),
                "candles_stored": stored,
                "elapsed": elapsed
            }

        except Exception as e:
            logger.error(f"Error: {e}")
            return {
                "symbol": symbol,
                "success": False,
                "error": str(e)
            }

    async def collect_all(self):
        """Collect for all target symbols"""
        logger.info("\n" + "="*80)
        logger.info("TARGETED RETRY DATA COLLECTION")
        logger.info("="*80)
        logger.info(f"Symbols: {self.config.target_symbols}")
        logger.info(f"Max retries: {self.config.max_retries}")
        logger.info(f"Rate limit wait: {self.config.long_wait_on_429}s")

        results = []
        for i, symbol in enumerate(self.config.target_symbols, 1):
            logger.info(f"\n[{i}/{len(self.config.target_symbols)}]")
            result = await self.collect_symbol(symbol)
            results.append(result)

            if i < len(self.config.target_symbols):
                await asyncio.sleep(3)

        return results


async def main():
    config = RetryConfig()
    orchestrator = RetryOrchestrator(config)

    try:
        await orchestrator.fetcher.initialize()
        await orchestrator.connect()

        results = await orchestrator.collect_all()

        # Print results
        logger.info("\n" + "="*80)
        logger.info("RESULTS")
        logger.info("="*80)

        for r in results:
            if r["success"]:
                if r.get("status") == "already_complete":
                    logger.info(f"✅ {r['symbol']:10} - Already complete")
                else:
                    logger.info(
                        f"✅ {r['symbol']:10} - Stored {r['candles_stored']} "
                        f"in {r['elapsed']:.1f}s"
                    )
            else:
                logger.error(f"❌ {r['symbol']:10} - {r['error']}")

        # Show final coverage
        logger.info("\n" + "-"*80)
        logger.info("FINAL COVERAGE")
        logger.info("-"*80)

        for symbol in config.target_symbols:
            coverage = await orchestrator.get_symbol_coverage(symbol)
            logger.info(
                f"{coverage['symbol']:10} | {coverage['total_candles']:5} candles | "
                f"{coverage['days_covered']:6.1f} days"
            )

    finally:
        await orchestrator.disconnect()
        await orchestrator.fetcher.close()


if __name__ == "__main__":
    asyncio.run(main())
