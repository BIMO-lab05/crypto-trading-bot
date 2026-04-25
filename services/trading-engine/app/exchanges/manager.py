"""
Exchange Manager Module - Phase 6: Multi-Exchange Support
Purpose: Unified management of multiple exchange connections

This module provides centralized exchange connection management:
- Connection lifecycle management
- Health monitoring and automatic recovery
- Failover logic between exchanges
- Connection pooling
- Cross-exchange risk management

Architecture:
    +------------------+
    | ExchangeManager  |
    +--------+---------+
             |
    +--------+--------+---------+--------+
    |        |        |         |        |
    v        v        v         v        v
  Bybit   Binance  Kraken  Coinbase   ...
    |        |        |         |
    +--------+--------+---------+--------+
             |
    +--------+---------+
    | ExchangeRouter   |
    +------------------+

Created: 2025-12-11
Author: Backend Developer Agent
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field

from app.exchanges.base import (
    AccountBalance,
    ExchangeCapabilities,
    ExchangeConfig,
    ExchangeInterface,
    ExchangeName,
    ProductType,
    UnifiedOrder,
    UnifiedPosition,
)
from app.exchanges.errors import (
    AuthenticationError,
    ConnectionError,
    ExchangeError,
    RateLimitError,
)
from app.exchanges.factory import ExchangeFactory, get_exchange_factory
from app.exchanges.router import (
    ExchangeRouter,
    RoutingConfig,
    RoutingDecision,
    RoutingStrategy,
)

# Configure logger
logger = logging.getLogger(__name__)


# ============================================================================
# CONNECTION STATE
# ============================================================================

class ConnectionState(str, Enum):
    """Exchange connection states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    MAINTENANCE = "maintenance"


@dataclass
class ExchangeStatus:
    """
    Status of an exchange connection

    Attributes:
        exchange: Exchange identifier
        state: Current connection state
        is_healthy: Whether exchange is healthy
        last_heartbeat: Last successful heartbeat
        error_count: Consecutive error count
        last_error: Last error message
        latency_ms: Recent latency measurement
        connected_at: When connection was established
        metrics: Additional metrics
    """
    exchange: ExchangeName
    state: ConnectionState = ConnectionState.DISCONNECTED
    is_healthy: bool = False
    last_heartbeat: Optional[datetime] = None
    error_count: int = 0
    last_error: Optional[str] = None
    latency_ms: float = 0.0
    connected_at: Optional[datetime] = None
    metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def uptime_seconds(self) -> float:
        """Calculate uptime in seconds"""
        if self.connected_at and self.state == ConnectionState.CONNECTED:
            return (datetime.now(timezone.utc) - self.connected_at).total_seconds()
        return 0.0


# ============================================================================
# MANAGER CONFIGURATION
# ============================================================================

class HealthCheckConfig(BaseModel):
    """
    Health check configuration

    Attributes:
        interval_seconds: Seconds between health checks
        timeout_seconds: Health check timeout
        max_failures: Failures before marking unhealthy
        recovery_threshold: Successes needed to recover
    """
    interval_seconds: float = Field(default=30.0, ge=5.0)
    timeout_seconds: float = Field(default=10.0, ge=1.0)
    max_failures: int = Field(default=3, ge=1)
    recovery_threshold: int = Field(default=2, ge=1)


class FailoverConfig(BaseModel):
    """
    Failover configuration

    Attributes:
        enabled: Enable automatic failover
        primary_exchange: Primary exchange for trading
        backup_exchanges: Ordered list of backup exchanges
        auto_switch_threshold: Errors before auto-switching
        cooldown_seconds: Seconds before retrying failed exchange
    """
    enabled: bool = Field(default=True)
    primary_exchange: Optional[ExchangeName] = None
    backup_exchanges: List[ExchangeName] = Field(default_factory=list)
    auto_switch_threshold: int = Field(default=5, ge=1)
    cooldown_seconds: float = Field(default=300.0, ge=60.0)


