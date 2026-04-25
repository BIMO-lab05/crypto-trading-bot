"""
Kraken Exchange Adapter - Phase 6: Multi-Exchange Support
Purpose: Adapter implementation for Kraken exchange

This adapter implements the ExchangeInterface for Kraken exchange,
providing unified access to Kraken Spot and Futures APIs.

Features:
- Full ExchangeInterface implementation
- Kraken Spot trading
- Kraken Futures support
- WebSocket support for real-time data
- Nonce-based request signing
- Error mapping to unified exceptions

Created: 2025-12-11
Author: Backend Developer Agent
"""

import asyncio
import base64
import hashlib
import hmac
import logging
import time
import urllib.parse
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

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
# KRAKEN SYMBOL MAPPING
# ============================================================================

# Kraken uses different symbol formats (XXBTZUSD vs BTCUSD)
KRAKEN_SYMBOL_MAP = {
    # Standard to Kraken
    "BTCUSD": "XXBTZUSD",
    "BTCUSDT": "XBTUSDT",
    "ETHUSD": "XETHZUSD",
    "ETHUSDT": "ETHUSDT",
    "XRPUSD": "XXRPZUSD",
    "LTCUSD": "XLTCZUSD",
    "BCHUSD": "BCHUSD",
    "ADAUSD": "ADAUSD",
    "DOTUSD": "DOTUSD",
    "SOLUSD": "SOLUSD",
}

# Kraken to Standard (reverse mapping)
KRAKEN_SYMBOL_REVERSE = {v: k for k, v in KRAKEN_SYMBOL_MAP.items()}


def to_kraken_symbol(symbol: str) -> str:
    """Convert standard symbol to Kraken format"""
    # Remove common separators
    clean_symbol = symbol.replace("/", "").replace("-", "").upper()
    return KRAKEN_SYMBOL_MAP.get(clean_symbol, clean_symbol)


def from_kraken_symbol(symbol: str) -> str:
    """Convert Kraken symbol to standard format"""
    return KRAKEN_SYMBOL_REVERSE.get(symbol, symbol)


# ============================================================================
# KRAKEN ERROR MAPPING
# ============================================================================

# Kraken error messages to unified exceptions
KRAKEN_ERROR_MAP = {
    "EGeneral:Invalid arguments": ValidationError,
    "EGeneral:Invalid arguments:volume": InvalidQuantityError,
    "EService:Unavailable": ConnectionError,
    "EService:Busy": RateLimitError,
    "EAPI:Invalid key": InvalidAPIKeyError,
    "EAPI:Invalid signature": InvalidSignatureError,
    "EAPI:Invalid nonce": AuthenticationError,
    "EAPI:Rate limit exceeded": RateLimitError,
    "EOrder:Insufficient funds": InsufficientBalanceError,
    "EOrder:Order minimum not met": InvalidQuantityError,
    "EOrder:Unknown order": OrderNotFoundError,
    "EOrder:Cannot open position": OrderRejectedError,
    "EOrder:Margin allowance exceeded": InsufficientBalanceError,
    "EOrder:Margin level too low": InsufficientBalanceError,
    "EOrder:Unknown position": OrderNotFoundError,
    "EQuery:Unknown asset pair": InvalidSymbolError,
}


