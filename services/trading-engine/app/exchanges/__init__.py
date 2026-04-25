"""
Multi-Exchange Support Module - Phase 6 Implementation
Purpose: Unified exchange abstraction layer for multi-exchange trading

This module provides a comprehensive abstraction layer that enables the trading
engine to interact with multiple cryptocurrency exchanges through a unified
interface. Key features include:

1. ExchangeInterface - Abstract base class defining standard operations:
   - Order management: place, cancel, get status
   - Account data: balance, positions
   - Market data: ticker, orderbook, trades, klines
   - WebSocket subscriptions (where supported)

2. Unified Data Models:
   - UnifiedOrder: Exchange-agnostic order representation
   - AccountBalance: Standardized balance information
   - UnifiedPosition: Position data across exchanges
   - Market data models (Ticker, OrderBook, Trade, Kline)

3. Exchange Adapters:
   - BybitExchangeAdapter: Wrapper for bybit-connector service
   - BinanceExchangeAdapter: Direct Binance API integration
   - KrakenExchangeAdapter: Kraken API with nonce-based auth
   - CoinbaseExchangeAdapter: Coinbase Advanced Trade API

4. ExchangeFactory:
   - Registry-based adapter creation
   - Configuration-driven instantiation
   - Instance caching/pooling
   - Lifecycle management

5. ExchangeRouter:
   - Smart order routing based on liquidity, fees, latency
   - Order splitting for large orders
   - Cross-exchange arbitrage detection
   - Balance-aware routing

6. ExchangeManager:
   - Connection lifecycle management
   - Health monitoring with automatic recovery
   - Failover logic between exchanges
   - Cross-exchange portfolio aggregation
   - Risk calculation

7. Error Handling:
   - Unified exception hierarchy
   - Exchange-specific error mapping
   - Automatic retry for retryable errors
   - Detailed error context

Architecture:
```
+------------------+     +------------------+     +------------------+
| ExchangeManager  | --> | ExchangeRouter   | --> | Exchange Adapters|
|                  |     |                  |     | - Bybit          |
| - Health Monitor |     | - Smart Routing  |     | - Binance        |
| - Failover       |     | - Order Splitting|     | - Kraken         |
| - Portfolio Agg  |     | - Arbitrage Det  |     | - Coinbase       |
+------------------+     +------------------+     +--------+---------+
                                                          |
                                                          v
                                                 +------------------+
                                                 | Exchange APIs    |
                                                 +------------------+
```

Usage Examples:

Basic Usage with Factory:
```python
from app.exchanges import (
    ExchangeName,
    create_exchange,
    UnifiedOrder,
    OrderSide,
    OrderType
)
from decimal import Decimal

# Create exchange adapter
exchange = await create_exchange(
    exchange=ExchangeName.BYBIT,
    api_key="your_api_key",
    api_secret="your_api_secret",
    testnet=True
)

# Get balance
balance = await exchange.get_balance()
print(f"Equity: ${balance.total_equity}")

# Place order
order = UnifiedOrder(
    exchange=ExchangeName.BYBIT,
    symbol="BTCUSDT",
    side=OrderSide.BUY,
    order_type=OrderType.MARKET,
    quantity=Decimal("0.001")
)
result = await exchange.place_order(order)
print(f"Order ID: {result.exchange_order_id}")

# Cleanup
await exchange.close()
```

Multi-Exchange with Manager:
```python
from app.exchanges import (
    ExchangeManager,
    ExchangeName,
    ManagerConfig
)

# Create manager
config = ManagerConfig()
manager = ExchangeManager(config)
await manager.start()

# Add multiple exchanges
await manager.add_exchange(
    exchange=ExchangeName.BYBIT,
    api_key="bybit_key",
    api_secret="bybit_secret",
    testnet=True
)
await manager.add_exchange(
    exchange=ExchangeName.BINANCE,
    api_key="binance_key",
    api_secret="binance_secret",
    testnet=True
)

# Get portfolio summary
portfolio = await manager.get_portfolio_summary()
print(f"Total equity: ${portfolio.total_equity}")

# Route and execute order
decision = await manager.route_order(order)
result = await manager.execute_order(order, decision.exchange)

# Cleanup
await manager.stop()
```

Smart Order Routing:
```python
from app.exchanges import (
    ExchangeRouter,
    RoutingConfig,
    RoutingStrategy
)

# Create router with config
config = RoutingConfig(
    strategy=RoutingStrategy.SMART,
    max_spread_bps=50.0,
    split_threshold=100000.0
)
router = ExchangeRouter(config)

# Register exchanges
router.register_exchange(bybit_adapter)
router.register_exchange(binance_adapter)

# Route order
decision = await router.route_order(order)
print(f"Best exchange: {decision.exchange.value}")
print(f"Reasons: {decision.reasons}")

# For large orders, split across exchanges
plan = await router.plan_split_order(large_order)
for exchange, qty in plan.allocations.items():
    print(f"{exchange.value}: {qty}")

# Find arbitrage opportunities
arb_opps = await router.find_arbitrage("BTCUSDT")
for opp in arb_opps:
    print(f"Buy on {opp.buy_exchange.value}, sell on {opp.sell_exchange.value}")
    print(f"Profit: {opp.profit_bps:.2f} bps")
```

Error Handling:
```python
from app.exchanges import (
    ExchangeError,
    RateLimitError,
    InsufficientBalanceError,
    OrderRejectedError
)

try:
    result = await exchange.place_order(order)
except RateLimitError as e:
    # Wait and retry
    await asyncio.sleep(e.retry_after)
    result = await exchange.place_order(order)
except InsufficientBalanceError as e:
    print(f"Need {e.required} {e.asset}, have {e.available}")
except OrderRejectedError as e:
    print(f"Order rejected: {e.message}")
except ExchangeError as e:
    print(f"Exchange error: {e.error_code} - {e.message}")
```

Module Structure:
```
app/exchanges/
    __init__.py         # This file - exports all public API
    base.py             # ExchangeInterface and unified models
    bybit_adapter.py    # Bybit exchange adapter
    binance.py          # Binance exchange adapter
    kraken.py           # Kraken exchange adapter
    coinbase.py         # Coinbase exchange adapter
    factory.py          # ExchangeFactory and creation utilities
    router.py           # ExchangeRouter for smart routing
    manager.py          # ExchangeManager for multi-exchange ops
    errors.py           # Exception hierarchy and error mapping
```

Created: 2025-12-11
Author: Backend Developer Agent
"""

