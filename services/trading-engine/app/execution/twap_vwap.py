"""
TWAP/VWAP Execution Algorithms - Time and Volume Weighted Execution
Phase 4.1: Smart Order Routing - Algorithmic Execution Component

Purpose:
- Execute large orders using Time-Weighted Average Price (TWAP) strategy
- Execute large orders using Volume-Weighted Average Price (VWAP) strategy
- Minimize market impact through intelligent order slicing
- Track execution vs benchmarks for performance analysis
- Adapt execution based on market conditions and fill rates
- Monitor slippage and adjust execution parameters in real-time

Research Sources:
- Almgren-Chriss Optimal Execution Framework
- VWAP Execution Algorithms (Konishi, 2002)
- Implementation Shortfall Analysis (Perold, 1988)
- Market Microstructure and Optimal Execution (Kissell & Glantz)
- Crypto Market Liquidity Patterns

TWAP Strategy:
- Splits order into equal-sized chunks
- Executes chunks at regular time intervals
- Minimizes timing risk, simple to implement
- Best for: Low urgency, stable markets
- Participation rate: 10-30% of market volume

VWAP Strategy:
- Splits order based on historical volume patterns
- Matches execution to intraday volume curve
- Minimizes market impact, tracks VWAP benchmark
- Best for: Following market rhythm, benchmark tracking
- Adaptive scheduling based on volume profile

Created: 2025-12-11
Author: Backend Developer Agent
"""

import asyncio
import logging
import random
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

# Configure logging for TWAP/VWAP execution
logger = logging.getLogger(__name__)


# ============================================================================
# ENUMERATIONS
# ============================================================================


class ExecutionState(str, Enum):
    """
    Execution state for algorithmic orders

    PENDING: Order created, not yet started
    RUNNING: Currently executing chunks
    PAUSED: Temporarily paused by user/system
    COMPLETED: All chunks executed successfully
    CANCELLED: Execution cancelled by user
    FAILED: Execution failed due to error
    """
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class AdaptiveMode(str, Enum):
    """
    Adaptive execution modes for dynamic adjustment

    PASSIVE: Maintain schedule, no urgency
    NEUTRAL: Minor adjustments based on fill rate
    AGGRESSIVE: Catch up if behind schedule
    URGENT: Execute remaining ASAP
    """
    PASSIVE = "passive"
    NEUTRAL = "neutral"
    AGGRESSIVE = "aggressive"
    URGENT = "urgent"


class BenchmarkType(str, Enum):
    """
    Benchmark types for execution quality measurement

    ARRIVAL_PRICE: Price when order was submitted
    MARKET_VWAP: Volume-weighted average market price
    TWAP: Time-weighted average market price
    CLOSE_PRICE: Closing price of period
    """
    ARRIVAL_PRICE = "arrival_price"
    MARKET_VWAP = "market_vwap"
    TWAP = "twap"
    CLOSE_PRICE = "close_price"


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class TWAPConfig:
    """
    Configuration for TWAP (Time-Weighted Average Price) execution

    Controls how orders are split and executed over time:
    - num_chunks: Number of equal-sized order slices
    - interval_seconds: Time between chunk executions
    - participation_rate: Target % of market volume per interval
    - randomize_timing: Add randomness to avoid detection
    - randomize_size: Vary chunk sizes slightly
    """
    # Chunk scheduling
    num_chunks: int = 10                        # Number of slices
    interval_seconds: int = 60                  # 1 minute intervals

    # Market participation
    participation_rate: float = 0.15            # 15% of volume per interval
    max_participation_rate: float = 0.30        # Max 30% of volume

    # Randomization (avoid pattern detection)
    randomize_timing: bool = True               # Add ±20% time variance
    randomize_size: bool = True                 # Add ±10% size variance
    timing_variance_pct: float = 0.20           # ±20% time randomization
    size_variance_pct: float = 0.10             # ±10% size randomization

    # Adaptive behavior
    adaptive_mode: AdaptiveMode = AdaptiveMode.NEUTRAL
    catchup_threshold: float = 0.80             # Catch up if <80% filled

    # Risk controls
    max_slippage_pct: float = 0.10              # 0.1% max slippage per chunk
    pause_on_high_slippage: bool = True         # Auto-pause if exceeded

    # Execution parameters
    use_limit_orders: bool = True               # Prefer limit over market
    limit_offset_bps: float = 5.0               # 5 basis points offset
    chunk_timeout_seconds: int = 30             # Cancel unfilled after 30s


@dataclass
class VWAPConfig:
    """
    Configuration for VWAP (Volume-Weighted Average Price) execution

    Volume-aware scheduling to match market rhythm:
    - volume_profile_periods: Historical periods for volume analysis
    - min_chunk_size_pct: Minimum chunk as % of total order
    - volume_forecast_method: How to predict future volume
    - benchmark_tracking: Track vs market VWAP
    """
    # Volume analysis
    volume_profile_periods: int = 20            # 20 periods of historical data
    volume_smoothing_factor: float = 0.3        # EMA smoothing for volume

    # Chunk sizing
    min_chunk_size_pct: float = 0.02            # Min 2% of order per chunk
    max_chunk_size_pct: float = 0.25            # Max 25% of order per chunk

    # Market participation
    participation_rate: float = 0.15            # 15% of forecasted volume
    max_participation_rate: float = 0.30        # Max 30% of volume

    # Volume forecasting
    volume_forecast_method: str = "historical_average"  # or "ema", "median"
    volume_safety_factor: float = 0.80          # Use 80% of forecast (conservative)

    # Adaptive behavior
    adaptive_mode: AdaptiveMode = AdaptiveMode.NEUTRAL
    catchup_aggressive_pct: float = 1.50        # 50% more aggressive when catching up

    # Benchmark tracking
    benchmark_type: BenchmarkType = BenchmarkType.MARKET_VWAP
    track_slippage: bool = True
    max_slippage_pct: float = 0.10              # 0.1% max vs VWAP

    # Execution parameters
    use_limit_orders: bool = True
    limit_offset_bps: float = 5.0
    chunk_timeout_seconds: int = 30


@dataclass
class ChunkSchedule:
    """
    Individual chunk in execution schedule

    Represents one slice of the parent order to be executed:
    - chunk_id: Unique identifier within parent order
    - quantity: Amount to execute in this chunk
    - scheduled_time: When to execute (can be adjusted)
    - target_participation: Expected % of market volume
    """
    chunk_id: int
    quantity: Decimal
    scheduled_time: datetime
    target_participation: float = 0.15

    # Execution tracking
    status: ExecutionState = ExecutionState.PENDING
    executed_quantity: Decimal = Decimal("0")
    average_price: Decimal = Decimal("0")
    slippage_pct: float = 0.0

    # Timing
    execution_started_at: Optional[datetime] = None
    execution_completed_at: Optional[datetime] = None

    # Market context
    market_volume_at_execution: Optional[float] = None
    actual_participation: Optional[float] = None


