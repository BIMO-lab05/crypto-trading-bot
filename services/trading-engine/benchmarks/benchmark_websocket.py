"""
WebSocket Performance Benchmark

Measures:
- Message serialization throughput
- Broadcast simulation throughput
- Update batching performance
- Connection handling capacity

Targets:
- Message serialization: >10000 msgs/sec
- Broadcast simulation: >5000 broadcasts/sec
- Batched updates: >1000 batches/sec

Author: Backend Developer Agent
Date: 2025-12-12
"""

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import sys
sys.path.insert(0, "/mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine")

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
        connections_simulated: Number of connections simulated
    """
    test_name: str
    duration_seconds: float
    total_operations: int
    throughput_per_sec: float
    target_throughput: float
    meets_target: bool = False
    latency_p50_ms: float = 0.0
    latency_p99_ms: float = 0.0
    connections_simulated: int = 0
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
            "connections_simulated": self.connections_simulated,
        }


class SimulatedWebSocketConnection:
    """Simulated WebSocket connection for benchmarking"""

    def __init__(self, connection_id: str):
        self.connection_id = connection_id
        self.messages_received = 0
        self.subscriptions: Set[str] = set()
        self._buffer: List[str] = []

    async def send(self, message: str) -> None:
        """Simulate sending a message"""
        self._buffer.append(message)
        self.messages_received += 1
        # Simulate minimal I/O delay
        await asyncio.sleep(0)

    def subscribe(self, channel: str) -> None:
        """Subscribe to a channel"""
        self.subscriptions.add(channel)

    def unsubscribe(self, channel: str) -> None:
        """Unsubscribe from a channel"""
        self.subscriptions.discard(channel)


class SimulatedConnectionManager:
    """Simulated WebSocket connection manager for benchmarking"""

    def __init__(self):
        self.connections: Dict[str, SimulatedWebSocketConnection] = {}
        self.channel_subscriptions: Dict[str, Set[str]] = {}

    def add_connection(self, connection_id: str) -> SimulatedWebSocketConnection:
        """Add a new connection"""
        conn = SimulatedWebSocketConnection(connection_id)
        self.connections[connection_id] = conn
        return conn

    def remove_connection(self, connection_id: str) -> None:
        """Remove a connection"""
        if connection_id in self.connections:
            # Clean up subscriptions
            conn = self.connections[connection_id]
            for channel in conn.subscriptions:
                if channel in self.channel_subscriptions:
                    self.channel_subscriptions[channel].discard(connection_id)
            del self.connections[connection_id]

    def subscribe_to_channel(self, connection_id: str, channel: str) -> None:
        """Subscribe a connection to a channel"""
        if connection_id in self.connections:
            self.connections[connection_id].subscribe(channel)
            if channel not in self.channel_subscriptions:
                self.channel_subscriptions[channel] = set()
            self.channel_subscriptions[channel].add(connection_id)

    async def broadcast_to_channel(self, channel: str, message: str) -> int:
        """Broadcast message to all connections subscribed to channel"""
        if channel not in self.channel_subscriptions:
            return 0

        count = 0
        for conn_id in self.channel_subscriptions[channel]:
            if conn_id in self.connections:
                await self.connections[conn_id].send(message)
                count += 1

        return count

    async def broadcast_to_all(self, message: str) -> int:
        """Broadcast message to all connections"""
        count = 0
        for conn in self.connections.values():
            await conn.send(message)
            count += 1
        return count


class WebSocketBenchmark:
    """
    Benchmark suite for WebSocket-related performance.

    Tests throughput and latency of:
    - Message serialization (JSON encoding)
    - Broadcast to multiple connections
    - Update batching
    - Connection management

    Usage:
        benchmark = WebSocketBenchmark()
        results = benchmark.run_all_benchmarks(duration_seconds=10)
        benchmark.print_report(results)
    """

    def __init__(
        self,
        target_serialization_throughput: float = 10000.0,
        target_broadcast_throughput: float = 5000.0,
        target_batching_throughput: float = 1000.0,
        target_connection_throughput: float = 5000.0,
    ):
        """
        Initialize WebSocket benchmark.

        Args:
            target_serialization_throughput: Target message serializations/sec
            target_broadcast_throughput: Target broadcasts/sec
            target_batching_throughput: Target batched updates/sec
            target_connection_throughput: Target connection ops/sec
        """
        self.target_serialization_throughput = target_serialization_throughput
        self.target_broadcast_throughput = target_broadcast_throughput
        self.target_batching_throughput = target_batching_throughput
        self.target_connection_throughput = target_connection_throughput

        # Test data
        self._test_symbols = [
            "BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOTUSDT",
        ]

        logger.info("WebSocketBenchmark initialized")

    def _generate_market_update(self, symbol: str) -> Dict[str, Any]:
        """Generate a sample market data update message"""
        return {
            "type": "market_update",
            "symbol": symbol,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "price": round(random.uniform(10, 100000), 2),
                "bid": round(random.uniform(10, 100000), 2),
                "ask": round(random.uniform(10, 100000), 2),
                "volume_24h": round(random.uniform(1000000, 100000000), 2),
                "change_24h": round(random.uniform(-10, 10), 2),
                "high_24h": round(random.uniform(10, 100000), 2),
                "low_24h": round(random.uniform(10, 100000), 2),
            }
        }

    def _generate_position_update(self) -> Dict[str, Any]:
        """Generate a sample position update message"""
        return {
            "type": "position_update",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "positions": [
                {
                    "symbol": symbol,
                    "side": random.choice(["long", "short"]),
                    "size": round(random.uniform(0.1, 10), 4),
                    "entry_price": round(random.uniform(10, 100000), 2),
                    "current_price": round(random.uniform(10, 100000), 2),
                    "unrealized_pnl": round(random.uniform(-1000, 1000), 2),
                    "unrealized_pnl_pct": round(random.uniform(-10, 10), 2),
                }
                for symbol in self._test_symbols[:3]
            ]
        }

    def _generate_metrics_update(self) -> Dict[str, Any]:
        """Generate a sample metrics update message"""
        return {
            "type": "metrics_update",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "total_pnl": round(random.uniform(-10000, 50000), 2),
                "total_pnl_pct": round(random.uniform(-10, 50), 2),
                "win_rate": round(random.uniform(0.4, 0.7), 3),
                "sharpe_ratio": round(random.uniform(-1, 3), 3),
                "max_drawdown": round(random.uniform(-30, -5), 2),
                "trades_today": random.randint(0, 50),
                "portfolio_value": round(random.uniform(10000, 100000), 2),
            }
        }

    def benchmark_message_serialization(
        self,
        duration_seconds: float = 10.0
    ) -> BenchmarkResult:
        """
        Benchmark JSON message serialization.

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
            # Generate different message types
            if i % 3 == 0:
                message = self._generate_market_update(self._test_symbols[i % 5])
            elif i % 3 == 1:
                message = self._generate_position_update()
            else:
                message = self._generate_metrics_update()

            op_start = time.perf_counter()
            serialized = json.dumps(message)
            op_end = time.perf_counter()

            latencies.append((op_end - op_start) * 1000)
            operations += 1
            i += 1

        actual_duration = time.perf_counter() - start_time
        throughput = operations / actual_duration

        return BenchmarkResult(
            test_name="message_serialization",
            duration_seconds=actual_duration,
            total_operations=operations,
            throughput_per_sec=throughput,
            target_throughput=self.target_serialization_throughput,
            latencies_ms=latencies,
        )

    def benchmark_broadcast_simulation(
        self,
        duration_seconds: float = 10.0,
        num_connections: int = 100
    ) -> BenchmarkResult:
        """
        Benchmark broadcast to multiple connections (simulated).

        Args:
            duration_seconds: Test duration
            num_connections: Number of simulated connections

        Returns:
            BenchmarkResult with throughput metrics
        """
        latencies = []
        operations = 0

        # Setup connection manager
        manager = SimulatedConnectionManager()
        for i in range(num_connections):
            conn = manager.add_connection(f"conn_{i}")
            # Subscribe to random channels
            for symbol in self._test_symbols[:3]:
                manager.subscribe_to_channel(f"conn_{i}", f"market:{symbol}")

        start_time = time.perf_counter()
        end_time = start_time + duration_seconds

        async def run_broadcast():
            nonlocal operations
            i = 0
            while time.perf_counter() < end_time:
                message = self._generate_market_update(self._test_symbols[i % 5])
                serialized = json.dumps(message)
                channel = f"market:{self._test_symbols[i % 5]}"

                op_start = time.perf_counter()
                await manager.broadcast_to_channel(channel, serialized)
                op_end = time.perf_counter()

                latencies.append((op_end - op_start) * 1000)
                operations += 1
                i += 1

        asyncio.run(run_broadcast())

        actual_duration = time.perf_counter() - start_time
        throughput = operations / actual_duration

        return BenchmarkResult(
            test_name="broadcast_simulation",
            duration_seconds=actual_duration,
            total_operations=operations,
            throughput_per_sec=throughput,
            target_throughput=self.target_broadcast_throughput,
            latencies_ms=latencies,
            connections_simulated=num_connections,
        )

    def benchmark_update_batching(
        self,
        duration_seconds: float = 10.0,
        batch_size: int = 10
    ) -> BenchmarkResult:
        """
        Benchmark batched update creation and serialization.

        Args:
            duration_seconds: Test duration
            batch_size: Number of updates per batch

        Returns:
            BenchmarkResult with throughput metrics
        """
        latencies = []
        operations = 0
        start_time = time.perf_counter()
        end_time = start_time + duration_seconds

        while time.perf_counter() < end_time:
            op_start = time.perf_counter()

            # Create batched update
            batch = {
                "type": "batch_update",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "updates": []
            }

            for _ in range(batch_size):
                batch["updates"].append(
                    self._generate_market_update(random.choice(self._test_symbols))
                )

            # Serialize
            serialized = json.dumps(batch)

            op_end = time.perf_counter()

            latencies.append((op_end - op_start) * 1000)
            operations += 1

        actual_duration = time.perf_counter() - start_time
        throughput = operations / actual_duration

        return BenchmarkResult(
            test_name=f"update_batching_{batch_size}",
            duration_seconds=actual_duration,
            total_operations=operations,
            throughput_per_sec=throughput,
            target_throughput=self.target_batching_throughput,
            latencies_ms=latencies,
        )

    def benchmark_connection_management(
        self,
        duration_seconds: float = 10.0
    ) -> BenchmarkResult:
        """
        Benchmark connection add/remove/subscribe operations.

        Args:
            duration_seconds: Test duration

        Returns:
            BenchmarkResult with throughput metrics
        """
        latencies = []
        operations = 0
        start_time = time.perf_counter()
        end_time = start_time + duration_seconds

        manager = SimulatedConnectionManager()

        i = 0
        while time.perf_counter() < end_time:
            conn_id = f"conn_{i % 1000}"

            op_start = time.perf_counter()

            # Simulate connection lifecycle
            if i % 3 == 0:
                # Add connection
                manager.add_connection(conn_id)
            elif i % 3 == 1:
                # Subscribe to channel
                if conn_id in manager.connections:
                    manager.subscribe_to_channel(conn_id, f"market:{random.choice(self._test_symbols)}")
            else:
                # Remove connection
                if conn_id in manager.connections:
                    manager.remove_connection(conn_id)

            op_end = time.perf_counter()

            latencies.append((op_end - op_start) * 1000)
            operations += 1
            i += 1

        actual_duration = time.perf_counter() - start_time
        throughput = operations / actual_duration

        return BenchmarkResult(
            test_name="connection_management",
            duration_seconds=actual_duration,
            total_operations=operations,
            throughput_per_sec=throughput,
            target_throughput=self.target_connection_throughput,
            latencies_ms=latencies,
        )

    def benchmark_full_broadcast_cycle(
        self,
        duration_seconds: float = 10.0,
        num_connections: int = 50
    ) -> BenchmarkResult:
        """
        Benchmark full broadcast cycle (serialize + broadcast to all).

        Args:
            duration_seconds: Test duration
            num_connections: Number of simulated connections

        Returns:
            BenchmarkResult with throughput metrics
        """
        latencies = []
        operations = 0

        # Setup
        manager = SimulatedConnectionManager()
        for i in range(num_connections):
            manager.add_connection(f"conn_{i}")

        start_time = time.perf_counter()
        end_time = start_time + duration_seconds

        async def run_full_cycle():
            nonlocal operations
            i = 0
            while time.perf_counter() < end_time:
                # Generate message
                message = self._generate_metrics_update()

                op_start = time.perf_counter()

                # Serialize
                serialized = json.dumps(message)

                # Broadcast to all
                await manager.broadcast_to_all(serialized)

                op_end = time.perf_counter()

                latencies.append((op_end - op_start) * 1000)
                operations += 1
                i += 1

        asyncio.run(run_full_cycle())

        actual_duration = time.perf_counter() - start_time
        throughput = operations / actual_duration

        return BenchmarkResult(
            test_name="full_broadcast_cycle",
            duration_seconds=actual_duration,
            total_operations=operations,
            throughput_per_sec=throughput,
            target_throughput=self.target_broadcast_throughput / 2,  # Lower target for full cycle
            latencies_ms=latencies,
            connections_simulated=num_connections,
        )

    def run_all_benchmarks(
        self,
        duration_seconds: float = 10.0
    ) -> Dict[str, BenchmarkResult]:
        """
        Run all WebSocket benchmarks.

        Args:
            duration_seconds: Duration per test

        Returns:
            Dictionary of benchmark results
        """
        logger.info(f"Running all WebSocket benchmarks ({duration_seconds}s each)")

        results = {}

        logger.info("Benchmarking message serialization...")
        results["message_serialization"] = self.benchmark_message_serialization(duration_seconds)

        logger.info("Benchmarking broadcast simulation...")
        results["broadcast_simulation"] = self.benchmark_broadcast_simulation(duration_seconds)

        logger.info("Benchmarking update batching...")
        results["update_batching"] = self.benchmark_update_batching(duration_seconds)

        logger.info("Benchmarking connection management...")
        results["connection_management"] = self.benchmark_connection_management(duration_seconds)

        logger.info("Benchmarking full broadcast cycle...")
        results["full_broadcast_cycle"] = self.benchmark_full_broadcast_cycle(duration_seconds)

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
            "WEBSOCKET BENCHMARK REPORT",
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


def run_websocket_benchmark(duration_seconds: float = 10.0) -> Dict[str, BenchmarkResult]:
    """
    Convenience function to run WebSocket benchmarks.

    Args:
        duration_seconds: Duration per test

    Returns:
        Dictionary of benchmark results
    """
    benchmark = WebSocketBenchmark()
    results = benchmark.run_all_benchmarks(duration_seconds)
    benchmark.print_report(results)
    return results


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    results = run_websocket_benchmark(duration_seconds=10)

    all_pass = all(r.meets_target for r in results.values())
    exit(0 if all_pass else 1)
