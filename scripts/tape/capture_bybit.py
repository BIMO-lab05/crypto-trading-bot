#!/usr/bin/env python3
"""
Bybit Tape Fixture Capture
==========================
Purpose: Capture deterministic, in-repo recorded-tape fixtures for the 5 validated symbols
         (BTC, ETH, SOL, BNB, ADA) covering klines (5-minute) and ticker over a 7-day window
         from Bybit mainnet public REST endpoints.

Decisions honoured:
  D-01: Storage format = JSONL per (feed, symbol), one file per pair.
  D-03: Scope = 5 validated symbols x 7 days, 5m kline cadence + ticker snapshots; <50 MB.
  D-04: Storage location = tests/fixtures/tape/ checked into git; no git-lfs in v1.
  D-05: Capture method = this script, live Bybit mainnet REST, operator runs manually.
  D-06: Refresh cadence = manual on demand only.
  D-07: Schema versioning = first line of every JSONL is a header object with tape_version=1.

Usage:
  python3 scripts/tape/capture_bybit.py [--help]

This script uses ONLY public endpoints — no authentication required.
It can run with a completely empty environment (no exchange credentials needed).
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import requests

# ---------------------------------------------------------------------------
# Constants (D-03, D-05 — do not parameterize away from these)
# ---------------------------------------------------------------------------
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'ADAUSDT']     # D-03 validated set
INTERVAL = '5'                                                           # D-03 5-minute klines
DAYS = 7                                                                 # D-03 7-day window
BYBIT_API_ENDPOINT = 'https://api.bybit.com'                            # D-05 mainnet REST
MAX_LIMIT = 200                                                          # Bybit per-request max
RATE_LIMIT_DELAY = 0.5                                                   # seconds between requests

# Output directory: resolve from scripts/tape/ up 2 levels to repo root, then into tests/
# scripts/tape/capture_bybit.py -> parents[0]=scripts/tape  parents[1]=scripts  parents[2]=repo-root
OUTPUT_DIR = Path(__file__).resolve().parents[2] / 'tests' / 'fixtures' / 'tape'

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# REST helpers — public endpoints only
# ---------------------------------------------------------------------------

def _get(path: str, params: dict) -> dict:
    """
    Send a GET request to the Bybit V5 public endpoint.
    No authentication headers are sent. Exits non-zero on any error.
    """
    url = f"{BYBIT_API_ENDPOINT}{path}"
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    if data.get('retCode') != 0:
        logger.error(
            "Bybit returned retCode=%s retMsg=%s for %s params=%s",
            data.get('retCode'), data.get('retMsg'), path, params
        )
        sys.exit(1)
    return data.get('result', {})


# ---------------------------------------------------------------------------
# Kline capture
# ---------------------------------------------------------------------------

def capture_klines(symbol: str, dry_run: bool = False) -> int:
    """
    Capture 7 days of 5-minute klines for symbol and write JSONL fixture.
    Returns the number of data lines written (not counting the header).

    Bybit V5 kline returns results in DESCENDING timestamp order. We paginate
    backwards using start/end window slices and sort ascending before writing.
    """
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = int((datetime.now(timezone.utc) - timedelta(days=DAYS)).timestamp() * 1000)

    all_klines: List[List[str]] = []
    chunk_end_ms = now_ms

    while chunk_end_ms > start_ms:
        # Each chunk: MAX_LIMIT x 5m candles = 200 x 5m = 1000 minutes
        chunk_start_ms = max(chunk_end_ms - (MAX_LIMIT * int(INTERVAL) * 60 * 1000), start_ms)

        params = {
            'category': 'linear',
            'symbol': symbol,
            'interval': INTERVAL,
            'start': chunk_start_ms,
            'end': chunk_end_ms,
            'limit': MAX_LIMIT,
        }
        result = _get('/v5/market/kline', params)
        raw_list = result.get('list', [])

        if raw_list:
            all_klines.extend(raw_list)
            logger.info(
                "  %s klines: fetched %d candles chunk [%s -> %s]",
                symbol, len(raw_list),
                datetime.fromtimestamp(chunk_start_ms / 1000, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M'),
                datetime.fromtimestamp(chunk_end_ms / 1000, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M'),
            )
        else:
            logger.warning("  %s klines: no candles returned for chunk, stopping", symbol)
            break

        chunk_end_ms = chunk_start_ms
        time.sleep(RATE_LIMIT_DELAY)

    if not all_klines:
        logger.error("No klines collected for %s — aborting", symbol)
        sys.exit(1)

    # Remove duplicates and sort ascending by timestamp (index 0)
    seen: set = set()
    unique_klines: List[List[str]] = []
    for kline in all_klines:
        ts = kline[0]
        if ts not in seen:
            seen.add(ts)
            unique_klines.append(kline)
    unique_klines.sort(key=lambda k: int(k[0]))

    if dry_run:
        logger.info("[dry-run] %s klines: would write %d candles", symbol, len(unique_klines))
        return len(unique_klines)

    # Write JSONL fixture
    out_path = OUTPUT_DIR / 'klines' / f'{symbol}.jsonl'
    out_path.parent.mkdir(parents=True, exist_ok=True)

    header = {
        "tape_version": 1,
        "captured_at": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        "source": "bybit-mainnet",
        "symbol": symbol,
        "feed": "klines",
    }

    with out_path.open('w', encoding='utf-8') as fh:
        fh.write(json.dumps(header) + '\n')
        for kline in unique_klines:
            fh.write(json.dumps(kline) + '\n')

    lines_written = len(unique_klines)
    logger.info("wrote %s (lines=%d)", out_path, lines_written + 1)
    return lines_written


# ---------------------------------------------------------------------------
# Ticker capture
# ---------------------------------------------------------------------------

def capture_ticker(symbol: str, dry_run: bool = False) -> int:
    """
    Capture a single ticker snapshot for symbol and write JSONL fixture.
    Returns the number of data lines written (not counting the header).
    """
    params = {
        'category': 'linear',
        'symbol': symbol,
    }
    result = _get('/v5/market/tickers', params)
    ticker_list = result.get('list', [])

    if not ticker_list:
        logger.error("Empty ticker list returned for %s — aborting", symbol)
        sys.exit(1)

    ticker_record = ticker_list[0]

    if dry_run:
        logger.info("[dry-run] %s ticker: would write 1 snapshot", symbol)
        return 1

    out_path = OUTPUT_DIR / 'ticker' / f'{symbol}.jsonl'
    out_path.parent.mkdir(parents=True, exist_ok=True)

    header = {
        "tape_version": 1,
        "captured_at": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        "source": "bybit-mainnet",
        "symbol": symbol,
        "feed": "ticker",
    }

    with out_path.open('w', encoding='utf-8') as fh:
        fh.write(json.dumps(header) + '\n')
        fh.write(json.dumps(ticker_record) + '\n')

    logger.info("wrote %s (lines=2)", out_path)
    return 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Capture Bybit mainnet kline + ticker fixtures for replay testing. "
            "Writes 10 JSONL files under tests/fixtures/tape/. "
            "Uses only public endpoints — no authentication required."
        )
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate API connectivity and show what would be captured, without writing files.',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dry_run = args.dry_run

    if dry_run:
        logger.info("=== DRY RUN — no files will be written ===")

    logger.info(
        "capture_bybit: symbols=%s interval=%sm days=%d endpoint=%s",
        ','.join(SYMBOLS), INTERVAL, DAYS, BYBIT_API_ENDPOINT,
    )

    total_kline_lines = 0
    total_ticker_lines = 0

    for symbol in SYMBOLS:
        logger.info("--- %s ---", symbol)

        kline_lines = capture_klines(symbol, dry_run=dry_run)
        total_kline_lines += kline_lines
        time.sleep(RATE_LIMIT_DELAY)

        ticker_lines = capture_ticker(symbol, dry_run=dry_run)
        total_ticker_lines += ticker_lines
        time.sleep(RATE_LIMIT_DELAY)

    logger.info(
        "done: %d symbols | klines total=%d | ticker total=%d",
        len(SYMBOLS), total_kline_lines, total_ticker_lines,
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
