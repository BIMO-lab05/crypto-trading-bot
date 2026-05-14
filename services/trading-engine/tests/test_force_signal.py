"""
Tests for the force-signal admin endpoint (CD-04, Phase 02 INFRA-01).

Endpoint: POST /api/v1/admin/force-signal

Purpose: Test-only entry point for the integration suite — injects a
deterministic synthetic signal that emits the same RabbitMQ event a real
strategy would. Plan 02-04's <60s round-trip test calls this to start
the signal -> strategy_orchestrator -> portfolio-manager DB row chain.

Security boundary: refuses with HTTP 403 when ``settings.trading_mode == "LIVE"``.
This is the HIGH severity threat for this surface (T-02-02-01) — must never
inject in real-money mode.

Auth note: trading-engine has NO auth middleware (auth lives upstream at the
api-gateway). These tests use a plain ``TestClient`` — the gate-under-test
is the TRADING_MODE refusal, not authentication.

We mount only the ``admin_force_signal_router`` onto a fresh FastAPI app to
avoid pulling the trading-engine's full lifespan stack (DB, Kelly sizer,
smart-router, etc.) during a unit test.
"""

from __future__ import annotations

import logging
import re
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.handlers.orchestration import admin_force_signal_router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app() -> FastAPI:
    """Build a minimal FastAPI app exposing only the force-signal router."""
    app = FastAPI()
    app.include_router(admin_force_signal_router)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture
def valid_payload() -> dict:
    """A valid SignalSubmissionRequest body."""
    return {
        "strategy_id": "force_test_strategy",
        "symbol": "SOLUSDT",
        "direction": "long",
        "action": "BUY",
        "strength": 0.5,
        "confidence": 0.5,
        "entry_price": 150.0,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.04,
        "position_size_pct": 0.1,
        "urgency": "MEDIUM",
        "reasoning": "Synthetic signal from integration test",
    }


@pytest.fixture
def mock_orchestrator():
    """Patch get_strategy_orchestrator inside the orchestration handler module."""
    mock = MagicMock()
    mock.submit_signal.return_value = {
        "accepted": True,
        "reason": "test_accept",
    }
    with patch(
        "app.handlers.orchestration.get_strategy_orchestrator",
        return_value=mock,
    ):
        yield mock


@pytest.fixture
def paper_settings():
    """Patch get_settings to return PAPER mode trading_mode."""
    settings = MagicMock()
    settings.trading_mode = "PAPER"
    with patch(
        "app.handlers.orchestration.get_settings",
        return_value=settings,
    ):
        yield settings


@pytest.fixture
def live_settings():
    """Patch get_settings to return LIVE mode trading_mode."""
    settings = MagicMock()
    settings.trading_mode = "LIVE"
    with patch(
        "app.handlers.orchestration.get_settings",
        return_value=settings,
    ):
        yield settings


# ---------------------------------------------------------------------------
# Test 1: 200 in PAPER mode + signal_id matches expected pattern
# ---------------------------------------------------------------------------


def test_force_signal_paper_mode_returns_200(
    client: TestClient,
    valid_payload: dict,
    mock_orchestrator,
    paper_settings,
):
    """POST with valid body in PAPER mode → 200 + signal_id matching regex."""
    resp = client.post("/api/v1/admin/force-signal", json=valid_payload)

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()

    # Response includes signal_id matching ``^sig_\d{8}_\d{6}_[a-f0-9]{8}$``.
    assert "signal_id" in body
    pattern = re.compile(r"^sig_\d{8}_\d{6}_[a-f0-9]{8}$")
    assert pattern.match(body["signal_id"]), (
        f"signal_id {body['signal_id']!r} does not match expected pattern"
    )

    # Success flag mirrors orchestrator's ``accepted`` boolean.
    assert body.get("success") is True or body.get("accepted") is True

    # Orchestrator was actually called (not silently mocked at the route layer).
    mock_orchestrator.submit_signal.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2: 403 in LIVE mode + orchestrator NOT called
# ---------------------------------------------------------------------------


def test_force_signal_live_mode_returns_403(
    client: TestClient,
    valid_payload: dict,
    mock_orchestrator,
    live_settings,
):
    """POST with valid body in LIVE mode → 403 + submit_signal NOT called."""
    resp = client.post("/api/v1/admin/force-signal", json=valid_payload)

    assert resp.status_code == 403, (
        f"Expected 403 in LIVE mode, got {resp.status_code}: {resp.text}"
    )
    detail = resp.json().get("detail", "")
    assert "LIVE" in detail or "live" in detail.lower(), (
        f"403 detail should mention LIVE mode; got: {detail!r}"
    )

    # CRITICAL: orchestrator MUST NOT be reached when LIVE-mode gate refuses.
    mock_orchestrator.submit_signal.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: 422 on invalid body (missing required field)
# ---------------------------------------------------------------------------


def test_force_signal_missing_strategy_id_returns_422(
    client: TestClient,
    mock_orchestrator,
    paper_settings,
):
    """POST with missing ``strategy_id`` → 422 (pydantic validation)."""
    bad_payload = {
        # strategy_id missing — required field
        "symbol": "SOLUSDT",
        "direction": "long",
        "action": "BUY",
        "strength": 0.5,
        "confidence": 0.5,
    }
    resp = client.post("/api/v1/admin/force-signal", json=bad_payload)
    assert resp.status_code == 422, (
        f"Expected 422 for missing strategy_id, got {resp.status_code}: {resp.text}"
    )

    # Orchestrator MUST NOT be reached when pydantic validation refuses.
    mock_orchestrator.submit_signal.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4: emits a single grep-able log line on success path
# ---------------------------------------------------------------------------


def test_force_signal_emits_audit_log_line(
    client: TestClient,
    valid_payload: dict,
    mock_orchestrator,
    paper_settings,
    caplog,
):
    """Success path emits a sanitized ``FORCE_SIGNAL: strategy_id=...`` log line."""
    with caplog.at_level(logging.WARNING, logger="app.handlers.orchestration"):
        resp = client.post("/api/v1/admin/force-signal", json=valid_payload)

    assert resp.status_code == 200

    # The log line is the contract for the CI log audit (02-09 anti-mock guard
    # and 02-07 RUNBOOK triage rely on this scaling-out in `docker compose
    # logs trading-engine | grep FORCE_SIGNAL`).
    assert "FORCE_SIGNAL: strategy_id=" in caplog.text, (
        f"Expected audit log line; got logs: {caplog.text!r}"
    )

    # The strategy_id from the request should be present in the log line.
    assert valid_payload["strategy_id"] in caplog.text

    # Sanitization: free-form ``reasoning`` field must NEVER reach the logger
    # (log injection vector — T-02-02-03).
    assert valid_payload["reasoning"] not in caplog.text, (
        f"reasoning field leaked into log line; log injection vector!\n"
        f"caplog.text={caplog.text!r}"
    )
