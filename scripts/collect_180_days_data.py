#!/usr/bin/env python3
"""
Historical Data Collection Script for Strategy Validation
==========================================================
Purpose: Collect 180 days of hourly OHLCV data from Bybit API
         Properly handles pagination and API rate limits

Author: Data Researcher Agent
Date: 2025-12-11

This script:
1. Connects directly to Bybit V5 API (no service dependencies)
2. Fetches data in batches of 1000 candles with proper pagination
3. Saves data to CSV files for offline backtesting
4. Validates data completeness and quality

Usage:
    python collect_180_days_data.py
    python collect_180_days_data.py --symbols BTCUSDT ETHUSDT
    python collect_180_days_data.py --days 365 --interval 60

Requirements:
    pip install httpx pandas
"""

import asyncio
import argparse
import csv
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parent.parent
from typing import List, Dict, Any, Optional
import json
import time

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

try:
    import pandas as pd
except ImportError:
    pd = None
    print("WARNING: pandas not installed. CSV validation will be limited.")


# =============================================================================
# CONFIGURATION
# =============================================================================

# Bybit V5 API Base URL (mainnet for historical data)
BYBIT_API_URL = "https://api.bybit.com"

# Default symbols to collect
DEFAULT_SYMBOLS = [
    "BTCUSDT",   # Bitcoin
    "ETHUSDT",   # Ethereum
    "SOLUSDT",   # Solana
    "BNBUSDT",   # Binance Coin
    "XRPUSDT",   # Ripple
    "DOGEUSDT", # Dogecoin
    "ADAUSDT",   # Cardano
    "LTCUSDT",   # Litecoin
    "AVAXUSDT", # Avalanche
    "DOTUSDT",   # Polkadot
    "LINKUSDT", # Chainlink
    "MATICUSDT",# Polygon (POL)
    "SUIUSDT",   # Sui
    "ARBUSDT",   # Arbitrum
    "OPUSDT",    # Optimism
    "APTUSDT",   # Aptos
]

# Output directory for CSV files
OUTPUT_DIR = (_REPO_ROOT / 'data/historical')

# API rate limit (requests per second)
RATE_LIMIT_RPS = 5

# Maximum candles per API request (Bybit V5 limit)
MAX_CANDLES_PER_REQUEST = 1000


# =============================================================================
# DATA COLLECTION FUNCTIONS
# =============================================================================

async def fetch_klines_batch(
    client: httpx.AsyncClient,
    symbol: str,
    interval: str,
    start_time: int,
    end_time: int,
    limit: int = MAX_CANDLES_PER_REQUEST
) -> List[List[Any]]:
    """
    Fetch a single batch of klines from Bybit API

    Args:
        client: HTTP client instance
        symbol: Trading pair (e.g., BTCUSDT)
        interval: Candlestick interval in minutes (e.g., "60")
        start_time: Start timestamp in milliseconds
        end_time: End timestamp in milliseconds
        limit: Number of candles to fetch (max 1000)

    Returns:
        List of kline arrays [timestamp, open, high, low, close, volume, turnover]

    Raises:
        Exception: If API request fails
    """
    params = {
        "category": "linear",     # USDT perpetual contracts
        "symbol": symbol,
        "interval": interval,
        "start": start_time,
        "end": end_time,
        "limit": min(limit, MAX_CANDLES_PER_REQUEST)
    }

    try:
        response = await client.get(
            f"{BYBIT_API_URL}/v5/market/kline",
            params=params
        )

        if response.status_code != 200:
            print(f"  ERROR: HTTP {response.status_code} - {response.text[:200]}")
            return []

        data = response.json()

        if data.get("retCode") != 0:
            error_msg = data.get("retMsg", "Unknown error")
            print(f"  ERROR: Bybit API error - {error_msg}")
            return []

        klines = data.get("result", {}).get("list", [])
        return klines

    except httpx.RequestError as e:
        print(f"  ERROR: Network error - {e}")
        return []
    except json.JSONDecodeError as e:
        print(f"  ERROR: Invalid JSON response - {e}")
        return []


