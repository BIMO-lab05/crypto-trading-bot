"""Integration tests for the ml-gate digest scheduler (MLGATE-03, Plan 09-03 D-09-03-07).

Closes checker Blocker 2 SC#4 cross-service delivery clause:
- scheduler fetches reason counts via HTTP from the trading-engine endpoint
- forwards them to alert_manager.send_daily_summary
- the dispatched Telegram payload contains the rendered ML Gate Reasons block

Mocking discipline (per plan + advisor guidance):
- ``respx`` intercepts the httpx.AsyncClient.get() call. We do NOT cross-import
  from services/trading-engine/app/ — both service packages name themselves
  ``app`` and would collide on PYTHONPATH. The trading-engine endpoint is
  exercised in its own per-handler smoke test (test_ml_gate_reasons_endpoint.py).
- The Telegram dispatch is captured by patching alert_manager.send_alert (the
  AlertManager layer above the channel clients), so we do not need to stub
  every channel's send method.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from app.alert_manager import AlertManager
from app.scheduler.ml_gate_digest import fetch_and_dispatch_digest


@pytest.fixture
def manager_with_capture(monkeypatch) -> AlertManager:
    """Real AlertManager with send_alert patched so we capture the AlertCreate."""
    am = AlertManager()
    captured: list = []

    async def _capture(alert_create):
        captured.append(alert_create)
        from app.models import AlertResponse

        return AlertResponse(
            success=True,
            alert_id="test-alert-id",
            message="captured",
            channels_sent=["telegram"],
        )

    monkeypatch.setattr(am, "send_alert", AsyncMock(side_effect=_capture))
    am._captured = captured  # type: ignore[attr-defined]
    return am


@pytest.mark.asyncio
@respx.mock
async def test_scheduler_fetches_counts_and_dispatches_telegram(manager_with_capture):
    """Happy path: 200 OK with reason counts → digest dispatched with rendered section."""
    base_url = "http://trading-engine:8005"
    respx.get(f"{base_url}/api/preflight/ml-gate-reason-counts").mock(
        return_value=httpx.Response(200, json={"no_evidence": 1, "dsr_below_gate": 1})
    )

    summary = await fetch_and_dispatch_digest(
        trading_engine_url=base_url,
        alert_manager=manager_with_capture,
    )

    # Returned dispatch summary.
    assert summary["fetch_status"] == "ok"
    assert summary["reason_counts"] == {"no_evidence": 1, "dsr_below_gate": 1}
    assert summary["dispatched"] is True

    # Captured AlertCreate (the would-be Telegram payload via AlertManager.send_alert).
    assert len(manager_with_capture._captured) == 1
    captured = manager_with_capture._captured[0]
    assert "ML Gate Reasons (24h):" in captured.message
    assert "- no_evidence: 1" in captured.message
    assert "- dsr_below_gate: 1" in captured.message


@pytest.mark.asyncio
@respx.mock
async def test_scheduler_handles_trading_engine_unreachable(manager_with_capture):
    """Connection error → digest STILL dispatched, ML section absent (graceful degradation)."""
    base_url = "http://trading-engine:8005"
    respx.get(f"{base_url}/api/preflight/ml-gate-reason-counts").mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    summary = await fetch_and_dispatch_digest(
        trading_engine_url=base_url,
        alert_manager=manager_with_capture,
    )

    assert summary["fetch_status"] == "error"
    assert summary["reason_counts"] is None
    # Digest STILL dispatched per graceful-degradation discipline.
    assert summary["dispatched"] is True
    assert len(manager_with_capture._captured) == 1
    captured = manager_with_capture._captured[0]
    assert "ML Gate Reasons" not in captured.message
    # Performance section still present.
    assert "Performance Summary" in captured.message


@pytest.mark.asyncio
@respx.mock
async def test_scheduler_handles_non_200_response(manager_with_capture):
    """500 from trading-engine → same graceful-degradation shape."""
    base_url = "http://trading-engine:8005"
    respx.get(f"{base_url}/api/preflight/ml-gate-reason-counts").mock(
        return_value=httpx.Response(500, text="")
    )

    summary = await fetch_and_dispatch_digest(
        trading_engine_url=base_url,
        alert_manager=manager_with_capture,
    )

    assert summary["fetch_status"] == "error"
    assert summary["reason_counts"] is None
    assert summary["dispatched"] is True
    assert "ML Gate Reasons" not in manager_with_capture._captured[0].message


@pytest.mark.asyncio
@respx.mock
async def test_scheduler_handles_non_dict_json_response(manager_with_capture):
    """200 OK but body is not a JSON dict → graceful degradation."""
    base_url = "http://trading-engine:8005"
    respx.get(f"{base_url}/api/preflight/ml-gate-reason-counts").mock(
        return_value=httpx.Response(200, json=["unexpected", "list"])
    )

    summary = await fetch_and_dispatch_digest(
        trading_engine_url=base_url,
        alert_manager=manager_with_capture,
    )

    assert summary["fetch_status"] == "error"
    assert summary["reason_counts"] is None
    assert summary["dispatched"] is True
