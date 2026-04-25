"""
Coinbase Exchange Adapter - Phase 6: Multi-Exchange Support
Purpose: Adapter implementation for Coinbase Advanced Trade API

This adapter implements the ExchangeInterface for Coinbase exchange,
providing unified access to Coinbase Advanced Trade API.

Features:
- Full ExchangeInterface implementation
- Advanced Trade API (formerly Coinbase Pro)
- JWT-based authentication
- Rate limiting with tiered quotas
- Error mapping to unified exceptions

Note: This adapter uses Coinbase Advanced Trade API (v3), not the legacy
Coinbase Pro API. The Advanced Trade API uses JWT authentication.

Created: 2025-12-11
Author: Backend Developer Agent
"""

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode
import jwt

import httpx
from pydantic import BaseModel

from app.exchanges.base import (
    AccountBalance,
    AssetBalance,
    ExchangeCapabilities,
    ExchangeConfig,
    ExchangeInterface,
    ExchangeName,
    Kline,
    OrderBook,
    OrderBookLevel,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    ProductType,
    Ticker,
    TimeInForce,
    Trade,
    UnifiedOrder,
    UnifiedPosition,
)
from app.exchanges.errors import (
    AuthenticationError,
    ConnectionError,
    DataUnavailableError,
    ExchangeError,
    ExchangeErrorCode,
    InsufficientBalanceError,
    InvalidAPIKeyError,
    InvalidQuantityError,
    InvalidSignatureError,
    InvalidSymbolError,
    OrderAlreadyCancelledError,
    OrderNotFoundError,
    OrderRejectedError,
    PermissionDeniedError,
    RateLimitError,
    TimeoutError,
    ValidationError,
)

# Configure logger
logger = logging.getLogger(__name__)


# ============================================================================
# COINBASE ERROR MAPPING
# ============================================================================

COINBASE_ERROR_MAP = {
    "INVALID_ARGUMENT": ValidationError,
    "FAILED_PRECONDITION": OrderRejectedError,
    "NOT_FOUND": OrderNotFoundError,
    "ALREADY_EXISTS": OrderAlreadyCancelledError,
    "PERMISSION_DENIED": PermissionDeniedError,
    "UNAUTHENTICATED": AuthenticationError,
    "RESOURCE_EXHAUSTED": RateLimitError,
    "INTERNAL": ExchangeError,
    "UNAVAILABLE": ConnectionError,
    "INSUFFICIENT_FUND": InsufficientBalanceError,
    "UNKNOWN_ORDER": OrderNotFoundError,
}


def map_coinbase_error(
    error_type: str,
    error_message: str,
    details: Optional[Dict[str, Any]] = None
) -> ExchangeError:
    """
    Map Coinbase error to unified exception

    Args:
        error_type: Coinbase error type
        error_message: Error message
        details: Additional context

    Returns:
        Appropriate ExchangeError subclass instance
    """
    details = details if details is not None else {}

    exception_class = COINBASE_ERROR_MAP.get(error_type, ExchangeError)

    if exception_class == RateLimitError:
        return RateLimitError(
            exchange="coinbase",
            retry_after=30,
            native_code=error_type,
            native_message=error_message,
            details=details.copy()
        )
    elif exception_class == InsufficientBalanceError:
        return InsufficientBalanceError(
            exchange="coinbase",
            native_code=error_type,
            native_message=error_message,
            details=details.copy()
        )
    elif exception_class == OrderNotFoundError:
        return OrderNotFoundError(
            exchange="coinbase",
            native_code=error_type,
            native_message=error_message,
            details=details.copy()
        )
    elif issubclass(exception_class, ExchangeError):
        try:
            return exception_class(
                exchange="coinbase",
                native_code=error_type,
                native_message=error_message,
                details=details.copy()
            )
        except TypeError:
            pass

    return ExchangeError(
        message=error_message or f"Coinbase error: {error_type}",
        error_code=ExchangeErrorCode.UNKNOWN_ERROR,
        exchange="coinbase",
        native_code=error_type,
        native_message=error_message,
        details=details.copy()
    )


# ============================================================================
# COINBASE RATE LIMITER
# ============================================================================

