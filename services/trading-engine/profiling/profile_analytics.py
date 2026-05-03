"""
Analytics/Metrics Calculation Profiling Module

Purpose:
- Profile advanced metrics calculation
- Measure risk-adjusted metrics performance
- Profile drawdown analysis
- Measure attribution calculations
- Profile rolling metrics computation

Target Latencies:
- Comprehensive metrics: <100ms p99
- Risk-adjusted metrics: <30ms p99
- Drawdown analysis: <20ms p99
- Attribution by dimension: <15ms p99
- Rolling metrics: <50ms p99

Author: Backend Developer Agent
Date: 2025-12-12
"""

import cProfile
import io
import logging
import pstats
import random
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))

from app.analytics.advanced_metrics import (
    AdvancedMetricsCalculator,
    TradeMetadata,
    get_advanced_metrics_calculator,
    reset_advanced_metrics_calculator,
    MetricsPeriod,
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
        trades_count: Number of trades in test data
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
    target_ms: float = 100.0
    hotspots: List[Tuple[str, float]] = field(default_factory=list)
    trades_count: int = 0

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
            "trades_count": self.trades_count,
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
            "hotspots": self.hotspots[:10],
        }


class AnalyticsProfiler:
    """
    Comprehensive profiler for analytics/metrics components.

    Profiles:
    - Comprehensive metrics calculation
    - Risk-adjusted metrics (Sharpe, Sortino, etc.)
    - Risk metrics (VaR, CVaR, etc.)
    - Statistical metrics
    - Drawdown analysis
    - Attribution analysis
    - Rolling metrics calculation

    Usage:
        profiler = AnalyticsProfiler()

        # Profile specific component
        result = profiler.profile_comprehensive_metrics(iterations=100)

        # Run all profiles
        results = profiler.run_all_profiles()

        # Generate report
        report = profiler.generate_report(results)
    """

    def __init__(
        self,
        target_comprehensive_ms: float = 100.0,
        target_risk_adjusted_ms: float = 30.0,
        target_risk_metrics_ms: float = 25.0,
        target_statistical_ms: float = 20.0,
        target_drawdown_ms: float = 20.0,
        target_attribution_ms: float = 15.0,
        target_rolling_ms: float = 50.0,
    ):
        """
        Initialize analytics profiler.

        Args:
            target_comprehensive_ms: Target p99 for comprehensive metrics
            target_risk_adjusted_ms: Target p99 for risk-adjusted metrics
            target_risk_metrics_ms: Target p99 for risk metrics
            target_statistical_ms: Target p99 for statistical metrics
            target_drawdown_ms: Target p99 for drawdown analysis
            target_attribution_ms: Target p99 for attribution analysis
            target_rolling_ms: Target p99 for rolling metrics
        """
        self.target_comprehensive_ms = target_comprehensive_ms
        self.target_risk_adjusted_ms = target_risk_adjusted_ms
        self.target_risk_metrics_ms = target_risk_metrics_ms
        self.target_statistical_ms = target_statistical_ms
        self.target_drawdown_ms = target_drawdown_ms
        self.target_attribution_ms = target_attribution_ms
        self.target_rolling_ms = target_rolling_ms

        # Test data
        self._test_symbols = [
            "BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOTUSDT",
            "LINKUSDT", "MATICUSDT", "ATOMUSDT", "NEARUSDT", "FTMUSDT",
        ]

        self._test_strategies = [
            "momentum", "mean_reversion", "pairs_trading",
            "trend_following", "stat_arb",
        ]

        logger.info(
            f"AnalyticsProfiler initialized: "
            f"targets={{comp={target_comprehensive_ms}ms, "
            f"risk_adj={target_risk_adjusted_ms}ms, "
            f"drawdown={target_drawdown_ms}ms}}"
        )

    def _generate_trades(self, n_trades: int) -> List[TradeMetadata]:
        """
        Generate synthetic trade data for testing.

        Args:
            n_trades: Number of trades to generate

        Returns:
            List of TradeMetadata objects
        """
        trades = []
        base_time = datetime.now(timezone.utc) - timedelta(days=90)

        for i in range(n_trades):
            # Randomize trade characteristics
            pnl = random.gauss(50, 200)  # Mean $50, std $200
            is_winner = pnl > 0

            # Generate return percentage
            base_capital = 10000
            pnl_pct = pnl / base_capital

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
        """
        Create and populate a metrics calculator for testing.

        Args:
            n_trades: Number of trades to add

        Returns:
            Configured AdvancedMetricsCalculator
        """
        reset_advanced_metrics_calculator()

        calculator = AdvancedMetricsCalculator(
            initial_capital=10000.0,
            risk_free_rate=0.02,
            rolling_window=30,
        )

        # Generate and add trades
        trades = self._generate_trades(n_trades)
        calculator.add_trades_batch(trades)

        # Set benchmark returns
        benchmark_returns = [random.gauss(0.0005, 0.02) for _ in range(n_trades)]
        calculator.set_benchmark_returns(benchmark_returns)

        return calculator

    def profile_comprehensive_metrics(
        self,
        iterations: int = 50,
        trades_per_calc: int = 500
    ) -> ProfileResult:
        """
        Profile comprehensive metrics calculation.

        This is the main metrics endpoint, includes all calculations.
        Target: <100ms p99

        Args:
            iterations: Number of iterations
            trades_per_calc: Number of trades in calculator

        Returns:
            ProfileResult with latency statistics
        """
        latencies = []

        for i in range(iterations):
            calculator = self._setup_calculator(trades_per_calc)

            start = time.perf_counter()

            # Force recalculation each time
            metrics = calculator.get_comprehensive_metrics(force_recalculate=True)

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        result = ProfileResult(
            function_name="get_comprehensive_metrics",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=self.target_comprehensive_ms,
            trades_count=trades_per_calc,
        )
        return result

    def profile_risk_adjusted_metrics(
        self,
        iterations: int = 100,
        trades_per_calc: int = 500
    ) -> ProfileResult:
        """
        Profile risk-adjusted metrics calculation (Sharpe, Sortino, etc.).

        Target: <30ms p99

        Args:
            iterations: Number of iterations
            trades_per_calc: Number of trades

        Returns:
            ProfileResult
        """
        latencies = []

        calculator = self._setup_calculator(trades_per_calc)

        for i in range(iterations):
            # Add a new trade to invalidate cache
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

            start = time.perf_counter()

            metrics = calculator.get_risk_adjusted_metrics()

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        return ProfileResult(
            function_name="get_risk_adjusted_metrics",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=self.target_risk_adjusted_ms,
            trades_count=trades_per_calc,
        )

    def profile_risk_metrics(
        self,
        iterations: int = 100,
        trades_per_calc: int = 500
    ) -> ProfileResult:
        """
        Profile risk metrics calculation (VaR, CVaR, Beta, etc.).

        Target: <25ms p99

        Args:
            iterations: Number of iterations
            trades_per_calc: Number of trades

        Returns:
            ProfileResult
        """
        latencies = []

        calculator = self._setup_calculator(trades_per_calc)

        for i in range(iterations):
            start = time.perf_counter()

            metrics = calculator.get_risk_metrics()

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        return ProfileResult(
            function_name="get_risk_metrics",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=self.target_risk_metrics_ms,
            trades_count=trades_per_calc,
        )

    def profile_statistical_metrics(
        self,
        iterations: int = 100,
        trades_per_calc: int = 500
    ) -> ProfileResult:
        """
        Profile statistical metrics calculation.

        Target: <20ms p99

        Args:
            iterations: Number of iterations
            trades_per_calc: Number of trades

        Returns:
            ProfileResult
        """
        latencies = []

        calculator = self._setup_calculator(trades_per_calc)

        for i in range(iterations):
            start = time.perf_counter()

            metrics = calculator.get_statistical_metrics()

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        return ProfileResult(
            function_name="get_statistical_metrics",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=self.target_statistical_ms,
            trades_count=trades_per_calc,
        )

    def profile_drawdown_analysis(
        self,
        iterations: int = 100,
        trades_per_calc: int = 500
    ) -> ProfileResult:
        """
        Profile drawdown analysis calculation.

        Target: <20ms p99

        Args:
            iterations: Number of iterations
            trades_per_calc: Number of trades

        Returns:
            ProfileResult
        """
        latencies = []

        calculator = self._setup_calculator(trades_per_calc)

        for i in range(iterations):
            start = time.perf_counter()

            analysis = calculator.get_drawdown_analysis()

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        return ProfileResult(
            function_name="get_drawdown_analysis",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=self.target_drawdown_ms,
            trades_count=trades_per_calc,
        )

    def profile_attribution_by_strategy(
        self,
        iterations: int = 100,
        trades_per_calc: int = 500
    ) -> ProfileResult:
        """
        Profile attribution by strategy calculation.

        Target: <15ms p99

        Args:
            iterations: Number of iterations
            trades_per_calc: Number of trades

        Returns:
            ProfileResult
        """
        latencies = []

        calculator = self._setup_calculator(trades_per_calc)

        for i in range(iterations):
            start = time.perf_counter()

            attribution = calculator.get_attribution_by_strategy()

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        return ProfileResult(
            function_name="get_attribution_by_strategy",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=self.target_attribution_ms,
            trades_count=trades_per_calc,
        )

    def profile_attribution_by_symbol(
        self,
        iterations: int = 100,
        trades_per_calc: int = 500
    ) -> ProfileResult:
        """
        Profile attribution by symbol calculation.

        Target: <15ms p99

        Args:
            iterations: Number of iterations
            trades_per_calc: Number of trades

        Returns:
            ProfileResult
        """
        latencies = []

        calculator = self._setup_calculator(trades_per_calc)

        for i in range(iterations):
            start = time.perf_counter()

            attribution = calculator.get_attribution_by_symbol()

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        return ProfileResult(
            function_name="get_attribution_by_symbol",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=self.target_attribution_ms,
            trades_count=trades_per_calc,
        )

    def profile_rolling_metrics(
        self,
        iterations: int = 50,
        trades_per_calc: int = 500,
        window_size: int = 30
    ) -> ProfileResult:
        """
        Profile rolling metrics calculation.

        Target: <50ms p99

        Args:
            iterations: Number of iterations
            trades_per_calc: Number of trades
            window_size: Rolling window size

        Returns:
            ProfileResult
        """
        latencies = []

        calculator = self._setup_calculator(trades_per_calc)

        for i in range(iterations):
            start = time.perf_counter()

            rolling = calculator.get_rolling_metrics(
                window_size=window_size,
                period=MetricsPeriod.DAILY,
            )

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        return ProfileResult(
            function_name=f"get_rolling_metrics_window_{window_size}",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=self.target_rolling_ms,
            trades_count=trades_per_calc,
        )

    def profile_trade_addition(
        self,
        iterations: int = 1000
    ) -> ProfileResult:
        """
        Profile trade addition performance.

        This happens in real-time, must be very fast.
        Target: <5ms p99

        Args:
            iterations: Number of iterations

        Returns:
            ProfileResult
        """
        latencies = []

        calculator = self._setup_calculator(100)  # Start with some trades

        for i in range(iterations):
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

            start = time.perf_counter()

            calculator.add_trade(trade)

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        return ProfileResult(
            function_name="add_trade",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=5.0,
        )

    def profile_sharpe_calculation(
        self,
        iterations: int = 500
    ) -> ProfileResult:
        """
        Profile isolated Sharpe ratio calculation.

        Target: <5ms p99

        Args:
            iterations: Number of iterations

        Returns:
            ProfileResult
        """
        latencies = []

        # Generate test returns
        n_returns = 252
        base_returns = np.random.randn(n_returns) * 0.02

        calculator = AdvancedMetricsCalculator()

        for i in range(iterations):
            # Vary returns slightly
            returns = base_returns + np.random.randn(n_returns) * 0.001

            start = time.perf_counter()

            sharpe = calculator._calculate_sharpe_ratio(returns)

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        return ProfileResult(
            function_name="_calculate_sharpe_ratio",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=5.0,
        )

    def profile_var_calculation(
        self,
        iterations: int = 500
    ) -> ProfileResult:
        """
        Profile VaR calculation.

        Target: <5ms p99

        Args:
            iterations: Number of iterations

        Returns:
            ProfileResult
        """
        latencies = []

        n_returns = 252
        base_returns = np.random.randn(n_returns) * 0.02

        calculator = AdvancedMetricsCalculator()

        for i in range(iterations):
            returns = base_returns + np.random.randn(n_returns) * 0.001

            start = time.perf_counter()

            var_95 = calculator._calculate_var(returns, confidence=0.95)
            var_99 = calculator._calculate_var(returns, confidence=0.99)

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        return ProfileResult(
            function_name="_calculate_var",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=5.0,
        )

    def run_all_profiles(
        self,
        iterations: int = 50,
        trades_per_calc: int = 500
    ) -> Dict[str, ProfileResult]:
        """
        Run all analytics profiling tests.

        Args:
            iterations: Number of iterations per test
            trades_per_calc: Number of trades in calculator

        Returns:
            Dictionary of ProfileResult objects keyed by test name
        """
        logger.info(
            f"Running all analytics profiles with {iterations} iterations, "
            f"{trades_per_calc} trades per calculation"
        )

        results = {}

        # Comprehensive metrics
        logger.info("Profiling comprehensive metrics...")
        results["comprehensive_metrics"] = self.profile_comprehensive_metrics(
            iterations, trades_per_calc
        )

        # Risk-adjusted metrics
        logger.info("Profiling risk-adjusted metrics...")
        results["risk_adjusted_metrics"] = self.profile_risk_adjusted_metrics(
            iterations * 2, trades_per_calc
        )

        # Risk metrics
        logger.info("Profiling risk metrics...")
        results["risk_metrics"] = self.profile_risk_metrics(
            iterations * 2, trades_per_calc
        )

        # Statistical metrics
        logger.info("Profiling statistical metrics...")
        results["statistical_metrics"] = self.profile_statistical_metrics(
            iterations * 2, trades_per_calc
        )

        # Drawdown analysis
        logger.info("Profiling drawdown analysis...")
        results["drawdown_analysis"] = self.profile_drawdown_analysis(
            iterations * 2, trades_per_calc
        )

        # Attribution by strategy
        logger.info("Profiling attribution by strategy...")
        results["attribution_strategy"] = self.profile_attribution_by_strategy(
            iterations * 2, trades_per_calc
        )

        # Attribution by symbol
        logger.info("Profiling attribution by symbol...")
        results["attribution_symbol"] = self.profile_attribution_by_symbol(
            iterations * 2, trades_per_calc
        )

        # Rolling metrics
        logger.info("Profiling rolling metrics...")
        results["rolling_metrics"] = self.profile_rolling_metrics(
            iterations, trades_per_calc
        )

        # Trade addition
        logger.info("Profiling trade addition...")
        results["trade_addition"] = self.profile_trade_addition(iterations * 20)

        # Sharpe calculation
        logger.info("Profiling Sharpe calculation...")
        results["sharpe_calculation"] = self.profile_sharpe_calculation(iterations * 10)

        # VaR calculation
        logger.info("Profiling VaR calculation...")
        results["var_calculation"] = self.profile_var_calculation(iterations * 10)

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
            "ANALYTICS/METRICS PROFILING REPORT",
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
                f"  Trades: {result.trades_count}",
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
                "-" * 40,
                "",
            ])

        # Summary
        lines.extend([
            "=" * 80,
            f"SUMMARY: {'ALL TESTS PASSED' if all_pass else 'SOME TESTS FAILED'}",
            "=" * 80,
        ])

        return "\n".join(lines)


def profile_metrics_calculation(
    iterations: int = 50,
    trades: int = 500
) -> Dict[str, ProfileResult]:
    """
    Convenience function to run analytics profiling.

    Args:
        iterations: Number of iterations per test
        trades: Number of trades per calculation

    Returns:
        Dictionary of profiling results
    """
    profiler = AnalyticsProfiler()
    results = profiler.run_all_profiles(iterations, trades)

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
    results = profile_metrics_calculation(iterations=50, trades=500)

    # Check targets
    all_pass = all(r.meets_target for r in results.values())
    exit(0 if all_pass else 1)
