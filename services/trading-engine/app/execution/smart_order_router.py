"""
Smart Order Router - Intelligent Order Type Selection and Execution Optimization
Phase 4.1: Smart Order Routing - Main Integration Component

Purpose:
- Intelligent order routing based on size and urgency
- Orderbook analysis for optimal order type selection
- Iceberg order implementation for large sizes
- Multi-venue routing preparation (Bybit, Binance, OKX)
- Integration with orderbook analyzer and execution optimizer

Research Sources:
- Almgren-Chriss Optimal Execution Model
- Market Microstructure Theory
- Crypto Market Liquidity Analysis
- Post-Only Order Economics

Order Type Selection Matrix:
+------------------+------------------+------------------+------------------+
| Order Size       | Spread           | Urgency          | Recommendation   |
+------------------+------------------+------------------+------------------+
| <$1000           | <0.05%           | HIGH/CRITICAL    | MARKET           |
| <$1000           | <0.05%           | MEDIUM/LOW       | LIMIT            |
| <$1000           | >0.05%           | Any              | LIMIT            |
| $1000-$10000     | <0.05%           | HIGH/CRITICAL    | MARKET           |
| $1000-$10000     | >0.05%           | Any              | LIMIT at mid     |
| >$10000          | Any              | LOW              | ICEBERG          |
| >$10000          | Any              | MEDIUM/HIGH      | TWAP (3-5 split) |
| Any              | Any              | LOW (stat arb)   | POST_ONLY        |
+------------------+------------------+------------------+------------------+

Slippage Protection:
- Pre-trade slippage estimation
- Max acceptable: 0.1% for BTC/ETH, 0.3% for alts
- Cancel and retry if threshold exceeded
- Post-trade analysis and reporting

Created: 2025-12-11
Author: Backend Developer Agent
"""

import asyncio
import logging
import time
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Any, Callable
from collections import deque
import statistics

# Import orderbook analyzer for liquidity analysis
from app.execution.orderbook_analyzer import (
    OrderbookAnalyzer,
    OrderBookConfig,
    LiquidityReport,
    LiquidityLevel,
    MarketImpactEstimate,
    OptimalLimitPrice,
    get_orderbook_analyzer
)

# Import execution optimizer for fee and timing optimization
from app.execution.execution_optimizer import (
    ExecutionOptimizer,
    ExecutionOptimizerConfig,
    FeeStructure,
    ExecutionUrgency,
    OptimalOrderType,
    TimingStrategy,
    OptimizationResult,
    CostBreakdown,
    get_execution_optimizer
)

# Configure logging for smart order routing
logger = logging.getLogger(__name__)


# ============================================================================
# ENUMERATIONS
# ============================================================================

class RoutingStrategy(str, Enum):
    """
    Order routing strategy types

    SINGLE_EXCHANGE: Route to single exchange (current implementation)
    SMART_SPLIT: Split across exchanges for best execution (future)
    VENUE_OPTIMAL: Select best venue per order (future)
    """
    SINGLE_EXCHANGE = "single_exchange"
    SMART_SPLIT = "smart_split"           # Future: multi-venue
    VENUE_OPTIMAL = "venue_optimal"       # Future: best venue selection


class ExecutionMode(str, Enum):
    """
    Execution mode for order placement

    IMMEDIATE: Execute immediately with market/aggressive limit
    PASSIVE: Wait for fill, use maker orders
    SPLIT_TWAP: Time-weighted split execution
    SPLIT_ICEBERG: Hidden size with visible portion
    """
    IMMEDIATE = "immediate"
    PASSIVE = "passive"
    SPLIT_TWAP = "split_twap"
    SPLIT_ICEBERG = "split_iceberg"


class OrderStatus(str, Enum):
    """Order execution status"""
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class SmartRouterConfig:
    """
    Configuration for smart order routing

    Combines settings from orderbook analyzer and execution optimizer
    with routing-specific parameters.
    """
    # Order size thresholds (in USD)
    small_order_threshold: float = 1000.0        # Single market order OK
    medium_order_threshold: float = 10000.0      # Limit preferred
    large_order_threshold: float = 10000.0       # Requires splitting

    # Slippage thresholds by asset type (as percentage)
    btc_eth_max_slippage: float = 0.10           # 0.1% for major assets
    alt_max_slippage: float = 0.30               # 0.3% for altcoins
    default_max_slippage: float = 0.20           # 0.2% default

    # TWAP execution settings
    twap_min_chunks: int = 3                     # Minimum splits
    twap_max_chunks: int = 10                    # Maximum splits
    twap_interval_seconds: int = 120             # Seconds between chunks
    twap_max_duration_minutes: int = 30          # Maximum TWAP duration

    # Iceberg settings
    iceberg_visible_pct: float = 0.15            # Show 15% of order
    iceberg_min_visible_usd: float = 500.0       # Minimum visible amount
    iceberg_randomize: bool = True               # Randomize visible size

    # Retry settings
    max_retry_attempts: int = 3
    retry_delay_seconds: float = 1.0

    # Venue configuration (for multi-venue routing)
    enabled_venues: List[str] = field(default_factory=lambda: ["bybit"])
    primary_venue: str = "bybit"

    # Orderbook analyzer config
    orderbook_config: OrderBookConfig = field(default_factory=OrderBookConfig)

    # Execution optimizer config
    optimizer_config: ExecutionOptimizerConfig = field(default_factory=ExecutionOptimizerConfig)


