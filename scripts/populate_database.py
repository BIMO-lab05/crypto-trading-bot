#!/usr/bin/env python3
"""
Database Population Script
Purpose: Directly populate TimescaleDB with historical market data
Usage: python3 scripts/populate_database.py
"""

import asyncio
import asyncpg
import httpx
import sys
from datetime import datetime, timezone
from typing import List, Dict

# Database configuration
DB_CONFIG = {
    "host": "localhost",
    "port": 5433,  # TimescaleDB port
    "database": "market_data",
    "user": "cryptobot",
    "password": "timescale_dev_password",
}

# Bybit Connector URL
BYBIT_URL = "http://localhost:8001"

# Trading pairs to collect
SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "DOGEUSDT",
]

# Interval to collect (60 = 1 hour)
INTERVAL = "60"
LIMIT = 720  # 30 days of hourly data


async def fetch_klines_from_bybit(client: httpx.AsyncClient, symbol: str) -> List[Dict]:
    """
    Fetch historical klines from Bybit Connector

    Args:
        client: HTTP client
        symbol: Trading pair

    Returns:
        List of kline dictionaries
    """
    try:
        url = f"{BYBIT_URL}/api/v1/market/kline"
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": INTERVAL,
            "limit": LIMIT
        }

        response = await client.get(url, params=params, timeout=30.0)

        if response.status_code == 200:
            data = response.json()
            klines = data.get("data", [])
            print(f"  ├─ Fetched {len(klines)} candles from Bybit")
            return klines
        elif response.status_code == 429:
            print(f"  ├─ ⚠️ Rate limited, waiting 60s...")
            await asyncio.sleep(60)
            return []
        else:
            print(f"  ├─ ❌ Error: HTTP {response.status_code}")
            return []

    except Exception as e:
        print(f"  ├─ ❌ Exception: {e}")
        return []


def convert_bybit_kline_to_db_format(kline: List, symbol: str) -> Dict:
    """
    Convert Bybit kline format to database format

    Bybit format: [timestamp, open, high, low, close, volume, turnover]
    DB format: {time, symbol, interval, open, high, low, close, volume, ...}

    Args:
        kline: Bybit kline array
        symbol: Trading pair

    Returns:
        Dictionary ready for database insertion
    """
    try:
        # Bybit returns timestamp in milliseconds
        timestamp_ms = int(kline[0])
        timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

        return {
            "time": timestamp,
            "symbol": symbol,
            "interval": INTERVAL,
            "open": float(kline[1]),
            "high": float(kline[2]),
            "low": float(kline[3]),
            "close": float(kline[4]),
            "volume": float(kline[5]),
            "quote_volume": float(kline[6]) if len(kline) > 6 else 0.0,
            "trades_count": 0,  # Not provided by Bybit
        }
    except Exception as e:
        print(f"  ├─ ⚠️ Error converting kline: {e}")
        return None


async def insert_klines_to_db(pool: asyncpg.Pool, klines: List[Dict]) -> int:
    """
    Insert klines into TimescaleDB using UPSERT

    Args:
        pool: Database connection pool
        klines: List of kline dictionaries

    Returns:
        Number of rows inserted/updated
    """
    if not klines:
        return 0

    try:
        async with pool.acquire() as conn:
            # Use INSERT ... ON CONFLICT DO UPDATE for upsert
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
                    volume = EXCLUDED.volume,
                    quote_volume = EXCLUDED.quote_volume,
                    trades_count = EXCLUDED.trades_count
            """

            # Prepare data for batch insert
            records = [
                (
                    k["time"],
                    k["symbol"],
                    k["interval"],
                    k["open"],
                    k["high"],
                    k["low"],
                    k["close"],
                    k["volume"],
                    k["quote_volume"],
                    k["trades_count"]
                )
                for k in klines
            ]

            # Execute batch insert
            await conn.executemany(query, records)

            return len(records)

    except Exception as e:
        print(f"  └─ ❌ Database error: {e}")
        return 0


async def verify_data_in_db(pool: asyncpg.Pool) -> Dict:
    """
    Verify data was inserted correctly

    Args:
        pool: Database connection pool

    Returns:
        Dictionary with verification results
    """
    try:
        async with pool.acquire() as conn:
            # Count total candles
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM market_data.candles"
            )

            # Count by symbol
            symbol_counts = await conn.fetch("""
                SELECT symbol, COUNT(*) as count,
                       MIN(time) as earliest,
                       MAX(time) as latest
                FROM market_data.candles
                GROUP BY symbol
                ORDER BY symbol
            """)

            return {
                "total": total,
                "by_symbol": [
                    {
                        "symbol": row["symbol"],
                        "count": row["count"],
                        "earliest": row["earliest"],
                        "latest": row["latest"]
                    }
                    for row in symbol_counts
                ]
            }
    except Exception as e:
        print(f"❌ Verification error: {e}")
        return {"total": 0, "by_symbol": []}


async def main():
    """
    Main function: Fetch data from Bybit and store in TimescaleDB
    """
    print("\n" + "="*70)
    print("🚀 CRYPTO BOT - DATABASE POPULATION")
    print("="*70)
    print(f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    print(f"Symbols: {len(SYMBOLS)}")
    print(f"Interval: {INTERVAL} minutes")
    print(f"Limit: {LIMIT} candles per symbol")
    print("="*70 + "\n")

    # Connect to database
    print("📊 Connecting to TimescaleDB...")
    try:
        pool = await asyncpg.create_pool(**DB_CONFIG)
        print("  └─ ✅ Connected successfully\n")
    except Exception as e:
        print(f"  └─ ❌ Connection failed: {e}\n")
        sys.exit(1)

    try:
        total_inserted = 0

        # Create HTTP client
        async with httpx.AsyncClient() as client:
            # Process each symbol
            for i, symbol in enumerate(SYMBOLS, 1):
                print(f"[{i}/{len(SYMBOLS)}] Processing {symbol}...")

                # Fetch klines from Bybit
                bybit_klines = await fetch_klines_from_bybit(client, symbol)

                if not bybit_klines:
                    print(f"  └─ ⚠️ No data fetched\n")
                    continue

                # Convert to database format
                db_klines = []
                for kline in bybit_klines:
                    converted = convert_bybit_kline_to_db_format(kline, symbol)
                    if converted:
                        db_klines.append(converted)

                print(f"  ├─ Converted {len(db_klines)} candles to DB format")

                # Insert into database
                inserted = await insert_klines_to_db(pool, db_klines)
                print(f"  └─ ✅ Inserted {inserted} candles into database\n")

                total_inserted += inserted

                # Wait between symbols to avoid rate limits
                if i < len(SYMBOLS):
                    await asyncio.sleep(3)

        # Verify data
        print("-"*70)
        print("📊 Verifying data in database...\n")
        verification = await verify_data_in_db(pool)

        print(f"Total candles in database: {verification['total']}")
        print("\nBreakdown by symbol:")
        for item in verification['by_symbol']:
            print(f"  {item['symbol']:10} - {item['count']:4} candles "
                  f"(from {item['earliest']} to {item['latest']})")

        print("\n" + "="*70)
        print("✅ DATABASE POPULATION COMPLETE!")
        print("="*70 + "\n")

    finally:
        # Close database connection
        await pool.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
