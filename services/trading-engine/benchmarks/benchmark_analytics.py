"""
Analytics Performance Benchmark

Measures:
- Comprehensive metrics throughput
- Risk-adjusted metrics throughput
- Attribution calculation throughput
- Trade addition throughput

Targets:
- Comprehensive metrics: >10 calcs/sec
- Risk-adjusted metrics: >50 calcs/sec
- Attribution: >100 calcs/sec
- Trade addition: >1000 trades/sec

Author: Backend Developer Agent
Date: 2025-12-12
"""

import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))

from app.analytics.advanced_metrics import (
    AdvancedMetricsCalculator,
    TradeMetadata,
    reset_advanced_metrics_calculator,
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
        trades_count: Number of trades in test data
    """
    test_name: str
    duration_seconds: float
    total_operations: int
    throughput_per_sec: float
    target_throughput: float
    meets_target: bool = False
    latency_p50_ms: float = 0.0
    latency_p99_ms: float = 0.0
    trades_count: int = 0
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
            "trades_count": self.trades_count,
        }


class AnalyticsBenchmark:
    """
    Benchmark suite for analytics/metrics module.

    Tests throughput and latency of:
    - Comprehensive metrics calculation
    - Risk-adjusted metrics
    - Attribution analysis
    - Trade addition

    Usage:
        benchmark = AnalyticsBenchmark()
        results = benchmark.run_all_benchmarks(duration_seconds=10)
        benchmark.print_report(results)
    """

    def __init__(
        self,
        target_comprehensive_throughput: float = 10.0,
        target_risk_adjusted_throughput: float = 50.0,
        target_attribution_throughput: float = 100.0,
        target_trade_addition_throughput: float = 1000.0,
        target_metrics_update_throughput: float = 1000.0,
    ):
        """
        Initialize analytics benchmark.

        Args:
            target_comprehensive_throughput: Target comprehensive calcs/sec
            target_risk_adjusted_throughput: Target risk-adjusted calcs/sec
            target_attribution_throughput: Target attribution calcs/sec
            target_trade_addition_throughput: Target trade additions/sec
            target_metrics_update_throughput: Target metrics updates/sec
        """
        self.target_comprehensive_throughput = target_comprehensive_throughput
        self.target_risk_adjusted_throughput = target_risk_adjusted_throughput
        self.target_attribution_throughput = target_attribution_throughput
        self.target_trade_addition_throughput = target_trade_addition_throughput
        self.target_metrics_update_throughput = target_metrics_update_throughput

        # Test data
        self._test_symbols = [
            "BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOTUSDT",
            "LINKUSDT", "MATICUSDT", "ATOMUSDT", "NEARUSDT", "FTMUSDT",
        ]

        self._test_strategies = [
            "momentum", "mean_reversion", "pairs_trading",
            "trend_following", "stat_arb",
        ]

        logger.info("AnalyticsBenchmark initialized")

    def _generate_trades(self, n_trades: int) -> List[TradeMetadata]:
        """Generate synthetic trade data"""
        trades = []
        base_time = datetime.now(timezone.utc) - timedelta(days=90)

        for i in range(n_trades):
            pnl = random.gauss(50, 200)
            is_winner = pnl > 0
            pnl_pct = pnl / 10000

            trade = TradeMetadata(
                trade_id=f"trade_{i:04d}",
                timestamp=base_time + timedelta(hours=i * 4),
                pnl=pnl,
                pnl_pct=pnl_pct,
                strategy=self._test_strategies[i % len(self._test_strategies)],
                symbol=self._test_symbols[i % len(self._test_symbols)],
                direction="long" if i % 2 == 0 else "short",
                duration_seconds=random.randint(300, 86400),
                is_winner=is_winner,
            )
            trades.append(trade)

        return trades

    def _setup_calculator(self, n_trades: int = 500) -> AdvancedMetricsCalculator:
        """Create and populate a metrics calculator"""
        reset_advanced_metrics_calculator()

        calculator = AdvancedMetricsCalculator(
            initial_capital=10000.0,
            risk_free_rate=0.02,
            rolling_window=30,
        )

        trades = self._generate_trades(n_trades)
        calculator.add_trades_batch(trades)

        benchmark_returns = [random.gauss(0.0005, 0.02) for _ in range(n_trades)]
        calculator.set_benchmark_returns(benchmark_returns)

        return calculator

    def benchmark_comprehensive_metrics(
        self,
        duration_seconds: float = 10.0,
        trades_count: int = 500
    ) -> BenchmarkResult:
        """
        Benchmark comprehensive metrics calculation.

        Args:
            duration_seconds: Test duration
            trades_count: Number of trades in calculator

        Returns:
            BenchmarkResult with throughput metrics
        """
        latencies = []
        operations = 0
        start_time = time.perf_counter()
        end_time = start_time + duration_seconds

        while time.perf_counter() < end_time:
            calculator = self._setup_calculator(trades_count)

            op_start = time.perf_counter()
            metrics = calculator.get_comprehensive_metrics(force_recalculate=True)
            op_end = time.perf_counter()

            latencies.append((op_end - op_start) * 1000)
            operations += 1

        actual_duration = time.perf_counter() - start_time
        throughput = operations / actual_duration

        return BenchmarkResult(
            test_name="comprehensive_metrics",
            duration_seconds=actual_duration,
            total_operations=operations,
            throughput_per_sec=throughput,
            target_throughput=self.target_comprehensive_throughput,
            latencies_ms=latencies,
            trades_count=trades_count,
        )

    def benchmark_risk_adjusted_metrics(
        self,
        duration_seconds: float = 10.0,
        trades_count: int = 500
    ) -> BenchmarkResult:
        """
        Benchmark risk-adjusted metrics calculation.

        Args:
            duration_seconds: Test duration
            trades_count: Number of trades

        Returns:
            BenchmarkResult with throughput metrics
        """
        latencies = []
        operations = 0
        start_time = time.perf_counter()
        end_time = start_time + duration_seconds

        calculator = self._setup_calculator(trades_count)

        i = 0
        while time.perf_counter() < end_time:
            # Add a trade to invalidate cache
            trade = TradeMetadata(
                trade_id=f"new_trade_{i}",
                timestamp=datetime.now(timezone.utc),
                pnl=random.gauss(50, 200),
                pnl_pct=random.gauss(0.005, 0.02),
                strategy=self._test_strategies[i % len(self._test_strategies)],
                symbol=self._test_symbols[i % len(self._test_symbols)],
                direction="long",
                is_winner=random.random() > 0.4,
            )
            calculator.add_trade(trade)

            op_start = time.perf_counter()
            metrics = calculator.get_risk_adjusted_metrics()
            op_end = time.perf_counter()

            latencies.append((op_end - op_start) * 1000)
            operations += 1
            i += 1

        actual_duration = time.perf_counter() - start_time
        throughput = operations / actual_duration

        return BenchmarkResult(
            test_name="risk_adjusted_metrics",
            duration_seconds=actual_duration,
            total_operations=operations,
            throughput_per_sec=throughput,
            target_throughput=self.target_risk_adjusted_throughput,
            latencies_ms=latencies,
            trades_count=trades_count,
        )

    def benchmark_attribution(
        self,
        duration_seconds: float = 10.0,
        trades_count: int = 500
    ) -> BenchmarkResult:
        """
        Benchmark attribution calculation.

        Args:
            duration_seconds: Test duration
            trades_count: Number of trades

        Returns:
            BenchmarkResult with throughput metrics
        """
        latencies = []
        operations = 0
        start_time = time.perf_counter()
        end_time = start_time + duration_seconds

        calculator = self._setup_calculator(trades_count)

        i = 0
        while time.perf_counter() < end_time:
            op_start = time.perf_counter()

            # Calculate both attributions
            by_strategy = calculator.get_attribution_by_strategy()
            by_symbol = calculator.get_attribution_by_symbol()

            op_end = time.perf_counter()

            latencies.append((op_end - op_start) * 1000)
            operations += 1
            i += 1

        actual_duration = time.perf_counter() - start_time
        throughput = operations / actual_duration

        return BenchmarkResult(
            test_name="attribution_calculation",
            duration_seconds=actual_duration,
            total_operations=operations,
            throughput_per_sec=throughput,
            target_throughput=self.target_attribution_throughput,
            latencies_ms=latencies,
            trades_count=trades_count,
        )

    def benchmark_trade_addition(
        self,
        duration_seconds: float = 10.0
    ) -> BenchmarkResult:
        """
        Benchmark trade addition performance.

        Args:
            duration_seconds: Test duration

        Returns:
            BenchmarkResult with throughput metrics
        """
        latencies = []
        operations = 0
        start_time = time.perf_counter()
        end_time = start_time + duration_seconds

        calculator = self._setup_calculator(100)

        i = 0
        while time.perf_counter() < end_time:
            trade = TradeMetadata(
                trade_id=f"realtime_trade_{i}",
                timestamp=datetime.now(timezone.utc),
                pnl=random.gauss(50, 200),
                pnl_pct=random.gauss(0.005, 0.02),
                strategy=self._test_strategies[i % len(self._test_strategies)],
                symbol=self._test_symbols[i % len(self._test_symbols)],
                direction="long" if i % 2 == 0 else "short",
                is_winner=random.random() > 0.4,
            )

            op_start = time.perf_counter()
            calculator.add_trade(trade)
            op_end = time.perf_counter()

            latencies.append((op_end - op_start) * 1000)
            operations += 1
            i += 1

        actual_duration = time.perf_counter() - start_time
        throughput = operations / actual_duration

        return BenchmarkResult(
            test_name="trade_addition",
            duration_seconds=actual_duration,
            total_operations=operations,
            throughput_per_sec=throughput,
            target_throughput=self.target_trade_addition_throughput,
            latencies_ms=latencies,
        )

    def benchmark_incremental_update(
        self,
        duration_seconds: float = 10.0,
        trades_count: int = 500
    ) -> BenchmarkResult:
        """
        Benchmark incremental metrics update (simulating real-time updates).

        Each iteration adds a trade and fetches updated metrics.

        Args:
            duration_seconds: Test duration
            trades_count: Initial trades in calculator

        Returns:
            BenchmarkResult with throughput metrics
        """
        latencies = []
        operations = 0
        start_time = time.perf_counter()
        end_time = start_time + duration_seconds

        calculator = self._setup_calculator(trades_count)

        i = 0
        while time.perf_counter() < end_time:
            trade = TradeMetadata(
                trade_id=f"update_trade_{i}",
                timestamp=datetime.now(timezone.utc),
                pnl=random.gauss(50, 200),
                pnl_pct=random.gauss(0.005, 0.02),
                strategy=self._test_strategies[i % len(self._test_strategies)],
                symbol=self._test_symbols[i % len(self._test_symbols)],
                direction="long",
                is_winner=random.random() > 0.4,
            )

            op_start = time.perf_counter()

            # Simulate real-time update cycle
            calculator.add_trade(trade)
            summary = calculator.get_summary_metrics()

            op_end = time.perf_counter()

            latencies.append((op_end - op_start) * 1000)
            operations += 1
            i += 1

        actual_duration = time.perf_counter() - start_time
        throughput = operations / actual_duration

        return BenchmarkResult(
            test_name="incremental_update",
            duration_seconds=actual_duration,
            total_operations=operations,
            throughput_per_sec=throughput,
            target_throughput=self.target_metrics_update_throughput,
            latencies_ms=latencies,
            trades_count=trades_count,
        )

    def run_all_benchmarks(
        self,
        duration_seconds: float = 10.0,
        trades_count: int = 500
    ) -> Dict[str, BenchmarkResult]:
        """
        Run all analytics benchmarks.

        Args:
            duration_seconds: Duration per test
            trades_count: Number of trades for tests

        Returns:
            Dictionary of benchmark results
        """
        logger.info(f"Running all analytics benchmarks ({duration_seconds}s each, {trades_count} trades)")

        results = {}

        logger.info("Benchmarking comprehensive metrics...")
        results["comprehensive_metrics"] = self.benchmark_comprehensive_metrics(
            duration_seconds, trades_count
        )

        logger.info("Benchmarking risk-adjusted metrics...")
        results["risk_adjusted_metrics"] = self.benchmark_risk_adjusted_metrics(
            duration_seconds, trades_count
        )

        logger.info("Benchmarking attribution...")
        results["attribution"] = self.benchmark_attribution(duration_seconds, trades_count)

        logger.info("Benchmarking trade addition...")
        results["trade_addition"] = self.benchmark_trade_addition(duration_seconds)

        logger.info("Benchmarking incremental update...")
        results["incremental_update"] = self.benchmark_incremental_update(
            duration_seconds, trades_count
        )

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
            "=" * 85,
            "ANALYTICS BENCHMARK REPORT",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            "=" * 85,
            "",
            f"{'Test':<30} {'Throughput':>15} {'Target':>12} {'p99 Latency':>12} {'Status':>10}",
            "-" * 85,
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
            "=" * 85,
            f"SUMMARY: {'ALL BENCHMARKS PASSED' if all_pass else 'SOME BENCHMARKS FAILED'}",
            "=" * 85,
        ])

        report = "\n".join(lines)
        print(report)
        return report


def run_analytics_benchmark(duration_seconds: float = 10.0) -> Dict[str, BenchmarkResult]:
    """
    Convenience function to run analytics benchmarks.

    Args:
        duration_seconds: Duration per test

    Returns:
        Dictionary of benchmark results
    """
    benchmark = AnalyticsBenchmark()
    results = benchmark.run_all_benchmarks(duration_seconds)
    benchmark.print_report(results)
    return results


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    results = run_analytics_benchmark(duration_seconds=10)

    all_pass = all(r.meets_target for r in results.values())
    exit(0 if all_pass else 1)