# ============================================================================
# BASE INTERFACE AND MODELS
# ============================================================================

from app.exchanges.base import (
    # Abstract interface
    ExchangeInterface,

    # Enumerations
    ExchangeName,
    ProductType,
    OrderSide,
    OrderType,
    TimeInForce,
    OrderStatus,
    PositionSide,

    # Configuration
    ExchangeConfig,
    ExchangeCapabilities,

    # Order model
    UnifiedOrder,

    # Balance models
    AssetBalance,
    AccountBalance,

    # Position model
    UnifiedPosition,

    # Market data models
    Ticker,
    OrderBookLevel,
    OrderBook,
    Trade,
    Kline,
)

# ============================================================================
# ERROR HANDLING
# ============================================================================

from app.exchanges.errors import (
    # Error codes
    ExchangeErrorCode,

    # Base exception
    ExchangeError,

    # Connection errors
    ConnectionError,
    TimeoutError,
    NetworkError,

    # Authentication errors
    AuthenticationError,
    InvalidAPIKeyError,
    InvalidSignatureError,
    PermissionDeniedError,

    # Rate limiting
    RateLimitError,

    # Validation errors
    ValidationError,
    InvalidSymbolError,
    InvalidQuantityError,
    InvalidPriceError,

    # Order errors
    OrderError,
    OrderNotFoundError,
    OrderAlreadyCancelledError,
    InsufficientBalanceError,
    OrderRejectedError,

    # Market data errors
    MarketDataError,
    SymbolNotFoundError,
    DataUnavailableError,

    # System errors
    ExchangeMaintenanceError,

    # Mapping utilities
    BYBIT_ERROR_MAP,
    map_bybit_error,
)

# ============================================================================
# EXCHANGE ADAPTERS
# ============================================================================

# Bybit Adapter
from app.exchanges.bybit_adapter import (
    BybitExchangeAdapter,
    BybitAdapterConfig,
    RateLimiter,
    create_bybit_adapter,
)

# Binance Adapter
from app.exchanges.binance import (
    BinanceExchangeAdapter,
    BinanceAdapterConfig,
    BinanceRateLimiter,
    create_binance_adapter,
    map_binance_error,
    BINANCE_ERROR_MAP,
)

# Kraken Adapter
from app.exchanges.kraken import (
    KrakenExchangeAdapter,
    KrakenAdapterConfig,
    KrakenRateLimiter,
    create_kraken_adapter,
    map_kraken_error,
    to_kraken_symbol,
    from_kraken_symbol,
)

# Coinbase Adapter
from app.exchanges.coinbase import (
    CoinbaseExchangeAdapter,
    CoinbaseAdapterConfig,
    CoinbaseRateLimiter,
    create_coinbase_adapter,
    map_coinbase_error,
)

# ============================================================================
# FACTORY
# ============================================================================

