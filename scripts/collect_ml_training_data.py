#!/usr/bin/env python3
"""
ML Training Data Collection Script
===================================
Collects comprehensive historical data for ML model training

Target: 12-24 months of data (Jan 2024 - Dec 2025)
Timeframes: 1H, 4H, 1D
Symbols: 10 major cryptocurrencies
Purpose: Provide sufficient data for robust ML training

Requirements from ML Assessment:
- Minimum: 6-12 months (4,320-8,640 hourly candles)
- Recommended: 12-24 months for robust learning
- Multiple timeframes for multi-timeframe models
- Different market regimes (bull, bear, ranging)
"""
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict
import pandas as pd
import asyncio
import time

# Add services to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'market-data-service'))

from app.bybit_client import BybitClient
from app.config import settings

class MLDataCollector:
    """Collect historical data for ML training"""

    def __init__(self):
        self.client = BybitClient(
            api_key=settings.BYBIT_API_KEY,
            api_secret=settings.BYBIT_API_SECRET,
            testnet=settings.BYBIT_TESTNET
        )
        self.output_dir = Path(__file__).parent.parent / 'data' / 'ml_training'
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def get_collection_periods(self, months: int = 24) -> List[Dict]:
        """
        Calculate collection periods for specified months

        Args:
            months: Number of months to collect (default 24 = 2 years)

        Returns:
            List of period dicts with start/end timestamps
        """
        periods = []
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months * 30)

        # Bybit limit is 200 candles per request
        # For 1H: 200 hours = 8.3 days per request
        # For 4H: 200 * 4 hours = 33.3 days per request
        # For 1D: 200 days per request

        periods.append({
            'name': f'{months}months',
            'start': start_date,
            'end': end_date,
            'days': months * 30
        })

        return periods

    async def collect_symbol_timeframe(
        self,
        symbol: str,
        interval: str,
        period: Dict,
        max_retries: int = 3
    ) -> pd.DataFrame:
        """
        Collect data for one symbol and timeframe

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            interval: Candle interval ('60' = 1H, '240' = 4H, 'D' = 1D)
            period: Period dict with start/end dates
            max_retries: Maximum retry attempts on failure

        Returns:
            DataFrame with OHLCV data
        """
        print(f"\n{'='*80}")
        print(f"Collecting {symbol} - {interval} interval")
        print(f"Period: {period['start'].strftime('%Y-%m-%d')} to {period['end'].strftime('%Y-%m-%d')}")
        print(f"{'='*80}")

        all_candles = []
        current_end = int(period['end'].timestamp() * 1000)

        # Calculate interval in milliseconds
        interval_ms = {
            '60': 60 * 60 * 1000,      # 1 hour
            '240': 4 * 60 * 60 * 1000, # 4 hours
            'D': 24 * 60 * 60 * 1000   # 1 day
        }[interval]

        batch_count = 0
        total_candles = 0

        while True:
            retry_count = 0
            success = False

            while retry_count < max_retries and not success:
                try:
                    # Fetch batch of candles
                    response = await self.client.get_klines(
                        symbol=symbol,
                        interval=interval,
                        limit=200,
                        end_time=current_end
                    )

                    if not response or 'list' not in response:
                        print(f"⚠️ Empty response, retrying... ({retry_count + 1}/{max_retries})")
                        retry_count += 1
                        await asyncio.sleep(2)
                        continue

                    candles = response['list']

                    if not candles:
                        print("✅ Reached end of available data")
                        success = True
                        break

                    # Add candles to collection
                    all_candles.extend(candles)
                    total_candles += len(candles)
                    batch_count += 1

                    # Get oldest timestamp from batch
                    oldest_timestamp = int(candles[-1][0])

                    # Check if we've reached the start of our period
                    if oldest_timestamp <= int(period['start'].timestamp() * 1000):
                        print(f"✅ Reached target start date")
                        success = True
                        break

                    # Update for next batch
                    current_end = oldest_timestamp - 1

                    # Progress update
                    if batch_count % 10 == 0:
                        current_date = datetime.fromtimestamp(oldest_timestamp / 1000)
                        print(f"   Batch {batch_count}: {total_candles} candles collected (now at {current_date.strftime('%Y-%m-%d')})")

                    # Rate limiting: Bybit allows 120 requests/minute
                    await asyncio.sleep(0.5)
                    success = True

                except Exception as e:
                    print(f"❌ Error: {e}")
                    retry_count += 1
                    if retry_count < max_retries:
                        print(f"   Retrying... ({retry_count}/{max_retries})")
                        await asyncio.sleep(5)
                    else:
                        print(f"   Failed after {max_retries} attempts")
                        break

            if not success:
                print(f"⚠️ Collection incomplete due to errors")
                break

            # Check if we have enough data
            if len(all_candles) >= 200:
                # Check oldest candle timestamp
                oldest = int(all_candles[-1][0])
                if oldest <= int(period['start'].timestamp() * 1000):
                    break
            else:
                # Less than 200 candles means we hit the end
                break

        print(f"\n✅ Collection complete:")
        print(f"   Total candles: {total_candles}")
        print(f"   Batches: {batch_count}")

        # Convert to DataFrame
        if not all_candles:
            print("⚠️ No data collected")
            return pd.DataFrame()

        df = pd.DataFrame(all_candles, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
        ])

        # Convert types
        df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms')
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)

        # Sort by timestamp ascending
        df = df.sort_values('timestamp').reset_index(drop=True)

        # Filter to exact period
        df = df[
            (df['timestamp'] >= period['start']) &
            (df['timestamp'] <= period['end'])
        ]

        print(f"   Final dataset: {len(df)} candles")
        print(f"   Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
        print(f"   Completeness: {len(df) / (period['days'] * 24 / int(interval.replace('D', '1440')) * (1 if interval != 'D' else 1)) * 100:.1f}%")

        return df

    async def collect_all_data(
        self,
        symbols: List[str],
        intervals: List[str],
        months: int = 24
    ):
        """
        Collect data for all symbols and timeframes

        Args:
            symbols: List of trading pairs
            intervals: List of intervals ('60', '240', 'D')
            months: Number of months to collect
        """
        print("="*80)
        print("ML TRAINING DATA COLLECTION")
        print("="*80)
        print(f"Target: {months} months of historical data")
        print(f"Symbols: {len(symbols)}")
        print(f"Timeframes: {len(intervals)}")
        print(f"Total datasets: {len(symbols) * len(intervals)}")
        print(f"Output: {self.output_dir}")
        print("="*80)

        periods = self.get_collection_periods(months)
        period = periods[0]

        total_datasets = len(symbols) * len(intervals)
        completed = 0

        summary = []

        for symbol in symbols:
            for interval in intervals:
                completed += 1
                print(f"\n[{completed}/{total_datasets}] Processing {symbol} - {interval}")

                try:
                    # Collect data
                    df = await self.collect_symbol_timeframe(
                        symbol=symbol,
                        interval=interval,
                        period=period
                    )

                    if df.empty:
                        print(f"⚠️ No data collected for {symbol} - {interval}")
                        summary.append({
                            'symbol': symbol,
                            'interval': interval,
                            'candles': 0,
                            'status': 'FAILED'
                        })
                        continue

                    # Save to CSV
                    interval_name = {
                        '60': '1H',
                        '240': '4H',
                        'D': '1D'
                    }[interval]

                    filename = f"{symbol}_{interval_name}_{months}months_{datetime.now().strftime('%Y%m%d')}.csv"
                    filepath = self.output_dir / filename

                    df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].to_csv(
                        filepath,
                        index=False
                    )

                    print(f"✅ Saved: {filepath}")
                    print(f"   Size: {filepath.stat().st_size / 1024:.1f} KB")

                    summary.append({
                        'symbol': symbol,
                        'interval': interval_name,
                        'candles': len(df),
                        'file': filename,
                        'status': 'SUCCESS'
                    })

                except Exception as e:
                    print(f"❌ Error collecting {symbol} - {interval}: {e}")
                    summary.append({
                        'symbol': symbol,
                        'interval': interval,
                        'candles': 0,
                        'status': 'ERROR',
                        'error': str(e)
                    })

                # Brief pause between datasets
                await asyncio.sleep(1)

        # Print summary
        print("\n" + "="*80)
        print("COLLECTION SUMMARY")
        print("="*80)

        summary_df = pd.DataFrame(summary)

        print(f"\nTotal datasets: {len(summary_df)}")
        print(f"Successful: {len(summary_df[summary_df['status'] == 'SUCCESS'])}")
        print(f"Failed: {len(summary_df[summary_df['status'] != 'SUCCESS'])}")

        if len(summary_df[summary_df['status'] == 'SUCCESS']) > 0:
            print(f"\nTotal candles collected: {summary_df[summary_df['status'] == 'SUCCESS']['candles'].sum():,}")
            print(f"Average per dataset: {summary_df[summary_df['status'] == 'SUCCESS']['candles'].mean():.0f}")

        # Save summary
        summary_file = self.output_dir / f"collection_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        summary_df.to_csv(summary_file, index=False)
        print(f"\nSummary saved: {summary_file}")

        # Print detailed results
        print("\nDetailed Results:")
        print("-" * 80)
        for _, row in summary_df.iterrows():
            status_icon = "✅" if row['status'] == 'SUCCESS' else "❌"
            print(f"{status_icon} {row['symbol']:10} {row['interval']:4} - {row['candles']:6,} candles")

        print("\n" + "="*80)
        print("COLLECTION COMPLETE")
        print("="*80)


