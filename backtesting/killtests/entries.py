"""Closed-entry fixture: the 13 CLOSED paper positions, extracted once from Postgres.

Regenerate with:  python3 backtesting/killtests/entries.py --extract
(requires crypto-bot-postgres up; read-only). The committed fixture is the
source of record for H3 — replays never touch the DB.
"""

import argparse
import json
import os
import subprocess
from dataclasses import dataclass

DEFAULT_FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "closed_entries_2026-08.json"
)

_SQL = """
COPY (
  SELECT json_agg(row_to_json(t)) FROM (
    SELECT p.id, p.position_id::text, p.symbol, p.side, p.quantity::float8,
           p.entry_price::float8, p.exit_price::float8 AS actual_exit_price,
           p.realized_pnl::float8 AS actual_realized_pnl,
           (EXTRACT(EPOCH FROM p.opened_at) * 1000)::bigint AS entry_ts_ms,
           (EXTRACT(EPOCH FROM p.closed_at) * 1000)::bigint AS exit_ts_ms,
           tr.signal_confidence::float8
    FROM positions p
    LEFT JOIN trades tr
      ON tr.metadata->>'position_id' = p.position_id::text
     AND tr.side = CASE WHEN p.side = 'LONG' THEN 'BUY' ELSE 'SELL' END
     AND tr.strategy = 'ensemble'
    WHERE p.status = 'CLOSED'
    ORDER BY p.closed_at
  ) t
) TO STDOUT;
"""


@dataclass(frozen=True)
class Entry:
    position_id: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    entry_ts_ms: int
    exit_ts_ms: int
    actual_exit_price: float
    actual_realized_pnl: float
    signal_confidence: float | None


def load_entries(path: str = DEFAULT_FIXTURE) -> list:
    with open(path) as f:
        doc = json.load(f)
    return [
        Entry(
            position_id=str(r["position_id"]),
            symbol=r["symbol"],
            side=r["side"],
            quantity=r["quantity"],
            entry_price=r["entry_price"],
            entry_ts_ms=r["entry_ts_ms"],
            exit_ts_ms=r["exit_ts_ms"],
            actual_exit_price=r["actual_exit_price"],
            actual_realized_pnl=r["actual_realized_pnl"],
            signal_confidence=r.get("signal_confidence"),
        )
        for r in doc["entries"]
    ]


def extract() -> None:
    out = subprocess.run(
        [
            "docker",
            "exec",
            "crypto-bot-postgres",
            "psql",
            "-U",
            "cryptobot",
            "-d",
            "cryptobot",
            "-At",
            "-c",
            _SQL,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    rows = json.loads(out.stdout.strip())
    # 13 is what the DB held when this fixture was first cut; the assert
    # exists to catch a broken LEFT JOIN silently multiplying or dropping
    # rows, not to claim the table can never legitimately grow.
    assert len(rows) == 13, (
        f"expected 13 closed positions, got {len(rows)}. More than 13 with "
        "duplicate position_ids means the side-matched trades join went "
        "multiplicative; fewer means rows were dropped. If paper trading has "
        "genuinely closed more positions since 2026-08-05, that is a fixture "
        "re-baseline (bump this number, re-run H3, and write a NEW dated "
        "verdict) — not a bug to suppress."
    )
    shorts = [r for r in rows if r["side"] == "SHORT"]
    assert shorts, "no SHORT rows — side-matched join is wrong"
    tz = subprocess.run(
        [
            "docker",
            "exec",
            "crypto-bot-postgres",
            "psql",
            "-U",
            "cryptobot",
            "-d",
            "cryptobot",
            "-At",
            "-c",
            "SHOW timezone;",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    doc = {
        "provenance": {
            "extracted_from": "crypto-bot-postgres db=cryptobot",
            "sql": _SQL.strip(),
            "timezone_check": tz,
            "note": "naive timestamps interpreted as UTC; epoch conversion done in SQL",
            "row_count": len(rows),
        },
        "entries": rows,
    }
    os.makedirs(os.path.dirname(DEFAULT_FIXTURE), exist_ok=True)
    with open(DEFAULT_FIXTURE, "w") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
    print(f"wrote {len(rows)} entries to {DEFAULT_FIXTURE}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", action="store_true")
    args = ap.parse_args()
    if args.extract:
        extract()
