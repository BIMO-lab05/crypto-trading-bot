#!/usr/bin/env python3
"""
Direct Bybit Historical Data Collection
========================================
Purpose: Collect 180 days of historical kline data directly from Bybit API

This script bypasses the market-data-service and fetches data directly
from Bybit's public API to get the full 180 days of historical data.

Features:
- Direct Bybit API connection using pybit
- 180 days of hourly candle data
- Rate limit handling
- Progress tracking
- Data validation
- Saves to database and CSV backup

Author: Phase 2.1.3 - Historical Data Collection
Date: 2025-12-08
"""

import os
import sys
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Symbols to collect
SYMBOLS = [
    'SOLUSDT',
    'BNBUSDT',
    'ADAUSDT',
    'APTUSDT',
    'DOTUSDT',
    'LTCUSDT',
    'POLUSDT',
    'ETHUSDT',
    'BTCUSDT',
    'AVAXUSDT'
]

# Configuration
DAYS_TO_COLLECT = 180
INTERVAL = '60'  # 60 minutes (hourly candles)
CANDLES_PER_DAY = 24
EXPECTED_CANDLES = DAYS_TO_COLLECT * CANDLES_PER_DAY  # 4,320 candles
BYBIT_API_ENDPOINT = 'https://api.bybit.com'
MAX_LIMIT = 200  # Bybit allows max 200 candles per request
RATE_LIMIT_DELAY = 0.5  # Delay between requests to avoid rate limits

# Database configuration
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', '5434'))
DB_NAME = os.getenv('DB_NAME', 'cryptobot')
DB_USER = os.getenv('DB_USER', 'cryptobot')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'your_password_here')

# Output directory for CSV backups
OUTPUT_DIR = '/mnt/d/Bimo_max/crypto-trading-bot/data/historical'


def print_header():
    """Print collection header"""
    print("=" * 80)
    print("DIRECT BYBIT HISTORICAL DATA COLLECTION - 180 DAYS")
    print("Phase 2.1.3 - Support/Resistance & ML Training Data")
    print("=" * 80)
    print()
    print(f"Symbols to collect: {', '.join(SYMBOLS)}")
    print(f"Collection period: {DAYS_TO_COLLECT} days (6 months)")
    print(f"Interval: {INTERVAL} minutes (hourly candles)")
    print(f"Expected candles per symbol: ~{EXPECTED_CANDLES:,}")
    print(f"Bybit API: {BYBIT_API_ENDPOINT}")
    print()


