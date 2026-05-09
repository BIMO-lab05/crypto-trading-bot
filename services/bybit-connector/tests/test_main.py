"""
Bybit Connector Service - FastAPI Main Application Tests
Purpose: Comprehensive tests for FastAPI endpoints, CORS, and error handling
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, patch
from fastapi import status

from app.main import app
from app.exceptions import BybitAPIException, RateLimitException, ValidationException
from app.models import OrderSide, OrderType, TimeInForce, Category


# ============================================================================
# HEALTH ENDPOINT TESTS
# ============================================================================

class TestHealthEndpoints:
    """Test health check and readiness endpoints"""

    def test_health_check_endpoint(self, client):
        """Test /health endpoint returns healthy status"""
        # When calling health endpoint
        response = client.get("/health")

        # Then response is successful
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "healthy", "service": "bybit-connector"}

    def test_readiness_check_endpoint_success(self, client, mock_rest_client):
        """Test /ready endpoint when Bybit connection is OK"""
        # Given mock client returns successful ticker response
        mock_rest_client.get_ticker = AsyncMock(return_value={
            "retCode": 0,
            "retMsg": "OK",
            "result": {"list": [{"symbol": "BTCUSDT", "lastPrice": "50000"}]}
        })

        # When calling readiness endpoint
        response = client.get("/ready")

        # Then response indicates ready
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "ready"
        assert response.json()["bybit_connection"] == "ok"

    def test_readiness_check_endpoint_failure(self, client, mock_rest_client):
        """Test /ready endpoint when Bybit connection fails"""
        # Given mock client raises exception
        mock_rest_client.get_ticker = AsyncMock(side_effect=Exception("Connection failed"))

        # When calling readiness endpoint
        response = client.get("/ready")

        # Then response indicates service unavailable
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "Bybit connection failed" in response.json()["detail"]

    def test_readiness_check_without_client(self):
        """Test /ready endpoint when client is not initialized"""
        # Given test client without mocked rest client
        with TestClient(app) as test_client:
            # Ensure no rest_client in app state
            test_client.app.state.rest_client = None

            # When calling readiness endpoint
            response = test_client.get("/ready")

            # Then response indicates service unavailable
            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


# ============================================================================
# ACCOUNT ENDPOINT TESTS
# ============================================================================

class TestAccountEndpoints:
    """Test account-related endpoints"""

    def test_get_balance_endpoint_success(self, client, mock_rest_client):
        """Test GET /api/v1/account/balance success"""
        # Given mock client returns balance data
        mock_rest_client.get_wallet_balance = AsyncMock(return_value={
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [{
                    "totalEquity": "10000",
                    "availableBalance": "8000"
                }]
            }
        })

        # When calling balance endpoint
        response = client.get("/api/v1/account/balance")

        # Then response is successful
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True
        assert "data" in response.json()

        # And client was called correctly
        mock_rest_client.get_wallet_balance.assert_called_once_with(
            account_type="UNIFIED",
            coin=None
        )

    def test_get_balance_endpoint_with_params(self, client, mock_rest_client):
        """Test GET /api/v1/account/balance with query parameters"""
        # Given mock client returns balance data
        mock_rest_client.get_wallet_balance = AsyncMock(return_value={
            "retCode": 0,
            "result": {}
        })

        # When calling balance endpoint with parameters
        response = client.get("/api/v1/account/balance?account_type=CONTRACT&coin=BTC")

        # Then client is called with correct params
        assert response.status_code == status.HTTP_200_OK
        mock_rest_client.get_wallet_balance.assert_called_once_with(
            account_type="CONTRACT",
            coin="BTC"
        )

    def test_get_balance_endpoint_error(self, client, mock_rest_client):
        """Test GET /api/v1/account/balance with API error"""
        # Given mock client raises exception
        mock_rest_client.get_wallet_balance = AsyncMock(
            side_effect=BybitAPIException("API Error", ret_code=10001, ret_msg="Invalid request")
        )

        # When calling balance endpoint
        response = client.get("/api/v1/account/balance")

        # Then error response is returned
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "API Error" in response.json()["detail"]

    def test_get_positions_endpoint_success(self, client, mock_rest_client):
        """Test GET /api/v1/account/positions success"""
        # Given mock client returns position data
        mock_rest_client.get_positions = AsyncMock(return_value={
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [{
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "size": "0.01",
                    "positionValue": "500"
                }]
            }
        })

        # When calling positions endpoint
        response = client.get("/api/v1/account/positions")

        # Then response is successful
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True
        assert "data" in response.json()

    def test_get_positions_endpoint_with_symbol(self, client, mock_rest_client):
        """Test GET /api/v1/account/positions with symbol filter"""
        # Given mock client returns position data
        mock_rest_client.get_positions = AsyncMock(return_value={
            "retCode": 0,
            "result": {"list": []}
        })

        # When calling positions endpoint with symbol
        response = client.get("/api/v1/account/positions?symbol=ETHUSDT")

        # Then client is called with symbol parameter
        assert response.status_code == status.HTTP_200_OK
        mock_rest_client.get_positions.assert_called_once_with(
            category="linear",
            symbol="ETHUSDT"
        )


# ============================================================================
# TRADING ENDPOINT TESTS
# ============================================================================

class TestTradingEndpoints:
    """Test trading-related endpoints"""

    def test_place_order_endpoint_success(self, client, mock_rest_client):
        """Test POST /api/v1/order/place with valid order"""
        # Given valid order request data
        order_data = {
            "category": "linear",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "order_type": "Limit",
            "qty": "0.01",
            "price": "50000",
            "time_in_force": "GTC"
        }

        # And mock client returns success
        mock_rest_client.place_order = AsyncMock(return_value={
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "orderId": "test-order-123",
                "orderLinkId": ""
            }
        })

        # When calling place order endpoint
        response = client.post("/api/v1/order/place", json=order_data)

        # Then response is successful
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True
        assert "data" in response.json()

        # And client was called with correct parameters
        mock_rest_client.place_order.assert_called_once()
        call_kwargs = mock_rest_client.place_order.call_args.kwargs
        assert call_kwargs["symbol"] == "BTCUSDT"
        assert call_kwargs["qty"] == "0.01"
        assert call_kwargs["price"] == "50000"

    def test_place_order_endpoint_invalid_data(self, client):
        """Test POST /api/v1/order/place with invalid data"""
        # Given invalid order request data (negative qty)
        order_data = {
            "symbol": "BTCUSDT",
            "side": "Buy",
            "order_type": "Limit",
            "qty": "-0.01",
            "price": "50000"
        }

        # When calling place order endpoint
        response = client.post("/api/v1/order/place", json=order_data)

        # Then validation error is returned
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_place_order_endpoint_limit_without_price(self, client):
        """Test POST /api/v1/order/place with limit order missing price"""
        # Given limit order without price
        order_data = {
            "symbol": "BTCUSDT",
            "side": "Buy",
            "order_type": "Limit",
            "qty": "0.01"
        }

        # When calling place order endpoint
        response = client.post("/api/v1/order/place", json=order_data)

        # Then validation error is returned
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_place_order_endpoint_api_error(self, client, mock_rest_client):
        """Test POST /api/v1/order/place with API error"""
        # Given valid order data but API error
        order_data = {
            "symbol": "BTCUSDT",
            "side": "Buy",
            "order_type": "Market",
            "qty": "0.01"
        }

        mock_rest_client.place_order = AsyncMock(
            side_effect=BybitAPIException("Insufficient balance", ret_code=10006, ret_msg="Balance not enough")
        )

        # When calling place order endpoint
        response = client.post("/api/v1/order/place", json=order_data)

        # Then API error is returned
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Insufficient balance" in response.json()["detail"]

    def test_cancel_order_endpoint_with_order_id(self, client, mock_rest_client):
        """Test POST /api/v1/order/cancel with order_id"""
        # Given cancel request with order_id
        cancel_data = {
            "symbol": "BTCUSDT",
            "order_id": "test-order-123"
        }

        mock_rest_client.cancel_order = AsyncMock(return_value={
            "retCode": 0,
            "retMsg": "OK",
            "result": {"orderId": "test-order-123"}
        })

        # When calling cancel order endpoint
        response = client.post("/api/v1/order/cancel", json=cancel_data)

        # Then response is successful
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True

        # And client was called correctly
        mock_rest_client.cancel_order.assert_called_once()

    def test_cancel_order_endpoint_with_order_link_id(self, client, mock_rest_client):
        """Test POST /api/v1/order/cancel with order_link_id"""
        # Given cancel request with order_link_id
        cancel_data = {
            "symbol": "BTCUSDT",
            "order_link_id": "my-order-456"
        }

        mock_rest_client.cancel_order = AsyncMock(return_value={
            "retCode": 0,
            "result": {}
        })

        # When calling cancel order endpoint
        response = client.post("/api/v1/order/cancel", json=cancel_data)

        # Then response is successful
        assert response.status_code == status.HTTP_200_OK

    def test_cancel_order_endpoint_without_ids(self, client):
        """Test POST /api/v1/order/cancel without order IDs"""
        # Given cancel request without IDs
        cancel_data = {
            "symbol": "BTCUSDT"
        }

        # When calling cancel order endpoint
        response = client.post("/api/v1/order/cancel", json=cancel_data)

        # Then validation error is returned
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_get_open_orders_endpoint(self, client, mock_rest_client):
        """Test GET /api/v1/order/open"""
        # Given mock client returns open orders
        mock_rest_client.get_open_orders = AsyncMock(return_value={
            "retCode": 0,
            "result": {
                "list": [
                    {"orderId": "1", "symbol": "BTCUSDT", "status": "New"},
                    {"orderId": "2", "symbol": "ETHUSDT", "status": "New"}
                ]
            }
        })

        # When calling get open orders endpoint
        response = client.get("/api/v1/order/open")

        # Then response is successful
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True

    def test_get_open_orders_endpoint_with_params(self, client, mock_rest_client):
        """Test GET /api/v1/order/open with query parameters"""
        # Given mock client
        mock_rest_client.get_open_orders = AsyncMock(return_value={
            "retCode": 0,
            "result": {"list": []}
        })

        # When calling with parameters
        response = client.get("/api/v1/order/open?symbol=BTCUSDT&limit=20")

        # Then client is called with correct params
        assert response.status_code == status.HTTP_200_OK
        mock_rest_client.get_open_orders.assert_called_once_with(
            category="linear",
            symbol="BTCUSDT",
            limit=20
        )

    def test_get_order_history_endpoint(self, client, mock_rest_client):
        """Test GET /api/v1/order/history"""
        # Given mock client returns order history
        mock_rest_client.get_order_history = AsyncMock(return_value={
            "retCode": 0,
            "result": {
                "list": [{"orderId": "1", "status": "Filled"}],
                "nextPageCursor": "cursor123"
            }
        })

        # When calling order history endpoint
        response = client.get("/api/v1/order/history")

        # Then response is successful
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True

    def test_get_order_history_endpoint_with_cursor(self, client, mock_rest_client):
        """Test GET /api/v1/order/history with pagination cursor"""
        # Given mock client
        mock_rest_client.get_order_history = AsyncMock(return_value={
            "retCode": 0,
            "result": {"list": []}
        })

        # When calling with cursor
        response = client.get("/api/v1/order/history?cursor=cursor123")

        # Then client is called with cursor
        assert response.status_code == status.HTTP_200_OK
        call_kwargs = mock_rest_client.get_order_history.call_args.kwargs
        assert call_kwargs["cursor"] == "cursor123"


# ============================================================================
# MARKET DATA ENDPOINT TESTS
# ============================================================================

class TestMarketDataEndpoints:
    """Test market data endpoints"""

    def test_get_ticker_endpoint(self, client, mock_rest_client):
        """Test GET /api/v1/market/ticker"""
        # Given mock client returns ticker data
        mock_rest_client.get_ticker = AsyncMock(return_value={
            "retCode": 0,
            "result": {
                "list": [{
                    "symbol": "BTCUSDT",
                    "lastPrice": "50000",
                    "volume24h": "1000"
                }]
            }
        })

        # When calling ticker endpoint
        response = client.get("/api/v1/market/ticker")

        # Then response is successful
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True
        assert "data" in response.json()

    def test_get_ticker_endpoint_with_symbol(self, client, mock_rest_client):
        """Test GET /api/v1/market/ticker with symbol parameter"""
        # Given mock client
        mock_rest_client.get_ticker = AsyncMock(return_value={
            "retCode": 0,
            "result": {"list": []}
        })

        # When calling with symbol
        response = client.get("/api/v1/market/ticker?symbol=ETHUSDT")

        # Then client is called with symbol
        assert response.status_code == status.HTTP_200_OK
        mock_rest_client.get_ticker.assert_called_once_with(
            category="linear",
            symbol="ETHUSDT"
        )

    def test_get_kline_endpoint(self, client, mock_rest_client):
        """Test GET /api/v1/market/kline"""
        # Given mock client returns kline data
        mock_rest_client.get_kline = AsyncMock(return_value={
            "retCode": 0,
            "result": {
                "list": [
                    ["1234567890000", "50000", "51000", "49000", "50500", "100"]
                ]
            }
        })

        # When calling kline endpoint
        response = client.get("/api/v1/market/kline")

        # Then response is successful
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True

    def test_get_kline_endpoint_with_params(self, client, mock_rest_client):
        """Test GET /api/v1/market/kline with parameters"""
        # Given mock client
        mock_rest_client.get_kline = AsyncMock(return_value={
            "retCode": 0,
            "result": {"list": []}
        })

        # When calling with parameters
        response = client.get(
            "/api/v1/market/kline?symbol=ETHUSDT&interval=240&limit=100"
        )

        # Then client is called with correct params
        # The endpoint passes start_time/end_time too (default None when query
        # params are absent), so the assert needs to include them.
        assert response.status_code == status.HTTP_200_OK
        mock_rest_client.get_kline.assert_called_once_with(
            category="linear",
            symbol="ETHUSDT",
            interval="240",
            limit=100,
            start_time=None,
            end_time=None,
        )

    def test_get_orderbook_endpoint(self, client, mock_rest_client):
        """Test GET /api/v1/market/orderbook"""
        # Given mock client returns orderbook data
        mock_rest_client.get_orderbook = AsyncMock(return_value={
            "retCode": 0,
            "result": {
                "b": [["50000", "0.5"], ["49900", "1.0"]],
                "a": [["50100", "0.3"], ["50200", "0.8"]]
            }
        })

        # When calling orderbook endpoint
        response = client.get("/api/v1/market/orderbook")

        # Then response is successful
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True

    def test_get_orderbook_endpoint_with_params(self, client, mock_rest_client):
        """Test GET /api/v1/market/orderbook with parameters"""
        # Given mock client
        mock_rest_client.get_orderbook = AsyncMock(return_value={
            "retCode": 0,
            "result": {"b": [], "a": []}
        })

        # When calling with parameters
        response = client.get(
            "/api/v1/market/orderbook?symbol=ETHUSDT&limit=50"
        )

        # Then client is called with correct params
        assert response.status_code == status.HTTP_200_OK
        mock_rest_client.get_orderbook.assert_called_once_with(
            category="linear",
            symbol="ETHUSDT",
            limit=50
        )

    def test_get_funding_rate_history_endpoint(self, client, mock_rest_client):
        """Test GET /api/v1/market/funding-rate/history"""
        mock_rest_client.get_funding_rate_history = AsyncMock(return_value=[
            {"symbol": "SOLUSDT", "fundingRate": "0.00010000",
             "fundingRateTimestamp": "1672041600000"},
        ])

        response = client.get(
            "/api/v1/market/funding-rate/history?symbol=SOLUSDT&limit=50"
        )

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["success"] is True
        assert len(body["data"]) == 1
        mock_rest_client.get_funding_rate_history.assert_called_once_with(
            category="linear",
            symbol="SOLUSDT",
            start_time=None,
            end_time=None,
            limit=50,
        )

    def test_get_funding_rate_history_endpoint_rejects_spot(self, client, mock_rest_client):
        """Spot has no funding — handler should surface a 400, not propagate."""
        async def raises(*_args, **_kwargs):
            raise ValueError("funding-rate history is perp-only; category='spot' unsupported")

        mock_rest_client.get_funding_rate_history = AsyncMock(side_effect=raises)

        response = client.get(
            "/api/v1/market/funding-rate/history?symbol=SOLUSDT&category=spot"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "perp-only" in response.json()["detail"]

    def test_get_instruments_info_endpoint(self, client, mock_rest_client):
        """Test GET /api/v1/market/instruments-info"""
        mock_rest_client.get_instruments_info = AsyncMock(return_value=[
            {"symbol": "SOLUSDT", "fundingInterval": "480",
             "priceFilter": {"tickSize": "0.001"},
             "lotSizeFilter": {"minOrderQty": "0.1"}}
        ])

        response = client.get(
            "/api/v1/market/instruments-info?category=linear&symbol=SOLUSDT"
        )

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["success"] is True
        assert body["data"][0]["fundingInterval"] == "480"
        mock_rest_client.get_instruments_info.assert_called_once_with(
            category="linear",
            symbol="SOLUSDT",
        )


# ============================================================================
# MONITORING ENDPOINT TESTS
# ============================================================================

class TestMonitoringEndpoints:
    """Test monitoring and circuit breaker endpoints"""

    def test_get_circuit_breaker_status(self, client, mock_rest_client):
        """Test GET /api/v1/status/circuit-breaker"""
        # Given mock client returns circuit breaker status
        mock_rest_client.get_circuit_breaker_status = Mock(return_value={
            "state": "closed",
            "failure_count": 0,
            "last_failure_time": None
        })

        # When calling circuit breaker status endpoint
        response = client.get("/api/v1/status/circuit-breaker")

        # Then response is successful
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True
        assert "data" in response.json()

    def test_reset_circuit_breaker(self, client, mock_rest_client):
        """Test POST /api/v1/status/circuit-breaker/reset"""
        # Given mock client with reset method
        mock_rest_client.reset_circuit_breaker = Mock()

        # When calling circuit breaker reset endpoint
        response = client.post("/api/v1/status/circuit-breaker/reset")

        # Then response is successful
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True
        assert "Circuit breaker reset" in response.json()["message"]

        # And reset method was called
        mock_rest_client.reset_circuit_breaker.assert_called_once()


# ============================================================================
# CORS TESTS
# ============================================================================

class TestCORSConfiguration:
    """Test CORS middleware configuration"""

    def test_cors_headers_present(self, client):
        """Test CORS headers are included in responses"""
        # Given CORS configured origins
        # When making request with Origin header
        response = client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"}
        )

        # Then CORS headers are present
        assert response.status_code == status.HTTP_200_OK
        assert "access-control-allow-origin" in response.headers

    def test_cors_preflight_request(self, client):
        """Test CORS preflight OPTIONS request"""
        # When making preflight request
        response = client.options(
            "/api/v1/account/balance",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET"
            }
        )

        # Then preflight response is successful
        assert response.status_code == status.HTTP_200_OK


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestErrorHandling:
    """Test error handling across endpoints"""

    def test_rate_limit_exception_handling(self, client, mock_rest_client):
        """Test handling of rate limit exceptions"""
        # Given mock client raises rate limit exception
        mock_rest_client.get_ticker = AsyncMock(
            side_effect=RateLimitException("Rate limit exceeded")
        )

        # When calling endpoint
        response = client.get("/api/v1/market/ticker")

        # Then rate limit error is returned
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Rate limit exceeded" in response.json()["detail"]

    def test_validation_exception_handling(self, client, mock_rest_client):
        """Test handling of validation exceptions"""
        # Given mock client raises validation exception
        mock_rest_client.place_order = AsyncMock(
            side_effect=ValidationException("Invalid parameter", field="qty")
        )

        order_data = {
            "symbol": "BTCUSDT",
            "side": "Buy",
            "order_type": "Market",
            "qty": "0.01"
        }

        # When calling endpoint
        response = client.post("/api/v1/order/place", json=order_data)

        # Then validation error is returned
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid parameter" in response.json()["detail"]

    def test_generic_exception_handling(self, client, mock_rest_client):
        """Test handling of generic exceptions"""
        # Given mock client raises generic exception
        from app.exceptions import BybitConnectorException

        mock_rest_client.get_wallet_balance = AsyncMock(
            side_effect=BybitConnectorException("Unexpected error")
        )

        # When calling endpoint
        response = client.get("/api/v1/account/balance")

        # Then error is handled gracefully
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Unexpected error" in response.json()["detail"]

    def test_missing_rest_client_dependency(self):
        """Test endpoints fail gracefully when rest client is missing"""
        # Given test client without rest client
        with TestClient(app) as test_client:
            test_client.app.state.rest_client = None

            # When calling any endpoint requiring rest client
            response = test_client.get("/api/v1/account/balance")

            # Then service unavailable error is returned
            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            assert "not initialized" in response.json()["detail"]


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestEndpointIntegration:
    """Test endpoint integration and workflows"""

    def test_place_and_cancel_order_workflow(self, client, mock_rest_client):
        """Test complete workflow: place order then cancel it"""
        # Given successful place order
        mock_rest_client.place_order = AsyncMock(return_value={
            "retCode": 0,
            "result": {"orderId": "order-123", "orderLinkId": "my-order"}
        })

        order_data = {
            "symbol": "BTCUSDT",
            "side": "Buy",
            "order_type": "Limit",
            "qty": "0.01",
            "price": "50000",
            "order_link_id": "my-order"
        }

        # When placing order
        place_response = client.post("/api/v1/order/place", json=order_data)

        # Then order is placed successfully
        assert place_response.status_code == status.HTTP_200_OK
        order_id = place_response.json()["data"]["result"]["orderId"]

        # Given successful cancel order
        mock_rest_client.cancel_order = AsyncMock(return_value={
            "retCode": 0,
            "result": {"orderId": order_id}
        })

        cancel_data = {
            "symbol": "BTCUSDT",
            "order_id": order_id
        }

        # When canceling order
        cancel_response = client.post("/api/v1/order/cancel", json=cancel_data)

        # Then order is canceled successfully
        assert cancel_response.status_code == status.HTTP_200_OK

    def test_multiple_endpoint_calls(self, client, mock_rest_client):
        """Test making multiple API calls in sequence"""
        # Given mock responses for multiple endpoints
        mock_rest_client.get_ticker = AsyncMock(return_value={
            "retCode": 0,
            "result": {"list": []}
        })
        mock_rest_client.get_wallet_balance = AsyncMock(return_value={
            "retCode": 0,
            "result": {"list": []}
        })
        mock_rest_client.get_positions = AsyncMock(return_value={
            "retCode": 0,
            "result": {"list": []}
        })

        # When calling multiple endpoints
        ticker_resp = client.get("/api/v1/market/ticker")
        balance_resp = client.get("/api/v1/account/balance")
        positions_resp = client.get("/api/v1/account/positions")

        # Then all requests succeed
        assert ticker_resp.status_code == status.HTTP_200_OK
        assert balance_resp.status_code == status.HTTP_200_OK
        assert positions_resp.status_code == status.HTTP_200_OK
