"""
Orderbook Analyzer - Real-time Order Book Analysis for Execution Optimization
Phase 4.1: Smart Order Routing - Orderbook Analysis Component

Purpose:
- Analyze real-time order book depth and liquidity
- Calculate available liquidity at various price levels
- Estimate market impact for given order sizes
- Detect liquidity imbalances indicating buy/sell pressure
- Find optimal limit price for target fill probability
- Provide liquidity scoring for execution decisions

Research Sources:
- Market Microstructure Theory (Kyle, 1985)
- Order Book Dynamics (Cont, Stoikov & Talreja, 2010)
- Crypto Market Liquidity Analysis (Karolyi & Amihud studies)
- Optimal Execution in Limit Order Books (Obizhaeva & Wang, 2013)

Decision Matrix:
+------------------+------------------+------------------+------------------+
| Liquidity Score  | Spread           | Recommendation   | Max Order Size   |
+------------------+------------------+------------------+------------------+
| HIGH (>80)       | <0.05%           | Market OK        | Up to $50k       |
| MEDIUM (50-80)   | 0.05%-0.15%      | Limit preferred  | Up to $10k       |
| LOW (20-50)      | 0.15%-0.30%      | Limit only       | Up to $5k        |
| VERY_LOW (<20)   | >0.30%           | Avoid/Split      | <$1k per chunk   |
+------------------+------------------+------------------+------------------+

Created: 2025-12-11
Author: Backend Developer Agent
"""

import logging
import math
from decimal import Decimal
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from enum import Enum
from collections import deque
import statistics

# Configure logging for orderbook analysis
logger = logging.getLogger(__name__)


# ============================================================================
# ENUMERATIONS
# ============================================================================

class LiquidityLevel(str, Enum):
    """
    Order book liquidity classification levels

    Based on research: Crypto order books show significant variation
    in liquidity. Classification helps determine execution strategy.

    HIGH: Sufficient depth for large orders with minimal impact
    MEDIUM: Adequate for moderate orders, some slippage expected
    LOW: Thin book, significant slippage likely for any size
    VERY_LOW: Danger zone - high impact, consider avoiding
    """
    HIGH = "high"           # Deep book, tight spread
    MEDIUM = "medium"       # Adequate depth, moderate spread
    LOW = "low"             # Thin book, wide spread
    VERY_LOW = "very_low"   # Illiquid, high risk


class OrderBookState(str, Enum):
    """
    Order book state classification for market dynamics

    Research shows order book state affects optimal execution:
    - BALANCED: Symmetric, stable conditions
    - BID_HEAVY: Buy pressure, favorable for sells
    - ASK_HEAVY: Sell pressure, favorable for buys
    - DEPLETED: Thin book, high impact orders
    """
    BALANCED = "balanced"       # Symmetric order book
    BID_HEAVY = "bid_heavy"     # More bids than asks (buy pressure)
    ASK_HEAVY = "ask_heavy"     # More asks than bids (sell pressure)
    DEPLETED = "depleted"       # Low liquidity on both sides


class SpreadCategory(str, Enum):
    """
    Bid-ask spread classification

    Research-backed thresholds for crypto markets:
    - Major pairs (BTC, ETH): Typically <0.05%
    - Mid-cap alts: 0.05%-0.15%
    - Low-cap alts: >0.15%
    """
    TIGHT = "tight"           # <0.05% - Excellent execution
    NORMAL = "normal"         # 0.05%-0.10% - Good execution
    WIDE = "wide"             # 0.10%-0.20% - Consider limit orders
    VERY_WIDE = "very_wide"   # >0.20% - High cost execution


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class OrderBookConfig:
    """
    Configuration for orderbook analysis

    Thresholds calibrated for typical crypto market conditions:
    - depth_levels: Number of price levels to analyze
    - min_liquidity_usd: Minimum depth to consider liquid
    - imbalance_threshold: Ratio indicating significant imbalance
    """
    # Analysis depth
    depth_levels: int = 25                    # Number of levels to analyze

    # Liquidity thresholds (in USD)
    high_liquidity_threshold: float = 100000.0    # $100k+ = high liquidity
    medium_liquidity_threshold: float = 25000.0   # $25k+ = medium liquidity
    low_liquidity_threshold: float = 5000.0       # $5k+ = low liquidity

    # Spread thresholds (as decimal)
    tight_spread_threshold: float = 0.0005       # 0.05%
    normal_spread_threshold: float = 0.0010      # 0.10%
    wide_spread_threshold: float = 0.0020        # 0.20%

    # Imbalance detection
    imbalance_threshold: float = 1.5             # 1.5x difference = imbalanced
    strong_imbalance_threshold: float = 2.5      # 2.5x = strong imbalance

    # Price impact estimation
    impact_depth_pct: float = 0.01               # Analyze 1% from mid
    impact_warning_pct: float = 0.10             # Warn if >0.1% impact

    # Cache settings
    cache_ttl_seconds: int = 3                   # Order book cache TTL


