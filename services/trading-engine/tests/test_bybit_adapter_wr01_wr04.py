"""E2E verification for Phase 18 WR-01 (D-05 FILLED propagation) and
WR-04 (client-side get_order_status filter).

Both fixes were flagged `requires human verification` in 18-REVIEW-FIX.md
because no in-scope test exercised the semantic change. These tests mock
the bybit-connector HTTP surface with `respx` and assert the adapter
returns the correct UnifiedOrder shape after `place_order` and
`get_order_status`.

Runs against host pytest (no docker required — respx intercepts httpx
transport in-process). Companion to test_bybit_adapter_contract.py.
"""

from decimal import Decimal

import httpx
import pytest
import respx

from app.exchanges import (
    BybitExchangeAdapter,
    ExchangeConfig,
    ExchangeName,
    OrderNotFoundError,
    OrderSide,
    OrderStatus,
    OrderType,
    ProductType,
    UnifiedOrder,
)


CONNECTOR_URL = "http://mock-connector:8001"


@pytest.fixture
async def adapter():
    """Adapter with an httpx.AsyncClient pointed at the mock URL.

    We do not call `adapter.initialize()` because that path runs health_check +
    get_balance and would need extra respx routes unrelated to the fixes under
    test. Manually assign the client to keep the setup minimal.
    """
    config = ExchangeConfig(
        exchange=ExchangeName.BYBIT,
        api_key="test-key",
        api_secret="test-secret",
        testnet=True,
        default_product=ProductType.LINEAR,
    )
    a = BybitExchangeAdapter(config, connector_url=CONNECTOR_URL)
    a._client = httpx.AsyncClient(
        base_url=CONNECTOR_URL,
        timeout=httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=10.0),
        headers={"Content-Type": "application/json"},
    )
    try:
        yield a
    finally:
        await a.close()


# ---------------------------------------------------------------------------
# WR-01: D-05 deterministic FILLED must reach UnifiedOrder
# ---------------------------------------------------------------------------


@respx.mock
async def test_wr01_place_order_propagates_filled_status(adapter):
    """Tape-shape response: orderStatus='Filled', avgPrice, cumExecQty.
    Pre-fix behaviour hard-coded status = OrderStatus.NEW and dropped
    avgPrice / cumExecQty. Fix reads all three."""
    tape_response = {
        "success": True,
        "data": {
            "orderId": "TAPE_SOLUSDT_Buy_1700000000000_1",
            "orderLinkId": "cli-abc",
            "symbol": "SOLUSDT",
            "side": "Buy",
            "orderStatus": "Filled",
            "avgPrice": "150.42",
            "cumExecQty": "0.5",
            "qty": "0.5",
            "orderType": "Market",
            "category": "linear",
            "reduceOnly": False,
            "timeInForce": "GTC",
        },
    }

    route = respx.post(f"{CONNECTOR_URL}/api/v1/order/place").mock(
        return_value=httpx.Response(200, json=tape_response)
    )

    order = UnifiedOrder(
        exchange=ExchangeName.BYBIT,
        symbol="SOLUSDT",
        product_type=ProductType.LINEAR,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.5"),
    )

    result = await adapter.place_order(order)

    assert route.called, "place_order route was not hit"
    assert result.status == OrderStatus.FILLED, (
        f"WR-01 regression: expected OrderStatus.FILLED, got {result.status}"
    )
    assert result.filled_price == Decimal("150.42"), (
        f"WR-01 regression: expected filled_price=150.42, got {result.filled_price}"
    )
    assert result.filled_quantity == Decimal("0.5"), (
        f"WR-01 regression: expected filled_quantity=0.5, got {result.filled_quantity}"
    )
    assert result.exchange_order_id == "TAPE_SOLUSDT_Buy_1700000000000_1"
    assert result.client_order_id == "cli-abc"


@respx.mock
async def test_wr01_partial_fill_status_mapped(adapter):
    """Bybit 'PartiallyFilled' must map to OrderStatus.PARTIALLY_FILLED
    with the partial cumExecQty carried into filled_quantity."""
    partial_response = {
        "success": True,
        "data": {
            "orderId": "PARTIAL_1",
            "orderLinkId": "cli-partial",
            "symbol": "BTCUSDT",
            "side": "Sell",
            "orderStatus": "PartiallyFilled",
            "avgPrice": "60000.10",
            "cumExecQty": "0.001",
            "qty": "0.010",
            "orderType": "Limit",
            "category": "linear",
            "reduceOnly": False,
            "timeInForce": "GTC",
        },
    }
    respx.post(f"{CONNECTOR_URL}/api/v1/order/place").mock(
        return_value=httpx.Response(200, json=partial_response)
    )

    order = UnifiedOrder(
        exchange=ExchangeName.BYBIT,
        symbol="BTCUSDT",
        product_type=ProductType.LINEAR,
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.010"),
        price=Decimal("60000"),
    )
    result = await adapter.place_order(order)

    assert result.status == OrderStatus.PARTIALLY_FILLED
    assert result.filled_quantity == Decimal("0.001")
    assert result.filled_price == Decimal("60000.10")


