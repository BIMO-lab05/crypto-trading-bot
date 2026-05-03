"""
Execution Performance Benchmark

Measures:
- Order execution throughput (orders/second)
- TWAP/VWAP scheduling throughput
- Execution optimizer throughput
- Cost calculation throughput

Targets:
- Order execution: >100 orders/sec
- TWAP scheduling: >1000 schedules/sec
- Optimization: >500 optimizations/sec

Author: Backend Developer Agent
Date: 2025-12-12
"""

import logging
import random
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))

from app.execution.twap_vwap import (
    TWAPAlgorithm,
    VWAPAlgorithm,
    TWAPConfig,
    VWAPConfig,
)
from app.execution.execution_optimizer import (
    ExecutionOptimizer,
    ExecutionUrgency,
)

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """
    Result of a throughput benchmark.

    Attributes:
        test_name: Name of the benchmark test
        duration_seconds: Test duration
        total_operations: Total operations completed
        throughput_per_sec: Operations per second
        target_throughput: Target throughput
        meets_target: Whether target was met
        latency_p50_ms: 50th percentile latency
        latency_p99_ms: 99th percentile latency
        memory_mb: Memory usage
    """
    test_name: str
    duration_seconds: float
    total_operations: int
    throughput_per_sec: float
    target_throughput: float
    meets_target: bool = False
    latency_p50_ms: float = 0.0
    latency_p99_ms: float = 0.0
    memory_mb: Optional[float] = None
    latencies_ms: List[float] = field(default_factory=list)

    def __post_init__(self):
        """Calculate derived metrics"""
        self.meets_target = self.throughput_per_sec >= self.target_throughput

        if self.latencies_ms:
            sorted_latencies = sorted(self.latencies_ms)
            n = len(sorted_latencies)
            self.latency_p50_ms = sorted_latencies[int(n * 0.50)]
            self.latency_p99_ms = sorted_latencies[min(int(n * 0.99), n - 1)]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "test_name": self.test_name,
            "duration_seconds": round(self.duration_seconds, 2),
            "total_operations": self.total_operations,
            "throughput_per_sec": round(self.throughput_per_sec, 1),
            "target_throughput": self.target_throughput,
            "meets_target": self.meets_target,
            "latency_p50_ms": round(self.latency_p50_ms, 3),
            "latency_p99_ms": round(self.latency_p99_ms, 3),
            "memory_mb": round(self.memory_mb, 2) if self.memory_mb else None,
        }


