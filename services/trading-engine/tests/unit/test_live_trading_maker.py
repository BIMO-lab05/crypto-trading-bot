"""
Unit tests for LiveTradingEngine.execute_maker_order_with_fallback (T1.3).

The tested method orchestrates a PostOnly limit + timeout-based fallback
without ever touching the real Bybit API — `httpx.AsyncClient` is mocked
end-to-end. We also patch the in-method `time.monotonic` and
`asyncio.sleep` so polling runs synthetically without real wall time.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "shared"))

from app import live_trading as live_trading_module
from app.live_trading import LiveTradingEngine
from app.models import OrderCreate, OrderSide, OrderStatus, OrderType


def _make_settings(*, fallback: bool = True, timeout: int = 4) -> Mock:
    settings = Mock()
    settings.bybit_connector_url = "http://bybit-connector:8001"
    settings.prefer_maker_orders = True
    settings.maker_quote_timeout_seconds = timeout
    settings.maker_fallback_to_taker = fallback
    return settings


def _make_order(side: OrderSide = OrderSide.BUY) -> OrderCreate:
    return OrderCreate(
        symbol="BTCUSDT",
        side=side,
        type=OrderType.MARKET,
        quantity=Decimal("0.01"),
        strategy="research_optimized",
        entry_signal_confidence=0.65,
    )


def _http_response(payload: dict, status_code: int = 200) -> Mock:
    resp = Mock()
    resp.status_code = status_code
    resp.raise_for_status = Mock()
    resp.json = Mock(return_value=payload)
    return resp


@pytest.fixture
def engine():
    """LiveTradingEngine with all dependencies mocked, including httpx client."""
    settings = _make_settings()
    position_manager = Mock()
    position_manager.create_position = Mock(return_value=Mock(id="pos-1"))
    risk_manager = Mock()
    risk_manager.can_open_position = Mock(return_value=True)
    risk_manager.calculate_stop_loss = Mock(return_value=Decimal("48000"))
    risk_manager.calculate_take_profit = Mock(return_value=Decimal("52000"))

    with patch("app.live_trading.get_settings", return_value=settings), patch(
        "app.live_trading.get_position_manager", return_value=position_manager
    ), patch("app.live_trading.get_risk_manager", return_value=risk_manager), patch(
        "app.live_trading.httpx.AsyncClient"
    ) as MockClient:
        client = MockClient.return_value
        client.get = AsyncMock()
        client.post = AsyncMock()
        client.aclose = AsyncMock()

        eng = LiveTradingEngine()
        eng._mock_http = client
        eng._mock_position_manager = position_manager
        eng._mock_risk_manager = risk_manager
        yield eng


class TestMakerOrderHappyPath:
    @pytest.mark.asyncio
    async def test_post_only_fills_within_timeout(self, engine, monkeypatch):
        # Orderbook GET → bid=50000, ask=50001
        # Place POST → orderId=ORD-1
        # First open-orders GET → still open
        # Second open-orders GET → empty (filled)
        engine._mock_http.get.side_effect = [
            _http_response({"data": {"b": [["50000", "1"]], "a": [["50001", "1"]]}}),
            _http_response({"data": {"list": [{"orderId": "ORD-1"}]}}),
            _http_response({"data": {"list": []}}),
        ]
        engine._mock_http.post.return_value = _http_response(
            {"retCode": 0, "data": {"orderId": "ORD-1"}}
        )

        # Avoid real waits during polling
        monkeypatch.setattr(live_trading_module.asyncio, "sleep", AsyncMock())

        executed_order, error = await engine.execute_maker_order_with_fallback(
            _make_order(), Decimal("50000.5")
        )

        assert error is None
        assert executed_order is not None
        assert executed_order.status == OrderStatus.FILLED
        # BUY → posted at the bid (50000), not the ask
        assert executed_order.price == Decimal("50000")
        # Position was created at limit price, not the reference price
        engine._mock_position_manager.create_position.assert_called_once()
        kwargs = engine._mock_position_manager.create_position.call_args.kwargs
        assert kwargs["entry_price"] == Decimal("50000")

    @pytest.mark.asyncio
    async def test_sell_quotes_at_best_ask(self, engine, monkeypatch):
        engine._mock_http.get.side_effect = [
            _http_response({"data": {"b": [["50000", "1"]], "a": [["50010", "1"]]}}),
            _http_response({"data": {"list": []}}),  # filled on first poll
        ]
        engine._mock_http.post.return_value = _http_response(
            {"retCode": 0, "data": {"orderId": "ORD-2"}}
        )
        monkeypatch.setattr(live_trading_module.asyncio, "sleep", AsyncMock())

        executed_order, _ = await engine.execute_maker_order_with_fallback(
            _make_order(side=OrderSide.SELL), Decimal("50005")
        )
        # SELL → posted at the ask (50010)
        assert executed_order.price == Decimal("50010")
        # And the actual POST payload had Sell + Limit + PostOnly
        post_kwargs = engine._mock_http.post.call_args.kwargs
        body = post_kwargs["json"]
        assert body["side"] == "Sell"
        assert body["order_type"] == "Limit"
        assert body["time_in_force"] == "PostOnly"
        assert body["price"] == "50010"


class TestMakerOrderTimeout:
    @pytest.mark.asyncio
    async def test_timeout_with_fallback_routes_to_taker(self, engine, monkeypatch):
        # Orderbook → fine. Place succeeds. Every poll says "still open".
        engine._mock_http.get.side_effect = [
            _http_response({"data": {"b": [["50000", "1"]], "a": [["50001", "1"]]}}),
        ] + [_http_response({"data": {"list": [{"orderId": "ORD-3"}]}})] * 50

        engine._mock_http.post.return_value = _http_response(
            {"retCode": 0, "data": {"orderId": "ORD-3"}}
        )
        monkeypatch.setattr(live_trading_module.asyncio, "sleep", AsyncMock())

        # Patch out execute_market_order so we observe the fallback hop
        fallback_order = MagicMock()
        fallback_order.status = OrderStatus.FILLED
        engine.execute_market_order = AsyncMock(return_value=(fallback_order, None))

        executed_order, error = await engine.execute_maker_order_with_fallback(
            _make_order(), Decimal("50000.5")
        )

        assert error is None
        assert executed_order is fallback_order
        engine.execute_market_order.assert_awaited_once()
        # Cancel POST must have been issued before fallback
        cancel_calls = [
            c
            for c in engine._mock_http.post.call_args_list
            if "/order/cancel" in c.args[0]
        ]
        assert len(cancel_calls) == 1

    @pytest.mark.asyncio
    async def test_timeout_without_fallback_returns_error(self, engine, monkeypatch):
        engine.settings.maker_fallback_to_taker = False

        engine._mock_http.get.side_effect = [
            _http_response({"data": {"b": [["50000", "1"]], "a": [["50001", "1"]]}}),
        ] + [_http_response({"data": {"list": [{"orderId": "ORD-4"}]}})] * 50

        engine._mock_http.post.return_value = _http_response(
            {"retCode": 0, "data": {"orderId": "ORD-4"}}
        )
        monkeypatch.setattr(live_trading_module.asyncio, "sleep", AsyncMock())

        engine.execute_market_order = AsyncMock()

        executed_order, error = await engine.execute_maker_order_with_fallback(
            _make_order(), Decimal("50000.5")
        )

        assert executed_order is None
        assert error and "timed out" in error
        engine.execute_market_order.assert_not_awaited()


class TestMakerOrderDegradedPaths:
    @pytest.mark.asyncio
    async def test_orderbook_unreachable_falls_through_to_taker(self, engine, monkeypatch):
        # Orderbook fetch raises → falls through to execute_market_order
        engine._mock_http.get.side_effect = RuntimeError("connection refused")

        fallback_order = MagicMock(status=OrderStatus.FILLED)
        engine.execute_market_order = AsyncMock(return_value=(fallback_order, None))

        executed_order, error = await engine.execute_maker_order_with_fallback(
            _make_order(), Decimal("50000.5")
        )

        assert error is None
        assert executed_order is fallback_order
        engine.execute_market_order.assert_awaited_once()
        engine._mock_http.post.assert_not_awaited()  # never tried to place

    @pytest.mark.asyncio
    async def test_risk_manager_reject_short_circuits(self, engine):
        engine._mock_risk_manager.can_open_position.return_value = False

        executed_order, error = await engine.execute_maker_order_with_fallback(
            _make_order(), Decimal("50000")
        )

        assert executed_order is None
        assert "Risk manager" in error
        engine._mock_http.get.assert_not_awaited()
        engine._mock_http.post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_order_id_in_response_falls_back(self, engine, monkeypatch):
        # Orderbook OK. Place returns 200 with malformed body (no orderId).
        # bybit-connector raises HTTP 4xx on real Bybit rejections, so this
        # represents either a connector bug or schema drift; the maker path
        # treats missing orderId as a fail-soft and routes to the taker.
        engine._mock_http.get.return_value = _http_response(
            {"data": {"b": [["50000", "1"]], "a": [["50001", "1"]]}}
        )
        engine._mock_http.post.return_value = _http_response(
            {"success": True, "data": {}}  # no orderId
        )

        fallback_order = MagicMock(status=OrderStatus.FILLED)
        engine.execute_market_order = AsyncMock(return_value=(fallback_order, None))

        executed_order, error = await engine.execute_maker_order_with_fallback(
            _make_order(), Decimal("50000.5")
        )

        assert error is None
        assert executed_order is fallback_order
        engine.execute_market_order.assert_awaited_once()


class TestExecuteMarketOrderConnectorContract:
    """
    Regression tests for the bybit-connector response contract:
    {"success": True, "data": <bybit_result>}. The connector raises HTTP 4xx
    on Bybit errors, so the trading-engine never sees retCode in success
    responses. Prior to the fix, execute_market_order looked up `result`
    instead of `data` and gated on retCode != 0 — every successful order
    looked like 'Unknown error'.
    """

    @pytest.mark.asyncio
    async def test_market_order_extracts_bybit_order_id_from_data(self, engine):
        engine._mock_http.post.return_value = _http_response(
            {"success": True, "data": {"orderId": "BYB-XYZ-1"}}
        )

        executed_order, error = await engine.execute_market_order(
            _make_order(), Decimal("50100")
        )

        assert error is None
        assert executed_order is not None
        assert executed_order.bybit_order_id == "BYB-XYZ-1"
        # Filled fields populated at construction time (no post-init mutation)
        assert executed_order.filled_price == Decimal("50100")
        assert executed_order.filled_quantity == Decimal("0.01")
        assert executed_order.status == OrderStatus.FILLED
        engine._mock_position_manager.create_position.assert_called_once()

    @pytest.mark.asyncio
    async def test_market_order_position_uses_supplied_price(self, engine):
        engine._mock_http.post.return_value = _http_response(
            {"success": True, "data": {"orderId": "BYB-XYZ-2"}}
        )
        await engine.execute_market_order(_make_order(OrderSide.SELL), Decimal("49900"))
        kwargs = engine._mock_position_manager.create_position.call_args.kwargs
        assert kwargs["entry_price"] == Decimal("49900")
        # SELL → SHORT
        from app.models import PositionSide
        assert kwargs["side"] == PositionSide.SHORT
