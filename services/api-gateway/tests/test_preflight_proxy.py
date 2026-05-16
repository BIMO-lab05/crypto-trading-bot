"""Tests for api-gateway ``GET /api/preflight/live-readiness`` proxy route.

Unauthenticated per 08-CONTEXT.md (D-09 carryforward from
``/api/config/safety-state``). Uses ``test_client`` from
``services/api-gateway/tests/conftest.py`` — NOT ``admin_client``. Using
``admin_client`` here would silently mask a future regression that added
``Depends(get_current_admin_user)`` to the proxy route.

Tests:

* ``test_proxy_passes_through_preflight_report`` — happy path: trading-engine
  body surfaces verbatim through the gateway.
* ``test_proxy_returns_unknown_when_trading_engine_unreachable`` —
  load-bearing: when the proxy raises, the gateway returns 200 with all 6
  checks UNKNOWN and ``overall=UNKNOWN``. This is the "Open Question" close
  from CONTEXT.md: never PASS-on-fallback.
* ``test_proxy_no_auth_required`` — D-09 auth-leak regression guard.
* ``test_proxy_returns_unknown_when_trading_engine_returns_non_200`` —
  non-200 from trading-engine is also degraded to UNKNOWN.

api-gateway test env note (CLAUDE.md gotcha): host pip has fastapi 0.136
where HTTPBearer returns 401, the deployed container pins fastapi 0.109 (403).
This route is unauthenticated so the discrepancy doesn't bite us, but the
convention is to run inside the container:

    docker exec crypto-bot-api-gateway pytest tests/test_preflight_proxy.py
"""

import json

import pytest
from fastapi.responses import JSONResponse
from unittest.mock import patch


def _build_response(content, status_code: int = 200) -> JSONResponse:
    """Mimic ``ServiceProxy.proxy_request()`` return shape.

    The real ``proxy_request`` returns ``fastapi.responses.JSONResponse``
    with a populated ``.body`` attribute. The handler decodes via
    ``json.loads(resp.body.decode())`` (F-03 fix at safety-state:1080-1084).
    Tests must populate ``.body`` explicitly so the decode path runs.
    Mirrors ``tests/test_safety_state.py::_build_response`` (lines 32-40).
    """
    r = JSONResponse(content=content, status_code=status_code)
    r.body = json.dumps(content).encode()
    return r


@pytest.fixture
def mock_proxy(mock_service_proxy):
    """Override ``get_proxy()`` to return the controllable mock."""
    with patch("app.main.get_proxy", return_value=mock_service_proxy):
        yield mock_service_proxy


def _trading_engine_route(payload, status_code: int = 200):
    """Side-effect that asserts dispatch went to the right service+path."""

    async def _se(service_name, path, method="GET", **kwargs):
        assert service_name == "trading-engine", (
            f"preflight proxy must only fan out to trading-engine; got {service_name!r}"
        )
        assert path == "/api/preflight/live-readiness", (
            f"unexpected proxy path: {path!r}"
        )
        return _build_response(payload, status_code=status_code)

    return _se


_GOOD_PAYLOAD = {
    "schema_version": 1,
    "overall": "PASS",
    "evaluated_at": "2026-05-16T14:32:01+00:00",
    "checks": [
        {"check": "cap", "status": "PASS", "detail": "max_risk_per_trade=0.02"},
        {"check": "paper_mode", "status": "PASS", "detail": "PAPER_TRADING_MODE=false"},
        {"check": "trading_mode", "status": "PASS", "detail": "TRADING_MODE=LIVE"},
        {"check": "ack", "status": "PASS", "detail": "LIVE_TRADING_ACK present"},
        {
            "check": "emergency_stop",
            "status": "PASS",
            "detail": "no file at /app/EMERGENCY_STOP",
        },
        {
            "check": "dsr_evidence",
            "status": "PASS",
            "detail": "latest leaderboard dsr=0.97 > 0.95",
        },
    ],
}


def test_proxy_passes_through_preflight_report(test_client, mock_proxy):
    """Happy path — trading-engine report surfaces verbatim through gateway."""
    mock_proxy.proxy_request.side_effect = _trading_engine_route(_GOOD_PAYLOAD)
    resp = test_client.get("/api/preflight/live-readiness")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["schema_version"] == 1
    assert body["overall"] == "PASS"
    assert len(body["checks"]) == 6
    # Check name set is preserved end-to-end.
    names = {c["check"] for c in body["checks"]}
    assert names == {
        "cap",
        "paper_mode",
        "trading_mode",
        "ack",
        "emergency_stop",
        "dsr_evidence",
    }
    # And all status PASS — proves verbatim pass-through.
    assert all(c["status"] == "PASS" for c in body["checks"])


def test_proxy_returns_unknown_when_trading_engine_unreachable(test_client, mock_proxy):
    """Load-bearing: trading-engine raises -> overall=UNKNOWN, all 6 UNKNOWN.

    This is the "Open Question" close from 08-CONTEXT.md: never
    PASS-on-fallback. UNKNOWN is the only safe default.
    """

    async def _raise(*_args, **_kwargs):
        raise Exception("connection refused")

    mock_proxy.proxy_request.side_effect = _raise

    resp = test_client.get("/api/preflight/live-readiness")
    # NOT 500 — the gateway swallows the failure and returns a degraded body.
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["schema_version"] == 1
    assert body["overall"] == "UNKNOWN", (
        f"trading-engine unreachable MUST degrade to UNKNOWN, "
        f"never PASS or FAIL; got {body['overall']!r}"
    )
    assert len(body["checks"]) == 6
    assert all(c["status"] == "UNKNOWN" for c in body["checks"]), body["checks"]
    # Detail string says why so the dashboard can render the cause.
    for c in body["checks"]:
        assert "trading-engine unreachable" in c["detail"], c
    # Check name set is still the canonical 6.
    names = {c["check"] for c in body["checks"]}
    assert names == {
        "cap",
        "paper_mode",
        "trading_mode",
        "ack",
        "emergency_stop",
        "dsr_evidence",
    }


def test_proxy_no_auth_required(test_client, mock_proxy):
    """D-09 regression guard — endpoint stays unauthenticated.

    If a future refactor adds ``Depends(get_current_admin_user)`` to the
    proxy route, ``test_client`` (which has no auth override) would start
    getting 401/403 here and this test would fail loudly.
    """
    mock_proxy.proxy_request.side_effect = _trading_engine_route(_GOOD_PAYLOAD)
    resp = test_client.get("/api/preflight/live-readiness")
    assert resp.status_code == 200, (
        f"D-09: endpoint must not require auth; got {resp.status_code}: {resp.text}"
    )


def test_proxy_returns_unknown_when_trading_engine_returns_non_200(
    test_client, mock_proxy
):
    """Non-200 from trading-engine (e.g. 500) also degrades to UNKNOWN.

    The route handler must NOT decode the upstream body as a successful
    report when the upstream signalled failure — same safe default as the
    raise-path test above.
    """
    bad_payload = {"error": "boom"}
    mock_proxy.proxy_request.side_effect = _trading_engine_route(
        bad_payload, status_code=500
    )

    resp = test_client.get("/api/preflight/live-readiness")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["overall"] == "UNKNOWN"
    assert all(c["status"] == "UNKNOWN" for c in body["checks"])
