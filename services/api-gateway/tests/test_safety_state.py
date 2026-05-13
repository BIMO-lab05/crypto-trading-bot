"""
Tests for the api-gateway GET /api/config/safety-state route.

Plan 06-02 Task 4 (DASH-03). Covers:
- D-08 schema shape: trading_mode, paper_trading_mode, auto_trading_enabled,
  emergency_stop{active,mtime}, ml_predictions_enabled, kill_switch{daily_loss_armed,
  daily_pnl_pct, tripped}, last_updated_at
- F-01 (kill_switch derivation truth):
  * daily_loss_armed = bool(te_budget)  (te_budget reachable -> True; empty/down -> False)
  * tripped = bool(te_budget['emergency_mode']) — flat bool; NOT a dict-walk
- F-03 (proxy_request returns JSONResponse, not dict):
  * handler must decode via json.loads(resp.body.decode())
  * .get() on the JSONResponse object would raise AttributeError
- D-09 ownership: read-only, unauthenticated
- Graceful degradation: trading-engine down -> still 200, defaults filled

Tests MUST run inside the api-gateway container (CLAUDE.md gotcha — host
fastapi 0.136 returns 401, container fastapi 0.109 returns 403, but this
route is unauthenticated so the discrepancy does not bite us; we still
follow the container-run rule for consistency).
"""

import json
import os
from unittest.mock import patch

import pytest
from fastapi.responses import JSONResponse



def _build_response(content, status_code=200):
    """Mimic ServiceProxy.proxy_request() — returns a JSONResponse with
    a populated .body attribute (the test must exercise the body.decode
    path; F-03)."""
    r = JSONResponse(content=content, status_code=status_code)
    # JSONResponse already sets .body via render(); be explicit so the
    # mock matches what production code sees.
    r.body = json.dumps(content).encode()
    return r


@pytest.fixture
def mock_proxy(mock_service_proxy):
    """Override get_proxy to return a controllable mock for /safety-state
    tests. Each test customizes proxy_request side_effect / return_value."""
    with patch("app.main.get_proxy", return_value=mock_service_proxy):
        yield mock_service_proxy


def _default_status_payload(emergency_active=False, mtime=None):
    return {
        "status": "running",
        "trading_mode": "PAPER",
        "auto_trading_enabled": True,
        "active_strategy": "default",
        "open_positions_count": 0,
        "current_balance": 100000.0,
        "timestamp": 1700000000000,
        "system_metrics": {},
        "emergency_stop": {
            "file_path": "/app/EMERGENCY_STOP",
            "active": emergency_active,
            "mtime": mtime,
            "last_checked": "2026-05-13T10:00:00+00:00",
            "auto_trader_running": True,
        },
    }


def _default_budget_payload(emergency_mode=False, daily_pnl_pct=-1.5):
    return {
        "success": True,
        "budget": {"adjusted_budget_pct": 1.6, "adjusted_budget_usd": 1600.0},
        "utilization": {
            "total_budget_usd": 1600.0,
            "used_budget_usd": 0.0,
            "available_budget_usd": 1600.0,
            "utilization_pct": 0.0,
            "daily_pnl_pct": daily_pnl_pct,
        },
        "emergency_mode": emergency_mode,
        "config": {},
        "timestamp": "2026-05-13T10:00:00+00:00",
    }


def _route_proxy(status_payload, budget_payload):
    """Return a side_effect that dispatches by path."""

    async def _se(service_name, path, method="GET", **kwargs):
        assert service_name == "trading-engine", (
            f"safety-state must only fan out to trading-engine; got {service_name!r}"
        )
        if path == "/status":
            return _build_response(status_payload)
        if path == "/api/v1/risk/budget/current":
            return _build_response(budget_payload)
        raise AssertionError(f"unexpected proxy path: {path}")

    return _se


def test_safety_state_returns_full_d08_schema(test_client, mock_proxy):
    """Happy path: response contains every key from the D-08 schema."""
    mock_proxy.proxy_request.side_effect = _route_proxy(
        _default_status_payload(mtime="2026-05-13T10:00:00+00:00"),
        _default_budget_payload(),
    )
    resp = test_client.get("/api/config/safety-state")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    for key in (
        "trading_mode",
        "paper_trading_mode",
        "auto_trading_enabled",
        "emergency_stop",
        "ml_predictions_enabled",
        "kill_switch",
        "last_updated_at",
    ):
        assert key in body, f"D-08 schema requires top-level key '{key}'"
    for key in ("active", "mtime"):
        assert key in body["emergency_stop"], (
            f"emergency_stop missing required key '{key}'"
        )
    for key in ("daily_loss_armed", "daily_pnl_pct", "tripped"):
        assert key in body["kill_switch"], f"kill_switch missing required key '{key}'"


