"""
Tests for the indicator rolling-confidence gate endpoint.

Endpoint: POST /api/v1/admin/indicators/{name}/enable

Auth note: trading-engine has NO auth middleware (auth lives upstream at
the api-gateway). The CLAUDE.md ``admin_client`` fixture is api-gateway
only. So these tests use a plain ``TestClient`` — the gate-under-test
is :func:`assert_eligible` raising, not authentication.

We mount only the ``admin_indicator_router`` onto a fresh FastAPI app
to avoid pulling the trading-engine's full lifespan stack (DB, Kelly
sizer, smart-router, etc.) during a unit test.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.handlers.orchestration import admin_indicator_router
from app.services.indicator_registry import (
    MIN_SAMPLES_FOR_AVG,
    get_indicator_registry,
    reset_indicator_registry,
)


@pytest.fixture
def client() -> TestClient:
    """Build a minimal FastAPI app exposing only the admin gate router."""
    app = FastAPI()
    app.include_router(admin_indicator_router)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_registry_singleton():
    reset_indicator_registry()
    yield
    reset_indicator_registry()


# ---------------------------------------------------------------------------
# Gate behaviour
# ---------------------------------------------------------------------------


def test_enable_refused_when_no_samples(client: TestClient):
    """Cold start: zero samples → 409 Conflict, structured detail."""
    resp = client.post("/api/v1/admin/indicators/RSI_DIVERGENCE/enable")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["error"] == "indicator_below_threshold"
    assert detail["indicator"] == "RSI_DIVERGENCE"
    assert detail["current_avg"] is None
    assert 0.0 <= detail["threshold"] <= 1.0


def test_enable_refused_when_avg_below_threshold(client: TestClient):
    """RSI_DIVERGENCE-style stuck indicator (avg 0.20) is refused."""
    registry = get_indicator_registry()
    # Synchronous test client + async record: drive the loop manually.
    import asyncio

    async def _seed() -> None:
        for _ in range(MIN_SAMPLES_FOR_AVG):
            await registry.record("RSI_DIVERGENCE", 0.20, was_voted=True)

    asyncio.run(_seed())

    resp = client.post("/api/v1/admin/indicators/RSI_DIVERGENCE/enable")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["indicator"] == "RSI_DIVERGENCE"
    assert detail["current_avg"] == pytest.approx(0.20, abs=1e-9)


def test_enable_passes_gate_above_threshold(client: TestClient):
    """Above threshold + ≥ MIN_SAMPLES_FOR_AVG → 200, gated=True, persisted=False."""
    registry = get_indicator_registry()
    import asyncio

    async def _seed() -> None:
        for _ in range(MIN_SAMPLES_FOR_AVG):
            await registry.record("ICHIMOKU", 0.85, was_voted=True)

    asyncio.run(_seed())

    resp = client.post("/api/v1/admin/indicators/ICHIMOKU/enable")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["gated"] is True
    # Persistence layer doesn't exist yet — endpoint must surface this honestly.
    assert body["persisted"] is False
    assert body["indicator"] == "ICHIMOKU"
    assert body["stats"]["rolling_avg"] == pytest.approx(0.85, abs=1e-9)


def test_enable_refused_when_insufficient_samples(client: TestClient):
    """Even high observed avg fails when fewer than MIN_SAMPLES_FOR_AVG."""
    registry = get_indicator_registry()
    import asyncio

    async def _seed() -> None:
        for _ in range(MIN_SAMPLES_FOR_AVG - 1):
            await registry.record("SQZMOM_ENHANCED", 0.95, was_voted=True)

    asyncio.run(_seed())

    resp = client.post("/api/v1/admin/indicators/SQZMOM_ENHANCED/enable")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    # current_avg is None because the registry refuses to compute below the floor.
    assert detail["current_avg"] is None


# ---------------------------------------------------------------------------
# Stats endpoint (read-only sibling)
# ---------------------------------------------------------------------------


def test_stats_endpoint_returns_snapshot(client: TestClient):
    registry = get_indicator_registry()
    import asyncio

    async def _seed() -> None:
        for _ in range(MIN_SAMPLES_FOR_AVG):
            await registry.record("MACD", 0.66, was_voted=True)

    asyncio.run(_seed())

    resp = client.get("/api/v1/admin/indicators/MACD/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["indicator"] == "MACD"
    assert body["rolling_avg"] == pytest.approx(0.66, abs=1e-9)
    assert body["sample_count"] == MIN_SAMPLES_FOR_AVG
    assert 0.0 <= body["threshold"] <= 1.0
