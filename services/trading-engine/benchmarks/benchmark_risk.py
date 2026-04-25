"""
Risk Calculation Benchmark

Measures:
- Budget calculation throughput
- Order validation throughput (can_place_order)
- Correlation matrix calculation throughput
- Kelly criterion throughput

Targets:
- Budget calculation: >500 calcs/sec
- Order validation: >2000 validations/sec
- Correlation matrix (20 assets): >100 calcs/sec
- Kelly calculation: >1000 calcs/sec

Author: Backend Developer Agent
Date: 2025-12-12
"""

import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

import sys
sys.path.insert(0, "/mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine")

from app.risk.dynamic_budget import (
    DynamicBudgetManager,
    BudgetConfig,
    reset_budget_manager,
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
    """
    test_name: str
    duration_seconds: float
    total_operations: int
    throughput_per_sec: float
    target_throughput: float
    meets_target: bool = False
    latency_p50_ms: float = 0.0
    latency_p99_ms: float = 0.0
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
        }


class RiskBenchmark:
    """
    Benchmark suite for risk calculation module.

    Tests throughput and latency of:
    - Effective budget calculation
    - Order validation (can_place_order)
    - Multiplier calculations
    - Correlation matrix computation

    Usage:
        benchmark = RiskBenchmark()
        results = benchmark.run_all_benchmarks(duration_seconds=10)
        benchmark.print_report(results)
    """

    def __init__(
        self,
        target_budget_throughput: float = 500.0,
        target_validation_throughput: float = 2000.0,
        target_multiplier_throughput: float = 10000.0,
        target_correlation_throughput: float = 100.0,
        target_kelly_throughput: float = 1000.0,
    ):
        """
        Initialize risk benchmark.

        Args:
            target_budget_throughput: Target budget calcs/sec
            target_validation_throughput: Target validations/sec
            target_multiplier_throughput: Target multiplier calcs/sec
            target_correlation_throughput: Target correlation matrix calcs/sec
            target_kelly_throughput: Target Kelly calcs/sec
        """
        self.target_budget_throughput = target_budget_throughput
        self.target_validation_throughput = target_validation_throughput
        self.target_multiplier_throughput = target_multiplier_throughput
        self.target_correlation_throughput = target_correlation_throughput
        self.target_kelly_throughput = target_kelly_throughput

        # Test data
        self._test_symbols = [
            "BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOTUSDT",
            "LINKUSDT", "MATICUSDT", "ATOMUSDT", "NEARUSDT", "FTMUSDT",
            "ARBUSDT", "OPUSDT", "APTUSDT", "SUIUSDT", "INJUSDT",
            "TIAUSDT", "SEIUSDT", "AAVEUSDT", "MKRUSDT", "UNIUSDT",
        ]

        self._test_strategies = [
            "momentum", "mean_reversion", "pairs_trading",
            "trend_following", "stat_arb",
        ]

        logger.info("RiskBenchmark initialized")

    def _setup_budget_manager(self) -> DynamicBudgetManager:
        """Create and configure a budget manager for testing"""
        reset_budget_manager()

        config = BudgetConfig(
            total_capital=100000.0,
            max_total_risk_pct=10.0,
            max_strategy_risk_pct=5.0,
            max_asset_risk_pct=3.0,
            volatility_adjustment_enabled=True,
            correlation_adjustment_enabled=True,
            performance_adjustment_enabled=True,
            kelly_integration_enabled=True,
        )

        manager = DynamicBudgetManager(config=config)

        # Allocate budgets
        for strategy in self._test_strategies:
            manager.allocate_strategy_budget(strategy, 20.0)

        # Set asset limits
        for symbol in self._test_symbols[:10]:
            manager.set_asset_limit(symbol, 2.0)

        # Add positions
        positions = []
        for i in range(15):
            positions.append({
                "symbol": self._test_symbols[i % len(self._test_symbols)],
                "strategy": self._test_strategies[i % len(self._test_strategies)],
                "risk_amount": random.uniform(100, 500),
            })
        manager.update_positions(positions)

        # Add market data
        volatility_data = {}
        for symbol in self._test_symbols:
            volatility_data[symbol] = {
                "current_volatility": random.uniform(0.3, 0.8),
                "historical_avg": 0.5,
                "percentile_rank": random.uniform(20, 80),
            }
        manager.update_volatility(volatility_data)

        manager.update_correlations({
            "avg_correlation": random.uniform(0.3, 0.6),
            "max_correlation": random.uniform(0.6, 0.9),
        })

        attribution_data = {"by_strategy": {}}
        for strategy in self._test_strategies:
            attribution_data["by_strategy"][strategy] = {
                "trades_count": random.randint(20, 100),
                "sharpe_ratio": random.uniform(-0.5, 2.5),
            }
        manager.update_attribution(attribution_data)

        kelly_data = {}
        for strategy in self._test_strategies:
            kelly_data[strategy] = {
                "fractional_kelly_pct": random.uniform(0, 10),
            }
        manager.update_kelly_data(kelly_data)

        return manager

    def benchmark_budget_calculation(
        self,
        duration_seconds: float = 10.0
    ) -> BenchmarkResult:
        """
        Benchmark effective budget calculation.

        Args:
            duration_seconds: Test duration

        Returns:
            BenchmarkResult with throughput metrics
        """
        latencies = []
        operations = 0
        start_time = time.perf_counter()
        end_time = start_time + duration_seconds

        manager = self._setup_budget_manager()

        i = 0
        while time.perf_counter() < end_time:
            strategy = self._test_strategies[i % len(self._test_strategies)]
            symbol = self._test_symbols[i % len(self._test_symbols)]

            op_start = time.perf_counter()
            result = manager.get_effective_budget(strategy_name=strategy, symbol=symbol)
            op_end = time.perf_counter()

            latencies.append((op_end - op_start) * 1000)
            operations += 1
            i += 1

        actual_duration = time.perf_counter() - start_time
        throughput = operations / actual_duration

        return BenchmarkResult(
            test_name="budget_calculation",
            duration_seconds=actual_duration,
            total_operations=operations,
            throughput_per_sec=throughput,
            target_throughput=self.target_budget_throughput,
            latencies_ms=latencies,
        )

    def benchmark_order_validation(
        self,
        duration_seconds: float = 10.0
    ) -> BenchmarkResult:
        """
        Benchmark order validation (can_place_order).

        Args:
            duration_seconds: Test duration

        Returns:
            BenchmarkResult with throughput metrics
        """
        latencies = []
        operations = 0
        start_time = time.perf_counter()
        end_time = start_time + duration_seconds

        manager = self._setup_budget_manager()

        i = 0
        while time.perf_counter() < end_time:
            strategy = self._test_strategies[i % len(self._test_strategies)]
            symbol = self._test_symbols[i % len(self._test_symbols)]
            risk_amount = random.uniform(50, 500)

            op_start = time.perf_counter()
            can_place, reason = manager.can_place_order(
                strategy_name=strategy,
                symbol=symbol,
                order_risk_amount=risk_amount,
            )
            op_end = time.perf_counter()

            latencies.append((op_end - op_start) * 1000)
            operations += 1
            i += 1

        actual_duration = time.perf_counter() - start_time
        throughput = operations / actual_duration

        return BenchmarkResult(
            test_name="order_validation",
            duration_seconds=actual_duration,
            total_operations=operations,
            throughput_per_sec=throughput,
            target_throughput=self.target_validation_throughput,
            latencies_ms=latencies,
        )

    def benchmark_multiplier_calculation(
        self,
        duration_seconds: float = 10.0
    ) -> BenchmarkResult:
        """
        Benchmark multiplier calculations (volatility, correlation, performance).

        Args:
            duration_seconds: Test duration

        Returns:
            BenchmarkResult with throughput metrics
        """
        latencies = []
        operations = 0
        start_time = time.perf_counter()
        end_time = start_time + duration_seconds

        manager = self._setup_budget_manager()

        i = 0
        while time.perf_counter() < end_time:
            volatility_data = {
                "current_volatility": random.uniform(0.2, 1.0),
                "historical_avg": 0.5,
                "percentile_rank": random.uniform(0, 100),
            }
            strategy = self._test_strategies[i % len(self._test_strategies)]

            op_start = time.perf_counter()
            vol_mult = manager.calculate_volatility_multiplier(volatility_data)
            corr_mult = manager.calculate_correlation_multiplier()
            perf_mult = manager.calculate_performance_multiplier(strategy)
            op_end = time.perf_counter()

            latencies.append((op_end - op_start) * 1000)
            operations += 1
            i += 1

        actual_duration = time.perf_counter() - start_time
        throughput = operations / actual_duration

        return BenchmarkResult(
            test_name="multiplier_calculation",
            duration_seconds=actual_duration,
            total_operations=operations,
            throughput_per_sec=throughput,
            target_throughput=self.target_multiplier_throughput,
            latencies_ms=latencies,
        )

    def benchmark_correlation_matrix(
        self,
        duration_seconds: float = 10.0,
        n_assets: int = 20
    ) -> BenchmarkResult:
        """
        Benchmark correlation matrix calculation.

        Args:
            duration_seconds: Test duration
            n_assets: Number of assets

        Returns:
            BenchmarkResult with throughput metrics
        """
        latencies = []
        operations = 0
        start_time = time.perf_counter()
        end_time = start_time + duration_seconds

        # Pre-generate base returns
        base_returns = np.random.randn(252, n_assets) * 0.02

        while time.perf_counter() < end_time:
            # Add noise
            noise = np.random.randn(252, n_assets) * 0.001
            data = base_returns + noise

            op_start = time.perf_counter()

            # Full correlation computation
            corr_matrix = np.corrcoef(data.T)
            mean_corr = np.mean(corr_matrix[np.triu_indices(n_assets, k=1)])
            max_corr = np.max(corr_matrix[np.triu_indices(n_assets, k=1)])
            eigenvalues = np.linalg.eigvalsh(corr_matrix)

            op_end = time.perf_counter()

            latencies.append((op_end - op_start) * 1000)
            operations += 1

        actual_duration = time.perf_counter() - start_time
        throughput = operations / actual_duration

        return BenchmarkResult(
            test_name=f"correlation_matrix_{n_assets}_assets",
            duration_seconds=actual_duration,
            total_operations=operations,
            throughput_per_sec=throughput,
            target_throughput=self.target_correlation_throughput,
            latencies_ms=latencies,
        )

    def benchmark_kelly_calculation(
        self,
        duration_seconds: float = 10.0
    ) -> BenchmarkResult:
        """
        Benchmark Kelly criterion calculation.

        Args:
            duration_seconds: Test duration

        Returns:
            BenchmarkResult with throughput metrics
        """
        latencies = []
        operations = 0
        start_time = time.perf_counter()
        end_time = start_time + duration_seconds

        while time.perf_counter() < end_time:
            n_trades = random.randint(30, 100)
            win_rate = random.uniform(0.4, 0.7)
            avg_win = random.uniform(50, 200)
            avg_loss = random.uniform(30, 150)

            wins = int(n_trades * win_rate)
            losses = n_trades - wins

            trade_pnls = (
                [avg_win * random.uniform(0.8, 1.2) for _ in range(wins)] +
                [-avg_loss * random.uniform(0.8, 1.2) for _ in range(losses)]
            )

            op_start = time.perf_counter()

            # Kelly calculation
            actual_win_rate = wins / n_trades if n_trades > 0 else 0
            actual_avg_win = sum(p for p in trade_pnls if p > 0) / wins if wins > 0 else 0
            actual_avg_loss = abs(sum(p for p in trade_pnls if p < 0)) / losses if losses > 0 else 1

            if actual_avg_loss > 0:
                win_loss_ratio = actual_avg_win / actual_avg_loss
                kelly_fraction = actual_win_rate - (1 - actual_win_rate) / win_loss_ratio
            else:
                kelly_fraction = 0

            fractional_kelly = kelly_fraction * 0.25

            op_end = time.perf_counter()

            latencies.append((op_end - op_start) * 1000)
            operations += 1

        actual_duration = time.perf_counter() - start_time
        throughput = operations / actual_duration

        return BenchmarkResult(
            test_name="kelly_calculation",
            duration_seconds=actual_duration,
            total_operations=operations,
            throughput_per_sec=throughput,
            target_throughput=self.target_kelly_throughput,
            latencies_ms=latencies,
        )

    def run_all_benchmarks(
        self,
        duration_seconds: float = 10.0
    ) -> Dict[str, BenchmarkResult]:
        """
        Run all risk benchmarks.

        Args:
            duration_seconds: Duration per test

        Returns:
            Dictionary of benchmark results
        """
        logger.info(f"Running all risk benchmarks ({duration_seconds}s each)")

        results = {}

        logger.info("Benchmarking budget calculation...")
        results["budget_calculation"] = self.benchmark_budget_calculation(duration_seconds)

        logger.info("Benchmarking order validation...")
        results["order_validation"] = self.benchmark_order_validation(duration_seconds)

        logger.info("Benchmarking multiplier calculation...")
        results["multiplier_calculation"] = self.benchmark_multiplier_calculation(duration_seconds)

        logger.info("Benchmarking correlation matrix...")
        results["correlation_matrix"] = self.benchmark_correlation_matrix(duration_seconds)

        logger.info("Benchmarking Kelly calculation...")
        results["kelly_calculation"] = self.benchmark_kelly_calculation(duration_seconds)

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
            "RISK CALCULATION BENCHMARK REPORT",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            "=" * 80,
            "",
            f"{'Test':<35} {'Throughput':>15} {'Target':>12} {'p99 Latency':>12} {'Status':>10}",
            "-" * 85,
        ]

        all_pass = True
        for name, result in results.items():
            status = "PASS" if result.meets_target else "FAIL"
            if not result.meets_target:
                all_pass = False

            lines.append(
                f"{name:<35} {result.throughput_per_sec:>12.1f}/s "
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


def run_risk_benchmark(duration_seconds: float = 10.0) -> Dict[str, BenchmarkResult]:
    """
    Convenience function to run risk benchmarks.

    Args:
        duration_seconds: Duration per test

    Returns:
        Dictionary of benchmark results
    """
    benchmark = RiskBenchmark()
    results = benchmark.run_all_benchmarks(duration_seconds)
    benchmark.print_report(results)
    return results


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    results = run_risk_benchmark(duration_seconds=10)

    all_pass = all(r.meets_target for r in results.values())
    exit(0 if all_pass else 1)