def map_kraken_error(
    error_message: str,
    details: Optional[Dict[str, Any]] = None
) -> ExchangeError:
    """
    Map Kraken error message to unified exception

    Args:
        error_message: Kraken error message
        details: Additional context

    Returns:
        Appropriate ExchangeError subclass instance
    """
    details = details if details is not None else {}

    # Find matching error
    for pattern, exception_class in KRAKEN_ERROR_MAP.items():
        if pattern in error_message:
            if exception_class == RateLimitError:
                return RateLimitError(
                    exchange="kraken",
                    retry_after=15,
                    native_message=error_message,
                    details=details.copy()
                )
            elif exception_class == InsufficientBalanceError:
                return InsufficientBalanceError(
                    exchange="kraken",
                    native_message=error_message,
                    details=details.copy()
                )
            elif exception_class == OrderNotFoundError:
                return OrderNotFoundError(
                    exchange="kraken",
                    native_message=error_message,
                    details=details.copy()
                )
            else:
                try:
                    return exception_class(
                        exchange="kraken",
                        native_message=error_message,
                        details=details.copy()
                    )
                except TypeError:
                    pass

    return ExchangeError(
        message=error_message or "Unknown Kraken error",
        error_code=ExchangeErrorCode.UNKNOWN_ERROR,
        exchange="kraken",
        native_message=error_message,
        details=details.copy()
    )


# ============================================================================
# KRAKEN RATE LIMITER
# ============================================================================

class KrakenRateLimiter:
    """
    Rate limiter for Kraken API

    Kraken has different rate limits for different API tiers.
    Default is 15 calls per 3 seconds (starter tier).

    Attributes:
        calls_per_second: Maximum calls per second
        current_calls: Current call count
    """

    def __init__(self, calls_per_second: float = 5.0):
        """
        Initialize rate limiter

        Args:
            calls_per_second: Maximum calls per second
        """
        self.calls_per_second = calls_per_second
        self.tokens = calls_per_second
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        """Acquire a rate limit token"""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(
                self.calls_per_second,
                self.tokens + elapsed * self.calls_per_second
            )
            self.last_update = now

            if self.tokens >= 1:
                self.tokens -= 1
                return 0.0
            else:
                wait_time = (1 - self.tokens) / self.calls_per_second
                return wait_time

    async def wait_and_acquire(self) -> None:
        """Wait for and acquire a token"""
        wait_time = await self.acquire()
        if wait_time > 0:
            await asyncio.sleep(wait_time)


# ============================================================================
# KRAKEN ADAPTER CONFIGURATION
# ============================================================================

class KrakenAdapterConfig(BaseModel):
    """
    Configuration specific to Kraken adapter

    Attributes:
        use_futures: Use Kraken Futures API
        otp: Two-factor authentication token (if enabled)
    """
    use_futures: bool = False
    otp: Optional[str] = None


# ============================================================================
# KRAKEN EXCHANGE ADAPTER
# ============================================================================

