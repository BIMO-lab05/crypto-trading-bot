#!/usr/bin/env python3
"""
Simple synchronous download for OPUSDT and SUIUSDT - 6 months data
"""
import requests
from pathlib import Path as _Path
_REPO_ROOT = _Path(__file__).resolve().parent.parent.parent
import pandas as pd
from datetime import datetime, timedelta
import time

def download_symbol(symbol, months=6):
    """Download historical data for a symbol"""
    print(f"\n{'='*80}")
    print(f"DOWNLOADING: {symbol} ({months} months)")
    print(f"{'='*80}")

    # Calculate start time (months ago)
    end_time = datetime.now()
    start_time = end_time - timedelta(days=months*30)
    start_ms = int(start_time.timestamp() * 1000)
    end_ms = int(end_time.timestamp() * 1000)

    all_data = []
    current_start = start_ms
    batch = 0

    while current_start < end_ms:
        batch += 1
        url = "https://api.bybit.com/v5/market/kline"
        params = {
            "category": "spot",
            "symbol": symbol,
            "interval": "60",  # 1 hour
            "start": current_start,
            "limit": 1000
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get('retCode') != 0:
                print(f"❌ API error: {data.get('retMsg', 'Unknown error')}")
                break

            candles = data.get('result', {}).get('list', [])
            if not candles:
                print(f"✅ No more data, stopping at batch {batch}")
                break

            # Bybit returns newest first, reverse it
            candles.reverse()
            all_data.extend(candles)

            # Update start time for next batch (use last candle time + 1 hour)
            last_time = int(candles[-1][0])
            current_start = last_time + 3600000  # +1 hour in ms

            if batch % 10 == 0:
                print(f"  Batch {batch}: Collected {len(all_data)} candles")

            # Rate limit: 0.2s between requests
            time.sleep(0.2)

        except Exception as e:
            print(f"❌ Error in batch {batch}: {e}")
            break

    if not all_data:
        print(f"❌ No data collected for {symbol}")
        return None

    # Create DataFrame
    df = pd.DataFrame(all_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
    df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')

    # Convert to numeric
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df.sort_values('timestamp').reset_index(drop=True)

    # Save
    output_file = fstr(_REPO_ROOT / 'data/ml_training/{symbol}_1H_6months_20251210.csv')
    df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].to_csv(output_file, index=False)

    print(f"\n✅ COMPLETE: {symbol}")
    print(f"   Rows: {len(df)}")
    print(f"   Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"   Saved: {output_file}")

    return output_file

if __name__ == '__main__':
    symbols = ['OPUSDT', 'SUIUSDT']

    print("\n" + "="*80)
    print("DOWNLOADING 6-MONTH DATA FOR OPUSDT AND SUIUSDT")
    print("="*80)

    for symbol in symbols:
        result = download_symbol(symbol, months=6)
        if result:
            print(f"✅ {symbol} downloaded successfully")
        else:
            print(f"❌ {symbol} download failed")

    print("\n" + "="*80)
    print("DOWNLOAD COMPLETE")
    print("="*80 + "\n")