class ManagerConfig(BaseModel):
    """
    Exchange manager configuration

    Attributes:
        health_check: Health check configuration
        failover: Failover configuration
        routing: Router configuration
        max_concurrent_requests: Max concurrent API requests
        enable_metrics: Enable metrics collection
    """
    health_check: HealthCheckConfig = Field(default_factory=HealthCheckConfig)
    failover: FailoverConfig = Field(default_factory=FailoverConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    max_concurrent_requests: int = Field(default=50, ge=1)
    enable_metrics: bool = Field(default=True)


# ============================================================================
# PORTFOLIO SUMMARY
# ============================================================================

@dataclass
class PortfolioSummary:
    """
    Cross-exchange portfolio summary

    Attributes:
        total_equity: Total equity across all exchanges (USD)
        available_balance: Total available balance (USD)
        used_margin: Total used margin
        unrealized_pnl: Total unrealized P&L
        positions_count: Number of open positions
        by_exchange: Breakdown by exchange
        by_asset: Breakdown by asset
        updated_at: Last update timestamp
    """
    total_equity: Decimal = Decimal("0")
    available_balance: Decimal = Decimal("0")
    used_margin: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    positions_count: int = 0
    by_exchange: Dict[ExchangeName, AccountBalance] = field(default_factory=dict)
    by_asset: Dict[str, Decimal] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CrossExchangeRisk:
    """
    Cross-exchange risk metrics

    Attributes:
        total_exposure: Total position exposure (USD)
        max_drawdown: Maximum drawdown percentage
        concentration_by_exchange: Position concentration per exchange
        concentration_by_symbol: Position concentration per symbol
        risk_score: Overall risk score (0-100)
    """
    total_exposure: Decimal = Decimal("0")
    max_drawdown: float = 0.0
    concentration_by_exchange: Dict[ExchangeName, float] = field(default_factory=dict)
    concentration_by_symbol: Dict[str, float] = field(default_factory=dict)
    risk_score: float = 0.0


# ============================================================================
# EXCHANGE MANAGER
# ============================================================================

class ExchangeManager:
    """
    Centralized manager for multiple exchange connections

    Responsibilities:
    - Manage exchange adapter lifecycle
    - Monitor connection health
    - Handle failover between exchanges
    - Provide unified portfolio view
    - Coordinate cross-exchange operations

    Features:
    - Automatic health monitoring with recovery
    - Failover to backup exchanges
    - Connection pooling and reuse
    - Unified balance/position aggregation
    - Cross-exchange risk calculation
    - Event callbacks for state changes

    Usage:
        manager = ExchangeManager(config)

        # Add exchanges
        await manager.add_exchange(
            exchange=ExchangeName.BYBIT,
            api_key="...",
            api_secret="...",
            testnet=True
        )
        await manager.add_exchange(
            exchange=ExchangeName.BINANCE,
            api_key="...",
            api_secret="..."
        )

        # Start health monitoring
        await manager.start()

        # Get portfolio summary
        portfolio = await manager.get_portfolio_summary()
        print(f"Total equity: ${portfolio.total_equity}")

        # Place order with smart routing
        decision = await manager.route_order(order)
        result = await manager.execute_order(order, decision.exchange)

        # Stop and cleanup
        await manager.stop()
    """

    def __init__(
        self,
        config: Optional[ManagerConfig] = None
    ):
        """
        Initialize exchange manager

        Args:
            config: Manager configuration
        """
        self.config = config or ManagerConfig()

        # Exchange adapters
        self._adapters: Dict[ExchangeName, ExchangeInterface] = {}

        # Exchange status
        self._status: Dict[ExchangeName, ExchangeStatus] = {}

        # Exchange configurations (for reconnection)
        self._configs: Dict[ExchangeName, ExchangeConfig] = {}

        # Factory instance
        self._factory: Optional[ExchangeFactory] = None

        # Router instance
        self._router: Optional[ExchangeRouter] = None

        # Background tasks
        self._health_task: Optional[asyncio.Task] = None
        self._running = False

        # Concurrency control
        self._request_semaphore = asyncio.Semaphore(
            self.config.max_concurrent_requests
        )

        # Event callbacks
        self._callbacks: Dict[str, List[Callable]] = {
            "connected": [],
            "disconnected": [],
            "health_changed": [],
            "failover": [],
        }

        # Failover state
        self._current_primary: Optional[ExchangeName] = None
        self._failed_exchanges: Dict[ExchangeName, datetime] = {}

        logger.info("Created ExchangeManager")

    # ========================================================================
    # LIFECYCLE
    # ========================================================================

    async def start(self) -> None:
        """
        Start the exchange manager

        Initializes factory, router, and starts health monitoring.
        """
        logger.info("Starting ExchangeManager...")

        # Initialize factory
        self._factory = await get_exchange_factory()

        # Initialize router
        self._router = ExchangeRouter(self.config.routing)

        # Register existing adapters with router
        for exchange, adapter in self._adapters.items():
            self._router.register_exchange(adapter)

        # Set primary exchange
        if self.config.failover.primary_exchange:
            self._current_primary = self.config.failover.primary_exchange
        elif self._adapters:
            self._current_primary = list(self._adapters.keys())[0]

        # Start health check task
        self._running = True
        self._health_task = asyncio.create_task(self._health_check_loop())

        logger.info(
            f"ExchangeManager started with {len(self._adapters)} exchanges"
        )

    async def stop(self) -> None:
        """
        Stop the exchange manager

        Stops health monitoring and closes all connections.
        """
        logger.info("Stopping ExchangeManager...")

        # Stop health check
        self._running = False
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass

        # Close all adapters
        for exchange, adapter in list(self._adapters.items()):
            try:
                await adapter.close()
                self._update_status(
                    exchange,
                    ConnectionState.DISCONNECTED,
                    is_healthy=False
                )
            except Exception as e:
                logger.warning(f"Error closing {exchange.value}: {e}")

        self._adapters.clear()
        self._status.clear()

        logger.info("ExchangeManager stopped")

    # ========================================================================
    # EXCHANGE MANAGEMENT
    # ========================================================================

    async def add_exchange(
        self,
        exchange: ExchangeName,
        api_key: str,
        api_secret: str,
        testnet: bool = True,
        passphrase: Optional[str] = None,
        **kwargs
    ) -> bool:
        """
        Add and connect to an exchange

        Args:
            exchange: Exchange identifier
            api_key: API key
            api_secret: API secret
            testnet: Use testnet
            passphrase: Additional passphrase (for some exchanges)
            **kwargs: Additional adapter parameters

        Returns:
            True if successfully connected
        """
        if exchange in self._adapters:
            logger.warning(f"Exchange {exchange.value} already registered")
            return True

        # Store config for reconnection
        config = ExchangeConfig(
            exchange=exchange,
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            testnet=testnet
        )
        self._configs[exchange] = config

        # Initialize status
        self._status[exchange] = ExchangeStatus(
            exchange=exchange,
            state=ConnectionState.CONNECTING
        )

        try:
            # Create adapter via factory
            if not self._factory:
                self._factory = await get_exchange_factory()

            adapter = await self._factory.create(
                exchange=exchange,
                api_key=api_key,
                api_secret=api_secret,
                testnet=testnet,
                passphrase=passphrase,
                initialize=True,
                **kwargs
            )

            # Store adapter
            self._adapters[exchange] = adapter

            # Update status
            self._update_status(
                exchange,
                ConnectionState.CONNECTED,
                is_healthy=True,
                connected_at=datetime.now(timezone.utc)
            )

            # Register with router
            if self._router:
                self._router.register_exchange(adapter)

            # Trigger callback
            await self._trigger_callback("connected", exchange)

            logger.info(f"Connected to {exchange.value}")
            return True

        except AuthenticationError as e:
            logger.error(f"Authentication failed for {exchange.value}: {e}")
            self._update_status(
                exchange,
                ConnectionState.FAILED,
                is_healthy=False,
                last_error=str(e)
            )
            return False

        except Exception as e:
            logger.error(f"Failed to connect to {exchange.value}: {e}")
            self._update_status(
                exchange,
                ConnectionState.FAILED,
                is_healthy=False,
                last_error=str(e)
            )
            return False

    async def remove_exchange(self, exchange: ExchangeName) -> bool:
        """
        Remove and disconnect from an exchange

        Args:
            exchange: Exchange to remove

        Returns:
            True if successfully removed
        """
        if exchange not in self._adapters:
            return False

        try:
            # Close adapter
            adapter = self._adapters[exchange]
            await adapter.close()

            # Unregister from router
            if self._router:
                self._router.unregister_exchange(exchange)

            # Cleanup
            del self._adapters[exchange]
            if exchange in self._status:
                del self._status[exchange]
            if exchange in self._configs:
                del self._configs[exchange]

            # Trigger callback
            await self._trigger_callback("disconnected", exchange)

            logger.info(f"Removed exchange: {exchange.value}")
            return True

        except Exception as e:
            logger.error(f"Error removing {exchange.value}: {e}")
            return False

    def get_adapter(self, exchange: ExchangeName) -> Optional[ExchangeInterface]:
        """Get adapter for an exchange"""
        return self._adapters.get(exchange)

    def get_status(self, exchange: ExchangeName) -> Optional[ExchangeStatus]:
        """Get status for an exchange"""
        return self._status.get(exchange)

    def get_all_status(self) -> Dict[ExchangeName, ExchangeStatus]:
        """Get status for all exchanges"""
        return dict(self._status)

    def get_healthy_exchanges(self) -> List[ExchangeName]:
        """Get list of healthy exchanges"""
        return [
            ex for ex, status in self._status.items()
            if status.is_healthy
        ]

    def _update_status(
        self,
        exchange: ExchangeName,
        state: Optional[ConnectionState] = None,
        is_healthy: Optional[bool] = None,
        error: Optional[str] = None,
        latency_ms: Optional[float] = None,
        connected_at: Optional[datetime] = None
    ) -> None:
        """Update exchange status"""
        if exchange not in self._status:
            self._status[exchange] = ExchangeStatus(exchange=exchange)

        status = self._status[exchange]

        if state is not None:
            status.state = state
        if is_healthy is not None:
            old_healthy = status.is_healthy
            status.is_healthy = is_healthy
            if old_healthy != is_healthy:
                asyncio.create_task(
                    self._trigger_callback("health_changed", exchange, is_healthy)
                )
        if error is not None:
            status.last_error = error
            status.error_count += 1
        if latency_ms is not None:
            status.latency_ms = latency_ms
            status.last_heartbeat = datetime.now(timezone.utc)
        if connected_at is not None:
            status.connected_at = connected_at

    # ========================================================================
    # HEALTH MONITORING
    # ========================================================================

    async def _health_check_loop(self) -> None:
        """Background health check loop"""
        while self._running:
            try:
                await self._perform_health_checks()
            except Exception as e:
                logger.error(f"Health check error: {e}")

            await asyncio.sleep(self.config.health_check.interval_seconds)

    async def _perform_health_checks(self) -> None:
        """Perform health checks on all exchanges"""
        tasks = []
        for exchange, adapter in self._adapters.items():
            tasks.append(self._check_exchange_health(exchange, adapter))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_exchange_health(
        self,
        exchange: ExchangeName,
        adapter: ExchangeInterface
    ) -> None:
        """Check health of a single exchange"""
        status = self._status.get(exchange)
        if not status:
            return

        try:
            start = asyncio.get_event_loop().time()

            # Perform health check with timeout
            is_healthy = await asyncio.wait_for(
                adapter.health_check(),
                timeout=self.config.health_check.timeout_seconds
            )

            latency_ms = (asyncio.get_event_loop().time() - start) * 1000

            if is_healthy:
                # Reset error count on success
                status.error_count = 0
                self._update_status(
                    exchange,
                    state=ConnectionState.CONNECTED,
                    is_healthy=True,
                    latency_ms=latency_ms
                )

                # Clear from failed exchanges
                if exchange in self._failed_exchanges:
                    del self._failed_exchanges[exchange]

                # Update router metrics
                if self._router:
                    await self._router.update_metrics(
                        exchange,
                        latency_ms=latency_ms
                    )
            else:
                raise ConnectionError(
                    message="Health check returned false",
                    exchange=exchange.value
                )

        except asyncio.TimeoutError:
            self._handle_health_failure(
                exchange,
                "Health check timeout"
            )

        except Exception as e:
            self._handle_health_failure(exchange, str(e))

    def _handle_health_failure(
        self,
        exchange: ExchangeName,
        error: str
    ) -> None:
        """Handle health check failure"""
        status = self._status.get(exchange)
        if not status:
            return

        status.error_count += 1
        status.last_error = error

        logger.warning(
            f"Health check failed for {exchange.value}: {error} "
            f"(failures: {status.error_count})"
        )

        # Mark as unhealthy after threshold
        if status.error_count >= self.config.health_check.max_failures:
            self._update_status(
                exchange,
                state=ConnectionState.FAILED,
                is_healthy=False,
                error=error
            )

            # Track failure time for cooldown
            self._failed_exchanges[exchange] = datetime.now(timezone.utc)

            # Trigger failover if needed
            if self.config.failover.enabled:
                asyncio.create_task(self._handle_failover(exchange))

    async def _handle_failover(self, failed_exchange: ExchangeName) -> None:
        """Handle failover when exchange fails"""
        if self._current_primary != failed_exchange:
            return

        # Find backup exchange
        healthy_exchanges = self.get_healthy_exchanges()

        # Try backups in order
        for backup in self.config.failover.backup_exchanges:
            if backup in healthy_exchanges:
                logger.info(
                    f"Failing over from {failed_exchange.value} to {backup.value}"
                )
                self._current_primary = backup

                await self._trigger_callback(
                    "failover",
                    failed_exchange,
                    backup
                )
                return

        # Fall back to any healthy exchange
        for exchange in healthy_exchanges:
            if exchange != failed_exchange:
                logger.info(
                    f"Failing over from {failed_exchange.value} to {exchange.value}"
                )
                self._current_primary = exchange

                await self._trigger_callback(
                    "failover",
                    failed_exchange,
                    exchange
                )
                return

        logger.error("No healthy exchanges available for failover")

    async def reconnect_exchange(self, exchange: ExchangeName) -> bool:
        """
        Attempt to reconnect to a failed exchange

        Args:
            exchange: Exchange to reconnect

        Returns:
            True if reconnection successful
        """
        config = self._configs.get(exchange)
        if not config:
            logger.error(f"No config stored for {exchange.value}")
            return False

        # Check cooldown
        if exchange in self._failed_exchanges:
            failed_at = self._failed_exchanges[exchange]
            elapsed = (datetime.now(timezone.utc) - failed_at).total_seconds()
            if elapsed < self.config.failover.cooldown_seconds:
                logger.debug(
                    f"Skipping reconnect for {exchange.value}: "
                    f"in cooldown ({elapsed:.0f}s elapsed)"
                )
                return False

        logger.info(f"Attempting reconnect to {exchange.value}")

        # Remove old adapter
        if exchange in self._adapters:
            try:
                await self._adapters[exchange].close()
            except Exception:
                pass
            del self._adapters[exchange]

        # Try to reconnect
        return await self.add_exchange(
            exchange=exchange,
            api_key=config.api_key,
            api_secret=config.api_secret,
            testnet=config.testnet,
            passphrase=config.passphrase
        )

    # ========================================================================
    # TRADING OPERATIONS
    # ========================================================================

    async def route_order(
        self,
        order: UnifiedOrder,
        strategy: Optional[RoutingStrategy] = None
    ) -> RoutingDecision:
        """
        Route order to optimal exchange

        Args:
            order: Order to route
            strategy: Routing strategy

        Returns:
            Routing decision
        """
        if not self._router:
            raise RuntimeError("Manager not started")

        return await self._router.route_order(order, strategy)

    async def execute_order(
        self,
        order: UnifiedOrder,
        exchange: Optional[ExchangeName] = None
    ) -> UnifiedOrder:
        """
        Execute order on specified exchange

        Args:
            order: Order to execute
            exchange: Target exchange (uses primary if None)

        Returns:
            Executed order with updates
        """
        target = exchange or self._current_primary

        if not target:
            raise RuntimeError("No exchange available")

        adapter = self._adapters.get(target)
        if not adapter:
            raise RuntimeError(f"No adapter for {target.value}")

        async with self._request_semaphore:
            try:
                order.exchange = target
                result = await adapter.place_order(order)

                logger.info(
                    f"Order executed on {target.value}: "
                    f"{result.symbol} {result.side.value} {result.quantity} "
                    f"(id={result.exchange_order_id})"
                )

                return result

            except RateLimitError as e:
                # Try failover on rate limit
                if self.config.failover.enabled:
                    return await self._execute_with_failover(order, target)
                raise

            except ExchangeError:
                raise

    async def _execute_with_failover(
        self,
        order: UnifiedOrder,
        failed_exchange: ExchangeName
    ) -> UnifiedOrder:
        """Try to execute order on backup exchanges"""
        for exchange in self.get_healthy_exchanges():
            if exchange == failed_exchange:
                continue

            adapter = self._adapters.get(exchange)
            if not adapter:
                continue

            try:
                order.exchange = exchange
                return await adapter.place_order(order)
            except Exception as e:
                logger.warning(
                    f"Failover order failed on {exchange.value}: {e}"
                )
                continue

        raise RuntimeError("All exchanges failed for order execution")

    # ========================================================================
    # PORTFOLIO AGGREGATION
    # ========================================================================

    async def get_portfolio_summary(self) -> PortfolioSummary:
        """
        Get aggregated portfolio across all exchanges

        Returns:
            Cross-exchange portfolio summary
        """
        summary = PortfolioSummary()

        # Fetch balances from all exchanges
        tasks = []
        exchanges = []

        for exchange, adapter in self._adapters.items():
            if self._status.get(exchange, ExchangeStatus(exchange)).is_healthy:
                tasks.append(adapter.get_balance())
                exchanges.append(exchange)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        for exchange, result in zip(exchanges, results):
            if isinstance(result, AccountBalance):
                summary.by_exchange[exchange] = result
                summary.total_equity += result.total_equity
                summary.available_balance += result.available_balance
                summary.used_margin += result.used_margin
                summary.unrealized_pnl += result.unrealized_pnl

                # Aggregate by asset
                for asset in result.assets:
                    if asset.asset not in summary.by_asset:
                        summary.by_asset[asset.asset] = Decimal("0")
                    summary.by_asset[asset.asset] += asset.total

        # Count positions
        position_results = await self.get_all_positions()
        summary.positions_count = len(position_results)

        summary.updated_at = datetime.now(timezone.utc)

        return summary

    async def get_all_positions(
        self,
        symbol: Optional[str] = None
    ) -> List[Tuple[ExchangeName, UnifiedPosition]]:
        """
        Get positions from all exchanges

        Args:
            symbol: Filter by symbol

        Returns:
            List of (exchange, position) tuples
        """
        all_positions = []

        tasks = []
        exchanges = []

        for exchange, adapter in self._adapters.items():
            if self._status.get(exchange, ExchangeStatus(exchange)).is_healthy:
                tasks.append(adapter.get_positions(symbol=symbol))
                exchanges.append(exchange)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for exchange, result in zip(exchanges, results):
            if isinstance(result, list):
                for position in result:
                    all_positions.append((exchange, position))

        return all_positions

    async def calculate_risk(self) -> CrossExchangeRisk:
        """
        Calculate cross-exchange risk metrics

        Returns:
            Risk metrics
        """
        risk = CrossExchangeRisk()

        # Get all positions
        positions = await self.get_all_positions()

        if not positions:
            return risk

        # Calculate total exposure
        total_exposure = Decimal("0")
        exposure_by_exchange: Dict[ExchangeName, Decimal] = {}
        exposure_by_symbol: Dict[str, Decimal] = {}

        for exchange, position in positions:
            exposure = position.notional_value

            total_exposure += exposure

            if exchange not in exposure_by_exchange:
                exposure_by_exchange[exchange] = Decimal("0")
            exposure_by_exchange[exchange] += exposure

            if position.symbol not in exposure_by_symbol:
                exposure_by_symbol[position.symbol] = Decimal("0")
            exposure_by_symbol[position.symbol] += exposure

        risk.total_exposure = total_exposure

        # Calculate concentration
        if total_exposure > 0:
            for exchange, exp in exposure_by_exchange.items():
                risk.concentration_by_exchange[exchange] = float(exp / total_exposure)

            for symbol, exp in exposure_by_symbol.items():
                risk.concentration_by_symbol[symbol] = float(exp / total_exposure)

        # Calculate risk score (simple heuristic)
        # Higher concentration = higher risk
        max_exchange_conc = max(
            risk.concentration_by_exchange.values(),
            default=0
        )
        max_symbol_conc = max(
            risk.concentration_by_symbol.values(),
            default=0
        )

        risk.risk_score = (max_exchange_conc + max_symbol_conc) / 2 * 100

        return risk

    # ========================================================================
    # EVENT CALLBACKS
    # ========================================================================

    def on_connected(self, callback: Callable) -> None:
        """Register callback for exchange connection"""
        self._callbacks["connected"].append(callback)

    def on_disconnected(self, callback: Callable) -> None:
        """Register callback for exchange disconnection"""
        self._callbacks["disconnected"].append(callback)

    def on_health_changed(self, callback: Callable) -> None:
        """Register callback for health status change"""
        self._callbacks["health_changed"].append(callback)

    def on_failover(self, callback: Callable) -> None:
        """Register callback for failover events"""
        self._callbacks["failover"].append(callback)

    async def _trigger_callback(
        self,
        event: str,
        *args,
        **kwargs
    ) -> None:
        """Trigger callbacks for an event"""
        for callback in self._callbacks.get(event, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(*args, **kwargs)
                else:
                    callback(*args, **kwargs)
            except Exception as e:
                logger.error(f"Callback error for {event}: {e}")


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================

async def create_exchange_manager(
    exchanges: List[Dict[str, Any]],
    config: Optional[ManagerConfig] = None
) -> ExchangeManager:
    """
    Create and configure exchange manager

    Args:
        exchanges: List of exchange configurations
            [{"exchange": "bybit", "api_key": "...", "api_secret": "...", "testnet": True}, ...]
        config: Manager configuration

    Returns:
        Configured and started ExchangeManager

    Example:
        manager = await create_exchange_manager([
            {
                "exchange": "bybit",
                "api_key": "key",
                "api_secret": "secret",
                "testnet": True
            },
            {
                "exchange": "binance",
                "api_key": "key",
                "api_secret": "secret",
                "testnet": True
            }
        ])
    """
    manager = ExchangeManager(config)
    await manager.start()

    for ex_config in exchanges:
        exchange_name = ex_config.pop("exchange")
        if isinstance(exchange_name, str):
            exchange_name = ExchangeName(exchange_name)

        await manager.add_exchange(
            exchange=exchange_name,
            **ex_config
        )

    return manager


__all__ = [
    # State
    "ConnectionState",
    "ExchangeStatus",

    # Configuration
    "HealthCheckConfig",
    "FailoverConfig",
    "ManagerConfig",

    # Data
    "PortfolioSummary",
    "CrossExchangeRisk",

    # Manager
    "ExchangeManager",
    "create_exchange_manager",
]
