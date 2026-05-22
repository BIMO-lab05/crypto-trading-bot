#!/usr/bin/env python3
"""
Simple data downloader for final 4 symbols

BC-02 (Phase 13): Routes through bybit-connector REST (was direct api.bybit.com).
Fail-fasts (exit 2) if BYBIT_CONNECTOR_URL is unreachable. See
.planning/phases/13-bybit-connector-market-data-centralization/.
"""

import asyncio
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SYMBOLS = ["LINKUSDT", "OPUSDT", "POLUSDT", "SUIUSDT"]
INTERVAL = "60"
MONTHS = 24
OUTPUT_DIR = _REPO_ROOT / "data/ml_training"

# BC-02: Route through bybit-connector REST. Host-friendly default; compose
# env override to http://bybit-connector:8001 when running in-container.
BYBIT_CONNECTOR_URL = os.getenv("BYBIT_CONNECTOR_URL", "http://localhost:8001")
KLINE_ENDPOINT = "/api/v1/market/kline"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


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


async def fetch_klines(client, symbol, start_ms, end_ms):
    """Fetch klines from bybit-connector"""
    try:
        params = {
            "category": "spot",
            "symbol": symbol,
            "interval": INTERVAL,
            "start": start_ms,
            "end": end_ms,
            "limit": 1000,
        }

        resp = await client.get(KLINE_ENDPOINT, params=params)
        if resp.status_code == 200:
            # BC-02 parser swap: wrapper-shape {success, data}. httpx .json() is sync.
            data = resp.json()
            if data.get("success"):
                raw = data.get("data", {})
                if isinstance(raw, dict):
                    return raw.get("list", [])
                return raw or []
    except Exception as e:
        print(f"    Error: {e}")
    return None


async def download_symbol(symbol):
    """Download 24 months of data"""
    print(f"\n{'=' * 80}")
    print(f"[{symbol}] Downloading 24-month hourly data")
    print(f"{'=' * 80}")

    end_time = datetime.now()
    start_time = end_time - timedelta(days=MONTHS * 30)

    end_ms = int(end_time.timestamp() * 1000)
    start_ms = int(start_time.timestamp() * 1000)

    all_klines = []
    current_start = start_ms
    batch = 0

    async with httpx.AsyncClient(base_url=BYBIT_CONNECTOR_URL, timeout=30.0) as client:
        while current_start < end_ms:
            batch += 1
            batch_end = min(current_start + (1000 * 60 * 60 * 1000), end_ms)

            if batch % 5 == 1:
                print(
                    f"  Batch {batch}: {datetime.fromtimestamp(current_start / 1000).strftime('%Y-%m-%d')} to {datetime.fromtimestamp(batch_end / 1000).strftime('%Y-%m-%d')}"
                )

            klines = await fetch_klines(client, symbol, current_start, batch_end)

            if klines:
                all_klines.extend(klines)
                if len(klines) < 1000:
                    break
                last_time = int(klines[-1][0])
                current_start = last_time + 1
            else:
                print("    No more data")
                break

            await asyncio.sleep(0.2)

    if not all_klines:
        print("  No data downloaded")
        return None

    # Convert to DataFrame
    df = pd.DataFrame(
        all_klines,
        columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"],
    )

    df["timestamp"] = pd.to_datetime(df["timestamp"].astype(float), unit="ms")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    df = df.sort_values("timestamp").reset_index(drop=True)
    df = df.drop_duplicates(subset=["timestamp"], keep="first")
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]

    # Filter to exactly 24 months
    df = df[df["timestamp"] >= start_time]

    print(f"  Downloaded {len(df):,} candles")
    print(f"  Range: {df['timestamp'].min()} to {df['timestamp'].max()}")

    return df


async def main():
    print("\n" + "=" * 100)
    print("DOWNLOADING DATA FOR FINAL 4 SYMBOLS")
    print("=" * 100)
    print(f"Symbols: {', '.join(SYMBOLS)}")
    print(f"Period: {MONTHS} months")
    print(f"bybit-connector: {BYBIT_CONNECTOR_URL}")
    print("=" * 100)

    start_time = time.time()
    results = {}

    for i, symbol in enumerate(SYMBOLS, 1):
        print(f"\n[{i}/{len(SYMBOLS)}] {symbol}")

        try:
            df = await download_symbol(symbol)

            if df is not None and len(df) > 0:
                # Save
                today = datetime.now().strftime("%Y%m%d")
                filename = f"{symbol}_1H_24months_{today}.csv"
                filepath = OUTPUT_DIR / filename
                df.to_csv(filepath, index=False)

                size_kb = filepath.stat().st_size / 1024
                print(f"  Saved: {filename} ({size_kb:.1f} KB)")
                results[symbol] = "SUCCESS"
            else:
                results[symbol] = "FAILED"

        except Exception as e:
            print(f"  Error: {e}")
            results[symbol] = "FAILED"

        await asyncio.sleep(1)

    # Summary
    elapsed = time.time() - start_time
    successful = sum(1 for r in results.values() if r == "SUCCESS")

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"Time: {elapsed / 60:.1f} minutes")
    print(f"Success: {successful}/{len(SYMBOLS)}")
    print()
    for symbol, status in results.items():
        print(f"  {symbol}: {status}")
    print("=" * 100)


if __name__ == "__main__":
    # BC-02 / D-04: fail-fast BEFORE any other work.
    _check_or_exit()
    asyncio.run(main())
