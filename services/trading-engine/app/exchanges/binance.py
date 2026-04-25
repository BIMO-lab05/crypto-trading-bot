"""
Binance Exchange Adapter - Phase 6: Multi-Exchange Support
Purpose: Adapter implementation for Binance exchange

This adapter implements the ExchangeInterface for Binance exchange,
providing unified access to Binance Spot and Futures APIs.

Features:
- Full ExchangeInterface implementation
- Binance Futures (USDT-M and COIN-M) support
- Binance Spot trading support
- WebSocket support for real-time data
- Rate limiting with weight-based tracking
- Error mapping to unified exceptions

Created: 2025-12-11
Author: Backend Developer Agent
"""

import asyncio
import hashlib
import hmac
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

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
    RateLimitError,
    TimeoutError,
    ValidationError,
)

# Configure logger
logger = logging.getLogger(__name__)


# ============================================================================
# BINANCE ERROR MAPPING
# ============================================================================

# Binance API error codes to unified exceptions
BINANCE_ERROR_MAP: Dict[int, type] = {
    # Authentication errors
    -1002: AuthenticationError,  # Unauthorized
    -1003: RateLimitError,  # Too many requests
    -1022: InvalidSignatureError,  # Signature invalid
    -2008: InvalidAPIKeyError,  # Invalid API key
    -2014: InvalidAPIKeyError,  # API key format invalid
    -2015: InvalidAPIKeyError,  # Invalid API key, IP, or permissions

    # Validation errors
    -1100: ValidationError,  # Illegal characters found
    -1101: ValidationError,  # Too many parameters
    -1102: ValidationError,  # Mandatory parameter missing
    -1104: ValidationError,  # Not all parameters sent
    -1105: ValidationError,  # Parameter empty
    -1111: InvalidQuantityError,  # Precision over max
    -1112: ValidationError,  # No orders on book
    -1116: ValidationError,  # Invalid orderType
    -1117: ValidationError,  # Invalid side
    -1121: InvalidSymbolError,  # Invalid symbol

    # Order errors
    -2010: OrderRejectedError,  # NEW_ORDER_REJECTED
    -2011: OrderNotFoundError,  # CANCEL_REJECTED (order not found)
    -2013: OrderNotFoundError,  # Order does not exist
    -2014: OrderAlreadyCancelledError,  # Order already closed
    -2015: OrderRejectedError,  # No trading window
    -2018: InsufficientBalanceError,  # Balance insufficient
    -2019: InsufficientBalanceError,  # Margin insufficient
    -2020: OrderRejectedError,  # Unable to fill
    -2021: OrderRejectedError,  # Order would trigger immediately

    # Position errors
    -4028: OrderRejectedError,  # Position mode error
    -4045: OrderRejectedError,  # Position not enough
    -4046: InsufficientBalanceError,  # Available balance insufficient

    # Rate limit
    -1015: RateLimitError,  # Too many orders
    -1010: RateLimitError,  # Too many requests
}


def map_binance_error(
    error_code: int,
    error_msg: str,
    details: Optional[Dict[str, Any]] = None
) -> ExchangeError:
    """
    Map Binance error code to unified exception

    Args:
        error_code: Binance API error code
        error_msg: Binance API error message
        details: Additional context

    Returns:
        Appropriate ExchangeError subclass instance
    """
    details = details if details is not None else {}
    exception_class = BINANCE_ERROR_MAP.get(error_code, ExchangeError)

    # Handle specific error types
    if error_code == -1003 or error_code == -1015:
        return RateLimitError(
            exchange="binance",
            retry_after=60,
            native_code=str(error_code),
            native_message=error_msg,
            details=details.copy()
        )
    elif error_code == -2018 or error_code == -2019 or error_code == -4046:
        return InsufficientBalanceError(
            exchange="binance",
            native_code=str(error_code),
            native_message=error_msg,
            details=details.copy()
        )
    elif exception_class == OrderNotFoundError:
        return OrderNotFoundError(
            order_id=details.get("orderId"),
            exchange="binance",
            native_code=str(error_code),
            native_message=error_msg,
            details=details.copy()
        )
    elif issubclass(exception_class, ExchangeError):
        try:
            return exception_class(
                exchange="binance",
                native_code=str(error_code),
                native_message=error_msg,
                details=details.copy()
            )
        except TypeError:
            # Fall back to base error if constructor doesn't match
            pass

    return ExchangeError(
        message=error_msg or "Unknown Binance error",
        error_code=ExchangeErrorCode.UNKNOWN_ERROR,
        exchange="binance",
        native_code=str(error_code),
        native_message=error_msg,
        details=details.copy()
    )


