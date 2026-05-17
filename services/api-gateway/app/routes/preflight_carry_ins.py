"""
GET /api/preflight/carry-ins — carry-ins state + 24h continuous-PASS window.

Unauthenticated read-only by design — matches the /api/preflight/live-readiness
(Phase 8) and /api/preflight/ml-gate-reason-counts (Phase 9) precedent. The
payload contains only operator-workflow state (carry-in descriptions, window
timestamps, joined preflight checks) — no secrets, no PII.

UNKNOWN-from-upstream is mapped to DO_NOT_FLIP for the dashboard banner per
D-10-11: trading-engine unreachable is the safe-default failure mode. The
per-check live_readiness block in the response still surfaces UNKNOWN per check
so the operator can see the cause.

Phase 10 DASHLIVE-02 / DASHLIVE-03.
"""

import json
import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/preflight", tags=["preflight"])

_DEGRADED_CHECKS = [
    {"check": name, "status": "UNKNOWN", "detail": "trading-engine unreachable"}
    for name in (
        "cap",
        "paper_mode",
        "trading_mode",
        "ack",
        "emergency_stop",
        "dsr_evidence",
    )
]

_DEFAULT_STATE = {
    "carry_ins": [],
    "_state": {
        "first_all_pass_at": None,
        "last_evaluated_at": None,
        "last_overall": "UNKNOWN",
    },
}


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write payload as JSON to path atomically.

    Writes to a temp file in the same directory (same filesystem -> atomic
    rename) then os.replace()s into place. os.replace() is atomic on POSIX
    and on Windows from Python 3.3+. No torn writes; concurrent readers
    see either the old file or the new file, never a half-written one.

    dir=path.parent is REQUIRED — temp file MUST be on the same
    filesystem as the target for os.replace to be atomic.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # delete=False so the file persists after close() for the rename.
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=2)
            f.flush()
            os.fsync(f.fileno())  # belt-and-braces durability
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


