#!/usr/bin/env python3
"""
Fetch REAL historical kline data via bybit-connector
Replaces test data with accurate market prices for BTC and ETH
Purpose: Fix unrealistic test data causing -100% backtest results

Phase 13 (BC-02): routes through the bybit-connector service at
``$BYBIT_CONNECTOR_URL/api/v1/market/kline`` (default ``http://localhost:8001``)
instead of calling Bybit's public REST API directly. Exits 2 with an
operator-readable error when the connector is unreachable (D-04 fail-fast).
"""

import asyncio
import os
import sys
from pathlib import Path as _Path

_REPO_ROOT = _Path(__file__).resolve().parent.parent
import asyncpg
import httpx
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Phase 13 BC-02: bybit-connector endpoint. Host-friendly default; the compose
# stack overrides this to ``http://bybit-connector:8001`` via environment.
BYBIT_CONNECTOR_URL = os.getenv("BYBIT_CONNECTOR_URL", "http://localhost:8001")


async def assert_connector_reachable() -> None:
    """D-04: fail-fast with operator-readable error if bybit-connector down."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{BYBIT_CONNECTOR_URL}/health")
            response.raise_for_status()
    except Exception as e:
        print(
            f"\nERROR: bybit-connector is not reachable at {BYBIT_CONNECTOR_URL}.\n"
            f"  Cause: {e!r}\n"
            f"  Fix:   Run `docker compose -f docker-compose.unified.yml up -d bybit-connector`\n"
            f"  (or set BYBIT_CONNECTOR_URL if running against a non-default host).\n",
            file=sys.stderr,
        )
        sys.exit(2)


class BybitDataFetcher:
    """Fetch real historical data via bybit-connector."""

    def __init__(self):
        """Initialize HTTP client against the bybit-connector base URL."""
        self.base_url = BYBIT_CONNECTOR_URL
        self.http_client = httpx.AsyncClient(timeout=30.0, base_url=self.base_url)
        logger.info(f"Initialized Bybit Data Fetcher routed to {self.base_url}")

    async def fetch_klines(
        self,
        symbol: str,
        interval: str = "60",  # 60 = 1 hour
        limit: int = 200,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[List]:
        """
        Fetch kline data via bybit-connector.

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Timeframe (60 = 1 hour, 240 = 4 hour, D = 1 day)
            limit: Number of candles (max 200 per request)
            start_time: Start timestamp in milliseconds
            end_time: End timestamp in milliseconds

        Returns:
            List of kline arrays [timestamp, open, high, low, close, volume, turnover]
        """
        try:
            # bybit-connector kline endpoint (V5 list shape preserved by the wrapper)
            url = "/api/v1/market/kline"

            # Build parameters
            params = {
                "category": "linear",  # USDT perpetual futures
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            }

            if start_time:
                params["start"] = start_time
            if end_time:
                params["end"] = end_time

            logger.debug(
                f"Requesting {limit} candles for {symbol} (interval: {interval})"
            )

            # Make API request
            response = await self.http_client.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            # bybit-connector wrapper shape: {"success": bool, "data": {"list": [...]}}
            if not data.get("success"):
                logger.error(f"bybit-connector kline error: {data}")
                return []

            # Extract klines (V5 list shape preserved through the wrapper)
            klines = data.get("data", {}).get("list", [])

            logger.debug(f"Fetched {len(klines)} candles for {symbol}")
            return klines

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching klines for {symbol}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching klines for {symbol}: {e}")
            return []

    async def fetch_historical_range(
        self, symbol: str, days: int = 90, interval: str = "60"
    ) -> List[Dict]:
        """
        Fetch historical data for specified number of days

        Bybit limits: 200 candles per request
        For 90 days of hourly data: 90 * 24 = 2160 candles
        Need: 2160 / 200 = ~11 requests

        Args:
            symbol: Trading pair
            days: Number of days of historical data
            interval: Candle interval (60 = 1 hour)

        Returns:
            List of formatted kline dictionaries
        """
        all_klines = []

        # Calculate time range
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)

        logger.info(f"Fetching {days} days of {interval}-minute data for {symbol}")
        logger.info(f"Time range: {start_time} to {end_time}")

        # Convert to milliseconds
        current_end_ms = int(end_time.timestamp() * 1000)
        start_time_ms = int(start_time.timestamp() * 1000)

        # Calculate interval in milliseconds
        interval_minutes = int(interval)
        interval_ms = interval_minutes * 60 * 1000

        request_count = 0

        # Fetch data in batches (working backwards from present)
        while current_end_ms > start_time_ms and request_count < 20:  # Safety limit
            # Calculate batch start time (200 candles back)
            batch_start_ms = current_end_ms - (200 * interval_ms)
            batch_start_ms = max(batch_start_ms, start_time_ms)

            logger.info(
                f"Fetching batch {request_count + 1}: "
                f"{datetime.fromtimestamp(batch_start_ms / 1000)} to "
                f"{datetime.fromtimestamp(current_end_ms / 1000)}"
            )

            # Fetch klines for this batch
            klines = await self.fetch_klines(
                symbol=symbol,
                interval=interval,
                limit=200,
                start_time=batch_start_ms,
                end_time=current_end_ms,
            )

            if not klines:
                logger.warning(
                    f"No data received for batch {request_count + 1}, stopping"
                )
                break

            # Convert Bybit format to our format
            # Bybit returns: [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
            for k in klines:
                formatted_kline = {
                    "time": datetime.fromtimestamp(int(k[0]) / 1000),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "symbol": symbol,
                    "interval": interval,
                }
                all_klines.append(formatted_kline)

            logger.info(
                f"Batch {request_count + 1}: Fetched {len(klines)} candles "
                f"(Total: {len(all_klines)})"
            )

            # Move to next batch (go backwards in time)
            # Bybit returns newest first, so get oldest candle timestamp
            oldest_candle_time = int(klines[-1][0])  # Last in reversed list
            current_end_ms = oldest_candle_time - 1  # Move just before this candle

            request_count += 1

            # Rate limiting (Bybit allows 10 req/s for public endpoints)
            await asyncio.sleep(0.2)  # 200ms delay = 5 req/s (safe margin)

        # Sort by timestamp (ascending)
        all_klines.sort(key=lambda x: x["time"])

        logger.info(f"✅ Fetched total of {len(all_klines)} candles for {symbol}")

        if all_klines:
            logger.info(
                f"   Date range: {all_klines[0]['time']} to {all_klines[-1]['time']}"
            )
            logger.info(
                f"   Price range: ${min(k['close'] for k in all_klines):.2f} to "
                f"${max(k['close'] for k in all_klines):.2f}"
            )

        return all_klines

    async def close(self):
        """Close HTTP client"""
        await self.http_client.aclose()
        logger.info("Closed HTTP client")


class DataReplacer:
    """Replace test data in TimescaleDB with real data"""

    def __init__(self, db_config: Dict):
        """
        Initialize database connection configuration

        Args:
            db_config: Database connection parameters
        """
        self.db_config = db_config
        self.conn = None
        logger.info("Initialized Data Replacer")

    async def connect(self):
        """Connect to TimescaleDB"""
        try:
            self.conn = await asyncpg.connect(
                host=self.db_config["host"],
                port=self.db_config["port"],
                database=self.db_config["database"],
                user=self.db_config["user"],
                password=self.db_config["password"],
            )
            logger.info(
                f"✅ Connected to TimescaleDB at {self.db_config['host']}:{self.db_config['port']}"
            )
        except Exception as e:
            logger.error(f"❌ Failed to connect to database: {e}")
            raise

    async def verify_schema(self):
        """Verify database schema exists"""
        try:
            # Check if table exists
            result = await self.conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'market_data'
                    AND table_name = 'candles'
                )
                """
            )

            if result:
                logger.info("✅ Schema verified: market_data.candles table exists")

                # Show current data count
                count = await self.conn.fetchval(
                    "SELECT COUNT(*) FROM market_data.candles"
                )
                logger.info(f"   Current candle count: {count}")
            else:
                logger.error(
                    "❌ Schema error: market_data.candles table does not exist"
                )
                raise Exception("Database schema not initialized")

        except Exception as e:
            logger.error(f"Error verifying schema: {e}")
            raise

    async def clear_symbol_data(self, symbol: str, interval: str = "60"):
        """
        Delete existing test data for symbol

        Args:
            symbol: Trading pair to clear
            interval: Timeframe to clear
        """
        try:
            result = await self.conn.execute(
                "DELETE FROM market_data.candles WHERE symbol = $1 AND interval = $2",
                symbol,
                interval,
            )

            # Extract number of deleted rows
            deleted_count = result.split()[-1] if result else "0"
            logger.info(
                f"✅ Cleared {deleted_count} existing candles for {symbol} (interval: {interval})"
            )

        except Exception as e:
            logger.error(f"❌ Error clearing data for {symbol}: {e}")
            raise

    async def insert_klines(self, klines: List[Dict]):
        """
        Insert real klines into database

        Args:
            klines: List of kline dictionaries
        """
        if not klines:
            logger.warning("No klines to insert")
            return

        try:
            # Prepare data for bulk insert
            values = [
                (
                    k["time"],
                    k["symbol"],
                    k["interval"],
                    k["open"],
                    k["high"],
                    k["low"],
                    k["close"],
                    k["volume"],
                )
                for k in klines
            ]

            logger.info(f"Inserting {len(values)} candles into database...")

            # Bulk insert with ON CONFLICT to handle duplicates
            await self.conn.executemany(
                """
                INSERT INTO market_data.candles
                (time, symbol, interval, open, high, low, close, volume)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (time, symbol, interval) DO UPDATE
                SET open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume
                """,
                values,
            )

            logger.info(f"✅ Inserted {len(values)} candles successfully")

        except Exception as e:
            logger.error(f"❌ Error inserting klines: {e}")
            raise

    async def verify_insertion(self, symbol: str, interval: str = "60") -> Dict:
        """
        Verify data was inserted correctly

        Args:
            symbol: Trading pair to verify
            interval: Timeframe

        Returns:
            Dictionary with verification stats
        """
        try:
            # Count records
            count = await self.conn.fetchval(
                "SELECT COUNT(*) FROM market_data.candles WHERE symbol = $1 AND interval = $2",
                symbol,
                interval,
            )

            # Get date range
            date_range = await self.conn.fetchrow(
                """
                SELECT
                    MIN(time) as first_candle,
                    MAX(time) as last_candle,
                    MIN(close) as min_price,
                    MAX(close) as max_price,
                    AVG(close) as avg_price
                FROM market_data.candles
                WHERE symbol = $1 AND interval = $2
                """,
                symbol,
                interval,
            )

            stats = {
                "count": count,
                "first_candle": date_range["first_candle"],
                "last_candle": date_range["last_candle"],
                "min_price": float(date_range["min_price"]),
                "max_price": float(date_range["max_price"]),
                "avg_price": float(date_range["avg_price"]),
            }

            logger.info(f"\n📊 Data Verification for {symbol}:")
            logger.info(f"   Candle Count: {stats['count']}")
            logger.info(
                f"   Date Range: {stats['first_candle']} to {stats['last_candle']}"
            )
            logger.info(
                f"   Price Range: ${stats['min_price']:.2f} to ${stats['max_price']:.2f}"
            )
            logger.info(f"   Average Price: ${stats['avg_price']:.2f}")

            return stats

        except Exception as e:
            logger.error(f"Error verifying insertion: {e}")
            raise

    async def close(self):
        """Close database connection"""
        if self.conn:
            await self.conn.close()
            logger.info("✅ Database connection closed")


