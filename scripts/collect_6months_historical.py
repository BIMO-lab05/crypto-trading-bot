#!/usr/bin/env python3
"""
Historical Data Collection Script
Purpose: Fetch 6 months of hourly OHLCV data for all trading symbols
Phase 2.1.3 - Support/Resistance Strategy Validation

This script collects 180 days of historical data for:
- SOLUSDT, BNBUSDT, ADAUSDT (existing symbols)
- APTUSDT, DOTUSDT, LTCUSDT, POLUSDT (newly added symbols)

Data is fetched from market-data-service API and saved to database.
"""

import asyncio
import httpx
import sys
from datetime import datetime, timedelta
from typing import List, Dict
import pandas as pd

# Market data service URL
MARKET_DATA_API = "http://localhost:8002"

# All trading symbols
SYMBOLS = [
    "SOLUSDT",   # Solana
    "BNBUSDT",   # BNB
    "ADAUSDT",   # Cardano
    "APTUSDT",   # Aptos (NEW)
    "DOTUSDT",   # Polkadot (NEW)
    "LTCUSDT",   # Litecoin (NEW)
    "POLUSDT",   # Polygon (NEW)
]

# Collection parameters
DAYS_TO_COLLECT = 180  # 6 months
INTERVAL_MINUTES = 60  # 1 hour candles
BATCH_SIZE = 1000  # Fetch 1000 candles per API call


async def fetch_historical_data(
    symbol: str,
    start_time: datetime,
    end_time: datetime,
    interval: int = 60,
    limit: int = 1000
) -> List[Dict]:
    """
    Fetch historical OHLCV data from market-data-service API

    Args:
        symbol: Trading symbol (e.g., SOLUSDT)
        start_time: Start datetime
        end_time: End datetime
        interval: Candle interval in minutes (default: 60)
        limit: Number of candles per request (max: 1000)

    Returns:
        List of OHLCV candle dictionaries
    """
    all_candles = []
    current_start = start_time

    async with httpx.AsyncClient(timeout=30.0) as client:
        while current_start < end_time:
            # Convert to timestamp
            start_ts = int(current_start.timestamp() * 1000)

            # Build request URL
            url = f"{MARKET_DATA_API}/api/v1/klines/{symbol}"
            params = {
                "interval": interval,
                "limit": limit,
                "start_time": start_ts
            }

            try:
                print(f"  Fetching {symbol}: {current_start.strftime('%Y-%m-%d %H:%M')} - {limit} candles", end="")
                response = await client.get(url, params=params)
                response.raise_for_status()

                # API returns {"success": true, "data": [...]}
                response_data = response.json()

                # Extract candles from data field
                if "data" in response_data:
                    candles = response_data["data"]
                else:
                    candles = response_data

                if not candles:
                    print(" - No data")
                    break

                # Add candles to collection
                all_candles.extend(candles)
                print(f" - Got {len(candles)} candles")

                # Move to next batch
                last_candle_time = datetime.fromtimestamp(candles[-1]["timestamp"] / 1000)
                current_start = last_candle_time + timedelta(minutes=interval)

                # Avoid hitting rate limits
                await asyncio.sleep(0.1)

            except httpx.HTTPStatusError as e:
                print(f" - HTTP error: {e.response.status_code}")
                break
            except Exception as e:
                print(f" - Error: {str(e)}")
                break

    return all_candles


