"""result.json → leaderboard row pipeline (ingest side).

Single trust boundary: the experiment container's /output/result.json. Bounded
read + schema validate + classify before any SQL insert.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from app.leaderboard.db import LeaderboardDB
from app.leaderboard.result_schema import (
    MAX_RESULT_BYTES,
    validate as validate_result_schema,
)
from app.orchestrator.failure import classify


logger = logging.getLogger(__name__)


PASSWORD_SCRUB_RE = re.compile(
    r"(TIMESCALE_PASSWORD|TOURNAMENT_READER_PASSWORD)=\S+",
    re.IGNORECASE,
)


def _scrub(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    return PASSWORD_SCRUB_RE.sub(r"\1=***", text)


def read_and_validate_result(
    result_path: str | os.PathLike,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Read /output/result.json bounded + schema-validated.

    Returns:
        (payload_dict_or_None, validation_error_or_None).
        - (None, None)  → file missing
        - (None, msg)   → file present but unreadable / oversized / unparseable
        - (dict, None)  → valid
        - (dict, msg)   → parseable JSON but schema_validate raised
    """
    path = Path(result_path)
    if not path.exists():
        return (None, None)
    try:
        size = path.stat().st_size
    except OSError as e:
        return (None, f"stat failed: {e}")
    if size > MAX_RESULT_BYTES:
        return (None, f"oversized result.json: {size} bytes > {MAX_RESULT_BYTES}")
    try:
        raw = path.read_bytes()
    except OSError as e:
        return (None, f"read failed: {e}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        return (None, f"json parse failed: {e}")
    try:
        _, normalised = validate_result_schema(payload, raw)
        return (normalised, None)
    except ValueError as e:
        return (payload, str(e))


def ingest_run(
    db: LeaderboardDB,
    spec: Dict[str, Any],
    container_state: Dict[str, Any],
    result_path: str | os.PathLike,
    stderr_tail: Optional[str] = None,
) -> str:
    """Read result.json (if present), classify, insert exactly one leaderboard row.

    TOURN-04 contract: every experiment produces a row, success or failed.

    Returns:
        the failure_reason persisted, or empty string on success.
    """
    payload, verr = read_and_validate_result(result_path)
    status, reason = classify(container_state, payload, verr)

    if status == "success" and payload is not None:
        # payload is already result_schema-normalised
        record = dict(payload)
        record["failure_reason"] = None
        record["failure_stderr_tail"] = None
    else:
        # Build a failed row from the spec — payload may or may not be present
        record = {
            "run_id": spec["run_id"],
            "tournament_id": spec["tournament_id"],
            "architecture": spec["architecture"],
            "symbol": spec["symbol"],
            "horizon": int(spec["horizon"]),
            "target_mode": spec["target_mode"],
            "hp_hash": spec["hp_hash"],
            "metrics": (payload or {}).get("metrics")
            or {
                "r2_returns": None,
                "dir_acc_corrected": None,
                "oos_sharpe": None,
                "psr": None,
                "dsr": None,
                "cpcv_dsr": None,
                "train_seconds": None,
            },
            "git_sha": spec.get("git_sha") or os.environ.get("GIT_SHA", "unknown"),
            "tournament_start_ts": spec.get("tournament_start_ts")
            or os.environ.get("TS_START", ""),
            "train_window_includes_contaminated": (payload or {}).get(
                "train_window_includes_contaminated", False
            ),
            "status": "failed",
            "failure_reason": reason,
            "failure_stderr_tail": _scrub(stderr_tail),
        }

    db.insert_run(record)
    return reason


__all__ = ["read_and_validate_result", "ingest_run"]
