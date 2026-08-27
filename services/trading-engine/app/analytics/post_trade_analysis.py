"""
Post-Trade Analysis Module
Purpose: Analyze execution quality, slippage, and cost breakdown for every trade
         to identify improvements and optimize trading performance.

This module provides comprehensive post-trade analysis including:
- Trade Cost Analysis (expected vs actual, slippage breakdown, fees)
- Execution Quality Metrics (Implementation Shortfall, Price Improvement)
- Trade Classification (aggressive/passive, market conditions, liquidity)
- Benchmark Comparisons (arrival price, VWAP, TWAP)
- Improvement Recommendations

Author: Backend Developer Agent
Date: 2025-12-12
Version: 1.0.0
"""

import logging
import threading
import math
from typing import List, Dict, Optional, Any, Tuple
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from uuid import uuid4
import statistics

# Configure logging for post-trade analysis module
logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS FOR TRADE CLASSIFICATION
# =============================================================================

class ExecutionStyle(str, Enum):
    """Trade execution style classification"""
    AGGRESSIVE = "aggressive"      # Market orders, crossing the spread
    PASSIVE = "passive"            # Limit orders, providing liquidity
    HYBRID = "hybrid"              # Combination of both


class MarketConditionType(str, Enum):
    """Market conditions during trade execution"""
    VOLATILE = "volatile"          # High volatility (>2 std dev moves)
    STABLE = "stable"              # Normal volatility
    TRENDING_UP = "trending_up"    # Strong upward price movement
    TRENDING_DOWN = "trending_down"  # Strong downward price movement
    RANGING = "ranging"            # Sideways/consolidating market


class LiquidityLevel(str, Enum):
    """Liquidity assessment during execution"""
    DEEP = "deep"                  # Excellent liquidity, minimal impact
    NORMAL = "normal"              # Standard liquidity conditions
    THIN = "thin"                  # Low liquidity, high impact risk


class TradingSession(str, Enum):
    """Trading session based on time of day"""
    ASIA = "asia"                  # 00:00-08:00 UTC
    EUROPE = "europe"              # 08:00-16:00 UTC
    US = "us"                      # 16:00-24:00 UTC


class ExecutionQualityGrade(str, Enum):
    """Overall execution quality grade"""
    EXCELLENT = "excellent"        # 90-100 score
    GOOD = "good"                  # 75-89 score
    FAIR = "fair"                  # 50-74 score
    POOR = "poor"                  # 25-49 score
    VERY_POOR = "very_poor"        # 0-24 score


class BenchmarkType(str, Enum):
    """Benchmark types for execution comparison"""
    ARRIVAL_PRICE = "arrival_price"     # Price at decision time
    VWAP = "vwap"                        # Volume-weighted average price
    TWAP = "twap"                        # Time-weighted average price
    CLOSE = "close"                      # Closing price


# =============================================================================
# DATA MODELS FOR POST-TRADE ANALYSIS
# =============================================================================

@dataclass
class SlippageBreakdown:
    """
    Detailed breakdown of slippage components

    Slippage = Market Impact + Spread Cost + Timing Cost

    Attributes:
        market_impact: Price moved against us due to our order
        spread_cost: Cost of crossing bid-ask spread
        timing_cost: Adverse selection from execution delay
        total_slippage: Sum of all slippage components
        slippage_bps: Total slippage in basis points
    """
    market_impact: float = 0.0
    spread_cost: float = 0.0
    timing_cost: float = 0.0
    total_slippage: float = 0.0
    slippage_bps: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        # market_impact / spread_cost / timing_cost / total_slippage are
        # USD costs, not per-unit prices: _calculate_slippage multiplies
        # every component through by size or notional before it lands here
        # (slippage_cost = raw_slippage * size; spread_cost =
        # spread_bps / 10000 * notional / 2). 4dp is cent precision on a
        # dollar total, not tick precision on a price. Classified for the
        # Phase 22 guard enrollment - re-read that method before reopening.
        return {
            "market_impact": round(self.market_impact, 4),  # non-price-round
            "spread_cost": round(self.spread_cost, 4),  # non-price-round
            "timing_cost": round(self.timing_cost, 4),  # non-price-round
            "total_slippage": round(self.total_slippage, 4),  # non-price-round
            "slippage_bps": round(self.slippage_bps, 2),  # non-price-round
        }


@dataclass
class ExecutionQuality:
    """
    Execution quality metrics

    Attributes:
        implementation_shortfall: Difference between paper and actual performance
        price_improvement: Amount saved compared to worst expected price
        fill_rate: Percentage of order filled
        time_to_completion: Seconds to complete execution
        spread_capture_rate: How much of spread was captured (for limit orders)
        benchmark_comparisons: Performance vs various benchmarks
        quality_score: Overall quality score (0-100)
        quality_grade: Letter grade for quality
    """
    implementation_shortfall: float = 0.0
    implementation_shortfall_bps: float = 0.0
    price_improvement: float = 0.0
    price_improvement_bps: float = 0.0
    fill_rate: float = 100.0
    time_to_completion: float = 0.0
    spread_capture_rate: float = 0.0
    benchmark_comparisons: Dict[str, float] = field(default_factory=dict)
    quality_score: int = 0
    quality_grade: ExecutionQualityGrade = ExecutionQualityGrade.FAIR

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "implementation_shortfall": round(self.implementation_shortfall, 4),  # non-price-round
            "implementation_shortfall_bps": round(  # non-price-round
                self.implementation_shortfall_bps, 2
            ),
            # PRICE-01: a per-unit price DELTA, not a USD total -
            # _calculate_execution_quality takes worst_price minus
            # execution_price against a half-spread of
            # expected_price * (spread_bps / 20000). At ADA scale that is
            # ~1.5e-4, so 4dp reported real improvements as 0.0.
            "price_improvement": float(self.price_improvement),
            "price_improvement_bps": round(self.price_improvement_bps, 2),  # non-price-round
            "fill_rate": round(self.fill_rate, 2),  # non-price-round
            "time_to_completion": round(self.time_to_completion, 2),  # non-price-round
            "spread_capture_rate": round(self.spread_capture_rate, 2),  # non-price-round
            "benchmark_comparisons": {
                k: round(v, 4) for k, v in self.benchmark_comparisons.items()  # non-price-round
            },
            "quality_score": self.quality_score,
            "quality_grade": self.quality_grade.value,
        }