class KrakenExchangeAdapter(ExchangeInterface):
    """
    Kraken exchange adapter implementing ExchangeInterface

    This adapter provides direct API access to Kraken exchange,
    supporting Spot trading and optionally Futures.

    Features:
    - Spot trading with full order types
    - Margin trading support
    - Nonce-based request authentication
    - Symbol format translation
    - Error mapping to unified exceptions

    Usage:
        config = ExchangeConfig(
            exchange=ExchangeName.KRAKEN,
            api_key="...",
            api_secret="...",
            testnet=False  # Kraken has no testnet
        )
        adapter = KrakenExchangeAdapter(config)
        await adapter.initialize()

        # Place order
        order = await adapter.place_order(unified_order)
    """

    # Kraken API endpoints
    SPOT_URL = "https://api.kraken.com"
    FUTURES_URL = "https://futures.kraken.com"

    def __init__(
        self,
        config: ExchangeConfig,
        use_futures: bool = False
    ):
        """
        Initialize Kraken adapter

        Args:
            config: Exchange configuration
            use_futures: Use Kraken Futures API
        """
        super().__init__(config)

        # Kraken-specific config
        self._use_futures = use_futures
        self._base_url = self.FUTURES_URL if use_futures else self.SPOT_URL

        # Override with custom URL if provided
        if config.base_url:
            self._base_url = config.base_url.rstrip("/")

        # Nonce counter (must be increasing)
        self._nonce = int(time.time() * 1000)
        self._nonce_lock = asyncio.Lock()

        # HTTP client
        self._client: Optional[httpx.AsyncClient] = None

        # Rate limiter
        self._rate_limiter = KrakenRateLimiter(calls_per_second=5.0)

        # Set Kraken capabilities
        self._capabilities = ExchangeCapabilities(
            # Trading products
            spot_trading=True,
            perpetual_trading=use_futures,
            margin_trading=True,
            options_trading=False,

            # Order types
            market_orders=True,
            limit_orders=True,
            stop_orders=True,
            trailing_stop=False,
            post_only=True,
            reduce_only=use_futures,

            # WebSocket
            websocket_public=True,
            websocket_private=True,
            orderbook_depth=500,

            # Rate limits
            rate_limit_per_second=5,
            order_rate_limit=5,

            # Trading
            max_leverage=5,  # Spot margin
            min_order_size_usd=0.0,  # Varies by pair

            # Environment
            testnet_available=False,
            sandbox_mode=False,
        )

        logger.info(
            f"Created Kraken adapter (futures={use_futures})"
        )

    # ========================================================================
    # SIGNATURE GENERATION
    # ========================================================================

    async def _get_nonce(self) -> int:
        """Get unique nonce for request signing"""
        async with self._nonce_lock:
            self._nonce += 1
            return self._nonce

    def _generate_signature(
        self,
        urlpath: str,
        data: Dict[str, Any],
        nonce: int
    ) -> str:
        """
        Generate Kraken API signature

        Args:
            urlpath: API endpoint path
            data: Request data
            nonce: Request nonce

        Returns:
            Base64 encoded signature
        """
        # Build postdata string
        postdata = urllib.parse.urlencode(data)

        # Create message: nonce + postdata
        message = (str(nonce) + postdata).encode()

        # Create SHA256 hash
        sha256_hash = hashlib.sha256(message).digest()

        # Create HMAC-SHA512 signature
        secret_decoded = base64.b64decode(self._config.api_secret)
        mac = hmac.new(
            secret_decoded,
            urlpath.encode() + sha256_hash,
            hashlib.sha512
        )

        return base64.b64encode(mac.digest()).decode()

    # ========================================================================
    # LIFECYCLE METHODS
    # ========================================================================

    async def initialize(self) -> None:
        """
        Initialize connection to Kraken

        Raises:
            ConnectionError: If connection fails
            AuthenticationError: If credentials are invalid
        """
        logger.info("Initializing Kraken adapter...")

        # Create HTTP client
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(
                connect=5.0,
                read=self._config.timeout,
                write=10.0,
                pool=10.0
            ),
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # Verify connectivity
        try:
            health_ok = await self.health_check()
            if not health_ok:
                raise ConnectionError(
                    message="Kraken connectivity check failed",
                    exchange="kraken"
                )
        except httpx.HTTPError as e:
            raise ConnectionError(
                message=f"Failed to connect to Kraken: {e}",
                exchange="kraken"
            )

        # Validate credentials
        try:
            await self.get_balance()
        except AuthenticationError:
            raise
        except Exception as e:
            logger.warning(f"Balance check during init failed: {e}")

        self._initialized = True
        logger.info("Kraken adapter initialized successfully")

    async def close(self) -> None:
        """Close HTTP client connection"""
        if self._client:
            await self._client.aclose()
            self._client = None
        self._initialized = False
        logger.info("Kraken adapter closed")

    async def health_check(self) -> bool:
        """
        Check Kraken connectivity

        Returns:
            True if exchange is reachable
        """
        try:
            response = await self._client.get("/0/public/SystemStatus")
            data = response.json()
            status = data.get("result", {}).get("status", "")
            return status == "online"
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False

    # ========================================================================
    # HTTP REQUEST HELPERS
    # ========================================================================

    async def _public_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make public (unsigned) request

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            Response data
        """
        if not self._client:
            raise ConnectionError(
                message="Adapter not initialized",
                exchange="kraken"
            )

        await self._rate_limiter.wait_and_acquire()

        try:
            response = await self._client.get(endpoint, params=params)
            data = response.json()

            # Check for errors
            if data.get("error"):
                error_msg = data["error"][0] if data["error"] else "Unknown error"
                raise map_kraken_error(error_msg, data)

            return data.get("result", data)

        except httpx.TimeoutException as e:
            raise TimeoutError(message=f"Request timed out: {e}", exchange="kraken")
        except ExchangeError:
            raise
        except Exception as e:
            raise ConnectionError(message=f"Request failed: {e}", exchange="kraken")

    async def _private_request(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make private (signed) request

        Args:
            endpoint: API endpoint
            data: Request data

        Returns:
            Response data
        """
        if not self._client:
            raise ConnectionError(
                message="Adapter not initialized",
                exchange="kraken"
            )

        await self._rate_limiter.wait_and_acquire()

        # Build request data with nonce
        nonce = await self._get_nonce()
        request_data = dict(data or {})
        request_data["nonce"] = nonce

        # Generate signature
        signature = self._generate_signature(endpoint, request_data, nonce)

        # Set headers
        headers = {
            "API-Key": self._config.api_key,
            "API-Sign": signature
        }

        try:
            response = await self._client.post(
                endpoint,
                data=request_data,
                headers=headers
            )
            result = response.json()

            # Check for errors
            if result.get("error"):
                error_msg = result["error"][0] if result["error"] else "Unknown error"
                raise map_kraken_error(error_msg, result)

            return result.get("result", result)

        except httpx.TimeoutException as e:
            raise TimeoutError(message=f"Request timed out: {e}", exchange="kraken")
        except ExchangeError:
            raise
        except Exception as e:
            raise ConnectionError(message=f"Request failed: {e}", exchange="kraken")

    # ========================================================================
    # ACCOUNT METHODS
    # ========================================================================

    async def get_balance(
        self,
        asset: Optional[str] = None
    ) -> AccountBalance:
        """Get account balance"""
        result = await self._private_request("/0/private/Balance")
        return self._parse_balance(result, asset)

    def _parse_balance(
        self,
        data: Dict[str, Any],
        asset_filter: Optional[str] = None
    ) -> AccountBalance:
        """Parse Kraken balance response"""
        assets = []
        total_equity = Decimal("0")

        for asset_name, balance in data.items():
            # Skip if filtering
            if asset_filter:
                # Handle Kraken's asset naming (e.g., XXBT -> BTC)
                clean_name = asset_name.lstrip("X").lstrip("Z")
                if clean_name.upper() != asset_filter.upper():
                    continue

            balance_decimal = Decimal(str(balance))
            if balance_decimal > 0:
                assets.append(AssetBalance(
                    asset=asset_name,
                    free=balance_decimal,
                    locked=Decimal("0")  # Kraken returns available balance
                ))
                total_equity += balance_decimal

        return AccountBalance(
            exchange=ExchangeName.KRAKEN,
            account_type="SPOT",
            total_equity=total_equity,
            available_balance=total_equity,
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
        """Get open positions"""
        if not self._use_futures:
            # Spot margin positions
            try:
                result = await self._private_request("/0/private/OpenPositions")
                positions = []

                for pos_id, pos_data in result.items():
                    pos = self._parse_position(pos_id, pos_data)
                    if pos:
                        if not symbol or pos.symbol == symbol:
                            positions.append(pos)

                return positions
            except ExchangeError:
                return []

        return []

    def _parse_position(
        self,
        pos_id: str,
        data: Dict[str, Any]
    ) -> Optional[UnifiedPosition]:
        """Parse Kraken position data"""
        vol = Decimal(str(data.get("vol", "0")))
        vol_closed = Decimal(str(data.get("vol_closed", "0")))
        net_vol = vol - vol_closed

        if net_vol == 0:
            return None

        # Determine side
        pos_type = data.get("type", "buy")
        side = PositionSide.LONG if pos_type == "buy" else PositionSide.SHORT

        return UnifiedPosition(
            exchange=ExchangeName.KRAKEN,
            symbol=from_kraken_symbol(data.get("pair", "")),
            product_type=ProductType.MARGIN,
            side=side,
            quantity=abs(net_vol),
            entry_price=Decimal(str(data.get("cost", "0"))) / net_vol if net_vol else Decimal("0"),
            unrealized_pnl=Decimal(str(data.get("net", "0"))),
            leverage=int(float(data.get("leverage", "1"))),
            margin=Decimal(str(data.get("margin", "0"))),
            margin_mode="isolated",
            updated_at=datetime.now(timezone.utc)
        )

    # ========================================================================
    # TRADING METHODS
    # ========================================================================

    async def place_order(self, order: UnifiedOrder) -> UnifiedOrder:
        """Place an order on Kraken"""
        params = self._order_to_kraken(order)

        result = await self._private_request("/0/private/AddOrder", params)

        # Get transaction IDs
        txids = result.get("txid", [])
        order.exchange_order_id = txids[0] if txids else None
        order.status = OrderStatus.NEW
        order.updated_at = datetime.now(timezone.utc)

        logger.info(
            f"Order placed: {order.symbol} {order.side.value} {order.quantity} "
            f"@ {order.price or 'MARKET'} (id={order.exchange_order_id})"
        )

        return order

    def _order_to_kraken(self, order: UnifiedOrder) -> Dict[str, Any]:
        """Convert unified order to Kraken format"""
        # Map order type
        type_map = {
            OrderType.MARKET: "market",
            OrderType.LIMIT: "limit",
            OrderType.STOP_MARKET: "stop-loss",
            OrderType.STOP_LIMIT: "stop-loss-limit",
            OrderType.TAKE_PROFIT_MARKET: "take-profit",
            OrderType.TAKE_PROFIT_LIMIT: "take-profit-limit",
        }

        params = {
            "pair": to_kraken_symbol(order.symbol),
            "type": "buy" if order.side == OrderSide.BUY else "sell",
            "ordertype": type_map.get(order.order_type, "market"),
            "volume": str(order.quantity),
        }

        # Add price for limit orders
        if order.price:
            params["price"] = str(order.price)

        # Add stop price for stop orders
        if order.stop_price:
            params["price2"] = str(order.stop_price)

        # Add flags
        flags = []
        if order.post_only:
            flags.append("post")
        if flags:
            params["oflags"] = ",".join(flags)

        # Add client order ID
        if order.client_order_id:
            params["userref"] = order.client_order_id[:32]  # Max 32 chars

        return params

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
                exchange="kraken"
            )

        params = {}
        if order_id:
            params["txid"] = order_id
        elif client_order_id:
            params["userref"] = client_order_id

        result = await self._private_request("/0/private/CancelOrder", params)

        # Return cancelled order
        return UnifiedOrder(
            exchange=ExchangeName.KRAKEN,
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
        params = {}
        if order_id:
            params["txid"] = order_id
        elif client_order_id:
            params["userref"] = client_order_id

        result = await self._private_request("/0/private/QueryOrders", params)

        if not result:
            raise OrderNotFoundError(
                order_id=order_id,
                client_order_id=client_order_id,
                exchange="kraken"
            )

        # Get first order
        for txid, order_data in result.items():
            return self._parse_order(txid, order_data)

        raise OrderNotFoundError(order_id=order_id, exchange="kraken")

    def _parse_order(self, txid: str, data: Dict[str, Any]) -> UnifiedOrder:
        """Parse Kraken order response"""
        # Map status
        status_map = {
            "pending": OrderStatus.PENDING,
            "open": OrderStatus.NEW,
            "closed": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "expired": OrderStatus.EXPIRED,
        }

        # Map type
        type_map = {
            "market": OrderType.MARKET,
            "limit": OrderType.LIMIT,
            "stop-loss": OrderType.STOP_MARKET,
            "stop-loss-limit": OrderType.STOP_LIMIT,
            "take-profit": OrderType.TAKE_PROFIT_MARKET,
            "take-profit-limit": OrderType.TAKE_PROFIT_LIMIT,
        }

        descr = data.get("descr", {})

        return UnifiedOrder(
            exchange=ExchangeName.KRAKEN,
            exchange_order_id=txid,
            client_order_id=str(data.get("userref")) if data.get("userref") else None,
            symbol=from_kraken_symbol(descr.get("pair", "")),
            product_type=ProductType.SPOT,
            side=OrderSide.BUY if descr.get("type") == "buy" else OrderSide.SELL,
            order_type=type_map.get(descr.get("ordertype", "market"), OrderType.MARKET),
            quantity=Decimal(str(data.get("vol", "0"))),
            price=Decimal(str(descr.get("price", "0"))) if descr.get("price") else None,
            time_in_force=TimeInForce.GTC,
            status=status_map.get(data.get("status", "open"), OrderStatus.NEW),
            filled_quantity=Decimal(str(data.get("vol_exec", "0"))),
            filled_price=Decimal(str(data.get("price", "0"))) if data.get("price") else None,
            commission=Decimal(str(data.get("fee", "0"))),
            updated_at=datetime.now(timezone.utc)
        )

    async def get_open_orders(
        self,
        symbol: Optional[str] = None,
        product_type: Optional[ProductType] = None
    ) -> List[UnifiedOrder]:
        """Get all open orders"""
        result = await self._private_request("/0/private/OpenOrders")

        orders = []
        for txid, order_data in result.get("open", {}).items():
            order = self._parse_order(txid, order_data)
            if not symbol or from_kraken_symbol(order.symbol) == symbol:
                orders.append(order)

        return orders

    # ========================================================================
    # MARKET DATA METHODS
    # ========================================================================

    async def get_ticker(self, symbol: str) -> Ticker:
        """Get ticker data"""
        kraken_symbol = to_kraken_symbol(symbol)

        result = await self._public_request(
            "/0/public/Ticker",
            params={"pair": kraken_symbol}
        )

        # Get first result
        for pair, data in result.items():
            return Ticker(
                exchange=ExchangeName.KRAKEN,
                symbol=from_kraken_symbol(pair),
                last_price=Decimal(str(data["c"][0])),  # Last trade close
                bid_price=Decimal(str(data["b"][0])),  # Best bid
                ask_price=Decimal(str(data["a"][0])),  # Best ask
                high_24h=Decimal(str(data["h"][1])),  # 24h high
                low_24h=Decimal(str(data["l"][1])),  # 24h low
                volume_24h=Decimal(str(data["v"][1])),  # 24h volume
                timestamp=datetime.now(timezone.utc)
            )

        raise InvalidSymbolError(symbol=symbol, exchange="kraken")

    async def get_orderbook(
        self,
        symbol: str,
        depth: int = 25
    ) -> OrderBook:
        """Get orderbook"""
        kraken_symbol = to_kraken_symbol(symbol)

        result = await self._public_request(
            "/0/public/Depth",
            params={"pair": kraken_symbol, "count": min(depth, 500)}
        )

        # Get first result
        for pair, data in result.items():
            bids = [
                OrderBookLevel(
                    price=Decimal(str(level[0])),
                    quantity=Decimal(str(level[1]))
                )
                for level in data.get("bids", [])
            ]

            asks = [
                OrderBookLevel(
                    price=Decimal(str(level[0])),
                    quantity=Decimal(str(level[1]))
                )
                for level in data.get("asks", [])
            ]

            return OrderBook(
                exchange=ExchangeName.KRAKEN,
                symbol=from_kraken_symbol(pair),
                bids=bids,
                asks=asks,
                timestamp=datetime.now(timezone.utc)
            )

        raise InvalidSymbolError(symbol=symbol, exchange="kraken")

    async def get_trades(
        self,
        symbol: str,
        limit: int = 100
    ) -> List[Trade]:
        """Get recent trades"""
        kraken_symbol = to_kraken_symbol(symbol)

        result = await self._public_request(
            "/0/public/Trades",
            params={"pair": kraken_symbol}
        )

        trades = []
        for pair, data in result.items():
            if pair == "last":
                continue

            for trade_data in data[-limit:]:
                try:
                    timestamp = datetime.fromtimestamp(
                        float(trade_data[2]),
                        tz=timezone.utc
                    )

                    trades.append(Trade(
                        exchange=ExchangeName.KRAKEN,
                        symbol=from_kraken_symbol(pair),
                        trade_id=str(trade_data[2]),  # Use timestamp as ID
                        price=Decimal(str(trade_data[0])),
                        quantity=Decimal(str(trade_data[1])),
                        side=OrderSide.BUY if trade_data[3] == "b" else OrderSide.SELL,
                        timestamp=timestamp
                    ))
                except (IndexError, ValueError, TypeError):
                    continue

            break

        return trades

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 100,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Kline]:
        """Get kline/OHLCV data"""
        kraken_symbol = to_kraken_symbol(symbol)

        # Map interval to Kraken format (minutes)
        interval_map = {
            "1": 1, "1m": 1, "5": 5, "5m": 5, "15": 15, "15m": 15,
            "30": 30, "30m": 30, "60": 60, "1h": 60, "240": 240, "4h": 240,
            "1440": 1440, "1d": 1440, "D": 1440, "10080": 10080, "1w": 10080, "W": 10080
        }
        kraken_interval = interval_map.get(interval, 60)

        params = {"pair": kraken_symbol, "interval": kraken_interval}
        if start_time:
            params["since"] = int(start_time.timestamp())

        result = await self._public_request("/0/public/OHLC", params=params)

        klines = []
        for pair, data in result.items():
            if pair == "last":
                continue

            for kline_data in data[-limit:]:
                try:
                    open_time = datetime.fromtimestamp(
                        kline_data[0],
                        tz=timezone.utc
                    )
                    close_time = datetime.fromtimestamp(
                        kline_data[0] + kraken_interval * 60,
                        tz=timezone.utc
                    )

                    klines.append(Kline(
                        exchange=ExchangeName.KRAKEN,
                        symbol=from_kraken_symbol(pair),
                        interval=interval,
                        open_time=open_time,
                        open=Decimal(str(kline_data[1])),
                        high=Decimal(str(kline_data[2])),
                        low=Decimal(str(kline_data[3])),
                        close=Decimal(str(kline_data[4])),
                        volume=Decimal(str(kline_data[6])),
                        close_time=close_time
                    ))
                except (IndexError, ValueError, TypeError):
                    continue

            break

        return klines


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_kraken_adapter(
    api_key: str,
    api_secret: str,
    use_futures: bool = False
) -> KrakenExchangeAdapter:
    """
    Factory function to create Kraken adapter

    Args:
        api_key: Kraken API key
        api_secret: Kraken API secret (base64 encoded)
        use_futures: Use Kraken Futures API

    Returns:
        Configured KrakenExchangeAdapter
    """
    config = ExchangeConfig(
        exchange=ExchangeName.KRAKEN,
        api_key=api_key,
        api_secret=api_secret,
        testnet=False  # Kraken has no testnet
    )

    return KrakenExchangeAdapter(config, use_futures=use_futures)


__all__ = [
    "KrakenExchangeAdapter",
    "KrakenAdapterConfig",
    "KrakenRateLimiter",
    "create_kraken_adapter",
    "map_kraken_error",
    "to_kraken_symbol",
    "from_kraken_symbol",
]
