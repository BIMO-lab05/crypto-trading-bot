"""Unauthenticated read-only endpoint exposing snapshot_reasons() as JSON.

Closes ROADMAP Phase 9 SC#4 cross-service delivery clause (Plan 09-03 D-09-03-07):
the notification-service daily-digest scheduler fetches this dict via httpx
and forwards it to send_daily_summary().

Sibling to handlers/preflight.py — same shape (no auth, read-only, public-grade
observability data per Phase 8 D-09 unauthenticated read-only decision).

NOTE: this router is **not mounted** in this module. `app/main.py` owns the
include_router call (extends the Phase 8 preflight_router mount). Splitting the
mount keeps router-registration logic centralized for future grep gates.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.aggregation.ml_gate_reasons import snapshot_reasons

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/preflight", tags=["preflight"])


@router.get("/ml-gate-reason-counts")
async def get_ml_gate_reason_counts() -> dict[str, int]:
    """Return the current ML-gate reason counter as a JSON dict.

    Returns the live snapshot of `app.aggregation.ml_gate_reasons._counter` —
    a 24h running tally of disabled-event reasons keyed by the 5-member enum.

    Unauthenticated read-only by design (08-CONTEXT.md D-09 carryforward).
    Reason counts are public-grade observability data: they reveal that ML
    predictions are gated, but do NOT reveal credentials, DSR thresholds,
    position sizes, or any secret material. Same disclosure level as the
    existing /api/preflight/live-readiness endpoint (Phase 8).

    On any internal exception in snapshot_reasons(), returns 500 with a
    public-safe detail string (only type(e).__name__ is logged for the
    operator; the response body does NOT echo the exception text — same
    discipline as the Phase 8 sqlite-error path).
    """
    try:
        return snapshot_reasons()
    except Exception as e:
        logger.error(
            f"ml-gate-reason-counts handler failed: {type(e).__name__}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="ml-gate-reason-counts read failed",
        )
