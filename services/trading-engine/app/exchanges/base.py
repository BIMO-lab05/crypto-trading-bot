"""
Exchange Base Module - Phase 6: Multi-Exchange Support
Purpose: Abstract base class and unified data models for exchange adapters

This module provides:
- ExchangeInterface: Abstract base class defining standard exchange operations
- Unified data models for orders, balances, positions, and market data
- ExchangeConfig: Configuration for exchange connections
- ExchangeCapabilities: Feature flags for exchange-specific capabilities

Architecture:
    +-------------------+
    | ExchangeInterface |  <- Abstract base
    +--------+----------+
             |
    +--------+----------+----------+
    |        |          |          |
    v        v          v          v
  Bybit   Binance    OKX      FTX (etc.)

Created: 2025-12-11
Author: Backend Developer Agent
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    TypeVar,
    Union
)
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, ConfigDict, field_validator

# Configure logger
logger = logging.getLogger(__name__)


# ============================================================================
# ENUMERATIONS
# ============================================================================

class ExchangeName(str, Enum):
    """
    Supported exchange identifiers

    Each exchange adapter must identify itself with one of these values.
    """
    BYBIT = "bybit"
    BINANCE = "binance"
    OKX = "okx"
    KRAKEN = "kraken"
    COINBASE = "coinbase"
    KUCOIN = "kucoin"
    GATE = "gate"
    HUOBI = "huobi"
    MEXC = "mexc"
    BITGET = "bitget"


class ProductType(str, Enum):
    """
    Trading product categories

    Different exchanges may use different names for these,
    adapters handle the mapping.
    """
    SPOT = "spot"
    LINEAR = "linear"  # USDT-margined perpetuals
    INVERSE = "inverse"  # Coin-margined perpetuals
    OPTION = "option"
    MARGIN = "margin"


class OrderSide(str, Enum):
    """Order side (direction)"""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order types supported across exchanges"""
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"
    TAKE_PROFIT_MARKET = "take_profit_market"
    TAKE_PROFIT_LIMIT = "take_profit_limit"
    TRAILING_STOP = "trailing_stop"


class TimeInForce(str, Enum):
    """Time in force options for orders"""
    GTC = "gtc"  # Good Till Cancel
    IOC = "ioc"  # Immediate or Cancel
    FOK = "fok"  # Fill or Kill
    POST_ONLY = "post_only"  # Maker only


class OrderStatus(str, Enum):
    """Unified order status"""
    PENDING = "pending"
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class PositionSide(str, Enum):
    """Position side for futures"""
    LONG = "long"
    SHORT = "short"
    BOTH = "both"  # One-way mode


# ============================================================================
# EXCHANGE CAPABILITIES
# ============================================================================

@dataclass
class ExchangeCapabilities:
    """
    Feature flags indicating exchange-specific capabilities

    Adapters set these flags during initialization to inform
    the trading engine which features are available.

    Attributes:
        spot_trading: Supports spot market trading
        perpetual_trading: Supports perpetual futures
        margin_trading: Supports margin trading
        options_trading: Supports options trading

        market_orders: Supports market order type
        limit_orders: Supports limit order type
        stop_orders: Supports stop orders (stop-loss, take-profit)
        trailing_stop: Supports trailing stop orders
        post_only: Supports post-only (maker) orders
        reduce_only: Supports reduce-only flag

        websocket_public: Has public WebSocket feeds
        websocket_private: Has private WebSocket feeds
        orderbook_depth: Maximum orderbook depth available

        rate_limit_per_second: Requests allowed per second
        order_rate_limit: Orders allowed per second

        max_leverage: Maximum leverage available
        min_order_size_usd: Minimum order size in USD equivalent

        testnet_available: Has testnet environment
        sandbox_mode: Supports sandbox/demo trading
    """
    # Trading products
    spot_trading: bool = False
    perpetual_trading: bool = False
    margin_trading: bool = False
    options_trading: bool = False

    # Order types
    market_orders: bool = True
    limit_orders: bool = True
    stop_orders: bool = False
    trailing_stop: bool = False
    post_only: bool = False
    reduce_only: bool = False

    # WebSocket support
    websocket_public: bool = False
    websocket_private: bool = False
    orderbook_depth: int = 25

    # Rate limits
    rate_limit_per_second: int = 10
    order_rate_limit: int = 10

    # Trading parameters
    max_leverage: int = 100
    min_order_size_usd: float = 1.0

    # Environment options
    testnet_available: bool = False
    sandbox_mode: bool = False

    def supports(self, feature: str) -> bool:
        """
        Check if exchange supports a specific feature

        Args:
            feature: Feature name (attribute name)

        Returns:
            True if feature is supported
        """
        return getattr(self, feature, False)