def test_trading_mode_uppercased_from_env(test_client, mock_proxy):
    """TRADING_MODE=PAPER env -> response.trading_mode == 'PAPER'."""
    mock_proxy.proxy_request.side_effect = _route_proxy(
        _default_status_payload(), _default_budget_payload()
    )
    with patch.dict(os.environ, {"TRADING_MODE": "paper"}):
        resp = test_client.get("/api/config/safety-state")
    assert resp.status_code == 200
    assert resp.json()["trading_mode"] == "PAPER", (
        "trading_mode must be uppercased even if env is lowercase"
    )


def test_trading_engine_status_unreachable_returns_200_with_defaults(
    test_client, mock_proxy
):
    """When /status proxy raises, response stays 200 and emergency_stop
    falls back to {active: False, mtime: None}. auto_trading_enabled falls
    back to False (safety default)."""

    async def _se(service_name, path, method="GET", **kwargs):
        if path == "/status":
            raise RuntimeError("trading-engine down")
        if path == "/api/v1/risk/budget/current":
            return _build_response(_default_budget_payload())
        raise AssertionError(path)

    mock_proxy.proxy_request.side_effect = _se
    resp = test_client.get("/api/config/safety-state")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["auto_trading_enabled"] is False
    assert body["emergency_stop"] == {"active": False, "mtime": None}


def test_trading_engine_budget_unreachable_zero_defaults(test_client, mock_proxy):
    """When /api/v1/risk/budget/current proxy raises, daily_pnl_pct falls
    back to 0.0 and tripped to False."""

    async def _se(service_name, path, method="GET", **kwargs):
        if path == "/status":
            return _build_response(_default_status_payload())
        if path == "/api/v1/risk/budget/current":
            raise RuntimeError("budget endpoint down")
        raise AssertionError(path)

    mock_proxy.proxy_request.side_effect = _se
    resp = test_client.get("/api/config/safety-state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kill_switch"]["daily_pnl_pct"] == 0.0
    assert body["kill_switch"]["tripped"] is False


def test_last_updated_at_is_iso_utc(test_client, mock_proxy):
    """last_updated_at must be an ISO 8601 string parseable by fromisoformat."""
    from datetime import datetime

    mock_proxy.proxy_request.side_effect = _route_proxy(
        _default_status_payload(), _default_budget_payload()
    )
    resp = test_client.get("/api/config/safety-state")
    assert resp.status_code == 200
    ts = resp.json()["last_updated_at"]
    parsed = datetime.fromisoformat(ts)
    assert parsed.tzinfo is not None, "timestamp must be timezone-aware (UTC)"


def test_route_does_not_require_auth(test_client, mock_proxy):
    """D-09: endpoint is unauthenticated. test_client (no admin) must get 200."""
    mock_proxy.proxy_request.side_effect = _route_proxy(
        _default_status_payload(), _default_budget_payload()
    )
    resp = test_client.get("/api/config/safety-state")
    assert resp.status_code == 200, (
        f"endpoint must not require auth; got {resp.status_code}: {resp.text}"
    )


def test_url_has_no_v1_prefix(test_client, mock_proxy):
    """CLAUDE.md: gateway routes are /api/<domain>/<resource>, no /v1/."""
    mock_proxy.proxy_request.side_effect = _route_proxy(
        _default_status_payload(), _default_budget_payload()
    )
    resp_correct = test_client.get("/api/config/safety-state")
    resp_wrong = test_client.get("/api/v1/config/safety-state")
    assert resp_correct.status_code == 200
    assert resp_wrong.status_code == 404, (
        "/api/v1/config/safety-state must NOT exist; only /api/config/safety-state"
    )


