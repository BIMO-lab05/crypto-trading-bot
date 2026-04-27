#!/usr/bin/env python3
"""
Collect 24-month data for final 4 symbols
Uses the working BybitClient from market-data-service
"""
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import asyncio
import time

# Add services to path
sys.path.insert(0, '/mnt/d/Bimo_max/crypto-trading-bot/services/market-data-service')

from app.bybit_client import BybitClient
from app.config import settings

# Target symbols
SYMBOLS = ['LINKUSDT', 'OPUSDT', 'POLUSDT', 'SUIUSDT']
INTERVAL = '60'  # 60 minutes
MONTHS = 24
OUTPUT_DIR = Path('/mnt/d/Bimo_max/crypto-trading-bot/data/ml_training')

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

async def collect_symbol(client: BybitClient, symbol: str) -> pd.DataFrame:
    """Collect 24 months of data for one symbol"""
    print(f"\n{'='*80}")
    print(f"Collecting {symbol} - {MONTHS} months of hourly data")
    print(f"{'='*80}")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=MONTHS * 30)

    all_candles = []
    current_end = int(end_date.timestamp() * 1000)
    start_ms = int(start_date.timestamp() * 1000)

    batch = 0
    while True:
        try:
            # Fetch batch
            response = await client.get_klines(
                symbol=symbol,
                interval=INTERVAL,
                limit=200,
                end_time=current_end
            )

            if not response or 'list' not in response:
                print(f"  ⚠️ Empty response, stopping")
                break

            candles = response['list']
            if not candles:
                print(f"  ✅ Reached end of data")
                break

            all_candles.extend(candles)
            batch += 1

            oldest_timestamp = int(candles[-1][0])

            # Check if reached target start date
            if oldest_timestamp <= start_ms:
                print(f"  ✅ Reached target date")
                break

            current_end = oldest_timestamp - 1

            if batch % 10 == 0:
                current_date = datetime.fromtimestamp(oldest_timestamp / 1000)
                print(f"  Batch {batch}: {len(all_candles)} candles (at {current_date.strftime('%Y-%m-%d')})")

            await asyncio.sleep(0.5)

        except Exception as e:
            print(f"  ❌ Error: {e}")
            break

    print(f"\n  ✅ Downloaded {len(all_candles)} candles")

    if not all_candles:
        return pd.DataFrame()

    # Convert to DataFrame
    df = pd.DataFrame(all_candles, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
    ])

    df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)

    df = df.sort_values('timestamp').reset_index(drop=True)
    df = df.drop_duplicates(subset=['timestamp'], keep='first')
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]

    return df


async def main():
    """Download data for all 4 symbols"""
    print("\n" + "="*100)
    print("DATA COLLECTION - FINAL 4 SYMBOLS")
    print("="*100)
    print(f"Symbols: {', '.join(SYMBOLS)}")
    print(f"Period: {MONTHS} months")
    print(f"Interval: {INTERVAL} minutes (1H)")
    print("="*100)

    client = BybitClient(
        api_key=settings.bybit_api_key,
        api_secret=settings.bybit_api_secret,
        testnet=settings.bybit_testnet,
    )

    results = {}
    start_time = time.time()

    for i, symbol in enumerate(SYMBOLS, 1):
        print(f"\n[{i}/{len(SYMBOLS)}] Processing {symbol}...")

        try:
            df = await collect_symbol(client, symbol)

            if df.empty:
                print(f"  ❌ No data collected")
                results[symbol] = 'FAILED'
                continue

            # Save CSV
            today = datetime.now().strftime('%Y%m%d')
            output_file = OUTPUT_DIR / f"{symbol}_1H_24months_{today}.csv"
            df.to_csv(output_file, index=False)

            size_kb = output_file.stat().st_size / 1024
            print(f"  💾 Saved: {output_file.name} ({size_kb:.1f} KB)")
            print(f"  📊 Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")

            results[symbol] = 'SUCCESS'

        except Exception as e:
            print(f"  ❌ Failed: {e}")
            results[symbol] = 'FAILED'

        if i < len(SYMBOLS):
            await asyncio.sleep(1)

    # Summary
    elapsed = time.time() - start_time
    successful = sum(1 for r in results.values() if r == 'SUCCESS')

    print("\n" + "="*100)
    print("COLLECTION SUMMARY")
    print("="*100)
    print(f"Time: {elapsed/60:.1f} minutes")
    print(f"Success: {successful}/{len(SYMBOLS)}")
    print()

    for symbol, status in results.items():
        icon = "✅" if status == "SUCCESS" else "❌"
        print(f"  {icon} {symbol}: {status}")

    print("="*100)


if __name__ == "__main__":
    asyncio.run(main())