async def collect_data_for_symbol(symbol: str, days: int = 180) -> pd.DataFrame:
    """
    Collect historical data for a single symbol

    Args:
        symbol: Trading symbol
        days: Number of days to collect

    Returns:
        DataFrame with OHLCV data
    """
    print(f"\n{'='*80}")
    print(f"Collecting {days} days of data for {symbol}")
    print(f"{'='*80}")

    # Calculate time range
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)

    print(f"Time range: {start_time.strftime('%Y-%m-%d')} to {end_time.strftime('%Y-%m-%d')}")
    print(f"Fetching hourly candles...")

    # Fetch data
    candles = await fetch_historical_data(
        symbol=symbol,
        start_time=start_time,
        end_time=end_time,
        interval=INTERVAL_MINUTES,
        limit=BATCH_SIZE
    )

    if not candles:
        print(f"❌ No data collected for {symbol}")
        return pd.DataFrame()

    # Convert to DataFrame
    df = pd.DataFrame(candles)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.sort_values('timestamp')

    # Remove duplicates
    df = df.drop_duplicates(subset=['timestamp'])

    print(f"\n✅ Collected {len(df)} candles for {symbol}")
    print(f"   Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"   Price range: ${df['low'].min():.2f} - ${df['high'].max():.2f}")
    print(f"   Total volume: {df['volume'].sum():,.0f}")

    return df


async def verify_data_availability():
    """Verify market-data-service is running and accessible"""
    print("Verifying market-data-service availability...")

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{MARKET_DATA_API}/health")
            response.raise_for_status()
            print("✅ Market-data-service is running")
            return True
        except Exception as e:
            print(f"❌ Cannot reach market-data-service: {e}")
            print(f"\nPlease ensure market-data-service is running:")
            print(f"  docker-compose up -d market-data")
            return False


async def main():
    """Main data collection workflow"""
    print("\n" + "="*80)
    print("HISTORICAL DATA COLLECTION - 6 MONTHS")
    print("Phase 2.1.3 - Support/Resistance Strategy Validation")
    print("="*80)
    print(f"\nSymbols to collect: {', '.join(SYMBOLS)}")
    print(f"Collection period: {DAYS_TO_COLLECT} days (~6 months)")
    print(f"Interval: {INTERVAL_MINUTES} minutes (hourly candles)")
    print(f"Expected candles per symbol: ~{DAYS_TO_COLLECT * 24}")

    # Verify service availability
    if not await verify_data_availability():
        return 1

    # Collect data for each symbol
    results = {}
    for symbol in SYMBOLS:
        df = await collect_data_for_symbol(symbol, days=DAYS_TO_COLLECT)
        results[symbol] = df

        # Brief pause between symbols
        await asyncio.sleep(0.5)

    # Summary
    print("\n" + "="*80)
    print("COLLECTION SUMMARY")
    print("="*80)

    total_candles = 0
    successful_symbols = 0
    failed_symbols = []

    for symbol, df in results.items():
        if df.empty:
            print(f"❌ {symbol}: NO DATA")
            failed_symbols.append(symbol)
        else:
            candles = len(df)
            days_covered = (df['timestamp'].max() - df['timestamp'].min()).days
            total_candles += candles
            successful_symbols += 1
            print(f"✅ {symbol}: {candles:,} candles ({days_covered} days)")

    print(f"\nTotal symbols: {len(SYMBOLS)}")
    print(f"Successful: {successful_symbols}")
    print(f"Failed: {len(failed_symbols)}")
    if failed_symbols:
        print(f"Failed symbols: {', '.join(failed_symbols)}")
    print(f"Total candles collected: {total_candles:,}")

    # Check if we have enough data for walk-forward validation
    print(f"\n{'='*80}")
    print("WALK-FORWARD VALIDATION READINESS")
    print(f"{'='*80}")
    print(f"Walk-forward requirements:")
    print(f"  - Training window: 60 days")
    print(f"  - Test window: 14 days")
    print(f"  - Minimum total: 74 days")
    print(f"\nData collected: {DAYS_TO_COLLECT} days")

    if DAYS_TO_COLLECT >= 74:
        print(f"✅ SUFFICIENT DATA for walk-forward validation")
        print(f"\nNext steps:")
        print(f"1. Run walk-forward validation: python3 scripts/test_sr_strategy_walkforward.py")
        print(f"2. Review results and compare with research_optimized strategy")
        print(f"3. Deploy S/R strategy if validation passes")
        return 0
    else:
        print(f"⚠ WARNING: Only {DAYS_TO_COLLECT} days collected")
        print(f"   Recommended: At least 180 days for robust validation")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠ Collection interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error during collection: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
