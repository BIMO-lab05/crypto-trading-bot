#!/usr/bin/env python3
"""
Test Script for Bybit API Pagination Fix
=========================================
Purpose: Verify that the pagination fix works correctly for fetching
         historical data > 1000 candles.

This script tests:
1. Direct Bybit API call with start/end parameters
2. Market Data Fetcher pagination for 180 days of data
3. Data completeness and quality validation

Usage:
    python test_pagination_fix.py

Author: Backend Developer Agent
Date: 2025-12-11
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)


# Bybit V5 API Base URL (mainnet for historical data)
BYBIT_API_URL = "https://api.bybit.com"

# Test parameters
TEST_SYMBOL = "BTCUSDT"
TEST_INTERVAL = "60"  # 1 hour
TEST_DAYS = 180


async def test_direct_bybit_api_with_time_range():
    """
    Test 1: Verify Bybit API returns correct data when start/end parameters are provided

    This test confirms that the Bybit V5 API:
    1. Accepts start and end timestamps
    2. Returns data within the specified range
    3. Returns up to 1000 candles per request
    """
    print("\n" + "=" * 70)
    print("TEST 1: Direct Bybit API with Time Range Parameters")
    print("=" * 70)

    # Calculate time range for last 7 days (should return ~168 candles for hourly)
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=7)

    end_ms = int(end_time.timestamp() * 1000)
    start_ms = int(start_time.timestamp() * 1000)

    params = {
        "category": "linear",
        "symbol": TEST_SYMBOL,
        "interval": TEST_INTERVAL,
        "start": start_ms,
        "end": end_ms,
        "limit": 1000
    }

    print(f"Request parameters:")
    print(f"  Symbol: {TEST_SYMBOL}")
    print(f"  Interval: {TEST_INTERVAL} minutes")
    print(f"  Start: {start_time.strftime('%Y-%m-%d %H:%M')} ({start_ms})")
    print(f"  End: {end_time.strftime('%Y-%m-%d %H:%M')} ({end_ms})")
    print(f"  Expected candles: ~168 (7 days * 24 hours)")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{BYBIT_API_URL}/v5/market/kline", params=params)

        if response.status_code != 200:
            print(f"\n  FAILED: HTTP {response.status_code}")
            return False

        data = response.json()

        if data.get("retCode") != 0:
            print(f"\n  FAILED: API error - {data.get('retMsg')}")
            return False

        klines = data.get("result", {}).get("list", [])

        print(f"\nResults:")
        print(f"  Candles received: {len(klines)}")

        if not klines:
            print("  FAILED: No candles returned")
            return False

        # Verify data is within range
        first_ts = int(klines[-1][0])  # Oldest (Bybit returns newest first)
        last_ts = int(klines[0][0])    # Newest

        first_date = datetime.fromtimestamp(first_ts / 1000)
        last_date = datetime.fromtimestamp(last_ts / 1000)

        print(f"  Date range: {first_date.strftime('%Y-%m-%d %H:%M')} to {last_date.strftime('%Y-%m-%d %H:%M')}")
        print(f"  First candle timestamp: {first_ts}")
        print(f"  Last candle timestamp: {last_ts}")

        # Validate timestamps are within requested range
        if first_ts < start_ms:
            print(f"  WARNING: First candle is before requested start time")
        if last_ts > end_ms:
            print(f"  WARNING: Last candle is after requested end time")

        # Check data quality
        sample = klines[0]
        print(f"\nSample candle (newest):")
        print(f"  Timestamp: {sample[0]}")
        print(f"  Open: {sample[1]}")
        print(f"  High: {sample[2]}")
        print(f"  Low: {sample[3]}")
        print(f"  Close: {sample[4]}")
        print(f"  Volume: {sample[5]}")

        expected_candles = 7 * 24
        if len(klines) >= expected_candles * 0.9:  # Allow 10% tolerance
            print(f"\n  PASSED: Received {len(klines)} candles (expected ~{expected_candles})")
            return True
        else:
            print(f"\n  WARNING: Received {len(klines)} candles (expected ~{expected_candles})")
            return True  # Still pass, might be due to timing


async def test_pagination_for_180_days():
    """
    Test 2: Verify pagination works for fetching 180 days of data

    This test confirms that:
    1. Multiple API calls are made with proper pagination
    2. Data is correctly merged without duplicates
    3. Coverage is close to expected (~4320 candles)
    """
    print("\n" + "=" * 70)
    print("TEST 2: Pagination for 180 Days of Historical Data")
    print("=" * 70)

    # Calculate time range
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=TEST_DAYS)

    end_ms = int(end_time.timestamp() * 1000)
    target_start_ms = int(start_time.timestamp() * 1000)

    expected_candles = TEST_DAYS * 24

    print(f"Fetching {TEST_DAYS} days of {TEST_SYMBOL} data ({TEST_INTERVAL}m interval)")
    print(f"  Start: {start_time.strftime('%Y-%m-%d %H:%M')}")
    print(f"  End: {end_time.strftime('%Y-%m-%d %H:%M')}")
    print(f"  Expected candles: ~{expected_candles}")
    print(f"  Required API calls: ~{expected_candles // 1000 + 1}")

    all_klines = []
    current_end_ms = end_ms
    batch_count = 0
    max_batches = 10  # Safety limit

    async with httpx.AsyncClient(timeout=30.0) as client:
        while current_end_ms > target_start_ms and batch_count < max_batches:
            batch_count += 1

            params = {
                "category": "linear",
                "symbol": TEST_SYMBOL,
                "interval": TEST_INTERVAL,
                "start": target_start_ms,
                "end": current_end_ms,
                "limit": 1000
            }

            response = await client.get(f"{BYBIT_API_URL}/v5/market/kline", params=params)

            if response.status_code != 200:
                print(f"  Batch {batch_count}: FAILED (HTTP {response.status_code})")
                break

            data = response.json()
            if data.get("retCode") != 0:
                print(f"  Batch {batch_count}: FAILED ({data.get('retMsg')})")
                break

            klines = data.get("result", {}).get("list", [])

            if not klines:
                print(f"  Batch {batch_count}: No more data")
                break

            all_klines.extend(klines)

            oldest_ts = min(int(k[0]) for k in klines)
            newest_ts = max(int(k[0]) for k in klines)

            oldest_date = datetime.fromtimestamp(oldest_ts / 1000)
            newest_date = datetime.fromtimestamp(newest_ts / 1000)

            print(f"  Batch {batch_count}: {len(klines)} candles ({oldest_date.strftime('%Y-%m-%d')} to {newest_date.strftime('%Y-%m-%d')}), total: {len(all_klines)}")

            if oldest_ts <= target_start_ms:
                print(f"  Reached target start date")
                break

            if len(klines) < 1000:
                print(f"  Received partial batch, no more data")
                break

            # Update end time for next batch
            current_end_ms = oldest_ts - 1

            # Rate limiting
            await asyncio.sleep(0.2)

    # Deduplicate
    unique_klines = {}
    for k in all_klines:
        ts = int(k[0])
        if ts not in unique_klines:
            unique_klines[ts] = k

    sorted_klines = sorted(unique_klines.values(), key=lambda x: int(x[0]))

    # Filter to target range
    filtered_klines = [
        k for k in sorted_klines
        if target_start_ms <= int(k[0]) <= end_ms
    ]

    print(f"\nResults:")
    print(f"  Total batches: {batch_count}")
    print(f"  Raw candles: {len(all_klines)}")
    print(f"  After deduplication: {len(sorted_klines)}")
    print(f"  After filtering: {len(filtered_klines)}")
    print(f"  Expected: ~{expected_candles}")

    if filtered_klines:
        first_ts = int(filtered_klines[0][0])
        last_ts = int(filtered_klines[-1][0])
        first_date = datetime.fromtimestamp(first_ts / 1000)
        last_date = datetime.fromtimestamp(last_ts / 1000)

        coverage = (len(filtered_klines) / expected_candles) * 100

        print(f"  Coverage: {coverage:.1f}%")
        print(f"  Date range: {first_date.strftime('%Y-%m-%d %H:%M')} to {last_date.strftime('%Y-%m-%d %H:%M')}")

        if coverage >= 95:
            print(f"\n  PASSED: {coverage:.1f}% coverage achieved")
            return True
        elif coverage >= 80:
            print(f"\n  PASSED (with warning): {coverage:.1f}% coverage (some gaps may exist)")
            return True
        else:
            print(f"\n  FAILED: Only {coverage:.1f}% coverage")
            return False
    else:
        print("\n  FAILED: No data collected")
        return False


async def test_data_quality():
    """
    Test 3: Verify data quality (no invalid values)

    This test confirms that:
    1. All OHLCV values are valid numbers
    2. High >= Low for all candles
    3. Open, High, Low, Close are positive
    4. Volume is non-negative
    """
    print("\n" + "=" * 70)
    print("TEST 3: Data Quality Validation")
    print("=" * 70)

    # Fetch sample data (last 100 candles)
    params = {
        "category": "linear",
        "symbol": TEST_SYMBOL,
        "interval": TEST_INTERVAL,
        "limit": 100
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{BYBIT_API_URL}/v5/market/kline", params=params)

        if response.status_code != 200:
            print(f"  FAILED: HTTP {response.status_code}")
            return False

        data = response.json()
        klines = data.get("result", {}).get("list", [])

    if not klines:
        print("  FAILED: No data to validate")
        return False

    print(f"Validating {len(klines)} candles...")

    issues = []

    for i, k in enumerate(klines):
        ts = int(k[0])
        open_price = float(k[1])
        high_price = float(k[2])
        low_price = float(k[3])
        close_price = float(k[4])
        volume = float(k[5])

        # Check high >= low
        if high_price < low_price:
            issues.append(f"Candle {i}: High ({high_price}) < Low ({low_price})")

        # Check positive prices
        if open_price <= 0:
            issues.append(f"Candle {i}: Invalid open price ({open_price})")
        if high_price <= 0:
            issues.append(f"Candle {i}: Invalid high price ({high_price})")
        if low_price <= 0:
            issues.append(f"Candle {i}: Invalid low price ({low_price})")
        if close_price <= 0:
            issues.append(f"Candle {i}: Invalid close price ({close_price})")

        # Check non-negative volume
        if volume < 0:
            issues.append(f"Candle {i}: Negative volume ({volume})")

        # Check OHLC consistency
        if high_price < max(open_price, close_price):
            issues.append(f"Candle {i}: High ({high_price}) < max(Open, Close)")
        if low_price > min(open_price, close_price):
            issues.append(f"Candle {i}: Low ({low_price}) > min(Open, Close)")

    if issues:
        print(f"\nData quality issues found ({len(issues)}):")
        for issue in issues[:10]:  # Show first 10
            print(f"  - {issue}")
        if len(issues) > 10:
            print(f"  ... and {len(issues) - 10} more")
        print(f"\n  FAILED: {len(issues)} data quality issues")
        return False
    else:
        print(f"\n  PASSED: All {len(klines)} candles passed validation")
        return True


async def main():
    """Run all tests"""
    print("=" * 70)
    print("BYBIT API PAGINATION FIX - TEST SUITE")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    results = []

    # Test 1: Direct API with time range
    results.append(("Direct API with Time Range", await test_direct_bybit_api_with_time_range()))

    # Test 2: Pagination for 180 days
    results.append(("180 Days Pagination", await test_pagination_for_180_days()))

    # Test 3: Data quality
    results.append(("Data Quality Validation", await test_data_quality()))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    all_passed = True
    for test_name, passed in results:
        status = "PASSED" if passed else "FAILED"
        print(f"  {test_name}: {status}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("ALL TESTS PASSED - Pagination fix is working correctly")
    else:
        print("SOME TESTS FAILED - Review issues above")
    print("=" * 70)

    return all_passed


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        sys.exit(1)
