"""
Comprehensive Tests for Bybit REST Client
Purpose: Achieve >80% test coverage for bybit_rest_client.py
Coverage Target: All REST endpoints, error handling, circuit breaker integration
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import httpx
from app.bybit_rest_client import BybitRestClient, create_rest_client
from app.config import Settings
from app.exceptions import (
    BybitAPIException,
    RateLimitException,
    ValidationException,
    AuthenticationException
)


# ============================================================================
# CLIENT INITIALIZATION TESTS
# ============================================================================

class TestBybitRestClientInitialization:
    """Test client initialization with various configurations"""

    def test_client_initialization_testnet(self):
        """Test client initializes with testnet configuration"""
        client = BybitRestClient(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True
        )

        assert client.testnet is True
        assert client.base_url == "https://api-testnet.bybit.com"
        assert client.authenticator is not None
        assert client.circuit_breaker is not None

    def test_client_initialization_mainnet(self):
        """Test client initializes with mainnet configuration"""
        client = BybitRestClient(
            api_key="test_key",
            api_secret="test_secret",
            testnet=False
        )

        assert client.testnet is False
        assert client.base_url == "https://api.bybit.com"

    def test_client_initialization_custom_base_url(self):
        """Test client initializes with custom base URL"""
        custom_url = "https://custom-api.example.com"
        client = BybitRestClient(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True,
            base_url=custom_url
        )

        assert client.base_url == custom_url

    def test_client_initialization_custom_timeout(self):
        """Test client initializes with custom timeout"""
        client = BybitRestClient(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True,
            timeout=60.0
        )

        # Timeout is set in the httpx client configuration
        assert client.client is not None


# ============================================================================
# CORE REQUEST METHOD TESTS
# ============================================================================

class TestCoreRequestMethods:
    """Test internal request handling methods"""

    @pytest.mark.asyncio
    async def test_make_request_success(self):
        """Test successful HTTP request"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        # Mock the httpx client
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {"data": "success"}
        }

        with patch.object(client.client, 'request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            response = await client._make_request(
                method="GET",
                endpoint="/v5/market/tickers",
                params={"category": "linear"},
                json_data=None,
                headers={}
            )

            assert response.status_code == 200
            mock_request.assert_called_once()

        await client.close()

    @pytest.mark.asyncio
    async def test_handle_response_success(self):
        """Test response handling for successful API response"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {"balance": "10000"}
        }

        result = client._handle_response(mock_response)

        assert result == {"balance": "10000"}
        await client.close()

    @pytest.mark.asyncio
    async def test_handle_response_api_error(self):
        """Test response handling for API error"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        mock_response = Mock(spec=httpx.Response)
        # Bybit returns retCode!=0 inside HTTP 200 for application-level errors
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "retCode": 10001,
            "retMsg": "Invalid parameter"
        }

        with pytest.raises(AuthenticationException):
            client._handle_response(mock_response)

        await client.close()

    @pytest.mark.asyncio
    async def test_handle_response_rate_limit(self):
        """Test response handling for rate limit error"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "retCode": 10006,
            "retMsg": "Rate limit exceeded"
        }

        with pytest.raises(RateLimitException) as exc_info:
            client._handle_response(mock_response)

        assert exc_info.value.retry_after == 60
        await client.close()

    @pytest.mark.asyncio
    async def test_handle_response_http_429_rate_limit(self):
        """An HTTP 429 maps to RateLimitException regardless of body"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 429
        mock_response.json.return_value = {}

        with pytest.raises(RateLimitException):
            client._handle_response(mock_response)

        await client.close()

    @pytest.mark.asyncio
    async def test_handle_response_http_500_surfaces_error(self):
        """A 5xx without retCode does NOT silently look like success"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 503
        mock_response.json.return_value = {"message": "service unavailable"}

        with pytest.raises(BybitAPIException):
            client._handle_response(mock_response)

        await client.close()

    @pytest.mark.asyncio
    async def test_handle_response_invalid_json(self):
        """Test response handling for invalid JSON response"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")

        with pytest.raises(BybitAPIException) as exc_info:
            client._handle_response(mock_response)

        assert "Invalid JSON response" in str(exc_info.value)
        await client.close()


# ============================================================================
# ACCOUNT ENDPOINT TESTS
# ============================================================================

