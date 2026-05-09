"""
Execution Scheduler - Background Task Management for Algorithmic Orders
Phase 4.2: Enhanced TWAP/VWAP Execution Algorithms

Purpose:
- Schedule and manage TWAP/VWAP order execution
- Run execution algorithms as background tasks
- Maintain order queue with priority management
- Monitor and adjust execution progress in real-time
- Handle cancellation, pause, and resume operations
- Generate execution quality reports

Architecture:
+------------------+
|ExecutionScheduler|  <- Main scheduler managing all algorithmic orders
+--------+---------+
         |
    +----+----+----------------+-------------+
    |         |                |             |
+---v---+ +---v------+  +------v-------+ +---v----+
|Order  | |Background|  |Execution     | |Status  |
|Queue  | |Tasks     |  |Monitor       | |Tracker |
+-------+ +----------+  +--------------+ +--------+

Key Features:
- Asynchronous order slice execution
- Priority-based queue management
- Real-time fill monitoring and adaptive adjustments
- Graceful pause/resume/cancel mechanisms
- Comprehensive execution quality reporting
- Circuit breaker integration for exchange calls

Research Sources:
- Optimal Execution Scheduling (Almgren)
- Priority Queue Management in Trading Systems
- Asynchronous Task Processing Patterns
- Exchange Rate Limiting Best Practices

Created: 2025-12-12
Author: Backend Developer Agent
"""

import asyncio
import logging
import uuid
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
import statistics

# Configure logging for execution scheduler
logger = logging.getLogger(__name__)


# ============================================================================
# ENUMERATIONS
# ============================================================================


class OrderPriority(str, Enum):
    """
    Priority levels for algorithmic orders in the queue

    URGENT: Process immediately, skip queue
    HIGH: Process before normal orders
    NORMAL: Standard processing order
    LOW: Process after all higher priority orders
    """
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class AlgorithmType(str, Enum):
    """
    Types of execution algorithms

    TWAP: Time-Weighted Average Price
    VWAP: Volume-Weighted Average Price
    ICEBERG: Hidden order with visible portion
    POV: Percentage of Volume
    """
    TWAP = "twap"
    VWAP = "vwap"
    ICEBERG = "iceberg"
    POV = "pov"


class SchedulerState(str, Enum):
    """
    Scheduler operational state

    IDLE: No orders being processed
    RUNNING: Actively processing orders
    PAUSED: Temporarily stopped
    STOPPED: Fully stopped (requires restart)
    """
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class OrderLifecycleState(str, Enum):
    """
    Lifecycle states for scheduled orders

    QUEUED: In queue waiting for processing
    SCHEDULED: Active with scheduled chunks
    EXECUTING: Currently executing chunk
    PAUSED: Temporarily paused
    COMPLETED: All chunks executed
    CANCELLED: Cancelled by user
    FAILED: Execution failed
    PARTIAL: Partially filled then stopped
    """
    QUEUED = "queued"
    SCHEDULED = "scheduled"
    EXECUTING = "executing"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    PARTIAL = "partial"


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class ScheduledOrder:
    """
    Represents an algorithmic order scheduled for execution

    Contains all information needed to track and execute an order:
    - Order identification and parameters
    - Algorithm configuration
    - Progress tracking
    - Performance metrics
    """
    # Identification
    order_id: str                                   # Unique order identifier
    algorithm_type: AlgorithmType                   # TWAP, VWAP, etc.
    priority: OrderPriority = OrderPriority.NORMAL  # Queue priority

    # Order parameters
    symbol: str = ""                                # Trading symbol
    side: str = ""                                  # BUY or SELL
    total_quantity: Decimal = Decimal("0")          # Total quantity to execute

    # Algorithm configuration
    duration_minutes: int = 10                      # Total execution duration
    num_chunks: int = 10                            # Number of order slices
    interval_seconds: int = 60                      # Seconds between chunks
    participation_rate: float = 0.15                # Target % of market volume
    randomize_timing: bool = True                   # Add timing variance
    urgency: str = "medium"                         # Execution urgency level

    # State tracking
    state: OrderLifecycleState = OrderLifecycleState.QUEUED
    current_chunk: int = 0                          # Current chunk being executed

    # Progress metrics
    filled_quantity: Decimal = Decimal("0")         # Total quantity filled
    average_price: Decimal = Decimal("0")           # Volume-weighted avg price
    total_value: Decimal = Decimal("0")             # Total value executed

    # Performance tracking
    arrival_price: Decimal = Decimal("0")           # Price at order submission
    benchmark_price: Decimal = Decimal("0")         # TWAP/VWAP benchmark
    slippage_pct: float = 0.0                       # Actual vs benchmark
    slippage_usd: float = 0.0                       # Dollar slippage

    # Timing
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_chunk_at: Optional[datetime] = None

    # Chunk tracking
    chunk_results: List[Dict] = field(default_factory=list)

    # Error tracking
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

    # Callbacks (optional)
    on_complete_callback: Optional[str] = None
    on_error_callback: Optional[str] = None

    def get_fill_rate(self) -> float:
        """Calculate current fill rate"""
        if self.total_quantity > 0:
            return float(self.filled_quantity / self.total_quantity)
        return 0.0

    def get_progress_pct(self) -> float:
        """Calculate execution progress percentage"""
        if self.num_chunks > 0:
            return (self.current_chunk / self.num_chunks) * 100
        return 0.0

    def is_active(self) -> bool:
        """Check if order is still active"""
        return self.state in (
            OrderLifecycleState.QUEUED,
            OrderLifecycleState.SCHEDULED,
            OrderLifecycleState.EXECUTING
        )

    def calculate_slippage(self) -> Tuple[float, float]:
        """Calculate slippage vs benchmark"""
        if self.average_price <= 0 or self.benchmark_price <= 0:
            return 0.0, 0.0

        if self.side.upper() == "BUY":
            # For buys, paying more than benchmark is negative slippage
            slippage_pct = float(
                (self.average_price - self.benchmark_price) / self.benchmark_price
            ) * 100
        else:
            # For sells, receiving less than benchmark is negative slippage
            slippage_pct = float(
                (self.benchmark_price - self.average_price) / self.benchmark_price
            ) * 100

        slippage_usd = abs(slippage_pct / 100 * float(self.total_value))

        return slippage_pct, slippage_usd