async def main():
    """Main function to fetch and replace data"""

    print("\n" + "=" * 80)
    print("REAL DATA FETCHER FOR BYBIT - BTC/ETH BACKTEST FIX")
    print("=" * 80)
    print("Purpose: Replace unrealistic test data with real Bybit market data")
    print("Target: BTCUSDT and ETHUSDT")
    print("Timeframe: 90 days of hourly candles")
    print("=" * 80 + "\n")

    # Database configuration (matching docker-compose)
    db_config = {
        "host": "localhost",
        "port": 5433,
        "database": "market_data",
        "user": "cryptobot",
        "password": "timescale_dev_password",
    }

    # Symbols to fetch (BTC and ETH only)
    symbols = ["BTCUSDT", "ETHUSDT"]

    # Initialize fetcher and replacer
    fetcher = BybitDataFetcher()
    replacer = DataReplacer(db_config)

    # Store results for summary
    results_summary = {}

    try:
        # Connect to database
        await replacer.connect()

        # Verify schema
        await replacer.verify_schema()

        print()

        # Process each symbol
        for symbol in symbols:
            print(f"\n{'=' * 80}")
            print(f"PROCESSING {symbol}")
            print(f"{'=' * 80}\n")

            # Step 1: Fetch real data from Bybit (90 days)
            logger.info("Step 1/4: Fetching 90 days of hourly data from Bybit...")
            klines = await fetcher.fetch_historical_range(
                symbol=symbol,
                days=90,
                interval="60",  # 1 hour
            )

            if not klines:
                logger.error(f"❌ No data fetched for {symbol}, skipping")
                results_summary[symbol] = {
                    "status": "failed",
                    "error": "No data fetched",
                }
                continue

            # Step 2: Clear old test data
            logger.info(f"\nStep 2/4: Clearing old test data for {symbol}...")
            await replacer.clear_symbol_data(symbol, "60")

            # Step 3: Insert real data
            logger.info(
                f"\nStep 3/4: Inserting {len(klines)} real candles for {symbol}..."
            )
            await replacer.insert_klines(klines)

            # Step 4: Verify insertion
            logger.info("\nStep 4/4: Verifying data integrity...")
            stats = await replacer.verify_insertion(symbol, "60")

            results_summary[symbol] = {
                "status": "success",
                "candles_inserted": len(klines),
                "date_range": f"{stats['first_candle']} to {stats['last_candle']}",
                "price_range": f"${stats['min_price']:.2f} to ${stats['max_price']:.2f}",
                "avg_price": f"${stats['avg_price']:.2f}",
            }

            print(
                f"\n✅ {symbol}: Successfully replaced with {len(klines)} real candles"
            )

        # Print summary
        print(f"\n\n{'=' * 80}")
        print("DATA REPLACEMENT COMPLETE - SUMMARY")
        print(f"{'=' * 80}\n")

        for symbol, result in results_summary.items():
            print(f"\n{symbol}:")
            if result["status"] == "success":
                print("  ✅ Status: Success")
                print(f"  📊 Candles: {result['candles_inserted']}")
                print(f"  📅 Date Range: {result['date_range']}")
                print(f"  💰 Price Range: {result['price_range']}")
                print(f"  📈 Average Price: {result['avg_price']}")
            else:
                print("  ❌ Status: Failed")
                print(f"  ⚠️  Error: {result['error']}")

        print(f"\n{'=' * 80}")
        print("NEXT STEPS:")
        print("=" * 80)
        print("1. Re-run backtests with real data:")
        print("   cd <repo>/services/technical-analysis/backtesting")
        print("   python3 run_backtest.py")
        print("\n2. Compare results with old test data")
        print("\n3. Analyze if BTC/ETH should be added to trading symbols")
        print("=" * 80 + "\n")

        # Save results to JSON
        results_file = str(_REPO_ROOT / "scripts/data_replacement_results.json")
        with open(results_file, "w") as f:
            json.dump(results_summary, f, indent=2, default=str)
        logger.info(f"📄 Results saved to: {results_file}")

    except Exception as e:
        logger.error(f"\n❌ FATAL ERROR: {e}", exc_info=True)
        raise

    finally:
        # Cleanup
        await fetcher.close()
        await replacer.close()


if __name__ == "__main__":
    # D-04 fail-fast: probe bybit-connector reachability BEFORE any argparse /
    # database work so operators get an actionable error within seconds when the
    # connector container is not up.
    asyncio.run(assert_connector_reachable())
    asyncio.run(main())
