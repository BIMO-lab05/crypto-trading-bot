"""
Execution Timer - Position Monitoring Interval Control
Research Source: FIA Best Practices, Low-Latency Trading Systems

Purpose:
- Control monitoring intervals for position management
- Prevent excessive API calls during position monitoring
- Adaptive timing based on market conditions
- Track execution latency for optimization

RESEARCH: Position monitoring needs proper interval control to balance
responsiveness with resource usage. High-frequency monitoring without
intervals causes unnecessary load and API rate limiting.
"""

import logging
import time
import asyncio
from enum import Enum
from typing import Optional, Dict, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque

logger = logging.getLogger(__name__)


class TimingMode(Enum):
    """Timing modes for different scenarios"""
    AGGRESSIVE = "aggressive"     # Fast monitoring (5-10s)
    NORMAL = "normal"            # Standard monitoring (15-30s)
    CONSERVATIVE = "conservative" # Slow monitoring (60s+)
    ADAPTIVE = "adaptive"         # Adjusts based on conditions


@dataclass
class TimingConfig:
    """
    Configuration for execution timing

    RESEARCH-BACKED INTERVALS:
    - Position monitoring: 10-30 seconds is typical
    - Price updates: 5-15 seconds for active positions
    - Trailing stop updates: 10-20 seconds
    """
    position_check_interval: float = 15.0     # Seconds between position checks
    price_update_interval: float = 10.0       # Seconds between price updates
    trailing_stop_interval: float = 15.0      # Seconds for trailing stop updates
    signal_check_interval: float = 30.0       # Seconds between signal checks
    min_interval: float = 5.0                 # Minimum allowed interval
    max_interval: float = 300.0               # Maximum allowed interval
    adaptive_factor: float = 1.5              # Multiplier for adaptive adjustments


@dataclass
class LatencyRecord:
    """Record of execution latency"""
    operation: str
    latency_ms: float
    timestamp: datetime
    success: bool


@dataclass
class LatencyStats:
    """Aggregate latency statistics"""
    total_operations: int = 0
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    min_latency_ms: float = float('inf')
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    failed_operations: int = 0


