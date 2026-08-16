"""
Smart Order Router - Intelligent Order Type Selection and Execution Optimization
Phase 4.1: Smart Order Routing for Improved Execution

Purpose:
- Automatically select optimal order type based on market conditions
- Minimize slippage through intelligent routing decisions
- Improve fill rates by adapting to order book liquidity
- Implement order splitting strategies for large orders
- Track and report execution quality metrics

Research Sources:
- Almgren-Chriss Optimal Execution Model
- Market Microstructure Theory
- Crypto Market Liquidity Analysis
- Post-Only Order Economics

Order Type Selection Matrix:
- MARKET orders: When spread < 0.05% AND urgency = HIGH
- LIMIT orders: When spread > 0.05% AND urgency = MEDIUM
- ICEBERG orders: When size > 1% of order book depth
- POST_ONLY: For stat arb (no urgency, capture maker fees)

Execution Strategy Selection:
- Small orders (<$1000): Single market order
- Medium orders ($1000-$5000): Limit order at mid-price
- Large orders (>$5000): Split into 3-5 chunks (TWAP)

Created: 2025-12-11
Author: Backend Developer Agent
"""

import asyncio
import logging
import time
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Any, Callable
from collections import deque
import statistics

# Configure logging for smart order routing
logger = logging.getLogger(__name__)


# ============================================================================
# ENUMERATIONS
# ============================================================================

class ExecutionUrgency(str, Enum):
    """
    Execution urgency levels affecting order type selection

    LOW: Patient execution, prioritize cost savings (maker fees)
    MEDIUM: Balanced approach between speed and cost
    HIGH: Speed is critical, accept higher costs
    CRITICAL: Immediate execution required, ignore cost
    """
    LOW = "low"           # Patient, minimize impact (for stat arb)
    MEDIUM = "medium"     # Balanced approach
    HIGH = "high"         # Speed over cost
    CRITICAL = "critical" # Immediate execution (stop loss, liquidation)


class ExecutionStrategyType(str, Enum):
    """
    Execution strategy types for order placement

    SINGLE: One order (market or limit)
    SPLIT_TWAP: Time-weighted average price (split into chunks over time)
    SPLIT_ICEBERG: Hide order size (show only portion)
    POST_ONLY: Maker-only orders (capture maker rebates)
    """
    SINGLE = "single"           # Single order execution
    SPLIT_TWAP = "split_twap"   # Time-weighted split execution
    SPLIT_ICEBERG = "iceberg"   # Hidden order with visible portion
    POST_ONLY = "post_only"     # Maker-only order for fee capture


class OrderTypeSelection(str, Enum):
    """
    Recommended order type from router analysis

    MARKET: Execute immediately at market price
    LIMIT: Place limit order at specified price
    LIMIT_IOC: Limit with Immediate-or-Cancel
    POST_ONLY: Maker-only, reject if would take
    """
    MARKET = "market"
    LIMIT = "limit"
    LIMIT_IOC = "limit_ioc"    # Immediate or cancel
    POST_ONLY = "post_only"


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class SmartRouterConfig:
    """
    Configuration for smart order routing decisions

    Threshold values calibrated for typical crypto market conditions:
    - tight_spread_threshold: Spread below which market orders are preferred
    - wide_spread_threshold: Spread above which limit orders are strongly preferred
    - large_order_threshold: Order size (as % of book depth) triggering iceberg
    - twap_time_minutes: Duration for TWAP execution
    """
    # Spread thresholds (as decimal, e.g., 0.0005 = 0.05%)
    tight_spread_threshold: float = 0.0005      # 0.05% - Use market orders below
    wide_spread_threshold: float = 0.002        # 0.2% - Strong preference for limit

    # Order size thresholds (in USD)
    small_order_threshold: float = 1000.0       # Single market order
    medium_order_threshold: float = 5000.0      # Limit at mid-price
    large_order_threshold_pct: float = 0.01     # 1% of book depth -> iceberg

    # TWAP execution settings
    twap_min_chunks: int = 3                    # Minimum splits for large orders
    twap_max_chunks: int = 5                    # Maximum splits
    twap_time_minutes: int = 10                 # Default TWAP duration
    twap_chunk_interval_seconds: int = 120      # Seconds between chunks

    # Limit order settings
    limit_offset_bps: float = 5.0               # Basis points offset from mid
    limit_timeout_seconds: int = 30             # Time to wait for fill
    limit_fallback_to_market: bool = True       # Fall back to market if unfilled

    # Iceberg settings
    iceberg_visible_pct: float = 0.15           # Show 15% of order
    iceberg_randomize: bool = True              # Randomize visible size

    # Post-only settings
    post_only_enabled: bool = True              # Enable maker-only orders
    post_only_max_urgency: ExecutionUrgency = ExecutionUrgency.LOW

    # Slippage settings
    max_acceptable_slippage_pct: float = 0.30   # 0.3% max slippage
    slippage_warning_threshold: float = 0.15   # 0.15% warn level

    # Thin liquidity detection
    thin_liquidity_depth_usd: float = 10000.0  # Min depth to consider liquid


@dataclass
class OrderBookLevel:
    """
    Single price level in order book

    Attributes:
        price: Price at this level
        quantity: Total quantity available
        order_count: Number of orders (if available)
    """
    price: Decimal
    quantity: Decimal
    order_count: int = 1


@dataclass
class OrderBookAnalysis:
    """
    Analysis results from order book examination

    Provides comprehensive liquidity metrics:
    - spread_pct: Current bid-ask spread
    - mid_price: Midpoint between best bid/ask
    - depth_bids_usd/depth_asks_usd: Total liquidity in USD
    - imbalance_ratio: Buy vs sell pressure indicator
    - is_thin_liquidity: Warning flag for low liquidity
    """
    symbol: str
    timestamp: datetime

    # Price levels
    best_bid: Decimal
    best_ask: Decimal
    mid_price: Decimal

    # Spread analysis
    spread_absolute: Decimal
    spread_pct: float              # As decimal (0.0005 = 0.05%)

    # Depth analysis (in USD)
    depth_bids_usd: float          # Total bid liquidity
    depth_asks_usd: float          # Total ask liquidity
    depth_total_usd: float         # Combined depth

    # Multi-level depth (at 0.1%, 0.5%, 1% from mid)
    depth_at_01pct: float          # Depth within 0.1% of mid
    depth_at_05pct: float          # Depth within 0.5% of mid
    depth_at_1pct: float           # Depth within 1% of mid

    # Order book shape
    imbalance_ratio: float         # bid_depth / ask_depth (>1 = buy pressure)

    # Liquidity flags
    is_thin_liquidity: bool = False
    thin_liquidity_warning: Optional[str] = None