def test_daily_loss_armed_defaults_false_when_budget_empty(test_client, mock_proxy):
    """F-01 load-bearing: when te_budget proxy raises OR returns {}, the
    response's kill_switch.daily_loss_armed is False (NOT True). This is
    the regression guard for the WRONG hardcoded True literal."""

    async def _se(service_name, path, method="GET", **kwargs):
        if path == "/status":
            return _build_response(_default_status_payload())
        if path == "/api/v1/risk/budget/current":
            raise RuntimeError("down")
        raise AssertionError(path)

    mock_proxy.proxy_request.side_effect = _se
    resp = test_client.get("/api/config/safety-state")
    assert resp.status_code == 200
    assert resp.json()["kill_switch"]["daily_loss_armed"] is False, (
        "when te_budget is unreachable, daily_loss_armed must be False (NOT hardcoded True)"
    )

    # Empty-dict branch (proxy returns {} body).
    async def _se_empty(service_name, path, method="GET", **kwargs):
        if path == "/status":
            return _build_response(_default_status_payload())
        if path == "/api/v1/risk/budget/current":
            return _build_response({})
        raise AssertionError(path)

    mock_proxy.proxy_request.side_effect = _se_empty
    resp = test_client.get("/api/config/safety-state")
    assert resp.status_code == 200
    assert resp.json()["kill_switch"]["daily_loss_armed"] is False, (
        "when te_budget body is {}, daily_loss_armed must still be False"
    )


def test_daily_loss_armed_true_when_budget_reachable(test_client, mock_proxy):
    """F-01: when budget returns a non-empty dict with emergency_mode=False,
    daily_loss_armed=True AND tripped=False."""
    mock_proxy.proxy_request.side_effect = _route_proxy(
        _default_status_payload(),
        _default_budget_payload(emergency_mode=False, daily_pnl_pct=-3.2),
    )
    resp = test_client.get("/api/config/safety-state")
    assert resp.status_code == 200
    ks = resp.json()["kill_switch"]
    assert ks["daily_loss_armed"] is True, (
        "te_budget is reachable -> daily_loss_armed must be True"
    )
    assert ks["tripped"] is False, "emergency_mode flat bool is False -> tripped False"
    assert ks["daily_pnl_pct"] == pytest.approx(-3.2)


def test_tripped_true_when_emergency_mode_flag_set(test_client, mock_proxy):
    """F-01: emergency_mode is a FLAT BOOL on the wire. tripped = bool(te_budget['emergency_mode']).
    The WRONG PATTERNS.md dict-walk on emergency_mode.armed would return False here."""
    mock_proxy.proxy_request.side_effect = _route_proxy(
        _default_status_payload(),
        _default_budget_payload(emergency_mode=True, daily_pnl_pct=-5.1),
    )
    resp = test_client.get("/api/config/safety-state")
    assert resp.status_code == 200
    ks = resp.json()["kill_switch"]
    assert ks["tripped"] is True, (
        "emergency_mode flat bool True must produce tripped=True (F-01 fix)"
    )
    assert ks["daily_pnl_pct"] == pytest.approx(-5.1)


def test_proxy_returns_jsonresponse_decoded_via_body_decode(test_client, mock_proxy):
    """F-03 load-bearing: ServiceProxy.proxy_request returns a JSONResponse,
    NOT a dict. The handler must decode via json.loads(resp.body.decode()).
    Calling .get() on the JSONResponse itself would raise AttributeError.

    This test feeds a real JSONResponse mock and asserts the handler
    end-to-end returns non-default values — proving the decode path
    executed."""
    status = _default_status_payload(
        emergency_active=True, mtime="2026-05-13T11:00:00+00:00"
    )
    budget = _default_budget_payload(emergency_mode=True, daily_pnl_pct=-7.4)
    # Both responses are real JSONResponse instances.
    real_status = JSONResponse(content=status, status_code=200)
    real_status.body = json.dumps(status).encode()
    real_budget = JSONResponse(content=budget, status_code=200)
    real_budget.body = json.dumps(budget).encode()

    async def _se(service_name, path, method="GET", **kwargs):
        if path == "/status":
            return real_status
        if path == "/api/v1/risk/budget/current":
            return real_budget
        raise AssertionError(path)

    mock_proxy.proxy_request.side_effect = _se
    resp = test_client.get("/api/config/safety-state")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # If the handler had called .get() on the JSONResponse directly, it
    # would have raised AttributeError and the test client would get 500.
    # Non-default values prove the body.decode pipeline worked.
    assert body["emergency_stop"]["active"] is True
    assert body["emergency_stop"]["mtime"] == "2026-05-13T11:00:00+00:00"
    assert body["kill_switch"]["tripped"] is True
    assert body["kill_switch"]["daily_pnl_pct"] == pytest.approx(-7.4)