@dataclass
class TradeClassification:
    """
    Trade classification based on execution characteristics

    Attributes:
        execution_style: Aggressive vs passive execution
        market_condition: Market state during trade
        liquidity_level: Liquidity assessment
        trading_session: Time of day session
        order_urgency: Urgency level of the order
    """
    execution_style: ExecutionStyle = ExecutionStyle.AGGRESSIVE
    market_condition: MarketConditionType = MarketConditionType.STABLE
    liquidity_level: LiquidityLevel = LiquidityLevel.NORMAL
    trading_session: TradingSession = TradingSession.US
    order_urgency: str = "normal"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "execution_style": self.execution_style.value,
            "market_condition": self.market_condition.value,
            "liquidity_level": self.liquidity_level.value,
            "trading_session": self.trading_session.value,
            "order_urgency": self.order_urgency,
        }


@dataclass
class TradeExecutionData:
    """
    Input data for a trade execution to be analyzed

    Attributes:
        trade_id: Unique trade identifier
        symbol: Trading symbol (e.g., BTCUSDT)
        side: BUY or SELL
        size: Order size in base currency
        expected_price: Price at decision time
        execution_price: Actual average fill price
        fees: Total fees paid
        order_type: MARKET, LIMIT, etc.
        decision_timestamp: When trade decision was made
        execution_timestamp: When trade was fully executed
        strategy: Strategy that generated the trade
        benchmark_prices: Dictionary of benchmark prices
        market_data: Additional market data (volatility, spread, etc.)
    """
    trade_id: str
    symbol: str
    side: str
    size: float
    expected_price: float
    execution_price: float
    fees: float = 0.0
    order_type: str = "MARKET"
    decision_timestamp: Optional[datetime] = None
    execution_timestamp: Optional[datetime] = None
    strategy: str = "unknown"
    benchmark_prices: Dict[str, float] = field(default_factory=dict)
    market_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "size": self.size,
            "expected_price": self.expected_price,
            "execution_price": self.execution_price,
            "fees": self.fees,
            "order_type": self.order_type,
            "decision_timestamp": self.decision_timestamp.isoformat() if self.decision_timestamp else None,
            "execution_timestamp": self.execution_timestamp.isoformat() if self.execution_timestamp else None,
            "strategy": self.strategy,
            "benchmark_prices": self.benchmark_prices,
            "market_data": self.market_data,
        }


@dataclass
class PostTradeAnalysisResult:
    """
    Complete post-trade analysis result

    Contains all analysis components for a single trade.
    """
    trade_id: str
    symbol: str
    side: str
    size: float
    expected_price: float
    execution_price: float

    # Cost breakdown
    slippage: SlippageBreakdown = field(default_factory=SlippageBreakdown)
    fees: float = 0.0
    total_cost: float = 0.0
    cost_bps: float = 0.0

    # Execution quality
    execution_quality: ExecutionQuality = field(default_factory=ExecutionQuality)

    # Classification
    classification: TradeClassification = field(default_factory=TradeClassification)

    # Recommendations
    recommendations: List[str] = field(default_factory=list)

    # Metadata
    analyzed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    strategy: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "size": self.size,
            "expected_price": round(self.expected_price, 8),
            "execution_price": round(self.execution_price, 8),
            "slippage": self.slippage.to_dict(),
            "fees": round(self.fees, 4),  # non-price-round
            "total_cost": round(self.total_cost, 4),  # non-price-round
            "cost_bps": round(self.cost_bps, 2),  # non-price-round
            "execution_quality": self.execution_quality.to_dict(),
            "classification": self.classification.to_dict(),
            "recommendations": self.recommendations,
            "analyzed_at": self.analyzed_at.isoformat(),
            "strategy": self.strategy,
        }


@dataclass
class DailySummary:
    """
    Daily execution summary aggregating all trades

    Attributes:
        date: Date of the summary
        total_trades: Number of trades
        total_volume: Total trading volume in USD
        avg_slippage_bps: Average slippage in basis points
        avg_cost_bps: Average total cost in basis points
        avg_quality_score: Average execution quality score
        best_trade_id: Best execution of the day
        worst_trade_id: Worst execution of the day
        by_strategy: Breakdown by strategy
        by_symbol: Breakdown by symbol
        by_session: Breakdown by trading session
        recommendations: Daily improvement recommendations
    """
    date: str
    total_trades: int = 0
    total_volume: float = 0.0
    avg_slippage_bps: float = 0.0
    avg_cost_bps: float = 0.0
    avg_quality_score: float = 0.0
    total_fees: float = 0.0
    total_slippage_cost: float = 0.0
    best_trade_id: Optional[str] = None
    best_trade_score: int = 0
    worst_trade_id: Optional[str] = None
    worst_trade_score: int = 100
    by_strategy: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    by_symbol: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    by_session: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "date": self.date,
            "total_trades": self.total_trades,
            "total_volume": round(self.total_volume, 2),  # non-price-round
            "avg_slippage_bps": round(self.avg_slippage_bps, 2),  # non-price-round
            "avg_cost_bps": round(self.avg_cost_bps, 2),  # non-price-round
            "avg_quality_score": round(self.avg_quality_score, 1),
            "total_fees": round(self.total_fees, 2),  # non-price-round
            "total_slippage_cost": round(self.total_slippage_cost, 2),  # non-price-round
            "best_trade": {
                "trade_id": self.best_trade_id,
                "score": self.best_trade_score,
            } if self.best_trade_id else None,
            "worst_trade": {
                "trade_id": self.worst_trade_id,
                "score": self.worst_trade_score,
            } if self.worst_trade_id else None,
            "by_strategy": self.by_strategy,
            "by_symbol": self.by_symbol,
            "by_session": self.by_session,
            "recommendations": self.recommendations,
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass
class ImprovementRecommendation:
    """
    Improvement recommendation based on analysis

    Attributes:
        category: Type of improvement (execution, timing, sizing, etc.)
        priority: Priority level (high, medium, low)
        recommendation: Detailed recommendation text
        expected_savings_bps: Estimated savings in basis points
        applicable_to: What trades/strategies this applies to
        evidence: Data supporting the recommendation
    """
    category: str
    priority: str
    recommendation: str
    expected_savings_bps: float = 0.0
    applicable_to: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "category": self.category,
            "priority": self.priority,
            "recommendation": self.recommendation,
            "expected_savings_bps": round(self.expected_savings_bps, 2),  # non-price-round
            "applicable_to": self.applicable_to,
            "evidence": self.evidence,
        }


