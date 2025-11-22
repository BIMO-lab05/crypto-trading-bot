#!/usr/bin/env python3
"""
Manual Data Collection Script
Purpose: Collect historical market data with proper rate limiting
Usage: python3 scripts/manual_data_collection.py
"""

import asyncio
import httpx
import sys
from datetime import datetime

# Configuration
MARKET_DATA_URL = "http://localhost:8002"
BYBIT_CONNECTOR_URL = "http://localhost:8001"

SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "DOGEUSDT",
]

# Only collect 1-hour candles to reduce API calls
INTERVALS = ["60"]  # 1 hour

# Days of historical data to collect
DAYS = 30


async def collect_data_for_symbol(client: httpx.AsyncClient, symbol: str, interval: str, days: int):
    """
    Collect data for a single symbol and interval

    Args:
        client: HTTP client
        symbol: Trading pair
        interval: Candle interval
        days: Days of history

    Returns:
        dict: Result of collection
    """
    try:
        print(f"  ├─ Fetching {symbol} ({interval}) - {days} days...")

        # Call bybit-connector directly to get historical klines
        url = f"{BYBIT_CONNECTOR_URL}/api/v1/market/historical-klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "days": days
        }

        response = await client.get(url, params=params, timeout=60.0)

        if response.status_code == 200:
            data = response.json()
            count = len(data.get("klines", []))
            print(f"  ├─ ✅ Fetched {count} candles for {symbol}")
            return {"symbol": symbol, "interval": interval, "success": True, "count": count}
        elif response.status_code == 429:
            print(f"  ├─ ⚠️ Rate limited for {symbol}, waiting 60s...")
            await asyncio.sleep(60)
            return {"symbol": symbol, "interval": interval, "success": False, "error": "rate_limit"}
        else:
            print(f"  ├─ ❌ Failed for {symbol}: {response.status_code}")
            return {"symbol": symbol, "interval": interval, "success": False, "error": f"status_{response.status_code}"}

    except Exception as e:
        print(f"  ├─ ❌ Error for {symbol}: {e}")
        return {"symbol": symbol, "interval": interval, "success": False, "error": str(e)}


async def save_to_database(client: httpx.AsyncClient, symbol: str, interval: str, klines: list):
    """
    Save collected klines to database via market-data-service

    Args:
        client: HTTP client
        symbol: Trading pair
        interval: Candle interval
        klines: List of kline data

    Returns:
        bool: Success status
    """
    try:
        # This would need to be implemented in market-data-service
        # For now, we'll use the historical collection endpoint
        pass
    except Exception as e:
        print(f"  └─ Error saving {symbol}: {e}")
        return False


async def main():
    """
    Main collection function with proper rate limiting
    """
    print("\n" + "="*70)
    print("🚀 CRYPTO BOT - MANUAL DATA COLLECTION")
    print("="*70)
    print(f"Symbols: {len(SYMBOLS)}")
    print(f"Intervals: {INTERVALS}")
    print(f"Historical Days: {DAYS}")
    print(f"Total API Calls: {len(SYMBOLS) * len(INTERVALS)}")
    print("="*70 + "\n")

    async with httpx.AsyncClient() as client:
        results = []

        # Check services health
        print("📊 Checking services health...")
        try:
            market_response = await client.get(f"{MARKET_DATA_URL}/health", timeout=5.0)
            if market_response.status_code == 200:
                print("  ├─ ✅ Market Data Service: Healthy")
            else:
                print(f"  ├─ ❌ Market Data Service: Unhealthy ({market_response.status_code})")
        except Exception as e:
            print(f"  ├─ ❌ Market Data Service: Error - {e}")

        try:
            bybit_response = await client.get(f"{BYBIT_CONNECTOR_URL}/health", timeout=5.0)
            if bybit_response.status_code == 200:
                print("  └─ ✅ Bybit Connector: Healthy")
            else:
                print(f"  └─ ❌ Bybit Connector: Unhealthy ({bybit_response.status_code})")
        except Exception as e:
            print(f"  └─ ❌ Bybit Connector: Error - {e}")

        print("\n" + "-"*70)
        print("📈 Starting data collection...")
        print("-"*70 + "\n")

        # Collect data with rate limiting
        for i, symbol in enumerate(SYMBOLS, 1):
            print(f"[{i}/{len(SYMBOLS)}] Processing {symbol}...")

            for interval in INTERVALS:
                result = await collect_data_for_symbol(client, symbol, interval, DAYS)
                results.append(result)

                # Wait between requests to avoid rate limits
                # Rate limit is 30/minute, so wait at least 2 seconds
                await asyncio.sleep(3)

            # Extra wait between symbols
            if i < len(SYMBOLS):
                print(f"  └─ Waiting 5s before next symbol...\n")
                await asyncio.sleep(5)

        # Summary
        print("\n" + "="*70)
        print("📊 COLLECTION SUMMARY")
        print("="*70)

        success_count = sum(1 for r in results if r.get("success"))
        failure_count = len(results) - success_count
        total_candles = sum(r.get("count", 0) for r in results if r.get("success"))

        print(f"Total Attempts: {len(results)}")
        print(f"✅ Successful: {success_count}")
        print(f"❌ Failed: {failure_count}")
        print(f"📊 Total Candles Fetched: {total_candles}")

        if failure_count > 0:
            print("\n⚠️ Failed Symbols:")
            for r in results:
                if not r.get("success"):
                    print(f"  - {r['symbol']} ({r['interval']}): {r.get('error', 'unknown')}")

        print("\n" + "="*70)
        print("✅ Collection Complete!")
        print("="*70 + "\n")

        # Now we need to actually save the data
        # Since the API endpoints have issues, we'll use a direct database approach
        print("⚠️ Note: Data fetched but needs to be stored in database")
        print("   Run the database storage script separately")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Collection interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        sys.exit(1)
