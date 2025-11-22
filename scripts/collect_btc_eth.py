#!/usr/bin/env python3
"""Quick script to collect BTC and ETH data after schema fix"""
import asyncio
import asyncpg
import httpx
from datetime import datetime, timezone

DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "database": "market_data",
    "user": "cryptobot",
    "password": "timescale_dev_password",
}

BYBIT_URL = "http://localhost:8001"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INTERVAL = "60"
LIMIT = 720

async def main():
    pool = await asyncpg.create_pool(**DB_CONFIG)

    async with httpx.AsyncClient() as client:
        for symbol in SYMBOLS:
            print(f"Collecting {symbol}...")

            response = await client.get(
                f"{BYBIT_URL}/api/v1/market/kline",
                params={"category": "linear", "symbol": symbol, "interval": INTERVAL, "limit": LIMIT},
                timeout=30.0
            )

            if response.status_code == 200:
                data = response.json()
                klines = data.get("data", [])
                print(f"  Fetched {len(klines)} candles")

                records = []
                for k in klines:
                    timestamp = datetime.fromtimestamp(int(k[0]) / 1000, tz=timezone.utc)
                    records.append((
                        timestamp, symbol, INTERVAL,
                        float(k[1]), float(k[2]), float(k[3]), float(k[4]),
                        float(k[5]), float(k[6]) if len(k) > 6 else 0.0, 0
                    ))

                async with pool.acquire() as conn:
                    await conn.executemany("""
                        INSERT INTO market_data.candles
                        (time, symbol, interval, open, high, low, close, volume, quote_volume, trades_count)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                        ON CONFLICT (time, symbol, interval) DO UPDATE SET
                            open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                            close = EXCLUDED.close, volume = EXCLUDED.volume,
                            quote_volume = EXCLUDED.quote_volume
                    """, records)

                print(f"  ✅ Inserted {len(records)} candles\n")
            else:
                print(f"  ❌ Failed: HTTP {response.status_code}\n")

    await pool.close()
    print("✅ Complete!")

if __name__ == "__main__":
    asyncio.run(main())
