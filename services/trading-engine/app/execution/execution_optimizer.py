"""
Execution Optimizer - Order Type Selection and Fee Optimization
Phase 4.1: Smart Order Routing - Execution Optimization Component

Purpose:
- Select optimal order type (Market vs Limit vs Post-Only)
- Optimize timing for execution (immediate vs passive)
- Minimize fees through maker/taker fee analysis
- Balance urgency vs cost tradeoffs
- Calculate execution cost including fees and slippage

Research Sources:
- Exchange Fee Structure Analysis (Bybit, Binance)
- Optimal Execution Timing (Almgren & Chriss)
- Maker vs Taker Economics in Crypto
- Post-Only Order Strategy Research

Fee Analysis (Bybit):
- Maker fee: 0.01% (can be negative with rebates)
- Taker fee: 0.06%
- Fee difference: 0.05% per trade
- For $10k order: $5 savings using limit vs market

Decision Framework:
+------------------+------------------+------------------+------------------+
| Urgency          | Spread           | Order Size       | Recommendation   |
+------------------+------------------+------------------+------------------+
| CRITICAL         | Any              | Any              | MARKET           |
| HIGH             | <0.03%           | <$1k             | MARKET           |
| HIGH             | >0.03%           | Any              | LIMIT_IOC        |
| MEDIUM           | <0.05%           | <$5k             | LIMIT_GTC        |
| MEDIUM           | >0.05%           | Any              | LIMIT_GTC        |
| LOW              | Any              | Any              | POST_ONLY        |
+------------------+------------------+------------------+------------------+

Created: 2025-12-11
Author: Backend Developer Agent
"""

import logging
import math
from decimal import Decimal
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Union
from enum import Enum
from collections import deque
import statistics

# Configure logging for execution optimization
logger = logging.getLogger(__name__)


# ============================================================================
# ENUMERATIONS
# ============================================================================

class ExecutionUrgency(str, Enum):
    """
    Execution urgency levels determining order type selection

    CRITICAL: Must execute immediately (stop loss, liquidation prevention)
    HIGH: Speed is important, accept some cost increase
    MEDIUM: Balanced approach between speed and cost
    LOW: Patient execution, minimize costs (stat arb, grid trading)
    """
    CRITICAL = "critical"   # Immediate execution required
    HIGH = "high"           # Speed over cost
    MEDIUM = "medium"       # Balanced approach
    LOW = "low"             # Cost minimization priority


class OptimalOrderType(str, Enum):
    """
    Order type recommendation from optimizer

    MARKET: Execute immediately at market price (taker)
    LIMIT_GTC: Limit order Good-Till-Cancelled (potentially maker)
    LIMIT_IOC: Limit order Immediate-Or-Cancel (usually taker)
    LIMIT_FOK: Limit order Fill-Or-Kill (all or nothing)
    POST_ONLY: Maker-only order (rejected if would take)
    """
    MARKET = "market"
    LIMIT_GTC = "limit_gtc"
    LIMIT_IOC = "limit_ioc"
    LIMIT_FOK = "limit_fok"
    POST_ONLY = "post_only"


class TimingStrategy(str, Enum):
    """
    Execution timing strategy

    IMMEDIATE: Execute now regardless of conditions
    OPPORTUNISTIC: Wait briefly for better price
    PATIENT: Wait for optimal conditions
    SCHEDULED: Execute at specific time
    """
    IMMEDIATE = "immediate"
    OPPORTUNISTIC = "opportunistic"
    PATIENT = "patient"
    SCHEDULED = "scheduled"


class CostComponent(str, Enum):
    """Components of total execution cost"""
    TAKER_FEE = "taker_fee"
    MAKER_FEE = "maker_fee"
    SLIPPAGE = "slippage"
    SPREAD = "spread"
    MARKET_IMPACT = "market_impact"
    OPPORTUNITY_COST = "opportunity_cost"


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class FeeStructure:
    """
    Exchange fee structure configuration

    Research-backed defaults for Bybit:
    - Maker: 0.01% (can be lower with VIP tiers)
    - Taker: 0.06%
    - Fee savings: 0.05% per trade using maker orders
    """
    # Standard fees (as decimal)
    maker_fee: float = 0.0001       # 0.01%
    taker_fee: float = 0.0006       # 0.06%

    # VIP tier adjustments
    vip_level: int = 0
    vip_maker_discount: float = 0.0
    vip_taker_discount: float = 0.0

    # Fee rebates (if any)
    maker_rebate: float = 0.0       # Some exchanges offer maker rebates

    @property
    def effective_maker_fee(self) -> float:
        """Calculate effective maker fee after discounts"""
        base_fee = self.maker_fee - self.maker_rebate
        return max(0, base_fee * (1 - self.vip_maker_discount))

    @property
    def effective_taker_fee(self) -> float:
        """Calculate effective taker fee after discounts"""
        return self.taker_fee * (1 - self.vip_taker_discount)

    @property
    def fee_difference(self) -> float:
        """Difference between taker and maker fees"""
        return self.effective_taker_fee - self.effective_maker_fee


