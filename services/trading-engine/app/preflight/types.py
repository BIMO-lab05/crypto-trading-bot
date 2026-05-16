"""
Preflight LIVE Readiness — typed result containers (PREFLIGHT-01).

Stdlib-only dataclasses so the CLI (scripts/preflight_live.py) can run on a
developer laptop without docker or FastAPI installed.

Schema is **versioned**. ``PreflightReport.schema_version`` is pinned at ``1``;
downstream consumers (Phase 10 dashboard tile, Phase 8 CLI/HTTP route,
Phase 8 CI workflow) all rely on the JSON shape below:

    {
      "schema_version": 1,
      "overall": "PASS|FAIL|UNKNOWN",
      "evaluated_at": "2026-05-16T14:32:01+00:00",
      "checks": [
        {"check": "cap",            "status": "PASS", "detail": "..."},
        {"check": "paper_mode",     "status": "PASS", "detail": "..."},
        {"check": "trading_mode",   "status": "PASS", "detail": "..."},
        {"check": "ack",            "status": "PASS", "detail": "..."},
        {"check": "emergency_stop", "status": "PASS", "detail": "..."},
        {"check": "dsr_evidence",   "status": "UNKNOWN", "detail": "..."}
      ]
    }

DO NOT modify the shape without bumping ``schema_version``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Literal

Status = Literal["PASS", "FAIL", "UNKNOWN"]


@dataclass(frozen=True)
class CheckResult:
    """One row of a PreflightReport.

    Attributes:
        check: stable check id (one of: cap, paper_mode, trading_mode, ack,
            emergency_stop, dsr_evidence). Frontend tiles in Phase 10 key off
            this exact string.
        status: PASS / FAIL / UNKNOWN. UNKNOWN is a *real* terminal state for
            checks gated on a downstream phase (e.g. dsr_evidence in Phase 8
            before MLGATE-02 lands).
        detail: human-readable explanation. Surfaced verbatim in dashboard
            and CLI output. MUST NOT contain secrets — configuration values
            only (same disclosure level as /api/config/safety-state).
    """

    check: str
    status: Status
    detail: str


@dataclass(frozen=True)
class PreflightReport:
    """Aggregate result of all six preflight checks.

    Schema is pinned at version 1; bump ``schema_version`` if the shape
    changes (e.g. new top-level key, new required field on CheckResult).
    """

    overall: Status
    checks: list[CheckResult]
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    schema_version: int = 1

    def to_dict(self) -> dict:
        """Return a plain dict suitable for JSONResponse or json.dumps."""
        return asdict(self)

    def to_json(self) -> str:
        """Return a JSON string (indent=2) — used by the CLI for --json output."""
        return json.dumps(asdict(self), indent=2)
