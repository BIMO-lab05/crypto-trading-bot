"""
Exchange Factory Module - Phase 6: Multi-Exchange Support
Purpose: Factory pattern for creating exchange adapter instances

This module provides:
- ExchangeFactory: Central factory for creating exchange adapters
- Registry of available exchange adapters
- Configuration-based adapter instantiation
- Adapter lifecycle management (pooling, caching)

Architecture:
    +-----------------+
    | ExchangeFactory |
    +--------+--------+
             |
    +--------+--------+--------+--------+
    |        |        |        |        |
    v        v        v        v        v
  Bybit   Binance  Kraken  Coinbase  [Future]
  Adapter  Adapter Adapter  Adapter  Adapters

Usage:
    # Create factory
    factory = ExchangeFactory()

    # Register custom adapter
    factory.register("custom_exchange", CustomExchangeAdapter)

    # Create adapter by exchange name
    adapter = await factory.create(
        exchange=ExchangeName.BYBIT,
        api_key="...",
        api_secret="...",
        testnet=True
    )

    # Or create from config
    config = ExchangeConfig(...)
    adapter = await factory.create_from_config(config)

    # Get cached adapter (singleton per config)
    adapter = await factory.get_or_create(...)

Created: 2025-12-11
Author: Backend Developer Agent
"""

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Type

from app.exchanges.base import (
    ExchangeCapabilities,
    ExchangeConfig,
    ExchangeInterface,
    ExchangeName,
    ProductType,
)
from app.exchanges.bybit_adapter import BybitExchangeAdapter
from app.exchanges.binance import BinanceExchangeAdapter
from app.exchanges.kraken import KrakenExchangeAdapter
from app.exchanges.coinbase import CoinbaseExchangeAdapter
from app.exchanges.errors import (
    ExchangeError,
    ExchangeErrorCode,
    ValidationError,
)

# Configure logger
logger = logging.getLogger(__name__)


# ============================================================================
# ADAPTER REGISTRY
# ============================================================================

# Type alias for adapter constructor
AdapterConstructor = Callable[[ExchangeConfig, Dict[str, Any]], ExchangeInterface]


@dataclass
class AdapterInfo:
    """
    Information about a registered adapter

    Attributes:
        name: Exchange identifier
        adapter_class: Adapter class type
        constructor: Custom constructor function (optional)
        capabilities: Exchange capabilities
        extra_params: Additional parameters for constructor
    """
    name: ExchangeName
    adapter_class: Type[ExchangeInterface]
    constructor: Optional[AdapterConstructor] = None
    capabilities: ExchangeCapabilities = field(default_factory=ExchangeCapabilities)
    extra_params: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# EXCHANGE FACTORY
# ============================================================================

