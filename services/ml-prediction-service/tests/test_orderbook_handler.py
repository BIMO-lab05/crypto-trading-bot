"""Tests for the refactored ml-prediction orderbook handler (BC-02 / D-03).

Asserts the handler routes through bybit-connector REST (not api.bybit.com directly)
and parses the wrapper-shape `{success, data}` response — not the raw Bybit
`{retCode, retMsg, result}` shape. Pitfall 2 in 13-RESEARCH.md catches the
mechanical refactor regression where URL is swapped but parser is not.

Test fixtures use respx to mock `${BYBIT_CONNECTOR_URL}/api/v1/market/orderbook`.
The connector default URL in-container is `http://bybit-connector:8001`.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict

import httpx
import pytest
import respx

# The orderbook handler imports `from app.config import get_settings`. The service
# package layout uses bare `app.*` imports, so we put the service dir on sys.path.
_SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICE_ROOT))


CONNECTOR_URL = "http://bybit-connector:8001"


def _wrap(data: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap payload in bybit-connector wrapper shape `{success, data}`."""
    return {"success": True, "data": data}


@pytest.fixture
def orderbook_module(monkeypatch):
    """Force-reimport the handler so module-level BYBIT_CONNECTOR_URL captures
    the env we set here. Also reset the module-global `_http_client` between
    tests so each test starts from a clean slate.
    """
    monkeypatch.setenv("BYBIT_CONNECTOR_URL", CONNECTOR_URL)
    # Drop any cached import so the module-level constant re-resolves.
    sys.modules.pop("app.handlers.orderbook", None)
    module = importlib.import_module("app.handlers.orderbook")
    # Reset module-level httpx client cache so respx mocks intercept cleanly.
    module._http_client = None
    yield module
    module._http_client = None
    sys.modules.pop("app.handlers.orderbook", None)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_orderbook_from_connector_hits_bybit_connector(orderbook_module):
    """Refactored handler MUST call `${BYBIT_CONNECTOR_URL}/api/v1/market/orderbook`
    with the expected query params and parse the wrapper-shape response into
    `[price, size]` float pairs.
    """
    sample_data = {
        "s": "BTCUSDT",
        "a": [["100001.0", "1.2"], ["100002.0", "0.8"]],
        "b": [["100000.0", "1.5"], ["99999.0", "2.0"]],
        "ts": 1700000000000,
        "u": 12345,
    }
    route = respx.get(f"{CONNECTOR_URL}/api/v1/market/orderbook").mock(
        return_value=httpx.Response(200, json=_wrap(sample_data))
    )

    result = await orderbook_module.fetch_orderbook_from_connector("BTCUSDT", limit=25)

    assert route.called, "Handler did not call bybit-connector REST endpoint"
    # Verify params (category=linear, symbol=BTCUSDT uppercase, limit=25)
    call = route.calls.last
    assert call.request.url.params["category"] == "linear"
    assert call.request.url.params["symbol"] == "BTCUSDT"
    assert call.request.url.params["limit"] == "25"

    # Wrapper-shape parsed: bids/asks are float pairs.
    assert result["bids"] == [[100000.0, 1.5], [99999.0, 2.0]]
    assert result["asks"] == [[100001.0, 1.2], [100002.0, 0.8]]
    assert result["timestamp"] == 1700000000000


@pytest.mark.asyncio
@respx.mock
async def test_fetch_orderbook_handles_empty_tape_response(orderbook_module):
    """Tape-mode stub returns `{"a":[], "b":[], "ts":0, "u":0}`. Handler must
    return empty bids/asks and timestamp=0 without raising. This is the
    BC-07 tape preservation contract.
    """
    tape_stub = {"a": [], "b": [], "ts": 0, "u": 0}
    respx.get(f"{CONNECTOR_URL}/api/v1/market/orderbook").mock(
        return_value=httpx.Response(200, json=_wrap(tape_stub))
    )

    result = await orderbook_module.fetch_orderbook_from_connector("BTCUSDT", limit=25)

    assert result["bids"] == []
    assert result["asks"] == []
    assert result["timestamp"] == 0


@pytest.mark.asyncio
@respx.mock
async def test_fetch_orderbook_raises_on_connector_failure(orderbook_module):
    """Wrapper-shape `success=False` MUST raise HTTPException(502) with a generic
    error message — NOT propagate inner Bybit retMsg (security V7 hygiene).
    """
    from fastapi import HTTPException

    respx.get(f"{CONNECTOR_URL}/api/v1/market/orderbook").mock(
        return_value=httpx.Response(
            200, json={"success": False, "error": "internal connector failure detail"}
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await orderbook_module.fetch_orderbook_from_connector("BTCUSDT", limit=25)

    assert exc_info.value.status_code == 502
    # Security V7: generic message, no inner-error propagation.
    detail = str(exc_info.value.detail)
    assert "internal connector failure detail" not in detail
    assert "bybit-connector" in detail.lower()


@pytest.mark.asyncio
@respx.mock
async def test_fetch_orderbook_raises_on_http_error(orderbook_module):
    """503 from bybit-connector MUST raise HTTPException (handler converts httpx
    error into a clean HTTP-friendly exception)."""
    from fastapi import HTTPException

    respx.get(f"{CONNECTOR_URL}/api/v1/market/orderbook").mock(
        return_value=httpx.Response(503, text="service unavailable")
    )

    with pytest.raises(HTTPException):
        await orderbook_module.fetch_orderbook_from_connector("BTCUSDT", limit=25)