class TestAccountEndpoints:
    """Test account-related endpoints"""

    @pytest.mark.asyncio
    async def test_get_wallet_balance_unified(self):
        """Test getting wallet balance for unified account"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        mock_response = {
            "accountType": "UNIFIED",
            "totalEquity": "10000.00",
            "coin": [
                {"coin": "USDT", "walletBalance": "10000.00", "availableToWithdraw": "10000.00"}
            ]
        }

        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await client.get_wallet_balance(account_type="UNIFIED")

            assert result["accountType"] == "UNIFIED"
            assert result["totalEquity"] == "10000.00"
            mock_request.assert_called_once_with(
                "GET",
                "/v5/account/wallet-balance",
                params={"accountType": "UNIFIED"}
            )

        await client.close()

    @pytest.mark.asyncio
    async def test_get_wallet_balance_with_coin_filter(self):
        """Test getting wallet balance for specific coin"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"coin": "BTC"}

            await client.get_wallet_balance(account_type="UNIFIED", coin="BTC")

            mock_request.assert_called_once_with(
                "GET",
                "/v5/account/wallet-balance",
                params={"accountType": "UNIFIED", "coin": "BTC"}
            )

        await client.close()

    @pytest.mark.asyncio
    async def test_get_positions_all_symbols(self):
        """Test getting positions for all symbols"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        mock_response = {
            "list": [
                {"symbol": "BTCUSDT", "size": "0.1", "side": "Buy"},
                {"symbol": "ETHUSDT", "size": "1.0", "side": "Sell"}
            ]
        }

        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await client.get_positions(category="linear")

            assert len(result) == 2
            assert result[0]["symbol"] == "BTCUSDT"
            mock_request.assert_called_once()

        await client.close()

    @pytest.mark.asyncio
    async def test_get_positions_specific_symbol(self):
        """Test getting positions for specific symbol"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"list": []}

            await client.get_positions(category="linear", symbol="BTCUSDT")

            mock_request.assert_called_once_with(
                "GET",
                "/v5/position/list",
                params={"category": "linear", "symbol": "BTCUSDT"}
            )

        await client.close()


# ============================================================================
# TRADING ENDPOINT TESTS
# ============================================================================