# ============================================================================
# EXCHANGE CONFIGURATION
# ============================================================================

class ExchangeConfig(BaseModel):
    """
    Configuration for exchange connection

    This configuration is passed to exchange adapters during initialization.
    All sensitive values (API keys) should come from environment variables.

    Attributes:
        exchange: Exchange identifier
        api_key: API key for authentication
        api_secret: API secret for signing
        passphrase: Additional passphrase (required by some exchanges)
        testnet: Use testnet/sandbox environment
        base_url: Override default API URL
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts for failed requests
        proxy: HTTP proxy URL if required
    """
    exchange: ExchangeName = Field(description="Exchange identifier")
    api_key: str = Field(description="API key for authentication")
    api_secret: str = Field(description="API secret for signing")
    passphrase: Optional[str] = Field(
        default=None,
        description="Additional passphrase (OKX, Coinbase)"
    )
    testnet: bool = Field(
        default=True,
        description="Use testnet environment"
    )
    base_url: Optional[str] = Field(
        default=None,
        description="Custom API base URL"
    )
    timeout: float = Field(
        default=30.0,
        ge=5.0,
        le=120.0,
        description="Request timeout in seconds"
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts"
    )
    proxy: Optional[str] = Field(
        default=None,
        description="HTTP proxy URL"
    )

    # Product configuration
    default_product: ProductType = Field(
        default=ProductType.LINEAR,
        description="Default product type for trading"
    )

    model_config = ConfigDict(
        extra="ignore",
        validate_assignment=True
    )

    @field_validator("api_key", "api_secret")
    @classmethod
    def validate_credentials(cls, v: str) -> str:
        """Validate that credentials are not empty"""
        if not v or not v.strip():
            raise ValueError("API credentials cannot be empty")
        return v.strip()


# ============================================================================
# UNIFIED ORDER MODEL
# ============================================================================