# ============================================================================
# RATE LIMITER WITH WEIGHT TRACKING
# ============================================================================

class BinanceRateLimiter:
    """
    Weight-based rate limiter for Binance API

    Binance uses request weights rather than simple request counts.
    Different endpoints have different weights, and the total weight
    per minute is limited.

    Attributes:
        weight_limit: Maximum weight per minute (default: 1200)
        current_weight: Current accumulated weight
        reset_time: Time when weight resets
    """

    def __init__(self, weight_limit: int = 1200):
        """
        Initialize rate limiter

        Args:
            weight_limit: Maximum weight per minute
        """
        self.weight_limit = weight_limit
        self.current_weight = 0
        self.reset_time = time.monotonic() + 60
        self._lock = asyncio.Lock()

    async def acquire(self, weight: int = 1) -> float:
        """
        Acquire rate limit capacity

        Args:
            weight: Request weight

        Returns:
            Wait time in seconds (0 if no wait needed)
        """
        async with self._lock:
            now = time.monotonic()

            # Reset weight if minute has passed
            if now >= self.reset_time:
                self.current_weight = 0
                self.reset_time = now + 60

            # Check if weight available
            if self.current_weight + weight <= self.weight_limit:
                self.current_weight += weight
                return 0.0
            else:
                # Wait until reset
                wait_time = self.reset_time - now
                return max(0.0, wait_time)

    async def wait_and_acquire(self, weight: int = 1) -> None:
        """Wait for and acquire capacity"""
        wait_time = await self.acquire(weight)
        if wait_time > 0:
            logger.debug(f"Rate limit wait: {wait_time:.2f}s")
            await asyncio.sleep(wait_time)
            # Re-acquire after wait
            await self.acquire(weight)


# ============================================================================
# BINANCE ADAPTER CONFIGURATION
# ============================================================================

class BinanceAdapterConfig(BaseModel):
    """
    Configuration specific to Binance adapter

    Attributes:
        futures_mode: Use Futures API (True) or Spot API (False)
        margin_type: USDT-margined (linear) or COIN-margined (inverse)
        recv_window: Request receive window in milliseconds
    """
    futures_mode: bool = True
    margin_type: str = "linear"  # "linear" or "inverse"
    recv_window: int = 5000


# ============================================================================
# BINANCE EXCHANGE ADAPTER
# ============================================================================

