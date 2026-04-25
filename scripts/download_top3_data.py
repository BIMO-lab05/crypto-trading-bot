#!/usr/bin/env python3
"""
Download Historical Data for Top 3 Performers
Created: 2025-12-06
Purpose: Download 90 days of 1-hour data for BNB, SOL, ADA from Bybit

This script downloads historical OHLCV data for the top 3 performing symbols
identified in the symbol filter analysis.

Symbols:
- BNBUSDT: Best performer (66.7% win rate, +$48.64)
- SOLUSDT: 2nd best (66.7% win rate, +$48.16)
- ADAUSDT: 3rd best (66.7% win rate, +$22.65)

Data specs:
- Period: 90 days
- Interval: 1 hour (60 minutes)
- Source: Bybit API v5
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import pandas as pd
from datetime import datetime
import logging

# Import data fetcher
from backtesting.bybit_data_fetcher import BybitDataFetcher

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def download_symbol_data(symbol: str, days: int = 90) -> pd.DataFrame:
    """
    Download historical data for a symbol

    Args:
        symbol: Trading pair (e.g., BNBUSDT)
        days: Number of days of historical data

    Returns:
        DataFrame with OHLCV data
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"DOWNLOADING {symbol} DATA")
    logger.info(f"{'='*80}")

    # Create data fetcher
    fetcher = BybitDataFetcher(testnet=False)  # Use mainnet

    try:
        # Download data
        data = await fetcher.download_historical_data(
            symbol=symbol,
            interval="60",  # 1 hour
            days=days
        )

        # Save to CSV
        data_dir = project_root / 'backtesting' / 'data'
        data_dir.mkdir(parents=True, exist_ok=True)

        output_file = data_dir / f'{symbol}_60m_{days}d_bybit.csv'
        data.to_csv(output_file, index=False)

        logger.info(f"✅ Saved to: {output_file}")
        logger.info(f"✅ Total candles: {len(data)}")
        logger.info(f"✅ Date range: {data['timestamp'].min()} to {data['timestamp'].max()}")

        return data

    except Exception as e:
        logger.error(f"❌ Failed to download {symbol}: {e}")
        raise
    finally:
        await fetcher.close()


async def main():
    """Main execution"""
    print("\n" + "="*80)
    print("DOWNLOADING HISTORICAL DATA FOR TOP 3 PERFORMERS")
    print("="*80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")

    # Top 3 symbols from analysis
    symbols = [
        ("BNBUSDT", "Binance Coin - Best performer"),
        ("SOLUSDT", "Solana - 2nd best performer"),
        ("ADAUSDT", "Cardano - 3rd best performer")
    ]

    results = {}

    for symbol, description in symbols:
        logger.info(f"\n📊 {description}")
        try:
            data = await download_symbol_data(symbol, days=90)
            results[symbol] = {
                'success': True,
                'candles': len(data),
                'data': data
            }
            logger.info(f"✅ {symbol} download complete!")

            # Brief pause to respect rate limits
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"❌ {symbol} download failed: {e}")
            results[symbol] = {
                'success': False,
                'error': str(e)
            }

    # Summary
    print("\n" + "="*80)
    print("DOWNLOAD SUMMARY")
    print("="*80)

    for symbol, result in results.items():
        if result['success']:
            print(f"✅ {symbol}: {result['candles']:,} candles downloaded")
        else:
            print(f"❌ {symbol}: FAILED - {result.get('error', 'Unknown error')}")

    # Overall success check
    success_count = sum(1 for r in results.values() if r['success'])
    total_count = len(results)

    print(f"\n{'='*80}")
    if success_count == total_count:
        print(f"✅ ALL {total_count}/{total_count} DOWNLOADS SUCCESSFUL!")
        print(f"{'='*80}")
        print("\nNext steps:")
        print("1. Run walk-forward optimization on BNB")
        print("2. Run walk-forward optimization on SOL")
        print("3. Run walk-forward optimization on ADA")
        print("4. Compare optimized parameters across symbols")
        return 0
    else:
        print(f"⚠️  {success_count}/{total_count} downloads successful")
        print(f"{'='*80}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