from app.exchanges.factory import (
    # Factory class
    ExchangeFactory,
    AdapterInfo,

    # Global factory functions
    get_exchange_factory,
    reset_exchange_factory,

    # Convenience functions
    create_exchange,
    get_exchange,
    list_supported_exchanges,
    list_registered_exchanges,
)

# ============================================================================
# ROUTER
# ============================================================================

from app.exchanges.router import (
    # Enumerations
    RoutingStrategy,
    RoutingPriority,

    # Data classes
    ExchangeMetrics,
    ExchangeLiquidity,
    RoutingDecision,
    SplitOrderPlan,
    ArbitrageOpportunity,

    # Configuration
    RoutingConfig,

    # Router class
    ExchangeRouter,
)

# ============================================================================
# MANAGER
# ============================================================================

from app.exchanges.manager import (
    # State
    ConnectionState,
    ExchangeStatus,

    # Configuration
    HealthCheckConfig,
    FailoverConfig,
    ManagerConfig,

    # Data
    PortfolioSummary,
    CrossExchangeRisk,

    # Manager class
    ExchangeManager,
    create_exchange_manager,
)


# ============================================================================
# VERSION INFO
# ============================================================================

__version__ = "1.0.0"
__author__ = "Backend Developer Agent"
__created__ = "2025-12-11"


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Version
    "__version__",

    # ========== Base Interface ==========
    "ExchangeInterface",

    # ========== Enumerations ==========
    "ExchangeName",
    "ProductType",
    "OrderSide",
    "OrderType",
    "TimeInForce",
    "OrderStatus",
    "PositionSide",

    # ========== Configuration ==========
    "ExchangeConfig",
    "ExchangeCapabilities",

    # ========== Order Model ==========
    "UnifiedOrder",

    # ========== Balance Models ==========
    "AssetBalance",
    "AccountBalance",

    # ========== Position Model ==========
    "UnifiedPosition",

    # ========== Market Data Models ==========
    "Ticker",
    "OrderBookLevel",
    "OrderBook",
    "Trade",
    "Kline",

    # ========== Error Handling ==========
    "ExchangeErrorCode",
    "ExchangeError",
    "ConnectionError",
    "TimeoutError",
    "NetworkError",
    "AuthenticationError",
    "InvalidAPIKeyError",
    "InvalidSignatureError",
    "PermissionDeniedError",
    "RateLimitError",
    "ValidationError",
    "InvalidSymbolError",
    "InvalidQuantityError",
    "InvalidPriceError",
    "OrderError",
    "OrderNotFoundError",
    "OrderAlreadyCancelledError",
    "InsufficientBalanceError",
    "OrderRejectedError",
    "MarketDataError",
    "SymbolNotFoundError",
    "DataUnavailableError",
    "ExchangeMaintenanceError",
    "BYBIT_ERROR_MAP",
    "map_bybit_error",
    "BINANCE_ERROR_MAP",
    "map_binance_error",
    "map_kraken_error",
    "map_coinbase_error",

    # ========== Bybit Adapter ==========
    "BybitExchangeAdapter",
    "BybitAdapterConfig",
    "RateLimiter",
    "create_bybit_adapter",

    # ========== Binance Adapter ==========
    "BinanceExchangeAdapter",
    "BinanceAdapterConfig",
    "BinanceRateLimiter",
    "create_binance_adapter",

    # ========== Kraken Adapter ==========
    "KrakenExchangeAdapter",
    "KrakenAdapterConfig",
    "KrakenRateLimiter",
    "create_kraken_adapter",
    "to_kraken_symbol",
    "from_kraken_symbol",

    # ========== Coinbase Adapter ==========
    "CoinbaseExchangeAdapter",
    "CoinbaseAdapterConfig",
    "CoinbaseRateLimiter",
    "create_coinbase_adapter",

    # ========== Factory ==========
    "ExchangeFactory",
    "AdapterInfo",
    "get_exchange_factory",
    "reset_exchange_factory",
    "create_exchange",
    "get_exchange",
    "list_supported_exchanges",
    "list_registered_exchanges",

    # ========== Router ==========
    "RoutingStrategy",
    "RoutingPriority",
    "ExchangeMetrics",
    "ExchangeLiquidity",
    "RoutingDecision",
    "SplitOrderPlan",
    "ArbitrageOpportunity",
    "RoutingConfig",
    "ExchangeRouter",

    # ========== Manager ==========
    "ConnectionState",
    "ExchangeStatus",
    "HealthCheckConfig",
    "FailoverConfig",
    "ManagerConfig",
    "PortfolioSummary",
    "CrossExchangeRisk",
    "ExchangeManager",
    "create_exchange_manager",
]
