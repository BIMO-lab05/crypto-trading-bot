#!/usr/bin/env python3
"""
Collect 6 Months Historical Data for ML Training
Purpose: Download 180 days of 60m kline data for GRU model training via bybit-connector.
Saves data to CSV files in /backtesting/data/ directory.

Phase 13 / BC-02: routes through bybit-connector REST (no direct Bybit URLs);
fail-fast (D-04) if connector unreachable.
"""

import asyncio
import os  # noqa: F401  -- used by BYBIT_CONNECTOR_URL os.getenv below; guard against autoflake
import sys
import httpx
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import logging
from typing import List

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Phase 13 / BC-02: route through bybit-connector REST (no direct Bybit URLs).
BYBIT_CONNECTOR_URL = os.getenv("BYBIT_CONNECTOR_URL", "http://localhost:8001")


def assert_connector_reachable() -> None:
    """D-04 fail-fast: exit 2 with operator-readable error if connector unreachable.

    Runs BEFORE any other __main__ logic so `tests/integration/test_scripts_fail_fast.py`
    (no-args invocation) triggers the probe.
    """

    async def _probe() -> None:
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

    asyncio.run(_probe())


class BybitDataCollector:
    """Collect historical kline data via bybit-connector and save to CSV"""

    def __init__(self):
        self.base_url = BYBIT_CONNECTOR_URL
        self.http_client = None
        self.data_dir = Path(__file__).parent.parent / "backtesting" / "data"
        self.data_dir.mkdir(exist_ok=True, parents=True)
        logger.info(f"Data directory: {self.data_dir}")

    async def initialize(self):
        """Initialize HTTP client"""
        self.http_client = httpx.AsyncClient(timeout=30.0)
        logger.info("HTTP client initialized")

    async def close(self):
        """Close HTTP client"""
        if self.http_client:
            await self.http_client.aclose()

    async def fetch_klines(
        self,
        symbol: str,
        interval: str = "60",
        limit: int = 200,
        start_time: int = None,
        end_time: int = None,
    ) -> List[List]:
        """
        Fetch kline data from Bybit API

        Args:
            symbol: Trading pair (e.g., SOLUSDT)
            interval: Timeframe (60 = 1 hour)
            limit: Number of candles (max 200)
            start_time: Start timestamp in milliseconds
            end_time: End timestamp in milliseconds

        Returns:
            List of klines: [timestamp, open, high, low, close, volume, turnover]
        """
        url = f"{self.base_url}/api/v1/market/kline"

        params = {
            "category": "linear",  # USDT perpetual
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }

        if start_time:
            params["start"] = start_time
        if end_time:
            params["end"] = end_time

        try:
            response = await self.http_client.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            if not data.get("success"):
                logger.error(
                    f"bybit-connector error: {data.get('error') or data.get('message')}"
                )
                return []

            klines = data.get("data", {}).get("list", [])
            logger.debug(f"Fetched {len(klines)} candles for {symbol}")
            return klines

        except Exception as e:
            logger.error(f"Error fetching klines: {e}")
            return []

    async def collect_symbol_data(
        self, symbol: str, days: int = 180, interval: str = "60"
    ) -> pd.DataFrame:
        """
        Collect full historical data for a symbol

        Args:
            symbol: Trading symbol
            days: Number of days to collect
            interval: Timeframe in minutes

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        logger.info(f"Collecting {days} days of {interval}m data for {symbol}...")

        # Calculate time range
        end_time = int(datetime.now().timestamp() * 1000)
        start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)

        all_klines = []
        batch_count = 0

        # Fetch data in batches (Bybit limit: 200 candles per request)
        current_end = end_time

        while True:
            # Fetch batch
            klines = await self.fetch_klines(
                symbol=symbol, interval=interval, limit=200, end_time=current_end
            )

            if not klines:
                logger.warning(f"No data returned for batch {batch_count + 1}")
                break

            # Add to collection
            all_klines.extend(klines)
            batch_count += 1

            # Bybit returns data in reverse chronological order
            # Get oldest timestamp from this batch
            oldest_timestamp = int(klines[-1][0])

            # Check if we've collected enough data
            if oldest_timestamp <= start_time:
                logger.info(f"Reached target date. Collected {batch_count} batches")
                break

            # Update end time for next batch
            current_end = oldest_timestamp - 1

            # Rate limiting
            await asyncio.sleep(0.5)

            if batch_count % 5 == 0:
                logger.info(
                    f"Collected {batch_count} batches ({len(all_klines)} candles)..."
                )

        logger.info(
            f"Total collected: {len(all_klines)} candles in {batch_count} batches"
        )

        # Convert to DataFrame
        df = pd.DataFrame(
            all_klines,
            columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"],
        )

        # Convert timestamp to datetime
        df["timestamp"] = pd.to_datetime(df["timestamp"].astype(int), unit="ms")

        # Convert price columns to float
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        # Sort by timestamp (oldest first)
        df = df.sort_values("timestamp").reset_index(drop=True)

        # Remove duplicates
        df = df.drop_duplicates(subset=["timestamp"])

        # Drop turnover column (not needed for ML training)
        df = df.drop(columns=["turnover"])

        logger.info(f"Cleaned data: {len(df)} unique candles")

        return df

    async def save_to_csv(
        self, df: pd.DataFrame, symbol: str, days: int, interval: str
    ):
        """Save DataFrame to CSV file"""
        filename = f"{symbol}_{interval}m_{days}d_bybit.csv"
        filepath = self.data_dir / filename

        df.to_csv(filepath, index=False)
        file_size = filepath.stat().st_size / 1024  # KB

        logger.info(f"Saved {len(df)} candles to {filename} ({file_size:.1f} KB)")

        # Show data range
        start_date = df["timestamp"].min()
        end_date = df["timestamp"].max()
        logger.info(f"Data range: {start_date} to {end_date}")

    async def collect_all_symbols(
        self, symbols: List[str], days: int = 180, interval: str = "60"
    ):
        """Collect data for multiple symbols"""
        logger.info(f"Starting data collection for {len(symbols)} symbols...")
        logger.info(f"Target: {days} days of {interval}m kline data")
        print("=" * 80)

        await self.initialize()

        try:
            for i, symbol in enumerate(symbols, 1):
                print(f"\n[{i}/{len(symbols)}] Processing {symbol}...")
                print("-" * 80)

                try:
                    # Collect data
                    df = await self.collect_symbol_data(symbol, days, interval)

                    if len(df) == 0:
                        logger.warning(f"No data collected for {symbol}")
                        continue

                    # Save to CSV
                    await self.save_to_csv(df, symbol, days, interval)

                    print(f"✅ {symbol} complete: {len(df)} candles")

                except Exception as e:
                    logger.error(f"Failed to collect {symbol}: {e}")
                    print(f"❌ {symbol} failed: {e}")

                # Delay between symbols to avoid rate limiting
                if i < len(symbols):
                    logger.info("Waiting 2 seconds before next symbol...")
                    await asyncio.sleep(2)

        finally:
            await self.close()

        print("\n" + "=" * 80)
        print("DATA COLLECTION COMPLETE")
        print("=" * 80)


async def main():
    """Main execution"""
    # Target symbols for ML training
    symbols = ["BNBUSDT", "SOLUSDT", "ADAUSDT"]

    # Create collector
    collector = BybitDataCollector()

    # Collect 6 months (180 days) of 60-minute kline data
    await collector.collect_all_symbols(symbols=symbols, days=180, interval="60")

    print(f"\n📊 Data saved to: {collector.data_dir}")
    print("\nNext steps:")
    print("1. Verify data files in /backtesting/data/")
    print("2. Re-train LSTM model with 6 months of data")
    print("3. Expect improved test accuracy (target: >55%)")


if __name__ == "__main__":
    # D-04 fail-fast: BEFORE any other __main__ logic so no-args invocation triggers the probe.
    assert_connector_reachable()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Collection interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback

        traceback.print_exc()