class UnifiedOrder(BaseModel):
    """
    Unified order model that works across all exchanges

    This model is the standard format for orders in the trading engine.
    Exchange adapters handle conversion to/from exchange-specific formats.

    Attributes:
        id: Internal order ID (UUID)
        exchange_order_id: Order ID assigned by exchange
        client_order_id: Custom order ID (for tracking)
        exchange: Exchange where order was placed
        symbol: Trading pair symbol
        product_type: Product category (spot, linear, etc.)
        side: Order side (buy/sell)
        order_type: Order type (market, limit, etc.)
        quantity: Order quantity
        price: Limit price (required for limit orders)
        stop_price: Trigger price for stop orders
        time_in_force: Time in force option
        reduce_only: Reduce position only flag
        post_only: Post only (maker) flag
        status: Current order status
        filled_quantity: Quantity filled so far
        filled_price: Average fill price
        commission: Trading commission paid
        commission_asset: Asset used for commission
        created_at: Order creation timestamp
        updated_at: Last update timestamp
    """
    # Identifiers
    id: UUID = Field(default_factory=uuid4, description="Internal order ID")
    exchange_order_id: Optional[str] = Field(
        default=None,
        description="Exchange-assigned order ID"
    )
    client_order_id: Optional[str] = Field(
        default=None,
        max_length=36,
        description="Custom client order ID"
    )

    # Exchange info
    exchange: ExchangeName = Field(description="Exchange identifier")
    symbol: str = Field(min_length=1, description="Trading pair symbol")
    product_type: ProductType = Field(
        default=ProductType.LINEAR,
        description="Product category"
    )

    # Order parameters
    side: OrderSide = Field(description="Order side")
    order_type: OrderType = Field(description="Order type")
    quantity: Decimal = Field(gt=0, description="Order quantity")
    price: Optional[Decimal] = Field(
        default=None,
        description="Limit price"
    )
    stop_price: Optional[Decimal] = Field(
        default=None,
        description="Stop/trigger price"
    )
    time_in_force: TimeInForce = Field(
        default=TimeInForce.GTC,
        description="Time in force"
    )

    # Flags
    reduce_only: bool = Field(
        default=False,
        description="Reduce position only"
    )
    post_only: bool = Field(
        default=False,
        description="Post only (maker)"
    )

    # Status
    status: OrderStatus = Field(
        default=OrderStatus.PENDING,
        description="Order status"
    )
    filled_quantity: Decimal = Field(
        default=Decimal("0"),
        description="Filled quantity"
    )
    filled_price: Optional[Decimal] = Field(
        default=None,
        description="Average fill price"
    )

    # Commission
    commission: Decimal = Field(
        default=Decimal("0"),
        description="Commission paid"
    )
    commission_asset: Optional[str] = Field(
        default=None,
        description="Commission asset"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Update timestamp"
    )

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True
    )

    @property
    def is_filled(self) -> bool:
        """Check if order is fully filled"""
        return self.status == OrderStatus.FILLED

    @property
    def is_open(self) -> bool:
        """Check if order is still active"""
        return self.status in (
            OrderStatus.PENDING,
            OrderStatus.NEW,
            OrderStatus.PARTIALLY_FILLED
        )

    @property
    def remaining_quantity(self) -> Decimal:
        """Calculate remaining quantity to fill"""
        return self.quantity - self.filled_quantity

    @property
    def fill_percentage(self) -> float:
        """Calculate fill percentage"""
        if self.quantity == 0:
            return 0.0
        return float(self.filled_quantity / self.quantity * 100)

    def to_exchange_format(self, exchange: ExchangeName) -> Dict[str, Any]:
        """
        Convert to exchange-specific format

        This is a placeholder - actual conversion is done in adapters.

        Args:
            exchange: Target exchange

        Returns:
            Exchange-specific order dict
        """
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "type": self.order_type.value,
            "quantity": str(self.quantity),
            "price": str(self.price) if self.price else None,
            "timeInForce": self.time_in_force.value,
        }


# ============================================================================
# BALANCE MODEL
# ============================================================================

class AssetBalance(BaseModel):
    """
    Single asset balance

    Attributes:
        asset: Asset/coin symbol
        free: Available balance
        locked: Balance locked in orders
        total: Total balance
    """
    asset: str = Field(description="Asset symbol")
    free: Decimal = Field(default=Decimal("0"), description="Available balance")
    locked: Decimal = Field(default=Decimal("0"), description="Locked in orders")

    @property
    def total(self) -> Decimal:
        """Calculate total balance"""
        return self.free + self.locked


class AccountBalance(BaseModel):
    """
    Account balance information

    Attributes:
        exchange: Exchange identifier
        account_type: Account type (spot, futures, etc.)
        total_equity: Total account equity in USD
        available_balance: Available balance in USD
        used_margin: Used margin for positions
        unrealized_pnl: Unrealized P&L from positions
        assets: Individual asset balances
        updated_at: Last update timestamp
    """
    exchange: ExchangeName = Field(description="Exchange identifier")
    account_type: str = Field(
        default="UNIFIED",
        description="Account type"
    )

    # USD values
    total_equity: Decimal = Field(
        default=Decimal("0"),
        description="Total equity USD"
    )
    available_balance: Decimal = Field(
        default=Decimal("0"),
        description="Available balance USD"
    )
    used_margin: Decimal = Field(
        default=Decimal("0"),
        description="Used margin"
    )
    unrealized_pnl: Decimal = Field(
        default=Decimal("0"),
        description="Unrealized P&L"
    )

    # Individual assets
    assets: List[AssetBalance] = Field(
        default_factory=list,
        description="Asset balances"
    )

    # Metadata
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Update timestamp"
    )

    model_config = ConfigDict(from_attributes=True)

    def get_asset(self, symbol: str) -> Optional[AssetBalance]:
        """Get balance for specific asset"""
        for asset in self.assets:
            if asset.asset.upper() == symbol.upper():
                return asset
        return None