@dataclass
class PriceLevel:
    """
    Single price level in order book with computed metrics

    Attributes:
        price: Price at this level
        quantity: Total quantity available
        value_usd: Dollar value of liquidity
        cumulative_qty: Running total quantity from best price
        cumulative_usd: Running total USD from best price
        distance_from_mid_pct: Percentage distance from mid price
    """
    price: Decimal
    quantity: Decimal
    value_usd: float
    cumulative_qty: Decimal = Decimal("0")
    cumulative_usd: float = 0.0
    distance_from_mid_pct: float = 0.0
    order_count: int = 1


@dataclass
class DepthAnalysis:
    """
    Analysis of order book depth at specific distance from mid

    Provides cumulative liquidity metrics:
    - bid_depth_usd/ask_depth_usd: Total liquidity available
    - avg_bid_price/avg_ask_price: VWAP if filled to this depth
    - levels_consumed: Number of price levels needed
    """
    distance_pct: float              # Distance from mid (0.1%, 0.5%, 1%, etc.)

    # Bid side
    bid_depth_usd: float             # Total bid liquidity
    bid_depth_qty: Decimal           # Total bid quantity
    avg_bid_price: Decimal           # VWAP for bids at this depth
    bid_levels_consumed: int         # Number of bid levels

    # Ask side
    ask_depth_usd: float             # Total ask liquidity
    ask_depth_qty: Decimal           # Total ask quantity
    avg_ask_price: Decimal           # VWAP for asks at this depth
    ask_levels_consumed: int         # Number of ask levels

    # Combined
    total_depth_usd: float           # Bid + Ask depth
    imbalance_ratio: float           # Bid/Ask ratio


@dataclass
class MarketImpactEstimate:
    """
    Estimated market impact for a potential order

    Calculates expected price movement from executing order:
    - temporary_impact_pct: Immediate price movement
    - permanent_impact_pct: Lasting price change
    - total_cost_pct: Combined execution cost
    - execution_price: Expected fill price
    """
    symbol: str
    side: str                        # BUY or SELL
    quantity: Decimal
    order_value_usd: float

    # Impact estimates
    temporary_impact_pct: float      # Immediate price movement
    permanent_impact_pct: float      # Lasting information impact
    total_impact_pct: float          # Combined impact

    # Execution details
    mid_price: Decimal
    execution_price: Decimal         # Expected average fill price
    worst_price: Decimal             # Price at full fill
    price_levels_consumed: int       # Number of levels consumed

    # Cost analysis
    slippage_cost_usd: float         # Dollar cost of slippage
    spread_cost_usd: float           # Half-spread cost
    total_cost_usd: float            # Total execution cost

    # Risk assessment
    is_acceptable: bool              # Within normal parameters
    warning_message: Optional[str] = None

    # Timestamp
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LiquidityReport:
    """
    Comprehensive liquidity assessment for a symbol

    Aggregates all order book metrics for decision making:
    - liquidity_level: Overall classification
    - spread_category: Spread quality assessment
    - book_state: Buy/sell pressure indication
    - optimal_order_size: Recommended max order
    """
    symbol: str
    timestamp: datetime

    # Price metrics
    best_bid: Decimal
    best_ask: Decimal
    mid_price: Decimal
    spread_absolute: Decimal
    spread_pct: float
    spread_category: SpreadCategory

    # Liquidity metrics
    liquidity_level: LiquidityLevel
    liquidity_score: float           # 0-100 composite score
    total_bid_depth_usd: float
    total_ask_depth_usd: float
    total_depth_usd: float

    # Order book state
    book_state: OrderBookState
    imbalance_ratio: float           # bid_depth / ask_depth

    # Depth at various levels
    depth_at_01pct: DepthAnalysis    # Depth within 0.1% of mid
    depth_at_05pct: DepthAnalysis    # Depth within 0.5% of mid
    depth_at_1pct: DepthAnalysis     # Depth within 1% of mid

    # Recommendations
    recommended_max_market_order_usd: float
    recommended_max_limit_order_usd: float
    optimal_limit_offset_pct: float  # Recommended limit price offset

    # Warnings
    warnings: List[str] = field(default_factory=list)


@dataclass
class OptimalLimitPrice:
    """
    Recommended limit price for target fill probability

    Calculates optimal limit price considering:
    - Current order book state
    - Historical fill rates at various offsets
    - Target fill probability
    - Time-to-fill estimate
    """
    symbol: str
    side: str
    quantity: Decimal

    # Prices
    current_mid: Decimal
    best_price: Decimal              # Best bid (sell) or ask (buy)
    recommended_price: Decimal       # Optimal limit price
    aggressive_price: Decimal        # Higher fill probability
    passive_price: Decimal           # Lower cost, lower fill

    # Analysis
    offset_from_mid_pct: float
    estimated_fill_probability: float   # 0-1
    estimated_time_to_fill_seconds: float

    # Cost comparison
    expected_cost_vs_market_pct: float  # Savings vs market order
    expected_cost_usd: float

    # Risk factors
    fill_risk: str                   # LOW/MEDIUM/HIGH

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================================
# ORDERBOOK ANALYZER
# ============================================================================

