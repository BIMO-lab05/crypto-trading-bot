#!/usr/bin/env python3
"""
Simple data downloader for final 4 symbols
Direct HTTP requests to Bybit API
"""
import asyncio
import aiohttp
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
import time

SYMBOLS = ['LINKUSDT', 'OPUSDT', 'POLUSDT', 'SUIUSDT']
INTERVAL = '60'
MONTHS = 24
OUTPUT_DIR = (_REPO_ROOT / 'data/ml_training')
BYBIT_API = "https://api.bybit.com/v5/market/kline"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

async def fetch_klines(session, symbol, start_ms, end_ms):
    """Fetch klines from Bybit"""
    try:
        params = {
            'category': 'spot',
            'symbol': symbol,
            'interval': INTERVAL,
            'start': start_ms,
            'end': end_ms,
            'limit': 1000
        }

        async with session.get(BYBIT_API, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get('retCode') == 0:
                    return data['result']['list']
    except Exception as e:
        print(f"    Error: {e}")
    return None


async def download_symbol(symbol):
    """Download 24 months of data"""
    print(f"\n{'='*80}")
    print(f"[{symbol}] Downloading 24-month hourly data")
    print(f"{'='*80}")

    end_time = datetime.now()
    start_time = end_time - timedelta(days=MONTHS * 30)

    end_ms = int(end_time.timestamp() * 1000)
    start_ms = int(start_time.timestamp() * 1000)

    all_klines = []
    current_start = start_ms
    batch = 0

    async with aiohttp.ClientSession() as session:
        while current_start < end_ms:
            batch += 1
            batch_end = min(current_start + (1000 * 60 * 60 * 1000), end_ms)

            if batch % 5 == 1:
                print(f"  Batch {batch}: {datetime.fromtimestamp(current_start/1000).strftime('%Y-%m-%d')} to {datetime.fromtimestamp(batch_end/1000).strftime('%Y-%m-%d')}")

            klines = await fetch_klines(session, symbol, current_start, batch_end)

            if klines:
                all_klines.extend(klines)
                if len(klines) < 1000:
                    break
                last_time = int(klines[-1][0])
                current_start = last_time + 1
            else:
                print(f"    No more data")
                break

            await asyncio.sleep(0.2)

    if not all_klines:
        print(f"  ❌ No data downloaded")
        return None

    # Convert to DataFrame
    df = pd.DataFrame(all_klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
    ])

    df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)

    df = df.sort_values('timestamp').reset_index(drop=True)
    df = df.drop_duplicates(subset=['timestamp'], keep='first')
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]

    # Filter to exactly 24 months
    df = df[df['timestamp'] >= start_time]

    print(f"  ✅ Downloaded {len(df):,} candles")
    print(f"  📅 Range: {df['timestamp'].min()} to {df['timestamp'].max()}")

    return df


async def main():
    print("\n" + "="*100)
    print("DOWNLOADING DATA FOR FINAL 4 SYMBOLS")
    print("="*100)
    print(f"Symbols: {', '.join(SYMBOLS)}")
    print(f"Period: {MONTHS} months")
    print("="*100)

    start_time = time.time()
    results = {}

    for i, symbol in enumerate(SYMBOLS, 1):
        print(f"\n[{i}/{len(SYMBOLS)}] {symbol}")

        try:
            df = await download_symbol(symbol)

            if df is not None and len(df) > 0:
                # Save
                today = datetime.now().strftime('%Y%m%d')
                filename = f"{symbol}_1H_24months_{today}.csv"
                filepath = OUTPUT_DIR / filename
                df.to_csv(filepath, index=False)

                size_kb = filepath.stat().st_size / 1024
                print(f"  💾 Saved: {filename} ({size_kb:.1f} KB)")
                results[symbol] = 'SUCCESS'
            else:
                results[symbol] = 'FAILED'

        except Exception as e:
            print(f"  ❌ Error: {e}")
            results[symbol] = 'FAILED'

        await asyncio.sleep(1)

    # Summary
    elapsed = time.time() - start_time
    successful = sum(1 for r in results.values() if r == 'SUCCESS')

    print("\n" + "="*100)
    print("SUMMARY")
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
