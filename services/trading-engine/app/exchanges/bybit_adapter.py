"""
Bybit Exchange Adapter - Phase 6: Multi-Exchange Support
Purpose: Wrapper adapter for the existing bybit-connector service

This adapter implements the ExchangeInterface for Bybit exchange,
delegating actual API calls to the bybit-connector microservice
while providing the unified interface for the trading engine.

Architecture:
    +---------------+     HTTP/REST      +------------------+
    | BybitAdapter  | -----------------> | bybit-connector  |
    +---------------+                    +------------------+
           |                                     |
           v                                     v
    ExchangeInterface                      Bybit API
    (unified models)                    (native format)

Features:
- Async HTTP client for service communication
- Automatic retry with exponential backoff
- Rate limiting to respect bybit-connector limits
- Model conversion between unified and Bybit formats
- Circuit breaker integration
- Comprehensive error mapping

Created: 2025-12-11
Author: Backend Developer Agent
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

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
    InvalidSymbolError,
    OrderNotFoundError,
    OrderRejectedError,
    RateLimitError,
    TimeoutError,
    ValidationError,
    map_bybit_error,
)

# Configure logger
logger = logging.getLogger(__name__)


# ============================================================================
# RATE LIMITER
# ============================================================================


class RateLimiter:
    """
    Simple token bucket rate limiter

    Implements a token bucket algorithm to enforce rate limits
    for API requests to the bybit-connector service.

    Attributes:
        rate: Maximum requests per second
        tokens: Current available tokens
        last_update: Last token refresh timestamp
    """

    def __init__(self, rate: float = 10.0):
        """
        Initialize rate limiter

        Args:
            rate: Maximum requests per second
        """
        self.rate = rate
        self.tokens = rate
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        """
        Acquire a token, waiting if necessary

        Returns:
            Wait time in seconds (0 if no wait needed)
        """
        async with self._lock:
            now = time.monotonic()
            # Refill tokens based on elapsed time
            elapsed = now - self.last_update
            self.tokens = min(self.rate, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens >= 1:
                # Token available, consume it
                self.tokens -= 1
                return 0.0
            else:
                # Need to wait for token
                wait_time = (1 - self.tokens) / self.rate
                self.tokens = 0
                return wait_time

    async def wait_and_acquire(self) -> None:
        """Wait for and acquire a token"""
        wait_time = await self.acquire()
        if wait_time > 0:
            await asyncio.sleep(wait_time)


# ============================================================================
# BYBIT ADAPTER CONFIGURATION
# ============================================================================


class BybitAdapterConfig(BaseModel):
    """
    Configuration specific to Bybit adapter

    Extends the base ExchangeConfig with Bybit-specific options.

    Attributes:
        connector_url: URL of bybit-connector service
        default_category: Default product category (linear, inverse, spot)
        account_type: Bybit account type (UNIFIED, CONTRACT, etc.)
    """

    connector_url: str = "http://localhost:8001"
    default_category: str = "linear"
    account_type: str = "UNIFIED"
    request_timeout: float = 30.0
    max_retries: int = 3


# ============================================================================
# BYBIT EXCHANGE ADAPTER
# ============================================================================


class BybitExchangeAdapter(ExchangeInterface):
    """
    Bybit exchange adapter implementing ExchangeInterface

    This adapter wraps the bybit-connector microservice to provide
    a unified interface for the trading engine. It handles:
    - Model conversion between unified and Bybit formats
    - HTTP communication with bybit-connector
    - Error mapping to unified exceptions
    - Rate limiting and retry logic

    Usage:
        config = ExchangeConfig(
            exchange=ExchangeName.BYBIT,
            api_key="...",
            api_secret="...",
            testnet=True
        )
        adapter = BybitExchangeAdapter(config, connector_url="http://localhost:8001")
        await adapter.initialize()

        # Place order
        order = UnifiedOrder(
            exchange=ExchangeName.BYBIT,
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.001")
        )
        result = await adapter.place_order(order)
    """

    def __init__(
        self,
        config: ExchangeConfig,
        connector_url: str = "http://localhost:8001",
        account_type: str = "UNIFIED",
    ):
        """
        Initialize Bybit adapter

        Args:
            config: Exchange configuration
            connector_url: URL of bybit-connector service
            account_type: Bybit account type
        """
        super().__init__(config)

        # Store Bybit-specific config
        self._connector_url = connector_url.rstrip("/")
        self._account_type = account_type
        self._default_category = config.default_product.value

        # HTTP client (created in initialize)
        self._client: Optional[httpx.AsyncClient] = None

        # Rate limiter
        self._rate_limiter = RateLimiter(rate=10.0)

        # Set Bybit capabilities
        self._capabilities = ExchangeCapabilities(
            # Trading products
            spot_trading=True,
            perpetual_trading=True,
            margin_trading=False,
            options_trading=True,
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
            orderbook_depth=200,
            # Rate limits (conservative)
            rate_limit_per_second=10,
            order_rate_limit=10,
            # Trading
            max_leverage=100,
            min_order_size_usd=1.0,
            # Environment
            testnet_available=True,
            sandbox_mode=False,
        )

        logger.info(
            f"Created Bybit adapter (connector_url={connector_url}, "
            f"testnet={config.testnet}, account_type={account_type})"
        )

    # ========================================================================
    # LIFECYCLE METHODS
    # ========================================================================

    async def initialize(self) -> None:
        """
        Initialize connection to bybit-connector service

        Creates HTTP client and validates connectivity.

        Raises:
            ConnectionError: If bybit-connector is not reachable
            AuthenticationError: If API credentials are invalid
        """
        logger.info("Initializing Bybit adapter...")

        # Create HTTP client with configured timeout
        self._client = httpx.AsyncClient(
            base_url=self._connector_url,
            timeout=httpx.Timeout(
                connect=5.0, read=self._config.timeout, write=10.0, pool=10.0
            ),
            headers={"Content-Type": "application/json"},
        )

        # Verify connectivity with health check
        try:
            health_ok = await self.health_check()
            if not health_ok:
                raise ConnectionError(
                    message="Bybit connector health check failed", exchange="bybit"
                )
        except httpx.HTTPError as e:
            raise ConnectionError(
                message=f"Failed to connect to bybit-connector: {e}", exchange="bybit"
            )

        # Validate credentials by fetching balance
        try:
            await self.get_balance()
        except AuthenticationError:
            raise
        except Exception as e:
            logger.warning(f"Balance check during init failed: {e}")

        self._initialized = True
        logger.info("Bybit adapter initialized successfully")

    async def close(self) -> None:
        """Close HTTP client connection"""
        if self._client:
            await self._client.aclose()
            self._client = None
        self._initialized = False
        logger.info("Bybit adapter closed")

    async def health_check(self) -> bool:
        """
        Check bybit-connector health

        Returns:
            True if service is healthy
        """
        try:
            response = await self._client.get("/health")
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
        json_data: Optional[Dict[str, Any]] = None,
        retries: int = 3,
    ) -> Dict[str, Any]:
        """
        Make HTTP request to bybit-connector with retry logic

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            params: Query parameters
            json_data: JSON body data
            retries: Number of retry attempts

        Returns:
            Response data from bybit-connector

        Raises:
            ExchangeError: On request failure
        """
        if not self._client:
            raise ConnectionError(message="Adapter not initialized", exchange="bybit")

        # Apply rate limiting
        await self._rate_limiter.wait_and_acquire()

        last_error: Optional[Exception] = None

        for attempt in range(retries):
            try:
                # Make request
                response = await self._client.request(
                    method=method, url=endpoint, params=params, json=json_data
                )

                # Parse response.
                # The bybit-connector strips Bybit's V5 envelope (retCode /
                # retMsg / result) and wraps the inner payload as
                # `{"success": True, "data": <bybit_inner>}` on success.
                # On Bybit-side rejection it raises an HTTPException with
                # `{"detail": "..."}`. There is therefore no retCode in
                # success bodies and no retCode/retMsg in error bodies.
                data = response.json()

                if response.status_code >= 400:
                    detail = (
                        data.get("detail") or data.get("message") or "Unknown error"
                    )
                    # Caller infrastructure expects a numeric retCode; reuse
                    # the HTTP status as a proxy when Bybit's code isn't
                    # available through this layer.
                    raise map_bybit_error(response.status_code, str(detail), data)

                return data.get("data", {})

            except httpx.TimeoutException as e:
                last_error = TimeoutError(
                    message=f"Request timed out: {e}", exchange="bybit"
                )
                logger.warning(
                    f"Request timeout (attempt {attempt + 1}/{retries}): {e}"
                )

            except httpx.HTTPStatusError as e:
                # Map HTTP status to exception
                if e.response.status_code == 429:
                    last_error = RateLimitError(exchange="bybit", retry_after=60)
                elif e.response.status_code == 401:
                    raise AuthenticationError(exchange="bybit")
                elif e.response.status_code == 403:
                    raise AuthenticationError(
                        message="Permission denied", exchange="bybit"
                    )
                else:
                    last_error = ExchangeError(
                        message=f"HTTP {e.response.status_code}: {e.response.text}",
                        exchange="bybit",
                    )

            except RateLimitError as e:
                # Wait and retry for rate limit
                if attempt < retries - 1:
                    await asyncio.sleep(e.retry_after or 60)
                last_error = e

            except ExchangeError:
                # Don't retry exchange errors
                raise

            except Exception as e:
                last_error = ConnectionError(
                    message=f"Request failed: {e}", exchange="bybit"
                )
                logger.warning(f"Request error (attempt {attempt + 1}/{retries}): {e}")

            # Exponential backoff before retry
            if attempt < retries - 1:
                await asyncio.sleep(2**attempt)

        # All retries exhausted
        if last_error:
            raise last_error
        raise ConnectionError(message="Request failed", exchange="bybit")

    # ========================================================================
    # ACCOUNT METHODS
    # ========================================================================

    async def get_balance(self, asset: Optional[str] = None) -> AccountBalance:
        """
        Get account balance from bybit-connector

        Args:
            asset: Specific asset to query (optional)

        Returns:
            Account balance information
        """
        # Phase 18 WR-02: connector route declares snake_case account_type
        # (services/bybit-connector/app/main.py:536). camelCase key silently
        # falls through to the FastAPI default — override was a no-op.
        params = {"account_type": self._account_type}
        if asset:
            params["coin"] = asset.upper()

        try:
            result = await self._request(
                "GET", "/api/v1/account/balance", params=params
            )

            # Parse response into AccountBalance
            return self._parse_balance(result)

        except ExchangeError:
            raise
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            raise ConnectionError(
                message=f"Failed to get balance: {e}", exchange="bybit"
            )

    def _parse_balance(self, data: Dict[str, Any]) -> AccountBalance:
        """
        Parse Bybit balance response into unified model

        Args:
            data: Raw balance data from Bybit

        Returns:
            AccountBalance model
        """
        # Parse individual coin balances
        assets = []
        coin_list = data.get("list", [])

        for account in coin_list:
            for coin_data in account.get("coin", []):
                assets.append(
                    AssetBalance(
                        asset=coin_data.get("coin", ""),
                        free=Decimal(str(coin_data.get("availableToWithdraw", "0"))),
                        locked=Decimal(str(coin_data.get("locked", "0"))),
                    )
                )

        # Get total equity (first account)
        total_equity = Decimal("0")
        available_balance = Decimal("0")
        used_margin = Decimal("0")
        unrealized_pnl = Decimal("0")

        if coin_list:
            first_account = coin_list[0]
            total_equity = Decimal(str(first_account.get("totalEquity", "0")))
            available_balance = Decimal(str(first_account.get("availableBalance", "0")))
            used_margin = Decimal(str(first_account.get("totalPositionIM", "0")))
            unrealized_pnl = Decimal(str(first_account.get("totalPerpUPL", "0")))

        return AccountBalance(
            exchange=ExchangeName.BYBIT,
            account_type=self._account_type,
            total_equity=total_equity,
            available_balance=available_balance,
            used_margin=used_margin,
            unrealized_pnl=unrealized_pnl,
            assets=assets,
            updated_at=datetime.now(timezone.utc),
        )

    async def get_positions(
        self, symbol: Optional[str] = None, product_type: Optional[ProductType] = None
    ) -> List[UnifiedPosition]:
        """
        Get open positions

        Args:
            symbol: Filter by symbol
            product_type: Filter by product type

        Returns:
            List of positions
        """
        category = product_type.value if product_type else self._default_category
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol.upper()

        try:
            result = await self._request(
                "GET", "/api/v1/account/positions", params=params
            )

            # Parse positions
            positions = []
            for pos_data in result.get("list", []):
                pos = self._parse_position(pos_data, category)
                if pos:
                    positions.append(pos)

            return positions

        except ExchangeError:
            raise
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            raise ConnectionError(
                message=f"Failed to get positions: {e}", exchange="bybit"
            )

    def _parse_position(
        self, data: Dict[str, Any], category: str
    ) -> Optional[UnifiedPosition]:
        """
        Parse Bybit position into unified model

        Args:
            data: Raw position data
            category: Product category

        Returns:
            UnifiedPosition or None if no position
        """
        # Skip empty positions
        size = Decimal(str(data.get("size", "0")))
        if size == 0:
            return None

        # Determine position side
        side_str = data.get("side", "").lower()
        if side_str == "buy":
            side = PositionSide.LONG
        elif side_str == "sell":
            side = PositionSide.SHORT
        else:
            side = PositionSide.BOTH

        # Map product type
        product_map = {
            "linear": ProductType.LINEAR,
            "inverse": ProductType.INVERSE,
            "spot": ProductType.SPOT,
            "option": ProductType.OPTION,
        }
        product_type = product_map.get(category, ProductType.LINEAR)

        return UnifiedPosition(
            exchange=ExchangeName.BYBIT,
            symbol=data.get("symbol", ""),
            product_type=product_type,
            side=side,
            quantity=abs(size),
            entry_price=Decimal(str(data.get("avgPrice", "0"))),
            mark_price=Decimal(str(data.get("markPrice", "0"))),
            liquidation_price=Decimal(str(data.get("liqPrice", "0")))
            if data.get("liqPrice")
            else None,
            unrealized_pnl=Decimal(str(data.get("unrealisedPnl", "0"))),
            realized_pnl=Decimal(str(data.get("cumRealisedPnl", "0"))),
            leverage=int(data.get("leverage", 1)),
            margin=Decimal(str(data.get("positionIM", "0"))),
            margin_mode=data.get("tradeMode", "cross"),
            updated_at=datetime.now(timezone.utc),
        )

    # ========================================================================
    # TRADING METHODS
    # ========================================================================

    async def place_order(self, order: UnifiedOrder) -> UnifiedOrder:
        """
        Place order via bybit-connector

        Args:
            order: Order to place

        Returns:
            Order with exchange ID and updated status
        """
        # Convert to Bybit format
        payload = self._order_to_bybit(order)

        try:
            result = await self._request(
                "POST", "/api/v1/order/place", json_data=payload
            )

            # Phase 18 WR-03: guard against silent rejection. Tape client
            # (and real Bybit under some edge cases) can return
            # {'orderId': '', 'orderStatus': 'Rejected'} on unroutable
            # requests. Previously we hard-coded status = NEW and stored
            # an empty exchange_order_id, so downstream cancel_order /
            # get_order_status silently no-op'd against a nonexistent
            # order and Phase 19 recon would look up phantoms.
            raw_status = str(result.get("orderStatus") or "").lower()
            raw_order_id = result.get("orderId") or ""
            if raw_status == "rejected" or not raw_order_id:
                raise OrderRejectedError(
                    reason=(
                        f"Exchange rejected order (orderId={raw_order_id!r}, "
                        f"orderStatus={result.get('orderStatus')!r})"
                    ),
                    exchange="bybit",
                )

            # Update order with result
            order.exchange_order_id = raw_order_id
            order.client_order_id = result.get("orderLinkId") or str(order.id)
            order.status = OrderStatus.NEW
            order.updated_at = datetime.now(timezone.utc)

            logger.info(
                f"Order placed: {order.symbol} {order.side.value} {order.quantity} "
                f"@ {order.price or 'MARKET'} (id={order.exchange_order_id})"
            )

            return order

        except ExchangeError:
            raise
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            raise OrderRejectedError(reason=str(e), exchange="bybit")

    def _order_to_bybit(self, order: UnifiedOrder) -> Dict[str, Any]:
        """
        Convert unified order to Bybit format

        Args:
            order: Unified order

        Returns:
            Bybit order payload
        """
        # Map order type
        type_map = {
            OrderType.MARKET: "Market",
            OrderType.LIMIT: "Limit",
        }

        # Map side
        side_map = {
            OrderSide.BUY: "Buy",
            OrderSide.SELL: "Sell",
        }

        # Map time in force
        tif_map = {
            TimeInForce.GTC: "GTC",
            TimeInForce.IOC: "IOC",
            TimeInForce.FOK: "FOK",
            TimeInForce.POST_ONLY: "PostOnly",
        }

        # Build payload
        payload = {
            "category": order.product_type.value,
            "symbol": order.symbol.upper(),
            "side": side_map[order.side],
            "orderType": type_map.get(order.order_type, "Market"),
            "qty": str(order.quantity),
            "timeInForce": tif_map.get(order.time_in_force, "GTC"),
        }

        # Add price for limit orders
        if order.price:
            payload["price"] = str(order.price)

        # Add optional flags
        if order.reduce_only:
            payload["reduceOnly"] = True
        if order.post_only:
            payload["timeInForce"] = "PostOnly"

        # Add client order ID
        if order.client_order_id:
            payload["orderLinkId"] = order.client_order_id
        else:
            payload["orderLinkId"] = str(order.id)

        return payload

    async def cancel_order(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
    ) -> UnifiedOrder:
        """
        Cancel an order

        Args:
            symbol: Trading pair
            order_id: Exchange order ID
            client_order_id: Client order ID

        Returns:
            Cancelled order
        """
        if not order_id and not client_order_id:
            raise ValidationError(
                message="Either order_id or client_order_id required", exchange="bybit"
            )

        payload = {
            "category": self._default_category,
            "symbol": symbol.upper(),
        }

        if order_id:
            payload["orderId"] = order_id
        if client_order_id:
            payload["orderLinkId"] = client_order_id

        try:
            result = await self._request(
                "POST", "/api/v1/order/cancel", json_data=payload
            )

            # Build cancelled order response
            return UnifiedOrder(
                exchange=ExchangeName.BYBIT,
                exchange_order_id=result.get("orderId", order_id),
                client_order_id=result.get("orderLinkId", client_order_id),
                symbol=symbol,
                product_type=ProductType(self._default_category),
                side=OrderSide.BUY,  # Placeholder
                order_type=OrderType.MARKET,  # Placeholder
                quantity=Decimal("0"),  # Will be updated
                status=OrderStatus.CANCELLED,
                updated_at=datetime.now(timezone.utc),
            )

        except ExchangeError:
            raise
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            raise OrderNotFoundError(
                order_id=order_id, client_order_id=client_order_id, exchange="bybit"
            )

    async def get_order_status(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
    ) -> UnifiedOrder:
        """
        Get order status

        Args:
            symbol: Trading pair
            order_id: Exchange order ID
            client_order_id: Client order ID

        Returns:
            Order with current status
        """
        params = {
            "category": self._default_category,
            "symbol": symbol.upper(),
        }

        if order_id:
            params["orderId"] = order_id
        if client_order_id:
            params["orderLinkId"] = client_order_id

        try:
            result = await self._request("GET", "/api/v1/order/open", params=params)

            # Parse order from result
            order_list = result.get("list", [])
            if not order_list:
                raise OrderNotFoundError(
                    order_id=order_id, client_order_id=client_order_id, exchange="bybit"
                )

            return self._parse_order(order_list[0])

        except ExchangeError:
            raise
        except Exception as e:
            logger.error(f"Failed to get order status: {e}")
            raise OrderNotFoundError(order_id=order_id, exchange="bybit")

    def _parse_order(self, data: Dict[str, Any]) -> UnifiedOrder:
        """
        Parse Bybit order into unified model

        Args:
            data: Raw order data

        Returns:
            UnifiedOrder
        """
        # Map status
        status_map = {
            "Created": OrderStatus.PENDING,
            "New": OrderStatus.NEW,
            "PartiallyFilled": OrderStatus.PARTIALLY_FILLED,
            "Filled": OrderStatus.FILLED,
            "Cancelled": OrderStatus.CANCELLED,
            "Rejected": OrderStatus.REJECTED,
            "Expired": OrderStatus.EXPIRED,
        }

        # Map side
        side_map = {
            "Buy": OrderSide.BUY,
            "Sell": OrderSide.SELL,
        }

        # Map type
        type_map = {
            "Market": OrderType.MARKET,
            "Limit": OrderType.LIMIT,
        }

        # Parse timestamps
        created_time = data.get("createdTime", "")
        updated_time = data.get("updatedTime", "")

        try:
            created_at = (
                datetime.fromtimestamp(int(created_time) / 1000, tz=timezone.utc)
                if created_time
                else datetime.now(timezone.utc)
            )
        except (ValueError, TypeError):
            created_at = datetime.now(timezone.utc)

        try:
            updated_at = (
                datetime.fromtimestamp(int(updated_time) / 1000, tz=timezone.utc)
                if updated_time
                else datetime.now(timezone.utc)
            )
        except (ValueError, TypeError):
            updated_at = datetime.now(timezone.utc)

        return UnifiedOrder(
            exchange=ExchangeName.BYBIT,
            exchange_order_id=data.get("orderId"),
            client_order_id=data.get("orderLinkId"),
            symbol=data.get("symbol", ""),
            product_type=ProductType.LINEAR,  # Default to linear
            side=side_map.get(data.get("side", "Buy"), OrderSide.BUY),
            order_type=type_map.get(data.get("orderType", "Market"), OrderType.MARKET),
            quantity=Decimal(str(data.get("qty", "0"))),
            price=Decimal(str(data.get("price", "0"))) if data.get("price") else None,
            time_in_force=TimeInForce.GTC,
            reduce_only=data.get("reduceOnly", False),
            status=status_map.get(data.get("orderStatus", "New"), OrderStatus.NEW),
            filled_quantity=Decimal(str(data.get("cumExecQty", "0"))),
            filled_price=Decimal(str(data.get("avgPrice", "0")))
            if data.get("avgPrice")
            else None,
            commission=Decimal(str(data.get("cumExecFee", "0"))),
            created_at=created_at,
            updated_at=updated_at,
        )

    async def get_open_orders(
        self, symbol: Optional[str] = None, product_type: Optional[ProductType] = None
    ) -> List[UnifiedOrder]:
        """
        Get all open orders

        Args:
            symbol: Filter by symbol
            product_type: Filter by product type

        Returns:
            List of open orders
        """
        category = product_type.value if product_type else self._default_category
        params = {"category": category, "limit": 50}
        if symbol:
            params["symbol"] = symbol.upper()

        try:
            result = await self._request("GET", "/api/v1/order/open", params=params)

            orders = []
            for order_data in result.get("list", []):
                order = self._parse_order(order_data)
                if order.is_open:
                    orders.append(order)

            return orders

        except ExchangeError:
            raise
        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            return []

    # ========================================================================
    # MARKET DATA METHODS
    # ========================================================================

    async def get_ticker(self, symbol: str) -> Ticker:
        """
        Get ticker for symbol

        Args:
            symbol: Trading pair

        Returns:
            Ticker data
        """
        params = {"category": self._default_category, "symbol": symbol.upper()}

        try:
            result = await self._request("GET", "/api/v1/market/ticker", params=params)

            ticker_list = result.get("list", [])
            if not ticker_list:
                raise InvalidSymbolError(symbol=symbol, exchange="bybit")

            data = ticker_list[0]
            return Ticker(
                exchange=ExchangeName.BYBIT,
                symbol=data.get("symbol", symbol),
                last_price=Decimal(str(data.get("lastPrice", "0"))),
                bid_price=Decimal(str(data.get("bid1Price", "0")))
                if data.get("bid1Price")
                else None,
                ask_price=Decimal(str(data.get("ask1Price", "0")))
                if data.get("ask1Price")
                else None,
                high_24h=Decimal(str(data.get("highPrice24h", "0")))
                if data.get("highPrice24h")
                else None,
                low_24h=Decimal(str(data.get("lowPrice24h", "0")))
                if data.get("lowPrice24h")
                else None,
                volume_24h=Decimal(str(data.get("volume24h", "0")))
                if data.get("volume24h")
                else None,
                change_24h=float(data.get("price24hPcnt", "0")) * 100
                if data.get("price24hPcnt")
                else None,
                timestamp=datetime.now(timezone.utc),
            )

        except ExchangeError:
            raise
        except Exception as e:
            logger.error(f"Failed to get ticker: {e}")
            raise DataUnavailableError(
                data_type="ticker", exchange="bybit", symbol=symbol
            )

    async def get_orderbook(self, symbol: str, depth: int = 25) -> OrderBook:
        """
        Get orderbook for symbol

        Args:
            symbol: Trading pair
            depth: Number of levels

        Returns:
            OrderBook snapshot
        """
        params = {
            "category": self._default_category,
            "symbol": symbol.upper(),
            "limit": min(depth, 200),
        }

        try:
            result = await self._request(
                "GET", "/api/v1/market/orderbook", params=params
            )

            # Parse bids
            bids = [
                OrderBookLevel(
                    price=Decimal(str(level[0])), quantity=Decimal(str(level[1]))
                )
                for level in result.get("b", [])
            ]

            # Parse asks
            asks = [
                OrderBookLevel(
                    price=Decimal(str(level[0])), quantity=Decimal(str(level[1]))
                )
                for level in result.get("a", [])
            ]

            return OrderBook(
                exchange=ExchangeName.BYBIT,
                symbol=symbol,
                bids=bids,
                asks=asks,
                timestamp=datetime.now(timezone.utc),
            )

        except ExchangeError:
            raise
        except Exception as e:
            logger.error(f"Failed to get orderbook: {e}")
            raise DataUnavailableError(
                data_type="orderbook", exchange="bybit", symbol=symbol
            )

    async def get_trades(self, symbol: str, limit: int = 100) -> List[Trade]:
        """
        Get recent trades

        Args:
            symbol: Trading pair
            limit: Maximum trades

        Returns:
            List of trades
        """
        params = {
            "category": self._default_category,
            "symbol": symbol.upper(),
            "limit": min(limit, 1000),
        }

        try:
            result = await self._request(
                "GET", "/api/v1/market/recent-trade", params=params
            )

            trades = []
            for trade_data in result.get("list", []):
                try:
                    timestamp = datetime.fromtimestamp(
                        int(trade_data.get("time", 0)) / 1000, tz=timezone.utc
                    )
                except (ValueError, TypeError):
                    timestamp = datetime.now(timezone.utc)

                trades.append(
                    Trade(
                        exchange=ExchangeName.BYBIT,
                        symbol=symbol,
                        trade_id=trade_data.get("execId", ""),
                        price=Decimal(str(trade_data.get("price", "0"))),
                        quantity=Decimal(str(trade_data.get("size", "0"))),
                        side=OrderSide.BUY
                        if trade_data.get("side") == "Buy"
                        else OrderSide.SELL,
                        timestamp=timestamp,
                    )
                )

            return trades

        except ExchangeError:
            raise
        except Exception as e:
            logger.error(f"Failed to get trades: {e}")
            return []

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 100,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Kline]:
        """
        Get kline data

        Args:
            symbol: Trading pair
            interval: Timeframe (1, 5, 15, 60, etc.)
            limit: Number of candles
            start_time: Start time
            end_time: End time

        Returns:
            List of klines
        """
        params = {
            "category": self._default_category,
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": min(limit, 1000),
        }

        if start_time:
            params["start"] = int(start_time.timestamp() * 1000)
        if end_time:
            params["end"] = int(end_time.timestamp() * 1000)

        try:
            result = await self._request("GET", "/api/v1/market/kline", params=params)

            klines = []
            for kline_data in result.get("list", []):
                try:
                    # Bybit returns: [timestamp, open, high, low, close, volume, turnover]
                    open_time = datetime.fromtimestamp(
                        int(kline_data[0]) / 1000, tz=timezone.utc
                    )
                    # Close time is open time + interval
                    interval_seconds = self._parse_interval(interval)
                    close_time = datetime.fromtimestamp(
                        int(kline_data[0]) / 1000 + interval_seconds, tz=timezone.utc
                    )

                    klines.append(
                        Kline(
                            exchange=ExchangeName.BYBIT,
                            symbol=symbol,
                            interval=interval,
                            open_time=open_time,
                            open=Decimal(str(kline_data[1])),
                            high=Decimal(str(kline_data[2])),
                            low=Decimal(str(kline_data[3])),
                            close=Decimal(str(kline_data[4])),
                            volume=Decimal(str(kline_data[5])),
                            close_time=close_time,
                        )
                    )
                except (IndexError, ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse kline: {e}")
                    continue

            return klines

        except ExchangeError:
            raise
        except Exception as e:
            logger.error(f"Failed to get klines: {e}")
            return []

    def _parse_interval(self, interval: str) -> int:
        """
        Convert interval string to seconds

        Args:
            interval: Interval string (1, 5, 15, 60, D, W)

        Returns:
            Interval in seconds
        """
        interval_map = {
            "1": 60,
            "3": 180,
            "5": 300,
            "15": 900,
            "30": 1800,
            "60": 3600,
            "120": 7200,
            "240": 14400,
            "360": 21600,
            "720": 43200,
            "D": 86400,
            "W": 604800,
            "M": 2592000,
        }
        return interval_map.get(str(interval), 60)


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def create_bybit_adapter(
    api_key: str,
    api_secret: str,
    testnet: bool = True,
    connector_url: str = "http://localhost:8001",
) -> BybitExchangeAdapter:
    """
    Factory function to create Bybit adapter

    Args:
        api_key: Bybit API key
        api_secret: Bybit API secret
        testnet: Use testnet environment
        connector_url: URL of bybit-connector service

    Returns:
        Configured BybitExchangeAdapter
    """
    config = ExchangeConfig(
        exchange=ExchangeName.BYBIT,
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet,
    )

    return BybitExchangeAdapter(config, connector_url=connector_url)


__all__ = [
    "BybitExchangeAdapter",
    "BybitAdapterConfig",
    "RateLimiter",
    "create_bybit_adapter",
]
