#!/usr/bin/env python3
"""
Simple synchronous download for OPUSDT and SUIUSDT - 6 months data

BC-02 (Phase 13): Routes through bybit-connector REST (was direct api.bybit.com).
Fail-fasts (exit 2) if BYBIT_CONNECTOR_URL is unreachable.

Note: Per advisor + plan Open Q #6, this script's main loop keeps `requests`
(synchronous) because the original is sync. Only the connector reachability
probe uses httpx (run via asyncio.run from sync wrapper). Smaller diff;
URL+parser swap still mandatory.

[Rule 1 bug fix] Pre-existing bug at the CSV path: `fstr(...)` was not a real
function — should have been an f-string. Fixed inline during this refactor.
"""

import asyncio
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path as _Path

import httpx
import pandas as pd
import requests

_REPO_ROOT = _Path(__file__).resolve().parent.parent.parent

# BC-02: Route through bybit-connector REST. Host-friendly default; compose
# env override to http://bybit-connector:8001 when running in-container.
BYBIT_CONNECTOR_URL = os.getenv("BYBIT_CONNECTOR_URL", "http://localhost:8001")
KLINE_ENDPOINT = "/api/v1/market/kline"


async def assert_connector_reachable() -> None:
    """BC-02 / D-04: fail-fast with operator-readable error if bybit-connector down."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{BYBIT_CONNECTOR_URL}/health")
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


def _check_or_exit() -> None:
    """Synchronous wrapper for the connector reachability check."""
    asyncio.run(assert_connector_reachable())


def download_symbol(symbol, months=6):
    """Download historical data for a symbol via bybit-connector REST"""
    print(f"\n{'=' * 80}")
    print(f"DOWNLOADING: {symbol} ({months} months)")
    print(f"{'=' * 80}")

    # Calculate start time (months ago)
    end_time = datetime.now()
    start_time = end_time - timedelta(days=months * 30)
    start_ms = int(start_time.timestamp() * 1000)
    end_ms = int(end_time.timestamp() * 1000)

    all_data = []
    current_start = start_ms
    batch = 0

    while current_start < end_ms:
        batch += 1
        # BC-02 URL swap: bybit-connector REST endpoint.
        url = f"{BYBIT_CONNECTOR_URL}{KLINE_ENDPOINT}"
        params = {
            "category": "spot",
            "symbol": symbol,
            "interval": "60",  # 1 hour
            "start": current_start,
            "limit": 1000,
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # BC-02 parser swap: wrapper-shape {success, data}.
            if not data.get("success"):
                print(f"bybit-connector non-success response: {data}")
                break

            raw = data.get("data", {})
            if isinstance(raw, dict):
                candles = raw.get("list", [])
            else:
                candles = raw or []

            if not candles:
                print(f"No more data, stopping at batch {batch}")
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
            print(f"Error in batch {batch}: {e}")
            break

    if not all_data:
        print(f"No data collected for {symbol}")
        return None

    # Create DataFrame
    df = pd.DataFrame(
        all_data,
        columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"].astype(float), unit="ms")

    # Convert to numeric
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("timestamp").reset_index(drop=True)

    # Save  [Rule 1 fix] was `fstr(...)` literal — replaced with real f-string.
    output_file = str(_REPO_ROOT / f"data/ml_training/{symbol}_1H_6months_20251210.csv")
    df[["timestamp", "open", "high", "low", "close", "volume"]].to_csv(
        output_file, index=False
    )

    print(f"\nCOMPLETE: {symbol}")
    print(f"   Rows: {len(df)}")
    print(f"   Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"   Saved: {output_file}")

    return output_file


if __name__ == "__main__":
    # BC-02 / D-04: fail-fast BEFORE any other work.
    _check_or_exit()

    symbols = ["OPUSDT", "SUIUSDT"]

    print("\n" + "=" * 80)
    print("DOWNLOADING 6-MONTH DATA FOR OPUSDT AND SUIUSDT")
    print("=" * 80)
    print(f"bybit-connector: {BYBIT_CONNECTOR_URL}")
    print("=" * 80)

    for symbol in symbols:
        result = download_symbol(symbol, months=6)
        if result:
            print(f"{symbol} downloaded successfully")
        else:
            print(f"{symbol} download failed")

    print("\n" + "=" * 80)
    print("DOWNLOAD COMPLETE")
    print("=" * 80 + "\n")