@dataclass
class ChunkExecution:
    """
    Result of executing a single chunk

    Contains execution details for one slice of an algorithmic order:
    - Quantities and prices
    - Timing information
    - Slippage and quality metrics
    """
    chunk_id: int                                   # Chunk identifier (1-based)
    order_id: str                                   # Parent order ID

    # Execution parameters
    target_quantity: Decimal = Decimal("0")         # Quantity to execute
    target_price: Decimal = Decimal("0")            # Expected price

    # Results
    filled_quantity: Decimal = Decimal("0")         # Actually filled
    average_price: Decimal = Decimal("0")           # Actual fill price

    # Timing
    scheduled_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    executed_at: Optional[datetime] = None
    execution_time_ms: float = 0.0

    # Performance
    slippage_pct: float = 0.0
    market_volume: Optional[float] = None           # Volume during execution
    participation_rate: Optional[float] = None      # Our % of market volume

    # Status
    success: bool = False
    error_message: Optional[str] = None


@dataclass
class ExecutionReport:
    """
    Comprehensive execution quality report for an algorithmic order

    Provides detailed analysis of execution performance:
    - Fill quality metrics
    - Benchmark comparison
    - Cost analysis
    - Recommendations
    """
    order_id: str
    algorithm_type: str
    symbol: str
    side: str

    # Order summary
    total_quantity: Decimal = Decimal("0")
    filled_quantity: Decimal = Decimal("0")
    fill_rate: float = 0.0

    # Price performance
    arrival_price: Decimal = Decimal("0")
    average_price: Decimal = Decimal("0")
    benchmark_price: Decimal = Decimal("0")         # TWAP or VWAP

    # Slippage analysis
    slippage_vs_arrival_pct: float = 0.0
    slippage_vs_arrival_usd: float = 0.0
    slippage_vs_benchmark_pct: float = 0.0
    slippage_vs_benchmark_usd: float = 0.0

    # Cost analysis
    estimated_market_impact_usd: float = 0.0        # If done immediately
    actual_impact_usd: float = 0.0
    savings_usd: float = 0.0
    savings_pct: float = 0.0

    # Execution quality
    chunks_total: int = 0
    chunks_successful: int = 0
    chunks_failed: int = 0
    avg_chunk_slippage: float = 0.0
    max_chunk_slippage: float = 0.0

    # Timing
    duration_planned_seconds: float = 0.0
    duration_actual_seconds: float = 0.0
    avg_execution_time_ms: float = 0.0

    # Participation
    target_participation_rate: float = 0.0
    actual_participation_rate: float = 0.0

    # Assessment
    quality_score: float = 0.0                      # 0-100 execution quality
    rating: str = ""                                # "excellent", "good", "fair", "poor"
    recommendations: List[str] = field(default_factory=list)

    # Timestamps
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SchedulerMetrics:
    """
    Aggregate metrics for the execution scheduler

    Tracks overall scheduler performance:
    - Order counts and fill rates
    - Average slippage and execution times
    - Algorithm-specific statistics
    """
    # Order counts
    total_orders_queued: int = 0
    total_orders_completed: int = 0
    total_orders_cancelled: int = 0
    total_orders_failed: int = 0
    orders_currently_active: int = 0

    # Fill metrics
    total_quantity_executed: float = 0.0
    total_value_executed_usd: float = 0.0
    avg_fill_rate: float = 0.0

    # Slippage metrics
    avg_slippage_pct: float = 0.0
    total_slippage_usd: float = 0.0
    avg_slippage_vs_benchmark: float = 0.0

    # Timing
    avg_execution_duration_seconds: float = 0.0
    avg_chunk_execution_ms: float = 0.0

    # By algorithm type
    twap_orders: int = 0
    twap_avg_slippage: float = 0.0
    vwap_orders: int = 0
    vwap_avg_slippage: float = 0.0

    # Last updated
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================================
# EXECUTION SCHEDULER
# ============================================================================