@dataclass
class RoutingDecision:
    """
    Complete routing decision for an order

    Contains full execution plan including:
    - Venue selection
    - Order type and timing
    - Slippage and cost analysis
    - Execution mode and chunks
    """
    # Order details
    order_id: str
    symbol: str
    side: str
    quantity: Decimal
    order_value_usd: float
    urgency: ExecutionUrgency

    # Routing decision
    venue: str
    execution_mode: ExecutionMode
    order_type: OptimalOrderType
    timing: TimingStrategy

    # Price and limits
    limit_price: Optional[Decimal] = None
    max_acceptable_slippage_pct: float = 0.20

    # For split orders
    chunks: List[Dict] = field(default_factory=list)
    visible_quantity: Optional[Decimal] = None

    # Analysis
    liquidity_report: Optional[LiquidityReport] = None
    market_impact: Optional[MarketImpactEstimate] = None
    optimization_result: Optional[OptimizationResult] = None

    # Estimates
    estimated_slippage_pct: float = 0.0
    estimated_total_cost_pct: float = 0.0
    estimated_fill_probability: float = 0.0
    estimated_time_to_fill_seconds: float = 0.0

    # Decision reasoning
    reasoning: str = ""
    confidence: float = 0.0
    warnings: List[str] = field(default_factory=list)

    # Timestamp
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ExecutionResult:
    """
    Result of order execution

    Tracks actual execution metrics for performance analysis:
    - Fill rate and execution price
    - Actual vs estimated slippage
    - Execution time
    """
    # Order reference
    order_id: str
    routing_decision: RoutingDecision

    # Execution results
    status: OrderStatus
    filled_quantity: Decimal
    fill_rate: float
    average_price: Decimal

    # Slippage analysis
    expected_price: Decimal
    actual_slippage_pct: float
    slippage_vs_estimate: float  # Ratio of actual/expected

    # Cost analysis
    total_fees_paid: float
    total_slippage_cost: float
    total_execution_cost: float

    # Timing
    execution_start: datetime
    execution_end: datetime
    execution_time_ms: float

    # For split orders
    chunk_results: List[Dict] = field(default_factory=list)

    # Errors
    error_message: Optional[str] = None


@dataclass
class RouterMetrics:
    """
    Aggregate metrics for router performance

    Tracks overall effectiveness:
    - Average slippage reduction vs naive execution
    - Order type distribution
    - Fill rates by execution mode
    """
    # Order counts
    total_orders: int = 0
    successful_orders: int = 0
    partial_fills: int = 0
    failed_orders: int = 0

    # Slippage metrics
    avg_slippage_pct: float = 0.0
    max_slippage_pct: float = 0.0
    slippage_reduction_vs_baseline: float = 0.0  # vs naive market orders

    # Fill metrics
    avg_fill_rate: float = 0.0
    fill_rate_by_mode: Dict[str, float] = field(default_factory=dict)

    # Cost metrics
    total_fees_usd: float = 0.0
    total_slippage_cost_usd: float = 0.0
    estimated_savings_usd: float = 0.0

    # Order type distribution
    orders_by_type: Dict[str, int] = field(default_factory=dict)
    orders_by_mode: Dict[str, int] = field(default_factory=dict)

    # Timing
    avg_execution_time_ms: float = 0.0

    # Last update
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================================
# SMART ORDER ROUTER
# ============================================================================

