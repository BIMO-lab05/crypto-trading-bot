#!/usr/bin/env python3
"""
ML Training Data Collection Script - Simplified
================================================
Collects comprehensive historical data for ML model training via bybit-connector REST.

Phase 13 / BC-02: pybit dependency removed; the connector handles testnet/mainnet
selection internally via BYBIT_TESTNET. Fail-fast (D-04) on connector unreachable.

Target: 12-24 months of data
Timeframes: 1H, 4H, 1D
Symbols: 10 major cryptocurrencies
Purpose: Provide sufficient data for robust ML training
"""

from __future__ import annotations

import os  # noqa: F401  -- used by BYBIT_CONNECTOR_URL os.getenv below; guard against autoflake
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List
import requests

# Heavy deps (pandas) imported lazily so the D-04 fail-fast probe can fire on
# hosts without pandas installed (e.g. CI runners verifying only the fail-fast
# contract). Re-checked once probe passes in main().
try:
    import pandas as pd  # noqa: F401
except ImportError as _e:
    pd = None  # type: ignore[assignment]
    _HEAVY_IMPORT_ERROR = _e
else:
    _HEAVY_IMPORT_ERROR = None


# Phase 13 / BC-02: route through bybit-connector REST (no direct Bybit URLs, no pybit).
BYBIT_CONNECTOR_URL = os.getenv("BYBIT_CONNECTOR_URL", "http://localhost:8001")


def assert_connector_reachable() -> None:
    """D-04 fail-fast: exit 2 with operator-readable error if connector unreachable.

    Runs BEFORE any other __main__ logic — including the input() prompt — so
    `tests/integration/test_scripts_fail_fast.py` (no-args invocation, no stdin)
    triggers the probe and exits 2 instead of raising EOFError on the prompt.
    """
    try:
        response = requests.get(f"{BYBIT_CONNECTOR_URL}/health", timeout=5.0)
        response.raise_for_status()
    except Exception as e:
        print(
            f"\nERROR: bybit-connector is not reachable at {BYBIT_CONNECTOR_URL}.\n"
            f"  Cause: {e!r}\n"
            f"  Fix:   Run `docker compose -f docker-compose.unified.yml up -d bybit-connector`\n"
            f"  (or set BYBIT_CONNECTOR_URL if running against a non-default host).\n",
            file=sys.stderr,
        )
        sys.exit(2)