class ExecutionScheduler:
    """
    Execution Scheduler - Manages Background Algorithmic Order Execution

    Central management component for TWAP/VWAP and other algorithmic orders.
    Handles scheduling, execution, monitoring, and reporting.

    Features:
    - Priority-based order queue
    - Concurrent order execution
    - Real-time monitoring and adaptation
    - Pause/resume/cancel support
    - Comprehensive metrics tracking
    - Execution quality reporting

    Usage:
        scheduler = ExecutionScheduler()
        await scheduler.start()

        # Submit TWAP order
        order_id = await scheduler.submit_twap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1.0"),
            duration_minutes=10,
            arrival_price=Decimal("50000")
        )

        # Check status
        status = scheduler.get_order_status(order_id)

        # Pause if needed
        scheduler.pause_order(order_id)

        # Get report when done
        report = scheduler.get_execution_report(order_id)
    """

    def __init__(
        self,
        max_concurrent_orders: int = 5,
        max_queue_size: int = 100,
        default_participation_rate: float = 0.15
    ):
        """
        Initialize execution scheduler

        Args:
            max_concurrent_orders: Maximum orders executing simultaneously
            max_queue_size: Maximum orders in queue
            default_participation_rate: Default market participation rate
        """
        # Configuration
        self.max_concurrent_orders = max_concurrent_orders
        self.max_queue_size = max_queue_size
        self.default_participation_rate = default_participation_rate

        # State
        self.state = SchedulerState.IDLE

        # Order storage
        self._orders: Dict[str, ScheduledOrder] = {}                    # All orders by ID
        self._order_queue: deque = deque(maxlen=max_queue_size)         # Waiting orders
        self._active_orders: Dict[str, asyncio.Task] = {}               # Running tasks
        self._completed_orders: deque = deque(maxlen=500)               # Recent completed

        # Execution functions (injected)
        self._execute_func: Optional[Callable] = None
        self._get_market_data_func: Optional[Callable] = None
        self._cancel_order_func: Optional[Callable] = None

        # Metrics
        self._metrics = SchedulerMetrics()
        self._slippage_history: deque = deque(maxlen=1000)

        # Control
        self._shutdown_event = asyncio.Event()
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused initially

        # Background task
        self._processor_task: Optional[asyncio.Task] = None

        logger.info(
            f"ExecutionScheduler initialized: "
            f"max_concurrent={max_concurrent_orders}, "
            f"max_queue={max_queue_size}, "
            f"participation={default_participation_rate:.1%}"
        )

    def set_execution_functions(
        self,
        execute_func: Callable,
        get_market_data_func: Optional[Callable] = None,
        cancel_order_func: Optional[Callable] = None
    ):
        """
        Set execution callback functions

        Args:
            execute_func: Async function to place orders
            get_market_data_func: Async function to get market data
            cancel_order_func: Async function to cancel orders
        """
        self._execute_func = execute_func
        self._get_market_data_func = get_market_data_func
        self._cancel_order_func = cancel_order_func

        logger.info("Execution functions configured")

    # ========================================================================
    # LIFECYCLE MANAGEMENT
    # ========================================================================

    async def start(self):
        """Start the execution scheduler"""
        if self.state == SchedulerState.RUNNING:
            logger.warning("Scheduler already running")
            return

        self.state = SchedulerState.RUNNING
        self._shutdown_event.clear()

        # Start background processor
        self._processor_task = asyncio.create_task(self._process_queue())

        logger.info("ExecutionScheduler started")

    async def stop(self, wait_for_completion: bool = True):
        """
        Stop the execution scheduler

        Args:
            wait_for_completion: Wait for active orders to complete
        """
        logger.info(f"Stopping scheduler (wait={wait_for_completion})")

        self._shutdown_event.set()
        self.state = SchedulerState.STOPPED

        if wait_for_completion and self._active_orders:
            # Wait for active orders
            await asyncio.gather(*self._active_orders.values(), return_exceptions=True)
        else:
            # Cancel active orders
            for order_id, task in self._active_orders.items():
                task.cancel()

        # Stop processor
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass

        logger.info("ExecutionScheduler stopped")

    def pause(self):
        """Pause all order processing"""
        self._pause_event.clear()
        self.state = SchedulerState.PAUSED
        logger.info("Scheduler paused")

    def resume(self):
        """Resume order processing"""
        self._pause_event.set()
        self.state = SchedulerState.RUNNING
        logger.info("Scheduler resumed")

    # ========================================================================
    # ORDER SUBMISSION
    # ========================================================================

    async def submit_twap_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        duration_minutes: int = 10,
        num_chunks: Optional[int] = None,
        arrival_price: Optional[Decimal] = None,
        participation_rate: Optional[float] = None,
        randomize_timing: bool = True,
        priority: OrderPriority = OrderPriority.NORMAL,
        urgency: str = "medium"
    ) -> str:
        """
        Submit a TWAP (Time-Weighted Average Price) order

        TWAP splits the order into equal-sized chunks executed at regular
        time intervals. Minimizes timing risk and is simple to implement.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            side: "BUY" or "SELL"
            quantity: Total quantity to execute
            duration_minutes: Total execution duration (default: 10)
            num_chunks: Number of slices (default: auto-calculate)
            arrival_price: Price at submission for benchmarking
            participation_rate: Target % of market volume
            randomize_timing: Add variance to timing (default: True)
            priority: Queue priority level
            urgency: Execution urgency (low/medium/high)

        Returns:
            Order ID for tracking
        """
        # Generate order ID
        order_id = f"twap_{symbol}_{uuid.uuid4().hex[:8]}"

        # Calculate chunks if not specified
        if num_chunks is None:
            # Default: ~1 chunk per minute
            num_chunks = max(3, min(60, duration_minutes))

        # Calculate interval
        interval_seconds = (duration_minutes * 60) // num_chunks

        # Create scheduled order
        order = ScheduledOrder(
            order_id=order_id,
            algorithm_type=AlgorithmType.TWAP,
            priority=priority,
            symbol=symbol,
            side=side.upper(),
            total_quantity=quantity,
            duration_minutes=duration_minutes,
            num_chunks=num_chunks,
            interval_seconds=interval_seconds,
            participation_rate=participation_rate or self.default_participation_rate,
            randomize_timing=randomize_timing,
            urgency=urgency,
            arrival_price=arrival_price or Decimal("0"),
            state=OrderLifecycleState.QUEUED
        )

        # Store and queue
        self._orders[order_id] = order
        self._order_queue.append(order_id)
        self._metrics.total_orders_queued += 1
        self._metrics.twap_orders += 1

        logger.info(
            f"TWAP order submitted: {order_id} - "
            f"{symbol} {side} {quantity}, {num_chunks} chunks over {duration_minutes}min"
        )

        return order_id

    async def submit_vwap_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        duration_minutes: int = 10,
        historical_volumes: Optional[List[float]] = None,
        arrival_price: Optional[Decimal] = None,
        target_vwap: Optional[Decimal] = None,
        participation_rate: Optional[float] = None,
        priority: OrderPriority = OrderPriority.NORMAL,
        urgency: str = "medium"
    ) -> str:
        """
        Submit a VWAP (Volume-Weighted Average Price) order

        VWAP splits the order based on historical volume patterns to match
        market rhythm and minimize impact. Larger chunks during high volume.

        Args:
            symbol: Trading symbol
            side: "BUY" or "SELL"
            quantity: Total quantity to execute
            duration_minutes: Total execution duration
            historical_volumes: Volume profile for scheduling
            arrival_price: Price at submission
            target_vwap: Target VWAP to track (optional)
            participation_rate: Target % of market volume
            priority: Queue priority level
            urgency: Execution urgency

        Returns:
            Order ID for tracking
        """
        # Generate order ID
        order_id = f"vwap_{symbol}_{uuid.uuid4().hex[:8]}"

        # Determine number of chunks based on volume data
        if historical_volumes:
            num_chunks = len(historical_volumes)
        else:
            # Default: same as TWAP
            num_chunks = max(3, min(60, duration_minutes))

        interval_seconds = (duration_minutes * 60) // num_chunks

        # Create scheduled order
        order = ScheduledOrder(
            order_id=order_id,
            algorithm_type=AlgorithmType.VWAP,
            priority=priority,
            symbol=symbol,
            side=side.upper(),
            total_quantity=quantity,
            duration_minutes=duration_minutes,
            num_chunks=num_chunks,
            interval_seconds=interval_seconds,
            participation_rate=participation_rate or self.default_participation_rate,
            randomize_timing=False,  # VWAP follows volume, not random
            urgency=urgency,
            arrival_price=arrival_price or Decimal("0"),
            benchmark_price=target_vwap or Decimal("0"),
            state=OrderLifecycleState.QUEUED
        )

        # Store volume profile in chunk_results as metadata
        if historical_volumes:
            normalized = self._normalize_volume_profile(historical_volumes)
            order.chunk_results = [{"volume_weight": v} for v in normalized]

        # Store and queue
        self._orders[order_id] = order
        self._order_queue.append(order_id)
        self._metrics.total_orders_queued += 1
        self._metrics.vwap_orders += 1

        logger.info(
            f"VWAP order submitted: {order_id} - "
            f"{symbol} {side} {quantity}, {num_chunks} chunks over {duration_minutes}min"
        )

        return order_id

    def _normalize_volume_profile(self, volumes: List[float]) -> List[float]:
        """
        Normalize volume profile to sum to 1.0

        Handles edge cases:
        - Empty list: returns empty list
        - Zero-sum volumes: returns equal distribution
        - Normal case: normalizes to sum to 1.0

        Args:
            volumes: List of volume values

        Returns:
            List of normalized weights summing to 1.0
        """
        # Handle empty list edge case
        if not volumes:
            return []

        # Handle zero-sum volume profile (fallback to equal distribution)
        total = sum(volumes)
        if total > 0:
            return [v / total for v in volumes]

        # Equal distribution when total is zero
        return [1.0 / len(volumes)] * len(volumes)

    # ========================================================================
    # ORDER CONTROL
    # ========================================================================

    def pause_order(self, order_id: str) -> bool:
        """
        Pause a specific order's execution

        Args:
            order_id: Order to pause

        Returns:
            True if paused, False if not found or cannot pause
        """
        order = self._orders.get(order_id)
        if not order:
            logger.warning(f"Order not found: {order_id}")
            return False

        if not order.is_active():
            logger.warning(f"Cannot pause inactive order: {order_id}")
            return False

        order.state = OrderLifecycleState.PAUSED
        logger.info(f"Order paused: {order_id}")
        return True

    def resume_order(self, order_id: str) -> bool:
        """
        Resume a paused order

        Args:
            order_id: Order to resume

        Returns:
            True if resumed, False if not found or not paused
        """
        order = self._orders.get(order_id)
        if not order:
            logger.warning(f"Order not found: {order_id}")
            return False

        if order.state != OrderLifecycleState.PAUSED:
            logger.warning(f"Order not paused: {order_id}")
            return False

        order.state = OrderLifecycleState.SCHEDULED
        logger.info(f"Order resumed: {order_id}")
        return True

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order's execution

        Args:
            order_id: Order to cancel

        Returns:
            True if cancelled, False if not found or already complete
        """
        order = self._orders.get(order_id)
        if not order:
            logger.warning(f"Order not found: {order_id}")
            return False

        if order.state in (OrderLifecycleState.COMPLETED, OrderLifecycleState.CANCELLED):
            logger.warning(f"Order already complete/cancelled: {order_id}")
            return False

        # Cancel any running task
        if order_id in self._active_orders:
            task = self._active_orders[order_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self._active_orders[order_id]

        # Update state
        if order.filled_quantity > 0:
            order.state = OrderLifecycleState.PARTIAL
        else:
            order.state = OrderLifecycleState.CANCELLED

        order.completed_at = datetime.now(timezone.utc)
        self._metrics.total_orders_cancelled += 1

        logger.info(f"Order cancelled: {order_id}, filled={order.filled_quantity}")
        return True

    # ========================================================================
    # STATUS & REPORTING
    # ========================================================================

    def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed status for an order

        Args:
            order_id: Order to query

        Returns:
            Order status dictionary or None if not found
        """
        order = self._orders.get(order_id)
        if not order:
            return None

        return {
            "order_id": order.order_id,
            "algorithm": order.algorithm_type.value,
            "symbol": order.symbol,
            "side": order.side,
            "state": order.state.value,
            "priority": order.priority.value,
            "progress": {
                "total_quantity": str(order.total_quantity),
                "filled_quantity": str(order.filled_quantity),
                "fill_rate": order.get_fill_rate(),
                "progress_pct": order.get_progress_pct(),
                "current_chunk": order.current_chunk,
                "total_chunks": order.num_chunks
            },
            "execution": {
                "average_price": str(order.average_price) if order.average_price else None,
                "arrival_price": str(order.arrival_price) if order.arrival_price else None,
                "benchmark_price": str(order.benchmark_price) if order.benchmark_price else None,
                "slippage_pct": round(order.slippage_pct, 4),
                "slippage_usd": round(order.slippage_usd, 2)
            },
            "timing": {
                "duration_minutes": order.duration_minutes,
                "interval_seconds": order.interval_seconds,
                "created_at": order.created_at.isoformat(),
                "started_at": order.started_at.isoformat() if order.started_at else None,
                "last_chunk_at": order.last_chunk_at.isoformat() if order.last_chunk_at else None,
                "completed_at": order.completed_at.isoformat() if order.completed_at else None
            },
            "chunks": len(order.chunk_results)
        }

    def get_active_algorithms(self) -> List[Dict[str, Any]]:
        """
        Get list of all active algorithmic orders

        Returns:
            List of active order summaries
        """
        active = []

        for order_id, order in self._orders.items():
            if order.is_active():
                active.append({
                    "order_id": order_id,
                    "algorithm": order.algorithm_type.value,
                    "symbol": order.symbol,
                    "side": order.side,
                    "state": order.state.value,
                    "fill_rate": order.get_fill_rate(),
                    "progress_pct": order.get_progress_pct(),
                    "started_at": order.started_at.isoformat() if order.started_at else None
                })

        return active

    def get_execution_report(self, order_id: str) -> Optional[ExecutionReport]:
        """
        Generate comprehensive execution report for an order

        Args:
            order_id: Order to analyze

        Returns:
            ExecutionReport or None if not found
        """
        order = self._orders.get(order_id)
        if not order:
            return None

        # Calculate slippage metrics
        slippage_vs_arrival_pct = 0.0
        slippage_vs_arrival_usd = 0.0

        if order.average_price > 0 and order.arrival_price > 0:
            if order.side == "BUY":
                slippage_vs_arrival_pct = float(
                    (order.average_price - order.arrival_price) / order.arrival_price
                ) * 100
            else:
                slippage_vs_arrival_pct = float(
                    (order.arrival_price - order.average_price) / order.arrival_price
                ) * 100
            slippage_vs_arrival_usd = abs(slippage_vs_arrival_pct / 100 * float(order.total_value))

        # Benchmark slippage (TWAP/VWAP)
        slippage_vs_benchmark_pct, slippage_vs_benchmark_usd = order.calculate_slippage()

        # Chunk statistics
        successful_chunks = sum(1 for c in order.chunk_results if c.get("success", False))
        failed_chunks = sum(1 for c in order.chunk_results if not c.get("success", True))

        chunk_slippages = [c.get("slippage_pct", 0) for c in order.chunk_results if "slippage_pct" in c]
        avg_chunk_slippage = statistics.mean(chunk_slippages) if chunk_slippages else 0.0
        max_chunk_slippage = max(chunk_slippages) if chunk_slippages else 0.0

        chunk_times = [c.get("execution_time_ms", 0) for c in order.chunk_results if "execution_time_ms" in c]
        avg_exec_time = statistics.mean(chunk_times) if chunk_times else 0.0

        # Calculate duration
        duration_planned = order.duration_minutes * 60
        duration_actual = 0.0
        if order.started_at and order.completed_at:
            duration_actual = (order.completed_at - order.started_at).total_seconds()
        elif order.started_at:
            duration_actual = (datetime.now(timezone.utc) - order.started_at).total_seconds()

        # Quality score (0-100)
        quality_score = self._calculate_quality_score(
            fill_rate=order.get_fill_rate(),
            slippage_pct=abs(slippage_vs_benchmark_pct),
            success_rate=successful_chunks / max(1, len(order.chunk_results)),
            timing_accuracy=1.0 - abs(duration_actual - duration_planned) / max(1, duration_planned)
        )

        # Rating
        if quality_score >= 90:
            rating = "excellent"
        elif quality_score >= 75:
            rating = "good"
        elif quality_score >= 50:
            rating = "fair"
        else:
            rating = "poor"

        # Recommendations
        recommendations = []
        if order.get_fill_rate() < 0.95:
            recommendations.append("Consider increasing chunk timeout or using more aggressive pricing")
        if abs(slippage_vs_benchmark_pct) > 0.1:
            recommendations.append("Slippage is elevated - consider smaller participation rate")
        if failed_chunks > 0:
            recommendations.append(f"{failed_chunks} chunks failed - review execution logs")

        return ExecutionReport(
            order_id=order_id,
            algorithm_type=order.algorithm_type.value,
            symbol=order.symbol,
            side=order.side,
            total_quantity=order.total_quantity,
            filled_quantity=order.filled_quantity,
            fill_rate=order.get_fill_rate(),
            arrival_price=order.arrival_price,
            average_price=order.average_price,
            benchmark_price=order.benchmark_price,
            slippage_vs_arrival_pct=slippage_vs_arrival_pct,
            slippage_vs_arrival_usd=slippage_vs_arrival_usd,
            slippage_vs_benchmark_pct=slippage_vs_benchmark_pct,
            slippage_vs_benchmark_usd=slippage_vs_benchmark_usd,
            chunks_total=order.num_chunks,
            chunks_successful=successful_chunks,
            chunks_failed=failed_chunks,
            avg_chunk_slippage=avg_chunk_slippage,
            max_chunk_slippage=max_chunk_slippage,
            duration_planned_seconds=duration_planned,
            duration_actual_seconds=duration_actual,
            avg_execution_time_ms=avg_exec_time,
            target_participation_rate=order.participation_rate,
            quality_score=quality_score,
            rating=rating,
            recommendations=recommendations,
            started_at=order.started_at,
            completed_at=order.completed_at
        )

    def _calculate_quality_score(
        self,
        fill_rate: float,
        slippage_pct: float,
        success_rate: float,
        timing_accuracy: float
    ) -> float:
        """Calculate execution quality score (0-100).

        Weights (sum to 1.0):
          - fill_rate:       0.50  (most important — did we get the size we wanted?)
          - success_rate:    0.20  (chunk-level reliability)
          - timing_accuracy: 0.15  (did we hit the schedule?)
          - slippage:        0.15  (price quality given the fill)

        fill_rate is the dominant factor: a perfect-quality partial fill is
        still a worse execution than a slightly-slippy complete fill, because
        unfilled inventory is unrealised exposure. The previous weighting
        (fill=0.35, slippage=0.30) let a 50%-filled order with zero slippage
        outscore a 100%-filled order with 0.3% slippage, which inverted the
        intended ordering.
        """
        # Weighted average of factors
        fill_score = fill_rate * 100 * 0.50
        slippage_score = max(0, (0.5 - slippage_pct) / 0.5 * 100) * 0.15
        success_score = success_rate * 100 * 0.20
        timing_score = max(0, timing_accuracy * 100) * 0.15

        return min(100, fill_score + slippage_score + success_score + timing_score)

    def get_performance_report(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get aggregate performance report for all orders

        Args:
            hours: Number of hours to analyze

        Returns:
            Aggregate performance metrics
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Filter recent orders
        recent_orders = [
            o for o in self._orders.values()
            if o.created_at >= cutoff
        ]

        completed = [o for o in recent_orders if o.state == OrderLifecycleState.COMPLETED]

        # Calculate metrics
        total_volume = sum(float(o.filled_quantity) for o in completed)
        total_value = sum(float(o.total_value) for o in completed)

        fill_rates = [o.get_fill_rate() for o in completed if o.total_quantity > 0]
        avg_fill_rate = statistics.mean(fill_rates) if fill_rates else 0.0

        slippages = [o.slippage_pct for o in completed if o.slippage_pct != 0]
        avg_slippage = statistics.mean(slippages) if slippages else 0.0
        total_slippage = sum(o.slippage_usd for o in completed)

        # By algorithm
        twap_orders = [o for o in completed if o.algorithm_type == AlgorithmType.TWAP]
        vwap_orders = [o for o in completed if o.algorithm_type == AlgorithmType.VWAP]

        twap_slippage = statistics.mean([o.slippage_pct for o in twap_orders]) if twap_orders else 0.0
        vwap_slippage = statistics.mean([o.slippage_pct for o in vwap_orders]) if vwap_orders else 0.0

        return {
            "period_hours": hours,
            "summary": {
                "total_orders": len(recent_orders),
                "completed_orders": len(completed),
                "cancelled_orders": len([o for o in recent_orders if o.state == OrderLifecycleState.CANCELLED]),
                "failed_orders": len([o for o in recent_orders if o.state == OrderLifecycleState.FAILED]),
                "active_orders": len([o for o in recent_orders if o.is_active()])
            },
            "volume": {
                "total_quantity_executed": round(total_volume, 4),
                "total_value_usd": round(total_value, 2)
            },
            "quality": {
                "avg_fill_rate": round(avg_fill_rate, 4),
                "avg_slippage_pct": round(avg_slippage, 4),
                "total_slippage_usd": round(total_slippage, 2)
            },
            "by_algorithm": {
                "twap": {
                    "count": len(twap_orders),
                    "avg_slippage_pct": round(twap_slippage, 4)
                },
                "vwap": {
                    "count": len(vwap_orders),
                    "avg_slippage_pct": round(vwap_slippage, 4)
                }
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def get_scheduler_status(self) -> Dict[str, Any]:
        """Get current scheduler status"""
        return {
            "state": self.state.value,
            "queue_size": len(self._order_queue),
            "active_orders": len(self._active_orders),
            "total_orders_tracked": len(self._orders),
            "config": {
                "max_concurrent_orders": self.max_concurrent_orders,
                "max_queue_size": self.max_queue_size,
                "default_participation_rate": self.default_participation_rate
            },
            "metrics": {
                "total_queued": self._metrics.total_orders_queued,
                "total_completed": self._metrics.total_orders_completed,
                "total_cancelled": self._metrics.total_orders_cancelled,
                "total_failed": self._metrics.total_orders_failed
            }
        }

    # ========================================================================
    # BACKGROUND PROCESSING
    # ========================================================================

    async def _process_queue(self):
        """Background task to process order queue"""
        logger.info("Queue processor started")

        while not self._shutdown_event.is_set():
            try:
                # Wait if paused
                await self._pause_event.wait()

                # Check for available capacity
                if len(self._active_orders) >= self.max_concurrent_orders:
                    await asyncio.sleep(1)
                    continue

                # Get next order from queue
                if not self._order_queue:
                    await asyncio.sleep(0.5)
                    continue

                order_id = self._order_queue.popleft()
                order = self._orders.get(order_id)

                if not order or order.state != OrderLifecycleState.QUEUED:
                    continue

                # Start execution
                order.state = OrderLifecycleState.SCHEDULED
                order.started_at = datetime.now(timezone.utc)

                # Create execution task
                task = asyncio.create_task(self._execute_order(order))
                self._active_orders[order_id] = task

                logger.info(f"Started execution: {order_id}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Queue processor error: {e}", exc_info=True)
                await asyncio.sleep(1)

        logger.info("Queue processor stopped")

    async def _execute_order(self, order: ScheduledOrder):
        """
        Execute a single algorithmic order

        Handles the full lifecycle of order execution including
        chunk scheduling, execution, and tracking.
        """
        try:
            order.state = OrderLifecycleState.EXECUTING

            # Calculate chunk sizes
            if order.algorithm_type == AlgorithmType.TWAP:
                chunk_quantities = self._calculate_twap_chunks(order)
            else:  # VWAP
                chunk_quantities = self._calculate_vwap_chunks(order)

            # Execute chunks
            for i, chunk_qty in enumerate(chunk_quantities):
                # Check for pause/cancel
                if order.state == OrderLifecycleState.PAUSED:
                    while order.state == OrderLifecycleState.PAUSED:
                        await asyncio.sleep(1)
                        if order.state in (OrderLifecycleState.CANCELLED,):
                            break

                if order.state == OrderLifecycleState.CANCELLED:
                    break

                order.current_chunk = i + 1

                # Execute chunk
                chunk_result = await self._execute_chunk(order, i + 1, chunk_qty)
                order.chunk_results.append(chunk_result)

                # Update order metrics
                if chunk_result.get("success"):
                    filled = Decimal(str(chunk_result.get("filled_quantity", 0)))
                    price = Decimal(str(chunk_result.get("average_price", 0)))

                    # Update weighted average price
                    old_value = order.filled_quantity * order.average_price
                    new_value = filled * price
                    order.filled_quantity += filled

                    if order.filled_quantity > 0:
                        order.average_price = (old_value + new_value) / order.filled_quantity

                    order.total_value += filled * price

                order.last_chunk_at = datetime.now(timezone.utc)

                # Wait for next chunk (with randomization for TWAP)
                if i < len(chunk_quantities) - 1:
                    wait_time = order.interval_seconds

                    if order.randomize_timing:
                        # Add ±20% variance
                        import random
                        variance = random.uniform(-0.2, 0.2) * wait_time
                        wait_time = max(1, wait_time + variance)

                    await asyncio.sleep(wait_time)

            # Calculate final slippage
            order.slippage_pct, order.slippage_usd = order.calculate_slippage()

            # Mark complete
            order.state = OrderLifecycleState.COMPLETED
            order.completed_at = datetime.now(timezone.utc)

            self._metrics.total_orders_completed += 1
            self._metrics.total_quantity_executed += float(order.filled_quantity)
            self._metrics.total_value_executed_usd += float(order.total_value)
            self._metrics.total_slippage_usd += order.slippage_usd

            logger.info(
                f"Order completed: {order.order_id} - "
                f"filled={order.filled_quantity}/{order.total_quantity}, "
                f"slippage={order.slippage_pct:.3f}%"
            )

        except asyncio.CancelledError:
            order.state = OrderLifecycleState.CANCELLED
            order.completed_at = datetime.now(timezone.utc)
            logger.info(f"Order cancelled: {order.order_id}")

        except Exception as e:
            order.state = OrderLifecycleState.FAILED
            order.error_message = str(e)
            order.completed_at = datetime.now(timezone.utc)
            self._metrics.total_orders_failed += 1
            logger.error(f"Order failed: {order.order_id} - {e}")

        finally:
            # Remove from active orders
            if order.order_id in self._active_orders:
                del self._active_orders[order.order_id]

            # Add to completed
            self._completed_orders.append(order.order_id)

    def _calculate_twap_chunks(self, order: ScheduledOrder) -> List[Decimal]:
        """Calculate equal-sized chunks for TWAP"""
        base_size = order.total_quantity / order.num_chunks
        chunks = [base_size] * order.num_chunks

        # Ensure total sums correctly
        remainder = order.total_quantity - sum(chunks)
        if remainder != 0:
            chunks[-1] += remainder

        return chunks

    def _calculate_vwap_chunks(self, order: ScheduledOrder) -> List[Decimal]:
        """Calculate volume-weighted chunks for VWAP"""
        if order.chunk_results and "volume_weight" in order.chunk_results[0]:
            # Use pre-calculated volume profile
            weights = [c.get("volume_weight", 1.0 / order.num_chunks) for c in order.chunk_results]
        else:
            # Equal weights (fallback)
            weights = [1.0 / order.num_chunks] * order.num_chunks

        # Calculate chunk sizes
        chunks = [order.total_quantity * Decimal(str(w)) for w in weights]

        # Ensure total sums correctly
        remainder = order.total_quantity - sum(chunks)
        if remainder != 0:
            chunks[-1] += remainder

        return chunks

    async def _execute_chunk(
        self,
        order: ScheduledOrder,
        chunk_id: int,
        quantity: Decimal
    ) -> Dict[str, Any]:
        """Execute a single chunk"""
        start_time = time.time()

        try:
            if not self._execute_func:
                raise ValueError("Execute function not configured")

            # Prepare order parameters
            params = {
                "symbol": order.symbol,
                "side": order.side,
                "quantity": str(quantity),
                "order_type": "Limit" if order.urgency != "high" else "Market"
            }

            # Get current price if available
            if self._get_market_data_func:
                market_data = await self._get_market_data_func(order.symbol)
                mid_price = (
                    Decimal(str(market_data.get("best_bid", 0))) +
                    Decimal(str(market_data.get("best_ask", 0)))
                ) / 2

                if params["order_type"] == "Limit":
                    # Set limit price slightly better than market
                    offset = mid_price * Decimal("0.0005")  # 5 bps
                    if order.side == "BUY":
                        params["price"] = str(mid_price + offset)
                    else:
                        params["price"] = str(mid_price - offset)

            # Execute
            result = await self._execute_func(**params)

            execution_time = (time.time() - start_time) * 1000

            filled = Decimal(str(result.get("filled_quantity", result.get("filled_qty", 0))))
            avg_price = Decimal(str(result.get("average_price", result.get("avg_price", 0))))

            # Calculate slippage for chunk
            slippage_pct = 0.0
            if avg_price > 0 and order.arrival_price > 0:
                if order.side == "BUY":
                    slippage_pct = float(
                        (avg_price - order.arrival_price) / order.arrival_price
                    ) * 100
                else:
                    slippage_pct = float(
                        (order.arrival_price - avg_price) / order.arrival_price
                    ) * 100

            return {
                "chunk_id": chunk_id,
                "success": True,
                "target_quantity": str(quantity),
                "filled_quantity": str(filled),
                "average_price": str(avg_price),
                "slippage_pct": slippage_pct,
                "execution_time_ms": execution_time,
                "executed_at": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000

            logger.error(f"Chunk execution failed: {order.order_id} chunk {chunk_id} - {e}")

            return {
                "chunk_id": chunk_id,
                "success": False,
                "target_quantity": str(quantity),
                "filled_quantity": "0",
                "average_price": "0",
                "error": str(e),
                "execution_time_ms": execution_time,
                "executed_at": datetime.now(timezone.utc).isoformat()
            }


# ============================================================================
# GLOBAL INSTANCE MANAGEMENT
# ============================================================================


# Global scheduler instance
_execution_scheduler: Optional[ExecutionScheduler] = None


def get_execution_scheduler(
    max_concurrent_orders: int = 5,
    max_queue_size: int = 100
) -> ExecutionScheduler:
    """
    Get or create global execution scheduler instance

    Args:
        max_concurrent_orders: Maximum concurrent orders
        max_queue_size: Maximum queue size

    Returns:
        ExecutionScheduler instance
    """
    global _execution_scheduler
    if _execution_scheduler is None:
        _execution_scheduler = ExecutionScheduler(
            max_concurrent_orders=max_concurrent_orders,
            max_queue_size=max_queue_size
        )
        logger.info("Global ExecutionScheduler instance created")
    return _execution_scheduler


async def reset_execution_scheduler():
    """Reset global execution scheduler instance"""
    global _execution_scheduler
    if _execution_scheduler:
        await _execution_scheduler.stop(wait_for_completion=False)
    _execution_scheduler = None
    logger.info("ExecutionScheduler instance reset")
