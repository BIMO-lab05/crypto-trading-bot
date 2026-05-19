"""
Phase 9 T-09-03-05 — admin-guard tests for POST /api/v1/alerts/daily-summary.

Verifies the spoofing mitigation: the route MUST reject requests without a
valid X-Admin-Key header, MUST reject requests with the wrong key, and MUST
accept requests with the correct key.

Mirrors the test shape from
services/risk-metrics-service/tests/test_auth.py.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


VALID_KEY = "test-admin-key-phase-9"
INVALID_KEY = "wrong-key"

PAYLOAD = {
    "total_pnl": 100.0,
    "total_trades": 5,
    "win_rate": 0.6,
    "best_trade": 50.0,
    "worst_trade": -10.0,
    "balance": 1100.0,
    "open_positions": 0,
    "ml_gate_reason_counts": {"no_evidence": 99},
}


@pytest.fixture
def auth_client(monkeypatch):
    """Test client with a known ADMIN_API_KEY configured."""
    # Configure before importing app so config picks up the value.
    monkeypatch.setenv("ADMIN_API_KEY", VALID_KEY)
    # Re-import config + app to pick up the new env. The notification-service
    # config is a module-level singleton; mutate it in place.
    from app.config import config

    monkeypatch.setattr(config, "admin_api_key", VALID_KEY)

    from app.main import app

    return TestClient(app)


@pytest.fixture
def unconfigured_client(monkeypatch):
    """Test client with NO admin key configured — must refuse all callers."""
    from app.config import config

    monkeypatch.setattr(config, "admin_api_key", "")

    from app.main import app

    return TestClient(app)


def test_daily_summary_missing_header_returns_401(auth_client):
    """Without X-Admin-Key, the route returns 401."""
    response = auth_client.post(
        "/api/v1/alerts/daily-summary",
        params={k: v for k, v in PAYLOAD.items() if k != "ml_gate_reason_counts"},
        json={"ml_gate_reason_counts": PAYLOAD["ml_gate_reason_counts"]},
    )
    assert response.status_code == 401, response.text
    assert "required" in response.json()["detail"].lower()


def test_daily_summary_invalid_key_returns_403(auth_client):
    """With wrong X-Admin-Key, the route returns 403."""
    response = auth_client.post(
        "/api/v1/alerts/daily-summary",
        params={k: v for k, v in PAYLOAD.items() if k != "ml_gate_reason_counts"},
        json={"ml_gate_reason_counts": PAYLOAD["ml_gate_reason_counts"]},
        headers={"X-Admin-Key": INVALID_KEY},
    )
    assert response.status_code == 403, response.text
    assert "invalid" in response.json()["detail"].lower()


def test_daily_summary_valid_key_passes_auth(auth_client):
    """With the correct X-Admin-Key, the route passes auth and invokes alert_manager."""
    fake_response = {
        "success": True,
        "alert_id": "test-id",
        "message": "Daily summary dispatched",
        "channels_sent": ["telegram"],
        "channels_failed": [],
        "suppressed": False,
        "suppression_reason": None,
        "timestamp": "2026-05-18T00:00:00",
    }
    with patch(
        "app.routers.alerts.alert_manager.send_daily_summary",
        new=AsyncMock(return_value=fake_response),
    ) as mock_send:
        response = auth_client.post(
            "/api/v1/alerts/daily-summary",
            params={k: v for k, v in PAYLOAD.items() if k != "ml_gate_reason_counts"},
            json={"ml_gate_reason_counts": PAYLOAD["ml_gate_reason_counts"]},
            headers={"X-Admin-Key": VALID_KEY},
        )
        assert response.status_code == 200, response.text
        mock_send.assert_awaited_once()


def test_daily_summary_unconfigured_server_returns_500(unconfigured_client):
    """If ADMIN_API_KEY is empty on the server, route refuses with 500.

    Closes the deploy-without-secret footgun: an empty server-side key
    would otherwise let any header through (or none at all). The auth
    helper raises 500 instead of silently accepting any caller.
    """
    response = unconfigured_client.post(
        "/api/v1/alerts/daily-summary",
        params={k: v for k, v in PAYLOAD.items() if k != "ml_gate_reason_counts"},
        json={"ml_gate_reason_counts": PAYLOAD["ml_gate_reason_counts"]},
        headers={"X-Admin-Key": "any-value"},
    )
    assert response.status_code == 500, response.text
    assert "not configured" in response.json()["detail"].lower()


def test_scheduler_path_does_not_hit_admin_guarded_endpoint():
    """The scheduled digest path must NOT call the HTTP /daily-summary route.

    The fetcher pulls reason counts from trading-engine and then calls
    `alert_manager.send_daily_summary` directly in-process. If a future
    refactor wires it through HTTP, the admin guard will break the
    scheduler. This test pins the in-process call shape.
    """
    import inspect

    from app.scheduler import ml_gate_digest

    source = inspect.getsource(ml_gate_digest)
    # Must call alert_manager directly, not via HTTP to /daily-summary.
    assert "alert_manager.send_daily_summary" in source, source
    assert "/api/v1/alerts/daily-summary" not in source, source
    assert "/daily-summary" not in source, source