# ============================================================================
# POSITION MODEL
# ============================================================================

class UnifiedPosition(BaseModel):
    """
    Unified position model for futures/perpetuals

    Attributes:
        exchange: Exchange identifier
        symbol: Trading pair
        product_type: Product category
        side: Position side (long/short)
        quantity: Position size
        entry_price: Average entry price
        mark_price: Current mark price
        liquidation_price: Liquidation price
        unrealized_pnl: Current unrealized P&L
        realized_pnl: Realized P&L
        leverage: Position leverage
        margin: Position margin
        margin_mode: Margin mode (cross/isolated)
        updated_at: Last update timestamp
    """
    exchange: ExchangeName = Field(description="Exchange identifier")
    symbol: str = Field(description="Trading pair")
    product_type: ProductType = Field(
        default=ProductType.LINEAR,
        description="Product type"
    )

    side: PositionSide = Field(description="Position side")
    quantity: Decimal = Field(description="Position size")
    entry_price: Decimal = Field(description="Entry price")
    mark_price: Optional[Decimal] = Field(
        default=None,
        description="Mark price"
    )
    liquidation_price: Optional[Decimal] = Field(
        default=None,
        description="Liquidation price"
    )

    # P&L
    unrealized_pnl: Decimal = Field(
        default=Decimal("0"),
        description="Unrealized P&L"
    )
    realized_pnl: Decimal = Field(
        default=Decimal("0"),
        description="Realized P&L"
    )

    # Leverage/margin
    leverage: int = Field(default=1, ge=1, description="Leverage")
    margin: Decimal = Field(
        default=Decimal("0"),
        description="Position margin"
    )
    margin_mode: str = Field(
        default="cross",
        description="Margin mode"
    )

    # Metadata
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Update timestamp"
    )

    model_config = ConfigDict(from_attributes=True)

    @property
    def is_long(self) -> bool:
        """Check if position is long"""
        return self.side == PositionSide.LONG

    @property
    def notional_value(self) -> Decimal:
        """Calculate position notional value"""
        return abs(self.quantity * self.entry_price)


# ============================================================================
# MARKET DATA MODELS
# ============================================================================

class Ticker(BaseModel):
    """
    Ticker/price data

    Attributes:
        exchange: Exchange identifier
        symbol: Trading pair
        last_price: Last traded price
        bid_price: Best bid price
        ask_price: Best ask price
        high_24h: 24h high
        low_24h: 24h low
        volume_24h: 24h volume
        change_24h: 24h change percentage
        timestamp: Data timestamp
    """
    exchange: ExchangeName = Field(description="Exchange")
    symbol: str = Field(description="Symbol")

    last_price: Decimal = Field(description="Last price")
    bid_price: Optional[Decimal] = Field(default=None, description="Best bid")
    ask_price: Optional[Decimal] = Field(default=None, description="Best ask")

    high_24h: Optional[Decimal] = Field(default=None, description="24h high")
    low_24h: Optional[Decimal] = Field(default=None, description="24h low")
    volume_24h: Optional[Decimal] = Field(default=None, description="24h volume")
    change_24h: Optional[float] = Field(default=None, description="24h change %")

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp"
    )

    model_config = ConfigDict(from_attributes=True)

    @property
    def spread(self) -> Optional[Decimal]:
        """Calculate bid-ask spread"""
        if self.bid_price and self.ask_price:
            return self.ask_price - self.bid_price
        return None

    @property
    def mid_price(self) -> Optional[Decimal]:
        """Calculate mid price"""
        if self.bid_price and self.ask_price:
            return (self.bid_price + self.ask_price) / 2
        return self.last_price


