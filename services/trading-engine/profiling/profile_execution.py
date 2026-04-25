"""
Execution Flow Profiling Module

Purpose:
- Profile order execution flow latency
- Identify bottlenecks in TWAP/VWAP algorithms
- Measure execution optimizer performance
- Track smart order router latency

Target Latencies:
- Order execution: <50ms p99
- TWAP chunk scheduling: <10ms
- VWAP volume analysis: <20ms
- Execution optimization: <15ms

Author: Backend Developer Agent
Date: 2025-12-12
"""

import asyncio
import cProfile
import io
import logging
import pstats
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple

# Attempt to import line_profiler for detailed analysis
try:
    from line_profiler import LineProfiler
    HAS_LINE_PROFILER = True
except ImportError:
    HAS_LINE_PROFILER = False

# Attempt to import memory_profiler
try:
    from memory_profiler import memory_usage
    HAS_MEMORY_PROFILER = True
except ImportError:
    HAS_MEMORY_PROFILER = False

import sys
sys.path.insert(0, "/mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine")

from app.execution.twap_vwap import (
    TWAPAlgorithm,
    VWAPAlgorithm,
    TWAPConfig,
    VWAPConfig,
    create_twap_algorithm,
    create_vwap_algorithm,
)
from app.execution.execution_optimizer import (
    ExecutionOptimizer,
    ExecutionOptimizerConfig,
    ExecutionUrgency,
)

logger = logging.getLogger(__name__)


