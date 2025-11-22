#!/usr/bin/env python3
"""
Load Testing Suite for Crypto Trading Bot
Tests system performance under high concurrent load

Features:
- 100+ concurrent signal requests
- Latency benchmarking (target: <100ms)
- Throughput measurement
- Error rate tracking
- Response time percentiles
"""
import asyncio
import aiohttp
import time
import statistics
from typing import List, Dict, Tuple
from dataclasses import dataclass
from datetime import datetime
import json


@dataclass
class LoadTestResult:
    """Results from a load test"""
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_time: float
    requests_per_second: float
    avg_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    error_rate: float
    timeouts: int


class TradingBotLoadTester:
    """
    Load testing framework for trading bot services
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: int = 10
    ):
        self.base_url = base_url
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.results: List[Tuple[float, bool, int, str]] = []  # (latency, success, status, error)

    async def make_request(
        self,
        session: aiohttp.ClientSession,
        url: str,
        method: str = "GET",
        **kwargs
    ) -> Tuple[float, bool, int, str]:
        """
        Make a single HTTP request and measure latency

        Returns: (latency_ms, success, status_code, error_message)
        """
        start = time.time()
        error_msg = ""
        status = 0

        try:
            async with session.request(method, url, **kwargs) as response:
                await response.text()  # Ensure full response is received
                status = response.status
                latency_ms = (time.time() - start) * 1000
                success = 200 <= status < 300
                return (latency_ms, success, status, error_msg)

        except asyncio.TimeoutError:
            latency_ms = (time.time() - start) * 1000
            return (latency_ms, False, 0, "Timeout")

        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            return (latency_ms, False, status, str(e))

    async def concurrent_requests(
        self,
        url: str,
        num_requests: int,
        concurrency: int = 100,
        method: str = "GET",
        **kwargs
    ) -> List[Tuple[float, bool, int, str]]:
        """
        Send concurrent requests to a URL

        Args:
            url: Target URL
            num_requests: Total number of requests
            concurrency: Number of concurrent requests
            method: HTTP method

        Returns:
            List of (latency, success, status, error) tuples
        """
        connector = aiohttp.TCPConnector(limit=concurrency)

        async with aiohttp.ClientSession(
            timeout=self.timeout,
            connector=connector
        ) as session:
            tasks = []
            for _ in range(num_requests):
                task = self.make_request(session, url, method, **kwargs)
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Handle exceptions in results
            processed_results = []
            for result in results:
                if isinstance(result, Exception):
                    processed_results.append((0, False, 0, str(result)))
                else:
                    processed_results.append(result)

            return processed_results

    def analyze_results(
        self,
        results: List[Tuple[float, bool, int, str]],
        duration: float
    ) -> LoadTestResult:
        """
        Analyze load test results and calculate metrics
        """
        total = len(results)
        successful = sum(1 for _, success, _, _ in results if success)
        failed = total - successful
        timeouts = sum(1 for _, _, _, error in results if error == "Timeout")

        # Calculate latency statistics (only for successful requests)
        latencies = [latency for latency, success, _, _ in results if success]

        if latencies:
            avg_latency = statistics.mean(latencies)
            min_latency = min(latencies)
            max_latency = max(latencies)

            # Calculate percentiles
            sorted_latencies = sorted(latencies)
            p50 = sorted_latencies[int(len(sorted_latencies) * 0.50)]
            p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)]
            p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]
        else:
            avg_latency = min_latency = max_latency = p50 = p95 = p99 = 0

        rps = total / duration if duration > 0 else 0
        error_rate = (failed / total * 100) if total > 0 else 0

        return LoadTestResult(
            total_requests=total,
            successful_requests=successful,
            failed_requests=failed,
            total_time=duration,
            requests_per_second=rps,
            avg_latency_ms=avg_latency,
            min_latency_ms=min_latency,
            max_latency_ms=max_latency,
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            p99_latency_ms=p99,
            error_rate=error_rate,
            timeouts=timeouts
        )

    def print_results(self, result: LoadTestResult, test_name: str):
        """Print formatted test results"""
        print(f"\n{'='*80}")
        print(f"Load Test Results: {test_name}")
        print(f"{'='*80}")
        print(f"Total Requests:       {result.total_requests:,}")
        print(f"Successful:           {result.successful_requests:,} ({result.successful_requests/result.total_requests*100:.1f}%)")
        print(f"Failed:               {result.failed_requests:,} ({result.error_rate:.1f}%)")
        print(f"Timeouts:             {result.timeouts:,}")
        print(f"Duration:             {result.total_time:.2f}s")
        print(f"Requests/sec:         {result.requests_per_second:.2f}")
        print(f"\nLatency Statistics (ms):")
        print(f"  Average:            {result.avg_latency_ms:.2f} ms")
        print(f"  Min:                {result.min_latency_ms:.2f} ms")
        print(f"  Max:                {result.max_latency_ms:.2f} ms")
        print(f"  P50 (median):       {result.p50_latency_ms:.2f} ms")
        print(f"  P95:                {result.p95_latency_ms:.2f} ms")
        print(f"  P99:                {result.p99_latency_ms:.2f} ms")

        # Performance verdict
        print(f"\n{'─'*80}")
        if result.p99_latency_ms < 100:
            print("✅ PASSED: P99 latency < 100ms target")
        else:
            print(f"❌ FAILED: P99 latency {result.p99_latency_ms:.2f}ms exceeds 100ms target")

        if result.error_rate < 1:
            print("✅ PASSED: Error rate < 1%")
        else:
            print(f"⚠️  WARNING: Error rate {result.error_rate:.1f}% exceeds 1% threshold")

        print(f"{'='*80}\n")

    async def test_trading_signals(
        self,
        num_requests: int = 100,
        concurrency: int = 50,
        symbols: List[str] = None
    ) -> LoadTestResult:
        """
        Load test trading signal generation

        Args:
            num_requests: Total requests to make
            concurrency: Concurrent requests
            symbols: Trading symbols to test (default: BTCUSDT, ETHUSDT, BNBUSDT)
        """
        if symbols is None:
            symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

        print(f"🚀 Load Testing Trading Signals...")
        print(f"   Requests: {num_requests:,} | Concurrency: {concurrency} | Symbols: {len(symbols)}")

        start_time = time.time()

        # Distribute requests across symbols
        all_results = []
        requests_per_symbol = num_requests // len(symbols)

        for symbol in symbols:
            url = f"{self.base_url}/api/trading/signals/{symbol}?interval=60"
            results = await self.concurrent_requests(
                url,
                requests_per_symbol,
                concurrency
            )
            all_results.extend(results)

        duration = time.time() - start_time
        result = self.analyze_results(all_results, duration)
        self.print_results(result, "Trading Signal Generation")

        return result

    async def test_technical_indicators(
        self,
        num_requests: int = 100,
        concurrency: int = 50
    ) -> LoadTestResult:
        """
        Load test technical indicator calculations
        """
        print(f"🚀 Load Testing Technical Indicators...")
        print(f"   Requests: {num_requests:,} | Concurrency: {concurrency}")

        indicators = [
            "/api/analysis/rsi/BTCUSDT?interval=60",
            "/api/analysis/macd/BTCUSDT?interval=60",
            "/api/analysis/all/BTCUSDT?interval=60"
        ]

        start_time = time.time()
        all_results = []

        requests_per_indicator = num_requests // len(indicators)

        for indicator in indicators:
            url = f"{self.base_url}{indicator}"
            results = await self.concurrent_requests(
                url,
                requests_per_indicator,
                concurrency
            )
            all_results.extend(results)

        duration = time.time() - start_time
        result = self.analyze_results(all_results, duration)
        self.print_results(result, "Technical Indicators")

        return result

    async def test_multi_timeframe(
        self,
        num_requests: int = 100,
        concurrency: int = 30
    ) -> LoadTestResult:
        """
        Load test multi-timeframe analysis (more intensive)
        """
        print(f"🚀 Load Testing Multi-Timeframe Analysis...")
        print(f"   Requests: {num_requests:,} | Concurrency: {concurrency}")

        url = f"{self.base_url}/api/analysis/multi-timeframe/BTCUSDT"

        start_time = time.time()
        results = await self.concurrent_requests(url, num_requests, concurrency)
        duration = time.time() - start_time

        result = self.analyze_results(results, duration)
        self.print_results(result, "Multi-Timeframe Analysis")

        return result

    async def test_market_data(
        self,
        num_requests: int = 200,
        concurrency: int = 100
    ) -> LoadTestResult:
        """
        Load test market data retrieval (should be fast with caching)
        """
        print(f"🚀 Load Testing Market Data...")
        print(f"   Requests: {num_requests:,} | Concurrency: {concurrency}")

        url = f"{self.base_url}/api/market/ticker/BTCUSDT"

        start_time = time.time()
        results = await self.concurrent_requests(url, num_requests, concurrency)
        duration = time.time() - start_time

        result = self.analyze_results(results, duration)
        self.print_results(result, "Market Data Retrieval")

        return result

    async def run_full_load_test(
        self,
        light: bool = False
    ) -> Dict[str, LoadTestResult]:
        """
        Run comprehensive load test suite

        Args:
            light: If True, run lighter tests (fewer requests)
        """
        results = {}

        if light:
            print("\n" + "="*80)
            print(" LIGHT LOAD TEST MODE")
            print("="*80)
            num_requests = 50
            high_concurrency = 25
            low_concurrency = 15
        else:
            print("\n" + "="*80)
            print(" FULL LOAD TEST MODE")
            print("="*80)
            num_requests = 200
            high_concurrency = 100
            low_concurrency = 50

        # Test 1: Market Data (highest concurrency, should be cached)
        results['market_data'] = await self.test_market_data(
            num_requests=num_requests * 2,
            concurrency=high_concurrency
        )

        # Test 2: Technical Indicators
        results['technical_indicators'] = await self.test_technical_indicators(
            num_requests=num_requests,
            concurrency=high_concurrency
        )

        # Test 3: Trading Signals
        results['trading_signals'] = await self.test_trading_signals(
            num_requests=num_requests,
            concurrency=low_concurrency
        )

        # Test 4: Multi-Timeframe (most intensive)
        results['multi_timeframe'] = await self.test_multi_timeframe(
            num_requests=num_requests // 2,
            concurrency=low_concurrency // 2
        )

        # Print summary
        self.print_summary(results)

        return results

    def print_summary(self, results: Dict[str, LoadTestResult]):
        """Print overall test summary"""
        print("\n" + "="*80)
        print(" LOAD TEST SUMMARY")
        print("="*80)
        print(f"{'Test Name':<30} {'RPS':>10} {'Avg(ms)':>10} {'P99(ms)':>10} {'Error%':>10}")
        print("-"*80)

        for test_name, result in results.items():
            print(
                f"{test_name:<30} "
                f"{result.requests_per_second:>10.2f} "
                f"{result.avg_latency_ms:>10.2f} "
                f"{result.p99_latency_ms:>10.2f} "
                f"{result.error_rate:>10.1f}"
            )

        print("="*80)

        # Overall verdict
        all_passed = all(
            result.p99_latency_ms < 100 and result.error_rate < 1
            for result in results.values()
        )

        if all_passed:
            print("✅ ALL TESTS PASSED")
        else:
            print("⚠️  SOME TESTS FAILED - Review results above")

        print("="*80 + "\n")


async def main():
    """Main entry point for load testing"""
    import argparse

    parser = argparse.ArgumentParser(description="Trading Bot Load Tester")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL for API Gateway"
    )
    parser.add_argument(
        "--light",
        action="store_true",
        help="Run lighter tests (50 requests instead of 200)"
    )
    parser.add_argument(
        "--test",
        choices=['signals', 'indicators', 'market', 'multi-timeframe', 'all'],
        default='all',
        help="Specific test to run"
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=100,
        help="Number of requests for single test"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=50,
        help="Concurrent requests"
    )

    args = parser.parse_args()

    tester = TradingBotLoadTester(base_url=args.base_url)

    if args.test == 'all':
        await tester.run_full_load_test(light=args.light)
    elif args.test == 'signals':
        await tester.test_trading_signals(args.requests, args.concurrency)
    elif args.test == 'indicators':
        await tester.test_technical_indicators(args.requests, args.concurrency)
    elif args.test == 'market':
        await tester.test_market_data(args.requests, args.concurrency)
    elif args.test == 'multi-timeframe':
        await tester.test_multi_timeframe(args.requests, args.concurrency)


if __name__ == "__main__":
    asyncio.run(main())