class OrderBookLevel(BaseModel):
    """Single level in orderbook"""
    price: Decimal = Field(description="Price level")
    quantity: Decimal = Field(description="Quantity at level")


class OrderBook(BaseModel):
    """
    Order book snapshot

    Attributes:
        exchange: Exchange identifier
        symbol: Trading pair
        bids: Bid levels (price, quantity)
        asks: Ask levels (price, quantity)
        timestamp: Snapshot timestamp
    """
    exchange: ExchangeName = Field(description="Exchange")
    symbol: str = Field(description="Symbol")

    bids: List[OrderBookLevel] = Field(
        default_factory=list,
        description="Bid levels"
    )
    asks: List[OrderBookLevel] = Field(
        default_factory=list,
        description="Ask levels"
    )

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp"
    )

    model_config = ConfigDict(from_attributes=True)

    @property
    def best_bid(self) -> Optional[OrderBookLevel]:
        """Get best bid"""
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> Optional[OrderBookLevel]:
        """Get best ask"""
        return self.asks[0] if self.asks else None

    @property
    def spread(self) -> Optional[Decimal]:
        """Calculate spread"""
        if self.best_bid and self.best_ask:
            return self.best_ask.price - self.best_bid.price
        return None

    def total_bid_volume(self, depth: int = 10) -> Decimal:
        """Calculate total bid volume up to depth"""
        return sum(
            level.quantity for level in self.bids[:depth]
        )

    def total_ask_volume(self, depth: int = 10) -> Decimal:
        """Calculate total ask volume up to depth"""
        return sum(
            level.quantity for level in self.asks[:depth]
        )


class Trade(BaseModel):
    """
    Public trade data

    Attributes:
        exchange: Exchange identifier
        symbol: Trading pair
        trade_id: Trade ID from exchange
        price: Trade price
        quantity: Trade quantity
        side: Trade side (buy/sell)
        timestamp: Trade timestamp
    """
    exchange: ExchangeName = Field(description="Exchange")
    symbol: str = Field(description="Symbol")
    trade_id: str = Field(description="Trade ID")
    price: Decimal = Field(description="Price")
    quantity: Decimal = Field(description="Quantity")
    side: OrderSide = Field(description="Side")
    timestamp: datetime = Field(description="Timestamp")

    model_config = ConfigDict(from_attributes=True)


class Kline(BaseModel):
    """
    Candlestick/OHLCV data

    Attributes:
        exchange: Exchange identifier
        symbol: Trading pair
        interval: Timeframe interval
        open_time: Candle open time
        open: Open price
        high: High price
        low: Low price
        close: Close price
        volume: Trading volume
        close_time: Candle close time
    """
    exchange: ExchangeName = Field(description="Exchange")
    symbol: str = Field(description="Symbol")
    interval: str = Field(description="Interval")

    open_time: datetime = Field(description="Open time")
    open: Decimal = Field(description="Open price")
    high: Decimal = Field(description="High price")
    low: Decimal = Field(description="Low price")
    close: Decimal = Field(description="Close price")
    volume: Decimal = Field(description="Volume")
    close_time: datetime = Field(description="Close time")

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# ABSTRACT EXCHANGE INTERFACE
# ============================================================================

