"""
Connector contract test (Phase B5)

Pins the HTTP contract between the trading-engine and the bybit-connector.
Specifically verifies:

* `BybitExchangeAdapter` calls the actual paths the connector exposes
  (`/api/v1/order/place`, `/api/v1/order/open`, `/api/v1/account/positions`,
  `/api/v1/market/ticker`, `/api/v1/market/recent-trade`, …) — NOT the
  underlying Bybit-native paths (`/v5/order/create`, `/v5/order/realtime`, …).
* The adapter correctly unwraps the connector's
  ``{"success": True, "data": {...}}`` response envelope.
* `LiveTradingEngine.execute_market_order` reads the same envelope shape and
  treats ``success: True`` as a successful order placement (the bug this
  test guards against silently rejected every successful live order with
  ``"Unknown error"``).
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from app.exchanges import (
    BybitExchangeAdapter,
    ExchangeConfig,
    ExchangeName,
    OrderSide,
    OrderType,
    ProductType,
    UnifiedOrder,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wrap(result: dict) -> dict:
    """Mimic the bybit-connector success envelope."""
    return {"success": True, "data": result}


@pytest.fixture
def adapter() -> BybitExchangeAdapter:
    config = ExchangeConfig(
        exchange=ExchangeName.BYBIT,
        api_key="test-key",
        api_secret="test-secret",
        testnet=True,
    )
    return BybitExchangeAdapter(config, connector_url="http://localhost:8001")


# ---------------------------------------------------------------------------
# Adapter URL contract
# ---------------------------------------------------------------------------

class TestBybitAdapterURLContract:
    """Every adapter call must hit a path the connector actually serves."""

    @pytest.mark.asyncio
    async def test_get_balance_hits_account_balance(self, adapter):
        captured = {}

        async def fake_request(method, url, **kwargs):
            captured["url"] = url
            response = MagicMock(spec=httpx.Response)
            response.status_code = 200
            response.json.return_value = _wrap({"list": [{
                "totalEquity": "100",
                "availableBalance": "100",
                "totalPositionIM": "0",
                "totalPerpUPL": "0",
                "coin": [],
            }]})
            return response

        adapter._client = MagicMock()
        adapter._client.request = AsyncMock(side_effect=fake_request)

        await adapter.get_balance()
        assert captured["url"] == "/api/v1/account/balance"

    @pytest.mark.asyncio
    async def test_get_positions_hits_account_positions(self, adapter):
        captured = {}

        async def fake_request(method, url, **kwargs):
            captured["url"] = url
            response = MagicMock(spec=httpx.Response)
            response.status_code = 200
            response.json.return_value = _wrap({"list": []})
            return response

        adapter._client = MagicMock()
        adapter._client.request = AsyncMock(side_effect=fake_request)

        await adapter.get_positions()
        # Critical: NOT "/api/v1/position/list" (which doesn't exist)
        assert captured["url"] == "/api/v1/account/positions"

    @pytest.mark.asyncio
    async def test_place_order_hits_order_place(self, adapter):
        captured = {}

        async def fake_request(method, url, **kwargs):
            captured["url"] = url
            captured["method"] = method
            response = MagicMock(spec=httpx.Response)
            response.status_code = 200
            response.json.return_value = _wrap({
                "orderId": "abc123",
                "orderLinkId": "link-1",
            })
            return response

        adapter._client = MagicMock()
        adapter._client.request = AsyncMock(side_effect=fake_request)

        order = UnifiedOrder(
            exchange=ExchangeName.BYBIT,
            symbol="SOLUSDT",
            product_type=ProductType.LINEAR,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.5"),
        )
        result = await adapter.place_order(order)

        # Critical: NOT "/api/v1/order/create"
        assert captured["url"] == "/api/v1/order/place"
        assert captured["method"] == "POST"
        # Confirm the response unwrapping path returned the data envelope.
        assert result.exchange_order_id == "abc123"

    @pytest.mark.asyncio
    async def test_get_open_orders_hits_order_open(self, adapter):
        captured = {}

        async def fake_request(method, url, **kwargs):
            captured["url"] = url
            response = MagicMock(spec=httpx.Response)
            response.status_code = 200
            response.json.return_value = _wrap({"list": []})
            return response

        adapter._client = MagicMock()
        adapter._client.request = AsyncMock(side_effect=fake_request)

        await adapter.get_open_orders()
        # Critical: NOT "/api/v1/order/realtime"
        assert captured["url"] == "/api/v1/order/open"

    @pytest.mark.asyncio
    async def test_get_ticker_hits_market_ticker_singular(self, adapter):
        captured = {}

        async def fake_request(method, url, **kwargs):
            captured["url"] = url
            response = MagicMock(spec=httpx.Response)
            response.status_code = 200
            response.json.return_value = _wrap({"list": [{
                "symbol": "SOLUSDT",
                "lastPrice": "150",
            }]})
            return response

        adapter._client = MagicMock()
        adapter._client.request = AsyncMock(side_effect=fake_request)

        await adapter.get_ticker("SOLUSDT")
        # Critical: singular "ticker", NOT "tickers"
        assert captured["url"] == "/api/v1/market/ticker"

    @pytest.mark.asyncio
    async def test_get_trades_hits_market_recent_trade(self, adapter):
        captured = {}

        async def fake_request(method, url, **kwargs):
            captured["url"] = url
            response = MagicMock(spec=httpx.Response)
            response.status_code = 200
            response.json.return_value = _wrap({"list": []})
            return response

        adapter._client = MagicMock()
        adapter._client.request = AsyncMock(side_effect=fake_request)

        await adapter.get_trades("SOLUSDT")
        # Connector now exposes this as a thin proxy.
        assert captured["url"] == "/api/v1/market/recent-trade"


# ---------------------------------------------------------------------------
# Live trading engine envelope contract
# ---------------------------------------------------------------------------

class TestLiveTradingResponseEnvelope:
    """`LiveTradingEngine` must read connector's ``{"success", "data"}`` shape."""

    @pytest.mark.asyncio
    async def test_execute_market_order_success_envelope(self):
        # Lazy import — the trading-engine module pulls in heavy deps.
        from app.live_trading import LiveTradingEngine
        from app.models import OrderCreate, OrderSide as MOrderSide, OrderType as MOrderType

        engine = LiveTradingEngine.__new__(LiveTradingEngine)  # bypass __init__ side-effects
        engine.bybit_url = "http://test-connector"
        engine.client = MagicMock()
        engine.client.post = AsyncMock()

        # Stub risk + position managers — they're orthogonal to the response shape.
        # `execute_market_order` gates on check_position_limits(positions,
        # balance) -> (allowed, reason); the 2026-05-01 audit replaced
        # can_open_position with it. A bare MagicMock returns a MagicMock,
        # which fails to unpack into two names before the envelope is ever
        # parsed, so the tuple must be stubbed explicitly.
        engine.risk_manager = MagicMock()
        engine.risk_manager.check_position_limits.return_value = (True, "")
        engine.risk_manager.calculate_stop_loss.return_value = Decimal("145")
        engine.risk_manager.calculate_take_profit.return_value = Decimal("160")
        engine.position_manager = MagicMock()
        engine.position_manager.get_open_positions.return_value = []
        engine.position_manager.create_position.return_value = MagicMock(id=uuid4())
        # get_balance() awaits self.client.get(); stub the coroutine directly
        # so this test stays about the response envelope. $100 is the account
        # size of record (CLAUDE.md 1).
        engine.get_balance = AsyncMock(return_value=Decimal("100"))

        # The connector returns the wrapped envelope.
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "success": True,
            "data": {"orderId": "ORDER_123"},
        }
        engine.client.post.return_value = response

        order = OrderCreate(
            symbol="SOLUSDT",
            side=MOrderSide.BUY,
            type=MOrderType.MARKET,
            quantity=Decimal("0.5"),
        )

        executed, error = await engine.execute_market_order(order, current_price=Decimal("150"))

        # The whole point of the bug fix: a wrapped success must NOT be
        # mis-read as "Unknown error".
        assert error is None, f"Unexpected error: {error!r}"
        assert executed is not None
        assert executed.bybit_order_id == "ORDER_123"

    @pytest.mark.asyncio
    async def test_execute_market_order_failure_envelope(self):
        """When connector responds {"success": false, "detail": "..."} we surface it."""
        from app.live_trading import LiveTradingEngine
        from app.models import OrderCreate, OrderSide as MOrderSide, OrderType as MOrderType

        engine = LiveTradingEngine.__new__(LiveTradingEngine)
        engine.bybit_url = "http://test-connector"
        engine.client = MagicMock()
        engine.client.post = AsyncMock()

        engine.risk_manager = MagicMock()
        engine.risk_manager.check_position_limits.return_value = (True, "")
        engine.position_manager = MagicMock()
        engine.position_manager.get_open_positions.return_value = []
        engine.get_balance = AsyncMock(return_value=Decimal("100"))

        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "success": False,
            "detail": "Insufficient balance",
        }
        engine.client.post.return_value = response

        order = OrderCreate(
            symbol="SOLUSDT",
            side=MOrderSide.BUY,
            type=MOrderType.MARKET,
            quantity=Decimal("0.5"),
        )

        executed, error = await engine.execute_market_order(order, current_price=Decimal("150"))

        assert executed is None
        assert error == "Insufficient balance"
