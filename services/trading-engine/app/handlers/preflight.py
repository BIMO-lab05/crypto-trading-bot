"""
Preflight LIVE-readiness HTTP route (PREFLIGHT-01 / Phase 8 plan 02).

Exposes ``GET /api/preflight/live-readiness`` on the trading-engine (port
8005). Returns the schema_version=1 :class:`PreflightReport` shape from the
shared :mod:`app.preflight` module — same source of truth as
``scripts/preflight_live.py``. Used by the api-gateway proxy at
``services/api-gateway/app/main.py`` and by the dashboard (Phase 10).

Unauthenticated read-only by design (08-CONTEXT.md D-09 carryforward from
``/api/config/safety-state``). Do NOT add an auth dependency — the route
shape is the contract for the dashboard tile, and the test
``test_route_no_auth_required`` exists to detect a regression.

NOTE: this router is **not mounted** in this plan. Phase 8 plan 03 owns
``services/trading-engine/app/main.py`` and includes:

    from app.handlers.preflight import router as preflight_router
    app.include_router(preflight_router)

co-located with the boot-path cap-check block. Splitting the mount keeps the
grep-gate scope single-file. The route test
(``tests/test_preflight_route.py``) builds a standalone FastAPI test app so
the route is exercised pre-mount.
"""

import logging

from fastapi import APIRouter, HTTPException

from app.preflight import run_all

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/preflight", tags=["preflight"])


@router.get("/live-readiness")
async def get_live_readiness() -> dict:
    """Return the schema_version=1 :class:`PreflightReport` as a JSON dict.

    On any internal exception in ``run_all()``, returns ``500`` so the
    api-gateway proxy can detect the failure and translate it into the
    graceful-degradation ``overall=UNKNOWN`` body (08-CONTEXT.md Open
    Question close — UNKNOWN is the safe default, never PASS-on-fallback).
    """
    try:
        report = run_all()
        return report.to_dict()
    except Exception as e:
        logger.error(
            f"Preflight live-readiness check failed: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Preflight check internal error: {e}",
        )
