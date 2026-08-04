#!/usr/bin/env python3
"""
Download 24-Month Data for Missing Symbols
Downloads hourly candle data for symbols that need GRU training

Symbols: LINKUSDT, OPUSDT, POLUSDT, SUIUSDT
Target: 24 months of 1H data for consistency with other models

BC-02 (Phase 13): Routes through bybit-connector REST. Fail-fasts (exit 2)
if BYBIT_CONNECTOR_URL is unreachable. See
.planning/phases/13-bybit-connector-market-data-centralization/.
"""

import asyncio
import os
import sys
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("data_download_missing.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# Configuration
SYMBOLS = ["LINKUSDT", "OPUSDT", "POLUSDT", "SUIUSDT"]
INTERVAL = "60"  # 60 minutes = 1H
MONTHS_BACK = 24  # 24 months of data
OUTPUT_DIR = _REPO_ROOT / "data/ml_training"

# BC-02: Route through bybit-connector REST (no direct Bybit access).
# Host-friendly default; compose env override to http://bybit-connector:8001.
BYBIT_CONNECTOR_URL = os.getenv("BYBIT_CONNECTOR_URL", "http://localhost:8001")
KLINE_ENDPOINT = "/api/v1/market/kline"

# Create output directory
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def assert_connector_reachable() -> None:
    """BC-02 / D-04: fail-fast with operator-readable error if bybit-connector down."""
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


def _check_or_exit() -> None:
    """Synchronous wrapper for the connector reachability check."""
    asyncio.run(assert_connector_reachable())


async def fetch_klines(
    client: httpx.AsyncClient,
    symbol: str,
    interval: str,
    start_time: int,
    end_time: int,
    limit: int = 1000,
) -> Optional[list]:
    """
    Fetch klines via bybit-connector REST.

    Args:
        client: httpx.AsyncClient configured against BYBIT_CONNECTOR_URL
        symbol: Trading symbol
        interval: Candle interval in minutes
        start_time: Start timestamp (ms)
        end_time: End timestamp (ms)
        limit: Number of candles to fetch (max 1000)

    Returns:
        List of klines or None on error
    """
    try:
        params = {
            "category": "spot",
            "symbol": symbol,
            "interval": interval,
            "start": start_time,
            "end": end_time,
            "limit": limit,
        }

        response = await client.get(KLINE_ENDPOINT, params=params)
        if response.status_code == 200:
            # BC-02 parser swap: wrapper-shape {success, data} (was raw Bybit shape).
            # httpx .json() is sync (unlike aiohttp); see RESEARCH Pitfall 6.
            data = response.json()
            if data.get("success"):
                raw = data.get("data", {})
                if isinstance(raw, dict):
                    return raw.get("list", [])
                return raw or []
            else:
                logger.error(f"bybit-connector non-success response: {data}")
                return None
        else:
            logger.error(f"HTTP error: {response.status_code}")
            return None

    except Exception as e:
        logger.error(f"Error fetching klines: {e}")
        return None


async def download_symbol_data(symbol: str, months: int = 24) -> pd.DataFrame:
    """
    Download historical data for a symbol

    Args:
        symbol: Trading symbol
        months: Number of months of historical data

    Returns:
        DataFrame with OHLCV data
    """
    logger.info(f"\n{'=' * 80}")
    logger.info(f"Downloading {months}-month data for {symbol}")
    logger.info(f"{'=' * 80}")

    # Calculate time range
    end_time = datetime.now()
    start_time = end_time - timedelta(days=months * 30)

    logger.info(f"Date range: {start_time} to {end_time}")

    # Convert to milliseconds
    start_ms = int(start_time.timestamp() * 1000)
    end_ms = int(end_time.timestamp() * 1000)

    all_klines = []
    current_start = start_ms

    async with httpx.AsyncClient(base_url=BYBIT_CONNECTOR_URL, timeout=30.0) as client:
        batch = 0
        while current_start < end_ms:
            batch += 1

            # Calculate batch end time (max 1000 candles = ~41 days for 1H)
            batch_end = min(current_start + (1000 * 60 * 60 * 1000), end_ms)

            logger.info(
                f"Batch {batch}: Fetching {datetime.fromtimestamp(current_start / 1000)} to {datetime.fromtimestamp(batch_end / 1000)}"
            )

            # Fetch data
            klines = await fetch_klines(
                client,
                symbol=symbol,
                interval=INTERVAL,
                start_time=current_start,
                end_time=batch_end,
                limit=1000,
            )

            if klines:
                all_klines.extend(klines)
                logger.info(
                    f"  -> Got {len(klines)} candles (total: {len(all_klines)})"
                )

                # Move to next batch
                if len(klines) < 1000:
                    # Got less than limit, we're done
                    break
                else:
                    # Move start time forward
                    last_candle_time = int(
                        klines[-1][0]
                    )  # Bybit returns timestamp in first field
                    current_start = last_candle_time + 1

                # Rate limiting - be nice to the connector
                await asyncio.sleep(0.2)
            else:
                logger.warning(f"Failed to fetch batch {batch}, retrying...")
                await asyncio.sleep(1)
                continue

    if not all_klines:
        logger.error(f"No data downloaded for {symbol}")
        return pd.DataFrame()

    # Convert to DataFrame
    # Bybit format: [timestamp, open, high, low, close, volume, turnover]
    df = pd.DataFrame(
        all_klines,
        columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"],
    )

    # Convert types
    df["timestamp"] = pd.to_datetime(df["timestamp"].astype(float), unit="ms")
    for col in ["open", "high", "low", "close", "volume", "turnover"]:
        df[col] = df[col].astype(float)

    # Sort by timestamp
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Remove duplicates
    df = df.drop_duplicates(subset=["timestamp"], keep="first")

    # Keep only required columns
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]

    logger.info(f"\nDownloaded {len(df)} candles for {symbol}")
    logger.info(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    logger.info(f"Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")

    return df


async def main():
    """Download data for all missing symbols"""

    logger.info("\n" + "=" * 100)
    logger.info("DATA DOWNLOAD - MISSING SYMBOLS FOR GRU TRAINING")
    logger.info("=" * 100)
    logger.info(f"Symbols: {', '.join(SYMBOLS)}")
    logger.info(f"Interval: {INTERVAL} minutes (1H)")
    logger.info(f"History: {MONTHS_BACK} months")
    logger.info(f"Output directory: {OUTPUT_DIR}")
    logger.info(f"bybit-connector: {BYBIT_CONNECTOR_URL}")
    logger.info("=" * 100 + "\n")

    start_time = time.time()
    results = {}

    # Download each symbol
    for i, symbol in enumerate(SYMBOLS, 1):
        logger.info(f"\n[{i}/{len(SYMBOLS)}] Processing {symbol}...")

        try:
            # Download data
            df = await download_symbol_data(symbol, MONTHS_BACK)

            if df.empty:
                logger.error(f"{symbol} - No data downloaded")
                results[symbol] = {"status": "FAILED", "reason": "No data"}
                continue

            # Save to CSV
            today = datetime.now().strftime("%Y%m%d")
            output_file = OUTPUT_DIR / f"{symbol}_1H_24months_{today}.csv"
            df.to_csv(output_file, index=False)

            logger.info(f"Saved to: {output_file}")
            logger.info(f"   File size: {output_file.stat().st_size / 1024:.2f} KB")

            results[symbol] = {
                "status": "SUCCESS",
                "candles": len(df),
                "file": str(output_file),
                "date_range": f"{df['timestamp'].min()} to {df['timestamp'].max()}",
            }

        except Exception as e:
            logger.error(f"{symbol} failed: {e}", exc_info=True)
            results[symbol] = {"status": "FAILED", "error": str(e)}

        # Pause between symbols
        if i < len(SYMBOLS):
            await asyncio.sleep(1)

    # Summary
    total_time = time.time() - start_time

    logger.info("\n" + "=" * 100)
    logger.info("DOWNLOAD SUMMARY")
    logger.info("=" * 100)
    logger.info(f"Total time: {total_time:.1f} seconds ({total_time / 60:.1f} minutes)")
    logger.info("")

    successful = sum(1 for r in results.values() if r["status"] == "SUCCESS")
    failed = sum(1 for r in results.values() if r["status"] == "FAILED")

    logger.info("Results:")
    logger.info(f"  Successful: {successful}/{len(SYMBOLS)}")
    logger.info(f"  Failed: {failed}/{len(SYMBOLS)}")
    logger.info("")

    # Detailed results
    logger.info("Detailed Results:")
    logger.info("-" * 100)

    for symbol, result in results.items():
        if result["status"] == "SUCCESS":
            logger.info(
                f"{symbol:<12} {result['candles']:,} candles | {result['file']}"
            )
        else:
            logger.info(
                f"{symbol:<12} FAILED - {result.get('error', result.get('reason', 'Unknown'))}"
            )

    logger.info("=" * 100)
    logger.info("\nData download complete!\n")

    # List all files in output directory
    logger.info("\nAll 24-month data files:")
    for csv_file in sorted(OUTPUT_DIR.glob("*_1H_24months_*.csv")):
        size_kb = csv_file.stat().st_size / 1024
        logger.info(f"  - {csv_file.name} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    # BC-02 / D-04: fail-fast BEFORE any other work (incl. logging setup messages).
    _check_or_exit()
    logger.info("Starting data download...")
    asyncio.run(main())