class CoinbaseRateLimiter:
    """
    Rate limiter for Coinbase Advanced Trade API

    Coinbase has different rate limits:
    - Public endpoints: 10 requests/second
    - Private endpoints: 15 requests/second
    - Order endpoints: 30 requests/second

    Attributes:
        requests_per_second: Maximum requests per second
    """

    def __init__(self, requests_per_second: float = 10.0):
        """
        Initialize rate limiter

        Args:
            requests_per_second: Maximum requests per second
        """
        self.requests_per_second = requests_per_second
        self.tokens = requests_per_second
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        """Acquire a rate limit token"""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(
                self.requests_per_second,
                self.tokens + elapsed * self.requests_per_second
            )
            self.last_update = now

            if self.tokens >= 1:
                self.tokens -= 1
                return 0.0
            else:
                wait_time = (1 - self.tokens) / self.requests_per_second
                return wait_time

    async def wait_and_acquire(self) -> None:
        """Wait for and acquire a token"""
        wait_time = await self.acquire()
        if wait_time > 0:
            await asyncio.sleep(wait_time)


# ============================================================================
# COINBASE ADAPTER CONFIGURATION
# ============================================================================

class CoinbaseAdapterConfig(BaseModel):
    """
    Configuration specific to Coinbase adapter

    Attributes:
        portfolio_id: Portfolio UUID (for advanced trading)
    """
    portfolio_id: Optional[str] = None


# ============================================================================
# COINBASE EXCHANGE ADAPTER
# ============================================================================

