"""One-shot backfill of TimescaleDB klines table from data/ml_training/*.csv.

CSVs are 1H candles spanning 24 months, originally collected for GRU training.
Same data is fine for strategy backtesting (relative patterns matter, not
absolute prices). Live mainnet data and historical testnet data don't share
timestamps, so ON CONFLICT DO NOTHING preserves whichever was inserted first.

Run from host:
    docker cp scripts/backfill_klines_from_csv.py crypto-bot-market-data:/tmp/
    docker exec -e DB_HOST=timescaledb crypto-bot-market-data python /tmp/backfill_klines_from_csv.py
"""

from __future__ import annotations

import csv
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

CSV_DIR = Path(os.getenv("CSV_DIR", "/app/data/ml_training"))
SYMBOLS = ["SOLUSDT", "BNBUSDT", "ADAUSDT", "BTCUSDT", "ETHUSDT"]
INTERVAL = "60"
BATCH_SIZE = 2000


def connect():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "timescaledb"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "cryptobot"),
        password=os.getenv("DB_PASSWORD", "cryptobot_secure_2024"),
        dbname=os.getenv("DB_NAME", "market_data"),
    )


def find_csv(symbol: str) -> Path | None:
    matches = sorted(CSV_DIR.glob(f"{symbol}_1H_*.csv"))
    if not matches:
        return None
    return matches[-1]


def parse_row(row: dict, symbol: str, now_ms: int) -> tuple | None:
    ts_str = row.get("timestamp")
    if not ts_str:
        return None
    dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    ts_ms = int(dt.timestamp() * 1000)
    return (
        ts_ms,
        symbol,
        INTERVAL,
        float(row["open"]),
        float(row["high"]),
        float(row["low"]),
        float(row["close"]),
        float(row["volume"]),
        None,
        now_ms,
    )


def backfill_symbol(conn, symbol: str) -> tuple[int, int]:
    csv_path = find_csv(symbol)
    if csv_path is None:
        print(f"  {symbol}: no CSV under {CSV_DIR}, skipping")
        return (0, 0)

    print(f"  {symbol}: reading {csv_path.name}")
    now_ms = int(time.time() * 1000)
    rows = []
    with csv_path.open() as f:
        for r in csv.DictReader(f):
            parsed = parse_row(r, symbol, now_ms)
            if parsed:
                rows.append(parsed)

    if not rows:
        return (0, 0)

    sql = (
        "INSERT INTO klines "
        "(timestamp, symbol, interval, open, high, low, close, volume, turnover, created_at) "
        "VALUES %s "
        "ON CONFLICT (timestamp, symbol, interval) DO NOTHING"
    )
    inserted = 0
    with conn.cursor() as cur:
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            execute_values(cur, sql, batch, page_size=BATCH_SIZE)
            inserted += cur.rowcount
        conn.commit()
    return (len(rows), inserted)


def main():
    if not CSV_DIR.exists():
        print(f"CSV_DIR {CSV_DIR} not found")
        sys.exit(1)

    conn = connect()
    total_read, total_inserted = 0, 0
    print(f"Backfilling {len(SYMBOLS)} symbols from {CSV_DIR}")
    for sym in SYMBOLS:
        read, inserted = backfill_symbol(conn, sym)
        total_read += read
        total_inserted += inserted
        print(f"    -> read={read} inserted={inserted} (skipped={read - inserted} existing)")

    with conn.cursor() as cur:
        cur.execute(
            "SELECT symbol, COUNT(*) AS n, "
            "to_timestamp(MIN(timestamp)/1000) AT TIME ZONE 'UTC' AS first_ts, "
            "to_timestamp(MAX(timestamp)/1000) AT TIME ZONE 'UTC' AS last_ts "
            "FROM klines WHERE interval=%s AND symbol = ANY(%s) GROUP BY symbol ORDER BY symbol",
            (INTERVAL, SYMBOLS),
        )
        print("\nFinal klines counts (interval=60):")
        for symbol, n, first_ts, last_ts in cur.fetchall():
            print(f"  {symbol:8s}  count={n:6d}  range={first_ts}  ->  {last_ts}")

    conn.close()
    print(f"\nTotal: read={total_read}, inserted={total_inserted}")


if __name__ == "__main__":
    main()