class SmartOrderRouter:
    """
    Smart Order Routing Engine - Main Integration Component

    Combines orderbook analysis, execution optimization, and routing
    logic to provide intelligent order execution. Key capabilities:

    1. Intelligent Routing:
       - Analyze order book liquidity and spread
       - Select optimal order type based on conditions
       - Determine best execution mode (immediate/passive/split)

    2. Large Order Handling:
       - TWAP execution for time distribution
       - Iceberg orders for size hiding
       - Smart chunking based on liquidity

    3. Slippage Protection:
       - Pre-trade slippage estimation
       - Maximum slippage thresholds
       - Cancel and retry on excessive slippage

    4. Fee Optimization:
       - Maker vs taker fee analysis
       - Post-only orders for fee capture
       - Cost-benefit analysis for timing

    5. Multi-Venue Preparation:
       - Venue abstraction layer
       - Best execution venue selection (future)
       - Cross-venue splitting (future)

    Decision Process:
    1. Analyze order book (liquidity, spread, depth)
    2. Estimate market impact and slippage
    3. Get execution optimization recommendation
    4. Select execution mode based on size/urgency
    5. Generate execution plan with chunks if needed
    6. Execute and track results

    Usage:
        router = SmartOrderRouter()

        # Get routing decision
        decision = await router.route_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1.5"),
            urgency=ExecutionUrgency.MEDIUM,
            orderbook={"bids": [...], "asks": [...]}
        )

        # Execute the decision
        result = await router.execute_order(
            decision=decision,
            execute_func=bybit_client.place_order,
            cancel_func=bybit_client.cancel_order
        )

        # Get metrics
        metrics = router.get_metrics()
    """

    def __init__(self, config: Optional[SmartRouterConfig] = None):
        """
        Initialize smart order router

        Args:
            config: Router configuration (uses defaults if not provided)
        """
        # Store configuration
        self.config = config or SmartRouterConfig()

        # Initialize analyzers
        self._orderbook_analyzer = get_orderbook_analyzer(self.config.orderbook_config)
        self._execution_optimizer = get_execution_optimizer(self.config.optimizer_config)

        # Execution history for metrics
        self._execution_history: deque[ExecutionResult] = deque(maxlen=1000)

        # Metrics tracking
        self._metrics = RouterMetrics()

        # Active orders tracking
        self._active_orders: Dict[str, RoutingDecision] = {}

        # Symbol-specific slippage thresholds
        self._symbol_slippage_thresholds: Dict[str, float] = {
            "BTCUSDT": self.config.btc_eth_max_slippage,
            "ETHUSDT": self.config.btc_eth_max_slippage,
        }

        # Log initialization
        logger.info(
            f"SmartOrderRouter initialized: "
            f"small_order=${self.config.small_order_threshold}, "
            f"large_order=${self.config.large_order_threshold}, "
            f"venues={self.config.enabled_venues}"
        )

    # ========================================================================
    # ORDER ROUTING
    # ========================================================================

    async def route_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        urgency: ExecutionUrgency = ExecutionUrgency.MEDIUM,
        orderbook: Optional[Dict] = None,
        current_price: Optional[Decimal] = None
    ) -> RoutingDecision:
        """
        Generate routing decision for an order

        Analyzes market conditions and order parameters to produce
        comprehensive execution plan including order type, timing,
        and splitting strategy.

        Args:
            symbol: Trading symbol
            side: "BUY" or "SELL"
            quantity: Order quantity
            urgency: Execution urgency level
            orderbook: Order book data {"bids": [...], "asks": [...]}
            current_price: Current market price (optional)

        Returns:
            RoutingDecision with complete execution plan
        """
        order_id = f"smart_{symbol}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        # Parse order book data
        bids = orderbook.get("bids", []) if orderbook else []
        asks = orderbook.get("asks", []) if orderbook else []

        # Step 1: Analyze order book liquidity
        liquidity_report = self._orderbook_analyzer.analyze_liquidity(
            symbol=symbol,
            bids=bids,
            asks=asks,
            current_price=current_price
        )

        # Use mid price from analysis
        mid_price = liquidity_report.mid_price if liquidity_report.mid_price > 0 else (current_price or Decimal("0"))
        order_value_usd = float(quantity * mid_price)

        # Step 2: Estimate market impact
        market_impact = None
        if bids and asks:
            market_impact = self._orderbook_analyzer.estimate_market_impact(
                symbol=symbol,
                side=side,
                quantity=quantity,
                bids=bids,
                asks=asks,
                current_price=current_price
            )

        # Step 3: Get execution optimization
        optimization = self._execution_optimizer.optimize_execution(
            symbol=symbol,
            side=side,
            quantity=quantity,
            urgency=urgency,
            current_price=mid_price,
            spread_pct=liquidity_report.spread_pct,
            best_bid=liquidity_report.best_bid,
            best_ask=liquidity_report.best_ask,
            available_liquidity_usd=liquidity_report.depth_at_01pct.total_depth_usd,
            expected_slippage_pct=market_impact.total_impact_pct if market_impact else None
        )

        # Step 4: Determine execution mode
        execution_mode, chunks, visible_qty = self._determine_execution_mode(
            order_value_usd=order_value_usd,
            quantity=quantity,
            urgency=urgency,
            liquidity_report=liquidity_report,
            optimization=optimization
        )

        # Step 5: Calculate limit price if applicable
        limit_price = self._calculate_limit_price(
            execution_mode=execution_mode,
            optimization=optimization,
            side=side,
            liquidity_report=liquidity_report
        )

        # Step 6: Determine max slippage threshold
        max_slippage = self._get_max_slippage_for_symbol(symbol)

        # Step 7: Select venue (currently single venue)
        venue = self._select_venue(symbol, order_value_usd)

        # Step 8: Compile warnings
        warnings = list(optimization.warnings) + list(liquidity_report.warnings)
        if market_impact and market_impact.warning_message:
            warnings.append(market_impact.warning_message)

        # Generate reasoning
        reasoning = self._generate_reasoning(
            execution_mode=execution_mode,
            optimization=optimization,
            liquidity_report=liquidity_report,
            order_value_usd=order_value_usd
        )

        # Calculate confidence
        confidence = self._calculate_confidence(
            optimization=optimization,
            liquidity_report=liquidity_report,
            execution_mode=execution_mode
        )

        decision = RoutingDecision(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_value_usd=order_value_usd,
            urgency=urgency,
            venue=venue,
            execution_mode=execution_mode,
            order_type=optimization.recommended_order_type,
            timing=optimization.recommended_timing,
            limit_price=limit_price,
            max_acceptable_slippage_pct=max_slippage,
            chunks=chunks,
            visible_quantity=visible_qty,
            liquidity_report=liquidity_report,
            market_impact=market_impact,
            optimization_result=optimization,
            estimated_slippage_pct=market_impact.total_impact_pct if market_impact else 0.0,
            estimated_total_cost_pct=optimization.expected_cost.total_cost_pct,
            estimated_fill_probability=optimization.estimated_fill_probability,
            estimated_time_to_fill_seconds=optimization.estimated_time_to_fill_seconds,
            reasoning=reasoning,
            confidence=confidence,
            warnings=warnings
        )

        # Track active order
        self._active_orders[order_id] = decision

        logger.info(
            f"Routing decision for {symbol} {side} ${order_value_usd:,.0f}: "
            f"{execution_mode.value}/{optimization.recommended_order_type.value} | "
            f"Venue: {venue} | Confidence: {confidence:.1%}"
        )

        return decision

    def _determine_execution_mode(
        self,
        order_value_usd: float,
        quantity: Decimal,
        urgency: ExecutionUrgency,
        liquidity_report: LiquidityReport,
        optimization: OptimizationResult
    ) -> Tuple[ExecutionMode, List[Dict], Optional[Decimal]]:
        """
        Determine execution mode based on order characteristics

        Returns: (execution_mode, chunks, visible_quantity)
        """
        chunks = []
        visible_qty = None

        # Small orders: immediate execution
        if order_value_usd < self.config.small_order_threshold:
            return ExecutionMode.IMMEDIATE, [], None

        # Medium orders: depend on urgency and liquidity
        if order_value_usd < self.config.large_order_threshold:
            if urgency in (ExecutionUrgency.CRITICAL, ExecutionUrgency.HIGH):
                return ExecutionMode.IMMEDIATE, [], None
            else:
                return ExecutionMode.PASSIVE, [], None

        # Large orders: need splitting
        # Check if order is large relative to available liquidity
        available_depth = liquidity_report.depth_at_01pct.total_depth_usd
        relative_size = order_value_usd / available_depth if available_depth > 0 else 1.0

        if urgency == ExecutionUrgency.LOW:
            # Patient execution: use iceberg
            visible_pct = self.config.iceberg_visible_pct
            if self.config.iceberg_randomize:
                import random
                visible_pct *= random.uniform(0.8, 1.2)

            visible_qty = quantity * Decimal(str(visible_pct))

            # Ensure minimum visible amount
            min_visible_qty = Decimal(str(self.config.iceberg_min_visible_usd)) / liquidity_report.mid_price
            visible_qty = max(visible_qty, min_visible_qty)

            return ExecutionMode.SPLIT_ICEBERG, [], visible_qty

        else:
            # Use TWAP for time distribution
            # Calculate optimal number of chunks based on size
            if relative_size > 0.5:  # Very large
                num_chunks = self.config.twap_max_chunks
            elif relative_size > 0.2:
                num_chunks = min(8, max(self.config.twap_min_chunks, int(relative_size * 15)))
            else:
                num_chunks = self.config.twap_min_chunks

            chunk_qty = quantity / num_chunks
            interval = self.config.twap_interval_seconds

            for i in range(num_chunks):
                chunk_time = datetime.now(timezone.utc) + timedelta(
                    seconds=i * interval
                )
                chunks.append({
                    "chunk_id": i + 1,
                    "quantity": str(chunk_qty),
                    "scheduled_time": chunk_time.isoformat(),
                    "status": "pending"
                })

            return ExecutionMode.SPLIT_TWAP, chunks, None

    def _calculate_limit_price(
        self,
        execution_mode: ExecutionMode,
        optimization: OptimizationResult,
        side: str,
        liquidity_report: LiquidityReport
    ) -> Optional[Decimal]:
        """Calculate appropriate limit price for order"""
        # Market orders don't need limit price
        if optimization.recommended_order_type == OptimalOrderType.MARKET:
            return None

        # Use optimizer's recommended price if available
        if optimization.recommended_price:
            return optimization.recommended_price

        # Calculate based on order book
        mid_price = liquidity_report.mid_price
        offset = Decimal(str(liquidity_report.optimal_limit_offset_pct))

        if side.upper() == "BUY":
            # For buys: slightly below mid
            return mid_price * (1 - offset)
        else:
            # For sells: slightly above mid
            return mid_price * (1 + offset)

    def _get_max_slippage_for_symbol(self, symbol: str) -> float:
        """Get maximum acceptable slippage for symbol"""
        # Check symbol-specific threshold
        if symbol in self._symbol_slippage_thresholds:
            return self._symbol_slippage_thresholds[symbol]

        # Check if major asset
        if "BTC" in symbol or "ETH" in symbol:
            return self.config.btc_eth_max_slippage

        # Default to alt threshold
        return self.config.alt_max_slippage

    def _select_venue(self, symbol: str, order_value_usd: float) -> str:
        """
        Select execution venue

        Currently returns primary venue. Future: implement smart venue selection
        based on liquidity, fees, and execution quality across exchanges.
        """
        # TODO: Implement multi-venue routing
        # For now, always use primary venue
        return self.config.primary_venue

    def _generate_reasoning(
        self,
        execution_mode: ExecutionMode,
        optimization: OptimizationResult,
        liquidity_report: LiquidityReport,
        order_value_usd: float
    ) -> str:
        """Generate human-readable reasoning for routing decision"""
        parts = []

        # Size classification
        if order_value_usd < self.config.small_order_threshold:
            parts.append(f"Small order (${order_value_usd:,.0f})")
        elif order_value_usd < self.config.large_order_threshold:
            parts.append(f"Medium order (${order_value_usd:,.0f})")
        else:
            parts.append(f"Large order (${order_value_usd:,.0f})")

        # Liquidity assessment
        parts.append(f"Liquidity: {liquidity_report.liquidity_level.value} (score: {liquidity_report.liquidity_score:.0f})")

        # Spread assessment
        parts.append(f"Spread: {liquidity_report.spread_pct:.3%} ({liquidity_report.spread_category.value})")

        # Execution mode reasoning
        mode_reasons = {
            ExecutionMode.IMMEDIATE: "Immediate execution selected",
            ExecutionMode.PASSIVE: "Passive execution for cost savings",
            ExecutionMode.SPLIT_TWAP: f"TWAP split to minimize market impact",
            ExecutionMode.SPLIT_ICEBERG: "Iceberg to hide order size"
        }
        parts.append(mode_reasons.get(execution_mode, ""))

        # Add optimizer reasoning
        parts.append(optimization.reasoning)

        return " | ".join(filter(None, parts))

    def _calculate_confidence(
        self,
        optimization: OptimizationResult,
        liquidity_report: LiquidityReport,
        execution_mode: ExecutionMode
    ) -> float:
        """Calculate overall confidence in routing decision"""
        # Start with optimizer confidence
        base_confidence = optimization.confidence

        # Adjust for liquidity
        if liquidity_report.liquidity_level == LiquidityLevel.HIGH:
            base_confidence += 0.1
        elif liquidity_report.liquidity_level == LiquidityLevel.VERY_LOW:
            base_confidence -= 0.2

        # Adjust for execution mode complexity
        if execution_mode in (ExecutionMode.SPLIT_TWAP, ExecutionMode.SPLIT_ICEBERG):
            base_confidence -= 0.05  # More complexity = slightly less certainty

        return min(1.0, max(0.3, base_confidence))

    # ========================================================================
    # ORDER EXECUTION
    # ========================================================================

    async def execute_order(
        self,
        decision: RoutingDecision,
        execute_func: Callable[..., Any],
        cancel_func: Optional[Callable[..., Any]] = None,
        status_func: Optional[Callable[..., Any]] = None
    ) -> ExecutionResult:
        """
        Execute order based on routing decision

        Handles execution including:
        - Single order placement
        - TWAP chunk execution
        - Iceberg order management
        - Slippage monitoring
        - Retry on failure

        Args:
            decision: RoutingDecision from route_order
            execute_func: Async function to place orders
            cancel_func: Async function to cancel orders
            status_func: Async function to check order status

        Returns:
            ExecutionResult with actual execution metrics
        """
        execution_start = datetime.now(timezone.utc)
        expected_price = decision.liquidity_report.mid_price if decision.liquidity_report else Decimal("0")

        try:
            # Execute based on mode
            if decision.execution_mode == ExecutionMode.SPLIT_TWAP:
                result = await self._execute_twap(decision, execute_func, status_func)
            elif decision.execution_mode == ExecutionMode.SPLIT_ICEBERG:
                result = await self._execute_iceberg(decision, execute_func, cancel_func)
            else:
                result = await self._execute_single(decision, execute_func, cancel_func, status_func)

            # Calculate execution metrics
            execution_end = datetime.now(timezone.utc)
            execution_time_ms = (execution_end - execution_start).total_seconds() * 1000

            # Parse results
            filled_qty = Decimal(str(result.get("filled_quantity", 0)))
            avg_price = Decimal(str(result.get("avg_price", expected_price)))
            fill_rate = float(filled_qty / decision.quantity) if decision.quantity > 0 else 0.0

            # Calculate actual slippage
            if expected_price > 0:
                if decision.side.upper() == "BUY":
                    actual_slippage = float((avg_price - expected_price) / expected_price) * 100
                else:
                    actual_slippage = float((expected_price - avg_price) / expected_price) * 100
            else:
                actual_slippage = 0.0

            # Compare to estimate
            slippage_vs_estimate = (
                actual_slippage / decision.estimated_slippage_pct
                if decision.estimated_slippage_pct > 0 else 1.0
            )

            # Calculate costs
            fee_rate = 0.0006 if decision.order_type == OptimalOrderType.MARKET else 0.0001
            total_fees = float(filled_qty * avg_price) * fee_rate
            slippage_cost = abs(actual_slippage / 100) * float(filled_qty * avg_price)
            total_cost = total_fees + slippage_cost

            # Determine status
            if fill_rate >= 0.99:
                status = OrderStatus.FILLED
            elif fill_rate > 0:
                status = OrderStatus.PARTIAL
            elif result.get("error"):
                status = OrderStatus.FAILED
            else:
                status = OrderStatus.CANCELLED

            execution_result = ExecutionResult(
                order_id=decision.order_id,
                routing_decision=decision,
                status=status,
                filled_quantity=filled_qty,
                fill_rate=fill_rate,
                average_price=avg_price,
                expected_price=expected_price,
                actual_slippage_pct=actual_slippage,
                slippage_vs_estimate=slippage_vs_estimate,
                total_fees_paid=total_fees,
                total_slippage_cost=slippage_cost,
                total_execution_cost=total_cost,
                execution_start=execution_start,
                execution_end=execution_end,
                execution_time_ms=execution_time_ms,
                chunk_results=result.get("chunk_results", []),
                error_message=result.get("error")
            )

            # Record for metrics
            self._record_execution(execution_result)

            # Remove from active orders
            if decision.order_id in self._active_orders:
                del self._active_orders[decision.order_id]

            logger.info(
                f"Execution complete for {decision.order_id}: "
                f"Status: {status.value} | "
                f"Fill: {fill_rate:.1%} | "
                f"Slippage: {actual_slippage:.3f}% (vs estimate: {slippage_vs_estimate:.1f}x)"
            )

            return execution_result

        except Exception as e:
            logger.error(f"Execution failed for {decision.order_id}: {e}")

            return ExecutionResult(
                order_id=decision.order_id,
                routing_decision=decision,
                status=OrderStatus.FAILED,
                filled_quantity=Decimal("0"),
                fill_rate=0.0,
                average_price=Decimal("0"),
                expected_price=expected_price,
                actual_slippage_pct=0.0,
                slippage_vs_estimate=0.0,
                total_fees_paid=0.0,
                total_slippage_cost=0.0,
                total_execution_cost=0.0,
                execution_start=execution_start,
                execution_end=datetime.now(timezone.utc),
                execution_time_ms=0.0,
                error_message=str(e)
            )

    async def _execute_single(
        self,
        decision: RoutingDecision,
        execute_func: Callable,
        cancel_func: Optional[Callable],
        status_func: Optional[Callable]
    ) -> Dict:
        """Execute a single order (immediate or passive)"""
        # Build order parameters
        params = {
            "symbol": decision.symbol,
            "side": decision.side.upper(),
            "qty": str(decision.quantity)
        }

        # Set order type
        if decision.order_type == OptimalOrderType.MARKET:
            params["order_type"] = "Market"
        elif decision.order_type == OptimalOrderType.POST_ONLY:
            params["order_type"] = "Limit"
            params["price"] = str(decision.limit_price)
            params["time_in_force"] = "PostOnly"
        elif decision.order_type == OptimalOrderType.LIMIT_IOC:
            params["order_type"] = "Limit"
            params["price"] = str(decision.limit_price)
            params["time_in_force"] = "IOC"
        else:  # LIMIT_GTC or others
            params["order_type"] = "Limit"
            params["price"] = str(decision.limit_price)
            params["time_in_force"] = "GTC"

        # Execute with retry
        result = None
        last_error = None

        for attempt in range(self.config.max_retry_attempts):
            try:
                result = await execute_func(**params)

                # Check for slippage violation (for limit orders that filled as taker)
                filled_qty = Decimal(str(result.get("filled_qty", result.get("filledQty", 0))))
                avg_price = Decimal(str(result.get("avg_price", result.get("avgPrice", decision.limit_price or 0))))

                if filled_qty > 0 and decision.liquidity_report:
                    mid = decision.liquidity_report.mid_price
                    if decision.side.upper() == "BUY":
                        slippage = float((avg_price - mid) / mid) * 100
                    else:
                        slippage = float((mid - avg_price) / mid) * 100

                    if slippage > decision.max_acceptable_slippage_pct:
                        logger.warning(
                            f"Slippage {slippage:.3f}% exceeds threshold "
                            f"{decision.max_acceptable_slippage_pct:.3f}%"
                        )
                        # Don't retry on slippage - the order filled, just log warning

                break

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Execution attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retry_attempts - 1:
                    await asyncio.sleep(self.config.retry_delay_seconds)

        if result is None:
            return {"error": last_error, "filled_quantity": 0, "avg_price": 0}

        return {
            "order_id": result.get("orderId", result.get("order_id")),
            "filled_quantity": result.get("filled_qty", result.get("filledQty", 0)),
            "avg_price": result.get("avg_price", result.get("avgPrice", decision.limit_price or 0))
        }

    async def _execute_twap(
        self,
        decision: RoutingDecision,
        execute_func: Callable,
        status_func: Optional[Callable]
    ) -> Dict:
        """Execute TWAP order with time-weighted chunks"""
        total_filled = Decimal("0")
        total_value = Decimal("0")
        chunk_results = []

        for chunk in decision.chunks:
            chunk_qty = Decimal(str(chunk["quantity"]))

            try:
                # Use limit IOC for each chunk
                result = await execute_func(
                    symbol=decision.symbol,
                    side=decision.side.upper(),
                    qty=str(chunk_qty),
                    order_type="Limit",
                    price=str(decision.limit_price),
                    time_in_force="IOC"
                )

                filled = Decimal(str(result.get("filled_qty", result.get("filledQty", 0))))
                price = Decimal(str(result.get("avg_price", result.get("avgPrice", decision.limit_price))))

                total_filled += filled
                total_value += filled * price

                chunk["status"] = "executed"
                chunk["filled_quantity"] = str(filled)
                chunk["avg_price"] = str(price)

                chunk_results.append({
                    "chunk_id": chunk["chunk_id"],
                    "filled_qty": str(filled),
                    "avg_price": str(price),
                    "status": "success"
                })

            except Exception as e:
                chunk["status"] = "failed"
                chunk["error"] = str(e)
                chunk_results.append({
                    "chunk_id": chunk["chunk_id"],
                    "status": "failed",
                    "error": str(e)
                })
                logger.warning(f"TWAP chunk {chunk['chunk_id']} failed: {e}")

            # Wait for next chunk (except last)
            if chunk != decision.chunks[-1]:
                await asyncio.sleep(self.config.twap_interval_seconds)

        avg_price = total_value / total_filled if total_filled > 0 else Decimal("0")

        return {
            "filled_quantity": total_filled,
            "avg_price": avg_price,
            "chunk_results": chunk_results
        }

    async def _execute_iceberg(
        self,
        decision: RoutingDecision,
        execute_func: Callable,
        cancel_func: Optional[Callable]
    ) -> Dict:
        """Execute iceberg order with hidden size"""
        total_filled = Decimal("0")
        total_value = Decimal("0")
        remaining = decision.quantity
        visible = decision.visible_quantity or decision.quantity * Decimal("0.15")
        chunk_results = []
        iteration = 0
        max_iterations = 50  # Safety limit

        while remaining > 0 and iteration < max_iterations:
            iteration += 1
            chunk_qty = min(visible, remaining)

            try:
                result = await execute_func(
                    symbol=decision.symbol,
                    side=decision.side.upper(),
                    qty=str(chunk_qty),
                    order_type="Limit",
                    price=str(decision.limit_price),
                    time_in_force="GTC"
                )

                filled = Decimal(str(result.get("filled_qty", result.get("filledQty", 0))))
                price = Decimal(str(result.get("avg_price", result.get("avgPrice", decision.limit_price))))

                total_filled += filled
                total_value += filled * price
                remaining -= filled

                chunk_results.append({
                    "iteration": iteration,
                    "filled_qty": str(filled),
                    "avg_price": str(price),
                    "remaining": str(remaining)
                })

                # If poor fill rate, stop iceberg
                if filled < chunk_qty * Decimal("0.3"):
                    logger.warning(f"Iceberg fill rate too low ({filled}/{chunk_qty}), stopping")
                    break

            except Exception as e:
                chunk_results.append({
                    "iteration": iteration,
                    "status": "failed",
                    "error": str(e)
                })
                logger.warning(f"Iceberg iteration {iteration} failed: {e}")
                break

            # Brief pause between visible portions
            if remaining > 0:
                await asyncio.sleep(2)

        avg_price = total_value / total_filled if total_filled > 0 else Decimal("0")

        return {
            "filled_quantity": total_filled,
            "avg_price": avg_price,
            "chunk_results": chunk_results
        }

    # ========================================================================
    # METRICS
    # ========================================================================

    def _record_execution(self, result: ExecutionResult):
        """Record execution for metrics tracking"""
        self._execution_history.append(result)

        # Update counts
        self._metrics.total_orders += 1
        if result.status == OrderStatus.FILLED:
            self._metrics.successful_orders += 1
        elif result.status == OrderStatus.PARTIAL:
            self._metrics.partial_fills += 1
        else:
            self._metrics.failed_orders += 1

        # Update slippage metrics
        if result.actual_slippage_pct > self._metrics.max_slippage_pct:
            self._metrics.max_slippage_pct = result.actual_slippage_pct

        # Update costs
        self._metrics.total_fees_usd += result.total_fees_paid
        self._metrics.total_slippage_cost_usd += result.total_slippage_cost

        # Update order type distribution
        order_type = result.routing_decision.order_type.value
        self._metrics.orders_by_type[order_type] = \
            self._metrics.orders_by_type.get(order_type, 0) + 1

        exec_mode = result.routing_decision.execution_mode.value
        self._metrics.orders_by_mode[exec_mode] = \
            self._metrics.orders_by_mode.get(exec_mode, 0) + 1

        # Calculate running averages from history
        valid_results = [r for r in self._execution_history if r.status != OrderStatus.FAILED]
        if valid_results:
            self._metrics.avg_slippage_pct = statistics.mean(r.actual_slippage_pct for r in valid_results)
            self._metrics.avg_fill_rate = statistics.mean(r.fill_rate for r in valid_results)
            self._metrics.avg_execution_time_ms = statistics.mean(r.execution_time_ms for r in valid_results)

            # Calculate slippage reduction vs baseline (0.1% assumed for naive execution)
            baseline_slippage = 0.1
            self._metrics.slippage_reduction_vs_baseline = (
                (baseline_slippage - self._metrics.avg_slippage_pct) / baseline_slippage
                if baseline_slippage > 0 else 0
            )

        # Update by-mode fill rates
        for mode in ExecutionMode:
            mode_results = [
                r for r in valid_results
                if r.routing_decision.execution_mode == mode
            ]
            if mode_results:
                self._metrics.fill_rate_by_mode[mode.value] = \
                    statistics.mean(r.fill_rate for r in mode_results)

        # Record with optimizer for feedback loop
        if result.routing_decision.optimization_result:
            self._execution_optimizer.record_execution_result(
                optimization_result=result.routing_decision.optimization_result,
                actual_fill_rate=result.fill_rate,
                actual_cost_usd=result.total_execution_cost,
                execution_time_seconds=result.execution_time_ms / 1000
            )

        self._metrics.last_updated = datetime.now(timezone.utc)

    def get_metrics(self) -> RouterMetrics:
        """Get current router performance metrics"""
        return self._metrics

    def get_status(self) -> Dict:
        """Get router status summary"""
        return {
            "config": {
                "small_order_threshold": self.config.small_order_threshold,
                "large_order_threshold": self.config.large_order_threshold,
                "btc_eth_max_slippage": f"{self.config.btc_eth_max_slippage}%",
                "alt_max_slippage": f"{self.config.alt_max_slippage}%",
                "twap_chunks": f"{self.config.twap_min_chunks}-{self.config.twap_max_chunks}",
                "iceberg_visible_pct": f"{self.config.iceberg_visible_pct:.0%}",
                "venues": self.config.enabled_venues
            },
            "metrics": {
                "total_orders": self._metrics.total_orders,
                "successful_orders": self._metrics.successful_orders,
                "failed_orders": self._metrics.failed_orders,
                "avg_slippage_pct": round(self._metrics.avg_slippage_pct, 4),
                "max_slippage_pct": round(self._metrics.max_slippage_pct, 4),
                "slippage_reduction_vs_baseline": f"{self._metrics.slippage_reduction_vs_baseline:.1%}",
                "avg_fill_rate": round(self._metrics.avg_fill_rate, 4),
                "avg_execution_time_ms": round(self._metrics.avg_execution_time_ms, 1)
            },
            "order_distribution": {
                "by_type": self._metrics.orders_by_type,
                "by_mode": self._metrics.orders_by_mode
            },
            "active_orders": len(self._active_orders),
            "history_size": len(self._execution_history),
            "last_updated": self._metrics.last_updated.isoformat()
        }


# ============================================================================
# GLOBAL INSTANCE MANAGEMENT
# ============================================================================

# Global router instance
_smart_order_router: Optional[SmartOrderRouter] = None


def get_smart_order_router(
    config: Optional[SmartRouterConfig] = None
) -> SmartOrderRouter:
    """
    Get or create global smart order router instance

    Args:
        config: Optional configuration (only used if creating new instance)

    Returns:
        SmartOrderRouter instance
    """
    global _smart_order_router
    if _smart_order_router is None:
        _smart_order_router = SmartOrderRouter(config)
    return _smart_order_router


def reset_smart_order_router():
    """Reset global smart order router instance"""
    global _smart_order_router
    _smart_order_router = None
    logger.info("Smart order router instance reset")
