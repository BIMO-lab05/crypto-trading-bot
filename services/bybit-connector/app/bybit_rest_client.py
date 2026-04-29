"""
Bybit Connector Service - REST API Client
Purpose: Handle REST API calls to Bybit exchange
"""

import httpx
import json
from typing import Dict, Any, Optional, List
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import logging

from app.auth import BybitAuthenticator
from app.config import Settings
from app.exceptions import (
    BybitAPIException,
    RateLimitException,
    get_exception_for_bybit_error,
    ValidationException
)
from app.circuit_breaker import CircuitBreaker

# Configure logger
logger = logging.getLogger(__name__)


class BybitRestClient:
    """
    Bybit REST API client with authentication, retry logic, and circuit breaker
    
    Supports all major API endpoints:
    - Account: balance, positions
    - Trading: place order, cancel order, modify order
    - Market Data: tickers, klines, orderbook
    """
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = True,
        base_url: Optional[str] = None,
        timeout: float = 30.0
    ):
        """
        Initialize Bybit REST client
        
        Args:
            api_key: Bybit API key
            api_secret: Bybit API secret  
            testnet: Use testnet (True) or mainnet (False)
            base_url: Custom base URL (overrides testnet setting)
            timeout: Request timeout in seconds
        """
        # Authentication
        self.authenticator = BybitAuthenticator(api_key, api_secret)
        
        # API configuration
        self.testnet = testnet
        if base_url:
            self.base_url = base_url
        else:
            self.base_url = (
                "https://api-testnet.bybit.com"
                if testnet
                else "https://api.bybit.com"
            )
        
        # Fixed: HTTP client with separate connect and read timeouts (Critical Issue #5)
        # This prevents hung requests during network issues
        # Connect timeout: Time to establish connection
        # Read timeout: Time to receive response after connection established
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(
                connect=5.0,  # 5 seconds to establish connection
                read=timeout,  # 30 seconds to read response (for slow API responses)
                write=10.0,  # 10 seconds to send request data
                pool=10.0  # 10 seconds to get connection from pool
            ),
            headers={"Content-Type": "application/json"}
        )
        
        # Circuit breaker for resilience
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60,
            expected_exception=Exception
        )
        
        logger.info(
            f"Initialized Bybit REST client (testnet={testnet}, base_url={self.base_url})"
        )
    
    async def close(self):
        """Close HTTP client connection"""
        await self.client.aclose()
        logger.info("Closed Bybit REST client")
    
    # ========================================================================
    # CORE REQUEST METHODS
    # ========================================================================
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(RateLimitException)
    )
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        auth_required: bool = True
    ) -> Dict[str, Any]:
        """
        Make authenticated HTTP request to Bybit API
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            data: Request body data
            auth_required: Whether authentication is required
        
        Returns:
            API response data
        
        Raises:
            BybitAPIException: If API returns error
            RateLimitException: If rate limit exceeded
        """
        # Build headers with authentication
        headers = {}
        if auth_required:
            # Serialize body data to JSON string for signature if present
            body_str = json.dumps(data) if data else None
            headers = self.authenticator.get_headers(params=params, body=body_str)

        # Make request through circuit breaker
        try:
            response = await self.circuit_breaker.call_async(
                self._make_request,
                method=method,
                endpoint=endpoint,
                params=params,
                json_data=data,
                headers=headers
            )
            
            return self._handle_response(response)
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error during request to {endpoint}: {e}")
            raise BybitAPIException(
                message="HTTP request failed",
                ret_code=-1,
                ret_msg=str(e)
            )
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]],
        json_data: Optional[Dict[str, Any]],
        headers: Dict[str, str]
    ) -> httpx.Response:
        """
        Actually make the HTTP request
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            json_data: JSON body data
            headers: Request headers
        
        Returns:
            HTTP response
        """
        response = await self.client.request(
            method=method,
            url=endpoint,
            params=params,
            json=json_data,
            headers=headers
        )
        
        return response
    
    def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        """
        Handle API response and errors
        
        Args:
            response: HTTP response
        
        Returns:
            Parsed response data
        
        Raises:
            BybitAPIException: If API returns error
            RateLimitException: If rate limited
        """
        # Parse JSON response
        try:
            data = response.json()
        except Exception as e:
            logger.error(f"Failed to parse response JSON: {e}")
            raise BybitAPIException(
                message="Invalid JSON response",
                ret_code=-1,
                ret_msg=str(e)
            )
        
        # Check return code
        ret_code = data.get("retCode", 0)
        ret_msg = data.get("retMsg", "")
        
        # Success
        if ret_code == 0:
            return data.get("result", {})
        
        # Error - raise appropriate exception
        logger.error(f"API error: code={ret_code}, msg={ret_msg}")
        
        # Handle rate limiting specially
        if ret_code == 10006:
            raise RateLimitException(retry_after=60)
        
        # Raise mapped exception
        raise get_exception_for_bybit_error(ret_code, ret_msg)
    
    # ========================================================================
    # ACCOUNT ENDPOINTS
    # ========================================================================
    
    async def get_wallet_balance(self, account_type: str = "UNIFIED", coin: Optional[str] = None) -> Dict[str, Any]:
        """
        Get wallet balance
        
        Args:
            account_type: Account type (UNIFIED, CONTRACT, SPOT)
            coin: Specific coin to query (optional)
        
        Returns:
            Balance information
        
        Example response:
            {
                "accountType": "UNIFIED",
                "totalEquity": "10000.00",
                "coin": [
                    {"coin": "USDT", "walletBalance": "10000.00", "availableToWithdraw": "10000.00"}
                ]
            }
        """
        params = {"accountType": account_type}
        if coin:
            params["coin"] = coin
        
        logger.info(f"Getting wallet balance (account_type={account_type}, coin={coin})")
        result = await self._request("GET", "/v5/account/wallet-balance", params=params)
        return result
    
    async def get_positions(self, category: str = "linear", symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get position information
        
        Args:
            category: Product category (linear, inverse, option)
            symbol: Trading pair symbol (optional)
        
        Returns:
            List of positions
        """
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        
        logger.info(f"Getting positions (category={category}, symbol={symbol})")
        result = await self._request("GET", "/v5/position/list", params=params)
        return result.get("list", [])
    
    # ========================================================================
    # TRADING ENDPOINTS
    # ========================================================================
    
    async def place_order(
        self,
        category: str,
        symbol: str,
        side: str,
        order_type: str,
        qty: str,
        price: Optional[str] = None,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
        close_on_trigger: bool = False,
        order_link_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Place a new order
        
        Args:
            category: Product category (linear, inverse, spot, option)
            symbol: Trading pair (e.g., "BTCUSDT")
            side: Buy or Sell
            order_type: Market, Limit
            qty: Order quantity
            price: Order price (required for Limit orders)
            time_in_force: GTC, IOC, FOK, PostOnly
            reduce_only: Reduce position only
            close_on_trigger: Close on trigger
            order_link_id: Custom order ID
        
        Returns:
            Order information with orderId
        
        Raises:
            ValidationException: If parameters are invalid
        """
        # Validate required fields
        if not symbol or not side or not order_type or not qty:
            raise ValidationException("Missing required order parameters")
        
        # Validate limit order has price
        if order_type.lower() == "limit" and not price:
            raise ValidationException("Price required for limit orders", field="price")
        
        # Build order payload
        payload = {
            "category": category,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": qty,
            "timeInForce": time_in_force
        }
        
        # Add optional parameters
        if price:
            payload["price"] = price
        if reduce_only:
            payload["reduceOnly"] = reduce_only
        if close_on_trigger:
            payload["closeOnTrigger"] = close_on_trigger
        if order_link_id:
            payload["orderLinkId"] = order_link_id
        
        logger.info(f"Placing order: {symbol} {side} {qty} @ {price} ({order_type})")
        result = await self._request("POST", "/v5/order/create", data=payload)
        return result
    
    async def cancel_order(
        self,
        category: str,
        symbol: str,
        order_id: Optional[str] = None,
        order_link_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancel an order
        
        Args:
            category: Product category
            symbol: Trading pair
            order_id: Bybit order ID
            order_link_id: Custom order ID
        
        Returns:
            Cancellation result
        
        Raises:
            ValidationException: If neither order_id nor order_link_id provided
        """
        if not order_id and not order_link_id:
            raise ValidationException("Either order_id or order_link_id required")
        
        payload = {
            "category": category,
            "symbol": symbol
        }
        
        if order_id:
            payload["orderId"] = order_id
        if order_link_id:
            payload["orderLinkId"] = order_link_id
        
        logger.info(f"Cancelling order: {order_id or order_link_id}")
        result = await self._request("POST", "/v5/order/cancel", data=payload)
        return result
    
    async def get_open_orders(
        self,
        category: str = "linear",
        symbol: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get open orders
        
        Args:
            category: Product category
            symbol: Trading pair (optional)
            limit: Number of orders to return (max 50)
        
        Returns:
            List of open orders
        """
        params = {
            "category": category,
            "limit": min(limit, 50)  # API max is 50
        }
        
        if symbol:
            params["symbol"] = symbol
        
        logger.info(f"Getting open orders (symbol={symbol}, limit={limit})")
        result = await self._request("GET", "/v5/order/realtime", params=params)
        return result.get("list", [])
    
    async def get_order_history(
        self,
        category: str = "linear",
        symbol: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get order history
        
        Args:
            category: Product category
            symbol: Trading pair (optional)
            limit: Number of orders (max 50)
            cursor: Pagination cursor
        
        Returns:
            Dict with "list" of orders and "nextPageCursor"
        """
        params = {
            "category": category,
            "limit": min(limit, 50)
        }
        
        if symbol:
            params["symbol"] = symbol
        if cursor:
            params["cursor"] = cursor
        
        logger.info(f"Getting order history (symbol={symbol}, limit={limit})")
        result = await self._request("GET", "/v5/order/history", params=params)
        return result
    
    # ========================================================================
    # MARKET DATA ENDPOINTS (PUBLIC)
    # ========================================================================
    
    async def get_ticker(self, category: str = "linear", symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Get latest ticker data
        
        Args:
            category: Product category
            symbol: Trading pair (optional, returns all if not provided)
        
        Returns:
            Ticker data
        """
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        
        result = await self._request("GET", "/v5/market/tickers", params=params, auth_required=False)
        return result
    
    async def get_kline(
        self,
        category: str,
        symbol: str,
        interval: str,
        limit: int = 200,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None
    ) -> List[List[str]]:
        """
        Get kline/candlestick data
        
        Args:
            category: Product category
            symbol: Trading pair
            interval: Kline interval (1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M)
            limit: Number of klines (max 1000)
            start_time: Start timestamp (ms)
            end_time: End timestamp (ms)
        
        Returns:
            List of kline data [timestamp, open, high, low, close, volume, turnover]
        """
        params = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit, 1000)
        }
        
        if start_time:
            params["start"] = start_time
        if end_time:
            params["end"] = end_time
        
        result = await self._request("GET", "/v5/market/kline", params=params, auth_required=False)
        return result.get("list", [])
    
    async def get_orderbook(self, category: str, symbol: str, limit: int = 25) -> Dict[str, Any]:
        """
        Get orderbook depth

        Args:
            category: Product category
            symbol: Trading pair
            limit: Depth limit (1, 25, 50, 100, 200)

        Returns:
            Orderbook with bids and asks
        """
        params = {
            "category": category,
            "symbol": symbol,
            "limit": limit
        }

        result = await self._request("GET", "/v5/market/orderbook", params=params, auth_required=False)
        return result

    async def get_funding_rate_history(
        self,
        category: str,
        symbol: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 200,
    ) -> List[Dict[str, str]]:
        """
        Get historical funding rates for a perpetual contract.

        Args:
            category: linear or inverse (perpetuals only — not applicable to spot)
            symbol: Trading pair (e.g. SOLUSDT)
            start_time: Start timestamp (ms). Bybit returns rates with
                fundingRateTimestamp >= start_time.
            end_time: End timestamp (ms).
            limit: 1-200 (Bybit hard limit), default 200.

        Returns:
            List of {symbol, fundingRate, fundingRateTimestamp} dicts ordered
            newest-first per Bybit convention. Each fundingRate is a stringified
            decimal (e.g. "0.00010000" = 0.01% per settlement interval).
        """
        if category not in ("linear", "inverse"):
            raise ValueError(
                f"funding-rate history is perp-only; category={category!r} unsupported"
            )
        params: Dict[str, Any] = {
            "category": category,
            "symbol": symbol,
            "limit": min(max(limit, 1), 200),
        }
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        result = await self._request(
            "GET", "/v5/market/funding/history", params=params, auth_required=False
        )
        return result.get("list", [])

    async def get_instruments_info(
        self,
        category: str,
        symbol: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get instrument metadata (lot size, tick size, funding interval, etc.).

        For perp instruments, the response includes ``fundingInterval`` in
        minutes (e.g. 480 for 8h). Some symbols use 1h or 4h funding —
        T2.3 funding-rate awareness needs the per-symbol interval, not a
        hardcoded 8h.

        Args:
            category: spot, linear, inverse, or option.
            symbol: Restrict to a single symbol (optional).

        Returns:
            List of instrument dicts. For perps, key fields include:
              symbol, fundingInterval (str minutes), priceFilter.tickSize,
              lotSizeFilter.minOrderQty, lotSizeFilter.maxOrderQty.
        """
        params: Dict[str, Any] = {"category": category}
        if symbol:
            params["symbol"] = symbol
        result = await self._request(
            "GET", "/v5/market/instruments-info", params=params, auth_required=False
        )
        return result.get("list", [])

    # ========================================================================
    # UTILITY METHODS
    # ========================================================================
    
    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """Get circuit breaker current state"""
        return self.circuit_breaker.get_state()
    
    def reset_circuit_breaker(self):
        """Manually reset circuit breaker"""
        self.circuit_breaker.reset()
        logger.info("Circuit breaker reset")


# Convenience function to create client from settings
def create_rest_client(settings: Settings) -> BybitRestClient:
    """
    Create BybitRestClient from application settings
    
    Args:
        settings: Application settings
    
    Returns:
        Configured BybitRestClient
    """
    return BybitRestClient(
        api_key=settings.bybit_api_key,
        api_secret=settings.bybit_api_secret,
        testnet=settings.bybit_testnet
    )