@dataclass
class ExecutionOptimizerConfig:
    """
    Configuration for execution optimization

    Thresholds calibrated for typical crypto trading:
    - Spread thresholds determine market order acceptability
    - Size thresholds for order type selection
    - Timeout values for limit order patience
    """
    # Fee structure
    fee_structure: FeeStructure = field(default_factory=FeeStructure)

    # Spread thresholds (as decimal)
    market_order_max_spread: float = 0.0003     # 0.03% - Use market if spread below
    limit_preferred_min_spread: float = 0.0005  # 0.05% - Prefer limit if above

    # Order size thresholds (in USD)
    small_order_threshold: float = 1000.0       # Small orders can use market
    medium_order_threshold: float = 5000.0      # Medium orders prefer limit
    large_order_threshold: float = 10000.0      # Large orders need splitting

    # Timing configuration
    limit_order_timeout_seconds: int = 30       # Time to wait for limit fill
    patient_timeout_seconds: int = 120          # Time for patient execution
    post_only_max_wait_seconds: int = 60        # Max wait for post-only

    # Cost thresholds
    max_acceptable_cost_pct: float = 0.15       # 0.15% max total cost
    cost_warning_threshold_pct: float = 0.10    # 0.10% warning level

    # Urgency timing multipliers
    urgency_timeout_multipliers: Dict[str, float] = field(default_factory=lambda: {
        "critical": 0.0,   # No waiting
        "high": 0.25,      # 25% of normal timeout
        "medium": 1.0,     # Normal timeout
        "low": 3.0         # 3x normal timeout (patient)
    })

    # Fill probability thresholds
    min_fill_probability: float = 0.7           # Minimum acceptable fill prob


@dataclass
class CostBreakdown:
    """
    Detailed breakdown of execution costs

    Provides transparency into all cost components:
    - Trading fees (maker or taker)
    - Slippage from price movement
    - Spread cost (half-spread)
    - Market impact (for larger orders)
    - Opportunity cost (for patient execution)
    """
    # Component costs (in USD)
    fee_cost_usd: float
    slippage_cost_usd: float
    spread_cost_usd: float
    market_impact_cost_usd: float
    opportunity_cost_usd: float

    # Total
    total_cost_usd: float

    # As percentages
    fee_cost_pct: float
    slippage_cost_pct: float
    spread_cost_pct: float
    market_impact_cost_pct: float
    opportunity_cost_pct: float
    total_cost_pct: float

    # Fee type used
    is_maker_fee: bool


@dataclass
class OptimizationResult:
    """
    Complete optimization recommendation

    Contains:
    - Recommended order type and timing
    - Cost analysis comparing alternatives
    - Fill probability and time estimates
    - Risk warnings and confidence score
    """
    symbol: str
    side: str
    quantity: Decimal
    order_value_usd: float
    urgency: ExecutionUrgency

    # Recommendation
    recommended_order_type: OptimalOrderType
    recommended_timing: TimingStrategy
    recommended_price: Optional[Decimal]

    # Cost analysis
    expected_cost: CostBreakdown
    market_order_cost: CostBreakdown     # For comparison
    limit_order_cost: CostBreakdown      # For comparison
    post_only_cost: CostBreakdown        # For comparison

    # Cost savings
    savings_vs_market_usd: float
    savings_vs_market_pct: float

    # Fill probability and timing
    estimated_fill_probability: float
    estimated_time_to_fill_seconds: float

    # Risk assessment
    confidence: float                    # 0-1 confidence in recommendation
    warnings: List[str] = field(default_factory=list)
    reasoning: str = ""

    # Timestamp
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ExecutionMetrics:
    """
    Tracked execution performance metrics

    Used for optimization feedback loop:
    - Actual vs expected fill rates
    - Realized vs estimated costs
    - Order type effectiveness
    """
    total_optimizations: int = 0
    orders_executed: int = 0

    # Fill metrics
    avg_fill_rate: float = 0.0
    limit_order_fill_rate: float = 0.0
    post_only_fill_rate: float = 0.0

    # Cost metrics
    total_fees_paid_usd: float = 0.0
    total_slippage_usd: float = 0.0
    estimated_savings_usd: float = 0.0
    actual_savings_usd: float = 0.0

    # Order type distribution
    market_orders: int = 0
    limit_orders: int = 0
    post_only_orders: int = 0

    # Accuracy metrics
    cost_estimation_accuracy: float = 0.0   # Actual/Estimated

    # Last update
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================================
# EXECUTION OPTIMIZER
# ============================================================================