@respx.mock
async def test_wr01_new_status_still_maps_correctly(adapter):
    """Guard: when exchange truly returns 'New' (e.g. non-tape live path),
    behaviour is unchanged — status is NEW and fill fields stay at defaults."""
    new_response = {
        "success": True,
        "data": {
            "orderId": "LIMIT_OPEN_1",
            "orderLinkId": "cli-open",
            "symbol": "SOLUSDT",
            "side": "Buy",
            "orderStatus": "New",
            "qty": "1.0",
            "orderType": "Limit",
            "category": "linear",
            "reduceOnly": False,
            "timeInForce": "GTC",
        },
    }
    respx.post(f"{CONNECTOR_URL}/api/v1/order/place").mock(
        return_value=httpx.Response(200, json=new_response)
    )

    order = UnifiedOrder(
        exchange=ExchangeName.BYBIT,
        symbol="SOLUSDT",
        product_type=ProductType.LINEAR,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("1.0"),
        price=Decimal("100"),
    )
    result = await adapter.place_order(order)

    assert result.status == OrderStatus.NEW
    assert result.filled_quantity == Decimal("0")
    assert result.filled_price is None


# ---------------------------------------------------------------------------
# WR-04: get_order_status must filter client-side by orderId / orderLinkId
# ---------------------------------------------------------------------------


def _open_orders_response():
    """Three open orders under one symbol; connector route ignores the
    orderId query param, so it always returns them all in the same order.
    Pre-fix adapter would blindly return the first (A) regardless of what
    the caller asked for."""
    return {
        "success": True,
        "data": {
            "list": [
                {
                    "orderId": "A",
                    "orderLinkId": "cli-A",
                    "symbol": "SOLUSDT",
                    "side": "Buy",
                    "orderType": "Limit",
                    "orderStatus": "New",
                    "qty": "1",
                    "price": "100",
                    "avgPrice": "0",
                    "cumExecQty": "0",
                },
                {
                    "orderId": "B",
                    "orderLinkId": "cli-B",
                    "symbol": "SOLUSDT",
                    "side": "Buy",
                    "orderType": "Limit",
                    "orderStatus": "New",
                    "qty": "2",
                    "price": "110",
                    "avgPrice": "0",
                    "cumExecQty": "0",
                },
                {
                    "orderId": "C",
                    "orderLinkId": "cli-C",
                    "symbol": "SOLUSDT",
                    "side": "Buy",
                    "orderType": "Limit",
                    "orderStatus": "New",
                    "qty": "3",
                    "price": "120",
                    "avgPrice": "0",
                    "cumExecQty": "0",
                },
            ]
        },
    }


@respx.mock
async def test_wr04_get_order_status_returns_requested_by_order_id(adapter):
    """When multiple open orders exist for one symbol, get_order_status
    must return the one whose orderId matches — not just list[0]."""
    respx.get(f"{CONNECTOR_URL}/api/v1/order/open").mock(
        return_value=httpx.Response(200, json=_open_orders_response())
    )

    result = await adapter.get_order_status(symbol="SOLUSDT", order_id="B")

    assert result.exchange_order_id == "B", (
        f"WR-04 regression: expected B, got {result.exchange_order_id} "
        "(pre-fix would have returned A — the first entry)"
    )


@respx.mock
async def test_wr04_get_order_status_filters_by_client_order_id(adapter):
    """Same guarantee via client_order_id (orderLinkId) path."""
    respx.get(f"{CONNECTOR_URL}/api/v1/order/open").mock(
        return_value=httpx.Response(200, json=_open_orders_response())
    )

    result = await adapter.get_order_status(symbol="SOLUSDT", client_order_id="cli-C")

    assert result.exchange_order_id == "C"
    assert result.client_order_id == "cli-C"


@respx.mock
async def test_wr04_get_order_status_raises_when_id_missing(adapter):
    """Caller ID absent from the returned list => OrderNotFoundError
    (previously silently returned list[0] as a false-positive)."""
    respx.get(f"{CONNECTOR_URL}/api/v1/order/open").mock(
        return_value=httpx.Response(200, json=_open_orders_response())
    )

    with pytest.raises(OrderNotFoundError):
        await adapter.get_order_status(symbol="SOLUSDT", order_id="Z_NOT_PRESENT")


@respx.mock
async def test_wr04_get_order_status_empty_list_raises(adapter):
    """Empty list from connector still raises OrderNotFoundError (unchanged
    behaviour; kept in the regression net so future refactors don't break it)."""
    respx.get(f"{CONNECTOR_URL}/api/v1/order/open").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"list": []}})
    )

    with pytest.raises(OrderNotFoundError):
        await adapter.get_order_status(symbol="SOLUSDT", order_id="anything")