async def main():
    """Main execution"""

    # Configuration
    SYMBOLS = [
        'BTCUSDT',
        'ETHUSDT',
        'SOLUSDT',
        'BNBUSDT',
        'ADAUSDT',
        'APTUSDT',
        'DOTUSDT',
        'LTCUSDT',
        'AVAXUSDT',
        'ARBUSDT'
    ]

    INTERVALS = ['60', '240', 'D']  # 1H, 4H, 1D

    MONTHS = 24  # Collect 24 months (2 years)

    print("\nConfiguration:")
    print(f"  Symbols: {len(SYMBOLS)}")
    print(f"  Intervals: {INTERVALS} (1H, 4H, 1D)")
    print(f"  Period: {MONTHS} months")
    print(f"  Total datasets: {len(SYMBOLS) * len(INTERVALS)}")

    # Confirm before starting
    print("\n⚠️ This will collect approximately:")
    print(f"  - 1H data: ~{MONTHS * 30 * 24:,} candles per symbol")
    print(f"  - 4H data: ~{MONTHS * 30 * 6:,} candles per symbol")
    print(f"  - 1D data: ~{MONTHS * 30:,} candles per symbol")
    print(f"  - Total: ~{len(SYMBOLS) * (MONTHS * 30 * 24 + MONTHS * 30 * 6 + MONTHS * 30):,} candles")
    print(f"  - Estimated time: {len(SYMBOLS) * len(INTERVALS) * 5} minutes")

    response = input("\nProceed with data collection? (yes/no): ")
    if response.lower() != 'yes':
        print("Collection cancelled")
        return

    # Start collection
    collector = MLDataCollector()
    await collector.collect_all_data(
        symbols=SYMBOLS,
        intervals=INTERVALS,
        months=MONTHS
    )


if __name__ == "__main__":
    asyncio.run(main())