class OrderbookAnalyzer:
    """
    Real-time Order Book Analysis Engine

    Provides comprehensive analysis of order book data for optimal
    execution decisions. Key capabilities:

    1. Liquidity Assessment:
       - Calculate available depth at various price levels
       - Score overall liquidity (0-100)
       - Classify liquidity level (HIGH/MEDIUM/LOW/VERY_LOW)

    2. Market Impact Estimation:
       - Estimate price impact for given order size
       - Calculate expected execution cost
       - Predict price levels consumed

    3. Optimal Price Discovery:
       - Find best limit price for fill probability
       - Calculate cost savings vs market orders
       - Estimate time to fill

    4. Order Book State Analysis:
       - Detect buy/sell pressure from imbalance
       - Track spread dynamics
       - Identify liquidity changes

    Usage:
        analyzer = OrderbookAnalyzer()

        # Analyze order book
        report = analyzer.analyze_liquidity(
            symbol="BTCUSDT",
            bids=[["50000", "1.5"], ["49990", "2.0"], ...],
            asks=[["50010", "1.2"], ["50020", "1.8"], ...]
        )

        # Estimate market impact
        impact = analyzer.estimate_market_impact(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.5"),
            bids=bids,
            asks=asks
        )

        # Find optimal limit price
        optimal = analyzer.find_optimal_limit_price(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.5"),
            target_fill_probability=0.8
        )
    """

    def __init__(self, config: Optional[OrderBookConfig] = None):
        """
        Initialize orderbook analyzer

        Args:
            config: Analysis configuration (uses defaults if not provided)
        """
        # Store configuration
        self.config = config or OrderBookConfig()

        # Processed order book cache
        self._orderbook_cache: Dict[str, LiquidityReport] = {}
        self._cache_timestamps: Dict[str, datetime] = {}

        # Historical spread tracking for analysis
        self._spread_history: Dict[str, deque] = {}  # symbol -> spreads

        # Fill rate tracking for optimal price calculation
        self._fill_rate_history: Dict[str, List[Dict]] = {}

        # Log initialization
        logger.info(
            f"OrderbookAnalyzer initialized: "
            f"depth_levels={self.config.depth_levels}, "
            f"high_liquidity=${self.config.high_liquidity_threshold:,.0f}"
        )

    # ========================================================================
    # CORE ANALYSIS
    # ========================================================================

    def analyze_liquidity(
        self,
        symbol: str,
        bids: List[List[str]],
        asks: List[List[str]],
        current_price: Optional[Decimal] = None
    ) -> LiquidityReport:
        """
        Comprehensive liquidity analysis of order book

        Performs full analysis including:
        - Spread calculation and categorization
        - Depth analysis at multiple price levels
        - Liquidity scoring and classification
        - Imbalance detection
        - Order size recommendations

        Args:
            symbol: Trading symbol
            bids: Bid levels [[price, qty], ...]
            asks: Ask levels [[price, qty], ...]
            current_price: Optional current market price

        Returns:
            LiquidityReport with comprehensive analysis
        """
        timestamp = datetime.now(timezone.utc)
        warnings = []

        # Handle empty order books
        if not bids or not asks:
            logger.warning(f"Empty order book for {symbol}")
            return self._create_empty_report(symbol, timestamp, current_price)

        # Parse best bid and ask
        best_bid = Decimal(str(bids[0][0]))
        best_ask = Decimal(str(asks[0][0]))
        mid_price = (best_bid + best_ask) / 2
        spread_absolute = best_ask - best_bid
        spread_pct = float(spread_absolute / mid_price) if mid_price > 0 else 0.0

        # Categorize spread
        spread_category = self._categorize_spread(spread_pct)

        # Process all price levels
        bid_levels = self._process_levels(bids, mid_price, is_bid=True)
        ask_levels = self._process_levels(asks, mid_price, is_bid=False)

        # Calculate total depths
        total_bid_depth = sum(level.value_usd for level in bid_levels)
        total_ask_depth = sum(level.value_usd for level in ask_levels)
        total_depth = total_bid_depth + total_ask_depth

        # Calculate depth at various distances
        depth_at_01pct = self._calculate_depth_at_distance(
            bid_levels, ask_levels, mid_price, 0.001
        )
        depth_at_05pct = self._calculate_depth_at_distance(
            bid_levels, ask_levels, mid_price, 0.005
        )
        depth_at_1pct = self._calculate_depth_at_distance(
            bid_levels, ask_levels, mid_price, 0.01
        )

        # Calculate imbalance
        imbalance_ratio = total_bid_depth / total_ask_depth if total_ask_depth > 0 else 1.0

        # Determine book state
        book_state = self._classify_book_state(imbalance_ratio, total_depth)

        # Calculate liquidity score (0-100)
        liquidity_score = self._calculate_liquidity_score(
            spread_pct=spread_pct,
            total_depth_usd=total_depth,
            depth_at_01pct=depth_at_01pct.total_depth_usd,
            imbalance_ratio=imbalance_ratio
        )

        # Classify liquidity level
        liquidity_level = self._classify_liquidity(liquidity_score)

        # Calculate recommended order sizes
        max_market_order = self._calculate_max_market_order(
            liquidity_level, depth_at_01pct.total_depth_usd, spread_pct
        )
        max_limit_order = self._calculate_max_limit_order(
            liquidity_level, total_depth, spread_pct
        )

        # Calculate optimal limit offset
        optimal_offset = self._calculate_optimal_limit_offset(
            spread_pct, liquidity_level, imbalance_ratio
        )

        # Generate warnings
        if liquidity_level == LiquidityLevel.VERY_LOW:
            warnings.append(f"CRITICAL: Very low liquidity (${total_depth:,.0f} total depth)")
        elif liquidity_level == LiquidityLevel.LOW:
            warnings.append(f"WARNING: Low liquidity (${total_depth:,.0f} total depth)")

        if spread_category == SpreadCategory.VERY_WIDE:
            warnings.append(f"Wide spread: {spread_pct:.3%} - high execution cost")

        if abs(imbalance_ratio - 1.0) > self.config.strong_imbalance_threshold - 1:
            direction = "buy pressure" if imbalance_ratio > 1 else "sell pressure"
            warnings.append(f"Strong order imbalance: {imbalance_ratio:.2f}x ({direction})")

        # Track spread history
        if symbol not in self._spread_history:
            self._spread_history[symbol] = deque(maxlen=100)
        self._spread_history[symbol].append(spread_pct)

        # Create report
        report = LiquidityReport(
            symbol=symbol,
            timestamp=timestamp,
            best_bid=best_bid,
            best_ask=best_ask,
            mid_price=mid_price,
            spread_absolute=spread_absolute,
            spread_pct=spread_pct,
            spread_category=spread_category,
            liquidity_level=liquidity_level,
            liquidity_score=liquidity_score,
            total_bid_depth_usd=total_bid_depth,
            total_ask_depth_usd=total_ask_depth,
            total_depth_usd=total_depth,
            book_state=book_state,
            imbalance_ratio=imbalance_ratio,
            depth_at_01pct=depth_at_01pct,
            depth_at_05pct=depth_at_05pct,
            depth_at_1pct=depth_at_1pct,
            recommended_max_market_order_usd=max_market_order,
            recommended_max_limit_order_usd=max_limit_order,
            optimal_limit_offset_pct=optimal_offset,
            warnings=warnings
        )

        # Cache the report
        self._orderbook_cache[symbol] = report
        self._cache_timestamps[symbol] = timestamp

        logger.debug(
            f"Liquidity analysis for {symbol}: "
            f"score={liquidity_score:.1f}, level={liquidity_level.value}, "
            f"spread={spread_pct:.4%}, depth=${total_depth:,.0f}"
        )

        return report

    def _process_levels(
        self,
        levels: List[List[str]],
        mid_price: Decimal,
        is_bid: bool
    ) -> List[PriceLevel]:
        """Process raw order book levels into structured data"""
        processed = []
        cumulative_qty = Decimal("0")
        cumulative_usd = 0.0

        for i, level in enumerate(levels[:self.config.depth_levels]):
            price = Decimal(str(level[0]))
            qty = Decimal(str(level[1]))
            value_usd = float(price * qty)

            cumulative_qty += qty
            cumulative_usd += value_usd

            # Calculate distance from mid
            if is_bid:
                distance_pct = float((mid_price - price) / mid_price)
            else:
                distance_pct = float((price - mid_price) / mid_price)

            processed.append(PriceLevel(
                price=price,
                quantity=qty,
                value_usd=value_usd,
                cumulative_qty=cumulative_qty,
                cumulative_usd=cumulative_usd,
                distance_from_mid_pct=distance_pct
            ))

        return processed

    def _calculate_depth_at_distance(
        self,
        bid_levels: List[PriceLevel],
        ask_levels: List[PriceLevel],
        mid_price: Decimal,
        distance_pct: float
    ) -> DepthAnalysis:
        """Calculate cumulative depth within specified distance from mid"""
        # Aggregate bids within distance
        bid_depth_usd = 0.0
        bid_depth_qty = Decimal("0")
        bid_value_sum = Decimal("0")
        bid_levels_count = 0

        for level in bid_levels:
            if level.distance_from_mid_pct <= distance_pct:
                bid_depth_usd += level.value_usd
                bid_depth_qty += level.quantity
                bid_value_sum += level.price * level.quantity
                bid_levels_count += 1

        avg_bid = bid_value_sum / bid_depth_qty if bid_depth_qty > 0 else mid_price

        # Aggregate asks within distance
        ask_depth_usd = 0.0
        ask_depth_qty = Decimal("0")
        ask_value_sum = Decimal("0")
        ask_levels_count = 0

        for level in ask_levels:
            if level.distance_from_mid_pct <= distance_pct:
                ask_depth_usd += level.value_usd
                ask_depth_qty += level.quantity
                ask_value_sum += level.price * level.quantity
                ask_levels_count += 1

        avg_ask = ask_value_sum / ask_depth_qty if ask_depth_qty > 0 else mid_price

        # Calculate imbalance
        imbalance = bid_depth_usd / ask_depth_usd if ask_depth_usd > 0 else 1.0

        return DepthAnalysis(
            distance_pct=distance_pct,
            bid_depth_usd=bid_depth_usd,
            bid_depth_qty=bid_depth_qty,
            avg_bid_price=avg_bid,
            bid_levels_consumed=bid_levels_count,
            ask_depth_usd=ask_depth_usd,
            ask_depth_qty=ask_depth_qty,
            avg_ask_price=avg_ask,
            ask_levels_consumed=ask_levels_count,
            total_depth_usd=bid_depth_usd + ask_depth_usd,
            imbalance_ratio=imbalance
        )

    def _categorize_spread(self, spread_pct: float) -> SpreadCategory:
        """Categorize spread based on configured thresholds"""
        if spread_pct < self.config.tight_spread_threshold:
            return SpreadCategory.TIGHT
        elif spread_pct < self.config.normal_spread_threshold:
            return SpreadCategory.NORMAL
        elif spread_pct < self.config.wide_spread_threshold:
            return SpreadCategory.WIDE
        else:
            return SpreadCategory.VERY_WIDE

    def _classify_book_state(
        self,
        imbalance_ratio: float,
        total_depth: float
    ) -> OrderBookState:
        """Classify order book state based on imbalance and depth"""
        if total_depth < self.config.low_liquidity_threshold:
            return OrderBookState.DEPLETED

        if imbalance_ratio > self.config.imbalance_threshold:
            return OrderBookState.BID_HEAVY
        elif imbalance_ratio < 1 / self.config.imbalance_threshold:
            return OrderBookState.ASK_HEAVY
        else:
            return OrderBookState.BALANCED

    def _calculate_liquidity_score(
        self,
        spread_pct: float,
        total_depth_usd: float,
        depth_at_01pct: float,
        imbalance_ratio: float
    ) -> float:
        """
        Calculate composite liquidity score (0-100)

        Scoring components:
        - Spread score (0-40): Tighter = better
        - Depth score (0-40): More depth = better
        - Imbalance penalty (0-20): More balanced = better
        """
        # Spread score (40 points max)
        # 0.01% spread = 40 points, 0.5% spread = 0 points
        spread_score = max(0, min(40, 40 * (1 - spread_pct / 0.005)))

        # Depth score (40 points max)
        # $500k+ = 40 points, scaling down logarithmically
        if total_depth_usd > 0:
            depth_score = min(40, 10 * math.log10(total_depth_usd / 1000 + 1))
        else:
            depth_score = 0

        # Imbalance penalty (20 points deducted for severe imbalance)
        imbalance_deviation = abs(imbalance_ratio - 1.0)
        imbalance_score = max(0, 20 - imbalance_deviation * 10)

        total_score = spread_score + depth_score + imbalance_score

        return min(100, max(0, total_score))

    def _classify_liquidity(self, score: float) -> LiquidityLevel:
        """Classify liquidity level based on score"""
        if score >= 80:
            return LiquidityLevel.HIGH
        elif score >= 50:
            return LiquidityLevel.MEDIUM
        elif score >= 20:
            return LiquidityLevel.LOW
        else:
            return LiquidityLevel.VERY_LOW

    def _calculate_max_market_order(
        self,
        liquidity_level: LiquidityLevel,
        depth_at_01pct: float,
        spread_pct: float
    ) -> float:
        """Calculate recommended maximum market order size"""
        # Base on available depth within 0.1% of mid
        # Conservative: use 10-20% of available depth

        base_factors = {
            LiquidityLevel.HIGH: 0.20,      # Can use 20% of depth
            LiquidityLevel.MEDIUM: 0.15,    # Use 15% of depth
            LiquidityLevel.LOW: 0.10,       # Use 10% of depth
            LiquidityLevel.VERY_LOW: 0.05   # Use only 5% of depth
        }

        factor = base_factors.get(liquidity_level, 0.10)
        max_order = depth_at_01pct * factor

        # Apply spread penalty for wide spreads
        if spread_pct > 0.002:  # >0.2% spread
            max_order *= 0.5  # Halve the recommendation

        return max_order

    def _calculate_max_limit_order(
        self,
        liquidity_level: LiquidityLevel,
        total_depth: float,
        spread_pct: float
    ) -> float:
        """Calculate recommended maximum limit order size"""
        # Limit orders can be larger as they don't immediately impact

        base_factors = {
            LiquidityLevel.HIGH: 0.05,      # 5% of total depth
            LiquidityLevel.MEDIUM: 0.03,    # 3% of total depth
            LiquidityLevel.LOW: 0.02,       # 2% of total depth
            LiquidityLevel.VERY_LOW: 0.01   # 1% of total depth
        }

        factor = base_factors.get(liquidity_level, 0.02)
        return total_depth * factor

    def _calculate_optimal_limit_offset(
        self,
        spread_pct: float,
        liquidity_level: LiquidityLevel,
        imbalance_ratio: float
    ) -> float:
        """Calculate optimal limit price offset from mid"""
        # Base offset depends on spread
        base_offset = spread_pct / 2  # Start at half spread

        # Adjust for liquidity
        liquidity_factors = {
            LiquidityLevel.HIGH: 0.8,      # Can be aggressive
            LiquidityLevel.MEDIUM: 1.0,    # Standard
            LiquidityLevel.LOW: 1.5,       # Need more buffer
            LiquidityLevel.VERY_LOW: 2.0   # Much more buffer
        }

        factor = liquidity_factors.get(liquidity_level, 1.0)
        optimal_offset = base_offset * factor

        # Minimum of 0.01%, maximum of 0.5%
        return max(0.0001, min(0.005, optimal_offset))

    def _create_empty_report(
        self,
        symbol: str,
        timestamp: datetime,
        current_price: Optional[Decimal]
    ) -> LiquidityReport:
        """Create empty report for missing order book data"""
        price = current_price or Decimal("0")
        empty_depth = DepthAnalysis(
            distance_pct=0,
            bid_depth_usd=0,
            bid_depth_qty=Decimal("0"),
            avg_bid_price=price,
            bid_levels_consumed=0,
            ask_depth_usd=0,
            ask_depth_qty=Decimal("0"),
            avg_ask_price=price,
            ask_levels_consumed=0,
            total_depth_usd=0,
            imbalance_ratio=1.0
        )

        return LiquidityReport(
            symbol=symbol,
            timestamp=timestamp,
            best_bid=price,
            best_ask=price,
            mid_price=price,
            spread_absolute=Decimal("0"),
            spread_pct=0.0,
            spread_category=SpreadCategory.VERY_WIDE,
            liquidity_level=LiquidityLevel.VERY_LOW,
            liquidity_score=0.0,
            total_bid_depth_usd=0.0,
            total_ask_depth_usd=0.0,
            total_depth_usd=0.0,
            book_state=OrderBookState.DEPLETED,
            imbalance_ratio=1.0,
            depth_at_01pct=empty_depth,
            depth_at_05pct=empty_depth,
            depth_at_1pct=empty_depth,
            recommended_max_market_order_usd=0.0,
            recommended_max_limit_order_usd=0.0,
            optimal_limit_offset_pct=0.005,
            warnings=["Order book data unavailable"]
        )

    # ========================================================================
    # MARKET IMPACT ESTIMATION
    # ========================================================================

    def estimate_market_impact(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        bids: List[List[str]],
        asks: List[List[str]],
        current_price: Optional[Decimal] = None
    ) -> MarketImpactEstimate:
        """
        Estimate market impact for a potential order

        Uses Kyle's lambda model and order book simulation:
        1. Simulate order execution through book
        2. Calculate temporary and permanent impact
        3. Estimate total execution cost

        Args:
            symbol: Trading symbol
            side: "BUY" or "SELL"
            quantity: Order quantity
            bids: Bid levels
            asks: Ask levels
            current_price: Optional current price

        Returns:
            MarketImpactEstimate with detailed impact analysis
        """
        # Get liquidity report (may use cache)
        report = self.analyze_liquidity(symbol, bids, asks, current_price)
        mid_price = report.mid_price

        # Calculate order value
        order_value_usd = float(quantity * mid_price)

        # Select relevant side of book
        if side.upper() == "BUY":
            levels = [
                PriceLevel(
                    price=Decimal(str(a[0])),
                    quantity=Decimal(str(a[1])),
                    value_usd=float(Decimal(str(a[0])) * Decimal(str(a[1])))
                )
                for a in asks[:self.config.depth_levels]
            ]
        else:
            levels = [
                PriceLevel(
                    price=Decimal(str(b[0])),
                    quantity=Decimal(str(b[1])),
                    value_usd=float(Decimal(str(b[0])) * Decimal(str(b[1])))
                )
                for b in bids[:self.config.depth_levels]
            ]

        # Simulate order execution
        remaining_qty = quantity
        total_value = Decimal("0")
        levels_consumed = 0
        worst_price = mid_price

        for level in levels:
            if remaining_qty <= 0:
                break

            fill_qty = min(remaining_qty, level.quantity)
            total_value += fill_qty * level.price
            remaining_qty -= fill_qty
            levels_consumed += 1
            worst_price = level.price

        # Calculate execution price
        filled_qty = quantity - remaining_qty
        if filled_qty > 0:
            execution_price = total_value / filled_qty
        else:
            execution_price = mid_price

        # Calculate slippage
        if side.upper() == "BUY":
            slippage_pct = float((execution_price - mid_price) / mid_price) * 100
        else:
            slippage_pct = float((mid_price - execution_price) / mid_price) * 100

        # Temporary impact (immediate price movement)
        # Based on Kyle's model: impact = lambda * order_size
        # Lambda estimated from spread and depth
        available_depth = (
            report.depth_at_01pct.ask_depth_usd if side.upper() == "BUY"
            else report.depth_at_01pct.bid_depth_usd
        )
        if available_depth > 0:
            temp_impact = (order_value_usd / available_depth) * 0.5 * 100  # In percent
        else:
            temp_impact = slippage_pct

        # Permanent impact (information leakage)
        # Typically 30-50% of temporary impact persists
        perm_impact = temp_impact * 0.3

        # Total impact
        total_impact = temp_impact + perm_impact

        # Cost calculation
        slippage_cost_usd = abs(slippage_pct / 100 * order_value_usd)
        spread_cost_usd = (report.spread_pct / 2) * order_value_usd  # Half-spread
        total_cost_usd = slippage_cost_usd + spread_cost_usd

        # Risk assessment
        is_acceptable = total_impact < self.config.impact_warning_pct
        warning = None

        if remaining_qty > 0:
            fill_pct = float(filled_qty / quantity) * 100
            warning = f"Order too large: only {fill_pct:.1f}% can be filled with available liquidity"
            is_acceptable = False
        elif total_impact > self.config.impact_warning_pct:
            warning = f"High market impact: {total_impact:.2f}% expected price movement"

        return MarketImpactEstimate(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_value_usd=order_value_usd,
            temporary_impact_pct=temp_impact,
            permanent_impact_pct=perm_impact,
            total_impact_pct=total_impact,
            mid_price=mid_price,
            execution_price=execution_price,
            worst_price=worst_price,
            price_levels_consumed=levels_consumed,
            slippage_cost_usd=slippage_cost_usd,
            spread_cost_usd=spread_cost_usd,
            total_cost_usd=total_cost_usd,
            is_acceptable=is_acceptable,
            warning_message=warning
        )

    # ========================================================================
    # OPTIMAL PRICE DISCOVERY
    # ========================================================================

    def find_optimal_limit_price(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        target_fill_probability: float = 0.8,
        bids: Optional[List[List[str]]] = None,
        asks: Optional[List[List[str]]] = None
    ) -> OptimalLimitPrice:
        """
        Find optimal limit price for target fill probability

        Analyzes order book to find price that balances:
        - Fill probability (higher = more aggressive price)
        - Execution cost (lower price for buys, higher for sells)
        - Time to fill (more aggressive = faster)

        Args:
            symbol: Trading symbol
            side: "BUY" or "SELL"
            quantity: Order quantity
            target_fill_probability: Target fill probability (0-1)
            bids: Bid levels (optional if cached)
            asks: Ask levels (optional if cached)

        Returns:
            OptimalLimitPrice with price recommendations
        """
        # Get cached report or require fresh data
        report = self._orderbook_cache.get(symbol)

        if report is None:
            if bids is None or asks is None:
                logger.warning(f"No order book data for {symbol}")
                return self._create_default_limit_price(
                    symbol, side, quantity, target_fill_probability
                )
            report = self.analyze_liquidity(symbol, bids, asks)

        mid_price = report.mid_price
        best_price = report.best_bid if side.upper() == "SELL" else report.best_ask

        # Calculate base offset from spread and liquidity
        base_offset = report.optimal_limit_offset_pct

        # Adjust for fill probability target
        # Higher target = more aggressive (closer to market)
        # Lower target = more passive (better price)
        probability_factor = 1.0 + (target_fill_probability - 0.5) * 2

        # Calculate recommended price
        if side.upper() == "BUY":
            # For buys: start below mid, adjust up for higher fill prob
            recommended_offset = base_offset / probability_factor
            recommended_price = mid_price * (1 - Decimal(str(recommended_offset)))

            # Aggressive: at or above best ask
            aggressive_price = best_price

            # Passive: further below mid
            passive_price = mid_price * (1 - Decimal(str(base_offset * 2)))

        else:  # SELL
            # For sells: start above mid, adjust down for higher fill prob
            recommended_offset = base_offset / probability_factor
            recommended_price = mid_price * (1 + Decimal(str(recommended_offset)))

            # Aggressive: at or below best bid
            aggressive_price = best_price

            # Passive: further above mid
            passive_price = mid_price * (1 + Decimal(str(base_offset * 2)))

        # Estimate time to fill based on price aggressiveness
        # Aggressive: ~10s, Passive: ~60s
        if side.upper() == "BUY":
            distance_from_best = float((best_price - recommended_price) / best_price)
        else:
            distance_from_best = float((recommended_price - best_price) / best_price)

        # Time increases exponentially with distance
        base_time = 10  # seconds at best price
        time_to_fill = base_time * math.exp(distance_from_best * 100)
        time_to_fill = min(300, time_to_fill)  # Cap at 5 minutes

        # Estimate fill probability
        # Based on distance from best price and liquidity
        if report.liquidity_score > 70:
            fill_prob = target_fill_probability  # Good liquidity = target achievable
        else:
            # Reduce probability for low liquidity
            fill_prob = target_fill_probability * (report.liquidity_score / 70)

        # Cost savings vs market
        if side.upper() == "BUY":
            savings_pct = float((best_price - recommended_price) / best_price) * 100
        else:
            savings_pct = float((recommended_price - best_price) / best_price) * 100

        savings_pct = max(0, savings_pct)  # Can't have negative savings
        expected_cost = float(quantity * recommended_price) * (1 - savings_pct / 100)

        # Risk assessment
        if fill_prob < 0.5:
            fill_risk = "HIGH"
        elif fill_prob < 0.7:
            fill_risk = "MEDIUM"
        else:
            fill_risk = "LOW"

        return OptimalLimitPrice(
            symbol=symbol,
            side=side,
            quantity=quantity,
            current_mid=mid_price,
            best_price=best_price,
            recommended_price=recommended_price,
            aggressive_price=aggressive_price,
            passive_price=passive_price,
            offset_from_mid_pct=float(abs(recommended_price - mid_price) / mid_price),
            estimated_fill_probability=fill_prob,
            estimated_time_to_fill_seconds=time_to_fill,
            expected_cost_vs_market_pct=savings_pct,
            expected_cost_usd=expected_cost,
            fill_risk=fill_risk
        )

    def _create_default_limit_price(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        target_fill_probability: float
    ) -> OptimalLimitPrice:
        """Create default limit price when no order book data available"""
        return OptimalLimitPrice(
            symbol=symbol,
            side=side,
            quantity=quantity,
            current_mid=Decimal("0"),
            best_price=Decimal("0"),
            recommended_price=Decimal("0"),
            aggressive_price=Decimal("0"),
            passive_price=Decimal("0"),
            offset_from_mid_pct=0.001,
            estimated_fill_probability=0.5,
            estimated_time_to_fill_seconds=60.0,
            expected_cost_vs_market_pct=0.0,
            expected_cost_usd=0.0,
            fill_risk="HIGH"
        )

    # ========================================================================
    # UTILITY METHODS
    # ========================================================================

    def get_cached_report(self, symbol: str) -> Optional[LiquidityReport]:
        """Get cached liquidity report if valid"""
        report = self._orderbook_cache.get(symbol)
        timestamp = self._cache_timestamps.get(symbol)

        if report and timestamp:
            age = (datetime.now(timezone.utc) - timestamp).total_seconds()
            if age < self.config.cache_ttl_seconds:
                return report

        return None

    def get_average_spread(self, symbol: str, periods: int = 20) -> Optional[float]:
        """Get average spread from recent history"""
        history = self._spread_history.get(symbol)
        if not history:
            return None

        recent = list(history)[-periods:]
        if not recent:
            return None

        return statistics.mean(recent)

    def get_status(self) -> Dict:
        """Get analyzer status summary"""
        return {
            "config": {
                "depth_levels": self.config.depth_levels,
                "high_liquidity_threshold": self.config.high_liquidity_threshold,
                "tight_spread_threshold": self.config.tight_spread_threshold,
                "cache_ttl_seconds": self.config.cache_ttl_seconds
            },
            "cached_symbols": list(self._orderbook_cache.keys()),
            "spread_history_symbols": list(self._spread_history.keys())
        }


# ============================================================================
# GLOBAL INSTANCE MANAGEMENT
# ============================================================================

# Global analyzer instance
_orderbook_analyzer: Optional[OrderbookAnalyzer] = None


def get_orderbook_analyzer(
    config: Optional[OrderBookConfig] = None
) -> OrderbookAnalyzer:
    """
    Get or create global orderbook analyzer instance

    Args:
        config: Optional configuration (only used if creating new instance)

    Returns:
        OrderbookAnalyzer instance
    """
    global _orderbook_analyzer
    if _orderbook_analyzer is None:
        _orderbook_analyzer = OrderbookAnalyzer(config)
    return _orderbook_analyzer


def reset_orderbook_analyzer():
    """Reset global orderbook analyzer instance"""
    global _orderbook_analyzer
    _orderbook_analyzer = None
    logger.info("Orderbook analyzer instance reset")