@router.get("/carry-ins")
async def get_carry_ins():
    """
    Return carry-ins state, 24h continuous-PASS window, and joined live_readiness.

    Server computes overall per D-10-04:
    - DO_NOT_FLIP: any preflight check != PASS (UNKNOWN counts as not-PASS per D-10-08)
    - ALMOST: all 6 PASS but elapsed < required_seconds
    - READY: all 6 PASS and elapsed >= required_seconds

    State file is written atomically (tempfile + os.replace) on each request.
    On any failure (proxy, file I/O), returns 200 with overall=DO_NOT_FLIP —
    never raises. UNKNOWN is the safe default.

    Unauthenticated read-only (Phase 8/9 precedent, D-10-05).
    """
    # Local imports — autoflake removes unused top-level imports across
    # api-gateway/main.py refactors. Importing inside the function pins
    # the use site and survives the autoflake pass
    # (project memory: feedback_main_imports_autoflake.md).
    from datetime import datetime, timezone as _tz

    path_str = os.environ.get(
        "PREFLIGHT_CARRY_INS_PATH", "/app/planning_state/carry_ins.json"
    )
    required_seconds = int(
        os.environ.get("PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS", "86400")
    )

    now = datetime.now(_tz.utc)
    now_iso = now.isoformat()

    # --- Fan out to trading-engine for live-readiness report ---
    # Using the existing api-gateway proxy idiom from main.py:1196-1205.
    # get_proxy() is imported lazily here to avoid circular-import risk
    # (preflight_carry_ins.py is imported by main.py after app construction).
    live_readiness = None
    try:
        from app.main import get_proxy  # noqa: E402

        proxy = get_proxy()
        resp = await proxy.proxy_request(
            service_name="trading-engine",
            path="/api/preflight/live-readiness",
            method="GET",
        )
        if getattr(resp, "status_code", 500) == 200:
            live_readiness = json.loads(resp.body.decode())
        else:
            raise Exception(
                f"trading-engine returned status_code={getattr(resp, 'status_code', 'unknown')}"
            )
    except Exception as e:
        logger.warning(f"/api/preflight/carry-ins: trading-engine proxy failed: {e}")
        live_readiness = {
            "schema_version": 1,
            "overall": "UNKNOWN",
            "evaluated_at": now_iso,
            "checks": _DEGRADED_CHECKS,
        }

    # --- Read state file ---
    state = None
    carry_ins_path = Path(path_str)
    try:
        raw = carry_ins_path.read_text(encoding="utf-8")
        file_data = json.loads(raw)
        state = {
            "carry_ins": file_data.get("carry_ins", []),
            "_state": file_data.get(
                "_state",
                {
                    "first_all_pass_at": None,
                    "last_evaluated_at": None,
                    "last_overall": "UNKNOWN",
                },
            ),
        }
    except Exception as e:
        logger.warning(
            f"/api/preflight/carry-ins: state file read failed ({path_str}): {e}"
        )
        state = {
            "carry_ins": [],
            "_state": {
                "first_all_pass_at": None,
                "last_evaluated_at": None,
                "last_overall": "UNKNOWN",
            },
        }

    # --- Compute all_pass per D-10-07 + D-10-08 ---
    checks = live_readiness.get("checks", [])
    all_pass = len(checks) >= 6 and all(c.get("status") == "PASS" for c in checks)

    # --- Apply D-10-07 reset rule ---
    _st = state["_state"]
    if all_pass and _st.get("first_all_pass_at") is None:
        _st["first_all_pass_at"] = now_iso
    elif not all_pass:
        _st["first_all_pass_at"] = None
    _st["last_evaluated_at"] = now_iso

    # --- Compute elapsed / remaining ---
    first_all_pass_at = _st.get("first_all_pass_at")
    elapsed_seconds = 0
    if first_all_pass_at is not None:
        try:
            # Handle both "+00:00" and "Z" suffix forms from datetime.isoformat()
            ts_str = first_all_pass_at.replace("Z", "+00:00")
            parsed_dt = datetime.fromisoformat(ts_str)
            elapsed_seconds = max(0, int((now - parsed_dt).total_seconds()))
        except Exception as e:
            logger.warning(
                f"/api/preflight/carry-ins: could not parse first_all_pass_at: {e}"
            )
            elapsed_seconds = 0

    remaining_seconds = max(0, required_seconds - elapsed_seconds)

    # --- Compute overall per D-10-04 / D-10-11 ---
    if not all_pass:
        overall = "DO_NOT_FLIP"
    elif elapsed_seconds < required_seconds:
        overall = "ALMOST"
    else:
        overall = "READY"

    _st["last_overall"] = overall

    # --- Atomic write state back (best-effort; degrade gracefully on failure) ---
    try:
        # Reconstruct the full file payload preserving carry_ins[] from file_data
        # (Phase 11 LIVECLOSE owns carry_ins[] writes; we only own _state).
        write_payload = {
            "schema_version": 1,
            "carry_ins": state["carry_ins"],
            "_state": _st,
        }
        _atomic_write_json(carry_ins_path, write_payload)
    except Exception as e:
        logger.warning(
            f"/api/preflight/carry-ins: state file write failed ({path_str}): {e}"
        )
        # Continue serving — next poll will retry the write.

    # --- Compute preflight_summary counts ---
    pass_count = sum(1 for c in checks if c.get("status") == "PASS")
    fail_count = sum(1 for c in checks if c.get("status") == "FAIL")
    unknown_count = sum(1 for c in checks if c.get("status") == "UNKNOWN")

    return {
        "schema_version": 1,
        "evaluated_at": now_iso,
        "overall": overall,
        "carry_ins": state["carry_ins"],
        "window": {
            "first_all_pass_at": first_all_pass_at,
            "elapsed_seconds": elapsed_seconds,
            "required_seconds": required_seconds,
            "remaining_seconds": remaining_seconds,
        },
        "preflight_summary": {
            "pass": pass_count,
            "fail": fail_count,
            "unknown": unknown_count,
        },
        "live_readiness": live_readiness,
    }