def get_bybit_klines(
    symbol: str,
    interval: str,
    start_time: int,
    end_time: int,
    limit: int = 200
) -> List[Dict]:
    """
    Fetch kline data directly from Bybit public API

    Args:
        symbol: Trading pair (e.g., 'SOLUSDT')
        interval: Kline interval in minutes (e.g., '60')
        start_time: Start timestamp in milliseconds
        end_time: End timestamp in milliseconds
        limit: Number of candles to fetch (max 200)

    Returns:
        List of kline dictionaries
    """
    url = f"{BYBIT_API_ENDPOINT}/v5/market/kline"

    params = {
        'category': 'linear',  # USDT perpetual
        'symbol': symbol,
        'interval': interval,
        'start': start_time,
        'end': end_time,
        'limit': limit
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()

        if data.get('retCode') != 0:
            logger.error(f"Bybit API error: {data.get('retMsg')}")
            return []

        result = data.get('result', {})
        klines = result.get('list', [])

        return klines

    except requests.exceptions.RequestException as e:
        logger.error(f"Request error for {symbol}: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error for {symbol}: {e}")
        return []


def process_kline_data(klines: List[List]) -> pd.DataFrame:
    """
    Process raw kline data into DataFrame

    Bybit kline format:
    [
        startTime,
        open,
        high,
        low,
        close,
        volume,
        turnover
    ]

    Args:
        klines: List of kline arrays from Bybit

    Returns:
        DataFrame with processed kline data
    """
    if not klines:
        return pd.DataFrame()

    df_data = []

    for kline in klines:
        try:
            timestamp = int(kline[0])  # Milliseconds
            open_price = float(kline[1])
            high_price = float(kline[2])
            low_price = float(kline[3])
            close_price = float(kline[4])
            volume = float(kline[5])
            turnover = float(kline[6])

            df_data.append({
                'timestamp': pd.to_datetime(timestamp, unit='ms'),
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price,
                'volume': volume,
                'turnover': turnover
            })
        except (IndexError, ValueError) as e:
            logger.warning(f"Error processing kline: {e}")
            continue

    if not df_data:
        return pd.DataFrame()

    df = pd.DataFrame(df_data)

    # Sort by timestamp ascending (oldest first)
    df = df.sort_values('timestamp')

    # Remove duplicates
    df = df.drop_duplicates(subset=['timestamp'])

    return df


def collect_symbol_data(
    symbol: str,
    days: int = 180,
    interval: str = '60'
) -> pd.DataFrame:
    """
    Collect historical data for a symbol

    Args:
        symbol: Trading pair to collect
        days: Number of days to collect
        interval: Kline interval in minutes

    Returns:
        DataFrame with all collected klines
    """
    print(f"\n{'=' * 80}")
    print(f"Collecting {days} days of data for {symbol}")
    print(f"{'=' * 80}")

    # Calculate time range
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)

    print(f"Time range: {start_time.strftime('%Y-%m-%d')} to {end_time.strftime('%Y-%m-%d')}")
    print(f"Fetching hourly candles from Bybit API...")

    all_klines = []
    current_start = start_time
    request_count = 0

    # Fetch data in chunks (Bybit max 200 candles per request)
    while current_start < end_time:
        # Calculate chunk end time (200 candles * 60 minutes)
        chunk_end = min(
            current_start + timedelta(hours=200),
            end_time
        )

        # Convert to milliseconds
        start_ms = int(current_start.timestamp() * 1000)
        end_ms = int(chunk_end.timestamp() * 1000)

        # Fetch klines for this chunk
        logger.info(
            f"  Fetching {symbol}: {current_start.strftime('%Y-%m-%d %H:%M')} - "
            f"{chunk_end.strftime('%Y-%m-%d %H:%M')}"
        )

        klines = get_bybit_klines(
            symbol=symbol,
            interval=interval,
            start_time=start_ms,
            end_time=end_ms,
            limit=MAX_LIMIT
        )

        if klines:
            all_klines.extend(klines)
            logger.info(f"    Got {len(klines)} candles")
        else:
            logger.warning(f"    Got 0 candles (may have reached end of available data)")

        request_count += 1

        # Move to next chunk
        current_start = chunk_end

        # Rate limiting
        time.sleep(RATE_LIMIT_DELAY)

        # Progress update every 10 requests
        if request_count % 10 == 0:
            print(f"  Progress: {len(all_klines):,} candles collected ({request_count} requests)...")

    # Process all klines into DataFrame
    df = process_kline_data(all_klines)

    if df.empty:
        logger.error(f"❌ No data collected for {symbol}")
        return df

    # Validation
    print(f"\n✅ Collected {len(df):,} candles for {symbol}")
    print(f"   Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"   Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")
    print(f"   Total volume: {df['volume'].sum():,.0f}")
    print(f"   Requests made: {request_count}")

    return df


def save_to_csv(df: pd.DataFrame, symbol: str):
    """
    Save DataFrame to CSV backup file

    Args:
        df: DataFrame to save
        symbol: Symbol name for filename
    """
    # Create output directory if it doesn't exist
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    filename = f"{symbol}_180days_{datetime.now().strftime('%Y%m%d')}.csv"
    filepath = os.path.join(OUTPUT_DIR, filename)

    df.to_csv(filepath, index=False)
    logger.info(f"   Saved CSV backup: {filepath}")


def save_to_database(df: pd.DataFrame, symbol: str):
    """
    Save DataFrame to PostgreSQL database

    Args:
        df: DataFrame to save
        symbol: Symbol name
    """
    try:
        import psycopg2
        from psycopg2.extras import execute_values

        # Connect to database
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cur = conn.cursor()

        # Prepare data for insertion
        records = []
        for _, row in df.iterrows():
            records.append((
                symbol,
                row['timestamp'],
                row['open'],
                row['high'],
                row['low'],
                row['close'],
                row['volume'],
                '60',  # interval
                row.get('turnover', 0)
            ))

        # Insert data (upsert to handle duplicates)
        insert_query = """
        INSERT INTO klines (
            symbol, timestamp, open, high, low, close, volume, interval, turnover
        ) VALUES %s
        ON CONFLICT (symbol, timestamp, interval)
        DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            turnover = EXCLUDED.turnover
        """

        execute_values(cur, insert_query, records)
        conn.commit()

        logger.info(f"   Saved {len(records):,} candles to database")

        cur.close()
        conn.close()

    except ImportError:
        logger.warning("   psycopg2 not installed, skipping database save")
    except Exception as e:
        logger.error(f"   Database error: {e}")


def main():
    """Main execution function"""
    print_header()

    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Collection summary
    total_symbols = len(SYMBOLS)
    successful = 0
    failed = 0
    total_candles = 0

    start_time = datetime.now()

    # Collect data for each symbol
    for i, symbol in enumerate(SYMBOLS, 1):
        print(f"\n[{i}/{total_symbols}] Processing {symbol}...")

        try:
            # Collect data
            df = collect_symbol_data(symbol, days=DAYS_TO_COLLECT, interval=INTERVAL)

            if df.empty:
                logger.warning(f"No data collected for {symbol}")
                failed += 1
                continue

            # Save to CSV backup
            save_to_csv(df, symbol)

            # Save to database (if available)
            save_to_database(df, symbol)

            successful += 1
            total_candles += len(df)

        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")
            failed += 1
            continue

        # Small delay between symbols
        if i < total_symbols:
            time.sleep(1)

    # Final summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print(f"\n{'=' * 80}")
    print("COLLECTION COMPLETE")
    print(f"{'=' * 80}")
    print(f"Total symbols: {total_symbols}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Total candles: {total_candles:,}")
    print(f"Average per symbol: {total_candles // successful if successful > 0 else 0:,}")
    print(f"Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
    print(f"CSV backups saved to: {OUTPUT_DIR}")
    print()

    if successful > 0:
        print("✅ Data collection successful!")
        print(f"\nNext steps:")
        print(f"1. Verify CSV files in: {OUTPUT_DIR}")
        print(f"2. Check database records if applicable")
        print(f"3. Run S/R strategy validation with full dataset")
        print(f"4. Train ML models with 180 days of data")
    else:
        print("❌ Data collection failed!")
        print("Check logs above for error details")

    return 0 if successful > 0 else 1


if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nCollection interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