class ExecutionTimer:
    """
    Execution Timer for Position Monitoring

    RESEARCH-BACKED IMPLEMENTATION:
    - Controls intervals for various monitoring operations
    - Prevents excessive API calls
    - Tracks latency for optimization
    - Adapts intervals based on market conditions

    Usage:
        timer = ExecutionTimer()

        # In monitoring loop
        if timer.should_check_positions():
            await check_positions()
            timer.record_check("positions")

        # Or use as context manager
        async with timer.timed_operation("price_update"):
            await get_price()
    """

    def __init__(self, config: Optional[TimingConfig] = None):
        """
        Initialize execution timer

        Args:
            config: Timing configuration
        """
        self.config = config or TimingConfig()
        self.mode = TimingMode.NORMAL
        self._last_checks: Dict[str, float] = {}
        self._latency_history: deque = deque(maxlen=1000)
        self._stats: Dict[str, LatencyStats] = {}
        self._adaptive_multipliers: Dict[str, float] = {}

        logger.info(
            f"ExecutionTimer initialized: "
            f"position_check={self.config.position_check_interval}s, "
            f"price_update={self.config.price_update_interval}s"
        )

    def should_check(self, operation: str, interval: Optional[float] = None) -> bool:
        """
        Check if enough time has passed to perform an operation

        Args:
            operation: Name of the operation
            interval: Optional override interval (seconds)

        Returns:
            True if should perform operation
        """
        now = time.time()
        last_check = self._last_checks.get(operation, 0)

        # Get appropriate interval
        if interval is None:
            interval = self._get_interval(operation)

        # Apply adaptive multiplier if in adaptive mode
        if self.mode == TimingMode.ADAPTIVE:
            multiplier = self._adaptive_multipliers.get(operation, 1.0)
            interval *= multiplier

        elapsed = now - last_check
        should_check = elapsed >= interval

        if should_check:
            logger.debug(f"Timer: {operation} ready (elapsed: {elapsed:.1f}s >= {interval:.1f}s)")

        return should_check

    def should_check_positions(self) -> bool:
        """Check if should check positions"""
        return self.should_check("positions", self.config.position_check_interval)

    def should_update_price(self) -> bool:
        """Check if should update price"""
        return self.should_check("price_update", self.config.price_update_interval)

    def should_update_trailing_stops(self) -> bool:
        """Check if should update trailing stops"""
        return self.should_check("trailing_stop", self.config.trailing_stop_interval)

    def should_check_signals(self) -> bool:
        """Check if should check signals"""
        return self.should_check("signals", self.config.signal_check_interval)

    def record_check(self, operation: str):
        """
        Record that an operation was performed

        Args:
            operation: Name of the operation
        """
        self._last_checks[operation] = time.time()

    def _get_interval(self, operation: str) -> float:
        """Get interval for an operation based on mode"""
        base_interval = {
            "positions": self.config.position_check_interval,
            "price_update": self.config.price_update_interval,
            "trailing_stop": self.config.trailing_stop_interval,
            "signals": self.config.signal_check_interval,
        }.get(operation, self.config.position_check_interval)

        # Apply mode multiplier
        if self.mode == TimingMode.AGGRESSIVE:
            return max(base_interval * 0.5, self.config.min_interval)
        elif self.mode == TimingMode.CONSERVATIVE:
            return min(base_interval * 2.0, self.config.max_interval)

        return base_interval

    def set_mode(self, mode: TimingMode):
        """
        Set timing mode

        Args:
            mode: New timing mode
        """
        self.mode = mode
        logger.info(f"ExecutionTimer mode set to: {mode.value}")

    def set_aggressive_for_symbol(self, symbol: str):
        """
        Enable aggressive monitoring for a specific symbol

        Use when position is near stop loss or take profit
        """
        self._adaptive_multipliers[f"positions_{symbol}"] = 0.5
        self._adaptive_multipliers[f"price_update_{symbol}"] = 0.5
        logger.info(f"Aggressive monitoring enabled for {symbol}")

    def set_normal_for_symbol(self, symbol: str):
        """Reset to normal monitoring for a symbol"""
        self._adaptive_multipliers.pop(f"positions_{symbol}", None)
        self._adaptive_multipliers.pop(f"price_update_{symbol}", None)
        logger.info(f"Normal monitoring restored for {symbol}")

    async def timed_operation(self, operation: str):
        """
        Context manager for timing operations

        Usage:
            async with timer.timed_operation("price_update"):
                await get_price()
        """
        return TimedOperationContext(self, operation)

    def record_latency(
        self,
        operation: str,
        latency_ms: float,
        success: bool = True
    ):
        """
        Record latency for an operation

        Args:
            operation: Operation name
            latency_ms: Latency in milliseconds
            success: Whether operation succeeded
        """
        record = LatencyRecord(
            operation=operation,
            latency_ms=latency_ms,
            timestamp=datetime.now(),
            success=success
        )
        self._latency_history.append(record)
        self._update_stats(operation, latency_ms, success)

        # Adapt interval if latency is high
        if self.mode == TimingMode.ADAPTIVE:
            self._adapt_interval(operation, latency_ms)

    def _update_stats(self, operation: str, latency_ms: float, success: bool):
        """Update latency statistics"""
        if operation not in self._stats:
            self._stats[operation] = LatencyStats()

        stats = self._stats[operation]
        stats.total_operations += 1

        if not success:
            stats.failed_operations += 1

        # Update averages
        stats.avg_latency_ms = (
            (stats.avg_latency_ms * (stats.total_operations - 1) + latency_ms)
            / stats.total_operations
        )

        if latency_ms > stats.max_latency_ms:
            stats.max_latency_ms = latency_ms
        if latency_ms < stats.min_latency_ms:
            stats.min_latency_ms = latency_ms

        # Calculate percentiles from recent history
        operation_records = [r for r in self._latency_history if r.operation == operation][-100:]
        if operation_records:
            latencies = sorted([r.latency_ms for r in operation_records])
            stats.p95_latency_ms = latencies[int(len(latencies) * 0.95)] if len(latencies) >= 20 else 0
            stats.p99_latency_ms = latencies[int(len(latencies) * 0.99)] if len(latencies) >= 100 else 0

    def _adapt_interval(self, operation: str, latency_ms: float):
        """
        Adapt interval based on latency

        RESEARCH: If operations are taking longer, increase interval
        to prevent cascading delays
        """
        if operation not in self._stats:
            return

        avg_latency = self._stats[operation].avg_latency_ms
        if avg_latency == 0:
            return

        # If current latency is significantly higher than average
        if latency_ms > avg_latency * 2:
            current_mult = self._adaptive_multipliers.get(operation, 1.0)
            new_mult = min(current_mult * self.config.adaptive_factor, 3.0)
            self._adaptive_multipliers[operation] = new_mult
            logger.info(
                f"Interval adapted for {operation}: "
                f"latency {latency_ms:.0f}ms > {avg_latency:.0f}ms avg, "
                f"multiplier {current_mult:.1f} -> {new_mult:.1f}"
            )
        elif latency_ms < avg_latency * 0.5:
            # Latency improved, gradually reduce multiplier
            current_mult = self._adaptive_multipliers.get(operation, 1.0)
            if current_mult > 1.0:
                new_mult = max(current_mult / self.config.adaptive_factor, 1.0)
                self._adaptive_multipliers[operation] = new_mult

    def get_time_until_next(self, operation: str) -> float:
        """
        Get seconds until next check is allowed

        Args:
            operation: Operation name

        Returns:
            Seconds until next check (0 if ready now)
        """
        now = time.time()
        last_check = self._last_checks.get(operation, 0)
        interval = self._get_interval(operation)

        if self.mode == TimingMode.ADAPTIVE:
            multiplier = self._adaptive_multipliers.get(operation, 1.0)
            interval *= multiplier

        remaining = interval - (now - last_check)
        return max(0, remaining)

    async def wait_for_next(self, operation: str):
        """
        Wait until next check is allowed

        Args:
            operation: Operation name
        """
        wait_time = self.get_time_until_next(operation)
        if wait_time > 0:
            logger.debug(f"Waiting {wait_time:.1f}s for {operation}")
            await asyncio.sleep(wait_time)

    def get_status(self) -> Dict:
        """Get timer status"""
        return {
            "mode": self.mode.value,
            "config": {
                "position_check_interval": self.config.position_check_interval,
                "price_update_interval": self.config.price_update_interval,
                "trailing_stop_interval": self.config.trailing_stop_interval,
                "signal_check_interval": self.config.signal_check_interval,
            },
            "last_checks": {
                op: datetime.fromtimestamp(ts).isoformat()
                for op, ts in self._last_checks.items()
            },
            "time_until_next": {
                "positions": round(self.get_time_until_next("positions"), 1),
                "price_update": round(self.get_time_until_next("price_update"), 1),
                "trailing_stop": round(self.get_time_until_next("trailing_stop"), 1),
                "signals": round(self.get_time_until_next("signals"), 1),
            },
            "latency_stats": {
                op: {
                    "total_operations": stats.total_operations,
                    "avg_latency_ms": round(stats.avg_latency_ms, 2),
                    "max_latency_ms": round(stats.max_latency_ms, 2),
                    "p95_latency_ms": round(stats.p95_latency_ms, 2),
                    "failed_operations": stats.failed_operations,
                }
                for op, stats in self._stats.items()
            },
            "adaptive_multipliers": self._adaptive_multipliers,
        }


class TimedOperationContext:
    """Context manager for timed operations"""

    def __init__(self, timer: ExecutionTimer, operation: str):
        self.timer = timer
        self.operation = operation
        self.start_time: float = 0

    async def __aenter__(self):
        self.start_time = time.time()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        latency_ms = (time.time() - self.start_time) * 1000
        success = exc_type is None
        self.timer.record_latency(self.operation, latency_ms, success)
        self.timer.record_check(self.operation)
        return False  # Don't suppress exceptions


# Global timer instance
_execution_timer: Optional[ExecutionTimer] = None


def get_execution_timer(config: Optional[TimingConfig] = None) -> ExecutionTimer:
    """Get or create global execution timer"""
    global _execution_timer
    if _execution_timer is None:
        _execution_timer = ExecutionTimer(config)
    return _execution_timer