class ExecutionOptimizer:
    """
    Order Execution Optimization Engine

    Intelligently selects order types and timing strategies to minimize
    total execution cost while meeting fill requirements. Key capabilities:

    1. Order Type Selection:
       - Market: For urgent orders or tight spreads
       - Limit GTC: For patient execution
       - Limit IOC: For immediate limit attempts
       - Post-Only: For maker fee capture

    2. Cost Analysis:
       - Calculate expected fees (maker vs taker)
       - Estimate slippage costs
       - Factor in spread and market impact
       - Consider opportunity cost for delays

    3. Timing Optimization:
       - Immediate execution for urgent orders
       - Patient execution for cost minimization
       - Opportunistic timing for better prices

    4. Fee Optimization:
       - Track exchange fee structure
       - Recommend maker orders when beneficial
       - Calculate breakeven for limit vs market

    Decision Matrix:
    +-----------+-----------+----------+--------------+----------------+
    | Urgency   | Spread    | Size     | Order Type   | Expected Fill  |
    +-----------+-----------+----------+--------------+----------------+
    | CRITICAL  | Any       | Any      | MARKET       | 100%           |
    | HIGH      | <0.03%    | <$1k     | MARKET       | 100%           |
    | HIGH      | >0.03%    | Any      | LIMIT_IOC    | 70-90%         |
    | MEDIUM    | <0.05%    | <$5k     | LIMIT_GTC    | 80-95%         |
    | MEDIUM    | >0.05%    | >$5k     | LIMIT_GTC    | 60-80%         |
    | LOW       | Any       | Any      | POST_ONLY    | 50-70%         |
    +-----------+-----------+----------+--------------+----------------+

    Usage:
        optimizer = ExecutionOptimizer()

        # Get optimization recommendation
        result = optimizer.optimize_execution(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.5"),
            urgency=ExecutionUrgency.MEDIUM,
            current_price=Decimal("50000"),
            spread_pct=0.0005
        )

        # Use recommended order type
        order_type = result.recommended_order_type
        limit_price = result.recommended_price

        # Get metrics
        metrics = optimizer.get_metrics()
    """

    def __init__(self, config: Optional[ExecutionOptimizerConfig] = None):
        """
        Initialize execution optimizer

        Args:
            config: Optimizer configuration (uses defaults if not provided)
        """
        # Store configuration
        self.config = config or ExecutionOptimizerConfig()

        # Metrics tracking
        self._metrics = ExecutionMetrics()

        # Execution history for feedback loop
        self._execution_history: deque = deque(maxlen=500)

        # Historical fill rates by order type
        self._fill_rate_history: Dict[str, List[float]] = {
            OptimalOrderType.MARKET.value: [],
            OptimalOrderType.LIMIT_GTC.value: [],
            OptimalOrderType.LIMIT_IOC.value: [],
            OptimalOrderType.POST_ONLY.value: []
        }

        # Log initialization
        logger.info(
            f"ExecutionOptimizer initialized: "
            f"maker_fee={self.config.fee_structure.effective_maker_fee:.4%}, "
            f"taker_fee={self.config.fee_structure.effective_taker_fee:.4%}, "
            f"fee_savings={self.config.fee_structure.fee_difference:.4%}"
        )

    # ========================================================================
    # CORE OPTIMIZATION
    # ========================================================================

    def optimize_execution(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        urgency: ExecutionUrgency,
        current_price: Decimal,
        spread_pct: float,
        best_bid: Optional[Decimal] = None,
        best_ask: Optional[Decimal] = None,
        available_liquidity_usd: Optional[float] = None,
        expected_slippage_pct: Optional[float] = None
    ) -> OptimizationResult:
        """
        Optimize order execution strategy

        Analyzes order parameters and market conditions to recommend
        optimal order type, timing, and price. Returns comprehensive
        cost analysis for informed decision making.

        Args:
            symbol: Trading symbol
            side: "BUY" or "SELL"
            quantity: Order quantity
            urgency: Execution urgency level
            current_price: Current market price
            spread_pct: Current bid-ask spread (as decimal)
            best_bid: Best bid price (optional)
            best_ask: Best ask price (optional)
            available_liquidity_usd: Available liquidity (optional)
            expected_slippage_pct: Expected slippage (optional)

        Returns:
            OptimizationResult with complete recommendation
        """
        # Calculate order value
        order_value_usd = float(quantity * current_price)

        # Default values if not provided
        if best_bid is None:
            best_bid = current_price * (1 - Decimal(str(spread_pct / 2)))
        if best_ask is None:
            best_ask = current_price * (1 + Decimal(str(spread_pct / 2)))
        if expected_slippage_pct is None:
            expected_slippage_pct = spread_pct * 50  # Rough estimate: half spread

        # Calculate costs for each order type
        market_cost = self._calculate_cost_breakdown(
            order_value_usd=order_value_usd,
            is_maker=False,
            slippage_pct=expected_slippage_pct,
            spread_pct=spread_pct,
            urgency=urgency
        )

        limit_cost = self._calculate_cost_breakdown(
            order_value_usd=order_value_usd,
            is_maker=True,  # Assume maker if limit fills
            slippage_pct=expected_slippage_pct * 0.3,  # Less slippage with limit
            spread_pct=spread_pct,
            urgency=urgency,
            include_opportunity_cost=True
        )

        post_only_cost = self._calculate_cost_breakdown(
            order_value_usd=order_value_usd,
            is_maker=True,
            slippage_pct=0.0,  # No slippage if post-only fills
            spread_pct=spread_pct,
            urgency=urgency,
            include_opportunity_cost=True,
            opportunity_multiplier=2.0  # Higher opportunity cost
        )

        # Determine optimal order type
        order_type, timing, reasoning = self._select_optimal_order_type(
            urgency=urgency,
            spread_pct=spread_pct,
            order_value_usd=order_value_usd,
            market_cost=market_cost,
            limit_cost=limit_cost,
            post_only_cost=post_only_cost
        )

        # Calculate recommended price
        recommended_price = self._calculate_recommended_price(
            order_type=order_type,
            side=side,
            current_price=current_price,
            best_bid=best_bid,
            best_ask=best_ask,
            spread_pct=spread_pct
        )

        # Select expected cost based on recommendation
        if order_type == OptimalOrderType.MARKET:
            expected_cost = market_cost
        elif order_type == OptimalOrderType.POST_ONLY:
            expected_cost = post_only_cost
        else:
            expected_cost = limit_cost

        # Calculate savings vs market
        savings_usd = market_cost.total_cost_usd - expected_cost.total_cost_usd
        savings_pct = (savings_usd / order_value_usd) * 100 if order_value_usd > 0 else 0

        # Estimate fill probability
        fill_probability = self._estimate_fill_probability(
            order_type=order_type,
            spread_pct=spread_pct,
            order_value_usd=order_value_usd,
            available_liquidity=available_liquidity_usd
        )

        # Estimate time to fill
        time_to_fill = self._estimate_time_to_fill(
            order_type=order_type,
            timing=timing,
            urgency=urgency
        )

        # Calculate confidence
        confidence = self._calculate_confidence(
            urgency=urgency,
            spread_pct=spread_pct,
            fill_probability=fill_probability,
            order_type=order_type
        )

        # Generate warnings
        warnings = self._generate_warnings(
            order_type=order_type,
            urgency=urgency,
            expected_cost=expected_cost,
            fill_probability=fill_probability,
            spread_pct=spread_pct
        )

        # Update metrics
        self._metrics.total_optimizations += 1

        result = OptimizationResult(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_value_usd=order_value_usd,
            urgency=urgency,
            recommended_order_type=order_type,
            recommended_timing=timing,
            recommended_price=recommended_price,
            expected_cost=expected_cost,
            market_order_cost=market_cost,
            limit_order_cost=limit_cost,
            post_only_cost=post_only_cost,
            savings_vs_market_usd=savings_usd,
            savings_vs_market_pct=savings_pct,
            estimated_fill_probability=fill_probability,
            estimated_time_to_fill_seconds=time_to_fill,
            confidence=confidence,
            warnings=warnings,
            reasoning=reasoning
        )

        logger.info(
            f"Execution optimization for {symbol} {side} ${order_value_usd:,.0f}: "
            f"{order_type.value} ({timing.value}) | "
            f"Expected cost: {expected_cost.total_cost_pct:.3f}% | "
            f"Savings vs market: {savings_pct:.3f}%"
        )

        return result

    def _calculate_cost_breakdown(
        self,
        order_value_usd: float,
        is_maker: bool,
        slippage_pct: float,
        spread_pct: float,
        urgency: ExecutionUrgency,
        include_opportunity_cost: bool = False,
        opportunity_multiplier: float = 1.0
    ) -> CostBreakdown:
        """Calculate detailed cost breakdown for an execution scenario"""
        # Fee cost
        if is_maker:
            fee_rate = self.config.fee_structure.effective_maker_fee
        else:
            fee_rate = self.config.fee_structure.effective_taker_fee

        fee_cost_usd = order_value_usd * fee_rate

        # Slippage cost
        slippage_cost_usd = order_value_usd * (slippage_pct / 100)

        # Spread cost (half spread for single-sided execution)
        spread_cost_usd = order_value_usd * (spread_pct / 2)

        # Market impact (for larger orders, estimated as function of size)
        # Simple model: impact = size^0.5 * coefficient
        impact_coefficient = 0.0001  # Calibrated for typical crypto
        market_impact_pct = impact_coefficient * math.sqrt(order_value_usd / 1000)
        market_impact_cost_usd = order_value_usd * market_impact_pct

        # Opportunity cost (for patient execution)
        opportunity_cost_usd = 0.0
        if include_opportunity_cost:
            # Estimate based on average price movement during wait time
            avg_volatility_per_minute = 0.001  # 0.1% per minute typical
            expected_wait_minutes = self._get_expected_wait_time(urgency) / 60
            opportunity_cost_pct = avg_volatility_per_minute * expected_wait_minutes * opportunity_multiplier
            opportunity_cost_usd = order_value_usd * opportunity_cost_pct

        # Total cost
        total_cost_usd = (
            fee_cost_usd +
            slippage_cost_usd +
            spread_cost_usd +
            market_impact_cost_usd +
            opportunity_cost_usd
        )

        # Convert to percentages
        return CostBreakdown(
            fee_cost_usd=fee_cost_usd,
            slippage_cost_usd=slippage_cost_usd,
            spread_cost_usd=spread_cost_usd,
            market_impact_cost_usd=market_impact_cost_usd,
            opportunity_cost_usd=opportunity_cost_usd,
            total_cost_usd=total_cost_usd,
            fee_cost_pct=(fee_cost_usd / order_value_usd * 100) if order_value_usd > 0 else 0,
            slippage_cost_pct=(slippage_cost_usd / order_value_usd * 100) if order_value_usd > 0 else 0,
            spread_cost_pct=(spread_cost_usd / order_value_usd * 100) if order_value_usd > 0 else 0,
            market_impact_cost_pct=(market_impact_cost_usd / order_value_usd * 100) if order_value_usd > 0 else 0,
            opportunity_cost_pct=(opportunity_cost_usd / order_value_usd * 100) if order_value_usd > 0 else 0,
            total_cost_pct=(total_cost_usd / order_value_usd * 100) if order_value_usd > 0 else 0,
            is_maker_fee=is_maker
        )

    def _get_expected_wait_time(self, urgency: ExecutionUrgency) -> float:
        """Get expected wait time based on urgency"""
        base_timeout = self.config.limit_order_timeout_seconds
        multiplier = self.config.urgency_timeout_multipliers.get(
            urgency.value, 1.0
        )
        return base_timeout * multiplier

    def _select_optimal_order_type(
        self,
        urgency: ExecutionUrgency,
        spread_pct: float,
        order_value_usd: float,
        market_cost: CostBreakdown,
        limit_cost: CostBreakdown,
        post_only_cost: CostBreakdown
    ) -> Tuple[OptimalOrderType, TimingStrategy, str]:
        """
        Select optimal order type based on conditions

        Returns tuple of (order_type, timing_strategy, reasoning)
        """
        reasoning_parts = []

        # Rule 1: CRITICAL urgency always uses MARKET
        if urgency == ExecutionUrgency.CRITICAL:
            reasoning_parts.append("CRITICAL urgency requires immediate MARKET execution")
            return OptimalOrderType.MARKET, TimingStrategy.IMMEDIATE, " | ".join(reasoning_parts)

        # Rule 2: HIGH urgency with tight spread uses MARKET
        if urgency == ExecutionUrgency.HIGH:
            if spread_pct < self.config.market_order_max_spread:
                reasoning_parts.append(
                    f"HIGH urgency + tight spread ({spread_pct:.3%}) -> MARKET"
                )
                return OptimalOrderType.MARKET, TimingStrategy.IMMEDIATE, " | ".join(reasoning_parts)
            else:
                reasoning_parts.append(
                    f"HIGH urgency + wider spread ({spread_pct:.3%}) -> LIMIT_IOC for partial savings"
                )
                return OptimalOrderType.LIMIT_IOC, TimingStrategy.IMMEDIATE, " | ".join(reasoning_parts)

        # Rule 3: LOW urgency uses POST_ONLY for fee capture
        if urgency == ExecutionUrgency.LOW:
            # Check if fee savings justify the fill risk
            fee_savings = market_cost.fee_cost_usd - post_only_cost.fee_cost_usd
            if fee_savings > 1.0:  # At least $1 savings
                reasoning_parts.append(
                    f"LOW urgency + ${fee_savings:.2f} fee savings -> POST_ONLY"
                )
                return OptimalOrderType.POST_ONLY, TimingStrategy.PATIENT, " | ".join(reasoning_parts)

        # Rule 4: MEDIUM urgency - compare costs
        # If market is cheaper (including opportunity cost), use market
        if market_cost.total_cost_usd < limit_cost.total_cost_usd:
            reasoning_parts.append(
                f"MEDIUM urgency: Market cost (${market_cost.total_cost_usd:.2f}) < "
                f"Limit cost (${limit_cost.total_cost_usd:.2f}) -> MARKET"
            )
            return OptimalOrderType.MARKET, TimingStrategy.IMMEDIATE, " | ".join(reasoning_parts)

        # Rule 5: Default to LIMIT_GTC for cost savings
        savings = market_cost.total_cost_usd - limit_cost.total_cost_usd
        reasoning_parts.append(
            f"LIMIT_GTC saves ${savings:.2f} vs market ({limit_cost.total_cost_pct:.3f}% vs {market_cost.total_cost_pct:.3f}%)"
        )

        # Select timing based on spread
        if spread_pct < self.config.market_order_max_spread:
            timing = TimingStrategy.OPPORTUNISTIC
        else:
            timing = TimingStrategy.PATIENT

        return OptimalOrderType.LIMIT_GTC, timing, " | ".join(reasoning_parts)

    def _calculate_recommended_price(
        self,
        order_type: OptimalOrderType,
        side: str,
        current_price: Decimal,
        best_bid: Decimal,
        best_ask: Decimal,
        spread_pct: float
    ) -> Optional[Decimal]:
        """Calculate recommended limit price for order"""
        if order_type == OptimalOrderType.MARKET:
            return None  # No price needed for market orders

        mid_price = (best_bid + best_ask) / 2

        if order_type == OptimalOrderType.POST_ONLY:
            # Post at best bid (for buys) or best ask (for sells)
            # to ensure maker status
            if side.upper() == "BUY":
                return best_bid
            else:
                return best_ask

        # For limit orders, set price at mid with small offset
        offset = Decimal(str(spread_pct * 0.25))  # 25% of spread

        if side.upper() == "BUY":
            # Buy slightly below mid
            return mid_price * (1 - offset)
        else:
            # Sell slightly above mid
            return mid_price * (1 + offset)

    def _estimate_fill_probability(
        self,
        order_type: OptimalOrderType,
        spread_pct: float,
        order_value_usd: float,
        available_liquidity: Optional[float]
    ) -> float:
        """Estimate fill probability for order type"""
        # Base fill rates by order type
        base_rates = {
            OptimalOrderType.MARKET: 1.0,       # Always fills
            OptimalOrderType.LIMIT_IOC: 0.85,   # Usually fills
            OptimalOrderType.LIMIT_GTC: 0.75,   # Often fills
            OptimalOrderType.LIMIT_FOK: 0.60,   # Less likely
            OptimalOrderType.POST_ONLY: 0.55    # May not fill
        }

        base_rate = base_rates.get(order_type, 0.7)

        # Use historical fill rates if available
        history = self._fill_rate_history.get(order_type.value, [])
        if len(history) >= 10:
            historical_rate = statistics.mean(history[-20:])
            base_rate = (base_rate + historical_rate) / 2

        # Adjust for spread (tighter spread = higher fill prob)
        if spread_pct < 0.0003:  # Very tight
            spread_adjustment = 1.1
        elif spread_pct < 0.0010:  # Normal
            spread_adjustment = 1.0
        elif spread_pct < 0.0020:  # Wide
            spread_adjustment = 0.9
        else:  # Very wide
            spread_adjustment = 0.8

        # Adjust for order size relative to liquidity
        size_adjustment = 1.0
        if available_liquidity:
            size_ratio = order_value_usd / available_liquidity
            if size_ratio > 0.1:  # Large order
                size_adjustment = 0.8
            elif size_ratio > 0.05:
                size_adjustment = 0.9

        fill_probability = base_rate * spread_adjustment * size_adjustment
        return min(1.0, max(0.1, fill_probability))

    def _estimate_time_to_fill(
        self,
        order_type: OptimalOrderType,
        timing: TimingStrategy,
        urgency: ExecutionUrgency
    ) -> float:
        """Estimate time to fill in seconds"""
        # Base times by order type
        base_times = {
            OptimalOrderType.MARKET: 1.0,        # Instant
            OptimalOrderType.LIMIT_IOC: 2.0,     # Very fast
            OptimalOrderType.LIMIT_GTC: 30.0,    # May wait
            OptimalOrderType.LIMIT_FOK: 1.0,     # Instant (fills or cancels)
            OptimalOrderType.POST_ONLY: 60.0     # Patient
        }

        base_time = base_times.get(order_type, 30.0)

        # Adjust for timing strategy
        timing_multipliers = {
            TimingStrategy.IMMEDIATE: 1.0,
            TimingStrategy.OPPORTUNISTIC: 1.5,
            TimingStrategy.PATIENT: 3.0,
            TimingStrategy.SCHEDULED: 1.0
        }

        multiplier = timing_multipliers.get(timing, 1.0)

        # Adjust for urgency
        urgency_multipliers = {
            ExecutionUrgency.CRITICAL: 0.5,
            ExecutionUrgency.HIGH: 0.75,
            ExecutionUrgency.MEDIUM: 1.0,
            ExecutionUrgency.LOW: 2.0
        }

        urgency_mult = urgency_multipliers.get(urgency, 1.0)

        return base_time * multiplier * urgency_mult

    def _calculate_confidence(
        self,
        urgency: ExecutionUrgency,
        spread_pct: float,
        fill_probability: float,
        order_type: OptimalOrderType
    ) -> float:
        """Calculate confidence in recommendation"""
        # Base confidence
        confidence = 0.7

        # Higher confidence for CRITICAL urgency (clear choice)
        if urgency == ExecutionUrgency.CRITICAL:
            confidence = 0.95

        # Higher confidence for tight spreads (clear conditions)
        if spread_pct < 0.0003:
            confidence += 0.1

        # Lower confidence for low fill probability
        if fill_probability < 0.6:
            confidence -= 0.1

        # Higher confidence for simpler order types
        if order_type == OptimalOrderType.MARKET:
            confidence += 0.1

        return min(1.0, max(0.4, confidence))

    def _generate_warnings(
        self,
        order_type: OptimalOrderType,
        urgency: ExecutionUrgency,
        expected_cost: CostBreakdown,
        fill_probability: float,
        spread_pct: float
    ) -> List[str]:
        """Generate warnings for the optimization result"""
        warnings = []

        # Cost warning
        if expected_cost.total_cost_pct > self.config.cost_warning_threshold_pct:
            warnings.append(
                f"High execution cost: {expected_cost.total_cost_pct:.3f}% "
                f"(threshold: {self.config.cost_warning_threshold_pct:.3f}%)"
            )

        # Fill probability warning
        if fill_probability < self.config.min_fill_probability:
            warnings.append(
                f"Low fill probability: {fill_probability:.1%} "
                f"(minimum: {self.config.min_fill_probability:.1%})"
            )

        # Spread warning
        if spread_pct > self.config.limit_preferred_min_spread * 2:
            warnings.append(f"Wide spread: {spread_pct:.3%} - consider waiting for better conditions")

        # Urgency mismatch warning
        if urgency == ExecutionUrgency.LOW and order_type == OptimalOrderType.MARKET:
            warnings.append("Using MARKET order with LOW urgency - consider LIMIT for fee savings")

        return warnings

    # ========================================================================
    # FEEDBACK AND METRICS
    # ========================================================================

    def record_execution_result(
        self,
        optimization_result: OptimizationResult,
        actual_fill_rate: float,
        actual_cost_usd: float,
        execution_time_seconds: float
    ):
        """
        Record actual execution result for feedback loop

        Improves future optimizations by tracking:
        - Actual vs predicted fill rates
        - Actual vs predicted costs
        - Order type effectiveness
        """
        # Record fill rate
        order_type = optimization_result.recommended_order_type.value
        if order_type in self._fill_rate_history:
            self._fill_rate_history[order_type].append(actual_fill_rate)
            # Keep only recent history
            if len(self._fill_rate_history[order_type]) > 100:
                self._fill_rate_history[order_type] = \
                    self._fill_rate_history[order_type][-100:]

        # Update metrics
        self._metrics.orders_executed += 1

        if actual_fill_rate > 0:
            # Update average fill rate
            prev_total = self._metrics.avg_fill_rate * (self._metrics.orders_executed - 1)
            self._metrics.avg_fill_rate = (prev_total + actual_fill_rate) / self._metrics.orders_executed

        # Track costs
        self._metrics.total_fees_paid_usd += actual_cost_usd

        # Track order type distribution
        if optimization_result.recommended_order_type == OptimalOrderType.MARKET:
            self._metrics.market_orders += 1
        elif optimization_result.recommended_order_type == OptimalOrderType.POST_ONLY:
            self._metrics.post_only_orders += 1
        else:
            self._metrics.limit_orders += 1

        # Calculate actual vs estimated savings
        market_cost = optimization_result.market_order_cost.total_cost_usd
        actual_savings = market_cost - actual_cost_usd
        self._metrics.actual_savings_usd += actual_savings
        self._metrics.estimated_savings_usd += optimization_result.savings_vs_market_usd

        # Update estimation accuracy
        if optimization_result.expected_cost.total_cost_usd > 0:
            accuracy = actual_cost_usd / optimization_result.expected_cost.total_cost_usd
            prev_accuracy = self._metrics.cost_estimation_accuracy
            self._metrics.cost_estimation_accuracy = (prev_accuracy + accuracy) / 2

        self._metrics.last_updated = datetime.now(timezone.utc)

        logger.debug(
            f"Execution recorded: {order_type} | "
            f"Fill: {actual_fill_rate:.1%} | "
            f"Cost: ${actual_cost_usd:.2f} | "
            f"Savings: ${actual_savings:.2f}"
        )

    def get_metrics(self) -> ExecutionMetrics:
        """Get current optimizer metrics"""
        # Update order type fill rates
        for order_type in [OptimalOrderType.LIMIT_GTC, OptimalOrderType.POST_ONLY]:
            history = self._fill_rate_history.get(order_type.value, [])
            if history:
                if order_type == OptimalOrderType.LIMIT_GTC:
                    self._metrics.limit_order_fill_rate = statistics.mean(history[-20:])
                elif order_type == OptimalOrderType.POST_ONLY:
                    self._metrics.post_only_fill_rate = statistics.mean(history[-20:])

        return self._metrics

    def get_fee_comparison(self, order_value_usd: float) -> Dict[str, float]:
        """
        Get fee comparison for different order types

        Useful for UI display showing potential savings
        """
        maker_fee = order_value_usd * self.config.fee_structure.effective_maker_fee
        taker_fee = order_value_usd * self.config.fee_structure.effective_taker_fee
        savings = taker_fee - maker_fee

        return {
            "order_value_usd": order_value_usd,
            "maker_fee_usd": maker_fee,
            "taker_fee_usd": taker_fee,
            "potential_savings_usd": savings,
            "maker_fee_pct": self.config.fee_structure.effective_maker_fee * 100,
            "taker_fee_pct": self.config.fee_structure.effective_taker_fee * 100,
            "savings_pct": self.config.fee_structure.fee_difference * 100
        }

    def get_status(self) -> Dict:
        """Get optimizer status summary"""
        return {
            "config": {
                "maker_fee": f"{self.config.fee_structure.effective_maker_fee:.4%}",
                "taker_fee": f"{self.config.fee_structure.effective_taker_fee:.4%}",
                "fee_difference": f"{self.config.fee_structure.fee_difference:.4%}",
                "market_order_max_spread": f"{self.config.market_order_max_spread:.4%}",
                "limit_timeout_seconds": self.config.limit_order_timeout_seconds
            },
            "metrics": {
                "total_optimizations": self._metrics.total_optimizations,
                "orders_executed": self._metrics.orders_executed,
                "avg_fill_rate": f"{self._metrics.avg_fill_rate:.1%}",
                "limit_fill_rate": f"{self._metrics.limit_order_fill_rate:.1%}",
                "post_only_fill_rate": f"{self._metrics.post_only_fill_rate:.1%}",
                "total_fees_paid": f"${self._metrics.total_fees_paid_usd:,.2f}",
                "estimated_savings": f"${self._metrics.estimated_savings_usd:,.2f}",
                "actual_savings": f"${self._metrics.actual_savings_usd:,.2f}",
                "cost_estimation_accuracy": f"{self._metrics.cost_estimation_accuracy:.1%}"
            },
            "order_distribution": {
                "market": self._metrics.market_orders,
                "limit": self._metrics.limit_orders,
                "post_only": self._metrics.post_only_orders
            },
            "last_updated": self._metrics.last_updated.isoformat()
        }


# ============================================================================
# GLOBAL INSTANCE MANAGEMENT
# ============================================================================

# Global optimizer instance
_execution_optimizer: Optional[ExecutionOptimizer] = None


def get_execution_optimizer(
    config: Optional[ExecutionOptimizerConfig] = None
) -> ExecutionOptimizer:
    """
    Get or create global execution optimizer instance

    Args:
        config: Optional configuration (only used if creating new instance)

    Returns:
        ExecutionOptimizer instance
    """
    global _execution_optimizer
    if _execution_optimizer is None:
        _execution_optimizer = ExecutionOptimizer(config)
    return _execution_optimizer


def reset_execution_optimizer():
    """Reset global execution optimizer instance"""
    global _execution_optimizer
    _execution_optimizer = None
    logger.info("Execution optimizer instance reset")