class ExchangeFactory:
    """
    Factory for creating exchange adapter instances

    The factory maintains a registry of available exchange adapters and
    provides methods for creating instances based on configuration.

    Features:
    - Adapter registration and discovery
    - Configuration-based instantiation
    - Instance caching/pooling
    - Lifecycle management (initialize, close)

    Thread Safety:
    - Uses asyncio locks for thread-safe instance management
    - Cache is protected against race conditions

    Example:
        factory = ExchangeFactory()

        # Create Bybit adapter
        bybit = await factory.create(
            exchange=ExchangeName.BYBIT,
            api_key="api_key",
            api_secret="api_secret",
            testnet=True,
            connector_url="http://localhost:8001"
        )

        # Use adapter
        await bybit.initialize()
        balance = await bybit.get_balance()

        # Cleanup
        await factory.close_all()
    """

    # Class-level adapter registry
    _registry: Dict[ExchangeName, AdapterInfo] = {}

    def __init__(self):
        """Initialize exchange factory"""
        # Instance cache (keyed by config hash)
        self._cache: Dict[str, ExchangeInterface] = {}
        self._lock = asyncio.Lock()

        # Register default adapters
        self._register_defaults()

        logger.info("Exchange factory initialized")

    def _register_defaults(self) -> None:
        """Register default exchange adapters"""
        # Register Bybit adapter
        if ExchangeName.BYBIT not in self._registry:
            self.register(
                exchange=ExchangeName.BYBIT,
                adapter_class=BybitExchangeAdapter,
                capabilities=ExchangeCapabilities(
                    spot_trading=True,
                    perpetual_trading=True,
                    options_trading=True,
                    market_orders=True,
                    limit_orders=True,
                    stop_orders=True,
                    trailing_stop=True,
                    post_only=True,
                    reduce_only=True,
                    websocket_public=True,
                    websocket_private=True,
                    orderbook_depth=200,
                    rate_limit_per_second=10,
                    order_rate_limit=10,
                    max_leverage=100,
                    min_order_size_usd=1.0,
                    testnet_available=True,
                )
            )

        # Register Binance adapter
        if ExchangeName.BINANCE not in self._registry:
            self.register(
                exchange=ExchangeName.BINANCE,
                adapter_class=BinanceExchangeAdapter,
                capabilities=ExchangeCapabilities(
                    spot_trading=True,
                    perpetual_trading=True,
                    margin_trading=True,
                    options_trading=False,
                    market_orders=True,
                    limit_orders=True,
                    stop_orders=True,
                    trailing_stop=True,
                    post_only=True,
                    reduce_only=True,
                    websocket_public=True,
                    websocket_private=True,
                    orderbook_depth=1000,
                    rate_limit_per_second=20,
                    order_rate_limit=10,
                    max_leverage=125,
                    min_order_size_usd=5.0,
                    testnet_available=True,
                )
            )

        # Register Kraken adapter
        if ExchangeName.KRAKEN not in self._registry:
            self.register(
                exchange=ExchangeName.KRAKEN,
                adapter_class=KrakenExchangeAdapter,
                capabilities=ExchangeCapabilities(
                    spot_trading=True,
                    perpetual_trading=False,  # Requires separate Futures adapter
                    margin_trading=True,
                    options_trading=False,
                    market_orders=True,
                    limit_orders=True,
                    stop_orders=True,
                    trailing_stop=False,
                    post_only=True,
                    reduce_only=False,
                    websocket_public=True,
                    websocket_private=True,
                    orderbook_depth=500,
                    rate_limit_per_second=5,
                    order_rate_limit=5,
                    max_leverage=5,
                    min_order_size_usd=0.0,
                    testnet_available=False,  # Kraken has no testnet
                )
            )

        # Register Coinbase adapter
        if ExchangeName.COINBASE not in self._registry:
            self.register(
                exchange=ExchangeName.COINBASE,
                adapter_class=CoinbaseExchangeAdapter,
                capabilities=ExchangeCapabilities(
                    spot_trading=True,
                    perpetual_trading=False,  # Coinbase Advanced is spot-only
                    margin_trading=False,
                    options_trading=False,
                    market_orders=True,
                    limit_orders=True,
                    stop_orders=True,
                    trailing_stop=True,
                    post_only=True,
                    reduce_only=False,
                    websocket_public=True,
                    websocket_private=True,
                    orderbook_depth=50,
                    rate_limit_per_second=10,
                    order_rate_limit=30,
                    max_leverage=1,
                    min_order_size_usd=1.0,
                    testnet_available=True,
                    sandbox_mode=True,
                )
            )

    # ========================================================================
    # REGISTRATION
    # ========================================================================

    def register(
        self,
        exchange: ExchangeName,
        adapter_class: Type[ExchangeInterface],
        constructor: Optional[AdapterConstructor] = None,
        capabilities: Optional[ExchangeCapabilities] = None,
        extra_params: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Register an exchange adapter

        Args:
            exchange: Exchange identifier
            adapter_class: Adapter class type
            constructor: Custom constructor function (optional)
            capabilities: Exchange capabilities (optional)
            extra_params: Additional constructor params (optional)
        """
        self._registry[exchange] = AdapterInfo(
            name=exchange,
            adapter_class=adapter_class,
            constructor=constructor,
            capabilities=capabilities or ExchangeCapabilities(),
            extra_params=extra_params or {}
        )

        logger.info(f"Registered adapter for {exchange.value}")

    def unregister(self, exchange: ExchangeName) -> bool:
        """
        Unregister an exchange adapter

        Args:
            exchange: Exchange identifier

        Returns:
            True if adapter was unregistered
        """
        if exchange in self._registry:
            del self._registry[exchange]
            logger.info(f"Unregistered adapter for {exchange.value}")
            return True
        return False

    def is_registered(self, exchange: ExchangeName) -> bool:
        """Check if exchange adapter is registered"""
        return exchange in self._registry

    def list_exchanges(self) -> list[ExchangeName]:
        """Get list of registered exchanges"""
        return list(self._registry.keys())

    def get_capabilities(
        self,
        exchange: ExchangeName
    ) -> Optional[ExchangeCapabilities]:
        """
        Get capabilities for registered exchange

        Args:
            exchange: Exchange identifier

        Returns:
            Exchange capabilities or None if not registered
        """
        info = self._registry.get(exchange)
        return info.capabilities if info else None

    # ========================================================================
    # ADAPTER CREATION
    # ========================================================================

    async def create(
        self,
        exchange: ExchangeName,
        api_key: str,
        api_secret: str,
        testnet: bool = True,
        passphrase: Optional[str] = None,
        initialize: bool = True,
        **kwargs
    ) -> ExchangeInterface:
        """
        Create exchange adapter instance

        Args:
            exchange: Exchange identifier
            api_key: API key
            api_secret: API secret
            testnet: Use testnet environment
            passphrase: Additional passphrase (for OKX, etc.)
            initialize: Auto-initialize adapter
            **kwargs: Additional adapter-specific parameters

        Returns:
            Configured exchange adapter

        Raises:
            ValidationError: If exchange not registered
            ConnectionError: If initialization fails
        """
        # Check registration
        if not self.is_registered(exchange):
            raise ValidationError(
                message=f"Exchange '{exchange.value}' is not registered",
                exchange=exchange.value,
                field="exchange"
            )

        # Build config
        config = ExchangeConfig(
            exchange=exchange,
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            testnet=testnet,
            base_url=kwargs.pop("base_url", None),
            timeout=kwargs.pop("timeout", 30.0),
            max_retries=kwargs.pop("max_retries", 3),
            proxy=kwargs.pop("proxy", None),
            default_product=kwargs.pop(
                "default_product",
                ProductType.LINEAR
            )
        )

        # Create adapter
        adapter = await self.create_from_config(
            config,
            initialize=initialize,
            **kwargs
        )

        return adapter

    async def create_from_config(
        self,
        config: ExchangeConfig,
        initialize: bool = True,
        **kwargs
    ) -> ExchangeInterface:
        """
        Create adapter from configuration

        Args:
            config: Exchange configuration
            initialize: Auto-initialize adapter
            **kwargs: Additional adapter-specific parameters

        Returns:
            Configured exchange adapter
        """
        # Get adapter info
        info = self._registry.get(config.exchange)
        if not info:
            raise ValidationError(
                message=f"Exchange '{config.exchange.value}' is not registered",
                exchange=config.exchange.value
            )

        # Merge extra params
        all_params = {**info.extra_params, **kwargs}

        # Create adapter using constructor or class
        if info.constructor:
            adapter = info.constructor(config, all_params)
        else:
            # Default construction
            adapter = info.adapter_class(config, **all_params)

        # Initialize if requested
        if initialize:
            await adapter.initialize()

        logger.info(
            f"Created {config.exchange.value} adapter "
            f"(testnet={config.testnet}, initialized={initialize})"
        )

        return adapter

    # ========================================================================
    # CACHING
    # ========================================================================

    def _config_hash(self, config: ExchangeConfig) -> str:
        """
        Generate hash for configuration (for caching)

        Args:
            config: Exchange configuration

        Returns:
            Hash string
        """
        # Include key fields in hash (not secrets)
        hash_input = (
            f"{config.exchange.value}:"
            f"{config.testnet}:"
            f"{config.api_key[:8]}:"  # First 8 chars only
            f"{config.base_url or 'default'}"
        )
        return hashlib.md5(hash_input.encode()).hexdigest()

    async def get_or_create(
        self,
        exchange: ExchangeName,
        api_key: str,
        api_secret: str,
        testnet: bool = True,
        **kwargs
    ) -> ExchangeInterface:
        """
        Get cached adapter or create new one

        This method provides singleton-like behavior per configuration,
        reusing adapters when the same config is requested.

        Args:
            exchange: Exchange identifier
            api_key: API key
            api_secret: API secret
            testnet: Use testnet
            **kwargs: Additional parameters

        Returns:
            Cached or new adapter instance
        """
        # Build config for hash
        config = ExchangeConfig(
            exchange=exchange,
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet,
            base_url=kwargs.get("base_url"),
        )

        cache_key = self._config_hash(config)

        async with self._lock:
            # Check cache
            if cache_key in self._cache:
                adapter = self._cache[cache_key]
                # Verify adapter is still healthy
                try:
                    if await adapter.health_check():
                        logger.debug(f"Returning cached adapter for {exchange.value}")
                        return adapter
                except Exception:
                    # Remove unhealthy adapter
                    del self._cache[cache_key]

            # Create new adapter
            adapter = await self.create(
                exchange=exchange,
                api_key=api_key,
                api_secret=api_secret,
                testnet=testnet,
                **kwargs
            )

            # Cache it
            self._cache[cache_key] = adapter
            logger.info(f"Cached new adapter for {exchange.value}")

            return adapter

    async def remove_from_cache(
        self,
        exchange: ExchangeName,
        api_key: str,
        testnet: bool = True,
        base_url: Optional[str] = None
    ) -> bool:
        """
        Remove adapter from cache

        Args:
            exchange: Exchange identifier
            api_key: API key
            testnet: Testnet flag
            base_url: Base URL

        Returns:
            True if adapter was removed
        """
        config = ExchangeConfig(
            exchange=exchange,
            api_key=api_key,
            api_secret="dummy",  # Not used for hash
            testnet=testnet,
            base_url=base_url,
        )

        cache_key = self._config_hash(config)

        async with self._lock:
            if cache_key in self._cache:
                adapter = self._cache.pop(cache_key)
                await adapter.close()
                logger.info(f"Removed adapter from cache: {exchange.value}")
                return True

        return False

    # ========================================================================
    # LIFECYCLE
    # ========================================================================

    async def close_all(self) -> int:
        """
        Close all cached adapters

        Returns:
            Number of adapters closed
        """
        async with self._lock:
            count = 0
            for cache_key, adapter in list(self._cache.items()):
                try:
                    await adapter.close()
                    count += 1
                    logger.debug(f"Closed adapter: {adapter.exchange_name.value}")
                except Exception as e:
                    logger.warning(f"Error closing adapter: {e}")

            self._cache.clear()

        logger.info(f"Closed {count} cached adapters")
        return count

    async def health_check_all(self) -> Dict[str, bool]:
        """
        Health check all cached adapters

        Returns:
            Dict mapping cache keys to health status
        """
        results = {}

        async with self._lock:
            for cache_key, adapter in self._cache.items():
                try:
                    results[cache_key] = await adapter.health_check()
                except Exception:
                    results[cache_key] = False

        return results


# ============================================================================
# GLOBAL FACTORY INSTANCE
# ============================================================================

# Global factory instance (singleton pattern)
_factory: Optional[ExchangeFactory] = None
_factory_lock = asyncio.Lock()


async def get_exchange_factory() -> ExchangeFactory:
    """
    Get global exchange factory instance

    Returns:
        Exchange factory singleton
    """
    global _factory

    if _factory is None:
        async with _factory_lock:
            if _factory is None:
                _factory = ExchangeFactory()

    return _factory


async def reset_exchange_factory() -> None:
    """Reset global factory instance (closes all adapters)"""
    global _factory

    if _factory is not None:
        await _factory.close_all()
        _factory = None
        logger.info("Exchange factory reset")


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

async def create_exchange(
    exchange: ExchangeName,
    api_key: str,
    api_secret: str,
    testnet: bool = True,
    **kwargs
) -> ExchangeInterface:
    """
    Convenience function to create exchange adapter

    Uses global factory instance.

    Args:
        exchange: Exchange identifier
        api_key: API key
        api_secret: API secret
        testnet: Use testnet
        **kwargs: Additional parameters

    Returns:
        Exchange adapter instance
    """
    factory = await get_exchange_factory()
    return await factory.create(
        exchange=exchange,
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet,
        **kwargs
    )


async def get_exchange(
    exchange: ExchangeName,
    api_key: str,
    api_secret: str,
    testnet: bool = True,
    **kwargs
) -> ExchangeInterface:
    """
    Get cached exchange adapter (or create new)

    Uses global factory instance with caching.

    Args:
        exchange: Exchange identifier
        api_key: API key
        api_secret: API secret
        testnet: Use testnet
        **kwargs: Additional parameters

    Returns:
        Cached or new exchange adapter
    """
    factory = await get_exchange_factory()
    return await factory.get_or_create(
        exchange=exchange,
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet,
        **kwargs
    )


def list_supported_exchanges() -> list[str]:
    """
    List all supported exchange names

    Returns:
        List of exchange name strings
    """
    return [e.value for e in ExchangeName]


def list_registered_exchanges() -> list[str]:
    """
    List registered exchange adapters

    Note: This uses class-level registry, works before factory instantiation.

    Returns:
        List of registered exchange names
    """
    return [e.value for e in ExchangeFactory._registry.keys()]


__all__ = [
    # Factory
    "ExchangeFactory",
    "AdapterInfo",

    # Global factory functions
    "get_exchange_factory",
    "reset_exchange_factory",

    # Convenience functions
    "create_exchange",
    "get_exchange",
    "list_supported_exchanges",
    "list_registered_exchanges",
]