class TestTradingEndpoints:
    """Test trading-related endpoints"""

    @pytest.mark.asyncio
    async def test_place_order_market(self):
        """Test placing market order"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        mock_response = {
            "orderId": "test-order-123",
            "orderLinkId": "custom-id"
        }

        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await client.place_order(
                category="linear",
                symbol="BTCUSDT",
                side="Buy",
                order_type="Market",
                qty="0.01"
            )

            assert result["orderId"] == "test-order-123"
            mock_request.assert_called_once()

            # Verify payload structure
            call_args = mock_request.call_args
            assert call_args[0][0] == "POST"
            assert call_args[0][1] == "/v5/order/create"
            assert call_args[1]["data"]["symbol"] == "BTCUSDT"
            assert call_args[1]["data"]["orderType"] == "Market"

        await client.close()

    @pytest.mark.asyncio
    async def test_place_order_limit_with_price(self):
        """Test placing limit order with price"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"orderId": "limit-order-456"}

            await client.place_order(
                category="linear",
                symbol="ETHUSDT",
                side="Sell",
                order_type="Limit",
                qty="1.0",
                price="3000.00",
                time_in_force="PostOnly"
            )

            call_args = mock_request.call_args
            payload = call_args[1]["data"]
            assert payload["price"] == "3000.00"
            assert payload["timeInForce"] == "PostOnly"

        await client.close()

    @pytest.mark.asyncio
    async def test_place_order_missing_required_params(self):
        """Test placing order with missing required parameters"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        with pytest.raises(ValidationException):
            await client.place_order(
                category="linear",
                symbol="",  # Empty symbol
                side="Buy",
                order_type="Market",
                qty="0.01"
            )

        await client.close()

    @pytest.mark.asyncio
    async def test_place_order_limit_without_price(self):
        """Test placing limit order without price raises error"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        with pytest.raises(ValidationException) as exc_info:
            await client.place_order(
                category="linear",
                symbol="BTCUSDT",
                side="Buy",
                order_type="Limit",
                qty="0.01"
                # Missing price
            )

        assert "Price required for limit orders" in str(exc_info.value)
        await client.close()

    @pytest.mark.asyncio
    async def test_place_order_with_optional_params(self):
        """Test placing order with optional parameters"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"orderId": "test"}

            await client.place_order(
                category="linear",
                symbol="BTCUSDT",
                side="Buy",
                order_type="Market",
                qty="0.01",
                reduce_only=True,
                close_on_trigger=True,
                order_link_id="custom-123"
            )

            payload = mock_request.call_args[1]["data"]
            assert payload["reduceOnly"] is True
            assert payload["closeOnTrigger"] is True
            assert payload["orderLinkId"] == "custom-123"

        await client.close()

    @pytest.mark.asyncio
    async def test_cancel_order_with_order_id(self):
        """Test cancelling order with order ID"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"orderId": "cancelled-123"}

            result = await client.cancel_order(
                category="linear",
                symbol="BTCUSDT",
                order_id="test-order-123"
            )

            assert result["orderId"] == "cancelled-123"
            payload = mock_request.call_args[1]["data"]
            assert payload["orderId"] == "test-order-123"

        await client.close()

    @pytest.mark.asyncio
    async def test_cancel_order_with_order_link_id(self):
        """Test cancelling order with custom order link ID"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {}

            await client.cancel_order(
                category="linear",
                symbol="BTCUSDT",
                order_link_id="custom-order-id"
            )

            payload = mock_request.call_args[1]["data"]
            assert payload["orderLinkId"] == "custom-order-id"

        await client.close()

    @pytest.mark.asyncio
    async def test_cancel_order_without_identifiers(self):
        """Test cancelling order without order ID or link ID raises error"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        with pytest.raises(ValidationException):
            await client.cancel_order(
                category="linear",
                symbol="BTCUSDT"
                # Missing both order_id and order_link_id
            )

        await client.close()

    @pytest.mark.asyncio
    async def test_get_open_orders(self):
        """Test getting open orders"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        mock_response = {
            "list": [
                {"orderId": "order-1", "status": "New"},
                {"orderId": "order-2", "status": "PartiallyFilled"}
            ]
        }

        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await client.get_open_orders(
                category="linear",
                symbol="BTCUSDT",
                limit=50
            )

            assert len(result) == 2
            assert result[0]["orderId"] == "order-1"

        await client.close()

    @pytest.mark.asyncio
    async def test_get_open_orders_limit_enforcement(self):
        """Test that order limit is enforced to API maximum"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"list": []}

            # Try to request more than API max (50)
            await client.get_open_orders(category="linear", limit=100)

            # Should be capped at 50
            params = mock_request.call_args[1]["params"]
            assert params["limit"] == 50

        await client.close()

    @pytest.mark.asyncio
    async def test_get_order_history(self):
        """Test getting order history"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        mock_response = {
            "list": [{"orderId": "hist-1"}],
            "nextPageCursor": "cursor-123"
        }

        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await client.get_order_history(
                category="linear",
                symbol="BTCUSDT",
                limit=20,
                cursor="prev-cursor"
            )

            assert result["nextPageCursor"] == "cursor-123"
            params = mock_request.call_args[1]["params"]
            assert params["cursor"] == "prev-cursor"

        await client.close()


# ============================================================================
# MARKET DATA ENDPOINT TESTS
# ============================================================================

class TestMarketDataEndpoints:
    """Test market data endpoints (public, no auth required)"""

    @pytest.mark.asyncio
    async def test_get_ticker_all_symbols(self):
        """Test getting ticker for all symbols"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        mock_response = {
            "list": [
                {"symbol": "BTCUSDT", "lastPrice": "50000"},
                {"symbol": "ETHUSDT", "lastPrice": "3000"}
            ]
        }

        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await client.get_ticker(category="linear")

            assert len(result["list"]) == 2
            # Verify auth_required=False for public endpoint
            assert mock_request.call_args[1]["auth_required"] is False

        await client.close()

    @pytest.mark.asyncio
    async def test_get_ticker_specific_symbol(self):
        """Test getting ticker for specific symbol"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {}

            await client.get_ticker(category="linear", symbol="BTCUSDT")

            params = mock_request.call_args[1]["params"]
            assert params["symbol"] == "BTCUSDT"

        await client.close()

    @pytest.mark.asyncio
    async def test_get_kline(self):
        """Test getting kline/candlestick data"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        mock_response = {
            "list": [
                ["1640000000", "50000", "51000", "49000", "50500", "100", "5000000"]
            ]
        }

        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await client.get_kline(
                category="linear",
                symbol="BTCUSDT",
                interval="15",
                limit=200,
                start_time=1640000000000,
                end_time=1640100000000
            )

            assert len(result) == 1
            params = mock_request.call_args[1]["params"]
            assert params["interval"] == "15"
            assert params["start"] == 1640000000000
            assert params["end"] == 1640100000000

        await client.close()

    @pytest.mark.asyncio
    async def test_get_kline_limit_enforcement(self):
        """Test kline limit enforcement to API maximum"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"list": []}

            # Request more than API max (1000)
            await client.get_kline(
                category="linear",
                symbol="BTCUSDT",
                interval="1",
                limit=5000
            )

            # Should be capped at 1000
            params = mock_request.call_args[1]["params"]
            assert params["limit"] == 1000

        await client.close()

    @pytest.mark.asyncio
    async def test_get_orderbook(self):
        """Test getting orderbook depth"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        mock_response = {
            "bids": [["50000", "0.1"], ["49999", "0.2"]],
            "asks": [["50001", "0.1"], ["50002", "0.2"]]
        }

        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await client.get_orderbook(
                category="linear",
                symbol="BTCUSDT",
                limit=25
            )

            assert len(result["bids"]) == 2
            assert len(result["asks"]) == 2

        await client.close()


