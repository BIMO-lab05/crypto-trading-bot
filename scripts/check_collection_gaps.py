#!/usr/bin/env python3
"""Gap check for edge-search v2 collections (spec §2 verification #4).

Thresholds: orderbook inter-snapshot gap <= 60s; OI gap <= 15min, per symbol.
Also, orderbook achieved-cadence: avg inter-snapshot gap per symbol over the
last hour must be <= 7500ms (1.5x the nominal 5s cadence) — final review H-2
noted the plain 60s outage threshold is ~10x the target cadence and would let
a degradation from 5s to 50s pass silently. This check is evaluated on the
last hour of rows only (--window-minutes overrides), never against the full
table history, so a stale pre-fix batch never dilutes it and it never gets
loosened past 7500ms.

Runs psql inside the timescaledb container so it needs no host DB driver.
Exit 0 clean, 1 on any breach or empty table. Also prints table sizes
(spec §9.3 disk watch) via hypertable_size(), falling back to
pg_total_relation_size() if the hypertable call errors — the latter measures
only the empty parent on a hypertable and under-reports by ~186x (final
review M-7).

Tables are queried as public.<table> explicitly (final review L-11): a decoy
market_data.orderbook_snapshots hypertable exists, empty, in a different
schema. Querying it unqualified can silently resolve there depending on
search_path.
"""

import argparse
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

# Achieved-cadence gate, orderbook_snapshots only (final review H-2). 1.5x
# nominal 5s cadence. Never loosen this to make a mixed/stale window pass —
# widen --window-minutes or fix the collector instead.
ORDERBOOK_CADENCE_MAX_AVG_GAP_MS = 7_500

parser = argparse.ArgumentParser()
parser.add_argument(
    "--window-minutes",
    type=int,
    default=60,
    help="Evaluate the orderbook cadence assertion over the last N minutes "
    "of rows only (default 60). State this window explicitly when citing "
    "the result — it is never evaluated against full table history.",
)
args = parser.parse_args()
WINDOW_MS = args.window_minutes * 60_000


def q(sql: str) -> list[list[str]]:
    out = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, check=True)
    return [line.split("|") for line in out.stdout.strip().splitlines() if line]


def table_size(table: str) -> str:
    try:
        return q(f"SELECT pg_size_pretty(hypertable_size('public.{table}'))")[0][0]
    except subprocess.CalledProcessError:
        return q(f"SELECT pg_size_pretty(pg_total_relation_size('public.{table}'))")[0][
            0
        ]


breaches = 0
for table, max_gap_ms in CHECKS:
    rows = q(
        f"SELECT symbol, count(*), min(timestamp), max(timestamp), "
        f"COALESCE(max(gap),0) FROM (SELECT symbol, timestamp, "
        f"timestamp - lag(timestamp) OVER (PARTITION BY symbol ORDER BY timestamp) "
        f"AS gap FROM public.{table}) g GROUP BY symbol ORDER BY symbol"
    )
    size = table_size(table)
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

# Achieved-cadence assertion (final review H-2), orderbook_snapshots only,
# evaluated over the last WINDOW_MS of rows only.
print(
    f"== orderbook_snapshots achieved cadence "
    f"(last {args.window_minutes}min, max avg gap allowed "
    f"{ORDERBOOK_CADENCE_MAX_AVG_GAP_MS}ms)"
)
cadence_rows = q(
    "SELECT symbol, round(avg(gap)) FROM (SELECT symbol, timestamp, "
    "timestamp - lag(timestamp) OVER (PARTITION BY symbol ORDER BY timestamp) "
    "AS gap FROM public.orderbook_snapshots "
    f"WHERE timestamp >= (extract(epoch FROM now()) * 1000)::bigint - {WINDOW_MS}) g "
    "WHERE gap IS NOT NULL GROUP BY symbol ORDER BY symbol"
)
if not cadence_rows:
    print(f"  NO ROWS in last {args.window_minutes}min — breach")
    breaches += 1
else:
    for symbol, avg_gap in cadence_rows:
        ok = float(avg_gap) <= ORDERBOOK_CADENCE_MAX_AVG_GAP_MS
        print(f"  {symbol}: avg_gap_ms={avg_gap} {'OK' if ok else 'BREACH'}")
        breaches += 0 if ok else 1

print(f"RESULT: gap_breaches={breaches}")
sys.exit(1 if breaches else 0)
