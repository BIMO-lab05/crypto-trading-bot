"""Endpoint smoke tests for app.handlers.ml_gate_reasons (MLGATE-03, Plan 09-03 D-09-03-07).

Builds a standalone FastAPI TestClient over a minimal app that just mounts the
new router — same pattern as the Phase 8 preflight route test (the trading-engine
app.main.py mount is exercised end-to-end at integration time; here we want a
focused per-handler smoke).

Tests:
- Empty counter -> 200, returns {}.
- Populated counter -> 200, returns the canonical dict shape.
- Internal exception in snapshot_reasons -> 500 with public-safe detail string.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.aggregation.ml_gate_reasons import (
    record_ml_gate_event,
    reset_counter,
)
from app.handlers.ml_gate_reasons import router as ml_gate_reasons_router


@pytest.fixture
def client() -> TestClient:
    """A minimal FastAPI app mounting only the ml-gate-reason-counts router."""
    app = FastAPI()
    app.include_router(ml_gate_reasons_router)
    return TestClient(app)


def test_endpoint_returns_empty_dict_on_fresh_state(client):
    reset_counter()
    response = client.get("/api/preflight/ml-gate-reason-counts")
    assert response.status_code == 200
    assert response.json() == {}


def test_endpoint_returns_populated_dict_after_record_calls(client):
    reset_counter()
    record_ml_gate_event("no_evidence")
    record_ml_gate_event("no_evidence")
    record_ml_gate_event("dsr_below_gate")
    response = client.get("/api/preflight/ml-gate-reason-counts")
    assert response.status_code == 200
    body = response.json()
    assert body == {"no_evidence": 2, "dsr_below_gate": 1}


def test_endpoint_returns_500_on_internal_error(client, monkeypatch):
    """If snapshot_reasons raises, the handler must translate to 500.

    The response body must NOT echo the underlying exception text — only the
    public-safe detail string. The exception type is logged for the operator
    via the logger, not returned to the caller.
    """

    def _boom() -> dict[str, int]:
        raise RuntimeError("internal counter corruption — should NOT leak to client")

    # Patch the symbol the handler imported (NOT the source module) so the
    # handler's local binding is replaced.
    monkeypatch.setattr(
        "app.handlers.ml_gate_reasons.snapshot_reasons",
        _boom,
    )
    response = client.get("/api/preflight/ml-gate-reason-counts")
    assert response.status_code == 500
    body = response.json()
    assert body == {"detail": "ml-gate-reason-counts read failed"}
    # Confirm the raw exception text did not leak.
    assert "internal counter corruption" not in response.text
