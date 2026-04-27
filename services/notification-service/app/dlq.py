"""
Notification dead-letter queue.

When delivery to all enabled channels fails after retries, the alert is parked
here so it can be inspected, replayed, or audited later. The original incident
that drove the false-success fix could have been caught hours earlier with a
non-empty DLQ visible on a dashboard.

SQLite (stdlib, no extra dep) keyed off a file under /app/data so it survives
container restarts. Writes use a fresh connection per call — sqlite3 isn't
async-friendly, but at our volume (one row per failed alert, max ~10/min)
the synchronous overhead is in the tens of microseconds.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(os.getenv("DLQ_DB_PATH", "/app/data/dlq.sqlite3"))
_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS failed_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    failed_channels TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    response_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_failed_alerts_created ON failed_alerts(created_at DESC);
"""


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_dlq(path: Optional[Path] = None) -> None:
    p = path or _DEFAULT_PATH
    try:
        with _lock, _connect(p) as conn:
            conn.executescript(_SCHEMA)
        logger.info("Notification DLQ initialised at %s", p)
    except Exception as e:
        # DLQ should never crash the service. Loud log + carry on; subsequent
        # enqueue calls will keep trying and emit their own errors.
        logger.error("Failed to init DLQ at %s: %s", p, e)


def enqueue(
    *,
    endpoint: str,
    failed_channels: List[str],
    payload: Dict[str, Any],
    response: Dict[str, Any],
    path: Optional[Path] = None,
) -> None:
    p = path or _DEFAULT_PATH
    try:
        with _lock, _connect(p) as conn:
            conn.execute(
                "INSERT INTO failed_alerts (created_at, endpoint, failed_channels, payload_json, response_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    datetime.utcnow().isoformat() + "Z",
                    endpoint,
                    ",".join(failed_channels),
                    json.dumps(payload, default=str),
                    json.dumps(response, default=str),
                ),
            )
    except Exception as e:
        # Same rule: DLQ failure must not block the response cycle. Log critical
        # so the operator notices that the safety net itself is broken.
        logger.critical(
            "DLQ ENQUEUE FAILED endpoint=%s channels=%s error=%s",
            endpoint, failed_channels, e,
        )


def list_recent(limit: int = 50, path: Optional[Path] = None) -> List[Dict[str, Any]]:
    p = path or _DEFAULT_PATH
    try:
        with _lock, _connect(p) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT id, created_at, endpoint, failed_channels, payload_json, response_json "
                "FROM failed_alerts ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return [
                {
                    "id": r["id"],
                    "created_at": r["created_at"],
                    "endpoint": r["endpoint"],
                    "failed_channels": r["failed_channels"].split(",") if r["failed_channels"] else [],
                    "payload": json.loads(r["payload_json"]),
                    "response": json.loads(r["response_json"]),
                }
                for r in cur.fetchall()
            ]
    except Exception as e:
        logger.error("DLQ list failed at %s: %s", p, e)
        return []


def count(path: Optional[Path] = None) -> int:
    p = path or _DEFAULT_PATH
    try:
        with _lock, _connect(p) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM failed_alerts").fetchone()[0])
    except Exception:
        return -1
