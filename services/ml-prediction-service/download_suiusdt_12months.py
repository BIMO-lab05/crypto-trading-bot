#!/usr/bin/env python3
"""
Download 12-month hourly data for SUIUSDT to improve model performance
Target: Get enough data to achieve R²>0.85
"""
import requests
from pathlib import Path as _Path
_REPO_ROOT = _Path(__file__).resolve().parent.parent.parent
import pandas as pd
from datetime import datetime, timedelta
import time

def download_suiusdt_extended():
    """Download 12 months of hourly data for SUIUSDT"""
    print("="*80)
    print("DOWNLOADING EXTENDED DATA FOR SUIUSDT")
    print("="*80)
    print("Target: 12 months of hourly candles")
    print("Expected: ~8,760 rows (365 days * 24 hours)")
    print("="*80 + "\n")

    # Calculate dates (12 months ago)
    end_time = datetime.now()
    start_time = end_time - timedelta(days=365)  # 12 months
    start_ms = int(start_time.timestamp() * 1000)
    end_ms = int(end_time.timestamp() * 1000)

    print(f"Start: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"End: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    all_data = []
    current_start = start_ms
    batch = 0
    errors = 0

    while current_start < end_ms:
        batch += 1
        url = "https://api.bybit.com/v5/market/kline"
        params = {
            "category": "spot",
            "symbol": "SUIUSDT",
            "interval": "60",  # 1 hour
            "start": current_start,
            "limit": 1000
        }

        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            if data.get('retCode') != 0:
                print(f"❌ Batch {batch}: API error - {data.get('retMsg', 'Unknown')}")
                errors += 1
                if errors > 5:
                    print("Too many errors, stopping...")
                    break
                time.sleep(1)
                continue

            candles = data.get('result', {}).get('list', [])
            if not candles:
                print(f"✅ Batch {batch}: No more data (reached end)")
                break

            # Bybit returns newest first, reverse it
            candles.reverse()
            all_data.extend(candles)

            # Update start time for next batch
            last_time = int(candles[-1][0])
            current_start = last_time + 3600000  # +1 hour in ms

            # Progress update every 10 batches
            if batch % 10 == 0:
                current_date = datetime.fromtimestamp(last_time/1000).strftime('%Y-%m-%d')
                print(f"  Batch {batch:3d}: {len(all_data):5d} candles collected (reached {current_date})")

            # Rate limit
            time.sleep(0.15)

        except Exception as e:
            print(f"❌ Batch {batch}: Error - {e}")
            errors += 1
            if errors > 5:
                print("Too many errors, stopping...")
                break
            time.sleep(2)
            continue

    if not all_data:
        print("\n❌ FAILED: No data collected")
        return None

    # Create DataFrame
    df = pd.DataFrame(all_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
    df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')

    # Convert to numeric
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # Remove duplicates and NaN
    df = df.drop_duplicates(subset=['timestamp'])
    df = df.dropna()
    df = df.sort_values('timestamp').reset_index(drop=True)

    # Save
    output_file = str(_REPO_ROOT / 'data/ml_training/SUIUSDT_1H_12months_20251210.csv')
    df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].to_csv(output_file, index=False)

    print(f"\n{'='*80}")
    print("DOWNLOAD COMPLETE")
    print("="*80)
    print(f"✅ Total rows: {len(df):,}")
    print(f"✅ Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"✅ Duration: {(df['timestamp'].max() - df['timestamp'].min()).days} days")
    print(f"✅ Batches: {batch}")
    print(f"✅ Errors: {errors}")
    print(f"✅ Saved to: {output_file}")
    print("="*80 + "\n")

    return output_file

if __name__ == '__main__':
    result = download_suiusdt_extended()
    if result:
        print(f"Success! File: {result}")
    else:
        print("Failed to download data")
        exit(1)
