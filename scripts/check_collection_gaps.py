#!/usr/bin/env python3
"""Gap check for edge-search v2 collections (spec §2 verification #4).

Thresholds: orderbook inter-snapshot gap <= 60s; OI gap <= 15min, per symbol.
Runs psql inside the timescaledb container so it needs no host DB driver.
Exit 0 clean, 1 on any breach or empty table. Also prints table sizes
(spec §9.3 disk watch).
"""

import subprocess
import sys

PSQL = [
    "docker",
    "exec",
    "crypto-bot-timescaledb",
    "psql",
    "-U",
    "cryptobot",
    "-d",
    "market_data",
    "-t",
    "-A",
    "-F",
    "|",
]

CHECKS = [
    ("orderbook_snapshots", 60_000),
    ("open_interest", 900_000),
]


def q(sql: str) -> list[list[str]]:
    out = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, check=True)
    return [line.split("|") for line in out.stdout.strip().splitlines() if line]


breaches = 0
for table, max_gap_ms in CHECKS:
    rows = q(
        f"SELECT symbol, count(*), min(timestamp), max(timestamp), "
        f"COALESCE(max(gap),0) FROM (SELECT symbol, timestamp, "
        f"timestamp - lag(timestamp) OVER (PARTITION BY symbol ORDER BY timestamp) "
        f"AS gap FROM {table}) g GROUP BY symbol ORDER BY symbol"
    )
    size = q(f"SELECT pg_size_pretty(pg_total_relation_size('{table}'))")[0][0]
    print(f"== {table} (size {size}, max gap allowed {max_gap_ms}ms)")
    if not rows:
        print("  EMPTY TABLE — breach")
        breaches += 1
        continue
    for symbol, n, tmin, tmax, maxgap in rows:
        ok = int(maxgap) <= max_gap_ms
        print(
            f"  {symbol}: rows={n} span={tmin}..{tmax} max_gap_ms={maxgap} {'OK' if ok else 'BREACH'}"
        )
        breaches += 0 if ok else 1

print(f"RESULT: gap_breaches={breaches}")
sys.exit(1 if breaches else 0)
