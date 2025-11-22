#!/usr/bin/env python3
"""
Database Connection Test for TimescaleDB
Purpose: Verify connectivity and inspect available historical data
"""

import asyncio
import asyncpg
from datetime import datetime
import sys


async def test_connection():
    """Test TimescaleDB connection and show available data"""

    # Database configuration (matching docker-compose settings)
    db_config = {
        'host': 'localhost',
        'port': 5433,  # External port from docker-compose
        'database': 'market_data',
        'user': 'cryptobot',
        'password': 'timescale_dev_password'
    }

    print("="*80)
    print("TimescaleDB Connection Test")
    print("="*80)
    print(f"Connecting to: {db_config['host']}:{db_config['port']}")
    print(f"Database: {db_config['database']}")
    print(f"User: {db_config['user']}")
    print()

    try:
        # Connect to database
        conn = await asyncpg.connect(
            host=db_config['host'],
            port=db_config['port'],
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password']
        )

        print("✓ Successfully connected to TimescaleDB!")
        print()

        # Query available data
        query = """
            SELECT
                symbol,
                interval,
                COUNT(*) as candle_count,
                MIN(time) as earliest_time,
                MAX(time) as latest_time,
                EXTRACT(EPOCH FROM (MAX(time) - MIN(time))) / 86400 as days_of_data
            FROM market_data.candles
            GROUP BY symbol, interval
            ORDER BY symbol, interval;
        """

        print("Available Historical Data:")
        print("-" * 80)

        rows = await conn.fetch(query)

        if not rows:
            print("⚠ No data found in market_data.candles table")
            await conn.close()
            return False

        print(f"{'Symbol':<12} {'Interval':<10} {'Candles':<10} {'Earliest':<20} {'Latest':<20} {'Days':<8}")
        print("-" * 80)

        total_candles = 0
        symbols = set()

        for row in rows:
            symbol = row['symbol']
            interval = row['interval']
            count = row['candle_count']
            earliest = row['earliest_time'].strftime('%Y-%m-%d %H:%M')
            latest = row['latest_time'].strftime('%Y-%m-%d %H:%M')
            days = round(row['days_of_data'], 1)

            print(f"{symbol:<12} {interval:<10} {count:<10} {earliest:<20} {latest:<20} {days:<8}")

            total_candles += count
            symbols.add(symbol)

        print("-" * 80)
        print(f"Total Symbols: {len(symbols)}")
        print(f"Total Candles: {total_candles:,}")
        print()

        # Test query for a specific symbol (BTCUSDT)
        print("Sample Data (BTCUSDT, last 5 candles):")
        print("-" * 80)

        sample_query = """
            SELECT time, open, high, low, close, volume
            FROM market_data.candles
            WHERE symbol = 'BTCUSDT' AND interval = '60'
            ORDER BY time DESC
            LIMIT 5;
        """

        sample_rows = await conn.fetch(sample_query)

        if sample_rows:
            print(f"{'Time':<20} {'Open':<12} {'High':<12} {'Low':<12} {'Close':<12} {'Volume':<15}")
            print("-" * 80)

            for row in sample_rows:
                time_str = row['time'].strftime('%Y-%m-%d %H:%M')
                open_price = f"{row['open']:.2f}"
                high_price = f"{row['high']:.2f}"
                low_price = f"{row['low']:.2f}"
                close_price = f"{row['close']:.2f}"
                volume = f"{row['volume']:.2f}"

                print(f"{time_str:<20} {open_price:<12} {high_price:<12} {low_price:<12} {close_price:<12} {volume:<15}")

        print()
        print("="*80)
        print("✓ Database connection test completed successfully!")
        print("="*80)

        await conn.close()
        return True

    except asyncpg.exceptions.InvalidPasswordError:
        print("✗ Authentication failed: Invalid password")
        return False
    except asyncpg.exceptions.InvalidCatalogNameError:
        print("✗ Database 'market_data' does not exist")
        return False
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_connection())
    sys.exit(0 if success else 1)
