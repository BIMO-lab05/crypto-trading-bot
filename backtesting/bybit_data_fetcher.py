#!/usr/bin/env python3
"""
Bybit Historical Data Fetcher
Downloads OHLCV data directly from Bybit API for backtesting
Uses public API endpoints - no authentication required
"""

import asyncio
import httpx
import pandas as pd
from datetime import datetime, timedelta
import time
import logging
from typing import Optional
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BybitDataFetcher:
    """
    Fetches historical market data directly from Bybit API
    Uses public REST API v5 for kline data
    """

    def __init__(self, testnet: bool = False):
        """
        Initialize Bybit data fetcher

        Args:
            testnet: Use testnet API (default: False for mainnet)
        """
        # Bybit API v5 endpoints
        if testnet:
            self.base_url = "https://api-testnet.bybit.com"
        else:
            self.base_url = "https://api.bybit.com"

        self.client = httpx.AsyncClient(timeout=30.0)

        # Bybit rate limits: 10 requests per second for public endpoints
        self.rate_limit_delay = 0.15  # 150ms between requests (safe margin)

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
        limit: int = 200
    ) -> list:
        """
        Get kline/candlestick data from Bybit

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Kline interval (1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M)
            start_time: Start timestamp in milliseconds
            end_time: End timestamp in milliseconds
            limit: Number of candles to fetch (max 200)

        Returns:
            List of kline data
        """
        endpoint = f"{self.base_url}/v5/market/kline"

        params = {
            "category": "linear",  # USDT perpetual
            "symbol": symbol,
            "interval": interval,
            "start": start_time,
            "end": end_time,
            "limit": limit
        }

        try:
            response = await self.client.get(endpoint, params=params)
            response.raise_for_status()

            data = response.json()

            # Bybit API v5 response format
            if data.get("retCode") != 0:
                error_msg = data.get("retMsg", "Unknown error")
                logger.error(f"Bybit API error: {error_msg}")
                return []

            # Extract klines from result
            klines = data.get("result", {}).get("list", [])

            return klines

        except Exception as e:
            logger.error(f"Error fetching klines: {e}")
            return []

    def convert_interval_to_minutes(self, interval: str) -> int:
        """
        Convert interval string to minutes

        Args:
            interval: Interval string (60, 240, D, etc.)

        Returns:
            Number of minutes
        """
        if interval == "D":
            return 24 * 60
        elif interval == "W":
            return 7 * 24 * 60
        elif interval == "M":
            return 30 * 24 * 60
        else:
            return int(interval)

    async def download_historical_data(
        self,
        symbol: str,
        interval: str = "60",  # 1 hour
        days: int = 90,
        output_file: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Download historical OHLCV data from Bybit

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Candle interval in minutes (1, 5, 15, 30, 60, 240, D)
            days: Number of days of historical data
            output_file: Optional CSV file to save data

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        logger.info(f"Downloading {days} days of {symbol} data at {interval}m interval from Bybit...")

        # Calculate time range
        end_time = int(time.time() * 1000)  # Current time in ms
        interval_minutes = self.convert_interval_to_minutes(interval)
        start_time = end_time - (days * 24 * 60 * 60 * 1000)  # days ago in ms

        logger.info(f"Time range: {datetime.fromtimestamp(start_time/1000)} to {datetime.fromtimestamp(end_time/1000)}")

        all_klines = []
        current_end = end_time
        max_candles_per_request = 200  # Bybit limit

        # Calculate total candles needed
        total_candles_needed = int((days * 24 * 60) / interval_minutes)
        candles_downloaded = 0

        logger.info(f"Expecting approximately {total_candles_needed} candles...")

        # Fetch data in batches (working backwards from present)
        while current_end > start_time and candles_downloaded < total_candles_needed:
            # Calculate batch start time
            batch_duration_ms = max_candles_per_request * interval_minutes * 60 * 1000
            batch_start = max(start_time, current_end - batch_duration_ms)

            logger.info(f"Fetching batch: {datetime.fromtimestamp(batch_start/1000)} to {datetime.fromtimestamp(current_end/1000)}")

            # Fetch klines
            klines = await self.get_klines(
                symbol=symbol,
                interval=interval,
                start_time=batch_start,
                end_time=current_end,
                limit=max_candles_per_request
            )

            if not klines:
                logger.warning("No data received, stopping download")
                break

            # Bybit returns data in reverse order (newest first), so we need to reverse it
            klines.reverse()

            all_klines.extend(klines)
            candles_downloaded += len(klines)

            logger.info(f"Downloaded {len(klines)} candles (total: {candles_downloaded})")

            # Move to next batch (go backwards in time)
            # Use the timestamp of the oldest candle in this batch
            if klines:
                oldest_candle_time = int(klines[0][0])  # First element is start time
                current_end = oldest_candle_time - 1  # Move just before this candle

            # Rate limiting
            await asyncio.sleep(self.rate_limit_delay)

            # Safety check to prevent infinite loops
            if len(klines) < 10 and current_end > start_time:
                logger.warning("Received very few candles, might have reached data limit")
                break

        if not all_klines:
            logger.error("No data downloaded")
            return pd.DataFrame()

        # Convert to DataFrame
        # Bybit kline format: [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
        df = pd.DataFrame(all_klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
        ])

        # Convert data types
        df['timestamp'] = pd.to_numeric(df['timestamp'])
        df['open'] = pd.to_numeric(df['open'])
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        df['close'] = pd.to_numeric(df['close'])
        df['volume'] = pd.to_numeric(df['volume'])

        # Remove duplicates and sort
        df = df.drop_duplicates(subset=['timestamp'])
        df = df.sort_values('timestamp')

        # Convert timestamp to datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        # Keep only required columns
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]

        logger.info(f"Total candles downloaded: {len(df)}")
        logger.info(f"Date range: {df.iloc[0]['timestamp']} to {df.iloc[-1]['timestamp']}")
        logger.info(f"Price range: ${df['close'].min():.2f} to ${df['close'].max():.2f}")

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

            output_file = f"{output_dir}/{symbol}_{interval}m_{days}d_bybit.csv"

            df = await self.download_historical_data(
                symbol=symbol,
                interval=interval,
                days=days,
                output_file=output_file
            )

            logger.info(f"✓ {symbol} complete: {len(df)} candles\n")

            # Longer delay between symbols
            await asyncio.sleep(1.0)


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Download historical data from Bybit API")
    parser.add_argument('--symbol', type=str, default='BTCUSDT', help='Trading pair (default: BTCUSDT)')
    parser.add_argument('--interval', type=str, default='60', help='Interval in minutes (default: 60)')
    parser.add_argument('--days', type=int, default=90, help='Days of historical data (default: 90)')
    parser.add_argument('--output', type=str, help='Output CSV file')
    parser.add_argument('--testnet', action='store_true', help='Use testnet API')
    parser.add_argument('--multiple', nargs='+', help='Download multiple symbols')

    args = parser.parse_args()

    fetcher = BybitDataFetcher(testnet=args.testnet)

    try:
        if args.multiple:
            # Download multiple symbols
            await fetcher.download_multiple_symbols(
                symbols=args.multiple,
                interval=args.interval,
                days=args.days
            )
        else:
            # Download single symbol
            output_file = args.output or f"backtesting/data/{args.symbol}_{args.interval}m_{args.days}d_bybit.csv"

            df = await fetcher.download_historical_data(
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
                print(f"Price Range: ${df['close'].min():.2f} to ${df['close'].max():.2f}")
                print(f"File: {output_file}")
                print("="*80)

                # Show first and last few rows
                print("\nFirst 5 candles:")
                print(df.head())
                print("\nLast 5 candles:")
                print(df.tail())

    finally:
        await fetcher.close()


if __name__ == "__main__":
    asyncio.run(main())