@dataclass
class ExecutionBenchmark:
    """
    Benchmark tracking for execution quality analysis

    Compares actual execution against various benchmarks:
    - arrival_price: Price when order was first submitted
    - market_vwap: Volume-weighted average price of market
    - market_twap: Time-weighted average price of market
    - execution_vwap: Our actual volume-weighted price
    """
    symbol: str
    side: str

    # Benchmark prices
    arrival_price: Decimal                      # Price at order submission
    market_vwap: Decimal                        # Market VWAP during execution
    market_twap: Decimal                        # Market TWAP during execution
    close_price: Optional[Decimal] = None      # Closing price (if available)

    # Execution results
    execution_vwap: Decimal = Decimal("0")     # Our weighted average price
    execution_twap: Decimal = Decimal("0")     # Our time-weighted price

    # Performance metrics
    slippage_vs_arrival_pct: float = 0.0       # % vs arrival price
    slippage_vs_vwap_pct: float = 0.0          # % vs market VWAP
    slippage_vs_twap_pct: float = 0.0          # % vs market TWAP

    # Execution details
    total_quantity: Decimal = Decimal("0")
    total_value: Decimal = Decimal("0")
    num_chunks: int = 0
    chunks_executed: int = 0

    # Timing
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0


@dataclass
class SlippageAlert:
    """
    Alert for excessive slippage detection

    Triggered when slippage exceeds acceptable thresholds:
    - severity: How serious the slippage is
    - chunk_id: Which chunk caused the alert
    - recommended_action: What should be done
    """
    timestamp: datetime
    chunk_id: int
    severity: str  # "warning", "critical"
    slippage_pct: float
    threshold_pct: float
    message: str
    recommended_action: str  # "pause", "cancel", "continue_monitor"


@dataclass
class AlgorithmMetrics:
    """
    Aggregate metrics for algorithm execution tracking

    Comprehensive statistics across all chunks:
    - fill_rate: % of target quantity successfully filled
    - avg_slippage: Average slippage across all chunks
    - participation_rate: Actual vs target market participation
    - cost_savings: Estimated savings vs immediate execution
    """
    algorithm_type: str  # "TWAP" or "VWAP"

    # Fill metrics
    total_target_quantity: Decimal = Decimal("0")
    total_filled_quantity: Decimal = Decimal("0")
    fill_rate: float = 0.0                     # 0-1

    # Slippage metrics
    avg_slippage_pct: float = 0.0
    max_slippage_pct: float = 0.0
    min_slippage_pct: float = 0.0
    slippage_std_dev: float = 0.0

    # Participation metrics
    target_participation_rate: float = 0.15
    actual_participation_rate: float = 0.0

    # Cost analysis
    total_cost_usd: float = 0.0
    estimated_market_cost_usd: float = 0.0     # If done immediately
    cost_savings_usd: float = 0.0
    cost_savings_pct: float = 0.0

    # Execution quality
    chunks_completed: int = 0
    chunks_failed: int = 0
    chunks_cancelled: int = 0
    success_rate: float = 0.0

    # Timing
    avg_execution_time_per_chunk_ms: float = 0.0
    total_duration_seconds: float = 0.0

    # Benchmark comparison
    benchmark_slippage_pct: float = 0.0        # vs chosen benchmark

    # Last update
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================================
# SUPPORTING CLASSES
# ============================================================================