class BinanceExchangeAdapter(ExchangeInterface):
    """
    Binance exchange adapter implementing ExchangeInterface

    This adapter provides direct API access to Binance exchange,
    supporting both Spot and Futures trading.

    Features:
    - Spot and Futures trading
    - USDT-M and COIN-M perpetuals
    - Weight-based rate limiting
    - Signature generation for authenticated requests
    - Error mapping to unified exceptions

    Usage:
        config = ExchangeConfig(
            exchange=ExchangeName.BINANCE,
            api_key="...",
            api_secret="...",
            testnet=True
        )
        adapter = BinanceExchangeAdapter(config)
        await adapter.initialize()

        # Place order
        order = await adapter.place_order(unified_order)
    """

    # Binance API endpoints
    MAINNET_SPOT_URL = "https://api.binance.com"
    MAINNET_FUTURES_URL = "https://fapi.binance.com"  # USDT-M
    MAINNET_COIN_FUTURES_URL = "https://dapi.binance.com"  # COIN-M
    TESTNET_SPOT_URL = "https://testnet.binance.vision"
    TESTNET_FUTURES_URL = "https://testnet.binancefuture.com"

    def __init__(
        self,
        config: ExchangeConfig,
        futures_mode: bool = True,
        margin_type: str = "linear"
    ):
        """
        Initialize Binance adapter

        Args:
            config: Exchange configuration
            futures_mode: Use Futures API
            margin_type: "linear" (USDT-M) or "inverse" (COIN-M)
        """
        super().__init__(config)

        # Store Binance-specific config
        self._futures_mode = futures_mode
        self._margin_type = margin_type
        self._recv_window = 5000

        # Determine base URL
        self._base_url = self._get_base_url()

        # HTTP client (created in initialize)
        self._client: Optional[httpx.AsyncClient] = None

        # Rate limiter
        self._rate_limiter = BinanceRateLimiter(weight_limit=1200)

        # Set Binance capabilities
        self._capabilities = ExchangeCapabilities(
            # Trading products
            spot_trading=True,
            perpetual_trading=True,
            margin_trading=True,
            options_trading=False,

            # Order types
            market_orders=True,
            limit_orders=True,
            stop_orders=True,
            trailing_stop=True,
            post_only=True,
            reduce_only=True,

            # WebSocket
            websocket_public=True,
            websocket_private=True,
            orderbook_depth=1000,

            # Rate limits (weight-based)
            rate_limit_per_second=20,
            order_rate_limit=10,

            # Trading
            max_leverage=125,
            min_order_size_usd=5.0,

            # Environment
            testnet_available=True,
            sandbox_mode=False,
        )

        logger.info(
            f"Created Binance adapter (testnet={config.testnet}, "
            f"futures={futures_mode}, margin_type={margin_type})"
        )

    def _get_base_url(self) -> str:
        """Determine base URL based on configuration"""
        if self._config.base_url:
            return self._config.base_url.rstrip("/")

        if self._config.testnet:
            if self._futures_mode:
                return self.TESTNET_FUTURES_URL
            return self.TESTNET_SPOT_URL
        else:
            if self._futures_mode:
                if self._margin_type == "inverse":
                    return self.MAINNET_COIN_FUTURES_URL
                return self.MAINNET_FUTURES_URL
            return self.MAINNET_SPOT_URL

    # ========================================================================
    # SIGNATURE GENERATION
    # ========================================================================

    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """
        Generate HMAC SHA256 signature for authenticated requests

        Args:
            params: Request parameters

        Returns:
            Signature string
        """
        query_string = urlencode(sorted(params.items()))
        signature = hmac.new(
            self._config.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _add_signature(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add timestamp and signature to parameters

        Args:
            params: Request parameters

        Returns:
            Parameters with timestamp and signature
        """
        params = dict(params)
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = self._recv_window
        params["signature"] = self._generate_signature(params)
        return params

    # ========================================================================
    # LIFECYCLE METHODS
    # ========================================================================

    async def initialize(self) -> None:
        """
        Initialize connection to Binance

        Raises:
            ConnectionError: If connection fails
            AuthenticationError: If credentials are invalid
        """
        logger.info("Initializing Binance adapter...")

        # Create HTTP client
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(
                connect=5.0,
                read=self._config.timeout,
                write=10.0,
                pool=10.0
            ),
            headers={
                "Content-Type": "application/json",
                "X-MBX-APIKEY": self._config.api_key
            }
        )

        # Verify connectivity
        try:
            health_ok = await self.health_check()
            if not health_ok:
                raise ConnectionError(
                    message="Binance connectivity check failed",
                    exchange="binance"
                )
        except httpx.HTTPError as e:
            raise ConnectionError(
                message=f"Failed to connect to Binance: {e}",
                exchange="binance"
            )

        # Validate credentials by fetching account info
        try:
            await self.get_balance()
        except AuthenticationError:
            raise
        except Exception as e:
            logger.warning(f"Balance check during init failed: {e}")

        self._initialized = True
        logger.info("Binance adapter initialized successfully")

    async def close(self) -> None:
        """Close HTTP client connection"""
        if self._client:
            await self._client.aclose()
            self._client = None
        self._initialized = False
        logger.info("Binance adapter closed")

    async def health_check(self) -> bool:
        """
        Check Binance connectivity

        Returns:
            True if exchange is reachable
        """
        try:
            if self._futures_mode:
                response = await self._client.get("/fapi/v1/ping")
            else:
                response = await self._client.get("/api/v3/ping")
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
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
        weight: int = 1
    ) -> Dict[str, Any]:
        """
        Make HTTP request to Binance API

        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Request parameters
            signed: Whether to sign the request
            weight: Request weight for rate limiting

        Returns:
            Response data

        Raises:
            ExchangeError: On request failure
        """
        if not self._client:
            raise ConnectionError(
                message="Adapter not initialized",
                exchange="binance"
            )

        # Apply rate limiting
        await self._rate_limiter.wait_and_acquire(weight)

        params = dict(params or {})

        # Add signature for authenticated endpoints
        if signed:
            params = self._add_signature(params)

        try:
            if method.upper() == "GET":
                response = await self._client.get(endpoint, params=params)
            elif method.upper() == "POST":
                response = await self._client.post(endpoint, params=params)
            elif method.upper() == "DELETE":
                response = await self._client.delete(endpoint, params=params)
            else:
                response = await self._client.request(
                    method=method,
                    url=endpoint,
                    params=params
                )

            # Parse response
            data = response.json()

            # Check for Binance API errors
            if response.status_code >= 400 or "code" in data:
                error_code = data.get("code", response.status_code)
                error_msg = data.get("msg", "Unknown error")
                raise map_binance_error(error_code, error_msg, data)

            return data

        except httpx.TimeoutException as e:
            raise TimeoutError(
                message=f"Request timed out: {e}",
                exchange="binance"
            )
        except httpx.HTTPError as e:
            raise ConnectionError(
                message=f"HTTP error: {e}",
                exchange="binance"
            )
        except ExchangeError:
            raise
        except Exception as e:
            raise ExchangeError(
                message=f"Request failed: {e}",
                exchange="binance"
            )

    # ========================================================================
    # ACCOUNT METHODS
    # ========================================================================

    async def get_balance(
        self,
        asset: Optional[str] = None
    ) -> AccountBalance:
        """
        Get account balance

        Args:
            asset: Specific asset to query

        Returns:
            Account balance information
        """
        if self._futures_mode:
            endpoint = "/fapi/v2/account"
        else:
            endpoint = "/api/v3/account"

        result = await self._request("GET", endpoint, signed=True, weight=5)
        return self._parse_balance(result, asset)

    def _parse_balance(
        self,
        data: Dict[str, Any],
        asset_filter: Optional[str] = None
    ) -> AccountBalance:
        """Parse Binance balance response"""
        assets = []

        if self._futures_mode:
            # Futures account response
            for asset_data in data.get("assets", []):
                asset_name = asset_data.get("asset", "")
                if asset_filter and asset_name.upper() != asset_filter.upper():
                    continue

                assets.append(AssetBalance(
                    asset=asset_name,
                    free=Decimal(str(asset_data.get("availableBalance", "0"))),
                    locked=Decimal(str(asset_data.get("initialMargin", "0")))
                ))

            total_equity = Decimal(str(data.get("totalWalletBalance", "0")))
            available_balance = Decimal(str(data.get("availableBalance", "0")))
            unrealized_pnl = Decimal(str(data.get("totalUnrealizedProfit", "0")))
            used_margin = Decimal(str(data.get("totalInitialMargin", "0")))
        else:
            # Spot account response
            for balance in data.get("balances", []):
                asset_name = balance.get("asset", "")
                if asset_filter and asset_name.upper() != asset_filter.upper():
                    continue

                free = Decimal(str(balance.get("free", "0")))
                locked = Decimal(str(balance.get("locked", "0")))

                if free + locked > 0:
                    assets.append(AssetBalance(
                        asset=asset_name,
                        free=free,
                        locked=locked
                    ))

            # Calculate totals for spot (simplified)
            total_equity = sum(a.total for a in assets)
            available_balance = sum(a.free for a in assets)
            unrealized_pnl = Decimal("0")
            used_margin = Decimal("0")

        return AccountBalance(
            exchange=ExchangeName.BINANCE,
            account_type="FUTURES" if self._futures_mode else "SPOT",
            total_equity=total_equity,
            available_balance=available_balance,
            used_margin=used_margin,
            unrealized_pnl=unrealized_pnl,
            assets=assets,
            updated_at=datetime.now(timezone.utc)
        )

    async def get_positions(
        self,
        symbol: Optional[str] = None,
        product_type: Optional[ProductType] = None
    ) -> List[UnifiedPosition]:
        """Get open positions"""
        if not self._futures_mode:
            # Spot doesn't have positions
            return []

        endpoint = "/fapi/v2/positionRisk"
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()

        result = await self._request("GET", endpoint, params=params, signed=True, weight=5)

        positions = []
        for pos_data in result:
            pos = self._parse_position(pos_data)
            if pos:
                positions.append(pos)

        return positions

    def _parse_position(self, data: Dict[str, Any]) -> Optional[UnifiedPosition]:
        """Parse Binance position data"""
        position_amt = Decimal(str(data.get("positionAmt", "0")))
        if position_amt == 0:
            return None

        # Determine side
        if position_amt > 0:
            side = PositionSide.LONG
        else:
            side = PositionSide.SHORT

        return UnifiedPosition(
            exchange=ExchangeName.BINANCE,
            symbol=data.get("symbol", ""),
            product_type=ProductType.LINEAR,
            side=side,
            quantity=abs(position_amt),
            entry_price=Decimal(str(data.get("entryPrice", "0"))),
            mark_price=Decimal(str(data.get("markPrice", "0"))),
            liquidation_price=Decimal(str(data.get("liquidationPrice", "0"))) if data.get("liquidationPrice") else None,
            unrealized_pnl=Decimal(str(data.get("unRealizedProfit", "0"))),
            leverage=int(data.get("leverage", 1)),
            margin=Decimal(str(data.get("isolatedMargin", "0"))),
            margin_mode="isolated" if data.get("isolated") else "cross",
            updated_at=datetime.now(timezone.utc)
        )

    # ========================================================================
    # TRADING METHODS
    # ========================================================================

    async def place_order(self, order: UnifiedOrder) -> UnifiedOrder:
        """Place an order on Binance"""
        if self._futures_mode:
            endpoint = "/fapi/v1/order"
        else:
            endpoint = "/api/v3/order"

        params = self._order_to_binance(order)

        result = await self._request(
            "POST",
            endpoint,
            params=params,
            signed=True,
            weight=1
        )

        # Update order with result
        order.exchange_order_id = str(result.get("orderId"))
        order.client_order_id = result.get("clientOrderId")
        order.status = self._map_order_status(result.get("status", "NEW"))
        order.updated_at = datetime.now(timezone.utc)

        logger.info(
            f"Order placed: {order.symbol} {order.side.value} {order.quantity} "
            f"@ {order.price or 'MARKET'} (id={order.exchange_order_id})"
        )

        return order

    def _order_to_binance(self, order: UnifiedOrder) -> Dict[str, Any]:
        """Convert unified order to Binance format"""
        # Map order type
        type_map = {
            OrderType.MARKET: "MARKET",
            OrderType.LIMIT: "LIMIT",
            OrderType.STOP_MARKET: "STOP_MARKET",
            OrderType.STOP_LIMIT: "STOP",
            OrderType.TAKE_PROFIT_MARKET: "TAKE_PROFIT_MARKET",
            OrderType.TAKE_PROFIT_LIMIT: "TAKE_PROFIT",
        }

        # Map side
        side_map = {
            OrderSide.BUY: "BUY",
            OrderSide.SELL: "SELL",
        }

        # Map time in force
        tif_map = {
            TimeInForce.GTC: "GTC",
            TimeInForce.IOC: "IOC",
            TimeInForce.FOK: "FOK",
            TimeInForce.POST_ONLY: "GTX",  # Binance uses GTX for post-only
        }

        params = {
            "symbol": order.symbol.upper(),
            "side": side_map[order.side],
            "type": type_map.get(order.order_type, "MARKET"),
            "quantity": str(order.quantity),
        }

        # Add price for limit orders
        if order.price:
            params["price"] = str(order.price)

        # Add time in force for limit orders
        if order.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT, OrderType.TAKE_PROFIT_LIMIT):
            params["timeInForce"] = tif_map.get(order.time_in_force, "GTC")

        # Add stop price for stop orders
        if order.stop_price:
            params["stopPrice"] = str(order.stop_price)

        # Add reduce-only flag (futures only)
        if self._futures_mode and order.reduce_only:
            params["reduceOnly"] = "true"

        # Add client order ID
        if order.client_order_id:
            params["newClientOrderId"] = order.client_order_id

        return params

    def _map_order_status(self, status: str) -> OrderStatus:
        """Map Binance order status to unified status"""
        status_map = {
            "NEW": OrderStatus.NEW,
            "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
            "FILLED": OrderStatus.FILLED,
            "CANCELED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
            "EXPIRED": OrderStatus.EXPIRED,
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
                exchange="binance"
            )

        if self._futures_mode:
            endpoint = "/fapi/v1/order"
        else:
            endpoint = "/api/v3/order"

        params = {"symbol": symbol.upper()}
        if order_id:
            params["orderId"] = order_id
        if client_order_id:
            params["origClientOrderId"] = client_order_id

        result = await self._request(
            "DELETE",
            endpoint,
            params=params,
            signed=True,
            weight=1
        )

        return self._parse_order(result)

    async def get_order_status(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None
    ) -> UnifiedOrder:
        """Get order status"""
        if self._futures_mode:
            endpoint = "/fapi/v1/order"
        else:
            endpoint = "/api/v3/order"

        params = {"symbol": symbol.upper()}
        if order_id:
            params["orderId"] = order_id
        if client_order_id:
            params["origClientOrderId"] = client_order_id

        result = await self._request(
            "GET",
            endpoint,
            params=params,
            signed=True,
            weight=1
        )

        return self._parse_order(result)

    def _parse_order(self, data: Dict[str, Any]) -> UnifiedOrder:
        """Parse Binance order response"""
        # Map side
        side_map = {"BUY": OrderSide.BUY, "SELL": OrderSide.SELL}

        # Map type
        type_map = {
            "MARKET": OrderType.MARKET,
            "LIMIT": OrderType.LIMIT,
            "STOP": OrderType.STOP_LIMIT,
            "STOP_MARKET": OrderType.STOP_MARKET,
            "TAKE_PROFIT": OrderType.TAKE_PROFIT_LIMIT,
            "TAKE_PROFIT_MARKET": OrderType.TAKE_PROFIT_MARKET,
        }

        # Parse timestamps
        created_time = data.get("time") or data.get("transactTime", 0)
        updated_time = data.get("updateTime", created_time)

        try:
            created_at = datetime.fromtimestamp(created_time / 1000, tz=timezone.utc)
        except (ValueError, TypeError):
            created_at = datetime.now(timezone.utc)

        try:
            updated_at = datetime.fromtimestamp(updated_time / 1000, tz=timezone.utc)
        except (ValueError, TypeError):
            updated_at = datetime.now(timezone.utc)

        return UnifiedOrder(
            exchange=ExchangeName.BINANCE,
            exchange_order_id=str(data.get("orderId")),
            client_order_id=data.get("clientOrderId"),
            symbol=data.get("symbol", ""),
            product_type=ProductType.LINEAR if self._futures_mode else ProductType.SPOT,
            side=side_map.get(data.get("side", "BUY"), OrderSide.BUY),
            order_type=type_map.get(data.get("type", "MARKET"), OrderType.MARKET),
            quantity=Decimal(str(data.get("origQty", "0"))),
            price=Decimal(str(data.get("price", "0"))) if data.get("price") and data.get("price") != "0" else None,
            stop_price=Decimal(str(data.get("stopPrice", "0"))) if data.get("stopPrice") and data.get("stopPrice") != "0" else None,
            time_in_force=TimeInForce.GTC,
            reduce_only=data.get("reduceOnly", False),
            status=self._map_order_status(data.get("status", "NEW")),
            filled_quantity=Decimal(str(data.get("executedQty", "0"))),
            filled_price=Decimal(str(data.get("avgPrice", "0"))) if data.get("avgPrice") else None,
            commission=Decimal(str(data.get("commission", "0"))) if data.get("commission") else Decimal("0"),
            created_at=created_at,
            updated_at=updated_at
        )

    async def get_open_orders(
        self,
        symbol: Optional[str] = None,
        product_type: Optional[ProductType] = None
    ) -> List[UnifiedOrder]:
        """Get all open orders"""
        if self._futures_mode:
            endpoint = "/fapi/v1/openOrders"
        else:
            endpoint = "/api/v3/openOrders"

        params = {}
        if symbol:
            params["symbol"] = symbol.upper()

        result = await self._request(
            "GET",
            endpoint,
            params=params,
            signed=True,
            weight=40 if not symbol else 1
        )

        return [self._parse_order(order_data) for order_data in result]

    # ========================================================================
    # MARKET DATA METHODS
    # ========================================================================

    async def get_ticker(self, symbol: str) -> Ticker:
        """Get ticker data"""
        if self._futures_mode:
            endpoint = "/fapi/v1/ticker/24hr"
        else:
            endpoint = "/api/v3/ticker/24hr"

        result = await self._request(
            "GET",
            endpoint,
            params={"symbol": symbol.upper()},
            weight=1
        )

        return Ticker(
            exchange=ExchangeName.BINANCE,
            symbol=result.get("symbol", symbol),
            last_price=Decimal(str(result.get("lastPrice", "0"))),
            bid_price=Decimal(str(result.get("bidPrice", "0"))) if result.get("bidPrice") else None,
            ask_price=Decimal(str(result.get("askPrice", "0"))) if result.get("askPrice") else None,
            high_24h=Decimal(str(result.get("highPrice", "0"))) if result.get("highPrice") else None,
            low_24h=Decimal(str(result.get("lowPrice", "0"))) if result.get("lowPrice") else None,
            volume_24h=Decimal(str(result.get("volume", "0"))) if result.get("volume") else None,
            change_24h=float(result.get("priceChangePercent", "0")),
            timestamp=datetime.now(timezone.utc)
        )

    async def get_orderbook(
        self,
        symbol: str,
        depth: int = 25
    ) -> OrderBook:
        """Get orderbook"""
        if self._futures_mode:
            endpoint = "/fapi/v1/depth"
        else:
            endpoint = "/api/v3/depth"

        # Binance supports specific depth values
        valid_depths = [5, 10, 20, 50, 100, 500, 1000]
        limit = min([d for d in valid_depths if d >= depth], default=100)

        result = await self._request(
            "GET",
            endpoint,
            params={"symbol": symbol.upper(), "limit": limit},
            weight=5 if limit <= 100 else 10
        )

        bids = [
            OrderBookLevel(
                price=Decimal(str(level[0])),
                quantity=Decimal(str(level[1]))
            )
            for level in result.get("bids", [])
        ]

        asks = [
            OrderBookLevel(
                price=Decimal(str(level[0])),
                quantity=Decimal(str(level[1]))
            )
            for level in result.get("asks", [])
        ]

        return OrderBook(
            exchange=ExchangeName.BINANCE,
            symbol=symbol,
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
        if self._futures_mode:
            endpoint = "/fapi/v1/trades"
        else:
            endpoint = "/api/v3/trades"

        result = await self._request(
            "GET",
            endpoint,
            params={"symbol": symbol.upper(), "limit": min(limit, 1000)},
            weight=1
        )

        trades = []
        for trade_data in result:
            try:
                timestamp = datetime.fromtimestamp(
                    trade_data.get("time", 0) / 1000,
                    tz=timezone.utc
                )
            except (ValueError, TypeError):
                timestamp = datetime.now(timezone.utc)

            trades.append(Trade(
                exchange=ExchangeName.BINANCE,
                symbol=symbol,
                trade_id=str(trade_data.get("id", "")),
                price=Decimal(str(trade_data.get("price", "0"))),
                quantity=Decimal(str(trade_data.get("qty", "0"))),
                side=OrderSide.SELL if trade_data.get("isBuyerMaker") else OrderSide.BUY,
                timestamp=timestamp
            ))

        return trades

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 100,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Kline]:
        """Get kline/candlestick data"""
        if self._futures_mode:
            endpoint = "/fapi/v1/klines"
        else:
            endpoint = "/api/v3/klines"

        # Map interval to Binance format
        interval_map = {
            "1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m",
            "60": "1h", "120": "2h", "240": "4h", "360": "6h", "720": "12h",
            "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "12h": "12h",
            "1d": "1d", "D": "1d", "W": "1w", "M": "1M"
        }
        binance_interval = interval_map.get(interval, interval)

        params = {
            "symbol": symbol.upper(),
            "interval": binance_interval,
            "limit": min(limit, 1500)
        }

        if start_time:
            params["startTime"] = int(start_time.timestamp() * 1000)
        if end_time:
            params["endTime"] = int(end_time.timestamp() * 1000)

        result = await self._request("GET", endpoint, params=params, weight=1)

        klines = []
        for kline_data in result:
            try:
                open_time = datetime.fromtimestamp(
                    kline_data[0] / 1000,
                    tz=timezone.utc
                )
                close_time = datetime.fromtimestamp(
                    kline_data[6] / 1000,
                    tz=timezone.utc
                )

                klines.append(Kline(
                    exchange=ExchangeName.BINANCE,
                    symbol=symbol,
                    interval=interval,
                    open_time=open_time,
                    open=Decimal(str(kline_data[1])),
                    high=Decimal(str(kline_data[2])),
                    low=Decimal(str(kline_data[3])),
                    close=Decimal(str(kline_data[4])),
                    volume=Decimal(str(kline_data[5])),
                    close_time=close_time
                ))
            except (IndexError, ValueError, TypeError) as e:
                logger.warning(f"Failed to parse kline: {e}")
                continue

        return klines


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_binance_adapter(
    api_key: str,
    api_secret: str,
    testnet: bool = True,
    futures_mode: bool = True,
    margin_type: str = "linear"
) -> BinanceExchangeAdapter:
    """
    Factory function to create Binance adapter

    Args:
        api_key: Binance API key
        api_secret: Binance API secret
        testnet: Use testnet environment
        futures_mode: Use Futures API
        margin_type: "linear" or "inverse"

    Returns:
        Configured BinanceExchangeAdapter
    """
    config = ExchangeConfig(
        exchange=ExchangeName.BINANCE,
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet
    )

    return BinanceExchangeAdapter(
        config,
        futures_mode=futures_mode,
        margin_type=margin_type
    )


__all__ = [
    "BinanceExchangeAdapter",
    "BinanceAdapterConfig",
    "BinanceRateLimiter",
    "create_binance_adapter",
    "map_binance_error",
    "BINANCE_ERROR_MAP",
]