@dataclass
class SlippageEstimate:
    """
    Estimated slippage for a potential order

    Provides slippage prediction based on order book analysis:
    - expected_slippage_pct: Most likely slippage
    - worst_case_slippage_pct: Conservative estimate
    - levels_consumed: Number of price levels order would consume
    - execution_price: Expected average fill price
    """
    symbol: str
    side: str                      # "BUY" or "SELL"
    quantity: Decimal
    order_value_usd: float

    # Slippage estimates (as percentage)
    expected_slippage_pct: float   # Expected based on book
    worst_case_slippage_pct: float # Conservative estimate
    best_case_slippage_pct: float  # Optimistic estimate

    # Execution details
    mid_price: Decimal
    execution_price: Decimal       # Expected fill price
    levels_consumed: int           # Price levels required

    # Cost analysis
    slippage_cost_usd: float       # Dollar cost of slippage

    # Risk assessment
    is_acceptable: bool            # Within acceptable threshold
    warning_message: Optional[str] = None

    # Timestamp
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class OrderTypeRecommendation:
    """
    Smart router's recommendation for order execution

    Contains complete execution plan including:
    - order_type: Recommended order type (MARKET/LIMIT/POST_ONLY)
    - strategy: Execution strategy (SINGLE/SPLIT_TWAP/etc.)
    - chunks: For split orders, the individual chunk details
    - reasoning: Human-readable explanation of decision
    """
    symbol: str
    side: str
    quantity: Decimal
    order_value_usd: float
    urgency: ExecutionUrgency

    # Recommendation
    order_type: OrderTypeSelection
    strategy: ExecutionStrategyType

    # Execution details
    limit_price: Optional[Decimal] = None   # For limit orders
    visible_quantity: Optional[Decimal] = None  # For iceberg
    chunks: List[Dict] = field(default_factory=list)  # For TWAP

    # Analysis used for decision
    orderbook_analysis: Optional[OrderBookAnalysis] = None
    slippage_estimate: Optional[SlippageEstimate] = None

    # Reasoning
    reasoning: str = ""
    confidence: float = 0.0        # 0-1 confidence in recommendation

    # Timestamp
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ExecutionRecord:
    """
    Record of an executed order for metrics tracking

    Stores actual execution results for quality analysis:
    - expected_price vs actual_price for slippage calculation
    - fill_rate for partial fill tracking
    - execution_time_ms for latency monitoring
    """
    order_id: str
    symbol: str
    side: str
    quantity: Decimal
    order_type: OrderTypeSelection
    strategy: ExecutionStrategyType

    # Prices
    expected_price: Decimal
    actual_price: Decimal
    limit_price: Optional[Decimal] = None

    # Execution results
    filled_quantity: Decimal = Decimal("0")
    fill_rate: float = 0.0         # 0-1

    # Slippage
    slippage_pct: float = 0.0
    slippage_usd: float = 0.0
    slippage_vs_estimate: float = 0.0  # Actual vs predicted

    # Timing
    order_sent_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    order_filled_at: Optional[datetime] = None
    execution_time_ms: float = 0.0

    # Status
    is_complete: bool = False
    error_message: Optional[str] = None


@dataclass
class RouterMetrics:
    """
    Aggregated metrics for router performance

    Tracks overall router effectiveness:
    - avg_slippage_pct: Average slippage across all orders
    - fill_rate: Percentage of orders successfully filled
    - slippage_vs_estimate: Accuracy of slippage predictions
    """
    total_orders: int = 0
    successful_orders: int = 0
    failed_orders: int = 0

    # Slippage metrics
    total_slippage_usd: float = 0.0
    avg_slippage_pct: float = 0.0
    max_slippage_pct: float = 0.0
    slippage_vs_estimate: float = 0.0  # Actual / Estimated

    # Fill metrics
    avg_fill_rate: float = 0.0
    partial_fills: int = 0

    # Order type distribution
    market_orders: int = 0
    limit_orders: int = 0
    post_only_orders: int = 0
    iceberg_orders: int = 0
    twap_orders: int = 0

    # Strategy effectiveness
    limit_order_fill_rate: float = 0.0
    market_order_avg_slippage: float = 0.0

    # Timing
    avg_execution_time_ms: float = 0.0

    # Last update
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ExecutionQualityReport:
    """
    Comprehensive execution quality report

    Detailed analysis of router performance over time window:
    - slippage_savings_usd: Estimated savings vs naive market orders
    - strategy_breakdown: Performance by execution strategy
    - recommendations: Suggestions for improvement
    """
    report_period_start: datetime
    report_period_end: datetime

    # Overall metrics
    metrics: RouterMetrics

    # Performance indicators
    slippage_reduction_pct: float  # vs baseline market orders
    slippage_savings_usd: float    # Estimated cost savings
    fill_rate_improvement: float   # vs baseline

    # Strategy breakdown
    strategy_breakdown: Dict[str, Dict] = field(default_factory=dict)

    # Order type effectiveness
    order_type_breakdown: Dict[str, Dict] = field(default_factory=dict)

    # Liquidity conditions
    avg_spread_during_period: float = 0.0
    thin_liquidity_percentage: float = 0.0

    # Recommendations
    recommendations: List[str] = field(default_factory=list)


# ============================================================================
# SMART ORDER ROUTER
# ============================================================================