class ExchangeInterface(ABC):
    """
    Abstract base class defining standard exchange operations

    All exchange adapters must implement this interface to ensure
    consistent behavior across different exchanges.

    The interface is organized into categories:
    - Lifecycle: initialize, close, health check
    - Account: get balance, get positions
    - Trading: place/cancel/modify orders, get order status
    - Market Data: get ticker, orderbook, trades, klines
    - WebSocket: subscribe/unsubscribe to real-time data

    Usage:
        class BybitAdapter(ExchangeInterface):
            async def place_order(self, order: UnifiedOrder) -> UnifiedOrder:
                # Bybit-specific implementation
                ...

        # Using the adapter
        exchange = BybitAdapter(config)
        await exchange.initialize()
        order = await exchange.place_order(my_order)
        await exchange.close()
    """

    def __init__(self, config: ExchangeConfig):
        """
        Initialize exchange adapter

        Args:
            config: Exchange configuration
        """
        self._config = config
        self._capabilities = ExchangeCapabilities()
        self._initialized = False
        self._logger = logging.getLogger(
            f"{__name__}.{config.exchange.value}"
        )

    # ========================================================================
    # PROPERTIES
    # ========================================================================

    @property
    def exchange_name(self) -> ExchangeName:
        """Get exchange identifier"""
        return self._config.exchange

    @property
    def capabilities(self) -> ExchangeCapabilities:
        """Get exchange capabilities"""
        return self._capabilities

    @property
    def is_testnet(self) -> bool:
        """Check if using testnet"""
        return self._config.testnet

    @property
    def is_initialized(self) -> bool:
        """Check if adapter is initialized"""
        return self._initialized

    # ========================================================================
    # LIFECYCLE METHODS
    # ========================================================================

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize exchange connection

        This method should:
        - Establish HTTP client connections
        - Validate API credentials
        - Load exchange info (symbols, limits)
        - Initialize WebSocket connections if supported

        Raises:
            AuthenticationError: If credentials are invalid
            ConnectionError: If connection fails
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """
        Close exchange connection

        This method should:
        - Close HTTP client connections
        - Close WebSocket connections
        - Clean up any resources
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check exchange connection health

        Returns:
            True if connection is healthy
        """
        pass

    # ========================================================================
    # ACCOUNT METHODS
    # ========================================================================

    @abstractmethod
    async def get_balance(
        self,
        asset: Optional[str] = None
    ) -> AccountBalance:
        """
        Get account balance

        Args:
            asset: Specific asset to query (None for all)

        Returns:
            Account balance information

        Raises:
            AuthenticationError: If not authenticated
            ConnectionError: If request fails
        """
        pass

    @abstractmethod
    async def get_positions(
        self,
        symbol: Optional[str] = None,
        product_type: Optional[ProductType] = None
    ) -> List[UnifiedPosition]:
        """
        Get open positions

        Args:
            symbol: Filter by symbol
            product_type: Filter by product type

        Returns:
            List of open positions

        Raises:
            AuthenticationError: If not authenticated
        """
        pass

    # ========================================================================
    # TRADING METHODS
    # ========================================================================

    @abstractmethod
    async def place_order(self, order: UnifiedOrder) -> UnifiedOrder:
        """
        Place a new order

        Args:
            order: Order to place

        Returns:
            Updated order with exchange ID and status

        Raises:
            ValidationError: If order parameters invalid
            InsufficientBalanceError: If balance too low
            OrderRejectedError: If order rejected
        """
        pass

    @abstractmethod
    async def cancel_order(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None
    ) -> UnifiedOrder:
        """
        Cancel an order

        Either order_id or client_order_id must be provided.

        Args:
            symbol: Trading pair
            order_id: Exchange order ID
            client_order_id: Client order ID

        Returns:
            Cancelled order

        Raises:
            OrderNotFoundError: If order not found
            OrderAlreadyCancelledError: If already cancelled
        """
        pass

    @abstractmethod
    async def get_order_status(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None
    ) -> UnifiedOrder:
        """
        Get order status

        Args:
            symbol: Trading pair
            order_id: Exchange order ID
            client_order_id: Client order ID

        Returns:
            Order with current status

        Raises:
            OrderNotFoundError: If order not found
        """
        pass

    @abstractmethod
    async def get_open_orders(
        self,
        symbol: Optional[str] = None,
        product_type: Optional[ProductType] = None
    ) -> List[UnifiedOrder]:
        """
        Get all open orders

        Args:
            symbol: Filter by symbol
            product_type: Filter by product type

        Returns:
            List of open orders
        """
        pass

    # ========================================================================
    # MARKET DATA METHODS
    # ========================================================================

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Ticker:
        """
        Get ticker data for symbol

        Args:
            symbol: Trading pair

        Returns:
            Ticker data

        Raises:
            SymbolNotFoundError: If symbol not found
        """
        pass

    @abstractmethod
    async def get_orderbook(
        self,
        symbol: str,
        depth: int = 25
    ) -> OrderBook:
        """
        Get order book for symbol

        Args:
            symbol: Trading pair
            depth: Number of levels

        Returns:
            Order book snapshot
        """
        pass

    @abstractmethod
    async def get_trades(
        self,
        symbol: str,
        limit: int = 100
    ) -> List[Trade]:
        """
        Get recent trades for symbol

        Args:
            symbol: Trading pair
            limit: Maximum number of trades

        Returns:
            List of recent trades
        """
        pass

    @abstractmethod
    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 100,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Kline]:
        """
        Get kline/candlestick data

        Args:
            symbol: Trading pair
            interval: Timeframe (1m, 5m, 1h, 1d, etc.)
            limit: Number of candles
            start_time: Start time filter
            end_time: End time filter

        Returns:
            List of klines
        """
        pass

    # ========================================================================
    # WEBSOCKET METHODS (OPTIONAL)
    # ========================================================================

    async def subscribe_ticker(
        self,
        symbol: str,
        callback: Callable[[Ticker], None]
    ) -> str:
        """
        Subscribe to real-time ticker updates

        Args:
            symbol: Trading pair
            callback: Function to call with updates

        Returns:
            Subscription ID for unsubscribing

        Note:
            Default implementation raises NotImplementedError.
            Override in adapters that support WebSocket.
        """
        raise NotImplementedError(
            f"{self.exchange_name.value} does not support WebSocket ticker"
        )

    async def subscribe_orderbook(
        self,
        symbol: str,
        callback: Callable[[OrderBook], None],
        depth: int = 25
    ) -> str:
        """
        Subscribe to real-time orderbook updates

        Args:
            symbol: Trading pair
            callback: Function to call with updates
            depth: Number of levels

        Returns:
            Subscription ID
        """
        raise NotImplementedError(
            f"{self.exchange_name.value} does not support WebSocket orderbook"
        )

    async def subscribe_trades(
        self,
        symbol: str,
        callback: Callable[[Trade], None]
    ) -> str:
        """
        Subscribe to real-time trade updates

        Args:
            symbol: Trading pair
            callback: Function to call with trades

        Returns:
            Subscription ID
        """
        raise NotImplementedError(
            f"{self.exchange_name.value} does not support WebSocket trades"
        )

    async def subscribe_user_data(
        self,
        callback: Callable[[Dict[str, Any]], None]
    ) -> str:
        """
        Subscribe to user data updates (orders, positions, balance)

        Args:
            callback: Function to call with updates

        Returns:
            Subscription ID
        """
        raise NotImplementedError(
            f"{self.exchange_name.value} does not support WebSocket user data"
        )

    async def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe from WebSocket feed

        Args:
            subscription_id: Subscription ID to cancel

        Returns:
            True if successfully unsubscribed
        """
        raise NotImplementedError(
            f"{self.exchange_name.value} does not support WebSocket"
        )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Enums
    "ExchangeName",
    "ProductType",
    "OrderSide",
    "OrderType",
    "TimeInForce",
    "OrderStatus",
    "PositionSide",

    # Configuration
    "ExchangeConfig",
    "ExchangeCapabilities",

    # Order model
    "UnifiedOrder",

    # Balance models
    "AssetBalance",
    "AccountBalance",

    # Position model
    "UnifiedPosition",

    # Market data models
    "Ticker",
    "OrderBookLevel",
    "OrderBook",
    "Trade",
    "Kline",

    # Interface
    "ExchangeInterface",
]
