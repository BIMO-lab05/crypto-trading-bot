#!/usr/bin/env python3
"""Test database connection and data availability"""
import asyncio
import asyncpg

async def test_db():
    conn = await asyncpg.connect(
        host="crypto-bot-timescaledb",
        port=5432,
        database="market_data",
        user="cryptobot",
        password="timescale_dev_password"
    )

    # Check data availability
    query = """
    SELECT
        symbol,
        COUNT(*) as count,
        MIN(time) as first,
        MAX(time) as last,
        EXTRACT(DAY FROM MAX(time) - MIN(time)) as days
    FROM market_data.candles
    WHERE symbol IN ('BTCUSDT', 'ETHUSDT')
    GROUP BY symbol
    ORDER BY symbol
    """

    symbols = await conn.fetch(query)
    await conn.close()

    print("=" * 70)
    print("Database Connection Test - Data Availability")
    print("=" * 70)

    for row in symbols:
        symbol = row['symbol']
        count = row['count']
        first = row['first']
        last = row['last']
        days = int(row['days']) if row['days'] else 0

        print(f"\n{symbol}:")
        print(f"  - Total candles: {count}")
        print(f"  - First data: {first}")
        print(f"  - Last data: {last}")
        print(f"  - Days of data: {days}")
        print(f"  - Status: {'✓ READY' if days >= 30 else '✗ INSUFFICIENT'}")

    print("\n" + "=" * 70)

if __name__ == "__main__":
    asyncio.run(test_db())