class CoinbaseExchangeAdapter(ExchangeInterface):
    """
    Coinbase exchange adapter implementing ExchangeInterface

    This adapter provides direct API access to Coinbase Advanced Trade,
    supporting spot trading with advanced order types.

    Features:
    - Advanced Trade API v3
    - JWT authentication
    - Full order type support
    - Real-time market data
    - Error mapping to unified exceptions

    Authentication:
    Coinbase Advanced Trade uses JWT tokens for authentication.
    You need:
    - API Key Name (as api_key)
    - API Private Key (as api_secret, in PEM format)

    Usage:
        config = ExchangeConfig(
            exchange=ExchangeName.COINBASE,
            api_key="organizations/..../apiKeys/...",
            api_secret="-----BEGIN EC PRIVATE KEY-----...",
            testnet=False  # Coinbase sandbox requires different setup
        )
        adapter = CoinbaseExchangeAdapter(config)
        await adapter.initialize()

        # Place order
        order = await adapter.place_order(unified_order)
    """

    # Coinbase API endpoints
    BASE_URL = "https://api.coinbase.com"
    SANDBOX_URL = "https://api-public.sandbox.exchange.coinbase.com"

    def __init__(
        self,
        config: ExchangeConfig,
        portfolio_id: Optional[str] = None
    ):
        """
        Initialize Coinbase adapter

        Args:
            config: Exchange configuration
            portfolio_id: Optional portfolio UUID
        """
        super().__init__(config)

        # Coinbase-specific config
        self._portfolio_id = portfolio_id
        self._base_url = self.SANDBOX_URL if config.testnet else self.BASE_URL

        # Override with custom URL if provided
        if config.base_url:
            self._base_url = config.base_url.rstrip("/")

        # HTTP client
        self._client: Optional[httpx.AsyncClient] = None

        # Rate limiter
        self._rate_limiter = CoinbaseRateLimiter(requests_per_second=10.0)

        # Set Coinbase capabilities
        self._capabilities = ExchangeCapabilities(
            # Trading products
            spot_trading=True,
            perpetual_trading=False,  # Coinbase Advanced doesn't have perpetuals
            margin_trading=False,
            options_trading=False,

            # Order types
            market_orders=True,
            limit_orders=True,
            stop_orders=True,
            trailing_stop=True,
            post_only=True,
            reduce_only=False,

            # WebSocket
            websocket_public=True,
            websocket_private=True,
            orderbook_depth=50,

            # Rate limits
            rate_limit_per_second=10,
            order_rate_limit=30,

            # Trading
            max_leverage=1,  # No leverage on spot
            min_order_size_usd=1.0,

            # Environment
            testnet_available=True,
            sandbox_mode=True,
        )

        logger.info(
            f"Created Coinbase adapter (testnet={config.testnet})"
        )

    # ========================================================================
    # JWT AUTHENTICATION
    # ========================================================================

    def _generate_jwt(self, method: str, path: str) -> str:
        """
        Generate JWT token for authentication

        Args:
            method: HTTP method
            path: Request path

        Returns:
            JWT token string
        """
        # Parse the key name and extract the key ID
        key_name = self._config.api_key

        # Build JWT payload
        uri = f"{method.upper()} {self._base_url.replace('https://', '')}{path}"

        payload = {
            "sub": key_name,
            "iss": "coinbase-cloud",
            "nbf": int(time.time()),
            "exp": int(time.time()) + 120,  # 2 minute expiry
            "aud": ["retail_rest_api_proxy"],
        }

        # Add nonce for uniqueness
        headers = {
            "kid": key_name,
            "nonce": secrets.token_hex(16),
        }

        try:
            # Sign with private key
            token = jwt.encode(
                payload,
                self._config.api_secret,
                algorithm="ES256",
                headers=headers
            )
            return token
        except Exception as e:
            logger.error(f"JWT generation failed: {e}")
            raise AuthenticationError(
                message=f"Failed to generate JWT: {e}",
                exchange="coinbase"
            )

    def _get_headers(self, method: str, path: str) -> Dict[str, str]:
        """
        Get request headers with authentication

        Args:
            method: HTTP method
            path: Request path

        Returns:
            Headers dict
        """
        token = self._generate_jwt(method, path)

        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    # ========================================================================
    # LIFECYCLE METHODS
    # ========================================================================

    async def initialize(self) -> None:
        """
        Initialize connection to Coinbase

        Raises:
            ConnectionError: If connection fails
            AuthenticationError: If credentials are invalid
        """
        logger.info("Initializing Coinbase adapter...")

        # Create HTTP client
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=5.0,
                read=self._config.timeout,
                write=10.0,
                pool=10.0
            )
        )

        # Verify connectivity
        try:
            health_ok = await self.health_check()
            if not health_ok:
                raise ConnectionError(
                    message="Coinbase connectivity check failed",
                    exchange="coinbase"
                )
        except httpx.HTTPError as e:
            raise ConnectionError(
                message=f"Failed to connect to Coinbase: {e}",
                exchange="coinbase"
            )

        # Validate credentials
        try:
            await self.get_balance()
        except AuthenticationError:
            raise
        except Exception as e:
            logger.warning(f"Balance check during init failed: {e}")

        self._initialized = True
        logger.info("Coinbase adapter initialized successfully")

    async def close(self) -> None:
        """Close HTTP client connection"""
        if self._client:
            await self._client.aclose()
            self._client = None
        self._initialized = False
        logger.info("Coinbase adapter closed")

    async def health_check(self) -> bool:
        """
        Check Coinbase connectivity

        Returns:
            True if exchange is reachable
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/api/v3/brokerage/time"
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False

    # ========================================================================
    # HTTP REQUEST HELPER
    # ========================================================================

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        authenticated: bool = True
    ) -> Dict[str, Any]:
        """
        Make HTTP request to Coinbase API

        Args:
            method: HTTP method
            path: API endpoint path
            params: Query parameters
            json_data: JSON body data
            authenticated: Whether to add authentication

        Returns:
            Response data

        Raises:
            ExchangeError: On request failure
        """
        if not self._client:
            raise ConnectionError(
                message="Adapter not initialized",
                exchange="coinbase"
            )

        await self._rate_limiter.wait_and_acquire()

        url = f"{self._base_url}{path}"

        headers = {}
        if authenticated:
            headers = self._get_headers(method, path)

        try:
            if method.upper() == "GET":
                response = await self._client.get(
                    url,
                    params=params,
                    headers=headers
                )
            elif method.upper() == "POST":
                response = await self._client.post(
                    url,
                    params=params,
                    json=json_data,
                    headers=headers
                )
            elif method.upper() == "DELETE":
                response = await self._client.delete(
                    url,
                    params=params,
                    headers=headers
                )
            else:
                response = await self._client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    headers=headers
                )

            # Parse response
            if response.text:
                data = response.json()
            else:
                data = {}

            # Check for errors
            if response.status_code >= 400:
                error_type = data.get("error", "UNKNOWN")
                error_msg = data.get("message", data.get("error_details", "Unknown error"))
                raise map_coinbase_error(error_type, error_msg, data)

            return data

        except httpx.TimeoutException as e:
            raise TimeoutError(message=f"Request timed out: {e}", exchange="coinbase")
        except ExchangeError:
            raise
        except Exception as e:
            raise ConnectionError(message=f"Request failed: {e}", exchange="coinbase")

    # ========================================================================
    # ACCOUNT METHODS
    # ========================================================================

    async def get_balance(
        self,
        asset: Optional[str] = None
    ) -> AccountBalance:
        """Get account balance"""
        params = {"limit": 250}
        if asset:
            # Coinbase requires full asset UUID or currency
            params["asset_filter"] = asset.upper()

        result = await self._request(
            "GET",
            "/api/v3/brokerage/accounts",
            params=params
        )

        return self._parse_balance(result)

    def _parse_balance(self, data: Dict[str, Any]) -> AccountBalance:
        """Parse Coinbase balance response"""
        assets = []
        total_equity = Decimal("0")
        available_balance = Decimal("0")

        for account in data.get("accounts", []):
            currency = account.get("currency", "")
            available = Decimal(str(account.get("available_balance", {}).get("value", "0")))
            hold = Decimal(str(account.get("hold", {}).get("value", "0")))

            if available + hold > 0:
                assets.append(AssetBalance(
                    asset=currency,
                    free=available,
                    locked=hold
                ))

            total_equity += available + hold
            available_balance += available

        return AccountBalance(
            exchange=ExchangeName.COINBASE,
            account_type="SPOT",
            total_equity=total_equity,
            available_balance=available_balance,
            used_margin=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            assets=assets,
            updated_at=datetime.now(timezone.utc)
        )

    async def get_positions(
        self,
        symbol: Optional[str] = None,
        product_type: Optional[ProductType] = None
    ) -> List[UnifiedPosition]:
        """
        Get open positions

        Note: Coinbase Advanced Trade is spot-only, no positions.
        """
        return []

    # ========================================================================
    # TRADING METHODS
    # ========================================================================

    async def place_order(self, order: UnifiedOrder) -> UnifiedOrder:
        """Place an order on Coinbase"""
        payload = self._order_to_coinbase(order)

        result = await self._request(
            "POST",
            "/api/v3/brokerage/orders",
            json_data=payload
        )

        # Update order with result
        order.exchange_order_id = result.get("order_id")
        order.status = self._map_order_status(
            result.get("success_response", {}).get("order_id"),
            result.get("error_response")
        )
        order.updated_at = datetime.now(timezone.utc)

        logger.info(
            f"Order placed: {order.symbol} {order.side.value} {order.quantity} "
            f"@ {order.price or 'MARKET'} (id={order.exchange_order_id})"
        )

        return order

    def _order_to_coinbase(self, order: UnifiedOrder) -> Dict[str, Any]:
        """Convert unified order to Coinbase format"""
        # Convert symbol format (BTCUSDT -> BTC-USD)
        product_id = self._to_coinbase_symbol(order.symbol)

        # Generate client order ID if not provided
        client_order_id = order.client_order_id or f"order_{int(time.time() * 1000)}"

        payload = {
            "client_order_id": client_order_id,
            "product_id": product_id,
            "side": order.side.value.upper(),
        }

        # Configure order based on type
        if order.order_type == OrderType.MARKET:
            if order.side == OrderSide.BUY:
                # Market buy uses quote currency (USD)
                payload["order_configuration"] = {
                    "market_market_ioc": {
                        "quote_size": str(order.quantity * (order.price or Decimal("1")))
                    }
                }
            else:
                # Market sell uses base currency
                payload["order_configuration"] = {
                    "market_market_ioc": {
                        "base_size": str(order.quantity)
                    }
                }
        elif order.order_type == OrderType.LIMIT:
            config_key = "limit_limit_gtc"
            if order.time_in_force == TimeInForce.IOC:
                config_key = "limit_limit_ioc"
            elif order.time_in_force == TimeInForce.FOK:
                config_key = "limit_limit_fok"
            elif order.post_only:
                config_key = "limit_limit_gtc"  # Post-only handled by flag

            payload["order_configuration"] = {
                config_key: {
                    "base_size": str(order.quantity),
                    "limit_price": str(order.price),
                    "post_only": order.post_only
                }
            }
        elif order.order_type == OrderType.STOP_LIMIT:
            payload["order_configuration"] = {
                "stop_limit_stop_limit_gtc": {
                    "base_size": str(order.quantity),
                    "limit_price": str(order.price),
                    "stop_price": str(order.stop_price),
                    "stop_direction": "STOP_DIRECTION_STOP_DOWN" if order.side == OrderSide.SELL else "STOP_DIRECTION_STOP_UP"
                }
            }

        return payload

    def _to_coinbase_symbol(self, symbol: str) -> str:
        """Convert symbol to Coinbase format (BTC-USD)"""
        # Handle common formats
        symbol = symbol.upper().replace("/", "")

        # Common conversions
        if symbol.endswith("USDT"):
            base = symbol[:-4]
            return f"{base}-USD"  # Coinbase uses USD not USDT
        elif symbol.endswith("USD"):
            base = symbol[:-3]
            return f"{base}-USD"

        # Already in correct format
        if "-" in symbol:
            return symbol

        # Try to split (assume last 3-4 chars are quote)
        if len(symbol) > 4:
            return f"{symbol[:-4]}-{symbol[-4:]}"

        return symbol

    def _from_coinbase_symbol(self, product_id: str) -> str:
        """Convert Coinbase symbol to standard format"""
        return product_id.replace("-", "")

    def _map_order_status(
        self,
        success_order_id: Optional[str],
        error_response: Optional[Dict]
    ) -> OrderStatus:
        """Map Coinbase order result to status"""
        if success_order_id:
            return OrderStatus.NEW
        elif error_response:
            return OrderStatus.REJECTED
        return OrderStatus.PENDING

    def _parse_order_status(self, status: str) -> OrderStatus:
        """Map Coinbase status string to OrderStatus"""
        status_map = {
            "PENDING": OrderStatus.PENDING,
            "OPEN": OrderStatus.NEW,
            "FILLED": OrderStatus.FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "EXPIRED": OrderStatus.EXPIRED,
            "FAILED": OrderStatus.REJECTED,
        }
        return status_map.get(status, OrderStatus.NEW)

    async def cancel_order(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None
    ) -> UnifiedOrder:
        """Cancel an order"""
        if not order_id and not client_order_id:
            raise ValidationError(
                message="Either order_id or client_order_id required",
                exchange="coinbase"
            )

        # Coinbase requires array of order IDs
        order_ids = []
        if order_id:
            order_ids.append(order_id)

        result = await self._request(
            "POST",
            "/api/v3/brokerage/orders/batch_cancel",
            json_data={"order_ids": order_ids}
        )

        # Return cancelled order
        return UnifiedOrder(
            exchange=ExchangeName.COINBASE,
            exchange_order_id=order_id,
            client_order_id=client_order_id,
            symbol=symbol,
            product_type=ProductType.SPOT,
            side=OrderSide.BUY,  # Placeholder
            order_type=OrderType.MARKET,  # Placeholder
            quantity=Decimal("0"),
            status=OrderStatus.CANCELLED,
            updated_at=datetime.now(timezone.utc)
        )

    async def get_order_status(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None
    ) -> UnifiedOrder:
        """Get order status"""
        if not order_id:
            raise ValidationError(
                message="order_id is required",
                exchange="coinbase"
            )

        result = await self._request(
            "GET",
            f"/api/v3/brokerage/orders/historical/{order_id}"
        )

        order_data = result.get("order", {})
        return self._parse_order(order_data)

    def _parse_order(self, data: Dict[str, Any]) -> UnifiedOrder:
        """Parse Coinbase order response"""
        # Determine order type from configuration
        order_config = data.get("order_configuration", {})
        order_type = OrderType.MARKET

        price = None
        stop_price = None

        if "market_market_ioc" in order_config:
            order_type = OrderType.MARKET
        elif "limit_limit_gtc" in order_config:
            order_type = OrderType.LIMIT
            config = order_config["limit_limit_gtc"]
            price = Decimal(str(config.get("limit_price", "0")))
        elif "stop_limit_stop_limit_gtc" in order_config:
            order_type = OrderType.STOP_LIMIT
            config = order_config["stop_limit_stop_limit_gtc"]
            price = Decimal(str(config.get("limit_price", "0")))
            stop_price = Decimal(str(config.get("stop_price", "0")))

        # Parse timestamps
        created_time = data.get("created_time", "")
        try:
            created_at = datetime.fromisoformat(created_time.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            created_at = datetime.now(timezone.utc)

        return UnifiedOrder(
            exchange=ExchangeName.COINBASE,
            exchange_order_id=data.get("order_id"),
            client_order_id=data.get("client_order_id"),
            symbol=self._from_coinbase_symbol(data.get("product_id", "")),
            product_type=ProductType.SPOT,
            side=OrderSide.BUY if data.get("side") == "BUY" else OrderSide.SELL,
            order_type=order_type,
            quantity=Decimal(str(data.get("filled_size", "0"))) or Decimal(str(data.get("order_configuration", {}).get("limit_limit_gtc", {}).get("base_size", "0"))),
            price=price,
            stop_price=stop_price,
            time_in_force=TimeInForce.GTC,
            status=self._parse_order_status(data.get("status", "OPEN")),
            filled_quantity=Decimal(str(data.get("filled_size", "0"))),
            filled_price=Decimal(str(data.get("average_filled_price", "0"))) if data.get("average_filled_price") else None,
            commission=Decimal(str(data.get("total_fees", "0"))),
            created_at=created_at,
            updated_at=datetime.now(timezone.utc)
        )

    async def get_open_orders(
        self,
        symbol: Optional[str] = None,
        product_type: Optional[ProductType] = None
    ) -> List[UnifiedOrder]:
        """Get all open orders"""
        params = {"order_status": "OPEN", "limit": 100}
        if symbol:
            params["product_id"] = self._to_coinbase_symbol(symbol)

        result = await self._request(
            "GET",
            "/api/v3/brokerage/orders/historical/batch",
            params=params
        )

        orders = []
        for order_data in result.get("orders", []):
            orders.append(self._parse_order(order_data))

        return orders

    # ========================================================================
    # MARKET DATA METHODS
    # ========================================================================

    async def get_ticker(self, symbol: str) -> Ticker:
        """Get ticker data"""
        product_id = self._to_coinbase_symbol(symbol)

        result = await self._request(
            "GET",
            f"/api/v3/brokerage/products/{product_id}",
            authenticated=False
        )

        return Ticker(
            exchange=ExchangeName.COINBASE,
            symbol=self._from_coinbase_symbol(product_id),
            last_price=Decimal(str(result.get("price", "0"))),
            bid_price=Decimal(str(result.get("quote_min_size", "0"))),  # Approximate
            ask_price=Decimal(str(result.get("quote_max_size", "0"))),  # Approximate
            high_24h=Decimal(str(result.get("price_percentage_change_24h", "0"))) if result.get("price_percentage_change_24h") else None,
            volume_24h=Decimal(str(result.get("volume_24h", "0"))) if result.get("volume_24h") else None,
            change_24h=float(result.get("price_percentage_change_24h", "0")) if result.get("price_percentage_change_24h") else None,
            timestamp=datetime.now(timezone.utc)
        )

    async def get_orderbook(
        self,
        symbol: str,
        depth: int = 25
    ) -> OrderBook:
        """Get orderbook"""
        product_id = self._to_coinbase_symbol(symbol)

        # Get product book
        result = await self._request(
            "GET",
            f"/api/v3/brokerage/product_book",
            params={"product_id": product_id, "limit": min(depth, 50)},
            authenticated=False
        )

        pricebook = result.get("pricebook", {})

        bids = [
            OrderBookLevel(
                price=Decimal(str(level.get("price", "0"))),
                quantity=Decimal(str(level.get("size", "0")))
            )
            for level in pricebook.get("bids", [])
        ]

        asks = [
            OrderBookLevel(
                price=Decimal(str(level.get("price", "0"))),
                quantity=Decimal(str(level.get("size", "0")))
            )
            for level in pricebook.get("asks", [])
        ]

        return OrderBook(
            exchange=ExchangeName.COINBASE,
            symbol=self._from_coinbase_symbol(product_id),
            bids=bids,
            asks=asks,
            timestamp=datetime.now(timezone.utc)
        )

    async def get_trades(
        self,
        symbol: str,
        limit: int = 100
    ) -> List[Trade]:
        """Get recent trades"""
        product_id = self._to_coinbase_symbol(symbol)

        result = await self._request(
            "GET",
            f"/api/v3/brokerage/products/{product_id}/ticker",
            authenticated=False
        )

        # Coinbase ticker endpoint returns limited trade info
        trades = []
        for trade_data in result.get("trades", []):
            try:
                timestamp = datetime.fromisoformat(
                    trade_data.get("time", "").replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                timestamp = datetime.now(timezone.utc)

            trades.append(Trade(
                exchange=ExchangeName.COINBASE,
                symbol=self._from_coinbase_symbol(product_id),
                trade_id=str(trade_data.get("trade_id", "")),
                price=Decimal(str(trade_data.get("price", "0"))),
                quantity=Decimal(str(trade_data.get("size", "0"))),
                side=OrderSide.BUY if trade_data.get("side") == "BUY" else OrderSide.SELL,
                timestamp=timestamp
            ))

        return trades[:limit]

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 100,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Kline]:
        """Get kline/candlestick data"""
        product_id = self._to_coinbase_symbol(symbol)

        # Map interval to Coinbase granularity (seconds)
        granularity_map = {
            "1": "ONE_MINUTE", "1m": "ONE_MINUTE",
            "5": "FIVE_MINUTE", "5m": "FIVE_MINUTE",
            "15": "FIFTEEN_MINUTE", "15m": "FIFTEEN_MINUTE",
            "30": "THIRTY_MINUTE", "30m": "THIRTY_MINUTE",
            "60": "ONE_HOUR", "1h": "ONE_HOUR",
            "120": "TWO_HOUR", "2h": "TWO_HOUR",
            "360": "SIX_HOUR", "6h": "SIX_HOUR",
            "1440": "ONE_DAY", "1d": "ONE_DAY", "D": "ONE_DAY",
        }
        granularity = granularity_map.get(interval, "ONE_HOUR")

        params = {
            "granularity": granularity,
            "limit": min(limit, 300)
        }

        if start_time:
            params["start"] = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        if end_time:
            params["end"] = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        result = await self._request(
            "GET",
            f"/api/v3/brokerage/products/{product_id}/candles",
            params=params,
            authenticated=False
        )

        klines = []
        for candle in result.get("candles", []):
            try:
                # Coinbase returns unix timestamp
                open_timestamp = int(candle.get("start", 0))
                open_time = datetime.fromtimestamp(open_timestamp, tz=timezone.utc)

                # Calculate close time based on granularity
                granularity_seconds = {
                    "ONE_MINUTE": 60, "FIVE_MINUTE": 300, "FIFTEEN_MINUTE": 900,
                    "THIRTY_MINUTE": 1800, "ONE_HOUR": 3600, "TWO_HOUR": 7200,
                    "SIX_HOUR": 21600, "ONE_DAY": 86400
                }
                interval_seconds = granularity_seconds.get(granularity, 3600)
                close_time = datetime.fromtimestamp(
                    open_timestamp + interval_seconds,
                    tz=timezone.utc
                )

                klines.append(Kline(
                    exchange=ExchangeName.COINBASE,
                    symbol=self._from_coinbase_symbol(product_id),
                    interval=interval,
                    open_time=open_time,
                    open=Decimal(str(candle.get("open", "0"))),
                    high=Decimal(str(candle.get("high", "0"))),
                    low=Decimal(str(candle.get("low", "0"))),
                    close=Decimal(str(candle.get("close", "0"))),
                    volume=Decimal(str(candle.get("volume", "0"))),
                    close_time=close_time
                ))
            except (ValueError, TypeError, KeyError) as e:
                logger.warning(f"Failed to parse candle: {e}")
                continue

        return klines


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_coinbase_adapter(
    api_key: str,
    api_secret: str,
    testnet: bool = False,
    portfolio_id: Optional[str] = None
) -> CoinbaseExchangeAdapter:
    """
    Factory function to create Coinbase adapter

    Args:
        api_key: Coinbase API key name
        api_secret: Coinbase API private key (PEM format)
        testnet: Use sandbox environment
        portfolio_id: Optional portfolio UUID

    Returns:
        Configured CoinbaseExchangeAdapter
    """
    config = ExchangeConfig(
        exchange=ExchangeName.COINBASE,
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet
    )

    return CoinbaseExchangeAdapter(config, portfolio_id=portfolio_id)


__all__ = [
    "CoinbaseExchangeAdapter",
    "CoinbaseAdapterConfig",
    "CoinbaseRateLimiter",
    "create_coinbase_adapter",
    "map_coinbase_error",
]