class ExecutionBenchmark:
    """
    Benchmark suite for execution module.

    Tests throughput and latency of:
    - TWAP schedule creation
    - VWAP volume analysis
    - Execution optimization
    - Cost calculations

    Usage:
        benchmark = ExecutionBenchmark()
        results = benchmark.run_all_benchmarks(duration_seconds=10)
        benchmark.print_report(results)
    """

    def __init__(
        self,
        target_twap_throughput: float = 1000.0,
        target_vwap_throughput: float = 500.0,
        target_optimizer_throughput: float = 500.0,
        target_cost_calc_throughput: float = 5000.0,
    ):
        """
        Initialize execution benchmark.

        Args:
            target_twap_throughput: Target TWAP schedules/sec
            target_vwap_throughput: Target VWAP schedules/sec
            target_optimizer_throughput: Target optimizations/sec
            target_cost_calc_throughput: Target cost calculations/sec
        """
        self.target_twap_throughput = target_twap_throughput
        self.target_vwap_throughput = target_vwap_throughput
        self.target_optimizer_throughput = target_optimizer_throughput
        self.target_cost_calc_throughput = target_cost_calc_throughput

        # Test data
        self._test_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        self._test_quantities = [Decimal("0.5"), Decimal("1.0"), Decimal("2.5")]
        self._test_prices = [Decimal("50000"), Decimal("3000"), Decimal("100")]

        logger.info("ExecutionBenchmark initialized")

    def benchmark_twap_scheduling(
        self,
        duration_seconds: float = 10.0
    ) -> BenchmarkResult:
        """
        Benchmark TWAP schedule creation throughput.

        Args:
            duration_seconds: Test duration

        Returns:
            BenchmarkResult with throughput metrics
        """
        latencies = []
        operations = 0
        start_time = time.perf_counter()
        end_time = start_time + duration_seconds

        i = 0
        while time.perf_counter() < end_time:
            config = TWAPConfig(
                num_chunks=10 + (i % 5),
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

            op_start = time.perf_counter()
            schedule = twap.create_chunk_schedule(avg_market_volume=1000.0)
            op_end = time.perf_counter()

            latencies.append((op_end - op_start) * 1000)
            operations += 1
            i += 1

        actual_duration = time.perf_counter() - start_time
        throughput = operations / actual_duration

        return BenchmarkResult(
            test_name="twap_scheduling",
            duration_seconds=actual_duration,
            total_operations=operations,
            throughput_per_sec=throughput,
            target_throughput=self.target_twap_throughput,
            latencies_ms=latencies,
        )

    def benchmark_vwap_analysis(
        self,
        duration_seconds: float = 10.0
    ) -> BenchmarkResult:
        """
        Benchmark VWAP volume analysis and scheduling.

        Args:
            duration_seconds: Test duration

        Returns:
            BenchmarkResult with throughput metrics
        """
        latencies = []
        operations = 0
        start_time = time.perf_counter()
        end_time = start_time + duration_seconds

        # Pre-generate volume data
        base_volumes = [random.uniform(800, 1200) for _ in range(50)]

        i = 0
        while time.perf_counter() < end_time:
            config = VWAPConfig(
                volume_profile_periods=20,
                volume_smoothing_factor=0.3,
            )

            vwap = VWAPAlgorithm(
                symbol=self._test_symbols[i % 3],
                side="BUY",
                quantity=self._test_quantities[i % 3],
                config=config,
                arrival_price=self._test_prices[i % 3],
            )

            # Vary volume slightly
            volumes = [v * random.uniform(0.95, 1.05) for v in base_volumes]

            op_start = time.perf_counter()
            profile = vwap.analyze_volume_profile(volumes)
            schedule = vwap.create_volume_weighted_schedule(profile, interval_seconds=60)
            op_end = time.perf_counter()

            latencies.append((op_end - op_start) * 1000)
            operations += 1
            i += 1

        actual_duration = time.perf_counter() - start_time
        throughput = operations / actual_duration

        return BenchmarkResult(
            test_name="vwap_analysis_and_scheduling",
            duration_seconds=actual_duration,
            total_operations=operations,
            throughput_per_sec=throughput,
            target_throughput=self.target_vwap_throughput,
            latencies_ms=latencies,
        )

    def benchmark_execution_optimizer(
        self,
        duration_seconds: float = 10.0
    ) -> BenchmarkResult:
        """
        Benchmark execution optimizer.

        Args:
            duration_seconds: Test duration

        Returns:
            BenchmarkResult with throughput metrics
        """
        latencies = []
        operations = 0
        start_time = time.perf_counter()
        end_time = start_time + duration_seconds

        optimizer = ExecutionOptimizer()

        urgencies = [
            ExecutionUrgency.CRITICAL,
            ExecutionUrgency.HIGH,
            ExecutionUrgency.MEDIUM,
            ExecutionUrgency.LOW,
        ]

        i = 0
        while time.perf_counter() < end_time:
            symbol = self._test_symbols[i % 3]
            price = self._test_prices[i % 3]
            quantity = self._test_quantities[i % 3]
            urgency = urgencies[i % 4]
            spread_pct = 0.0002 + (i % 10) * 0.0001

            op_start = time.perf_counter()

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

            op_end = time.perf_counter()

            latencies.append((op_end - op_start) * 1000)
            operations += 1
            i += 1

        actual_duration = time.perf_counter() - start_time
        throughput = operations / actual_duration

        return BenchmarkResult(
            test_name="execution_optimizer",
            duration_seconds=actual_duration,
            total_operations=operations,
            throughput_per_sec=throughput,
            target_throughput=self.target_optimizer_throughput,
            latencies_ms=latencies,
        )

    def benchmark_cost_calculation(
        self,
        duration_seconds: float = 10.0
    ) -> BenchmarkResult:
        """
        Benchmark cost breakdown calculation.

        Args:
            duration_seconds: Test duration

        Returns:
            BenchmarkResult with throughput metrics
        """
        latencies = []
        operations = 0
        start_time = time.perf_counter()
        end_time = start_time + duration_seconds

        optimizer = ExecutionOptimizer()

        i = 0
        while time.perf_counter() < end_time:
            order_value = 10000 + (i % 100) * 100
            spread_pct = 0.0002 + (i % 10) * 0.0001
            slippage_pct = 0.0001 + (i % 5) * 0.0001

            op_start = time.perf_counter()

            cost = optimizer._calculate_cost_breakdown(
                order_value_usd=order_value,
                is_maker=i % 2 == 0,
                slippage_pct=slippage_pct,
                spread_pct=spread_pct,
                urgency=ExecutionUrgency.MEDIUM,
                include_opportunity_cost=i % 3 == 0,
            )

            op_end = time.perf_counter()

            latencies.append((op_end - op_start) * 1000)
            operations += 1
            i += 1

        actual_duration = time.perf_counter() - start_time
        throughput = operations / actual_duration

        return BenchmarkResult(
            test_name="cost_calculation",
            duration_seconds=actual_duration,
            total_operations=operations,
            throughput_per_sec=throughput,
            target_throughput=self.target_cost_calc_throughput,
            latencies_ms=latencies,
        )

    def run_all_benchmarks(
        self,
        duration_seconds: float = 10.0
    ) -> Dict[str, BenchmarkResult]:
        """
        Run all execution benchmarks.

        Args:
            duration_seconds: Duration per test

        Returns:
            Dictionary of benchmark results
        """
        logger.info(f"Running all execution benchmarks ({duration_seconds}s each)")

        results = {}

        logger.info("Benchmarking TWAP scheduling...")
        results["twap_scheduling"] = self.benchmark_twap_scheduling(duration_seconds)

        logger.info("Benchmarking VWAP analysis...")
        results["vwap_analysis"] = self.benchmark_vwap_analysis(duration_seconds)

        logger.info("Benchmarking execution optimizer...")
        results["execution_optimizer"] = self.benchmark_execution_optimizer(duration_seconds)

        logger.info("Benchmarking cost calculation...")
        results["cost_calculation"] = self.benchmark_cost_calculation(duration_seconds)

        return results

    def print_report(self, results: Dict[str, BenchmarkResult]) -> str:
        """
        Print benchmark report.

        Args:
            results: Benchmark results

        Returns:
            Formatted report string
        """
        lines = [
            "=" * 80,
            "EXECUTION BENCHMARK REPORT",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            "=" * 80,
            "",
            f"{'Test':<30} {'Throughput':>15} {'Target':>12} {'p99 Latency':>12} {'Status':>10}",
            "-" * 80,
        ]

        all_pass = True
        for name, result in results.items():
            status = "PASS" if result.meets_target else "FAIL"
            if not result.meets_target:
                all_pass = False

            lines.append(
                f"{name:<30} {result.throughput_per_sec:>12.1f}/s "
                f"{result.target_throughput:>9.0f}/s "
                f"{result.latency_p99_ms:>9.3f}ms "
                f"{status:>10}"
            )

        lines.extend([
            "",
            "=" * 80,
            f"SUMMARY: {'ALL BENCHMARKS PASSED' if all_pass else 'SOME BENCHMARKS FAILED'}",
            "=" * 80,
        ])

        report = "\n".join(lines)
        print(report)
        return report


def run_execution_benchmark(duration_seconds: float = 10.0) -> Dict[str, BenchmarkResult]:
    """
    Convenience function to run execution benchmarks.

    Args:
        duration_seconds: Duration per test

    Returns:
        Dictionary of benchmark results
    """
    benchmark = ExecutionBenchmark()
    results = benchmark.run_all_benchmarks(duration_seconds)
    benchmark.print_report(results)
    return results


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    results = run_execution_benchmark(duration_seconds=10)

    # Exit with error if any benchmark failed
    all_pass = all(r.meets_target for r in results.values())
    exit(0 if all_pass else 1)
