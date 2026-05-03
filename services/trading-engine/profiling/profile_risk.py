"""
Risk Calculation Profiling Module

Purpose:
- Profile risk budget calculations
- Measure dynamic budget adjustment performance
- Profile correlation calculations
- Measure Kelly criterion calculations

Target Latencies:
- Risk calculation: <20ms p99
- Budget check (can_place_order): <5ms p99
- Correlation matrix: <50ms for 20 assets
- Kelly calculation: <10ms p99

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

from app.risk.dynamic_budget import (
    DynamicBudgetManager,
    BudgetConfig,
    get_budget_manager,
    reset_budget_manager,
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
    target_ms: float = 20.0
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
            "hotspots": self.hotspots[:10],
        }


class RiskProfiler:
    """
    Comprehensive profiler for risk calculation components.

    Profiles:
    - Dynamic budget calculations and adjustments
    - Order validation (can_place_order)
    - Correlation matrix calculations
    - Kelly criterion calculations
    - Volatility multiplier calculations

    Usage:
        profiler = RiskProfiler()

        # Profile specific component
        result = profiler.profile_budget_calculation(iterations=100)

        # Run all profiles
        results = profiler.run_all_profiles()

        # Generate report
        report = profiler.generate_report(results)
    """

    def __init__(
        self,
        target_risk_calc_ms: float = 20.0,
        target_order_check_ms: float = 5.0,
        target_correlation_ms: float = 50.0,
        target_kelly_ms: float = 10.0,
    ):
        """
        Initialize risk profiler.

        Args:
            target_risk_calc_ms: Target p99 for risk calculations
            target_order_check_ms: Target p99 for order validation
            target_correlation_ms: Target p99 for correlation matrix
            target_kelly_ms: Target p99 for Kelly calculations
        """
        self.target_risk_calc_ms = target_risk_calc_ms
        self.target_order_check_ms = target_order_check_ms
        self.target_correlation_ms = target_correlation_ms
        self.target_kelly_ms = target_kelly_ms

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

        logger.info(
            f"RiskProfiler initialized: "
            f"targets={{risk={target_risk_calc_ms}ms, "
            f"order_check={target_order_check_ms}ms, "
            f"corr={target_correlation_ms}ms, "
            f"kelly={target_kelly_ms}ms}}"
        )

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
        for i, strategy in enumerate(self._test_strategies):
            manager.allocate_strategy_budget(strategy, 20.0)

        # Set some asset limits
        for symbol in self._test_symbols[:10]:
            manager.set_asset_limit(symbol, 2.0)

        # Add some positions
        positions = []
        for i in range(15):
            positions.append({
                "symbol": self._test_symbols[i % len(self._test_symbols)],
                "strategy": self._test_strategies[i % len(self._test_strategies)],
                "risk_amount": random.uniform(100, 500),
            })
        manager.update_positions(positions)

        # Add volatility data
        volatility_data = {}
        for symbol in self._test_symbols:
            volatility_data[symbol] = {
                "current_volatility": random.uniform(0.3, 0.8),
                "historical_avg": 0.5,
                "percentile_rank": random.uniform(20, 80),
            }
        manager.update_volatility(volatility_data)

        # Add correlation data
        manager.update_correlations({
            "avg_correlation": random.uniform(0.3, 0.6),
            "max_correlation": random.uniform(0.6, 0.9),
        })

        # Add attribution data
        attribution_data = {"by_strategy": {}}
        for strategy in self._test_strategies:
            attribution_data["by_strategy"][strategy] = {
                "trades_count": random.randint(20, 100),
                "sharpe_ratio": random.uniform(-0.5, 2.5),
                "total_pnl": random.uniform(-1000, 5000),
            }
        manager.update_attribution(attribution_data)

        # Add Kelly data
        kelly_data = {}
        for strategy in self._test_strategies:
            kelly_data[strategy] = {
                "fractional_kelly_pct": random.uniform(0, 10),
                "full_kelly_pct": random.uniform(0, 20),
            }
        manager.update_kelly_data(kelly_data)

        return manager

    def profile_budget_calculation(
        self,
        iterations: int = 100
    ) -> ProfileResult:
        """
        Profile effective budget calculation with all multipliers.

        Measures time to calculate budget with all adjustments applied.
        Target: <20ms p99

        Args:
            iterations: Number of iterations

        Returns:
            ProfileResult with latency statistics
        """
        latencies = []

        manager = self._setup_budget_manager()

        for i in range(iterations):
            strategy = self._test_strategies[i % len(self._test_strategies)]
            symbol = self._test_symbols[i % len(self._test_symbols)]

            start = time.perf_counter()

            # Profile full effective budget calculation
            result = manager.get_effective_budget(
                strategy_name=strategy,
                symbol=symbol
            )

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        return ProfileResult(
            function_name="get_effective_budget",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=self.target_risk_calc_ms,
        )

    def profile_order_validation(
        self,
        iterations: int = 500
    ) -> ProfileResult:
        """
        Profile order placement validation (can_place_order).

        This is called before every order, must be very fast.
        Target: <5ms p99

        Args:
            iterations: Number of iterations

        Returns:
            ProfileResult
        """
        latencies = []

        manager = self._setup_budget_manager()

        for i in range(iterations):
            strategy = self._test_strategies[i % len(self._test_strategies)]
            symbol = self._test_symbols[i % len(self._test_symbols)]
            risk_amount = random.uniform(50, 500)

            start = time.perf_counter()

            can_place, reason = manager.can_place_order(
                strategy_name=strategy,
                symbol=symbol,
                order_risk_amount=risk_amount,
            )

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        return ProfileResult(
            function_name="can_place_order",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=self.target_order_check_ms,
        )

    def profile_volatility_multiplier(
        self,
        iterations: int = 1000
    ) -> ProfileResult:
        """
        Profile volatility multiplier calculation.

        Simple calculation but called frequently.
        Target: <1ms p99

        Args:
            iterations: Number of iterations

        Returns:
            ProfileResult
        """
        latencies = []

        manager = self._setup_budget_manager()

        for i in range(iterations):
            volatility_data = {
                "current_volatility": random.uniform(0.2, 1.0),
                "historical_avg": 0.5,
                "percentile_rank": random.uniform(0, 100),
            }

            start = time.perf_counter()

            multiplier = manager.calculate_volatility_multiplier(volatility_data)

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        return ProfileResult(
            function_name="calculate_volatility_multiplier",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=1.0,
        )

    def profile_correlation_multiplier(
        self,
        iterations: int = 1000
    ) -> ProfileResult:
        """
        Profile correlation multiplier calculation.

        Target: <1ms p99

        Args:
            iterations: Number of iterations

        Returns:
            ProfileResult
        """
        latencies = []

        manager = self._setup_budget_manager()

        for i in range(iterations):
            # Update correlation data
            manager.update_correlations({
                "avg_correlation": random.uniform(0.1, 0.9),
                "max_correlation": random.uniform(0.5, 1.0),
            })

            start = time.perf_counter()

            multiplier = manager.calculate_correlation_multiplier()

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        return ProfileResult(
            function_name="calculate_correlation_multiplier",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=1.0,
        )

    def profile_performance_multiplier(
        self,
        iterations: int = 500
    ) -> ProfileResult:
        """
        Profile performance-based multiplier calculation.

        Target: <5ms p99

        Args:
            iterations: Number of iterations

        Returns:
            ProfileResult
        """
        latencies = []

        manager = self._setup_budget_manager()

        for i in range(iterations):
            strategy = self._test_strategies[i % len(self._test_strategies)]

            start = time.perf_counter()

            multiplier = manager.calculate_performance_multiplier(strategy)

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        return ProfileResult(
            function_name="calculate_performance_multiplier",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=5.0,
        )

    def profile_rebalance_calculation(
        self,
        iterations: int = 100
    ) -> ProfileResult:
        """
        Profile rebalance action calculation.

        Target: <20ms p99

        Args:
            iterations: Number of iterations

        Returns:
            ProfileResult
        """
        latencies = []

        for i in range(iterations):
            manager = self._setup_budget_manager()

            # Modify usage to create drift
            for strategy in self._test_strategies:
                manager._strategy_usage[strategy] = random.uniform(500, 2000)

            start = time.perf_counter()

            actions = manager.calculate_rebalance_actions()

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        return ProfileResult(
            function_name="calculate_rebalance_actions",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=20.0,
        )

    def profile_correlation_matrix(
        self,
        n_assets: int = 20,
        iterations: int = 50
    ) -> ProfileResult:
        """
        Profile correlation matrix calculation for n assets.

        This simulates the correlation calculation that would happen
        in the correlation manager.
        Target: <50ms p99 for 20 assets

        Args:
            n_assets: Number of assets
            iterations: Number of iterations

        Returns:
            ProfileResult
        """
        latencies = []

        # Generate sample returns data (252 days x n_assets)
        returns_data = np.random.randn(252, n_assets) * 0.02

        for i in range(iterations):
            # Add some variation
            noise = np.random.randn(252, n_assets) * 0.001
            data = returns_data + noise

            start = time.perf_counter()

            # Calculate correlation matrix
            corr_matrix = np.corrcoef(data.T)

            # Calculate additional statistics often needed
            mean_corr = np.mean(corr_matrix[np.triu_indices(n_assets, k=1)])
            max_corr = np.max(corr_matrix[np.triu_indices(n_assets, k=1)])
            min_corr = np.min(corr_matrix[np.triu_indices(n_assets, k=1)])

            # Eigenvalue decomposition (for diversification ratio)
            eigenvalues = np.linalg.eigvalsh(corr_matrix)

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        return ProfileResult(
            function_name=f"correlation_matrix_{n_assets}_assets",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=self.target_correlation_ms,
        )

    def profile_kelly_calculation(
        self,
        iterations: int = 500
    ) -> ProfileResult:
        """
        Profile Kelly criterion calculation.

        Target: <10ms p99

        Args:
            iterations: Number of iterations

        Returns:
            ProfileResult
        """
        latencies = []

        for i in range(iterations):
            # Generate sample trade results
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

            start = time.perf_counter()

            # Calculate Kelly fraction
            # K = W - (1-W)/R where W=win rate, R=win/loss ratio
            actual_win_rate = wins / n_trades if n_trades > 0 else 0
            actual_avg_win = sum(p for p in trade_pnls if p > 0) / wins if wins > 0 else 0
            actual_avg_loss = abs(sum(p for p in trade_pnls if p < 0)) / losses if losses > 0 else 1

            if actual_avg_loss > 0:
                win_loss_ratio = actual_avg_win / actual_avg_loss
                kelly_fraction = actual_win_rate - (1 - actual_win_rate) / win_loss_ratio
            else:
                kelly_fraction = 0

            # Apply fractional Kelly (typically 25-50%)
            fractional_kelly = kelly_fraction * 0.25

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        return ProfileResult(
            function_name="kelly_criterion_calculation",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=self.target_kelly_ms,
        )

    def profile_budget_state(
        self,
        iterations: int = 500
    ) -> ProfileResult:
        """
        Profile budget state retrieval.

        Called frequently for dashboard updates.
        Target: <5ms p99

        Args:
            iterations: Number of iterations

        Returns:
            ProfileResult
        """
        latencies = []

        manager = self._setup_budget_manager()

        for i in range(iterations):
            start = time.perf_counter()

            state = manager.get_budget_state()

            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        return ProfileResult(
            function_name="get_budget_state",
            iterations=iterations,
            latencies_ms=latencies,
            target_ms=5.0,
        )

    def run_all_profiles(
        self,
        iterations: int = 100
    ) -> Dict[str, ProfileResult]:
        """
        Run all risk profiling tests.

        Args:
            iterations: Number of iterations per test

        Returns:
            Dictionary of ProfileResult objects keyed by test name
        """
        logger.info(f"Running all risk profiles with {iterations} iterations")

        results = {}

        # Budget calculation
        logger.info("Profiling budget calculation...")
        results["budget_calculation"] = self.profile_budget_calculation(iterations)

        # Order validation
        logger.info("Profiling order validation...")
        results["order_validation"] = self.profile_order_validation(iterations * 5)

        # Volatility multiplier
        logger.info("Profiling volatility multiplier...")
        results["volatility_multiplier"] = self.profile_volatility_multiplier(iterations * 10)

        # Correlation multiplier
        logger.info("Profiling correlation multiplier...")
        results["correlation_multiplier"] = self.profile_correlation_multiplier(iterations * 10)

        # Performance multiplier
        logger.info("Profiling performance multiplier...")
        results["performance_multiplier"] = self.profile_performance_multiplier(iterations * 5)

        # Rebalance calculation
        logger.info("Profiling rebalance calculation...")
        results["rebalance_calculation"] = self.profile_rebalance_calculation(iterations)

        # Correlation matrix
        logger.info("Profiling correlation matrix (20 assets)...")
        results["correlation_matrix_20"] = self.profile_correlation_matrix(20, iterations // 2)

        # Kelly calculation
        logger.info("Profiling Kelly calculation...")
        results["kelly_calculation"] = self.profile_kelly_calculation(iterations * 5)

        # Budget state
        logger.info("Profiling budget state...")
        results["budget_state"] = self.profile_budget_state(iterations * 5)

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
            "RISK CALCULATION PROFILING REPORT",
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


def profile_risk_calculations(iterations: int = 100) -> Dict[str, ProfileResult]:
    """
    Convenience function to run risk profiling.

    Args:
        iterations: Number of iterations per test

    Returns:
        Dictionary of profiling results
    """
    profiler = RiskProfiler()
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
    results = profile_risk_calculations(iterations=100)

    # Check targets
    all_pass = all(r.meets_target for r in results.values())
    exit(0 if all_pass else 1)