class SimpleMLDataCollector:
    """Collect historical data for ML training via bybit-connector REST"""

    def __init__(self):
        # bybit-connector REST URL (no direct Bybit; no auth — public kline)
        self.connector_url = BYBIT_CONNECTOR_URL

        # Output directory
        self.output_dir = Path(__file__).parent.parent / "data" / "ml_training"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        print(f"Output directory: {self.output_dir}")

    def collect_symbol_timeframe(
        self, symbol: str, interval: str, months: int = 24
    ) -> pd.DataFrame:
        """
        Collect data for one symbol and timeframe

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            interval: Candle interval ('60' = 1H, '240' = 4H, 'D' = 1D)
            months: Number of months to collect

        Returns:
            DataFrame with OHLCV data
        """
        print(f"\n{'=' * 80}")
        print(f"Collecting {symbol} - {interval} interval")
        print(f"{'=' * 80}")

        # Calculate time range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months * 30)

        end_time_ms = int(end_date.timestamp() * 1000)
        start_time_ms = int(start_date.timestamp() * 1000)

        print(
            f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
        )

        all_candles = []
        current_end = end_time_ms
        batch_count = 0

        while True:
            try:
                # Fetch batch of candles (limit = 200 per request) via bybit-connector
                http_response = requests.get(
                    f"{self.connector_url}/api/v1/market/kline",
                    params={
                        "category": "linear",
                        "symbol": symbol,
                        "interval": interval,
                        "limit": 200,
                        "end": current_end,
                    },
                    timeout=30,
                )
                http_response.raise_for_status()
                response = http_response.json()

                if not response.get("success"):
                    print(
                        f"⚠️ bybit-connector error: "
                        f"{response.get('error') or response.get('message')}"
                    )
                    break

                candles = response["data"]["list"]

                if not candles:
                    print("✅ Reached end of available data")
                    break

                # Add candles to collection
                all_candles.extend(candles)
                batch_count += 1

                # Get oldest timestamp from batch
                oldest_timestamp = int(candles[-1][0])

                # Check if we've reached the start of our period
                if oldest_timestamp <= start_time_ms:
                    print("✅ Reached target start date")
                    break

                # Update for next batch
                current_end = oldest_timestamp - 1

                # Progress update every 10 batches
                if batch_count % 10 == 0:
                    current_date = datetime.fromtimestamp(oldest_timestamp / 1000)
                    print(
                        f"   Batch {batch_count}: {len(all_candles)} candles collected (now at {current_date.strftime('%Y-%m-%d')})"
                    )

                # Rate limiting: Bybit allows 120 requests/minute
                time.sleep(0.5)

            except Exception as e:
                print(f"❌ Error: {e}")
                break

        print("\n✅ Collection complete:")
        print(f"   Total candles: {len(all_candles)}")
        print(f"   Batches: {batch_count}")

        if not all_candles:
            print("⚠️ No data collected")
            return pd.DataFrame()

        # Convert to DataFrame
        # Bybit format: [timestamp, open, high, low, close, volume, turnover]
        df = pd.DataFrame(
            all_candles,
            columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"],
        )

        # Convert types
        df["timestamp"] = pd.to_datetime(df["timestamp"].astype(int), unit="ms")
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)

        # Sort by timestamp ascending (Bybit returns newest first)
        df = df.sort_values("timestamp").reset_index(drop=True)

        # Filter to exact period
        df = df[(df["timestamp"] >= start_date) & (df["timestamp"] <= end_date)]

        print(f"   Final dataset: {len(df)} candles")
        print(f"   Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")

        return df

    def collect_all_data(
        self, symbols: List[str], intervals: List[str], months: int = 24
    ):
        """
        Collect data for all symbols and timeframes

        Args:
            symbols: List of trading pairs
            intervals: List of intervals ('60', '240', 'D')
            months: Number of months to collect
        """
        print("=" * 80)
        print("ML TRAINING DATA COLLECTION")
        print("=" * 80)
        print(f"Target: {months} months of historical data")
        print(f"Symbols: {len(symbols)}")
        print(f"Timeframes: {len(intervals)}")
        print(f"Total datasets: {len(symbols) * len(intervals)}")
        print(f"Output: {self.output_dir}")
        print("=" * 80)

        total_datasets = len(symbols) * len(intervals)
        completed = 0

        summary = []

        for symbol in symbols:
            for interval in intervals:
                completed += 1
                print(
                    f"\n[{completed}/{total_datasets}] Processing {symbol} - {interval}"
                )

                try:
                    # Collect data
                    df = self.collect_symbol_timeframe(
                        symbol=symbol, interval=interval, months=months
                    )

                    if df.empty:
                        print(f"⚠️ No data collected for {symbol} - {interval}")
                        summary.append(
                            {
                                "symbol": symbol,
                                "interval": interval,
                                "candles": 0,
                                "status": "FAILED",
                            }
                        )
                        continue

                    # Save to CSV
                    interval_name = {"60": "1H", "240": "4H", "D": "1D"}[interval]

                    filename = f"{symbol}_{interval_name}_{months}months_{datetime.now().strftime('%Y%m%d')}.csv"
                    filepath = self.output_dir / filename

                    df[["timestamp", "open", "high", "low", "close", "volume"]].to_csv(
                        filepath, index=False
                    )

                    print(f"✅ Saved: {filepath}")
                    print(f"   Size: {filepath.stat().st_size / 1024:.1f} KB")

                    summary.append(
                        {
                            "symbol": symbol,
                            "interval": interval_name,
                            "candles": len(df),
                            "file": filename,
                            "status": "SUCCESS",
                        }
                    )

                except Exception as e:
                    print(f"❌ Error collecting {symbol} - {interval}: {e}")
                    summary.append(
                        {
                            "symbol": symbol,
                            "interval": interval,
                            "candles": 0,
                            "status": "ERROR",
                            "error": str(e),
                        }
                    )

                # Brief pause between datasets
                time.sleep(1)

        # Print summary
        print("\n" + "=" * 80)
        print("COLLECTION SUMMARY")
        print("=" * 80)

        summary_df = pd.DataFrame(summary)

        print(f"\nTotal datasets: {len(summary_df)}")
        print(f"Successful: {len(summary_df[summary_df['status'] == 'SUCCESS'])}")
        print(f"Failed: {len(summary_df[summary_df['status'] != 'SUCCESS'])}")

        if len(summary_df[summary_df["status"] == "SUCCESS"]) > 0:
            print(
                f"\nTotal candles collected: {summary_df[summary_df['status'] == 'SUCCESS']['candles'].sum():,}"
            )
            print(
                f"Average per dataset: {summary_df[summary_df['status'] == 'SUCCESS']['candles'].mean():.0f}"
            )

        # Save summary
        summary_file = (
            self.output_dir
            / f"collection_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        summary_df.to_csv(summary_file, index=False)
        print(f"\nSummary saved: {summary_file}")

        # Print detailed results
        print("\nDetailed Results:")
        print("-" * 80)
        for _, row in summary_df.iterrows():
            status_icon = "✅" if row["status"] == "SUCCESS" else "❌"
            print(
                f"{status_icon} {row['symbol']:10} {row['interval']:4} - {row['candles']:6,} candles"
            )

        print("\n" + "=" * 80)
        print("COLLECTION COMPLETE")
        print("=" * 80)


if __name__ == "__main__":
    # D-04 fail-fast: BEFORE any input() or other __main__ logic so no-args invocation
    # (no stdin attached) triggers the connector probe and exits 2 rather than tripping
    # the interactive input() prompt below.
    assert_connector_reachable()

    # Heavy deps required at run-time once probe passes
    if _HEAVY_IMPORT_ERROR is not None:
        raise ImportError(
            f"collect_ml_training_data_simple requires pandas at run-time: "
            f"{_HEAVY_IMPORT_ERROR!r}"
        )

    # Configuration
    SYMBOLS = [
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "BNBUSDT",
        "ADAUSDT",
        "APTUSDT",
        "DOTUSDT",
        "LTCUSDT",
        "AVAXUSDT",
        "ARBUSDT",
    ]

    INTERVALS = ["60", "240", "D"]  # 1H, 4H, 1D

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
    print(
        f"  - Total: ~{len(SYMBOLS) * (MONTHS * 30 * 24 + MONTHS * 30 * 6 + MONTHS * 30):,} candles"
    )
    print(f"  - Estimated time: {len(SYMBOLS) * len(INTERVALS) * 5} minutes")

    response = input("\nProceed with data collection? (yes/no): ")
    if response.lower() != "yes":
        print("Collection cancelled")
        exit(0)

    # Start collection
    collector = SimpleMLDataCollector()
    collector.collect_all_data(symbols=SYMBOLS, intervals=INTERVALS, months=MONTHS)
