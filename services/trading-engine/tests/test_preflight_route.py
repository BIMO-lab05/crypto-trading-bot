"""Tests for ``GET /api/preflight/live-readiness`` route (trading-engine).

Unauthenticated per 08-CONTEXT.md (matches ``/api/config/safety-state`` D-09
pattern). Use plain ``TestClient`` over a *standalone* ``FastAPI()`` test app
into which we ``include_router(router)`` — Phase 8 plan 03 is the one that
mounts this router on the real ``app`` in ``services/trading-engine/app/main.py``
co-located with the cap-check block. Building a fresh test app lets these
tests pass before 08-03 lands.

Tests:

* ``test_route_returns_schema_v1`` — schema + 6 check names + statuses set.
* ``test_route_no_auth_required`` — D-09 auth-leak guard (no header → 200).
* ``test_route_500_on_internal_error`` — ``run_all()`` exception surfaces 500
  (proxy translates to UNKNOWN; route itself does NOT silently PASS).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.handlers.preflight import router as preflight_router


_EXPECTED_CHECK_NAMES = {
    "cap",
    "paper_mode",
    "trading_mode",
    "ack",
    "emergency_stop",
    "dsr_evidence",
}


@pytest.fixture
def client() -> TestClient:
    """Build a standalone FastAPI app for the preflight router.

    08-03 owns mounting on the real app; this fixture lets the route be
    exercised in isolation. Mirrors the pattern documented in plan 02 §3.
    """
    test_app = FastAPI()
    test_app.include_router(preflight_router)
    return TestClient(test_app)


def test_route_returns_schema_v1(client: TestClient) -> None:
    """GET /api/preflight/live-readiness returns the schema_version=1 shape.

    Dashboard tile (Phase 10) keys off the exact set of 6 check names and
    the {check, status, detail} per-row keys. Status alphabet is
    {PASS, FAIL, UNKNOWN}.
    """
    resp = client.get("/api/preflight/live-readiness")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["schema_version"] == 1
    assert body["overall"] in {"PASS", "FAIL", "UNKNOWN"}
    assert isinstance(body["checks"], list)
    assert len(body["checks"]) == 6

    names = {c["check"] for c in body["checks"]}
    assert names == _EXPECTED_CHECK_NAMES, (
        f"check name set drift: {names ^ _EXPECTED_CHECK_NAMES}"
    )

    for c in body["checks"]:
        assert set(c.keys()) >= {"check", "status", "detail"}, c
        assert c["status"] in {"PASS", "FAIL", "UNKNOWN"}, c


def test_route_no_auth_required(client: TestClient) -> None:
    """GET without any auth header still returns 200 (D-09 unauthenticated).

    Regression guard: if a future refactor accidentally adds
    ``Depends(get_current_admin_user)`` to the route, this test will start
    returning 401 or 403 and fail loudly.
    """
    resp = client.get("/api/preflight/live-readiness")
    assert resp.status_code == 200, (
        f"D-09 says preflight is unauthenticated; got {resp.status_code}: {resp.text}"
    )


def test_route_500_on_internal_error(monkeypatch, client: TestClient) -> None:
    """If ``run_all()`` raises, the route returns 500 (NOT a silent PASS).

    The api-gateway proxy translates non-200 responses into the graceful-
    degradation ``overall=UNKNOWN`` body. The route itself must surface the
    failure rather than fabricate a PASS — that's the load-bearing
    behaviour 08-CONTEXT.md's "Open Question" pins.
    """

    def _explode(*_args, **_kwargs):
        raise RuntimeError("simulated check failure")

    # Patch the symbol where the handler resolves it.
    monkeypatch.setattr("app.handlers.preflight.run_all", _explode)

    resp = client.get("/api/preflight/live-readiness")
    assert resp.status_code == 500, resp.text
    body = resp.json()
    assert "Preflight check internal error" in body.get("detail", "")