@dataclass
class ProfileResult:
    """
    Result of a profiling run.

    Attributes:
        function_name: Name of profiled function
        iterations: Number of iterations run
        latencies_ms: List of latency measurements in milliseconds
        memory_mb: Memory usage in megabytes (if available)
        p50_ms: 50th percentile latency
        p95_ms: 95th percentile latency
        p99_ms: 99th percentile latency
        mean_ms: Mean latency
        std_ms: Standard deviation
        min_ms: Minimum latency
        max_ms: Maximum latency
        meets_target: Whether p99 meets target latency
        target_ms: Target latency threshold
        hotspots: Top functions by cumulative time
    """
    function_name: str
    iterations: int
    latencies_ms: List[float]
    memory_mb: Optional[float] = None
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    mean_ms: float = 0.0
    std_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    meets_target: bool = False
    target_ms: float = 50.0
    hotspots: List[Tuple[str, float]] = field(default_factory=list)

    def __post_init__(self):
        """Calculate statistics from latencies"""
        if self.latencies_ms:
            sorted_latencies = sorted(self.latencies_ms)
            n = len(sorted_latencies)

            self.mean_ms = statistics.mean(self.latencies_ms)
            self.std_ms = statistics.stdev(self.latencies_ms) if n > 1 else 0.0
            self.min_ms = min(self.latencies_ms)
            self.max_ms = max(self.latencies_ms)

            # Percentiles
            self.p50_ms = sorted_latencies[int(n * 0.50)]
            self.p95_ms = sorted_latencies[int(n * 0.95)]
            self.p99_ms = sorted_latencies[min(int(n * 0.99), n - 1)]

            self.meets_target = self.p99_ms <= self.target_ms

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for reporting"""
        return {
            "function_name": self.function_name,
            "iterations": self.iterations,
            "latency_stats": {
                "p50_ms": round(self.p50_ms, 3),
                "p95_ms": round(self.p95_ms, 3),
                "p99_ms": round(self.p99_ms, 3),
                "mean_ms": round(self.mean_ms, 3),
                "std_ms": round(self.std_ms, 3),
                "min_ms": round(self.min_ms, 3),
                "max_ms": round(self.max_ms, 3),
            },
            "memory_mb": round(self.memory_mb, 2) if self.memory_mb else None,
            "target_ms": self.target_ms,
            "meets_target": self.meets_target,
            "hotspots": self.hotspots[:10],  # Top 10
        }


def timing_decorator(func: Callable) -> Callable:
    """
    Decorator to measure function execution time.

    Usage:
        @timing_decorator
        def my_function():
            pass
    """
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.debug(f"{func.__name__} took {elapsed_ms:.3f}ms")
        return result, elapsed_ms

    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.debug(f"{func.__name__} took {elapsed_ms:.3f}ms")
        return result, elapsed_ms

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper


class ExecutionProfiler:
    """
    Comprehensive profiler for execution module components.

    Profiles:
    - TWAP algorithm schedule creation and execution
    - VWAP algorithm volume analysis and scheduling
    - Execution optimizer order type selection
    - Smart order router decision making

    Usage:
        profiler = ExecutionProfiler()

        # Profile specific component
        result = profiler.profile_twap_scheduling(iterations=100)

        # Run all profiles
        results = profiler.run_all_profiles()

        # Generate report
        report = profiler.generate_report(results)
    """

    def __init__(
        self,
        target_execution_ms: float = 50.0,
        target_scheduling_ms: float = 10.0,
        target_optimization_ms: float = 15.0,
    ):
        """
        Initialize execution profiler.

        Args:
            target_execution_ms: Target p99 for order execution
            target_scheduling_ms: Target p99 for chunk scheduling
            target_optimization_ms: Target p99 for execution optimization
        """
        self.target_execution_ms = target_execution_ms
        self.target_scheduling_ms = target_scheduling_ms
        self.target_optimization_ms = target_optimization_ms

        # Test data generators
        self._test_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        self._test_quantities = [Decimal("0.5"), Decimal("1.0"), Decimal("2.5")]
        self._test_prices = [Decimal("50000"), Decimal("3000"), Decimal("100")]

        logger.info(
            f"ExecutionProfiler initialized: "
            f"targets={{exec={target_execution_ms}ms, "
            f"sched={target_scheduling_ms}ms, "
            f"opt={target_optimization_ms}ms}}"
        )

    def profile_twap_scheduling(
        self,
        iterations: int = 100,
        use_cprofile: bool = True
    ) -> ProfileResult:
        """
        Profile TWAP schedule creation performance.

        This measures the time to create a chunk schedule for TWAP execution.
        Target: <10ms p99

        Args:
            iterations: Number of iterations to run
            use_cprofile: Whether to collect cProfile data

        Returns:
            ProfileResult with latency statistics
        """
        latencies = []
        profiler = cProfile.Profile() if use_cprofile else None

        for i in range(iterations):
            # Create fresh instance each time
            config = TWAPConfig(
                num_chunks=10 + (i % 5),  # Vary chunks
                interval_seconds=60,
                randomize_timing=True,
                randomize_size=True,
            )

            twap = TWAPAlgorithm(
                symbol=self._test_symbols[i % 3],
                side="BUY" if i % 2 == 0 else "SELL",
                quantity=self._test_quantities[i % 3],
                config=config,
                arrival_price=self._test_prices[i % 3],
            )

            # Profile schedule creation
            start = time.perf_counter()
            if profiler and i == iterations - 1:  # Profile last iteration
                profiler.enable()

            schedule = twap.create_chunk_schedule(
                avg_market_volume=1000.0 + (i * 10)
            )

            if profiler and i == iterations - 1:
                profiler.disable()

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        # Extract hotspots from cProfile
        hotspots = []
        if profiler:
            stats_stream = io.StringIO()
            stats = pstats.Stats(profiler, stream=stats_stream)
            stats.sort_stats('cumulative')
            stats.print_stats(20)

            # Parse stats for top functions
            for func, (cc, nc, tt, ct, callers) in stats.stats.items():
                filename, lineno, funcname = func
                if "twap_vwap" in filename or "execution" in filename:
                    hotspots.append((f"{funcname}:{lineno}", ct * 1000))

            hotspots.sort(key=lambda x: x[1], reverse=True)

        return ProfileResult(
            function_name="twap_create_chunk_schedule",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=self.target_scheduling_ms,
            hotspots=hotspots[:10],
        )

    def profile_vwap_volume_analysis(
        self,
        iterations: int = 100
    ) -> ProfileResult:
        """
        Profile VWAP volume profile analysis.

        Measures time to analyze historical volume and create weighted schedule.
        Target: <20ms p99

        Args:
            iterations: Number of iterations

        Returns:
            ProfileResult with latency statistics
        """
        latencies = []

        # Generate test volume data
        import random
        base_volumes = [random.uniform(800, 1200) for _ in range(50)]

        for i in range(iterations):
            config = VWAPConfig(
                volume_profile_periods=20 + (i % 10),
                volume_smoothing_factor=0.3,
            )

            vwap = VWAPAlgorithm(
                symbol=self._test_symbols[i % 3],
                side="BUY",
                quantity=self._test_quantities[i % 3],
                config=config,
                arrival_price=self._test_prices[i % 3],
            )

            # Vary volume data slightly
            volumes = [v * (0.9 + random.uniform(0, 0.2)) for v in base_volumes]

            start = time.perf_counter()

            # Profile volume analysis
            profile = vwap.analyze_volume_profile(volumes)

            # Profile schedule creation
            schedule = vwap.create_volume_weighted_schedule(
                volume_profile=profile,
                interval_seconds=60,
            )

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        return ProfileResult(
            function_name="vwap_volume_analysis_and_scheduling",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=20.0,
        )

    def profile_execution_optimizer(
        self,
        iterations: int = 100
    ) -> ProfileResult:
        """
        Profile execution optimizer decision making.

        Measures time to determine optimal order type and calculate costs.
        Target: <15ms p99

        Args:
            iterations: Number of iterations

        Returns:
            ProfileResult with latency statistics
        """
        latencies = []

        # Create optimizer
        optimizer = ExecutionOptimizer()

        urgencies = [
            ExecutionUrgency.CRITICAL,
            ExecutionUrgency.HIGH,
            ExecutionUrgency.MEDIUM,
            ExecutionUrgency.LOW,
        ]

        for i in range(iterations):
            symbol = self._test_symbols[i % 3]
            price = self._test_prices[i % 3]
            quantity = self._test_quantities[i % 3]
            urgency = urgencies[i % 4]

            # Vary spread
            spread_pct = 0.0002 + (i % 10) * 0.0001

            start = time.perf_counter()

            result = optimizer.optimize_execution(
                symbol=symbol,
                side="BUY" if i % 2 == 0 else "SELL",
                quantity=quantity,
                urgency=urgency,
                current_price=price,
                spread_pct=spread_pct,
                best_bid=price * Decimal("0.9999"),
                best_ask=price * Decimal("1.0001"),
                available_liquidity_usd=100000.0,
            )

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        return ProfileResult(
            function_name="execution_optimizer_optimize",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=self.target_optimization_ms,
        )

    def profile_cost_calculation(
        self,
        iterations: int = 1000
    ) -> ProfileResult:
        """
        Profile execution cost breakdown calculation.

        This is called frequently, needs to be very fast.
        Target: <5ms p99

        Args:
            iterations: Number of iterations

        Returns:
            ProfileResult
        """
        latencies = []

        optimizer = ExecutionOptimizer()

        for i in range(iterations):
            order_value = 10000 + (i % 100) * 100
            spread_pct = 0.0002 + (i % 10) * 0.0001
            slippage_pct = 0.0001 + (i % 5) * 0.0001

            start = time.perf_counter()

            # Profile internal cost calculation
            cost = optimizer._calculate_cost_breakdown(
                order_value_usd=order_value,
                is_maker=i % 2 == 0,
                slippage_pct=slippage_pct,
                spread_pct=spread_pct,
                urgency=ExecutionUrgency.MEDIUM,
                include_opportunity_cost=i % 3 == 0,
            )

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        return ProfileResult(
            function_name="calculate_cost_breakdown",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=5.0,
        )

    def run_all_profiles(
        self,
        iterations: int = 100
    ) -> Dict[str, ProfileResult]:
        """
        Run all execution profiling tests.

        Args:
            iterations: Number of iterations per test

        Returns:
            Dictionary of ProfileResult objects keyed by test name
        """
        logger.info(f"Running all execution profiles with {iterations} iterations")

        results = {}

        # TWAP scheduling
        logger.info("Profiling TWAP scheduling...")
        results["twap_scheduling"] = self.profile_twap_scheduling(iterations)

        # VWAP volume analysis
        logger.info("Profiling VWAP volume analysis...")
        results["vwap_analysis"] = self.profile_vwap_volume_analysis(iterations)

        # Execution optimizer
        logger.info("Profiling execution optimizer...")
        results["execution_optimizer"] = self.profile_execution_optimizer(iterations)

        # Cost calculation
        logger.info("Profiling cost calculation...")
        results["cost_calculation"] = self.profile_cost_calculation(iterations * 10)

        return results

    def generate_report(
        self,
        results: Dict[str, ProfileResult]
    ) -> str:
        """
        Generate text report from profiling results.

        Args:
            results: Dictionary of ProfileResult objects

        Returns:
            Formatted report string
        """
        lines = [
            "=" * 80,
            "EXECUTION MODULE PROFILING REPORT",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            "=" * 80,
            "",
        ]

        all_pass = True

        for name, result in results.items():
            status = "PASS" if result.meets_target else "FAIL"
            if not result.meets_target:
                all_pass = False

            lines.extend([
                f"Test: {name}",
                f"  Function: {result.function_name}",
                f"  Iterations: {result.iterations}",
                f"  Target: {result.target_ms}ms p99",
                f"  Status: {status}",
                f"",
                f"  Latency Statistics:",
                f"    p50:  {result.p50_ms:>8.3f}ms",
                f"    p95:  {result.p95_ms:>8.3f}ms",
                f"    p99:  {result.p99_ms:>8.3f}ms",
                f"    mean: {result.mean_ms:>8.3f}ms",
                f"    std:  {result.std_ms:>8.3f}ms",
                f"    min:  {result.min_ms:>8.3f}ms",
                f"    max:  {result.max_ms:>8.3f}ms",
                "",
            ])

            if result.hotspots:
                lines.append("  Top Hotspots:")
                for func, time_ms in result.hotspots[:5]:
                    lines.append(f"    {func}: {time_ms:.3f}ms")
                lines.append("")

            lines.append("-" * 40)
            lines.append("")

        # Summary
        lines.extend([
            "=" * 80,
            f"SUMMARY: {'ALL TESTS PASSED' if all_pass else 'SOME TESTS FAILED'}",
            "=" * 80,
        ])

        return "\n".join(lines)


def profile_execution_flow(iterations: int = 100) -> Dict[str, ProfileResult]:
    """
    Convenience function to run execution profiling.

    Args:
        iterations: Number of iterations per test

    Returns:
        Dictionary of profiling results
    """
    profiler = ExecutionProfiler()
    results = profiler.run_all_profiles(iterations)

    # Print report
    report = profiler.generate_report(results)
    print(report)

    return results


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run profiling
    results = profile_execution_flow(iterations=100)

    # Check targets
    all_pass = all(r.meets_target for r in results.values())
    exit(0 if all_pass else 1)