class SlippageTracker:
    """
    Monitors slippage and generates alerts

    Tracks slippage across chunks and triggers alerts when thresholds
    are exceeded. Maintains history for trend analysis.
    """

    def __init__(self, max_slippage_pct: float = 0.10):
        """
        Initialize slippage tracker

        Args:
            max_slippage_pct: Maximum acceptable slippage (0.1% default)
        """
        self.max_slippage_pct = max_slippage_pct
        self.warning_threshold_pct = max_slippage_pct * 0.75  # 75% of max

        # Slippage history
        self._slippage_history: deque = deque(maxlen=100)
        self._alerts: List[SlippageAlert] = []

        logger.debug(f"SlippageTracker initialized: max={max_slippage_pct:.3%}")

    def record_slippage(
        self,
        chunk_id: int,
        slippage_pct: float,
        expected_price: Decimal,
        actual_price: Decimal
    ) -> Optional[SlippageAlert]:
        """
        Record chunk slippage and check for alerts

        Args:
            chunk_id: Identifier of executed chunk
            slippage_pct: Actual slippage percentage
            expected_price: Expected execution price
            actual_price: Actual execution price

        Returns:
            SlippageAlert if threshold exceeded, None otherwise
        """
        # Record in history
        self._slippage_history.append({
            "chunk_id": chunk_id,
            "slippage_pct": slippage_pct,
            "timestamp": datetime.now(timezone.utc)
        })

        # Check for alerts
        alert = None

        if abs(slippage_pct) >= self.max_slippage_pct:
            # Critical alert
            alert = SlippageAlert(
                timestamp=datetime.now(timezone.utc),
                chunk_id=chunk_id,
                severity="critical",
                slippage_pct=slippage_pct,
                threshold_pct=self.max_slippage_pct,
                message=f"Critical slippage {slippage_pct:.3%} exceeds max {self.max_slippage_pct:.3%}",
                recommended_action="pause"
            )
            self._alerts.append(alert)
            logger.warning(f"CRITICAL SLIPPAGE: chunk={chunk_id}, slippage={slippage_pct:.3%}")

        elif abs(slippage_pct) >= self.warning_threshold_pct:
            # Warning alert
            alert = SlippageAlert(
                timestamp=datetime.now(timezone.utc),
                chunk_id=chunk_id,
                severity="warning",
                slippage_pct=slippage_pct,
                threshold_pct=self.warning_threshold_pct,
                message=f"Elevated slippage {slippage_pct:.3%} approaching max {self.max_slippage_pct:.3%}",
                recommended_action="continue_monitor"
            )
            self._alerts.append(alert)
            logger.info(f"Slippage warning: chunk={chunk_id}, slippage={slippage_pct:.3%}")

        return alert

    def get_average_slippage(self, recent_n: Optional[int] = None) -> float:
        """Calculate average slippage from recent chunks"""
        if not self._slippage_history:
            return 0.0

        recent = list(self._slippage_history)
        if recent_n:
            recent = recent[-recent_n:]

        return statistics.mean(r["slippage_pct"] for r in recent)

    def get_slippage_trend(self) -> str:
        """Analyze slippage trend: improving, worsening, stable"""
        if len(self._slippage_history) < 5:
            return "insufficient_data"

        recent = list(self._slippage_history)[-10:]
        first_half = recent[:len(recent)//2]
        second_half = recent[len(recent)//2:]

        avg_first = statistics.mean(abs(r["slippage_pct"]) for r in first_half)
        avg_second = statistics.mean(abs(r["slippage_pct"]) for r in second_half)

        if avg_second < avg_first * 0.9:
            return "improving"
        elif avg_second > avg_first * 1.1:
            return "worsening"
        else:
            return "stable"

    def get_alerts(self, severity: Optional[str] = None) -> List[SlippageAlert]:
        """Get slippage alerts, optionally filtered by severity"""
        if severity:
            return [a for a in self._alerts if a.severity == severity]
        return self._alerts.copy()


class MarketImpactEstimator:
    """
    Estimates market impact for order execution

    Uses historical data and order book analysis to predict
    how execution will affect market price.
    """

    def __init__(self):
        """Initialize market impact estimator"""
        # Impact history for calibration
        self._impact_history: deque = deque(maxlen=100)

        # Kyle's lambda (market impact coefficient)
        self._kyle_lambda: float = 0.01  # Default, calibrated over time

        logger.debug("MarketImpactEstimator initialized")

    def estimate_impact(
        self,
        quantity: Decimal,
        avg_volume: float,
        spread_pct: float,
        liquidity_usd: float
    ) -> Dict[str, float]:
        """
        Estimate market impact for a given quantity

        Uses Kyle's model: Impact = lambda * (quantity / avg_volume)

        Args:
            quantity: Order quantity
            avg_volume: Average market volume
            spread_pct: Current bid-ask spread
            liquidity_usd: Available liquidity in USD

        Returns:
            Dictionary with impact estimates
        """
        # Calculate order size as % of volume
        if avg_volume > 0:
            volume_pct = float(quantity) / avg_volume
        else:
            volume_pct = 1.0  # Conservative: assume full volume

        # Base impact from Kyle's model
        base_impact_pct = self._kyle_lambda * volume_pct * 100

        # Adjust for spread
        spread_impact = spread_pct / 2  # Half-spread crossing

        # Adjust for liquidity
        quantity_usd = float(quantity * Decimal("50000"))  # Estimate
        if liquidity_usd > 0:
            liquidity_factor = min(2.0, quantity_usd / liquidity_usd)
        else:
            liquidity_factor = 2.0

        # Total impact
        temporary_impact = base_impact_pct * liquidity_factor + spread_impact
        permanent_impact = temporary_impact * 0.3  # ~30% persists
        total_impact = temporary_impact + permanent_impact

        return {
            "temporary_impact_pct": temporary_impact,
            "permanent_impact_pct": permanent_impact,
            "total_impact_pct": total_impact,
            "volume_pct": volume_pct * 100,
            "liquidity_factor": liquidity_factor
        }

    def record_actual_impact(
        self,
        estimated_impact: float,
        actual_impact: float,
        quantity: Decimal,
        volume: float
    ):
        """Record actual impact to calibrate estimator"""
        self._impact_history.append({
            "estimated": estimated_impact,
            "actual": actual_impact,
            "quantity": quantity,
            "volume": volume,
            "timestamp": datetime.now(timezone.utc)
        })

        # Recalibrate Kyle's lambda if enough data
        if len(self._impact_history) >= 20:
            self._recalibrate_lambda()

    def _recalibrate_lambda(self):
        """Recalibrate Kyle's lambda based on actual vs estimated"""
        recent = list(self._impact_history)[-50:]

        if not recent:
            return

        # Calculate average ratio of actual to estimated
        ratios = []
        for record in recent:
            if record["estimated"] > 0:
                ratio = record["actual"] / record["estimated"]
                ratios.append(ratio)

        if ratios:
            avg_ratio = statistics.mean(ratios)
            # Adjust lambda (dampened adjustment)
            self._kyle_lambda *= (0.9 + 0.1 * avg_ratio)
            self._kyle_lambda = max(0.001, min(0.05, self._kyle_lambda))

            logger.debug(f"Recalibrated Kyle's lambda: {self._kyle_lambda:.4f}")


class AlgorithmMetricsAggregator:
    """
    Aggregates metrics across all chunks for final reporting

    Collects execution data from individual chunks and computes
    comprehensive algorithm-level statistics.
    """

    def __init__(self, algorithm_type: str, target_quantity: Decimal):
        """
        Initialize metrics aggregator

        Args:
            algorithm_type: "TWAP" or "VWAP"
            target_quantity: Total quantity to be executed
        """
        self.algorithm_type = algorithm_type
        self.metrics = AlgorithmMetrics(
            algorithm_type=algorithm_type,
            total_target_quantity=target_quantity
        )

        # Chunk-level data
        self._chunk_data: List[Dict] = []

        logger.debug(f"MetricsAggregator initialized: {algorithm_type}, target={target_quantity}")

    def add_chunk_result(
        self,
        chunk_id: int,
        quantity: Decimal,
        filled_quantity: Decimal,
        avg_price: Decimal,
        slippage_pct: float,
        execution_time_ms: float,
        status: ExecutionState
    ):
        """Record result from individual chunk execution"""
        self._chunk_data.append({
            "chunk_id": chunk_id,
            "quantity": quantity,
            "filled_quantity": filled_quantity,
            "avg_price": avg_price,
            "slippage_pct": slippage_pct,
            "execution_time_ms": execution_time_ms,
            "status": status
        })

        # Update aggregate metrics
        self._recalculate_metrics()

    def _recalculate_metrics(self):
        """Recalculate all aggregate metrics from chunk data"""
        if not self._chunk_data:
            return

        # Fill metrics
        total_filled = sum(Decimal(str(c["filled_quantity"])) for c in self._chunk_data)
        self.metrics.total_filled_quantity = total_filled
        self.metrics.fill_rate = float(total_filled / self.metrics.total_target_quantity) if self.metrics.total_target_quantity > 0 else 0.0

        # Slippage metrics
        slippages = [c["slippage_pct"] for c in self._chunk_data if c["status"] == ExecutionState.COMPLETED]
        if slippages:
            self.metrics.avg_slippage_pct = statistics.mean(slippages)
            self.metrics.max_slippage_pct = max(slippages)
            self.metrics.min_slippage_pct = min(slippages)
            if len(slippages) > 1:
                self.metrics.slippage_std_dev = statistics.stdev(slippages)

        # Execution counts
        self.metrics.chunks_completed = sum(1 for c in self._chunk_data if c["status"] == ExecutionState.COMPLETED)
        self.metrics.chunks_failed = sum(1 for c in self._chunk_data if c["status"] == ExecutionState.FAILED)
        self.metrics.chunks_cancelled = sum(1 for c in self._chunk_data if c["status"] == ExecutionState.CANCELLED)

        total_chunks = len(self._chunk_data)
        self.metrics.success_rate = self.metrics.chunks_completed / total_chunks if total_chunks > 0 else 0.0

        # Timing
        exec_times = [c["execution_time_ms"] for c in self._chunk_data if c["execution_time_ms"] > 0]
        if exec_times:
            self.metrics.avg_execution_time_per_chunk_ms = statistics.mean(exec_times)

        self.metrics.last_updated = datetime.now(timezone.utc)

    def get_metrics(self) -> AlgorithmMetrics:
        """Get current aggregate metrics"""
        return self.metrics


# ============================================================================
# TWAP ALGORITHM
# ============================================================================


class TWAPAlgorithm:
    """
    Time-Weighted Average Price (TWAP) Execution Algorithm

    Splits a large order into equal-sized chunks executed at regular
    time intervals. Minimizes timing risk and is simple to implement.

    Features:
    - Equal chunk sizing with optional randomization
    - Regular time intervals with optional variance
    - Participation rate control
    - Pause/resume/cancel capabilities
    - Adaptive timing based on fill rate
    - Slippage monitoring and auto-pause

    Usage:
        config = TWAPConfig(num_chunks=10, interval_seconds=60)
        twap = TWAPAlgorithm(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1.5"),
            config=config
        )

        # Create schedule
        schedule = twap.create_chunk_schedule()

        # Execute
        result = await twap.execute(execute_func=place_order_func)
    """

    def __init__(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        config: Optional[TWAPConfig] = None,
        arrival_price: Optional[Decimal] = None
    ):
        """
        Initialize TWAP algorithm

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            side: "BUY" or "SELL"
            quantity: Total quantity to execute
            config: TWAP configuration
            arrival_price: Price at order submission (for benchmarking)
        """
        self.symbol = symbol
        self.side = side.upper()
        self.quantity = quantity
        self.config = config or TWAPConfig()

        # State
        self.state = ExecutionState.PENDING
        self.schedule: List[ChunkSchedule] = []
        self._current_chunk_index = 0

        # Tracking
        self.slippage_tracker = SlippageTracker(self.config.max_slippage_pct)
        self.impact_estimator = MarketImpactEstimator()
        self.metrics_aggregator = AlgorithmMetricsAggregator("TWAP", quantity)

        # Benchmark
        self.benchmark = ExecutionBenchmark(
            symbol=symbol,
            side=side,
            arrival_price=arrival_price or Decimal("0"),
            market_vwap=Decimal("0"),
            market_twap=Decimal("0"),
            total_quantity=quantity,
            num_chunks=self.config.num_chunks
        )

        # Control
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused initially
        self._cancel_flag = False

        logger.info(
            f"TWAPAlgorithm initialized: {symbol} {side} {quantity}, "
            f"chunks={self.config.num_chunks}, interval={self.config.interval_seconds}s"
        )

    def calculate_max_chunk_size(
        self,
        avg_market_volume: float,
        participation_rate: Optional[float] = None
    ) -> Decimal:
        """
        Calculate maximum chunk size based on participation rate

        Ensures each chunk doesn't exceed target % of market volume.

        Args:
            avg_market_volume: Average market volume per interval
            participation_rate: Override config participation rate

        Returns:
            Maximum chunk size in base currency
        """
        rate = participation_rate or self.config.participation_rate
        max_size = Decimal(str(avg_market_volume * rate))

        # Enforce maximum participation cap
        if rate > self.config.max_participation_rate:
            logger.warning(
                f"Participation rate {rate:.2%} exceeds max {self.config.max_participation_rate:.2%}, "
                f"capping at max"
            )
            max_size = Decimal(str(avg_market_volume * self.config.max_participation_rate))

        logger.debug(
            f"Max chunk size: {max_size} (volume={avg_market_volume}, rate={rate:.2%})"
        )

        return max_size

    def create_chunk_schedule(
        self,
        start_time: Optional[datetime] = None,
        avg_market_volume: Optional[float] = None
    ) -> List[ChunkSchedule]:
        """
        Create TWAP execution schedule with equal-sized chunks

        Splits the order into equal chunks scheduled at regular intervals.
        Optionally applies randomization to timing and sizing.

        Args:
            start_time: When to start execution (default: now)
            avg_market_volume: Average volume for participation calc

        Returns:
            List of ChunkSchedule objects
        """
        if start_time is None:
            start_time = datetime.now(timezone.utc)

        # Calculate base chunk size
        base_chunk_size = self.quantity / self.config.num_chunks

        # Apply participation rate constraint if volume provided
        if avg_market_volume:
            max_chunk = self.calculate_max_chunk_size(avg_market_volume)
            if base_chunk_size > max_chunk:
                logger.warning(
                    f"Base chunk size {base_chunk_size} exceeds max {max_chunk}, "
                    f"increasing number of chunks"
                )
                # Increase number of chunks to respect participation
                self.config.num_chunks = int(float(self.quantity / max_chunk)) + 1
                base_chunk_size = self.quantity / self.config.num_chunks

        schedule = []
        cumulative_qty = Decimal("0")

        for i in range(self.config.num_chunks):
            # Calculate chunk quantity with optional randomization
            if self.config.randomize_size and i < self.config.num_chunks - 1:
                # Add ±10% variance
                variance = random.uniform(
                    -self.config.size_variance_pct,
                    self.config.size_variance_pct
                )
                chunk_qty = base_chunk_size * Decimal(str(1 + variance))
            else:
                chunk_qty = base_chunk_size

            # Last chunk gets remainder to ensure exact total
            if i == self.config.num_chunks - 1:
                chunk_qty = self.quantity - cumulative_qty

            cumulative_qty += chunk_qty

            # Calculate scheduled time with optional randomization
            base_time = start_time + timedelta(
                seconds=i * self.config.interval_seconds
            )

            if self.config.randomize_timing and i > 0:
                # Add ±20% variance to interval
                variance_seconds = int(
                    self.config.interval_seconds *
                    self.config.timing_variance_pct *
                    random.uniform(-1, 1)
                )
                scheduled_time = base_time + timedelta(seconds=variance_seconds)
            else:
                scheduled_time = base_time

            # Create chunk
            chunk = ChunkSchedule(
                chunk_id=i + 1,
                quantity=chunk_qty,
                scheduled_time=scheduled_time,
                target_participation=self.config.participation_rate
            )

            schedule.append(chunk)

        self.schedule = schedule
        self.benchmark.num_chunks = len(schedule)

        logger.info(
            f"Created TWAP schedule: {len(schedule)} chunks, "
            f"avg_size={base_chunk_size:.4f}, "
            f"duration={len(schedule) * self.config.interval_seconds}s"
        )

        return schedule

    async def execute(
        self,
        execute_func: Callable,
        get_market_data_func: Optional[Callable] = None
    ) -> AlgorithmMetrics:
        """
        Execute TWAP algorithm

        Executes chunks according to schedule, with pause/resume/cancel
        support and adaptive timing.

        Args:
            execute_func: Async function to execute individual orders
            get_market_data_func: Optional function to get market data

        Returns:
            AlgorithmMetrics with execution results
        """
        if not self.schedule:
            raise ValueError("No schedule created. Call create_chunk_schedule() first")

        self.state = ExecutionState.RUNNING
        self.benchmark.start_time = datetime.now(timezone.utc)

        logger.info(f"Starting TWAP execution: {len(self.schedule)} chunks")

        try:
            for i, chunk in enumerate(self.schedule):
                self._current_chunk_index = i

                # Check for cancellation
                if self._cancel_flag:
                    logger.info("TWAP execution cancelled by user")
                    self.state = ExecutionState.CANCELLED
                    break

                # Wait for scheduled time
                await self._wait_until_scheduled(chunk.scheduled_time)

                # Wait if paused
                await self._pause_event.wait()

                # Execute chunk
                await self._execute_chunk(chunk, execute_func, get_market_data_func)

                # Check slippage and potentially pause
                if self.config.pause_on_high_slippage:
                    alert = self.slippage_tracker.get_alerts(severity="critical")
                    if alert:
                        logger.warning("High slippage detected, pausing execution")
                        self.pause()
                        # Wait for manual resume
                        await self._pause_event.wait()

                # Adaptive timing adjustment
                if self.config.adaptive_mode != AdaptiveMode.PASSIVE:
                    self._adjust_remaining_schedule()

            # Mark as completed if all chunks done
            if all(c.status in (ExecutionState.COMPLETED, ExecutionState.FAILED) for c in self.schedule):
                self.state = ExecutionState.COMPLETED

            self.benchmark.end_time = datetime.now(timezone.utc)
            self.benchmark.duration_seconds = (
                self.benchmark.end_time - self.benchmark.start_time
            ).total_seconds()

            logger.info(
                f"TWAP execution finished: state={self.state.value}, "
                f"fill_rate={self.metrics_aggregator.metrics.fill_rate:.2%}"
            )

        except Exception as e:
            logger.error(f"TWAP execution failed: {e}", exc_info=True)
            self.state = ExecutionState.FAILED
            raise

        return self.metrics_aggregator.get_metrics()

    async def _execute_chunk(
        self,
        chunk: ChunkSchedule,
        execute_func: Callable,
        get_market_data_func: Optional[Callable]
    ):
        """Execute individual chunk"""
        chunk.status = ExecutionState.RUNNING
        chunk.execution_started_at = datetime.now(timezone.utc)

        try:
            # Prepare order parameters
            params = {
                "symbol": self.symbol,
                "side": self.side,
                "quantity": str(chunk.quantity),
                "order_type": "Limit" if self.config.use_limit_orders else "Market"
            }

            # Add limit price if using limit orders
            if self.config.use_limit_orders and get_market_data_func:
                market_data = await get_market_data_func(self.symbol)
                mid_price = (market_data["best_bid"] + market_data["best_ask"]) / 2

                # Offset for better fill probability
                offset = mid_price * Decimal(str(self.config.limit_offset_bps / 10000))
                if self.side == "BUY":
                    limit_price = mid_price + offset
                else:
                    limit_price = mid_price - offset

                params["price"] = str(limit_price)
                params["time_in_force"] = "GTC"

            # Execute order
            result = await execute_func(**params)

            # Process result
            chunk.executed_quantity = Decimal(str(result.get("filled_quantity", 0)))
            chunk.average_price = Decimal(str(result.get("avg_price", 0)))

            # Calculate slippage
            if chunk.average_price > 0 and self.benchmark.arrival_price > 0:
                if self.side == "BUY":
                    chunk.slippage_pct = float(
                        (chunk.average_price - self.benchmark.arrival_price) /
                        self.benchmark.arrival_price
                    ) * 100
                else:
                    chunk.slippage_pct = float(
                        (self.benchmark.arrival_price - chunk.average_price) /
                        self.benchmark.arrival_price
                    ) * 100

            # Track slippage
            self.slippage_tracker.record_slippage(
                chunk.chunk_id,
                chunk.slippage_pct,
                self.benchmark.arrival_price,
                chunk.average_price
            )

            chunk.status = ExecutionState.COMPLETED
            chunk.execution_completed_at = datetime.now(timezone.utc)

            # Update metrics
            exec_time_ms = (
                chunk.execution_completed_at - chunk.execution_started_at
            ).total_seconds() * 1000

            self.metrics_aggregator.add_chunk_result(
                chunk.chunk_id,
                chunk.quantity,
                chunk.executed_quantity,
                chunk.average_price,
                chunk.slippage_pct,
                exec_time_ms,
                chunk.status
            )

            logger.info(
                f"Chunk {chunk.chunk_id} executed: "
                f"qty={chunk.executed_quantity}/{chunk.quantity}, "
                f"price={chunk.average_price}, slippage={chunk.slippage_pct:.3f}%"
            )

        except Exception as e:
            chunk.status = ExecutionState.FAILED
            logger.error(f"Chunk {chunk.chunk_id} failed: {e}")

            self.metrics_aggregator.add_chunk_result(
                chunk.chunk_id,
                chunk.quantity,
                Decimal("0"),
                Decimal("0"),
                0.0,
                0.0,
                ExecutionState.FAILED
            )

    async def _wait_until_scheduled(self, scheduled_time: datetime):
        """Wait until chunk scheduled time"""
        now = datetime.now(timezone.utc)
        if scheduled_time > now:
            wait_seconds = (scheduled_time - now).total_seconds()
            if wait_seconds > 0:
                logger.debug(f"Waiting {wait_seconds:.1f}s until scheduled time")
                await asyncio.sleep(wait_seconds)

    def _adjust_remaining_schedule(self):
        """Adjust timing of remaining chunks based on fill rate"""
        metrics = self.metrics_aggregator.get_metrics()

        # If behind schedule, speed up
        if (
            metrics.fill_rate < self.config.catchup_threshold and
            self.config.adaptive_mode in (AdaptiveMode.AGGRESSIVE, AdaptiveMode.URGENT)
        ):
            # Reduce interval for remaining chunks
            remaining_chunks = self.schedule[self._current_chunk_index + 1:]
            for chunk in remaining_chunks:
                # Move up by 20%
                adjustment = timedelta(seconds=self.config.interval_seconds * 0.2)
                chunk.scheduled_time -= adjustment

            logger.info(f"Adjusted schedule to catch up (fill_rate={metrics.fill_rate:.2%})")

    def pause(self):
        """Pause execution (can be resumed)"""
        self._pause_event.clear()
        self.state = ExecutionState.PAUSED
        logger.info("TWAP execution paused")

    def resume(self):
        """Resume paused execution"""
        self._pause_event.set()
        self.state = ExecutionState.RUNNING
        logger.info("TWAP execution resumed")

    def cancel(self):
        """Cancel execution (cannot be resumed)"""
        self._cancel_flag = True
        self.state = ExecutionState.CANCELLED
        logger.info("TWAP execution cancelled")

    def get_status(self) -> Dict[str, Any]:
        """Get current execution status"""
        metrics = self.metrics_aggregator.get_metrics()

        return {
            "state": self.state.value,
            "symbol": self.symbol,
            "side": self.side,
            "total_quantity": str(self.quantity),
            "filled_quantity": str(metrics.total_filled_quantity),
            "fill_rate": metrics.fill_rate,
            "chunks_total": len(self.schedule),
            "chunks_completed": metrics.chunks_completed,
            "chunks_remaining": len(self.schedule) - self._current_chunk_index - 1,
            "avg_slippage_pct": metrics.avg_slippage_pct,
            "slippage_trend": self.slippage_tracker.get_slippage_trend(),
            "current_chunk": self._current_chunk_index + 1 if self._current_chunk_index < len(self.schedule) else len(self.schedule)
        }


# ============================================================================
# VWAP ALGORITHM
# ============================================================================


class VWAPAlgorithm:
    """
    Volume-Weighted Average Price (VWAP) Execution Algorithm

    Splits order based on historical volume patterns to match market
    rhythm and minimize impact. Schedules larger chunks during high
    volume periods.

    Features:
    - Volume-weighted chunk sizing
    - Historical volume profile analysis
    - Adaptive scheduling based on volume forecast
    - VWAP benchmark tracking
    - Catch-up adjustment for aggressive mode
    - Slippage vs VWAP monitoring

    Usage:
        config = VWAPConfig(volume_profile_periods=20)
        vwap = VWAPAlgorithm(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("2.0"),
            config=config
        )

        # Analyze volume
        profile = vwap.analyze_volume_profile(historical_volumes)

        # Create schedule
        schedule = vwap.create_volume_weighted_schedule(profile)

        # Execute
        result = await vwap.execute(execute_func=place_order_func)
    """

    def __init__(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        config: Optional[VWAPConfig] = None,
        arrival_price: Optional[Decimal] = None
    ):
        """
        Initialize VWAP algorithm

        Args:
            symbol: Trading symbol
            side: "BUY" or "SELL"
            quantity: Total quantity to execute
            config: VWAP configuration
            arrival_price: Price at submission
        """
        self.symbol = symbol
        self.side = side.upper()
        self.quantity = quantity
        self.config = config or VWAPConfig()

        # State
        self.state = ExecutionState.PENDING
        self.schedule: List[ChunkSchedule] = []
        self._current_chunk_index = 0

        # Volume analysis
        self._volume_profile: List[float] = []
        self._market_vwap_tracker: List[Tuple[Decimal, float]] = []  # (price, volume) pairs

        # Tracking
        self.slippage_tracker = SlippageTracker(self.config.max_slippage_pct)
        self.impact_estimator = MarketImpactEstimator()
        self.metrics_aggregator = AlgorithmMetricsAggregator("VWAP", quantity)

        # Benchmark
        self.benchmark = ExecutionBenchmark(
            symbol=symbol,
            side=side,
            arrival_price=arrival_price or Decimal("0"),
            market_vwap=Decimal("0"),
            market_twap=Decimal("0"),
            total_quantity=quantity
        )

        # Control
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._cancel_flag = False

        logger.info(
            f"VWAPAlgorithm initialized: {symbol} {side} {quantity}, "
            f"periods={self.config.volume_profile_periods}"
        )

    def analyze_volume_profile(
        self,
        historical_volumes: List[float],
        periods: Optional[int] = None
    ) -> List[float]:
        """
        Analyze historical volume to create intraday profile

        Examines past volume patterns to forecast future distribution.
        Uses exponential moving average for smoothing.

        Args:
            historical_volumes: List of volume data points
            periods: Number of periods to analyze (default: config)

        Returns:
            Normalized volume profile (sums to 1.0)
        """
        periods = periods or self.config.volume_profile_periods

        if len(historical_volumes) < periods:
            logger.warning(
                f"Insufficient volume data: {len(historical_volumes)} < {periods}, "
                f"using available data"
            )
            periods = len(historical_volumes)

        # Get recent volumes
        recent_volumes = historical_volumes[-periods:]

        # Apply smoothing based on forecast method
        if self.config.volume_forecast_method == "ema":
            # Exponential moving average
            smoothed = []
            alpha = self.config.volume_smoothing_factor
            ema = recent_volumes[0]

            for vol in recent_volumes:
                ema = alpha * vol + (1 - alpha) * ema
                smoothed.append(ema)

            profile = smoothed

        elif self.config.volume_forecast_method == "median":
            # Rolling median (more robust to outliers)
            window = max(3, periods // 5)
            profile = []

            for i in range(len(recent_volumes)):
                start = max(0, i - window // 2)
                end = min(len(recent_volumes), i + window // 2 + 1)
                window_vols = recent_volumes[start:end]
                profile.append(statistics.median(window_vols))

        else:  # "historical_average"
            # Simple historical average
            profile = recent_volumes.copy()

        # Normalize to sum to 1.0
        total_volume = sum(profile)
        if total_volume > 0:
            normalized_profile = [v / total_volume for v in profile]
        else:
            # Fallback to uniform distribution
            normalized_profile = [1.0 / len(profile)] * len(profile)

        self._volume_profile = normalized_profile

        logger.info(
            f"Volume profile analyzed: {len(normalized_profile)} periods, "
            f"max={max(normalized_profile):.3f}, min={min(normalized_profile):.3f}"
        )

        return normalized_profile

    def create_volume_weighted_schedule(
        self,
        volume_profile: Optional[List[float]] = None,
        start_time: Optional[datetime] = None,
        interval_seconds: int = 60
    ) -> List[ChunkSchedule]:
        """
        Create VWAP execution schedule based on volume profile

        Allocates order quantity proportionally to expected volume in
        each time period.

        Args:
            volume_profile: Volume distribution (default: use analyzed)
            start_time: When to start (default: now)
            interval_seconds: Seconds between chunks

        Returns:
            List of ChunkSchedule objects
        """
        if volume_profile is None:
            if not self._volume_profile:
                raise ValueError("No volume profile available. Call analyze_volume_profile() first")
            volume_profile = self._volume_profile

        if start_time is None:
            start_time = datetime.now(timezone.utc)

        # Apply safety factor for conservative volume forecast
        adjusted_profile = [
            v * self.config.volume_safety_factor for v in volume_profile
        ]

        schedule = []
        cumulative_qty = Decimal("0")
        num_chunks = len(volume_profile)

        for i, volume_pct in enumerate(adjusted_profile):
            # Calculate chunk size based on volume proportion
            chunk_qty = self.quantity * Decimal(str(volume_pct))

            # Enforce min/max chunk size constraints
            min_chunk = self.quantity * Decimal(str(self.config.min_chunk_size_pct))
            max_chunk = self.quantity * Decimal(str(self.config.max_chunk_size_pct))

            if chunk_qty < min_chunk:
                chunk_qty = min_chunk
            elif chunk_qty > max_chunk:
                chunk_qty = max_chunk

            # Last chunk gets remainder
            if i == num_chunks - 1:
                chunk_qty = self.quantity - cumulative_qty

            cumulative_qty += chunk_qty

            # Calculate scheduled time
            scheduled_time = start_time + timedelta(seconds=i * interval_seconds)

            # Create chunk
            chunk = ChunkSchedule(
                chunk_id=i + 1,
                quantity=chunk_qty,
                scheduled_time=scheduled_time,
                target_participation=self.config.participation_rate
            )

            schedule.append(chunk)

        self.schedule = schedule
        self.benchmark.num_chunks = len(schedule)

        logger.info(
            f"Created VWAP schedule: {len(schedule)} chunks, "
            f"avg={cumulative_qty / len(schedule):.4f}, "
            f"duration={len(schedule) * interval_seconds}s"
        )

        return schedule

    def calculate_vwap(
        self,
        price_volume_pairs: List[Tuple[Decimal, float]]
    ) -> Decimal:
        """
        Calculate VWAP from price-volume pairs

        VWAP = Sum(Price * Volume) / Sum(Volume)

        Args:
            price_volume_pairs: List of (price, volume) tuples

        Returns:
            Volume-weighted average price
        """
        if not price_volume_pairs:
            return Decimal("0")

        total_value = sum(float(price) * volume for price, volume in price_volume_pairs)
        total_volume = sum(volume for _, volume in price_volume_pairs)

        if total_volume == 0:
            return Decimal("0")

        vwap = Decimal(str(total_value / total_volume))

        logger.debug(f"Calculated VWAP: {vwap} from {len(price_volume_pairs)} points")

        return vwap

    def calculate_benchmark(
        self,
        market_trades: List[Dict]
    ) -> ExecutionBenchmark:
        """
        Calculate benchmark metrics vs market VWAP

        Compares execution performance against market VWAP during
        the same time period.

        Args:
            market_trades: List of market trades with price/volume

        Returns:
            Updated ExecutionBenchmark
        """
        # Calculate market VWAP
        market_pairs = [
            (Decimal(str(t["price"])), float(t["volume"]))
            for t in market_trades
        ]
        self.benchmark.market_vwap = self.calculate_vwap(market_pairs)

        # Calculate our execution VWAP
        our_pairs = [
            (chunk.average_price, float(chunk.executed_quantity))
            for chunk in self.schedule
            if chunk.status == ExecutionState.COMPLETED and chunk.average_price > 0
        ]
        self.benchmark.execution_vwap = self.calculate_vwap(our_pairs)

        # Calculate slippage vs market VWAP
        if self.benchmark.market_vwap > 0 and self.benchmark.execution_vwap > 0:
            if self.side == "BUY":
                self.benchmark.slippage_vs_vwap_pct = float(
                    (self.benchmark.execution_vwap - self.benchmark.market_vwap) /
                    self.benchmark.market_vwap
                ) * 100
            else:
                self.benchmark.slippage_vs_vwap_pct = float(
                    (self.benchmark.market_vwap - self.benchmark.execution_vwap) /
                    self.benchmark.market_vwap
                ) * 100

        logger.info(
            f"Benchmark calculated: market_vwap={self.benchmark.market_vwap}, "
            f"execution_vwap={self.benchmark.execution_vwap}, "
            f"slippage={self.benchmark.slippage_vs_vwap_pct:.3f}%"
        )

        return self.benchmark

    def calculate_catchup_adjustment(self) -> float:
        """
        Calculate aggressive factor for catch-up mode

        When behind schedule, increases chunk sizes to catch up.

        Returns:
            Multiplier for chunk sizes (1.0 = no change, 1.5 = 50% larger)
        """
        metrics = self.metrics_aggregator.get_metrics()

        # Check if we're behind schedule
        expected_fill = (
            self._current_chunk_index / len(self.schedule)
            if self.schedule else 1.0
        )

        actual_fill = metrics.fill_rate

        if actual_fill < expected_fill * 0.8:  # More than 20% behind
            # Apply aggressive factor
            if self.config.adaptive_mode == AdaptiveMode.AGGRESSIVE:
                adjustment = self.config.catchup_aggressive_pct
                logger.info(
                    f"Catch-up mode: {adjustment:.1%} size increase "
                    f"(expected={expected_fill:.1%}, actual={actual_fill:.1%})"
                )
                return adjustment
            elif self.config.adaptive_mode == AdaptiveMode.URGENT:
                # Even more aggressive
                return self.config.catchup_aggressive_pct * 1.5

        return 1.0  # No adjustment

    async def execute(
        self,
        execute_func: Callable,
        get_market_data_func: Optional[Callable] = None
    ) -> AlgorithmMetrics:
        """
        Execute VWAP algorithm

        Similar to TWAP but with volume-weighted scheduling and
        VWAP benchmark tracking.

        Args:
            execute_func: Async function to execute orders
            get_market_data_func: Optional function for market data

        Returns:
            AlgorithmMetrics with results
        """
        if not self.schedule:
            raise ValueError("No schedule created. Call create_volume_weighted_schedule() first")

        self.state = ExecutionState.RUNNING
        self.benchmark.start_time = datetime.now(timezone.utc)

        logger.info(f"Starting VWAP execution: {len(self.schedule)} chunks")

        try:
            for i, chunk in enumerate(self.schedule):
                self._current_chunk_index = i

                # Check for cancellation
                if self._cancel_flag:
                    logger.info("VWAP execution cancelled")
                    self.state = ExecutionState.CANCELLED
                    break

                # Wait for scheduled time
                await self._wait_until_scheduled(chunk.scheduled_time)

                # Wait if paused
                await self._pause_event.wait()

                # Apply catch-up adjustment if needed
                if self.config.adaptive_mode in (AdaptiveMode.AGGRESSIVE, AdaptiveMode.URGENT):
                    adjustment = self.calculate_catchup_adjustment()
                    if adjustment > 1.0:
                        chunk.quantity *= Decimal(str(adjustment))
                        logger.info(f"Chunk {chunk.chunk_id} size adjusted: {adjustment:.2f}x")

                # Execute chunk (reuse TWAP logic)
                await self._execute_chunk(chunk, execute_func, get_market_data_func)

                # Track for VWAP calculation
                if chunk.status == ExecutionState.COMPLETED:
                    self._market_vwap_tracker.append(
                        (chunk.average_price, float(chunk.executed_quantity))
                    )

            # Mark as completed
            if all(c.status in (ExecutionState.COMPLETED, ExecutionState.FAILED) for c in self.schedule):
                self.state = ExecutionState.COMPLETED

            self.benchmark.end_time = datetime.now(timezone.utc)
            self.benchmark.duration_seconds = (
                self.benchmark.end_time - self.benchmark.start_time
            ).total_seconds()

            # Calculate final VWAP
            self.benchmark.execution_vwap = self.calculate_vwap(self._market_vwap_tracker)

            logger.info(
                f"VWAP execution finished: state={self.state.value}, "
                f"fill_rate={self.metrics_aggregator.metrics.fill_rate:.2%}, "
                f"execution_vwap={self.benchmark.execution_vwap}"
            )

        except Exception as e:
            logger.error(f"VWAP execution failed: {e}", exc_info=True)
            self.state = ExecutionState.FAILED
            raise

        return self.metrics_aggregator.get_metrics()

    async def _execute_chunk(
        self,
        chunk: ChunkSchedule,
        execute_func: Callable,
        get_market_data_func: Optional[Callable]
    ):
        """Execute individual chunk (same as TWAP)"""
        # Reuse TWAP implementation
        twap_instance = TWAPAlgorithm(
            self.symbol,
            self.side,
            self.quantity,
            TWAPConfig(),
            self.benchmark.arrival_price
        )
        await twap_instance._execute_chunk(chunk, execute_func, get_market_data_func)

        # Update our metrics
        if chunk.status == ExecutionState.COMPLETED:
            exec_time_ms = (
                chunk.execution_completed_at - chunk.execution_started_at
            ).total_seconds() * 1000 if chunk.execution_completed_at and chunk.execution_started_at else 0

            self.metrics_aggregator.add_chunk_result(
                chunk.chunk_id,
                chunk.quantity,
                chunk.executed_quantity,
                chunk.average_price,
                chunk.slippage_pct,
                exec_time_ms,
                chunk.status
            )

            # Track slippage
            self.slippage_tracker.record_slippage(
                chunk.chunk_id,
                chunk.slippage_pct,
                self.benchmark.arrival_price,
                chunk.average_price
            )

    async def _wait_until_scheduled(self, scheduled_time: datetime):
        """Wait until scheduled time"""
        now = datetime.now(timezone.utc)
        if scheduled_time > now:
            wait_seconds = (scheduled_time - now).total_seconds()
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)

    def pause(self):
        """Pause execution"""
        self._pause_event.clear()
        self.state = ExecutionState.PAUSED
        logger.info("VWAP execution paused")

    def resume(self):
        """Resume execution"""
        self._pause_event.set()
        self.state = ExecutionState.RUNNING
        logger.info("VWAP execution resumed")

    def cancel(self):
        """Cancel execution"""
        self._cancel_flag = True
        self.state = ExecutionState.CANCELLED
        logger.info("VWAP execution cancelled")

    def get_status(self) -> Dict[str, Any]:
        """Get execution status"""
        metrics = self.metrics_aggregator.get_metrics()

        return {
            "state": self.state.value,
            "symbol": self.symbol,
            "side": self.side,
            "total_quantity": str(self.quantity),
            "filled_quantity": str(metrics.total_filled_quantity),
            "fill_rate": metrics.fill_rate,
            "chunks_total": len(self.schedule),
            "chunks_completed": metrics.chunks_completed,
            "chunks_remaining": len(self.schedule) - self._current_chunk_index - 1,
            "execution_vwap": str(self.benchmark.execution_vwap),
            "market_vwap": str(self.benchmark.market_vwap),
            "slippage_vs_vwap_pct": self.benchmark.slippage_vs_vwap_pct,
            "avg_slippage_pct": metrics.avg_slippage_pct
        }


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================

# Global instances (singleton pattern)
_twap_instance: Optional[TWAPAlgorithm] = None
_vwap_instance: Optional[VWAPAlgorithm] = None


def create_twap_algorithm(
    symbol: str,
    side: str,
    quantity: Decimal,
    config: Optional[TWAPConfig] = None,
    arrival_price: Optional[Decimal] = None
) -> TWAPAlgorithm:
    """
    Factory function to create TWAP algorithm instance

    Args:
        symbol: Trading symbol
        side: "BUY" or "SELL"
        quantity: Total quantity
        config: TWAP configuration
        arrival_price: Arrival price for benchmarking

    Returns:
        TWAPAlgorithm instance
    """
    return TWAPAlgorithm(symbol, side, quantity, config, arrival_price)


def create_vwap_algorithm(
    symbol: str,
    side: str,
    quantity: Decimal,
    config: Optional[VWAPConfig] = None,
    arrival_price: Optional[Decimal] = None
) -> VWAPAlgorithm:
    """
    Factory function to create VWAP algorithm instance

    Args:
        symbol: Trading symbol
        side: "BUY" or "SELL"
        quantity: Total quantity
        config: VWAP configuration
        arrival_price: Arrival price for benchmarking

    Returns:
        VWAPAlgorithm instance
    """
    return VWAPAlgorithm(symbol, side, quantity, config, arrival_price)


def get_twap_algorithm() -> Optional[TWAPAlgorithm]:
    """Get global TWAP instance if exists"""
    global _twap_instance
    return _twap_instance


def get_vwap_algorithm() -> Optional[VWAPAlgorithm]:
    """Get global VWAP instance if exists"""
    global _vwap_instance
    return _vwap_instance


def reset_algorithms():
    """Reset global algorithm instances"""
    global _twap_instance, _vwap_instance
    _twap_instance = None
    _vwap_instance = None
    logger.info("Algorithm instances reset")
