#!/usr/bin/env python3
"""
Stress Testing Script for Trading Engine
Purpose: Test system behavior under extreme load conditions

Scenarios:
- Concurrent signal requests
- Database connection pool exhaustion
- Memory pressure
- CPU intensive operations
"""

import asyncio
import httpx
import time
import psutil
import statistics
from typing import List, Dict
from dataclasses import dataclass
from datetime import datetime


@dataclass
class StressTestResult:
    """Results from a stress test run"""
    scenario: str
    total_requests: int
    successful: int
    failed: int
    avg_response_time: float
    p95_response_time: float
    p99_response_time: float
    max_response_time: float
    requests_per_second: float
    duration_seconds: float
    errors: List[str]


class TradingEngineStressTester:
    """Stress tester for Trading Engine API"""

    def __init__(self, base_url: str = "http://localhost:8005"):
        self.base_url = base_url
        self.results: List[StressTestResult] = []

    async def test_concurrent_signals(self, num_requests: int = 1000, concurrency: int = 50):
        """
        Test concurrent signal aggregation requests

        This tests the system's ability to handle many simultaneous
        requests for signal aggregation, which is the most critical path.
        """
        print(f"\n{'='*60}")
        print(f"STRESS TEST: Concurrent Signal Aggregation")
        print(f"Requests: {num_requests}, Concurrency: {concurrency}")
        print(f"{'='*60}\n")

        symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'ADAUSDT']
        intervals = ['15', '60', '240', '1440']

        response_times = []
        successful = 0
        failed = 0
        errors = []
        start_time = time.time()

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Create tasks
            tasks = []
            for i in range(num_requests):
                symbol = symbols[i % len(symbols)]
                interval = intervals[i % len(intervals)]
                tasks.append(self._make_signal_request(client, symbol, interval, response_times))

            # Execute in batches to control concurrency
            for i in range(0, len(tasks), concurrency):
                batch = tasks[i:i + concurrency]
                results = await asyncio.gather(*batch, return_exceptions=True)

                for result in results:
                    if isinstance(result, Exception):
                        failed += 1
                        errors.append(str(result))
                    elif result:
                        successful += 1
                    else:
                        failed += 1

        duration = time.time() - start_time

        # Calculate statistics
        result = StressTestResult(
            scenario="Concurrent Signal Aggregation",
            total_requests=num_requests,
            successful=successful,
            failed=failed,
            avg_response_time=statistics.mean(response_times) if response_times else 0,
            p95_response_time=statistics.quantiles(response_times, n=20)[18] if len(response_times) > 20 else 0,
            p99_response_time=statistics.quantiles(response_times, n=100)[98] if len(response_times) > 100 else 0,
            max_response_time=max(response_times) if response_times else 0,
            requests_per_second=num_requests / duration if duration > 0 else 0,
            duration_seconds=duration,
            errors=errors[:10]  # Keep first 10 errors
        )

        self.results.append(result)
        self._print_result(result)

    async def _make_signal_request(self, client: httpx.AsyncClient, symbol: str, interval: str, response_times: List[float]) -> bool:
        """Make a single signal request and record timing"""
        start = time.time()
        try:
            response = await client.get(
                f"{self.base_url}/api/v1/signals/aggregate",
                params={"symbol": symbol, "interval": interval}
            )
            duration = (time.time() - start) * 1000  # Convert to ms
            response_times.append(duration)
            return response.status_code in [200, 503]
        except Exception as e:
            duration = (time.time() - start) * 1000
            response_times.append(duration)
            return False

    async def test_rapid_health_checks(self, num_requests: int = 10000):
        """
        Test rapid health check requests

        Simulates monitoring systems hitting health endpoints repeatedly.
        """
        print(f"\n{'='*60}")
        print(f"STRESS TEST: Rapid Health Checks")
        print(f"Requests: {num_requests}")
        print(f"{'='*60}\n")

        response_times = []
        successful = 0
        failed = 0
        start_time = time.time()

        async with httpx.AsyncClient(timeout=10.0) as client:
            tasks = [
                self._make_health_request(client, response_times)
                for _ in range(num_requests)
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    failed += 1
                elif result:
                    successful += 1
                else:
                    failed += 1

        duration = time.time() - start_time

        result = StressTestResult(
            scenario="Rapid Health Checks",
            total_requests=num_requests,
            successful=successful,
            failed=failed,
            avg_response_time=statistics.mean(response_times) if response_times else 0,
            p95_response_time=statistics.quantiles(response_times, n=20)[18] if len(response_times) > 20 else 0,
            p99_response_time=statistics.quantiles(response_times, n=100)[98] if len(response_times) > 100 else 0,
            max_response_time=max(response_times) if response_times else 0,
            requests_per_second=num_requests / duration if duration > 0 else 0,
            duration_seconds=duration,
            errors=[]
        )

        self.results.append(result)
        self._print_result(result)

    async def _make_health_request(self, client: httpx.AsyncClient, response_times: List[float]) -> bool:
        """Make a single health check request"""
        start = time.time()
        try:
            response = await client.get(f"{self.base_url}/health")
            duration = (time.time() - start) * 1000
            response_times.append(duration)
            return response.status_code == 200
        except Exception:
            duration = (time.time() - start) * 1000
            response_times.append(duration)
            return False

    async def test_connection_pool_stress(self, num_connections: int = 100):
        """
        Test connection pool under stress

        Opens many concurrent connections to test pool limits.
        """
        print(f"\n{'='*60}")
        print(f"STRESS TEST: Connection Pool Stress")
        print(f"Concurrent Connections: {num_connections}")
        print(f"{'='*60}\n")

        response_times = []
        successful = 0
        failed = 0
        start_time = time.time()

        # Create many clients simultaneously
        async def make_request_with_own_client():
            start = time.time()
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(f"{self.base_url}/health")
                    duration = (time.time() - start) * 1000
                    response_times.append(duration)
                    return response.status_code == 200
            except Exception:
                duration = (time.time() - start) * 1000
                response_times.append(duration)
                return False

        tasks = [make_request_with_own_client() for _ in range(num_connections)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                failed += 1
            elif result:
                successful += 1
            else:
                failed += 1

        duration = time.time() - start_time

        result = StressTestResult(
            scenario="Connection Pool Stress",
            total_requests=num_connections,
            successful=successful,
            failed=failed,
            avg_response_time=statistics.mean(response_times) if response_times else 0,
            p95_response_time=statistics.quantiles(response_times, n=20)[18] if len(response_times) > 20 else 0,
            p99_response_time=statistics.quantiles(response_times, n=100)[98] if len(response_times) > 100 else 0,
            max_response_time=max(response_times) if response_times else 0,
            requests_per_second=num_connections / duration if duration > 0 else 0,
            duration_seconds=duration,
            errors=[]
        )

        self.results.append(result)
        self._print_result(result)

    def test_memory_usage(self):
        """Monitor memory usage during tests"""
        print(f"\n{'='*60}")
        print("SYSTEM RESOURCE MONITORING")
        print(f"{'='*60}\n")

        process = psutil.Process()
        memory_info = process.memory_info()
        cpu_percent = process.cpu_percent(interval=1.0)

        print(f"Memory Usage: {memory_info.rss / 1024 / 1024:.2f} MB")
        print(f"CPU Usage: {cpu_percent}%")
        print(f"Available Memory: {psutil.virtual_memory().available / 1024 / 1024:.2f} MB")
        print(f"CPU Count: {psutil.cpu_count()}")

    def _print_result(self, result: StressTestResult):
        """Print test results"""
        print(f"\nResults for: {result.scenario}")
        print(f"  Total Requests: {result.total_requests}")
        print(f"  Successful: {result.successful} ({result.successful/result.total_requests*100:.1f}%)")
        print(f"  Failed: {result.failed} ({result.failed/result.total_requests*100:.1f}%)")
        print(f"  Duration: {result.duration_seconds:.2f}s")
        print(f"  Throughput: {result.requests_per_second:.2f} req/s")
        print(f"  Response Time (avg): {result.avg_response_time:.2f}ms")
        print(f"  Response Time (p95): {result.p95_response_time:.2f}ms")
        print(f"  Response Time (p99): {result.p99_response_time:.2f}ms")
        print(f"  Response Time (max): {result.max_response_time:.2f}ms")

        if result.errors:
            print(f"\n  Sample Errors:")
            for error in result.errors[:5]:
                print(f"    - {error}")

    def generate_report(self):
        """Generate final summary report"""
        print(f"\n\n{'='*60}")
        print("STRESS TEST SUMMARY")
        print(f"{'='*60}\n")

        total_requests = sum(r.total_requests for r in self.results)
        total_successful = sum(r.successful for r in self.results)
        total_failed = sum(r.failed for r in self.results)

        print(f"Total Scenarios Run: {len(self.results)}")
        print(f"Total Requests: {total_requests}")
        print(f"Total Successful: {total_successful} ({total_successful/total_requests*100:.1f}%)")
        print(f"Total Failed: {total_failed} ({total_failed/total_requests*100:.1f}%)")

        print(f"\nScenario Breakdown:")
        for result in self.results:
            print(f"  {result.scenario}:")
            print(f"    Success Rate: {result.successful/result.total_requests*100:.1f}%")
            print(f"    Throughput: {result.requests_per_second:.2f} req/s")
            print(f"    Avg Response: {result.avg_response_time:.2f}ms")


async def main():
    """Run all stress tests"""
    tester = TradingEngineStressTester()

    print("\n" + "="*60)
    print("TRADING ENGINE STRESS TEST SUITE")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    # Check if service is up
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{tester.base_url}/health", timeout=5.0)
            if response.status_code != 200:
                print("\n❌ ERROR: Trading Engine is not healthy!")
                return
            print("\n✅ Trading Engine is healthy. Starting stress tests...\n")
    except Exception as e:
        print(f"\n❌ ERROR: Cannot connect to Trading Engine: {e}")
        return

    # Run stress tests
    try:
        await tester.test_rapid_health_checks(num_requests=5000)
        await tester.test_concurrent_signals(num_requests=500, concurrency=25)
        await tester.test_connection_pool_stress(num_connections=50)

        # Monitor resources
        tester.test_memory_usage()

        # Generate final report
        tester.generate_report()

    except KeyboardInterrupt:
        print("\n\n⚠️  Stress test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ ERROR during stress test: {e}")

    print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