class SmartOrderRouter:
    """
    Smart Order Routing Engine

    Intelligently selects order types and execution strategies to minimize
    slippage and improve fill rates based on:
    - Real-time order book analysis
    - Market spread conditions
    - Order size relative to liquidity
    - Execution urgency requirements

    Decision Matrix:
    +-----------------+---------------+-----------------+------------------+
    | Order Size      | Spread        | Urgency         | Recommendation   |
    +-----------------+---------------+-----------------+------------------+
    | <$1000          | <0.05%        | HIGH/CRITICAL   | MARKET           |
    | <$1000          | <0.05%        | MEDIUM/LOW      | LIMIT            |
    | <$1000          | >0.05%        | Any             | LIMIT            |
    | $1000-$5000     | <0.05%        | HIGH/CRITICAL   | MARKET           |
    | $1000-$5000     | >0.05%        | Any             | LIMIT at mid     |
    | >$5000          | Any           | LOW             | ICEBERG          |
    | >$5000          | Any           | MEDIUM/HIGH     | TWAP (3-5 split) |
    | Any             | Any           | LOW (stat arb)  | POST_ONLY        |
    +-----------------+---------------+-----------------+------------------+

    Usage:
        router = SmartOrderRouter()

        # Get order recommendation
        recommendation = router.get_order_recommendation(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.1"),
            urgency=ExecutionUrgency.MEDIUM,
            orderbook_depth=orderbook_data
        )

        # Execute the recommendation
        result = await router.execute_recommendation(
            recommendation=recommendation,
            execute_func=bybit_client.place_order
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

        # Execution history for metrics
        self._execution_history: deque[ExecutionRecord] = deque(maxlen=1000)

        # Order book cache (symbol -> analysis)
        self._orderbook_cache: Dict[str, OrderBookAnalysis] = {}
        self._cache_ttl_seconds: int = 5  # Order book cache TTL

        # Metrics tracking
        self._metrics = RouterMetrics()

        # Log initialization
        logger.info(
            f"SmartOrderRouter initialized: "
            f"tight_spread={self.config.tight_spread_threshold:.4%}, "
            f"small_order=${self.config.small_order_threshold}, "
            f"twap_chunks={self.config.twap_min_chunks}-{self.config.twap_max_chunks}"
        )

    # ========================================================================
    # ORDER BOOK ANALYSIS
    # ========================================================================

    def analyze_orderbook(
        self,
        symbol: str,
        bids: List[List[str]],  # [[price, qty], ...]
        asks: List[List[str]],
        current_price: Optional[Decimal] = None
    ) -> OrderBookAnalysis:
        """
        Analyze order book to extract liquidity metrics

        Examines the order book structure to understand:
        - Current spread and mid-price
        - Available liquidity at various price levels
        - Order imbalance indicating buy/sell pressure
        - Thin liquidity conditions

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            bids: List of bid levels [[price, qty], ...]
            asks: List of ask levels [[price, qty], ...]
            current_price: Optional current market price

        Returns:
            OrderBookAnalysis with comprehensive liquidity metrics
        """
        timestamp = datetime.now(timezone.utc)

        # Handle empty order books
        if not bids or not asks:
            logger.warning(f"Empty order book for {symbol}")
            # Return analysis with default values indicating thin liquidity
            mid_price = current_price or Decimal("0")
            return OrderBookAnalysis(
                symbol=symbol,
                timestamp=timestamp,
                best_bid=mid_price,
                best_ask=mid_price,
                mid_price=mid_price,
                spread_absolute=Decimal("0"),
                spread_pct=0.0,
                depth_bids_usd=0.0,
                depth_asks_usd=0.0,
                depth_total_usd=0.0,
                depth_at_01pct=0.0,
                depth_at_05pct=0.0,
                depth_at_1pct=0.0,
                imbalance_ratio=1.0,
                is_thin_liquidity=True,
                thin_liquidity_warning="Order book is empty"
            )

        # Parse best bid and ask
        best_bid = Decimal(str(bids[0][0]))
        best_ask = Decimal(str(asks[0][0]))

        # Calculate mid price and spread
        mid_price = (best_bid + best_ask) / 2
        spread_absolute = best_ask - best_bid
        spread_pct = float(spread_absolute / mid_price) if mid_price > 0 else 0.0

        # Calculate depth at various levels
        depth_bids_usd = 0.0
        depth_asks_usd = 0.0
        depth_at_01pct = 0.0
        depth_at_05pct = 0.0
        depth_at_1pct = 0.0

        # Process bids (descending order from best bid)
        for bid in bids:
            price = Decimal(str(bid[0]))
            qty = Decimal(str(bid[1]))
            value_usd = float(price * qty)
            depth_bids_usd += value_usd

            # Calculate distance from mid
            distance_pct = float((mid_price - price) / mid_price)
            if distance_pct <= 0.001:  # 0.1%
                depth_at_01pct += value_usd
            if distance_pct <= 0.005:  # 0.5%
                depth_at_05pct += value_usd
            if distance_pct <= 0.01:   # 1%
                depth_at_1pct += value_usd

        # Process asks (ascending order from best ask)
        for ask in asks:
            price = Decimal(str(ask[0]))
            qty = Decimal(str(ask[1]))
            value_usd = float(price * qty)
            depth_asks_usd += value_usd

            # Calculate distance from mid
            distance_pct = float((price - mid_price) / mid_price)
            if distance_pct <= 0.001:  # 0.1%
                depth_at_01pct += value_usd
            if distance_pct <= 0.005:  # 0.5%
                depth_at_05pct += value_usd
            if distance_pct <= 0.01:   # 1%
                depth_at_1pct += value_usd

        # Calculate imbalance ratio
        imbalance_ratio = depth_bids_usd / depth_asks_usd if depth_asks_usd > 0 else 1.0

        # Detect thin liquidity
        depth_total_usd = depth_bids_usd + depth_asks_usd
        is_thin_liquidity = depth_total_usd < self.config.thin_liquidity_depth_usd

        thin_warning = None
        if is_thin_liquidity:
            thin_warning = (
                f"Low liquidity: ${depth_total_usd:,.0f} total depth "
                f"(threshold: ${self.config.thin_liquidity_depth_usd:,.0f})"
            )

        # Create analysis object
        analysis = OrderBookAnalysis(
            symbol=symbol,
            timestamp=timestamp,
            best_bid=best_bid,
            best_ask=best_ask,
            mid_price=mid_price,
            spread_absolute=spread_absolute,
            spread_pct=spread_pct,
            depth_bids_usd=depth_bids_usd,
            depth_asks_usd=depth_asks_usd,
            depth_total_usd=depth_total_usd,
            depth_at_01pct=depth_at_01pct,
            depth_at_05pct=depth_at_05pct,
            depth_at_1pct=depth_at_1pct,
            imbalance_ratio=imbalance_ratio,
            is_thin_liquidity=is_thin_liquidity,
            thin_liquidity_warning=thin_warning
        )

        # Cache the analysis
        self._orderbook_cache[symbol] = analysis

        logger.debug(
            f"Order book analysis for {symbol}: "
            f"spread={spread_pct:.4%}, depth=${depth_total_usd:,.0f}, "
            f"imbalance={imbalance_ratio:.2f}"
        )

        return analysis

    # ========================================================================
    # SLIPPAGE ESTIMATION
    # ========================================================================

    def estimate_slippage(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        orderbook_analysis: Optional[OrderBookAnalysis] = None,
        bids: Optional[List[List[str]]] = None,
        asks: Optional[List[List[str]]] = None
    ) -> SlippageEstimate:
        """
        Estimate slippage for a potential order

        Calculates expected slippage by simulating order execution
        through the order book. Uses the actual price levels to
        determine how many levels would be consumed.

        Algorithm:
        1. Start from best bid (sell) or ask (buy)
        2. Consume levels until quantity is filled
        3. Calculate volume-weighted average price
        4. Compare to mid price for slippage

        Args:
            symbol: Trading symbol
            side: "BUY" or "SELL"
            quantity: Order quantity
            orderbook_analysis: Pre-computed analysis (optional)
            bids: Bid levels if analysis not provided
            asks: Ask levels if analysis not provided

        Returns:
            SlippageEstimate with expected slippage metrics
        """
        # Get or create order book analysis
        if orderbook_analysis is None:
            if bids is None or asks is None:
                # Try to use cached analysis
                analysis = self._orderbook_cache.get(symbol)
                if analysis is None:
                    logger.warning(f"No order book data available for {symbol}")
                    # Return conservative estimate
                    return SlippageEstimate(
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        order_value_usd=0.0,
                        expected_slippage_pct=0.5,  # Conservative default
                        worst_case_slippage_pct=1.0,
                        best_case_slippage_pct=0.1,
                        mid_price=Decimal("0"),
                        execution_price=Decimal("0"),
                        levels_consumed=0,
                        slippage_cost_usd=0.0,
                        is_acceptable=False,
                        warning_message="No order book data available"
                    )
            else:
                analysis = self.analyze_orderbook(symbol, bids, asks)
        else:
            analysis = orderbook_analysis
            # Get raw order book data if needed for detailed calculation
            bids = bids or []
            asks = asks or []

        mid_price = analysis.mid_price

        # Select appropriate side of book
        if side.upper() == "BUY":
            # Buying consumes asks (ascending price)
            levels = asks or []
            order_depth = analysis.depth_asks_usd
        else:
            # Selling consumes bids (descending price)
            levels = bids or []
            order_depth = analysis.depth_bids_usd

        # Calculate order value
        order_value_usd = float(quantity * mid_price)

        # Simulate order execution through order book
        remaining_qty = quantity
        total_value = Decimal("0")
        levels_consumed = 0

        for level in levels:
            if remaining_qty <= 0:
                break

            level_price = Decimal(str(level[0]))
            level_qty = Decimal(str(level[1]))

            # How much can we fill at this level
            fill_qty = min(remaining_qty, level_qty)
            total_value += fill_qty * level_price
            remaining_qty -= fill_qty
            levels_consumed += 1

        # Calculate execution price
        filled_qty = quantity - remaining_qty
        if filled_qty > 0:
            execution_price = total_value / filled_qty
        else:
            execution_price = mid_price

        # Calculate slippage
        if side.upper() == "BUY":
            # For buys, slippage is paying more than mid price
            slippage_pct = float((execution_price - mid_price) / mid_price) * 100
        else:
            # For sells, slippage is receiving less than mid price
            slippage_pct = float((mid_price - execution_price) / mid_price) * 100

        # Calculate slippage cost
        slippage_cost_usd = abs(slippage_pct / 100 * order_value_usd)

        # Estimate worst case (50% more than expected)
        worst_case_slippage_pct = slippage_pct * 1.5 if slippage_pct > 0 else 0.5

        # Estimate best case (50% of expected)
        best_case_slippage_pct = slippage_pct * 0.5 if slippage_pct > 0 else 0.0

        # Check if acceptable
        is_acceptable = abs(slippage_pct) <= self.config.max_acceptable_slippage_pct

        # Generate warning if needed
        warning_message = None
        if not is_acceptable:
            warning_message = (
                f"Expected slippage {slippage_pct:.3f}% exceeds threshold "
                f"{self.config.max_acceptable_slippage_pct:.3f}%"
            )
        elif abs(slippage_pct) > self.config.slippage_warning_threshold:
            warning_message = f"Elevated slippage expected: {slippage_pct:.3f}%"

        # Check for partial fill risk
        if remaining_qty > 0:
            fill_pct = float(filled_qty / quantity) * 100
            warning_message = (
                f"Partial fill likely: only {fill_pct:.1f}% fillable. "
                + (warning_message or "")
            )

        estimate = SlippageEstimate(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_value_usd=order_value_usd,
            expected_slippage_pct=slippage_pct,
            worst_case_slippage_pct=worst_case_slippage_pct,
            best_case_slippage_pct=best_case_slippage_pct,
            mid_price=mid_price,
            execution_price=execution_price,
            levels_consumed=levels_consumed,
            slippage_cost_usd=slippage_cost_usd,
            is_acceptable=is_acceptable,
            warning_message=warning_message
        )

        logger.debug(
            f"Slippage estimate for {symbol} {side} {quantity}: "
            f"expected={slippage_pct:.3f}%, cost=${slippage_cost_usd:.2f}, "
            f"levels={levels_consumed}"
        )

        return estimate

    # ========================================================================
    # ORDER TYPE SELECTION
    # ========================================================================

    def get_order_recommendation(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        urgency: ExecutionUrgency = ExecutionUrgency.MEDIUM,
        orderbook_depth: Optional[Dict] = None,
        current_price: Optional[Decimal] = None
    ) -> OrderTypeRecommendation:
        """
        Get intelligent order type recommendation

        Analyzes market conditions and order parameters to recommend
        the optimal order type and execution strategy.

        Decision Process:
        1. Analyze order book for spread and liquidity
        2. Estimate potential slippage
        3. Check order size relative to liquidity
        4. Consider execution urgency
        5. Select optimal order type and strategy

        Args:
            symbol: Trading symbol
            side: "BUY" or "SELL"
            quantity: Order quantity
            urgency: Execution urgency level
            orderbook_depth: Order book data {"bids": [...], "asks": [...]}
            current_price: Current market price

        Returns:
            OrderTypeRecommendation with complete execution plan
        """
        # Parse order book data
        bids = []
        asks = []

        if orderbook_depth:
            bids = orderbook_depth.get("bids", [])
            asks = orderbook_depth.get("asks", [])

        # Analyze order book
        analysis = self.analyze_orderbook(
            symbol=symbol,
            bids=bids,
            asks=asks,
            current_price=current_price
        )

        # Estimate slippage
        slippage_estimate = self.estimate_slippage(
            symbol=symbol,
            side=side,
            quantity=quantity,
            orderbook_analysis=analysis,
            bids=bids,
            asks=asks
        )

        # Calculate order value
        mid_price = analysis.mid_price if analysis.mid_price > 0 else (current_price or Decimal("0"))
        order_value_usd = float(quantity * mid_price)

        # Determine order size category
        is_small = order_value_usd < self.config.small_order_threshold
        is_medium = self.config.small_order_threshold <= order_value_usd < self.config.medium_order_threshold
        is_large = order_value_usd >= self.config.medium_order_threshold

        # Check if order is large relative to book depth
        relative_to_book = order_value_usd / analysis.depth_total_usd if analysis.depth_total_usd > 0 else 1.0
        is_large_for_book = relative_to_book > self.config.large_order_threshold_pct

        # Determine spread category
        is_tight_spread = analysis.spread_pct < self.config.tight_spread_threshold
        is_wide_spread = analysis.spread_pct > self.config.wide_spread_threshold

        # Initialize recommendation variables
        order_type = OrderTypeSelection.MARKET
        strategy = ExecutionStrategyType.SINGLE
        limit_price = None
        visible_quantity = None
        chunks = []
        reasoning_parts = []
        confidence = 0.7  # Base confidence

        # ====================================================================
        # DECISION LOGIC
        # ====================================================================

        # Rule 1: POST_ONLY for low urgency (stat arb)
        if (
            urgency == ExecutionUrgency.LOW and
            self.config.post_only_enabled and
            not analysis.is_thin_liquidity
        ):
            order_type = OrderTypeSelection.POST_ONLY
            strategy = ExecutionStrategyType.POST_ONLY

            # Set limit price to capture maker fee
            if side.upper() == "BUY":
                limit_price = analysis.best_bid  # Post at best bid
            else:
                limit_price = analysis.best_ask  # Post at best ask

            reasoning_parts.append("LOW urgency -> POST_ONLY to capture maker fees")
            confidence = 0.8

        # Rule 2: CRITICAL urgency -> always MARKET
        elif urgency == ExecutionUrgency.CRITICAL:
            order_type = OrderTypeSelection.MARKET
            strategy = ExecutionStrategyType.SINGLE
            reasoning_parts.append("CRITICAL urgency -> immediate MARKET execution")
            confidence = 0.95

        # Rule 3: Large orders relative to book -> ICEBERG or TWAP
        elif is_large_for_book:
            if urgency == ExecutionUrgency.LOW:
                # Use iceberg to hide size
                order_type = OrderTypeSelection.LIMIT
                strategy = ExecutionStrategyType.SPLIT_ICEBERG

                visible_quantity = quantity * Decimal(str(self.config.iceberg_visible_pct))
                if side.upper() == "BUY":
                    limit_price = analysis.mid_price
                else:
                    limit_price = analysis.mid_price

                reasoning_parts.append(
                    f"Large order ({relative_to_book:.1%} of book) + LOW urgency -> "
                    f"ICEBERG ({self.config.iceberg_visible_pct:.0%} visible)"
                )
                confidence = 0.75
            else:
                # Use TWAP to minimize impact
                order_type = OrderTypeSelection.LIMIT
                strategy = ExecutionStrategyType.SPLIT_TWAP

                # Calculate chunks
                num_chunks = min(
                    self.config.twap_max_chunks,
                    max(self.config.twap_min_chunks, int(relative_to_book / 0.005))
                )
                chunk_qty = quantity / num_chunks

                for i in range(num_chunks):
                    chunk_time = datetime.now(timezone.utc) + timedelta(
                        seconds=i * self.config.twap_chunk_interval_seconds
                    )
                    chunks.append({
                        "chunk_id": i + 1,
                        "quantity": chunk_qty,
                        "scheduled_time": chunk_time.isoformat(),
                        "status": "pending"
                    })

                reasoning_parts.append(
                    f"Large order ({relative_to_book:.1%} of book) -> "
                    f"TWAP ({num_chunks} chunks over {num_chunks * self.config.twap_chunk_interval_seconds // 60}min)"
                )
                confidence = 0.8

        # Rule 4: Small order, tight spread, high urgency -> MARKET
        elif is_small and is_tight_spread and urgency in (ExecutionUrgency.HIGH, ExecutionUrgency.CRITICAL):
            order_type = OrderTypeSelection.MARKET
            strategy = ExecutionStrategyType.SINGLE
            reasoning_parts.append(
                f"Small order (${order_value_usd:,.0f}) + tight spread ({analysis.spread_pct:.3%}) + "
                f"{urgency.value} urgency -> MARKET"
            )
            confidence = 0.85

        # Rule 5: Wide spread -> prefer LIMIT
        elif is_wide_spread:
            order_type = OrderTypeSelection.LIMIT
            strategy = ExecutionStrategyType.SINGLE

            # Set limit at mid price with offset (use Decimal for calculation)
            # Convert spread_pct (float) to Decimal for consistent arithmetic
            offset_decimal = Decimal(str(analysis.spread_pct)) * Decimal(str(self.config.limit_offset_bps / 100))
            if side.upper() == "BUY":
                limit_price = analysis.mid_price - (analysis.mid_price * offset_decimal)
            else:
                limit_price = analysis.mid_price + (analysis.mid_price * offset_decimal)

            reasoning_parts.append(
                f"Wide spread ({analysis.spread_pct:.3%} > {self.config.wide_spread_threshold:.3%}) -> "
                f"LIMIT at {limit_price}"
            )
            confidence = 0.75

        # Rule 6: Medium order -> LIMIT at mid price
        elif is_medium:
            order_type = OrderTypeSelection.LIMIT
            strategy = ExecutionStrategyType.SINGLE
            limit_price = analysis.mid_price

            reasoning_parts.append(
                f"Medium order (${order_value_usd:,.0f}) -> LIMIT at mid ({limit_price})"
            )
            confidence = 0.7

        # Rule 7: Default - LIMIT for small orders, MARKET for high urgency
        else:
            if urgency == ExecutionUrgency.HIGH:
                order_type = OrderTypeSelection.MARKET
                strategy = ExecutionStrategyType.SINGLE
                reasoning_parts.append(f"High urgency -> MARKET")
            else:
                order_type = OrderTypeSelection.LIMIT
                strategy = ExecutionStrategyType.SINGLE
                limit_price = analysis.mid_price
                reasoning_parts.append(f"Default -> LIMIT at mid ({limit_price})")

            confidence = 0.65

        # Add liquidity warning if applicable
        if analysis.is_thin_liquidity:
            reasoning_parts.append(f"WARNING: {analysis.thin_liquidity_warning}")
            confidence *= 0.8

        # Add slippage warning if applicable
        if slippage_estimate.warning_message:
            reasoning_parts.append(f"SLIPPAGE: {slippage_estimate.warning_message}")

        # Build recommendation
        recommendation = OrderTypeRecommendation(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_value_usd=order_value_usd,
            urgency=urgency,
            order_type=order_type,
            strategy=strategy,
            limit_price=limit_price,
            visible_quantity=visible_quantity,
            chunks=chunks,
            orderbook_analysis=analysis,
            slippage_estimate=slippage_estimate,
            reasoning=" | ".join(reasoning_parts),
            confidence=confidence
        )

        logger.info(
            f"Smart router recommendation for {symbol} {side} {quantity}: "
            f"{order_type.value}/{strategy.value} | {reasoning_parts[0]}"
        )

        return recommendation

    # ========================================================================
    # EXECUTION
    # ========================================================================

    async def execute_recommendation(
        self,
        recommendation: OrderTypeRecommendation,
        execute_func: Callable[..., Any],
        cancel_func: Optional[Callable[..., Any]] = None
    ) -> ExecutionRecord:
        """
        Execute order based on router recommendation

        Handles the actual order execution including:
        - Single orders (market/limit)
        - TWAP chunk execution
        - Iceberg order management
        - Limit order timeout and fallback

        Args:
            recommendation: OrderTypeRecommendation from get_order_recommendation
            execute_func: Async function to place orders
            cancel_func: Optional async function to cancel orders (for timeout)

        Returns:
            ExecutionRecord with actual execution results
        """
        order_id = f"smart_{recommendation.symbol}_{int(time.time() * 1000)}"
        order_sent_at = datetime.now(timezone.utc)

        # Initialize execution record
        record = ExecutionRecord(
            order_id=order_id,
            symbol=recommendation.symbol,
            side=recommendation.side,
            quantity=recommendation.quantity,
            order_type=recommendation.order_type,
            strategy=recommendation.strategy,
            expected_price=recommendation.slippage_estimate.execution_price if recommendation.slippage_estimate else recommendation.orderbook_analysis.mid_price,
            actual_price=Decimal("0"),
            limit_price=recommendation.limit_price,
            order_sent_at=order_sent_at
        )

        try:
            # Execute based on strategy
            if recommendation.strategy == ExecutionStrategyType.SPLIT_TWAP:
                # Execute TWAP chunks
                result = await self._execute_twap(recommendation, execute_func)
            elif recommendation.strategy == ExecutionStrategyType.SPLIT_ICEBERG:
                # Execute iceberg order
                result = await self._execute_iceberg(recommendation, execute_func)
            else:
                # Single order execution
                result = await self._execute_single(recommendation, execute_func, cancel_func)

            # Update record with results
            record.actual_price = result.get("avg_price", record.expected_price)
            record.filled_quantity = Decimal(str(result.get("filled_quantity", 0)))
            record.fill_rate = float(record.filled_quantity / recommendation.quantity) if recommendation.quantity > 0 else 0.0
            record.order_filled_at = datetime.now(timezone.utc)
            record.execution_time_ms = (record.order_filled_at - order_sent_at).total_seconds() * 1000
            record.is_complete = record.fill_rate >= 0.99

            # Calculate actual slippage
            if record.expected_price > 0:
                if recommendation.side.upper() == "BUY":
                    record.slippage_pct = float((record.actual_price - record.expected_price) / record.expected_price) * 100
                else:
                    record.slippage_pct = float((record.expected_price - record.actual_price) / record.expected_price) * 100

                record.slippage_usd = abs(record.slippage_pct / 100 * float(record.filled_quantity * record.actual_price))

            # Compare to estimate
            if recommendation.slippage_estimate:
                if recommendation.slippage_estimate.expected_slippage_pct != 0:
                    record.slippage_vs_estimate = record.slippage_pct / recommendation.slippage_estimate.expected_slippage_pct

            logger.info(
                f"Execution complete for {order_id}: "
                f"filled={record.fill_rate:.1%}, slippage={record.slippage_pct:.3f}%, "
                f"time={record.execution_time_ms:.0f}ms"
            )

        except Exception as e:
            record.error_message = str(e)
            record.is_complete = False
            logger.error(f"Execution failed for {order_id}: {e}")

        # Update metrics
        self._execution_history.append(record)
        self._update_metrics(record)

        return record

    async def _execute_single(
        self,
        recommendation: OrderTypeRecommendation,
        execute_func: Callable,
        cancel_func: Optional[Callable] = None
    ) -> Dict:
        """
        Execute a single order (market or limit)

        For limit orders, implements timeout and fallback to market.
        """
        params = {
            "symbol": recommendation.symbol,
            "side": recommendation.side.upper(),
            "qty": str(recommendation.quantity)
        }

        if recommendation.order_type == OrderTypeSelection.MARKET:
            params["order_type"] = "Market"
        elif recommendation.order_type == OrderTypeSelection.POST_ONLY:
            params["order_type"] = "Limit"
            params["price"] = str(recommendation.limit_price)
            params["time_in_force"] = "PostOnly"
        else:
            params["order_type"] = "Limit"
            params["price"] = str(recommendation.limit_price)
            params["time_in_force"] = "GTC"

        # Execute order
        result = await execute_func(**params)

        # For limit orders, check for fill and potentially fall back to market
        if recommendation.order_type in (OrderTypeSelection.LIMIT, OrderTypeSelection.POST_ONLY):
            if self.config.limit_fallback_to_market and cancel_func:
                # Wait for fill with timeout
                start_time = time.time()
                filled_qty = Decimal(str(result.get("filled_qty", 0)))

                while (
                    filled_qty < recommendation.quantity and
                    time.time() - start_time < self.config.limit_timeout_seconds
                ):
                    await asyncio.sleep(1)
                    # Check order status (would need status check function)
                    # For now, assume the initial result
                    break

                # If not filled and we should fall back to market
                if filled_qty < recommendation.quantity * Decimal("0.5"):
                    # Cancel remaining and place market order
                    order_id = result.get("orderId", result.get("order_id"))
                    if order_id:
                        try:
                            await cancel_func(symbol=recommendation.symbol, order_id=order_id)
                            remaining = recommendation.quantity - filled_qty
                            market_result = await execute_func(
                                symbol=recommendation.symbol,
                                side=recommendation.side.upper(),
                                qty=str(remaining),
                                order_type="Market"
                            )
                            # Combine results
                            market_filled = Decimal(str(market_result.get("filled_qty", 0)))
                            market_price = Decimal(str(market_result.get("avg_price", 0)))
                            limit_price = Decimal(str(result.get("avg_price", recommendation.limit_price)))

                            total_filled = filled_qty + market_filled
                            if total_filled > 0:
                                avg_price = (filled_qty * limit_price + market_filled * market_price) / total_filled
                                result["filled_quantity"] = str(total_filled)
                                result["avg_price"] = str(avg_price)
                        except Exception as e:
                            logger.warning(f"Failed to fall back to market: {e}")

        return {
            "order_id": result.get("orderId", result.get("order_id")),
            "filled_quantity": Decimal(str(result.get("filled_qty", result.get("filled_quantity", 0)))),
            "avg_price": Decimal(str(result.get("avg_price", result.get("avgPrice", recommendation.limit_price or 0))))
        }

    async def _execute_twap(
        self,
        recommendation: OrderTypeRecommendation,
        execute_func: Callable
    ) -> Dict:
        """
        Execute TWAP (Time-Weighted Average Price) order

        Splits order into chunks executed at regular intervals.
        """
        total_filled = Decimal("0")
        total_value = Decimal("0")

        for chunk in recommendation.chunks:
            chunk_qty = Decimal(str(chunk["quantity"]))

            try:
                result = await execute_func(
                    symbol=recommendation.symbol,
                    side=recommendation.side.upper(),
                    qty=str(chunk_qty),
                    order_type="Limit",
                    price=str(recommendation.orderbook_analysis.mid_price),
                    time_in_force="IOC"  # Immediate or cancel for each chunk
                )

                filled = Decimal(str(result.get("filled_qty", 0)))
                price = Decimal(str(result.get("avg_price", recommendation.orderbook_analysis.mid_price)))

                total_filled += filled
                total_value += filled * price

                chunk["status"] = "executed"
                chunk["filled_quantity"] = str(filled)

            except Exception as e:
                chunk["status"] = "failed"
                chunk["error"] = str(e)
                logger.warning(f"TWAP chunk {chunk['chunk_id']} failed: {e}")

            # Wait for next chunk
            if chunk != recommendation.chunks[-1]:
                await asyncio.sleep(self.config.twap_chunk_interval_seconds)

        avg_price = total_value / total_filled if total_filled > 0 else Decimal("0")

        return {
            "filled_quantity": total_filled,
            "avg_price": avg_price
        }

    async def _execute_iceberg(
        self,
        recommendation: OrderTypeRecommendation,
        execute_func: Callable
    ) -> Dict:
        """
        Execute iceberg order

        Places visible portion, refills as it gets consumed.
        """
        total_filled = Decimal("0")
        total_value = Decimal("0")
        remaining = recommendation.quantity
        visible = recommendation.visible_quantity or recommendation.quantity * Decimal("0.15")

        max_iterations = 20  # Safety limit
        iteration = 0

        while remaining > 0 and iteration < max_iterations:
            iteration += 1
            chunk_qty = min(visible, remaining)

            try:
                result = await execute_func(
                    symbol=recommendation.symbol,
                    side=recommendation.side.upper(),
                    qty=str(chunk_qty),
                    order_type="Limit",
                    price=str(recommendation.limit_price),
                    time_in_force="GTC"
                )

                filled = Decimal(str(result.get("filled_qty", 0)))
                price = Decimal(str(result.get("avg_price", recommendation.limit_price)))

                total_filled += filled
                total_value += filled * price
                remaining -= filled

                if filled < chunk_qty * Decimal("0.5"):
                    # Poor fill rate, stop iceberg
                    logger.warning("Iceberg fill rate too low, stopping")
                    break

            except Exception as e:
                logger.warning(f"Iceberg iteration {iteration} failed: {e}")
                break

            # Small delay between visible chunks
            if remaining > 0:
                await asyncio.sleep(2)

        avg_price = total_value / total_filled if total_filled > 0 else Decimal("0")

        return {
            "filled_quantity": total_filled,
            "avg_price": avg_price
        }

    # ========================================================================
    # METRICS
    # ========================================================================

    def _update_metrics(self, record: ExecutionRecord):
        """Update aggregate metrics with execution record"""
        self._metrics.total_orders += 1

        if record.is_complete:
            self._metrics.successful_orders += 1
        else:
            if record.error_message:
                self._metrics.failed_orders += 1
            else:
                self._metrics.partial_fills += 1

        # Update slippage metrics
        self._metrics.total_slippage_usd += record.slippage_usd

        if record.slippage_pct > self._metrics.max_slippage_pct:
            self._metrics.max_slippage_pct = record.slippage_pct

        # Update order type counts
        if record.order_type == OrderTypeSelection.MARKET:
            self._metrics.market_orders += 1
        elif record.order_type == OrderTypeSelection.POST_ONLY:
            self._metrics.post_only_orders += 1
        elif record.strategy == ExecutionStrategyType.SPLIT_ICEBERG:
            self._metrics.iceberg_orders += 1
        elif record.strategy == ExecutionStrategyType.SPLIT_TWAP:
            self._metrics.twap_orders += 1
        else:
            self._metrics.limit_orders += 1

        # Calculate averages from history
        if self._execution_history:
            valid_records = [r for r in self._execution_history if not r.error_message]
            if valid_records:
                self._metrics.avg_slippage_pct = statistics.mean(r.slippage_pct for r in valid_records)
                self._metrics.avg_fill_rate = statistics.mean(r.fill_rate for r in valid_records)
                self._metrics.avg_execution_time_ms = statistics.mean(r.execution_time_ms for r in valid_records)

                # Limit order fill rate
                limit_records = [r for r in valid_records if r.order_type in (OrderTypeSelection.LIMIT, OrderTypeSelection.POST_ONLY)]
                if limit_records:
                    self._metrics.limit_order_fill_rate = statistics.mean(r.fill_rate for r in limit_records)

                # Market order slippage
                market_records = [r for r in valid_records if r.order_type == OrderTypeSelection.MARKET]
                if market_records:
                    self._metrics.market_order_avg_slippage = statistics.mean(r.slippage_pct for r in market_records)

                # Estimate accuracy
                records_with_estimate = [r for r in valid_records if r.slippage_vs_estimate > 0]
                if records_with_estimate:
                    self._metrics.slippage_vs_estimate = statistics.mean(r.slippage_vs_estimate for r in records_with_estimate)

        self._metrics.last_updated = datetime.now(timezone.utc)

    def get_metrics(self) -> RouterMetrics:
        """
        Get current router performance metrics

        Returns:
            RouterMetrics with aggregate performance data
        """
        return self._metrics

    def get_execution_quality_report(
        self,
        period_hours: int = 24
    ) -> ExecutionQualityReport:
        """
        Generate comprehensive execution quality report

        Analyzes router performance over specified time period and
        provides actionable recommendations for improvement.

        Args:
            period_hours: Hours of history to analyze

        Returns:
            ExecutionQualityReport with detailed analysis
        """
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=period_hours)

        # Filter records to period
        period_records = [
            r for r in self._execution_history
            if r.order_sent_at >= start_time
        ]

        # Calculate metrics for period
        period_metrics = RouterMetrics()

        if period_records:
            valid_records = [r for r in period_records if not r.error_message]

            period_metrics.total_orders = len(period_records)
            period_metrics.successful_orders = len([r for r in period_records if r.is_complete])
            period_metrics.failed_orders = len([r for r in period_records if r.error_message])
            period_metrics.partial_fills = period_metrics.total_orders - period_metrics.successful_orders - period_metrics.failed_orders

            if valid_records:
                period_metrics.avg_slippage_pct = statistics.mean(r.slippage_pct for r in valid_records)
                period_metrics.total_slippage_usd = sum(r.slippage_usd for r in valid_records)
                period_metrics.avg_fill_rate = statistics.mean(r.fill_rate for r in valid_records)
                period_metrics.avg_execution_time_ms = statistics.mean(r.execution_time_ms for r in valid_records)

        # Calculate baseline comparison (assume 0.1% slippage for naive market orders)
        baseline_slippage = 0.1
        slippage_reduction = (baseline_slippage - period_metrics.avg_slippage_pct) / baseline_slippage if period_metrics.avg_slippage_pct else 0

        # Calculate strategy breakdown
        strategy_breakdown = {}
        for strategy in ExecutionStrategyType:
            strat_records = [r for r in period_records if r.strategy == strategy]
            if strat_records:
                strategy_breakdown[strategy.value] = {
                    "count": len(strat_records),
                    "avg_slippage_pct": statistics.mean(r.slippage_pct for r in strat_records),
                    "avg_fill_rate": statistics.mean(r.fill_rate for r in strat_records),
                    "success_rate": len([r for r in strat_records if r.is_complete]) / len(strat_records)
                }

        # Order type breakdown
        order_type_breakdown = {}
        for order_type in OrderTypeSelection:
            type_records = [r for r in period_records if r.order_type == order_type]
            if type_records:
                order_type_breakdown[order_type.value] = {
                    "count": len(type_records),
                    "avg_slippage_pct": statistics.mean(r.slippage_pct for r in type_records),
                    "avg_fill_rate": statistics.mean(r.fill_rate for r in type_records)
                }

        # Generate recommendations
        recommendations = []

        if period_metrics.avg_slippage_pct > 0.15:
            recommendations.append("Consider using more LIMIT orders - slippage is elevated")

        if period_metrics.avg_fill_rate < 0.9:
            recommendations.append("Fill rate below 90% - consider adjusting limit price offsets")

        limit_fill_rate = order_type_breakdown.get("limit", {}).get("avg_fill_rate", 1.0)
        if limit_fill_rate < 0.7:
            recommendations.append("Limit order fill rate low - consider using IOC or adjusting timeout")

        if period_metrics.partial_fills > period_metrics.total_orders * 0.2:
            recommendations.append("High partial fill rate - consider larger visible iceberg portions")

        if not recommendations:
            recommendations.append("Router performance is within acceptable parameters")

        return ExecutionQualityReport(
            report_period_start=start_time,
            report_period_end=now,
            metrics=period_metrics,
            slippage_reduction_pct=slippage_reduction * 100,
            slippage_savings_usd=(baseline_slippage - period_metrics.avg_slippage_pct) / 100 * period_metrics.total_slippage_usd if period_metrics.avg_slippage_pct else 0,
            fill_rate_improvement=period_metrics.avg_fill_rate - 0.95 if period_metrics.avg_fill_rate else 0,
            strategy_breakdown=strategy_breakdown,
            order_type_breakdown=order_type_breakdown,
            recommendations=recommendations
        )

    def get_status(self) -> Dict:
        """
        Get router status summary

        Returns:
            Dictionary with configuration and current metrics
        """
        return {
            "config": {
                "tight_spread_threshold": self.config.tight_spread_threshold,
                "wide_spread_threshold": self.config.wide_spread_threshold,
                "small_order_threshold": self.config.small_order_threshold,
                "medium_order_threshold": self.config.medium_order_threshold,
                "twap_chunks": f"{self.config.twap_min_chunks}-{self.config.twap_max_chunks}",
                "limit_timeout_seconds": self.config.limit_timeout_seconds,
                "max_acceptable_slippage": f"{self.config.max_acceptable_slippage_pct}%"
            },
            "metrics": {
                "total_orders": self._metrics.total_orders,
                "successful_orders": self._metrics.successful_orders,
                "failed_orders": self._metrics.failed_orders,
                "avg_slippage_pct": round(self._metrics.avg_slippage_pct, 4),
                "avg_fill_rate": round(self._metrics.avg_fill_rate, 4),
                "avg_execution_time_ms": round(self._metrics.avg_execution_time_ms, 1)
            },
            "order_type_distribution": {
                "market": self._metrics.market_orders,
                "limit": self._metrics.limit_orders,
                "post_only": self._metrics.post_only_orders,
                "iceberg": self._metrics.iceberg_orders,
                "twap": self._metrics.twap_orders
            },
            "history_size": len(self._execution_history),
            "last_updated": self._metrics.last_updated.isoformat() if self._metrics.last_updated else None
        }


# ============================================================================
# GLOBAL INSTANCE MANAGEMENT
# ============================================================================

# Global router instance
_smart_router: Optional[SmartOrderRouter] = None


def get_smart_router(config: Optional[SmartRouterConfig] = None) -> SmartOrderRouter:
    """
    Get or create global smart router instance

    Args:
        config: Optional configuration (only used if creating new instance)

    Returns:
        SmartOrderRouter instance
    """
    global _smart_router
    if _smart_router is None:
        if config is None:
            # RES-05 (2026-08-16): source the small-order threshold from
            # Settings instead of the hardcoded dataclass literal, so it is
            # operator-tunable via SMART_ROUTER_SMALL_ORDER_THRESHOLD_USD.
            #
            # Guarding on `config is None` is mandatory: an explicit config
            # passed by the caller must still win.
            #
            # Wired HERE rather than in the lifespan because
            # POST /api/v1/execution/reset calls reset_smart_router() and the
            # next get_smart_router() rebuilds through this factory — a
            # lifespan-only wiring would silently revert to the literal on the
            # first reset.
            #
            # Imported lazily INSIDE the function: a module-scope import risks
            # a config <-> execution import cycle.
            from app.config import get_settings

            settings = get_settings()
            config = SmartRouterConfig(
                small_order_threshold=settings.smart_router_small_order_threshold_usd
            )
        _smart_router = SmartOrderRouter(config)
    return _smart_router


def reset_smart_router():
    """Reset global smart router instance"""
    global _smart_router
    _smart_router = None
    logger.info("Smart router instance reset")
