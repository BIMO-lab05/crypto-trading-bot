"""
Exchange Router Module - Phase 6: Multi-Exchange Support
Purpose: Smart order routing and cross-exchange optimization

This module provides intelligent order routing capabilities:
- Route orders to best exchange based on liquidity, fees, latency
- Split large orders across multiple exchanges
- Detect cross-exchange arbitrage opportunities
- Balance-aware routing

Architecture:
    +------------------+
    | ExchangeRouter   |
    +--------+---------+
             |
    +--------+---------+---------+
    |        |         |         |
    v        v         v         v
  Bybit   Binance   Kraken   Coinbase
  (best   (lowest   (good    (fiat
  liquidity) fees)  security) gateway)

Created: 2025-12-11
Author: Backend Developer Agent
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from app.exchanges.base import (
    AccountBalance,
    ExchangeConfig,
    ExchangeInterface,
    ExchangeName,
    OrderBook,
    OrderSide,
    OrderStatus,
    OrderType,
    ProductType,
    Ticker,
    UnifiedOrder,
)
from app.exchanges.errors import (
    ExchangeError,
    InsufficientBalanceError,
    ValidationError,
)

# Configure logger
logger = logging.getLogger(__name__)


# ============================================================================
# ROUTING ENUMERATIONS
# ============================================================================

class RoutingStrategy(str, Enum):
    """Order routing strategies"""
    BEST_PRICE = "best_price"  # Route to exchange with best price
    LOWEST_FEE = "lowest_fee"  # Route to exchange with lowest fees
    LOWEST_LATENCY = "lowest_latency"  # Route to fastest exchange
    BEST_LIQUIDITY = "best_liquidity"  # Route to most liquid exchange
    SMART = "smart"  # Balanced optimization
    SPLIT = "split"  # Split across exchanges
    ARBITRAGE = "arbitrage"  # Cross-exchange arbitrage


class RoutingPriority(str, Enum):
    """Priority factors for routing decisions"""
    PRICE = "price"
    FEE = "fee"
    LIQUIDITY = "liquidity"
    LATENCY = "latency"
    BALANCE = "balance"


# ============================================================================
# ROUTING CONFIGURATION
# ============================================================================

@dataclass
class ExchangeMetrics:
    """
    Real-time metrics for an exchange

    Used by router to make routing decisions.

    Attributes:
        exchange: Exchange identifier
        latency_ms: Average request latency in milliseconds
        fill_rate: Historical fill rate (0-1)
        uptime: Recent uptime percentage (0-100)
        fee_maker: Maker fee rate
        fee_taker: Taker fee rate
        last_updated: When metrics were last updated
    """
    exchange: ExchangeName
    latency_ms: float = 100.0
    fill_rate: float = 0.95
    uptime: float = 99.9
    fee_maker: Decimal = Decimal("0.001")  # 0.1%
    fee_taker: Decimal = Decimal("0.001")  # 0.1%
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_stale(self, max_age_seconds: int = 60) -> bool:
        """Check if metrics are stale"""
        age = (datetime.now(timezone.utc) - self.last_updated).total_seconds()
        return age > max_age_seconds


@dataclass
class ExchangeLiquidity:
    """
    Liquidity snapshot for an exchange

    Attributes:
        exchange: Exchange identifier
        symbol: Trading pair
        bid_depth: Total bid liquidity (quote currency)
        ask_depth: Total ask liquidity (quote currency)
        spread_bps: Spread in basis points
        best_bid: Best bid price
        best_ask: Best ask price
        timestamp: Snapshot timestamp
    """
    exchange: ExchangeName
    symbol: str
    bid_depth: Decimal = Decimal("0")
    ask_depth: Decimal = Decimal("0")
    spread_bps: float = 0.0
    best_bid: Decimal = Decimal("0")
    best_ask: Decimal = Decimal("0")
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class RoutingConfig(BaseModel):
    """
    Configuration for order routing

    Attributes:
        strategy: Default routing strategy
        priorities: Priority weights for routing factors
        min_liquidity_ratio: Minimum liquidity vs order size ratio
        max_spread_bps: Maximum acceptable spread in basis points
        max_slippage_bps: Maximum acceptable slippage
        split_threshold: Order size threshold for splitting (USD)
        max_exchanges: Maximum exchanges to use for split orders
        enable_arbitrage: Enable arbitrage detection
        arbitrage_min_profit_bps: Minimum profit for arbitrage (basis points)
    """
    strategy: RoutingStrategy = Field(
        default=RoutingStrategy.SMART,
        description="Default routing strategy"
    )
    priorities: Dict[RoutingPriority, float] = Field(
        default_factory=lambda: {
            RoutingPriority.PRICE: 0.4,
            RoutingPriority.LIQUIDITY: 0.3,
            RoutingPriority.FEE: 0.2,
            RoutingPriority.LATENCY: 0.1,
        },
        description="Priority weights for routing factors"
    )
    min_liquidity_ratio: float = Field(
        default=3.0,
        description="Minimum liquidity/order ratio"
    )
    max_spread_bps: float = Field(
        default=50.0,
        description="Maximum spread in basis points"
    )
    max_slippage_bps: float = Field(
        default=10.0,
        description="Maximum slippage in basis points"
    )
    split_threshold: float = Field(
        default=100000.0,
        description="Order size threshold for splitting (USD)"
    )
    max_exchanges: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum exchanges for split orders"
    )
    enable_arbitrage: bool = Field(
        default=True,
        description="Enable arbitrage detection"
    )
    arbitrage_min_profit_bps: float = Field(
        default=20.0,
        description="Minimum arbitrage profit in basis points"
    )


# ============================================================================
# ROUTING RESULT
# ============================================================================

@dataclass
class RoutingDecision:
    """
    Result of routing decision

    Attributes:
        exchange: Selected exchange
        symbol: Trading pair
        score: Routing score (higher is better)
        reasons: List of reasons for selection
        alternatives: Alternative exchanges ranked
        estimated_fill_price: Expected execution price
        estimated_fee: Expected fee amount
        estimated_slippage_bps: Expected slippage
    """
    exchange: ExchangeName
    symbol: str
    score: float
    reasons: List[str] = field(default_factory=list)
    alternatives: List[Tuple[ExchangeName, float]] = field(default_factory=list)
    estimated_fill_price: Optional[Decimal] = None
    estimated_fee: Optional[Decimal] = None
    estimated_slippage_bps: Optional[float] = None


@dataclass
class SplitOrderPlan:
    """
    Plan for splitting order across exchanges

    Attributes:
        total_quantity: Total order quantity
        allocations: Quantity allocation per exchange
        estimated_total_cost: Total estimated cost
        estimated_avg_price: Weighted average price
    """
    total_quantity: Decimal
    allocations: Dict[ExchangeName, Decimal] = field(default_factory=dict)
    estimated_total_cost: Decimal = Decimal("0")
    estimated_avg_price: Decimal = Decimal("0")


@dataclass
class ArbitrageOpportunity:
    """
    Cross-exchange arbitrage opportunity

    Attributes:
        buy_exchange: Exchange to buy on
        sell_exchange: Exchange to sell on
        symbol: Trading pair
        buy_price: Price to buy at
        sell_price: Price to sell at
        profit_bps: Profit in basis points
        max_quantity: Maximum executable quantity
        expires_at: When opportunity expires
    """
    buy_exchange: ExchangeName
    sell_exchange: ExchangeName
    symbol: str
    buy_price: Decimal
    sell_price: Decimal
    profit_bps: float
    max_quantity: Decimal
    expires_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(seconds=5)
    )

    @property
    def is_expired(self) -> bool:
        """Check if opportunity has expired"""
        return datetime.now(timezone.utc) > self.expires_at


# ============================================================================
# EXCHANGE ROUTER
# ============================================================================

class ExchangeRouter:
    """
    Smart order router for multi-exchange trading

    Routes orders to optimal exchange based on:
    - Price (best execution)
    - Liquidity (depth, spread)
    - Fees (maker/taker rates)
    - Latency (response time)
    - Available balance

    Features:
    - Real-time liquidity analysis
    - Dynamic exchange scoring
    - Order splitting for large orders
    - Cross-exchange arbitrage detection
    - Balance-aware routing

    Usage:
        router = ExchangeRouter(config)
        router.register_exchange(bybit_adapter)
        router.register_exchange(binance_adapter)

        # Get best exchange for order
        decision = await router.route_order(order)

        # Or split large order
        plan = await router.plan_split_order(order)

        # Detect arbitrage
        opportunities = await router.find_arbitrage("BTCUSDT")
    """

    def __init__(
        self,
        config: Optional[RoutingConfig] = None
    ):
        """
        Initialize exchange router

        Args:
            config: Routing configuration
        """
        self.config = config or RoutingConfig()

        # Registered exchanges
        self._exchanges: Dict[ExchangeName, ExchangeInterface] = {}

        # Exchange metrics cache
        self._metrics: Dict[ExchangeName, ExchangeMetrics] = {}

        # Liquidity cache
        self._liquidity_cache: Dict[str, Dict[ExchangeName, ExchangeLiquidity]] = {}

        # Balance cache
        self._balance_cache: Dict[ExchangeName, AccountBalance] = {}

        # Locks for async operations
        self._metrics_lock = asyncio.Lock()
        self._liquidity_lock = asyncio.Lock()

        logger.info(
            f"Created ExchangeRouter (strategy={config.strategy.value if config else 'smart'})"
        )

    # ========================================================================
    # EXCHANGE MANAGEMENT
    # ========================================================================

    def register_exchange(
        self,
        adapter: ExchangeInterface,
        metrics: Optional[ExchangeMetrics] = None
    ) -> None:
        """
        Register an exchange adapter

        Args:
            adapter: Exchange adapter instance
            metrics: Initial metrics (optional)
        """
        exchange = adapter.exchange_name
        self._exchanges[exchange] = adapter

        # Set default metrics
        if metrics:
            self._metrics[exchange] = metrics
        else:
            self._metrics[exchange] = self._get_default_metrics(exchange)

        logger.info(f"Registered exchange: {exchange.value}")

    def unregister_exchange(self, exchange: ExchangeName) -> bool:
        """
        Unregister an exchange

        Args:
            exchange: Exchange to unregister

        Returns:
            True if exchange was unregistered
        """
        if exchange in self._exchanges:
            del self._exchanges[exchange]
            if exchange in self._metrics:
                del self._metrics[exchange]
            logger.info(f"Unregistered exchange: {exchange.value}")
            return True
        return False

    def _get_default_metrics(self, exchange: ExchangeName) -> ExchangeMetrics:
        """Get default metrics for exchange"""
        # Default fee structures (approximate)
        default_fees = {
            ExchangeName.BYBIT: (Decimal("0.0001"), Decimal("0.0006")),  # 0.01%, 0.06%
            ExchangeName.BINANCE: (Decimal("0.0002"), Decimal("0.0004")),  # 0.02%, 0.04%
            ExchangeName.KRAKEN: (Decimal("0.0016"), Decimal("0.0026")),  # 0.16%, 0.26%
            ExchangeName.COINBASE: (Decimal("0.004"), Decimal("0.006")),  # 0.4%, 0.6%
        }

        maker_fee, taker_fee = default_fees.get(
            exchange,
            (Decimal("0.001"), Decimal("0.001"))
        )

        return ExchangeMetrics(
            exchange=exchange,
            fee_maker=maker_fee,
            fee_taker=taker_fee
        )

    def get_available_exchanges(self) -> List[ExchangeName]:
        """Get list of registered exchanges"""
        return list(self._exchanges.keys())

    # ========================================================================
    # METRICS MANAGEMENT
    # ========================================================================

    async def update_metrics(
        self,
        exchange: ExchangeName,
        latency_ms: Optional[float] = None,
        fill_rate: Optional[float] = None,
        uptime: Optional[float] = None
    ) -> None:
        """
        Update exchange metrics

        Args:
            exchange: Exchange to update
            latency_ms: New latency measurement
            fill_rate: New fill rate
            uptime: New uptime percentage
        """
        async with self._metrics_lock:
            if exchange not in self._metrics:
                self._metrics[exchange] = self._get_default_metrics(exchange)

            metrics = self._metrics[exchange]

            if latency_ms is not None:
                # Exponential moving average for latency
                metrics.latency_ms = metrics.latency_ms * 0.8 + latency_ms * 0.2

            if fill_rate is not None:
                metrics.fill_rate = fill_rate

            if uptime is not None:
                metrics.uptime = uptime

            metrics.last_updated = datetime.now(timezone.utc)

    async def refresh_all_metrics(self) -> None:
        """Refresh metrics for all registered exchanges"""
        tasks = []
        for exchange, adapter in self._exchanges.items():
            tasks.append(self._measure_exchange_latency(exchange, adapter))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _measure_exchange_latency(
        self,
        exchange: ExchangeName,
        adapter: ExchangeInterface
    ) -> None:
        """Measure latency for an exchange"""
        try:
            start = asyncio.get_event_loop().time()
            await adapter.health_check()
            latency_ms = (asyncio.get_event_loop().time() - start) * 1000
            await self.update_metrics(exchange, latency_ms=latency_ms)
        except Exception as e:
            logger.warning(f"Failed to measure latency for {exchange.value}: {e}")

    # ========================================================================
    # LIQUIDITY ANALYSIS
    # ========================================================================

    async def get_liquidity(
        self,
        symbol: str,
        exchange: Optional[ExchangeName] = None
    ) -> Dict[ExchangeName, ExchangeLiquidity]:
        """
        Get liquidity data for a symbol

        Args:
            symbol: Trading pair
            exchange: Specific exchange (None for all)

        Returns:
            Liquidity data per exchange
        """
        exchanges = [exchange] if exchange else list(self._exchanges.keys())

        tasks = []
        for ex in exchanges:
            if ex in self._exchanges:
                tasks.append(self._fetch_liquidity(ex, symbol))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        liquidity = {}
        for ex, result in zip(exchanges, results):
            if isinstance(result, ExchangeLiquidity):
                liquidity[ex] = result

        return liquidity

    async def _fetch_liquidity(
        self,
        exchange: ExchangeName,
        symbol: str
    ) -> ExchangeLiquidity:
        """Fetch liquidity for a single exchange"""
        adapter = self._exchanges[exchange]

        try:
            orderbook = await adapter.get_orderbook(symbol, depth=50)

            # Calculate metrics
            bid_depth = sum(
                level.price * level.quantity
                for level in orderbook.bids[:25]
            )
            ask_depth = sum(
                level.price * level.quantity
                for level in orderbook.asks[:25]
            )

            best_bid = orderbook.best_bid.price if orderbook.best_bid else Decimal("0")
            best_ask = orderbook.best_ask.price if orderbook.best_ask else Decimal("0")

            spread_bps = 0.0
            if best_bid and best_ask:
                mid_price = (best_bid + best_ask) / 2
                if mid_price > 0:
                    spread_bps = float((best_ask - best_bid) / mid_price * 10000)

            return ExchangeLiquidity(
                exchange=exchange,
                symbol=symbol,
                bid_depth=bid_depth,
                ask_depth=ask_depth,
                spread_bps=spread_bps,
                best_bid=best_bid,
                best_ask=best_ask,
                timestamp=datetime.now(timezone.utc)
            )

        except Exception as e:
            logger.warning(f"Failed to fetch liquidity from {exchange.value}: {e}")
            return ExchangeLiquidity(exchange=exchange, symbol=symbol)

    # ========================================================================
    # ORDER ROUTING
    # ========================================================================

    async def route_order(
        self,
        order: UnifiedOrder,
        strategy: Optional[RoutingStrategy] = None
    ) -> RoutingDecision:
        """
        Determine optimal exchange for order

        Args:
            order: Order to route
            strategy: Routing strategy (uses config default if None)

        Returns:
            Routing decision with selected exchange

        Raises:
            ValidationError: If no exchanges available
        """
        if not self._exchanges:
            raise ValidationError(
                message="No exchanges registered",
                exchange="router"
            )

        strategy = strategy or self.config.strategy

        # Get current liquidity
        liquidity = await self.get_liquidity(order.symbol)

        # Score each exchange
        scores: List[Tuple[ExchangeName, float, List[str]]] = []

        for exchange in self._exchanges:
            score, reasons = await self._score_exchange(
                exchange,
                order,
                strategy,
                liquidity.get(exchange)
            )
            scores.append((exchange, score, reasons))

        # Sort by score (descending)
        scores.sort(key=lambda x: x[1], reverse=True)

        if not scores or scores[0][1] <= 0:
            raise ValidationError(
                message="No suitable exchange found for order",
                exchange="router"
            )

        # Build decision
        best_exchange, best_score, best_reasons = scores[0]
        alternatives = [(ex, sc) for ex, sc, _ in scores[1:]]

        # Get estimated execution metrics
        liq = liquidity.get(best_exchange)
        estimated_price = None
        estimated_slippage = None

        if liq:
            if order.side == OrderSide.BUY:
                estimated_price = liq.best_ask
            else:
                estimated_price = liq.best_bid

            if estimated_price and estimated_price > 0:
                # Estimate slippage based on order size vs liquidity
                order_value = order.quantity * estimated_price
                available_liq = liq.ask_depth if order.side == OrderSide.BUY else liq.bid_depth
                if available_liq > 0:
                    estimated_slippage = float(order_value / available_liq * 100)

        # Calculate estimated fee
        metrics = self._metrics.get(best_exchange)
        estimated_fee = None
        if metrics and estimated_price:
            fee_rate = metrics.fee_taker if order.order_type == OrderType.MARKET else metrics.fee_maker
            estimated_fee = order.quantity * estimated_price * fee_rate

        return RoutingDecision(
            exchange=best_exchange,
            symbol=order.symbol,
            score=best_score,
            reasons=best_reasons,
            alternatives=alternatives,
            estimated_fill_price=estimated_price,
            estimated_fee=estimated_fee,
            estimated_slippage_bps=estimated_slippage
        )

    async def _score_exchange(
        self,
        exchange: ExchangeName,
        order: UnifiedOrder,
        strategy: RoutingStrategy,
        liquidity: Optional[ExchangeLiquidity]
    ) -> Tuple[float, List[str]]:
        """
        Score an exchange for routing

        Args:
            exchange: Exchange to score
            order: Order to route
            strategy: Routing strategy
            liquidity: Current liquidity data

        Returns:
            Tuple of (score, reasons)
        """
        score = 0.0
        reasons = []
        metrics = self._metrics.get(exchange)

        if not metrics:
            return 0.0, ["No metrics available"]

        # Check if exchange is healthy
        if metrics.uptime < 95:
            return 0.0, [f"Low uptime: {metrics.uptime}%"]

        # Strategy-specific scoring
        if strategy == RoutingStrategy.BEST_PRICE:
            if liquidity:
                # Prefer exchange with best price
                price_score = self._calculate_price_score(order, liquidity)
                score = price_score * 100
                reasons.append(f"Price score: {price_score:.2f}")

        elif strategy == RoutingStrategy.LOWEST_FEE:
            # Prefer exchange with lowest fees
            fee_score = 1 - float(metrics.fee_taker)
            score = fee_score * 100
            reasons.append(f"Fee: {float(metrics.fee_taker) * 100:.3f}%")

        elif strategy == RoutingStrategy.LOWEST_LATENCY:
            # Prefer exchange with lowest latency
            latency_score = 1 / (1 + metrics.latency_ms / 100)
            score = latency_score * 100
            reasons.append(f"Latency: {metrics.latency_ms:.0f}ms")

        elif strategy == RoutingStrategy.BEST_LIQUIDITY:
            if liquidity:
                # Prefer exchange with best liquidity
                liq_score = self._calculate_liquidity_score(order, liquidity)
                score = liq_score * 100
                reasons.append(f"Liquidity score: {liq_score:.2f}")

        elif strategy == RoutingStrategy.SMART:
            # Balanced scoring using configured priorities
            scores = {}

            if liquidity:
                scores[RoutingPriority.PRICE] = self._calculate_price_score(order, liquidity)
                scores[RoutingPriority.LIQUIDITY] = self._calculate_liquidity_score(order, liquidity)

            scores[RoutingPriority.FEE] = 1 - float(metrics.fee_taker)
            scores[RoutingPriority.LATENCY] = 1 / (1 + metrics.latency_ms / 100)

            # Calculate weighted score
            for priority, weight in self.config.priorities.items():
                if priority in scores:
                    score += scores[priority] * weight * 100
                    reasons.append(f"{priority.value}: {scores[priority]:.2f}")

        # Check balance availability
        balance = self._balance_cache.get(exchange)
        if balance:
            # Verify sufficient balance
            order_value = order.quantity * (order.price or Decimal("1"))
            if balance.available_balance < order_value:
                score *= 0.5  # Penalize but don't eliminate
                reasons.append("Insufficient balance")

        return score, reasons

    def _calculate_price_score(
        self,
        order: UnifiedOrder,
        liquidity: ExchangeLiquidity
    ) -> float:
        """Calculate price score (0-1)"""
        if order.side == OrderSide.BUY:
            # Lower ask is better for buying
            if liquidity.best_ask > 0:
                return 1.0  # Normalized later when comparing
        else:
            # Higher bid is better for selling
            if liquidity.best_bid > 0:
                return 1.0

        return 0.0

    def _calculate_liquidity_score(
        self,
        order: UnifiedOrder,
        liquidity: ExchangeLiquidity
    ) -> float:
        """Calculate liquidity score (0-1)"""
        # Calculate order value
        price = liquidity.best_ask if order.side == OrderSide.BUY else liquidity.best_bid
        if not price:
            return 0.0

        order_value = float(order.quantity * price)
        available = float(liquidity.ask_depth if order.side == OrderSide.BUY else liquidity.bid_depth)

        if available <= 0:
            return 0.0

        # Score based on liquidity ratio
        ratio = available / order_value
        return min(1.0, ratio / self.config.min_liquidity_ratio)

    # ========================================================================
    # ORDER SPLITTING
    # ========================================================================

    async def plan_split_order(
        self,
        order: UnifiedOrder,
        max_exchanges: Optional[int] = None
    ) -> SplitOrderPlan:
        """
        Plan order split across multiple exchanges

        Args:
            order: Order to split
            max_exchanges: Maximum exchanges to use

        Returns:
            Split order plan with allocations
        """
        max_ex = max_exchanges or self.config.max_exchanges

        # Get liquidity from all exchanges
        liquidity = await self.get_liquidity(order.symbol)

        # Calculate available depth per exchange
        depths: List[Tuple[ExchangeName, Decimal]] = []

        for exchange, liq in liquidity.items():
            if order.side == OrderSide.BUY:
                depth = liq.ask_depth
            else:
                depth = liq.bid_depth

            if depth > 0:
                depths.append((exchange, depth))

        # Sort by depth (descending)
        depths.sort(key=lambda x: x[1], reverse=True)

        # Allocate quantity proportionally
        allocations = {}
        remaining = order.quantity
        total_depth = sum(d for _, d in depths[:max_ex])

        if total_depth <= 0:
            # Fallback to equal split
            per_exchange = order.quantity / Decimal(min(len(depths), max_ex))
            for exchange, _ in depths[:max_ex]:
                allocations[exchange] = per_exchange
        else:
            # Proportional allocation based on depth
            for exchange, depth in depths[:max_ex]:
                if remaining <= 0:
                    break

                proportion = depth / total_depth
                allocation = min(remaining, order.quantity * proportion)
                allocations[exchange] = allocation
                remaining -= allocation

            # Distribute any remaining to first exchange
            if remaining > 0 and allocations:
                first = list(allocations.keys())[0]
                allocations[first] += remaining

        # Calculate estimated costs
        total_cost = Decimal("0")
        weighted_price = Decimal("0")

        for exchange, qty in allocations.items():
            liq = liquidity.get(exchange)
            if liq:
                price = liq.best_ask if order.side == OrderSide.BUY else liq.best_bid
                if price:
                    cost = qty * price
                    total_cost += cost
                    weighted_price += cost

        avg_price = weighted_price / order.quantity if order.quantity > 0 else Decimal("0")

        return SplitOrderPlan(
            total_quantity=order.quantity,
            allocations=allocations,
            estimated_total_cost=total_cost,
            estimated_avg_price=avg_price
        )

    async def execute_split_order(
        self,
        order: UnifiedOrder,
        plan: SplitOrderPlan
    ) -> List[Tuple[ExchangeName, UnifiedOrder]]:
        """
        Execute a split order plan

        Args:
            order: Original order
            plan: Split plan to execute

        Returns:
            List of (exchange, result_order) tuples
        """
        results = []

        for exchange, quantity in plan.allocations.items():
            adapter = self._exchanges.get(exchange)
            if not adapter:
                continue

            # Create order for this exchange
            split_order = UnifiedOrder(
                exchange=exchange,
                symbol=order.symbol,
                product_type=order.product_type,
                side=order.side,
                order_type=order.order_type,
                quantity=quantity,
                price=order.price,
                time_in_force=order.time_in_force
            )

            try:
                result = await adapter.place_order(split_order)
                results.append((exchange, result))
            except ExchangeError as e:
                logger.error(f"Failed to place order on {exchange.value}: {e}")
                results.append((exchange, split_order))  # Return original with status

        return results

    # ========================================================================
    # ARBITRAGE DETECTION
    # ========================================================================

    async def find_arbitrage(
        self,
        symbol: str,
        min_profit_bps: Optional[float] = None
    ) -> List[ArbitrageOpportunity]:
        """
        Find cross-exchange arbitrage opportunities

        Args:
            symbol: Trading pair to analyze
            min_profit_bps: Minimum profit in basis points

        Returns:
            List of arbitrage opportunities
        """
        if not self.config.enable_arbitrage:
            return []

        min_profit = min_profit_bps or self.config.arbitrage_min_profit_bps

        # Get liquidity from all exchanges
        liquidity = await self.get_liquidity(symbol)

        opportunities = []

        # Compare all exchange pairs
        exchanges = list(liquidity.keys())

        for i, buy_ex in enumerate(exchanges):
            for sell_ex in exchanges[i + 1:]:
                buy_liq = liquidity[buy_ex]
                sell_liq = liquidity[sell_ex]

                if not buy_liq.best_ask or not sell_liq.best_bid:
                    continue

                # Check buy on buy_ex, sell on sell_ex
                profit_bps = self._calculate_arb_profit(
                    buy_liq.best_ask,
                    sell_liq.best_bid,
                    self._metrics.get(buy_ex),
                    self._metrics.get(sell_ex)
                )

                if profit_bps >= min_profit:
                    max_qty = min(buy_liq.ask_depth, sell_liq.bid_depth) / buy_liq.best_ask
                    opportunities.append(ArbitrageOpportunity(
                        buy_exchange=buy_ex,
                        sell_exchange=sell_ex,
                        symbol=symbol,
                        buy_price=buy_liq.best_ask,
                        sell_price=sell_liq.best_bid,
                        profit_bps=profit_bps,
                        max_quantity=max_qty
                    ))

                # Check opposite direction
                profit_bps = self._calculate_arb_profit(
                    sell_liq.best_ask,
                    buy_liq.best_bid,
                    self._metrics.get(sell_ex),
                    self._metrics.get(buy_ex)
                )

                if profit_bps >= min_profit:
                    max_qty = min(sell_liq.ask_depth, buy_liq.bid_depth) / sell_liq.best_ask
                    opportunities.append(ArbitrageOpportunity(
                        buy_exchange=sell_ex,
                        sell_exchange=buy_ex,
                        symbol=symbol,
                        buy_price=sell_liq.best_ask,
                        sell_price=buy_liq.best_bid,
                        profit_bps=profit_bps,
                        max_quantity=max_qty
                    ))

        # Sort by profit (descending)
        opportunities.sort(key=lambda x: x.profit_bps, reverse=True)

        return opportunities

    def _calculate_arb_profit(
        self,
        buy_price: Decimal,
        sell_price: Decimal,
        buy_metrics: Optional[ExchangeMetrics],
        sell_metrics: Optional[ExchangeMetrics]
    ) -> float:
        """Calculate arbitrage profit in basis points"""
        if buy_price <= 0 or sell_price <= 0:
            return 0.0

        # Calculate gross profit
        gross_profit_bps = float((sell_price - buy_price) / buy_price * 10000)

        # Subtract fees
        buy_fee_bps = float(buy_metrics.fee_taker * 10000) if buy_metrics else 10.0
        sell_fee_bps = float(sell_metrics.fee_taker * 10000) if sell_metrics else 10.0

        net_profit_bps = gross_profit_bps - buy_fee_bps - sell_fee_bps

        return net_profit_bps

    # ========================================================================
    # BALANCE MANAGEMENT
    # ========================================================================

    async def refresh_balances(self) -> None:
        """Refresh balance cache for all exchanges"""
        tasks = []
        for exchange, adapter in self._exchanges.items():
            tasks.append(self._fetch_balance(exchange, adapter))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _fetch_balance(
        self,
        exchange: ExchangeName,
        adapter: ExchangeInterface
    ) -> None:
        """Fetch and cache balance for an exchange"""
        try:
            balance = await adapter.get_balance()
            self._balance_cache[exchange] = balance
        except Exception as e:
            logger.warning(f"Failed to fetch balance from {exchange.value}: {e}")


__all__ = [
    # Enums
    "RoutingStrategy",
    "RoutingPriority",

    # Data classes
    "ExchangeMetrics",
    "ExchangeLiquidity",
    "RoutingDecision",
    "SplitOrderPlan",
    "ArbitrageOpportunity",

    # Config
    "RoutingConfig",

    # Router
    "ExchangeRouter",
]
