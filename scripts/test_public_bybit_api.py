#!/usr/bin/env python3
"""
Test Public Bybit API for Extended Historical Data
Purpose: Verify if public API can provide 90 days of historical data
"""

import httpx
import asyncio
from datetime import datetime, timedelta, timezone

async def test_public_bybit():
    """Test fetching from public Bybit API"""

    print("\n" + "="*80)
    print("TESTING PUBLIC BYBIT API FOR EXTENDED HISTORICAL DATA")
    print("="*80 + "\n")

    client = httpx.AsyncClient(timeout=30.0)

    # Public API endpoint
    api_url = "https://api.bybit.com/v5/market/klines"

    # Test symbol
    symbol = "BNBUSDT"
    interval = "60"  # 1 hour

    # Calculate 90 days ago in milliseconds
    now = datetime.now(timezone.utc)
    ninety_days_ago = now - timedelta(days=90)
    start_time = int(ninety_days_ago.timestamp() * 1000)

    print(f"Symbol: {symbol}")
    print(f"Interval: {interval} minutes (1 hour)")
    print(f"Target: 90 days of data")
    print(f"Start time: {ninety_days_ago} ({start_time}ms)")
    print(f"End time: {now} ({int(now.timestamp() * 1000)}ms)")
    print()

    try:
        # Fetch first batch
        print("Fetching first 200 candles from public API...")
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "limit": 200,
            "start": start_time
        }

        response = await client.get(api_url, params=params)
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"Response status: {data.get('retCode')}")
            print(f"Message: {data.get('retMsg')}")

            klines = data.get('result', {}).get('list', [])
            print(f"Candles received: {len(klines)}")

            if klines:
                # Show first and last candle
                first = klines[0]
                last = klines[-1]

                first_time = datetime.fromtimestamp(int(first[0])/1000, tz=timezone.utc)
                last_time = datetime.fromtimestamp(int(last[0])/1000, tz=timezone.utc)

                print(f"\nFirst candle: {first_time}")
                print(f"First price: {first[4]} USDT")
                print(f"\nLast candle: {last_time}")
                print(f"Last price: {last[4]} USDT")

                days_covered = (last_time - first_time).days
                print(f"\nDays covered: {days_covered}")
                print(f"Candles per day: {len(klines) / max(1, days_covered):.1f}")

                if days_covered >= 90:
                    print("\n✅ SUCCESS: Public API provides 90+ days of data!")
                else:
                    print(f"\n⚠️ WARNING: Public API only provides {days_covered} days")
        else:
            print(f"Error: HTTP {response.status_code}")
            print(response.text)

    except Exception as e:
        print(f"Error: {e}")

    finally:
        await client.aclose()

    print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    asyncio.run(test_public_bybit())
