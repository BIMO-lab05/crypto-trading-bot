"""TE-CAP-02: negative test confirming the trading-engine emergency-stop route is removed.

Phase 17 D-01/D-02: the unauthenticated `POST /api/v1/orchestrator/emergency-stop`
at services/trading-engine/app/handlers/orchestration.py:591-622 was deleted.
The api-gateway admin-guarded route at services/api-gateway/app/main.py:1747-1804
is now the sole entry for kill-switch activation (D-04: gateway is sole writer
to safety/EMERGENCY_STOP).

This test guarantees any direct caller hitting the trading-engine port sees a
visible 404 failure rather than a silent swallow or false-success 200.

TDD anchor (Phase 17 D-specifics §1): this test is written BEFORE deletion.
On the pre-deletion code path the route still exists and returns 200 — this
test must FAIL initially (RED). Deletion in Task 2 then makes it PASS (GREEN).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.handlers.orchestration import router as orchestration_router


@pytest.fixture
def app() -> FastAPI:
    """Mount only the orchestration router on a fresh FastAPI app.

    Mirrors the no-auth-middleware test bootstrap used in
    services/trading-engine/tests/test_force_signal.py:42-52 — trading-engine
    has zero auth dependencies to override (per
    services/trading-engine/app/handlers/orchestration.py:725-727 auth note),
    so a plain TestClient suffices.
    """
    app = FastAPI()
    app.include_router(orchestration_router)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_emergency_stop_route_deleted_returns_404(client: TestClient) -> None:
    """POST to the deleted trading-engine emergency-stop route returns 404.

    Phase 17 D-01: the trading-engine duplicate of POST /emergency-stop was
    removed; api-gateway's admin-guarded /api/portfolio/emergency-stop at
    services/api-gateway/app/main.py:1747-1804 is the only remaining entry.
    Direct callers to :8005 must see a visible failure (404), not a silent
    swallow or false-success 200.
    """
    resp = client.post("/api/v1/orchestrator/emergency-stop")
    assert resp.status_code == 404, (
        f"Expected 404 after route deletion, got {resp.status_code}: {resp.text}. "
        f"If status is 200/500, the route at "
        f"services/trading-engine/app/handlers/orchestration.py:591-622 "
        f"has not been deleted yet (Phase 17 Plan 01 Task 2)."
    )


def test_emergency_stop_route_deleted_returns_404_with_reason_query(
    client: TestClient,
) -> None:
    """Same assertion with the `reason` query param the old route accepted.

    Belt-and-braces: confirms the 404 is not query-string-dependent. The
    deleted handler accepted ``reason: str = Query("Manual emergency stop")``
    so we exercise the parameterised invocation shape too.
    """
    resp = client.post(
        "/api/v1/orchestrator/emergency-stop",
        params={"reason": "test-from-phase-17"},
    )
    assert resp.status_code == 404, (
        f"Expected 404 after route deletion (with reason= query param), got "
        f"{resp.status_code}: {resp.text}"
    )