async def collect_symbol_data(
    symbol: str,
    days: int = 180,
    interval: str = "60",
    rate_limit_delay: float = 0.2
) -> Dict[str, Any]:
    """
    Collect historical data for a single symbol

    Args:
        symbol: Trading pair symbol
        days: Number of days of history to collect
        interval: Candlestick interval in minutes
        rate_limit_delay: Delay between API calls (seconds)

    Returns:
        Dictionary with collection results:
        {
            "symbol": str,
            "success": bool,
            "candles": int,
            "start_date": str,
            "end_date": str,
            "file_path": str,
            "error": str (if failed)
        }
    """
    print(f"\n{'='*60}")
    print(f"Collecting {days} days of {symbol} data (interval: {interval}m)")
    print(f"{'='*60}")

    all_klines = []

    # Calculate time range
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=days)

    # Convert to milliseconds
    end_ms = int(end_time.timestamp() * 1000)
    target_start_ms = int(start_time.timestamp() * 1000)

    # Track progress
    current_end_ms = end_ms
    batch_count = 0
    max_batches = (days * 24 // (MAX_CANDLES_PER_REQUEST * int(interval) // 60)) + 10

    async with httpx.AsyncClient(timeout=30.0) as client:
        while current_end_ms > target_start_ms and batch_count < max_batches:
            batch_count += 1

            # Fetch batch
            batch = await fetch_klines_batch(
                client=client,
                symbol=symbol,
                interval=interval,
                start_time=target_start_ms,
                end_time=current_end_ms,
                limit=MAX_CANDLES_PER_REQUEST
            )

            if not batch:
                print(f"  No more data available")
                break

            # Bybit returns newest first, so we need to reverse for chronological order
            all_klines.extend(batch)

            # Get oldest timestamp from this batch for next iteration
            oldest_ts = min(int(k[0]) for k in batch)
            newest_ts = max(int(k[0]) for k in batch)

            oldest_dt = datetime.fromtimestamp(oldest_ts / 1000)
            newest_dt = datetime.fromtimestamp(newest_ts / 1000)

            print(
                f"  Batch {batch_count}: {len(batch)} candles "
                f"({oldest_dt.strftime('%Y-%m-%d %H:%M')} to {newest_dt.strftime('%Y-%m-%d %H:%M')}), "
                f"total: {len(all_klines)}"
            )

            # Check if we've reached the target start
            if oldest_ts <= target_start_ms:
                print(f"  Reached target start date")
                break

            # Update end time for next batch (1 ms before oldest)
            current_end_ms = oldest_ts - 1

            # Rate limiting
            await asyncio.sleep(rate_limit_delay)

    # Deduplicate and sort
    unique_klines = {}
    for k in all_klines:
        ts = int(k[0])
        if ts not in unique_klines:
            unique_klines[ts] = k

    sorted_klines = sorted(unique_klines.values(), key=lambda x: int(x[0]))

    # Filter to target time range
    filtered_klines = [
        k for k in sorted_klines
        if target_start_ms <= int(k[0]) <= end_ms
    ]

    print(f"\nData collection complete:")
    print(f"  Total candles: {len(filtered_klines)}")
    print(f"  Expected candles (~): {days * 24}")

    if not filtered_klines:
        return {
            "symbol": symbol,
            "success": False,
            "candles": 0,
            "error": "No data collected"
        }

    # Get date range
    first_ts = int(filtered_klines[0][0])
    last_ts = int(filtered_klines[-1][0])
    first_date = datetime.fromtimestamp(first_ts / 1000)
    last_date = datetime.fromtimestamp(last_ts / 1000)

    print(f"  Date range: {first_date.strftime('%Y-%m-%d %H:%M')} to {last_date.strftime('%Y-%m-%d %H:%M')}")

    # Save to CSV
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = OUTPUT_DIR / f"{symbol}_{days}days_{datetime.now().strftime('%Y%m%d')}.csv"

    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        # Header
        writer.writerow([
            'timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'turnover'
        ])

        # Data rows
        for k in filtered_klines:
            ts = int(k[0])
            dt = datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %H:%M:%S')
            writer.writerow([
                ts,        # timestamp (ms)
                dt,        # datetime string
                k[1],      # open
                k[2],      # high
                k[3],      # low
                k[4],      # close
                k[5],      # volume
                k[6] if len(k) > 6 else 0  # turnover
            ])

    print(f"  Saved to: {filename}")

    return {
        "symbol": symbol,
        "success": True,
        "candles": len(filtered_klines),
        "expected": days * 24,
        "coverage": round(len(filtered_klines) / (days * 24) * 100, 1),
        "start_date": first_date.strftime('%Y-%m-%d %H:%M'),
        "end_date": last_date.strftime('%Y-%m-%d %H:%M'),
        "file_path": str(filename)
    }


async def validate_csv_file(filepath: Path) -> Dict[str, Any]:
    """
    Validate a collected CSV file for data quality

    Args:
        filepath: Path to CSV file

    Returns:
        Validation results dictionary
    """
    if pd is None:
        return {"valid": True, "note": "pandas not available for full validation"}

    try:
        df = pd.read_csv(filepath)

        # Basic checks
        rows = len(df)
        columns = list(df.columns)

        # Check for required columns
        required = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        missing = [c for c in required if c not in columns]

        # Check for gaps
        if 'timestamp' in df.columns:
            df['ts'] = pd.to_numeric(df['timestamp'])
            df = df.sort_values('ts')
            df['gap'] = df['ts'].diff()

            # For hourly data, expected gap is 3600000 ms (1 hour)
            expected_gap = 3600000
            large_gaps = df[df['gap'] > expected_gap * 1.5]  # 50% tolerance

        # Check for invalid values
        price_cols = ['open', 'high', 'low', 'close']
        invalid_prices = 0
        for col in price_cols:
            if col in df.columns:
                invalid_prices += (df[col] <= 0).sum()

        # Check high >= low
        hl_violations = 0
        if 'high' in df.columns and 'low' in df.columns:
            hl_violations = (df['high'] < df['low']).sum()

        return {
            "valid": len(missing) == 0 and invalid_prices == 0 and hl_violations == 0,
            "rows": rows,
            "columns": columns,
            "missing_columns": missing,
            "gaps_detected": len(large_gaps) if 'large_gaps' in dir() else 0,
            "invalid_prices": invalid_prices,
            "high_low_violations": hl_violations
        }

    except Exception as e:
        return {
            "valid": False,
            "error": str(e)
        }


async def main(symbols: List[str], days: int, interval: str):
    """
    Main collection function

    Args:
        symbols: List of symbols to collect
        days: Number of days of history
        interval: Candlestick interval
    """
    print("=" * 70)
    print(f"HISTORICAL DATA COLLECTION - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Days: {days}")
    print(f"Interval: {interval} minutes")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 70)

    results = []
    start_time = time.time()

    for i, symbol in enumerate(symbols, 1):
        print(f"\n[{i}/{len(symbols)}] Processing {symbol}...")

        try:
            result = await collect_symbol_data(
                symbol=symbol,
                days=days,
                interval=interval,
                rate_limit_delay=1.0 / RATE_LIMIT_RPS
            )
            results.append(result)

            # Validate the file
            if result.get("success") and result.get("file_path"):
                validation = await validate_csv_file(Path(result["file_path"]))
                result["validation"] = validation

        except Exception as e:
            print(f"  FAILED: {e}")
            results.append({
                "symbol": symbol,
                "success": False,
                "error": str(e)
            })

        # Delay between symbols to avoid rate limiting
        if i < len(symbols):
            print(f"\nWaiting 2 seconds before next symbol...")
            await asyncio.sleep(2.0)

    # Print summary
    elapsed = time.time() - start_time
    print("\n")
    print("=" * 70)
    print("COLLECTION SUMMARY")
    print("=" * 70)

    successful = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]

    print(f"\nTotal symbols: {len(symbols)}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")
    print(f"Elapsed time: {elapsed:.1f} seconds")

    if successful:
        print(f"\nSuccessful collections:")
        for r in successful:
            coverage = r.get('coverage', 'N/A')
            print(f"  {r['symbol']}: {r['candles']:,} candles ({coverage}% coverage)")

    if failed:
        print(f"\nFailed collections:")
        for r in failed:
            print(f"  {r['symbol']}: {r.get('error', 'Unknown error')}")

    # Save summary to JSON
    summary_file = OUTPUT_DIR / f"collection_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(summary_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "days": days,
            "interval": interval,
            "results": results,
            "successful": len(successful),
            "failed": len(failed),
            "elapsed_seconds": elapsed
        }, f, indent=2)

    print(f"\nSummary saved to: {summary_file}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Collect historical OHLCV data from Bybit for strategy validation"
    )

    parser.add_argument(
        "--symbols",
        nargs="+",
        default=DEFAULT_SYMBOLS,
        help=f"Symbols to collect (default: {', '.join(DEFAULT_SYMBOLS[:5])}...)"
    )

    parser.add_argument(
        "--days",
        type=int,
        default=180,
        help="Number of days of history to collect (default: 180)"
    )

    parser.add_argument(
        "--interval",
        type=str,
        default="60",
        help="Candlestick interval in minutes (default: 60 = 1 hour)"
    )

    args = parser.parse_args()

    # Run collection
    try:
        asyncio.run(main(
            symbols=args.symbols,
            days=args.days,
            interval=args.interval
        ))
    except KeyboardInterrupt:
        print("\nCollection interrupted by user")
        sys.exit(1)