# =============================================================================
# POST-TRADE ANALYSIS ENGINE
# =============================================================================

class PostTradeAnalyzer:
    """
    Post-Trade Analysis Engine

    Analyzes trade executions to calculate costs, measure quality,
    classify trades, and generate improvement recommendations.

    Thread-safe implementation with caching for performance.

    Usage:
        analyzer = get_post_trade_analyzer()
        result = analyzer.analyze_trade(trade_data)
        summary = analyzer.get_daily_summary("2025-12-12")
        improvements = analyzer.get_improvement_recommendations()
    """

    # Configuration constants
    DEFAULT_SPREAD_BPS = 5.0           # Default bid-ask spread in bps
    SLIPPAGE_ALERT_THRESHOLD_BPS = 20  # Alert when slippage exceeds this
    QUALITY_SCORE_WEIGHTS = {
        "slippage": 0.30,
        "implementation_shortfall": 0.25,
        "fill_rate": 0.20,
        "time_to_completion": 0.15,
        "spread_capture": 0.10,
    }

    def __init__(
        self,
        default_maker_fee_bps: float = 2.0,
        default_taker_fee_bps: float = 5.0,
        slippage_alert_threshold_bps: float = 20.0,
    ):
        """
        Initialize the Post-Trade Analyzer

        Args:
            default_maker_fee_bps: Default maker fee in basis points
            default_taker_fee_bps: Default taker fee in basis points
            slippage_alert_threshold_bps: Threshold for slippage alerts
        """
        self._lock = threading.Lock()

        # Configuration
        self.default_maker_fee_bps = default_maker_fee_bps
        self.default_taker_fee_bps = default_taker_fee_bps
        self.slippage_alert_threshold = slippage_alert_threshold_bps

        # Analysis storage
        self._analyses: Dict[str, PostTradeAnalysisResult] = {}
        self._daily_summaries: Dict[str, DailySummary] = {}
        self._strategy_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "trade_count": 0,
            "total_slippage_bps": 0.0,
            "total_cost_bps": 0.0,
            "quality_scores": [],
        })
        self._symbol_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "trade_count": 0,
            "total_slippage_bps": 0.0,
            "total_cost_bps": 0.0,
            "quality_scores": [],
        })

        logger.info(
            f"PostTradeAnalyzer initialized: "
            f"maker_fee={default_maker_fee_bps}bps, "
            f"taker_fee={default_taker_fee_bps}bps, "
            f"slippage_alert={slippage_alert_threshold_bps}bps"
        )

    # =========================================================================
    # CORE ANALYSIS METHODS
    # =========================================================================

    def analyze_trade(self, trade_data: TradeExecutionData) -> PostTradeAnalysisResult:
        """
        Perform comprehensive post-trade analysis

        Args:
            trade_data: Trade execution data to analyze

        Returns:
            PostTradeAnalysisResult with complete analysis
        """
        with self._lock:
            # Calculate slippage breakdown
            slippage = self._calculate_slippage(trade_data)

            # Calculate execution quality
            execution_quality = self._calculate_execution_quality(trade_data, slippage)

            # Classify the trade
            classification = self._classify_trade(trade_data)

            # Calculate total cost
            notional = trade_data.size * trade_data.execution_price
            total_cost = slippage.total_slippage + trade_data.fees
            cost_bps = (total_cost / notional * 10000) if notional > 0 else 0.0

            # Generate recommendations
            recommendations = self._generate_trade_recommendations(
                trade_data, slippage, execution_quality, classification
            )

            # Create result
            result = PostTradeAnalysisResult(
                trade_id=trade_data.trade_id,
                symbol=trade_data.symbol,
                side=trade_data.side,
                size=trade_data.size,
                expected_price=trade_data.expected_price,
                execution_price=trade_data.execution_price,
                slippage=slippage,
                fees=trade_data.fees,
                total_cost=total_cost,
                cost_bps=cost_bps,
                execution_quality=execution_quality,
                classification=classification,
                recommendations=recommendations,
                strategy=trade_data.strategy,
            )

            # Store result
            self._analyses[trade_data.trade_id] = result

            # Update statistics
            self._update_statistics(result)

            # Check for alerts
            if slippage.slippage_bps > self.slippage_alert_threshold:
                logger.warning(
                    f"High slippage alert: Trade {trade_data.trade_id} "
                    f"slippage={slippage.slippage_bps:.2f}bps "
                    f"threshold={self.slippage_alert_threshold}bps"
                )

            logger.info(
                f"Trade analyzed: {trade_data.trade_id} "
                f"cost={cost_bps:.2f}bps "
                f"quality={execution_quality.quality_score}/100"
            )

            return result

    def _calculate_slippage(self, trade_data: TradeExecutionData) -> SlippageBreakdown:
        """
        Calculate detailed slippage breakdown

        Slippage = Market Impact + Spread Cost + Timing Cost

        Args:
            trade_data: Trade execution data

        Returns:
            SlippageBreakdown with component costs
        """
        # Calculate price difference
        price_diff = trade_data.execution_price - trade_data.expected_price

        # Adjust sign for side (BUY wants lower price, SELL wants higher)
        if trade_data.side.upper() == "BUY":
            # For buys, positive diff = slippage (paid more)
            raw_slippage = price_diff
        else:
            # For sells, negative diff = slippage (received less)
            raw_slippage = -price_diff

        # Calculate slippage cost in USD
        slippage_cost = raw_slippage * trade_data.size

        # Calculate slippage in basis points
        notional = trade_data.size * trade_data.expected_price
        slippage_bps = (slippage_cost / notional * 10000) if notional > 0 else 0.0

        # Get spread from market data or use default
        spread_bps = trade_data.market_data.get("spread_bps", self.DEFAULT_SPREAD_BPS)
        spread_cost = (spread_bps / 10000) * notional / 2  # Half spread for one-way trade

        # Estimate market impact (simplified model)
        # Market impact increases with order size relative to typical volume
        avg_volume = trade_data.market_data.get("avg_volume", 1000000)
        size_ratio = (trade_data.size * trade_data.execution_price) / avg_volume
        market_impact_factor = min(size_ratio * 10, 1.0)  # Cap at 100% of slippage

        # Timing cost is the remainder
        market_impact = abs(slippage_cost) * market_impact_factor
        timing_cost = max(0, abs(slippage_cost) - market_impact - spread_cost)

        # Ensure total equals raw slippage cost
        if slippage_cost >= 0:
            total_slippage = slippage_cost
        else:
            # Price improvement (negative slippage)
            total_slippage = slippage_cost
            market_impact = 0
            spread_cost = 0
            timing_cost = total_slippage

        return SlippageBreakdown(
            market_impact=market_impact,
            spread_cost=spread_cost,
            timing_cost=timing_cost,
            total_slippage=total_slippage,
            slippage_bps=slippage_bps,
        )

    def _calculate_execution_quality(
        self,
        trade_data: TradeExecutionData,
        slippage: SlippageBreakdown,
    ) -> ExecutionQuality:
        """
        Calculate execution quality metrics

        Args:
            trade_data: Trade execution data
            slippage: Calculated slippage breakdown

        Returns:
            ExecutionQuality with all metrics
        """
        notional = trade_data.size * trade_data.expected_price

        # Implementation Shortfall
        # IS = (Execution Price - Decision Price) / Decision Price
        price_diff = trade_data.execution_price - trade_data.expected_price
        if trade_data.side.upper() == "SELL":
            price_diff = -price_diff  # Flip sign for sells

        impl_shortfall = price_diff / trade_data.expected_price if trade_data.expected_price > 0 else 0
        impl_shortfall_bps = impl_shortfall * 10000

        # Price Improvement
        # Compare to worst expected price (considering spread)
        spread_bps = trade_data.market_data.get("spread_bps", self.DEFAULT_SPREAD_BPS)
        half_spread = trade_data.expected_price * (spread_bps / 20000)

        if trade_data.side.upper() == "BUY":
            worst_price = trade_data.expected_price + half_spread
            improvement = worst_price - trade_data.execution_price
        else:
            worst_price = trade_data.expected_price - half_spread
            improvement = trade_data.execution_price - worst_price

        price_improvement = max(0, improvement)
        price_improvement_bps = (price_improvement / trade_data.expected_price * 10000) if trade_data.expected_price > 0 else 0

        # Fill Rate
        fill_rate = trade_data.market_data.get("fill_rate", 100.0)

        # Time to Completion
        time_to_completion = 0.0
        if trade_data.decision_timestamp and trade_data.execution_timestamp:
            delta = trade_data.execution_timestamp - trade_data.decision_timestamp
            time_to_completion = delta.total_seconds()

        # Spread Capture Rate (for limit orders)
        spread_capture = 0.0
        if trade_data.order_type == "LIMIT":
            # If price improved from mid, we captured spread
            if price_improvement > 0:
                spread_capture = min(100, (price_improvement / (half_spread * 2)) * 100)

        # Benchmark Comparisons
        benchmark_comparisons = {}
        for bench_name, bench_price in trade_data.benchmark_prices.items():
            if bench_price > 0:
                diff = trade_data.execution_price - bench_price
                if trade_data.side.upper() == "SELL":
                    diff = -diff
                benchmark_comparisons[bench_name] = diff / bench_price * 10000  # In bps

        # Calculate Quality Score (0-100)
        quality_score = self._calculate_quality_score(
            slippage.slippage_bps,
            impl_shortfall_bps,
            fill_rate,
            time_to_completion,
            spread_capture,
        )

        # Determine grade
        quality_grade = self._get_quality_grade(quality_score)

        return ExecutionQuality(
            implementation_shortfall=impl_shortfall,
            implementation_shortfall_bps=impl_shortfall_bps,
            price_improvement=price_improvement,
            price_improvement_bps=price_improvement_bps,
            fill_rate=fill_rate,
            time_to_completion=time_to_completion,
            spread_capture_rate=spread_capture,
            benchmark_comparisons=benchmark_comparisons,
            quality_score=quality_score,
            quality_grade=quality_grade,
        )

    def _calculate_quality_score(
        self,
        slippage_bps: float,
        impl_shortfall_bps: float,
        fill_rate: float,
        time_to_completion: float,
        spread_capture: float,
    ) -> int:
        """
        Calculate overall quality score (0-100)

        Args:
            slippage_bps: Slippage in basis points
            impl_shortfall_bps: Implementation shortfall in bps
            fill_rate: Percentage filled
            time_to_completion: Seconds to complete
            spread_capture: Spread capture rate

        Returns:
            Quality score from 0-100
        """
        scores = {}

        # Slippage score (lower is better)
        # 0 bps = 100, 10 bps = 50, 20+ bps = 0
        slippage_score = max(0, 100 - abs(slippage_bps) * 5)
        scores["slippage"] = slippage_score

        # Implementation shortfall score (lower is better)
        # 0 bps = 100, 10 bps = 50, 20+ bps = 0
        is_score = max(0, 100 - abs(impl_shortfall_bps) * 5)
        scores["implementation_shortfall"] = is_score

        # Fill rate score (higher is better)
        scores["fill_rate"] = fill_rate

        # Time to completion score (faster is better)
        # 0 sec = 100, 60 sec = 50, 120+ sec = 0
        time_score = max(0, 100 - time_to_completion / 1.2)
        scores["time_to_completion"] = time_score

        # Spread capture score (higher is better)
        scores["spread_capture"] = spread_capture

        # Weighted average
        total_score = sum(
            scores[metric] * weight
            for metric, weight in self.QUALITY_SCORE_WEIGHTS.items()
        )

        return int(min(100, max(0, total_score)))

    def _get_quality_grade(self, score: int) -> ExecutionQualityGrade:
        """
        Convert numeric score to letter grade

        Args:
            score: Quality score (0-100)

        Returns:
            ExecutionQualityGrade enum
        """
        if score >= 90:
            return ExecutionQualityGrade.EXCELLENT
        elif score >= 75:
            return ExecutionQualityGrade.GOOD
        elif score >= 50:
            return ExecutionQualityGrade.FAIR
        elif score >= 25:
            return ExecutionQualityGrade.POOR
        else:
            return ExecutionQualityGrade.VERY_POOR

    def _classify_trade(self, trade_data: TradeExecutionData) -> TradeClassification:
        """
        Classify the trade based on execution characteristics

        Args:
            trade_data: Trade execution data

        Returns:
            TradeClassification with all classifications
        """
        # Execution Style
        if trade_data.order_type == "MARKET":
            execution_style = ExecutionStyle.AGGRESSIVE
        elif trade_data.order_type == "LIMIT":
            execution_style = ExecutionStyle.PASSIVE
        else:
            execution_style = ExecutionStyle.HYBRID

        # Market Condition
        volatility = trade_data.market_data.get("volatility", 0.02)
        price_change = trade_data.market_data.get("price_change_1h", 0.0)

        if volatility > 0.05:
            market_condition = MarketConditionType.VOLATILE
        elif price_change > 0.02:
            market_condition = MarketConditionType.TRENDING_UP
        elif price_change < -0.02:
            market_condition = MarketConditionType.TRENDING_DOWN
        elif abs(price_change) < 0.005:
            market_condition = MarketConditionType.RANGING
        else:
            market_condition = MarketConditionType.STABLE

        # Liquidity Level
        spread_bps = trade_data.market_data.get("spread_bps", self.DEFAULT_SPREAD_BPS)
        orderbook_depth = trade_data.market_data.get("orderbook_depth_ratio", 1.0)

        if spread_bps < 3 and orderbook_depth > 0.8:
            liquidity_level = LiquidityLevel.DEEP
        elif spread_bps > 10 or orderbook_depth < 0.3:
            liquidity_level = LiquidityLevel.THIN
        else:
            liquidity_level = LiquidityLevel.NORMAL

        # Trading Session
        exec_time = trade_data.execution_timestamp or datetime.now(timezone.utc)
        hour = exec_time.hour

        if 0 <= hour < 8:
            trading_session = TradingSession.ASIA
        elif 8 <= hour < 16:
            trading_session = TradingSession.EUROPE
        else:
            trading_session = TradingSession.US

        # Order Urgency
        time_to_exec = trade_data.market_data.get("time_to_execution", 0)
        if time_to_exec < 1:
            urgency = "high"
        elif time_to_exec < 60:
            urgency = "normal"
        else:
            urgency = "low"

        return TradeClassification(
            execution_style=execution_style,
            market_condition=market_condition,
            liquidity_level=liquidity_level,
            trading_session=trading_session,
            order_urgency=urgency,
        )

    def _generate_trade_recommendations(
        self,
        trade_data: TradeExecutionData,
        slippage: SlippageBreakdown,
        quality: ExecutionQuality,
        classification: TradeClassification,
    ) -> List[str]:
        """
        Generate improvement recommendations for this trade

        Args:
            trade_data: Original trade data
            slippage: Slippage breakdown
            quality: Execution quality metrics
            classification: Trade classification

        Returns:
            List of recommendation strings
        """
        recommendations = []

        # Slippage-based recommendations
        if slippage.slippage_bps > 10:
            if classification.execution_style == ExecutionStyle.AGGRESSIVE:
                recommendations.append(
                    f"High slippage ({slippage.slippage_bps:.1f}bps): "
                    f"Consider using limit orders for trades of this size in "
                    f"{classification.market_condition.value} markets"
                )
            if slippage.market_impact > slippage.spread_cost:
                recommendations.append(
                    "Market impact is the main slippage driver: "
                    "Consider breaking large orders into smaller pieces"
                )

        # Timing recommendations
        if quality.time_to_completion > 60:
            recommendations.append(
                f"Slow execution ({quality.time_to_completion:.0f}s): "
                "Consider using more aggressive order types if speed is critical"
            )

        # Liquidity recommendations
        if classification.liquidity_level == LiquidityLevel.THIN:
            recommendations.append(
                "Traded during thin liquidity: "
                "Consider timing orders during higher liquidity sessions"
            )

        # Session recommendations
        if classification.trading_session == TradingSession.ASIA:
            spread_bps = trade_data.market_data.get("spread_bps", self.DEFAULT_SPREAD_BPS)
            if spread_bps > 7:
                recommendations.append(
                    "Asian session typically has wider spreads: "
                    "Non-urgent orders may benefit from European session execution"
                )

        # Fill rate recommendations
        if quality.fill_rate < 100:
            recommendations.append(
                f"Partial fill ({quality.fill_rate:.0f}%): "
                "Consider adjusting limit price or using market orders"
            )

        # Quality improvement recommendations
        if quality.quality_score < 50:
            recommendations.append(
                f"Low execution quality score ({quality.quality_score}/100): "
                "Review order parameters and timing strategy"
            )

        # Positive reinforcement
        if quality.quality_score >= 85:
            recommendations.append(
                f"Excellent execution ({quality.quality_score}/100): "
                "Current strategy is working well for this trade profile"
            )

        return recommendations

    def _update_statistics(self, result: PostTradeAnalysisResult) -> None:
        """
        Update running statistics with new analysis result

        Args:
            result: Analysis result to incorporate
        """
        # Update strategy stats
        strategy_stat = self._strategy_stats[result.strategy]
        strategy_stat["trade_count"] += 1
        strategy_stat["total_slippage_bps"] += result.slippage.slippage_bps
        strategy_stat["total_cost_bps"] += result.cost_bps
        strategy_stat["quality_scores"].append(result.execution_quality.quality_score)

        # Update symbol stats
        symbol_stat = self._symbol_stats[result.symbol]
        symbol_stat["trade_count"] += 1
        symbol_stat["total_slippage_bps"] += result.slippage.slippage_bps
        symbol_stat["total_cost_bps"] += result.cost_bps
        symbol_stat["quality_scores"].append(result.execution_quality.quality_score)

    # =========================================================================
    # RETRIEVAL AND REPORTING METHODS
    # =========================================================================

    def get_analysis(self, trade_id: str) -> Optional[PostTradeAnalysisResult]:
        """
        Get analysis result for a specific trade

        Args:
            trade_id: Trade identifier

        Returns:
            PostTradeAnalysisResult or None if not found
        """
        with self._lock:
            return self._analyses.get(trade_id)

    def get_daily_summary(self, date: str) -> DailySummary:
        """
        Get or generate daily execution summary

        Args:
            date: Date string (YYYY-MM-DD)

        Returns:
            DailySummary for the specified date
        """
        with self._lock:
            # Check cache
            if date in self._daily_summaries:
                return self._daily_summaries[date]

            # Filter analyses for this date
            date_analyses = []
            for analysis in self._analyses.values():
                analysis_date = analysis.analyzed_at.strftime("%Y-%m-%d")
                if analysis_date == date:
                    date_analyses.append(analysis)

            # Create summary
            summary = self._generate_daily_summary(date, date_analyses)

            # Cache
            self._daily_summaries[date] = summary

            return summary

    def _generate_daily_summary(
        self,
        date: str,
        analyses: List[PostTradeAnalysisResult],
    ) -> DailySummary:
        """
        Generate daily summary from analyses

        Args:
            date: Date string
            analyses: List of analyses for the day

        Returns:
            DailySummary object
        """
        if not analyses:
            return DailySummary(date=date, recommendations=[
                "No trades to analyze for this day"
            ])

        # Basic aggregations
        total_trades = len(analyses)
        total_volume = sum(a.size * a.execution_price for a in analyses)
        total_fees = sum(a.fees for a in analyses)
        total_slippage = sum(a.slippage.total_slippage for a in analyses)

        avg_slippage_bps = statistics.mean(a.slippage.slippage_bps for a in analyses)
        avg_cost_bps = statistics.mean(a.cost_bps for a in analyses)
        avg_quality = statistics.mean(a.execution_quality.quality_score for a in analyses)

        # Find best and worst
        best = max(analyses, key=lambda a: a.execution_quality.quality_score)
        worst = min(analyses, key=lambda a: a.execution_quality.quality_score)

        # Breakdown by strategy
        by_strategy = {}
        for strategy in set(a.strategy for a in analyses):
            strategy_trades = [a for a in analyses if a.strategy == strategy]
            by_strategy[strategy] = {
                "trade_count": len(strategy_trades),
                "avg_slippage_bps": statistics.mean(a.slippage.slippage_bps for a in strategy_trades),
                "avg_cost_bps": statistics.mean(a.cost_bps for a in strategy_trades),
                "avg_quality_score": statistics.mean(
                    a.execution_quality.quality_score for a in strategy_trades
                ),
            }

        # Breakdown by symbol
        by_symbol = {}
        for symbol in set(a.symbol for a in analyses):
            symbol_trades = [a for a in analyses if a.symbol == symbol]
            by_symbol[symbol] = {
                "trade_count": len(symbol_trades),
                "avg_slippage_bps": statistics.mean(a.slippage.slippage_bps for a in symbol_trades),
                "avg_cost_bps": statistics.mean(a.cost_bps for a in symbol_trades),
                "avg_quality_score": statistics.mean(
                    a.execution_quality.quality_score for a in symbol_trades
                ),
            }

        # Breakdown by session
        by_session = {}
        for session in TradingSession:
            session_trades = [
                a for a in analyses
                if a.classification.trading_session == session
            ]
            if session_trades:
                by_session[session.value] = {
                    "trade_count": len(session_trades),
                    "avg_slippage_bps": statistics.mean(
                        a.slippage.slippage_bps for a in session_trades
                    ),
                    "avg_cost_bps": statistics.mean(a.cost_bps for a in session_trades),
                    "avg_quality_score": statistics.mean(
                        a.execution_quality.quality_score for a in session_trades
                    ),
                }

        # Generate daily recommendations
        recommendations = self._generate_daily_recommendations(
            analyses, by_strategy, by_symbol, by_session
        )

        return DailySummary(
            date=date,
            total_trades=total_trades,
            total_volume=total_volume,
            avg_slippage_bps=avg_slippage_bps,
            avg_cost_bps=avg_cost_bps,
            avg_quality_score=avg_quality,
            total_fees=total_fees,
            total_slippage_cost=total_slippage,
            best_trade_id=best.trade_id,
            best_trade_score=best.execution_quality.quality_score,
            worst_trade_id=worst.trade_id,
            worst_trade_score=worst.execution_quality.quality_score,
            by_strategy=by_strategy,
            by_symbol=by_symbol,
            by_session=by_session,
            recommendations=recommendations,
        )

    def _generate_daily_recommendations(
        self,
        analyses: List[PostTradeAnalysisResult],
        by_strategy: Dict[str, Dict[str, Any]],
        by_symbol: Dict[str, Dict[str, Any]],
        by_session: Dict[str, Dict[str, Any]],
    ) -> List[str]:
        """
        Generate daily improvement recommendations

        Args:
            analyses: All analyses for the day
            by_strategy: Strategy breakdown
            by_symbol: Symbol breakdown
            by_session: Session breakdown

        Returns:
            List of recommendation strings
        """
        recommendations = []

        # Strategy with worst execution
        if by_strategy:
            worst_strategy = max(
                by_strategy.items(),
                key=lambda x: x[1]["avg_cost_bps"]
            )
            if worst_strategy[1]["avg_cost_bps"] > 15:
                recommendations.append(
                    f"Strategy '{worst_strategy[0]}' has highest costs "
                    f"({worst_strategy[1]['avg_cost_bps']:.1f}bps avg). "
                    "Review execution parameters for this strategy."
                )

        # Symbol with worst execution
        if by_symbol:
            worst_symbol = max(
                by_symbol.items(),
                key=lambda x: x[1]["avg_slippage_bps"]
            )
            if worst_symbol[1]["avg_slippage_bps"] > 10:
                recommendations.append(
                    f"Symbol '{worst_symbol[0]}' has highest slippage "
                    f"({worst_symbol[1]['avg_slippage_bps']:.1f}bps avg). "
                    "Consider different order types or timing."
                )

        # Session with worst execution
        if by_session:
            worst_session = max(
                by_session.items(),
                key=lambda x: x[1]["avg_cost_bps"]
            )
            best_session = min(
                by_session.items(),
                key=lambda x: x[1]["avg_cost_bps"]
            )
            if worst_session[0] != best_session[0]:
                cost_diff = worst_session[1]["avg_cost_bps"] - best_session[1]["avg_cost_bps"]
                if cost_diff > 5:
                    recommendations.append(
                        f"Execution costs are {cost_diff:.1f}bps higher in "
                        f"{worst_session[0]} session vs {best_session[0]}. "
                        "Consider shifting non-urgent trades."
                    )

        # High slippage trades
        high_slippage_count = sum(
            1 for a in analyses if a.slippage.slippage_bps > 15
        )
        if high_slippage_count > 0:
            pct = high_slippage_count / len(analyses) * 100
            recommendations.append(
                f"{high_slippage_count} trades ({pct:.0f}%) had slippage >15bps. "
                "Review order sizing and timing for these trades."
            )

        # Overall quality assessment
        avg_score = statistics.mean(a.execution_quality.quality_score for a in analyses)
        if avg_score < 60:
            recommendations.append(
                f"Average quality score is {avg_score:.0f}/100. "
                "Consider fundamental changes to execution approach."
            )
        elif avg_score >= 80:
            recommendations.append(
                f"Strong execution day with {avg_score:.0f}/100 avg score. "
                "Current approach is effective."
            )

        return recommendations

    def get_worst_executions(self, limit: int = 10) -> List[PostTradeAnalysisResult]:
        """
        Get the worst executed trades

        Args:
            limit: Maximum number of results

        Returns:
            List of worst trades sorted by quality score ascending
        """
        with self._lock:
            sorted_analyses = sorted(
                self._analyses.values(),
                key=lambda a: a.execution_quality.quality_score
            )
            return sorted_analyses[:limit]

    def get_best_executions(self, limit: int = 10) -> List[PostTradeAnalysisResult]:
        """
        Get the best executed trades

        Args:
            limit: Maximum number of results

        Returns:
            List of best trades sorted by quality score descending
        """
        with self._lock:
            sorted_analyses = sorted(
                self._analyses.values(),
                key=lambda a: a.execution_quality.quality_score,
                reverse=True
            )
            return sorted_analyses[:limit]

    def get_by_strategy(self, strategy: str) -> List[PostTradeAnalysisResult]:
        """
        Get all analyses for a specific strategy

        Args:
            strategy: Strategy name

        Returns:
            List of analyses for the strategy
        """
        with self._lock:
            return [
                a for a in self._analyses.values()
                if a.strategy == strategy
            ]

    def get_by_symbol(self, symbol: str) -> List[PostTradeAnalysisResult]:
        """
        Get all analyses for a specific symbol

        Args:
            symbol: Trading symbol

        Returns:
            List of analyses for the symbol
        """
        with self._lock:
            return [
                a for a in self._analyses.values()
                if a.symbol == symbol
            ]

    def get_improvement_recommendations(self) -> List[ImprovementRecommendation]:
        """
        Generate global improvement recommendations based on all analyses

        Returns:
            List of ImprovementRecommendation objects
        """
        with self._lock:
            if not self._analyses:
                return []

            recommendations = []

            # Analyze strategies
            for strategy, stats in self._strategy_stats.items():
                if stats["trade_count"] < 5:
                    continue

                avg_slippage = stats["total_slippage_bps"] / stats["trade_count"]
                avg_quality = statistics.mean(stats["quality_scores"]) if stats["quality_scores"] else 50

                if avg_slippage > 12:
                    recommendations.append(ImprovementRecommendation(
                        category="execution_strategy",
                        priority="high" if avg_slippage > 20 else "medium",
                        recommendation=(
                            f"Strategy '{strategy}' averaging {avg_slippage:.1f}bps slippage. "
                            "Consider implementing TWAP/VWAP for larger orders or "
                            "switching to limit orders."
                        ),
                        expected_savings_bps=avg_slippage * 0.3,  # Estimate 30% improvement
                        applicable_to=[strategy],
                        evidence={
                            "trade_count": stats["trade_count"],
                            "avg_slippage_bps": avg_slippage,
                            "avg_quality_score": avg_quality,
                        }
                    ))

            # Analyze symbols
            for symbol, stats in self._symbol_stats.items():
                if stats["trade_count"] < 5:
                    continue

                avg_slippage = stats["total_slippage_bps"] / stats["trade_count"]

                if avg_slippage > 15:
                    recommendations.append(ImprovementRecommendation(
                        category="symbol_selection",
                        priority="medium",
                        recommendation=(
                            f"Symbol '{symbol}' has consistently high slippage "
                            f"({avg_slippage:.1f}bps). Consider alternative pairs "
                            "or adjusting position sizes."
                        ),
                        expected_savings_bps=avg_slippage * 0.25,
                        applicable_to=[symbol],
                        evidence={
                            "trade_count": stats["trade_count"],
                            "avg_slippage_bps": avg_slippage,
                        }
                    ))

            # Session timing recommendations
            session_costs = {}
            for analysis in self._analyses.values():
                session = analysis.classification.trading_session.value
                if session not in session_costs:
                    session_costs[session] = []
                session_costs[session].append(analysis.cost_bps)

            if len(session_costs) >= 2:
                session_avgs = {
                    s: statistics.mean(costs)
                    for s, costs in session_costs.items()
                    if len(costs) >= 3
                }

                if session_avgs:
                    best_session = min(session_avgs.items(), key=lambda x: x[1])
                    worst_session = max(session_avgs.items(), key=lambda x: x[1])

                    cost_diff = worst_session[1] - best_session[1]
                    if cost_diff > 5:
                        recommendations.append(ImprovementRecommendation(
                            category="timing",
                            priority="medium" if cost_diff < 10 else "high",
                            recommendation=(
                                f"Trading during {best_session[0]} session saves "
                                f"~{cost_diff:.1f}bps vs {worst_session[0]} session. "
                                "Shift non-urgent orders to favorable sessions."
                            ),
                            expected_savings_bps=cost_diff * 0.5,
                            applicable_to=["all"],
                            evidence={
                                "best_session": best_session[0],
                                "best_session_cost": best_session[1],
                                "worst_session": worst_session[0],
                                "worst_session_cost": worst_session[1],
                            }
                        ))

            # Order type recommendations
            market_orders = [
                a for a in self._analyses.values()
                if a.classification.execution_style == ExecutionStyle.AGGRESSIVE
            ]
            limit_orders = [
                a for a in self._analyses.values()
                if a.classification.execution_style == ExecutionStyle.PASSIVE
            ]

            if market_orders and limit_orders:
                market_avg_slip = statistics.mean(a.slippage.slippage_bps for a in market_orders)
                limit_avg_slip = statistics.mean(a.slippage.slippage_bps for a in limit_orders)

                if market_avg_slip - limit_avg_slip > 5:
                    recommendations.append(ImprovementRecommendation(
                        category="order_type",
                        priority="medium",
                        recommendation=(
                            f"Limit orders save ~{market_avg_slip - limit_avg_slip:.1f}bps "
                            "vs market orders. Use limit orders for non-urgent trades."
                        ),
                        expected_savings_bps=market_avg_slip - limit_avg_slip,
                        applicable_to=["market_orders"],
                        evidence={
                            "market_order_count": len(market_orders),
                            "market_avg_slippage": market_avg_slip,
                            "limit_order_count": len(limit_orders),
                            "limit_avg_slippage": limit_avg_slip,
                        }
                    ))

            # Sort by priority and expected savings
            priority_order = {"high": 0, "medium": 1, "low": 2}
            recommendations.sort(
                key=lambda r: (priority_order.get(r.priority, 2), -r.expected_savings_bps)
            )

            return recommendations

    def get_strategy_stats(self, strategy: str) -> Dict[str, Any]:
        """
        Get aggregated statistics for a strategy

        Args:
            strategy: Strategy name

        Returns:
            Dictionary with strategy statistics
        """
        with self._lock:
            stats = self._strategy_stats.get(strategy)
            if not stats or stats["trade_count"] == 0:
                return {"error": f"No data for strategy: {strategy}"}

            return {
                "strategy": strategy,
                "trade_count": stats["trade_count"],
                "avg_slippage_bps": stats["total_slippage_bps"] / stats["trade_count"],
                "avg_cost_bps": stats["total_cost_bps"] / stats["trade_count"],
                "avg_quality_score": (
                    statistics.mean(stats["quality_scores"])
                    if stats["quality_scores"] else 0
                ),
                "min_quality_score": min(stats["quality_scores"]) if stats["quality_scores"] else 0,
                "max_quality_score": max(stats["quality_scores"]) if stats["quality_scores"] else 0,
            }

    def get_symbol_stats(self, symbol: str) -> Dict[str, Any]:
        """
        Get aggregated statistics for a symbol

        Args:
            symbol: Trading symbol

        Returns:
            Dictionary with symbol statistics
        """
        with self._lock:
            stats = self._symbol_stats.get(symbol)
            if not stats or stats["trade_count"] == 0:
                return {"error": f"No data for symbol: {symbol}"}

            return {
                "symbol": symbol,
                "trade_count": stats["trade_count"],
                "avg_slippage_bps": stats["total_slippage_bps"] / stats["trade_count"],
                "avg_cost_bps": stats["total_cost_bps"] / stats["trade_count"],
                "avg_quality_score": (
                    statistics.mean(stats["quality_scores"])
                    if stats["quality_scores"] else 0
                ),
                "min_quality_score": min(stats["quality_scores"]) if stats["quality_scores"] else 0,
                "max_quality_score": max(stats["quality_scores"]) if stats["quality_scores"] else 0,
            }

    def get_summary(self) -> Dict[str, Any]:
        """
        Get overall summary of all post-trade analyses

        Returns:
            Dictionary with overall statistics
        """
        with self._lock:
            if not self._analyses:
                return {
                    "total_analyses": 0,
                    "message": "No trades analyzed yet",
                }

            all_analyses = list(self._analyses.values())

            return {
                "total_analyses": len(all_analyses),
                "avg_slippage_bps": statistics.mean(
                    a.slippage.slippage_bps for a in all_analyses
                ),
                "avg_cost_bps": statistics.mean(a.cost_bps for a in all_analyses),
                "avg_quality_score": statistics.mean(
                    a.execution_quality.quality_score for a in all_analyses
                ),
                "total_slippage_cost": sum(a.slippage.total_slippage for a in all_analyses),
                "total_fees": sum(a.fees for a in all_analyses),
                "unique_strategies": len(self._strategy_stats),
                "unique_symbols": len(self._symbol_stats),
                "quality_distribution": {
                    "excellent": sum(
                        1 for a in all_analyses
                        if a.execution_quality.quality_grade == ExecutionQualityGrade.EXCELLENT
                    ),
                    "good": sum(
                        1 for a in all_analyses
                        if a.execution_quality.quality_grade == ExecutionQualityGrade.GOOD
                    ),
                    "fair": sum(
                        1 for a in all_analyses
                        if a.execution_quality.quality_grade == ExecutionQualityGrade.FAIR
                    ),
                    "poor": sum(
                        1 for a in all_analyses
                        if a.execution_quality.quality_grade == ExecutionQualityGrade.POOR
                    ),
                    "very_poor": sum(
                        1 for a in all_analyses
                        if a.execution_quality.quality_grade == ExecutionQualityGrade.VERY_POOR
                    ),
                },
            }

    def reset(self) -> None:
        """Reset all stored analyses and statistics"""
        with self._lock:
            self._analyses.clear()
            self._daily_summaries.clear()
            self._strategy_stats.clear()
            self._symbol_stats.clear()
            logger.info("PostTradeAnalyzer reset to initial state")


