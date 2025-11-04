#!/usr/bin/env python3
"""
Historical Data Downloader for Backtesting
Downloads OHLCV data from Bybit for backtesting purposes
"""

import asyncio
import httpx
import pandas as pd
from datetime import datetime, timedelta
import time
import logging
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HistoricalDataDownloader:
    """Downloads historical market data for backtesting"""

    def __init__(self, market_data_url: str = "http://localhost:8003"):
        """
        Initialize downloader

        Args:
            market_data_url: URL of the market data service
        """
        self.market_data_url = market_data_url
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()

    async def download_historical_data(
        self,
        symbol: str,
        interval: str = "60",  # 1 hour
        days: int = 90,  # 3 months
        output_file: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Download historical OHLCV data

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Candle interval in minutes (1, 5, 15, 30, 60, 240, D)
            days: Number of days of historical data
            output_file: Optional CSV file to save data

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        logger.info(f"Downloading {days} days of {symbol} data at {interval}m interval...")

        # Calculate number of candles needed
        if interval == "D":
            candles_per_day = 1
        else:
            minutes_per_candle = int(interval)
            candles_per_day = (24 * 60) / minutes_per_candle

        total_candles = int(days * candles_per_day)
        max_candles_per_request = 200  # Bybit limit

        all_data = []
        candles_downloaded = 0

        while candles_downloaded < total_candles:
            # Request next batch
            limit = min(max_candles_per_request, total_candles - candles_downloaded)

            try:
                url = f"{self.market_data_url}/api/v1/klines/{symbol}"
                params = {
                    "interval": interval,
                    "limit": limit
                }

                logger.info(f"Requesting {limit} candles (total: {candles_downloaded}/{total_candles})...")
                response = await self.client.get(url, params=params)
                response.raise_for_status()

                data = response.json()

                if not data.get("success"):
                    logger.error(f"API error: {data.get('error', 'Unknown error')}")
                    break

                klines = data.get("data", [])
                if not klines:
                    logger.warning("No more data available")
                    break

                # Convert to DataFrame
                df = pd.DataFrame(klines)
                all_data.append(df)

                candles_downloaded += len(klines)
                logger.info(f"Downloaded {len(klines)} candles")

                # Rate limiting
                await asyncio.sleep(0.5)

                # If we got fewer candles than requested, we've reached the end
                if len(klines) < limit:
                    logger.info("Reached end of available data")
                    break

            except Exception as e:
                logger.error(f"Error downloading data: {e}")
                break

        if not all_data:
            logger.error("No data downloaded")
            return pd.DataFrame()

        # Combine all data
        df = pd.concat(all_data, ignore_index=True)

        # Remove duplicates and sort
        df = df.drop_duplicates(subset=['timestamp'])
        df = df.sort_values('timestamp')

        # Convert timestamp to datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        logger.info(f"Total candles downloaded: {len(df)}")
        logger.info(f"Date range: {df.iloc[0]['timestamp']} to {df.iloc[-1]['timestamp']}")

        # Save to CSV if requested
        if output_file:
            df.to_csv(output_file, index=False)
            logger.info(f"Data saved to: {output_file}")

        return df

    async def download_multiple_symbols(
        self,
        symbols: list,
        interval: str = "60",
        days: int = 90,
        output_dir: str = "backtesting/data"
    ):
        """
        Download data for multiple symbols

        Args:
            symbols: List of trading pairs
            interval: Candle interval
            days: Days of historical data
            output_dir: Directory to save CSV files
        """
        import os
        os.makedirs(output_dir, exist_ok=True)

        for symbol in symbols:
            logger.info(f"\n{'='*80}")
            logger.info(f"Downloading {symbol}")
            logger.info(f"{'='*80}\n")

            output_file = f"{output_dir}/{symbol}_{interval}m_{days}d.csv"

            df = await self.download_historical_data(
                symbol=symbol,
                interval=interval,
                days=days,
                output_file=output_file
            )

            logger.info(f"✓ {symbol} complete: {len(df)} candles\n")
            await asyncio.sleep(1)  # Rate limiting between symbols


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Download historical data for backtesting")
    parser.add_argument('--symbol', type=str, default='BTCUSDT', help='Trading pair (default: BTCUSDT)')
    parser.add_argument('--interval', type=str, default='60', help='Interval in minutes (default: 60)')
    parser.add_argument('--days', type=int, default=90, help='Days of historical data (default: 90)')
    parser.add_argument('--output', type=str, help='Output CSV file')
    parser.add_argument('--market-data-url', type=str, default='http://localhost:8003', help='Market data service URL')

    args = parser.parse_args()

    downloader = HistoricalDataDownloader(market_data_url=args.market_data_url)

    try:
        output_file = args.output or f"backtesting/data/{args.symbol}_{args.interval}m_{args.days}d.csv"

        df = await downloader.download_historical_data(
            symbol=args.symbol,
            interval=args.interval,
            days=args.days,
            output_file=output_file
        )

        if not df.empty:
            print("\n" + "="*80)
            print("DOWNLOAD COMPLETE")
            print("="*80)
            print(f"Symbol: {args.symbol}")
            print(f"Interval: {args.interval} minutes")
            print(f"Total Candles: {len(df)}")
            print(f"Date Range: {df.iloc[0]['timestamp']} to {df.iloc[-1]['timestamp']}")
            print(f"File: {output_file}")
            print("="*80)

    finally:
        await downloader.close()


if __name__ == "__main__":
    asyncio.run(main())
