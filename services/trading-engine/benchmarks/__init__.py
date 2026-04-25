"""
Benchmarks Module for Trading Engine Performance Testing

This module provides comprehensive benchmarking tools for:
- Execution performance (throughput and latency)
- Risk calculation throughput
- Analytics computation performance
- WebSocket message throughput

Usage:
    from benchmarks import (
        ExecutionBenchmark,
        RiskBenchmark,
        AnalyticsBenchmark,
        WebSocketBenchmark,
    )

    # Run all benchmarks
    from benchmarks import run_all_benchmarks
    results = run_all_benchmarks()

Author: Backend Developer Agent
Date: 2025-12-12
"""

from .benchmark_execution import ExecutionBenchmark, run_execution_benchmark
from .benchmark_risk import RiskBenchmark, run_risk_benchmark
from .benchmark_analytics import AnalyticsBenchmark, run_analytics_benchmark
from .benchmark_websocket import WebSocketBenchmark, run_websocket_benchmark

__all__ = [
    "ExecutionBenchmark",
    "run_execution_benchmark",
    "RiskBenchmark",
    "run_risk_benchmark",
    "AnalyticsBenchmark",
    "run_analytics_benchmark",
    "WebSocketBenchmark",
    "run_websocket_benchmark",
]


def run_all_benchmarks(duration_seconds: int = 10):
    """
    Run all benchmark suites and generate consolidated report.

    Args:
        duration_seconds: Duration for throughput tests

    Returns:
        Dictionary of all benchmark results
    """
    import logging
    logging.basicConfig(level=logging.INFO)

    results = {}

    print("=" * 80)
    print("RUNNING ALL BENCHMARKS")
    print("=" * 80)

    print("\n[1/4] Execution Benchmarks...")
    results["execution"] = run_execution_benchmark(duration_seconds)

    print("\n[2/4] Risk Calculation Benchmarks...")
    results["risk"] = run_risk_benchmark(duration_seconds)

    print("\n[3/4] Analytics Benchmarks...")
    results["analytics"] = run_analytics_benchmark(duration_seconds)

    print("\n[4/4] WebSocket Benchmarks...")
    results["websocket"] = run_websocket_benchmark(duration_seconds)

    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY")
    print("=" * 80)

    return results