# =============================================================================
# GLOBAL INSTANCE MANAGEMENT (THREAD-SAFE SINGLETON)
# =============================================================================

_post_trade_analyzer: Optional[PostTradeAnalyzer] = None
_instance_lock: threading.Lock = threading.Lock()


def get_post_trade_analyzer(
    default_maker_fee_bps: float = 2.0,
    default_taker_fee_bps: float = 5.0,
    slippage_alert_threshold_bps: float = 20.0,
) -> PostTradeAnalyzer:
    """
    Get or create the global PostTradeAnalyzer instance

    Thread-safe singleton pattern ensures only one instance exists.

    Args:
        default_maker_fee_bps: Default maker fee in basis points
        default_taker_fee_bps: Default taker fee in basis points
        slippage_alert_threshold_bps: Threshold for slippage alerts

    Returns:
        Global PostTradeAnalyzer instance

    Example:
        >>> analyzer = get_post_trade_analyzer()
        >>> result = analyzer.analyze_trade(trade_data)
    """
    global _post_trade_analyzer

    with _instance_lock:
        if _post_trade_analyzer is None:
            _post_trade_analyzer = PostTradeAnalyzer(
                default_maker_fee_bps=default_maker_fee_bps,
                default_taker_fee_bps=default_taker_fee_bps,
                slippage_alert_threshold_bps=slippage_alert_threshold_bps,
            )
            logger.info("Created new PostTradeAnalyzer instance")

        return _post_trade_analyzer


def reset_post_trade_analyzer() -> None:
    """
    Reset the global PostTradeAnalyzer instance

    Useful for testing or starting fresh analysis.
    """
    global _post_trade_analyzer

    with _instance_lock:
        _post_trade_analyzer = None
        logger.info("Global PostTradeAnalyzer reset")
