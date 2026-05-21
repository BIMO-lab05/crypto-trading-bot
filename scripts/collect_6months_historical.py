#!/usr/bin/env python3
"""
Historical Data Collection Script
Purpose: Fetch 6 months of hourly OHLCV data for all trading symbols
Phase 2.1.3 - Support/Resistance Strategy Validation

This script collects 180 days of historical data for:
- SOLUSDT, BNBUSDT, ADAUSDT (existing symbols)
- APTUSDT, DOTUSDT, LTCUSDT, POLUSDT (newly added symbols)

Phase 13 (BC-02): routes through the bybit-connector service at
``$BYBIT_CONNECTOR_URL/api/v1/market/kline`` (default ``http://localhost:8001``)
instead of the legacy market-data-service ``/api/v1/klines/{symbol}`` proxy.
Exits 2 with an operator-readable error when the connector is unreachable
(D-04 fail-fast).
"""

import asyncio
import os
import httpx
import sys
from datetime import datetime, timedelta
from typing import List, Dict
import pandas as pd

# Phase 13 BC-02: bybit-connector endpoint. Host-friendly default; the compose
# stack overrides this to ``http://bybit-connector:8001`` via environment.
BYBIT_CONNECTOR_URL = os.getenv("BYBIT_CONNECTOR_URL", "http://localhost:8001")

# All trading symbols
SYMBOLS = [
    "SOLUSDT",  # Solana
    "BNBUSDT",  # BNB
    "ADAUSDT",  # Cardano
    "APTUSDT",  # Aptos (NEW)
    "DOTUSDT",  # Polkadot (NEW)
    "LTCUSDT",  # Litecoin (NEW)
    "POLUSDT",  # Polygon (NEW)
]

# Collection parameters
DAYS_TO_COLLECT = 180  # 6 months
INTERVAL_MINUTES = 60  # 1 hour candles
BATCH_SIZE = 1000  # Fetch 1000 candles per API call


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