# ============================================================================
# UTILITY METHOD TESTS
# ============================================================================

class TestUtilityMethods:
    """Test utility and helper methods"""

    @pytest.mark.asyncio
    async def test_close_client(self):
        """Test client cleanup"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        with patch.object(client.client, 'aclose', new_callable=AsyncMock) as mock_close:
            await client.close()
            mock_close.assert_called_once()

    def test_get_circuit_breaker_status(self):
        """Test getting circuit breaker status"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        status = client.get_circuit_breaker_status()

        assert "state" in status
        assert "failure_count" in status
        assert "success_count" in status

    def test_reset_circuit_breaker(self):
        """Test resetting circuit breaker"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        # Simulate some failures
        client.circuit_breaker.failure_count = 3

        client.reset_circuit_breaker()

        status = client.get_circuit_breaker_status()
        assert status["failure_count"] == 0
        assert status["state"] == "closed"


# ============================================================================
# FACTORY FUNCTION TESTS
# ============================================================================

class TestFactoryFunctions:
    """Test factory functions for client creation"""

    def test_create_rest_client_from_settings(self):
        """Test creating client from settings"""
        settings = Settings(
            bybit_api_key="factory_test_key",
            bybit_api_secret="factory_test_secret",
            bybit_testnet=True
        )

        client = create_rest_client(settings)

        assert client is not None
        assert client.testnet is True
        assert client.base_url == "https://api-testnet.bybit.com"


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestErrorHandling:
    """Test error handling scenarios"""

    @pytest.mark.asyncio
    async def test_request_with_circuit_breaker_open(self):
        """Test request fails when circuit breaker is open"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        # Force circuit breaker open
        from app.circuit_breaker import CircuitState
        client.circuit_breaker.state = CircuitState.OPEN
        client.circuit_breaker.failure_count = 10

        from app.exceptions import CircuitBreakerOpenException

        with pytest.raises(CircuitBreakerOpenException):
            await client.get_ticker(category="linear")

        await client.close()

    @pytest.mark.asyncio
    async def test_request_with_connect_error_retries_then_raises(self):
        """Network ConnectError is retried and ultimately surfaces as itself"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        with patch.object(client.circuit_breaker, 'call_async', new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = httpx.ConnectError("Connection failed")

            with pytest.raises(httpx.ConnectError):
                await client._request("GET", "/test", params={})

            # tenacity should have retried (default 3 attempts)
            assert mock_call.call_count == 3

        await client.close()

    @pytest.mark.asyncio
    async def test_request_with_generic_http_error_wrapped(self):
        """A non-network httpx.HTTPError is still wrapped in BybitAPIException"""
        client = BybitRestClient("test_key", "test_secret", testnet=True)

        with patch.object(client.circuit_breaker, 'call_async', new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = httpx.HTTPError("generic http error")

            with pytest.raises(BybitAPIException) as exc_info:
                await client._request("GET", "/test", params={})

            assert "HTTP request failed" in str(exc_info.value)

        await client.close()