async def fetch_historical_data(
    symbol: str,
    start_time: datetime,
    end_time: datetime,
    interval: int = 60,
    limit: int = 1000,
) -> List[Dict]:
    """
    Fetch historical OHLCV data via bybit-connector.

    Args:
        symbol: Trading symbol (e.g., SOLUSDT)
        start_time: Start datetime
        end_time: End datetime
        interval: Candle interval in minutes (default: 60)
        limit: Number of candles per request (max: 1000)

    Returns:
        List of OHLCV candle dictionaries with a ``timestamp`` key in ms.
    """
    all_candles = []
    current_start = start_time
    interval_str = str(interval)

    async with httpx.AsyncClient(timeout=30.0, base_url=BYBIT_CONNECTOR_URL) as client:
        while current_start < end_time:
            # Convert to timestamp (Bybit V5 expects ms)
            start_ts = int(current_start.timestamp() * 1000)
            end_ts = int(end_time.timestamp() * 1000)

            # bybit-connector kline endpoint (V5 list shape preserved through wrapper)
            url = "/api/v1/market/kline"
            params = {
                "category": "linear",
                "symbol": symbol,
                "interval": interval_str,
                "limit": limit,
                "start": start_ts,
                "end": end_ts,
            }

            try:
                print(
                    f"  Fetching {symbol}: {current_start.strftime('%Y-%m-%d %H:%M')} - {limit} candles",
                    end="",
                )
                response = await client.get(url, params=params)
                response.raise_for_status()

                # bybit-connector wrapper shape: {"success": bool, "data": {"list": [...]}}
                response_data = response.json()
                if not response_data.get("success"):
                    print(f" - connector error: {response_data!r}")
                    break

                raw_list = response_data.get("data", {}).get("list", [])
                if not raw_list:
                    print(" - No data")
                    break

                # Bybit V5 kline row: [startTime, open, high, low, close, volume, turnover]
                # Normalize each row to the dict shape the rest of this script expects.
                candles = [
                    {
                        "timestamp": int(row[0]),
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "volume": float(row[5]),
                    }
                    for row in raw_list
                ]
                # V5 returns newest-first; sort ascending so the next-batch cursor logic
                # below picks the youngest candle for `current_start` advancement.
                candles.sort(key=lambda c: c["timestamp"])

                # Add candles to collection
                all_candles.extend(candles)
                print(f" - Got {len(candles)} candles")

                # Move to next batch from the most recent candle in this batch.
                last_candle_time = datetime.fromtimestamp(
                    candles[-1]["timestamp"] / 1000
                )
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
    print(f"\n{'=' * 80}")
    print(f"Collecting {days} days of data for {symbol}")
    print(f"{'=' * 80}")

    # Calculate time range
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)

    print(
        f"Time range: {start_time.strftime('%Y-%m-%d')} to {end_time.strftime('%Y-%m-%d')}"
    )
    print("Fetching hourly candles...")

    # Fetch data
    candles = await fetch_historical_data(
        symbol=symbol,
        start_time=start_time,
        end_time=end_time,
        interval=INTERVAL_MINUTES,
        limit=BATCH_SIZE,
    )

    if not candles:
        print(f"❌ No data collected for {symbol}")
        return pd.DataFrame()

    # Convert to DataFrame
    df = pd.DataFrame(candles)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.sort_values("timestamp")

    # Remove duplicates
    df = df.drop_duplicates(subset=["timestamp"])

    print(f"\n✅ Collected {len(df)} candles for {symbol}")
    print(f"   Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"   Price range: ${df['low'].min():.2f} - ${df['high'].max():.2f}")
    print(f"   Total volume: {df['volume'].sum():,.0f}")

    return df


async def verify_data_availability():
    """Verify bybit-connector is running and accessible.

    BC-02 (Phase 13): The script now sources klines from bybit-connector instead
    of the legacy market-data-service proxy. ``assert_connector_reachable()``
    exits 2 on failure (D-04 fail-fast contract), so we just return True here
    once it returns.
    """
    print(f"Verifying bybit-connector availability at {BYBIT_CONNECTOR_URL}...")
    await assert_connector_reachable()
    print("✅ bybit-connector is reachable")
    return True


async def main():
    """Main data collection workflow"""
    print("\n" + "=" * 80)
    print("HISTORICAL DATA COLLECTION - 6 MONTHS")
    print("Phase 2.1.3 - Support/Resistance Strategy Validation")
    print("=" * 80)
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
    print("\n" + "=" * 80)
    print("COLLECTION SUMMARY")
    print("=" * 80)

    total_candles = 0
    successful_symbols = 0
    failed_symbols = []

    for symbol, df in results.items():
        if df.empty:
            print(f"❌ {symbol}: NO DATA")
            failed_symbols.append(symbol)
        else:
            candles = len(df)
            days_covered = (df["timestamp"].max() - df["timestamp"].min()).days
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
    print(f"\n{'=' * 80}")
    print("WALK-FORWARD VALIDATION READINESS")
    print(f"{'=' * 80}")
    print("Walk-forward requirements:")
    print("  - Training window: 60 days")
    print("  - Test window: 14 days")
    print("  - Minimum total: 74 days")
    print(f"\nData collected: {DAYS_TO_COLLECT} days")

    if DAYS_TO_COLLECT >= 74:
        print("✅ SUFFICIENT DATA for walk-forward validation")
        print("\nNext steps:")
        print(
            "1. Run walk-forward validation: python3 scripts/test_sr_strategy_walkforward.py"
        )
        print("2. Review results and compare with research_optimized strategy")
        print("3. Deploy S/R strategy if validation passes")
        return 0
    else:
        print(f"⚠ WARNING: Only {DAYS_TO_COLLECT} days collected")
        print("   Recommended: At least 180 days for robust validation")
        return 1


if __name__ == "__main__":
    # D-04 fail-fast: probe bybit-connector reachability BEFORE the main workflow
    # so operators get an actionable error within seconds when the connector
    # container is not up. assert_connector_reachable() calls sys.exit(2) itself
    # on failure (operator-readable "docker compose ... bybit-connector" hint).
    asyncio.run(assert_connector_reachable())
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
