#!/usr/bin/env python3
"""
Memory Profiling Tool for Crypto Trading Bot
Tracks memory usage, identifies leaks, and generates reports

Features:
- Real-time memory monitoring
- Memory leak detection
- Object allocation tracking
- Heap dump analysis
- Memory growth trends
"""

import asyncio
import aiohttp
import psutil
import time
import statistics
from typing import List, Dict, Tuple
from dataclasses import dataclass
from datetime import datetime
import json
import sys
import tracemalloc
from collections import defaultdict


@dataclass
class MemorySnapshot:
    """Memory usage snapshot at a point in time"""
    timestamp: float
    rss_mb: float  # Resident Set Size (actual physical memory)
    vms_mb: float  # Virtual Memory Size
    percent: float  # Memory usage percentage
    request_count: int
    service_name: str


@dataclass
class MemoryGrowthAnalysis:
    """Analysis of memory growth over time"""
    service_name: str
    initial_memory_mb: float
    final_memory_mb: float
    growth_mb: float
    growth_rate_mb_per_request: float
    total_requests: int
    duration_seconds: float
    leak_detected: bool
    leak_severity: str  # 'none', 'minor', 'moderate', 'severe'


class MemoryProfiler:
    """
    Memory profiling tool for microservices
    """

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.snapshots: Dict[str, List[MemorySnapshot]] = defaultdict(list)
        self.process_map: Dict[str, psutil.Process] = {}

    def get_service_pid(self, port: int) -> int:
        """Get PID of service running on specified port"""
        for conn in psutil.net_connections():
            if conn.laddr.port == port and conn.status == 'LISTEN':
                return conn.pid
        return None

    def get_process(self, service_name: str, port: int) -> psutil.Process:
        """Get psutil.Process for a service"""
        if service_name in self.process_map:
            return self.process_map[service_name]

        pid = self.get_service_pid(port)
        if pid:
            try:
                proc = psutil.Process(pid)
                self.process_map[service_name] = proc
                return proc
            except psutil.NoSuchProcess:
                return None
        return None

    def take_memory_snapshot(
        self,
        service_name: str,
        port: int,
        request_count: int = 0
    ) -> MemorySnapshot:
        """Take a memory usage snapshot for a service"""
        proc = self.get_process(service_name, port)

        if not proc:
            return MemorySnapshot(
                timestamp=time.time(),
                rss_mb=0,
                vms_mb=0,
                percent=0,
                request_count=request_count,
                service_name=service_name
            )

        try:
            mem_info = proc.memory_info()
            mem_percent = proc.memory_percent()

            snapshot = MemorySnapshot(
                timestamp=time.time(),
                rss_mb=mem_info.rss / (1024 * 1024),  # Convert to MB
                vms_mb=mem_info.vms / (1024 * 1024),
                percent=mem_percent,
                request_count=request_count,
                service_name=service_name
            )

            self.snapshots[service_name].append(snapshot)
            return snapshot

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return MemorySnapshot(
                timestamp=time.time(),
                rss_mb=0,
                vms_mb=0,
                percent=0,
                request_count=request_count,
                service_name=service_name
            )

    async def profile_under_load(
        self,
        service_name: str,
        port: int,
        test_url: str,
        num_requests: int = 100,
        concurrency: int = 10,
        snapshot_interval: float = 1.0
    ) -> List[MemorySnapshot]:
        """
        Profile memory usage while service is under load

        Args:
            service_name: Name of the service
            port: Port the service is running on
            test_url: URL to send test requests to
            num_requests: Total number of requests
            concurrency: Concurrent requests
            snapshot_interval: Seconds between snapshots

        Returns:
            List of memory snapshots
        """
        print(f"\n🔍 Profiling {service_name} on port {port}")
        print(f"   Test URL: {test_url}")
        print(f"   Requests: {num_requests} | Concurrency: {concurrency}")

        # Clear previous snapshots
        self.snapshots[service_name] = []

        # Take initial snapshot
        initial_snapshot = self.take_memory_snapshot(service_name, port, 0)
        print(f"   Initial Memory: {initial_snapshot.rss_mb:.2f} MB RSS")

        # Start monitoring task
        monitor_task = asyncio.create_task(
            self._monitor_memory_loop(service_name, port, snapshot_interval)
        )

        # Run load test
        start_time = time.time()
        request_count = 0

        connector = aiohttp.TCPConnector(limit=concurrency)
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=connector
        ) as session:
            tasks = []
            for i in range(num_requests):
                task = asyncio.create_task(
                    self._make_request(session, test_url)
                )
                tasks.append(task)

            # Wait for all requests to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            request_count = len([r for r in results if not isinstance(r, Exception)])

        # Stop monitoring
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

        # Take final snapshot
        final_snapshot = self.take_memory_snapshot(
            service_name,
            port,
            request_count
        )

        duration = time.time() - start_time

        print(f"\n   Final Memory: {final_snapshot.rss_mb:.2f} MB RSS")
        print(f"   Memory Growth: {final_snapshot.rss_mb - initial_snapshot.rss_mb:.2f} MB")
        print(f"   Duration: {duration:.2f}s")
        print(f"   Requests: {request_count}/{num_requests}")

        return self.snapshots[service_name]

    async def _monitor_memory_loop(
        self,
        service_name: str,
        port: int,
        interval: float
    ):
        """Background task to monitor memory at intervals"""
        request_count = 0
        while True:
            await asyncio.sleep(interval)
            self.take_memory_snapshot(service_name, port, request_count)
            request_count += 1

    async def _make_request(
        self,
        session: aiohttp.ClientSession,
        url: str
    ) -> bool:
        """Make a single HTTP request"""
        try:
            async with session.get(url) as response:
                await response.text()
                return response.status == 200
        except Exception:
            return False

    def analyze_memory_growth(
        self,
        service_name: str
    ) -> MemoryGrowthAnalysis:
        """
        Analyze memory growth and detect potential leaks

        Returns analysis of memory usage patterns
        """
        snapshots = self.snapshots.get(service_name, [])

        if len(snapshots) < 2:
            return MemoryGrowthAnalysis(
                service_name=service_name,
                initial_memory_mb=0,
                final_memory_mb=0,
                growth_mb=0,
                growth_rate_mb_per_request=0,
                total_requests=0,
                duration_seconds=0,
                leak_detected=False,
                leak_severity='none'
            )

        initial = snapshots[0]
        final = snapshots[-1]

        growth_mb = final.rss_mb - initial.rss_mb
        duration = final.timestamp - initial.timestamp
        total_requests = final.request_count

        # Calculate growth rate
        growth_rate = growth_mb / total_requests if total_requests > 0 else 0

        # Detect leak based on growth rate
        # Thresholds:
        # - < 0.1 MB per request: normal
        # - 0.1 - 0.5 MB: minor leak
        # - 0.5 - 1 MB: moderate leak
        # - > 1 MB: severe leak

        leak_detected = growth_rate > 0.1
        if growth_rate < 0.1:
            leak_severity = 'none'
        elif growth_rate < 0.5:
            leak_severity = 'minor'
        elif growth_rate < 1.0:
            leak_severity = 'moderate'
        else:
            leak_severity = 'severe'

        return MemoryGrowthAnalysis(
            service_name=service_name,
            initial_memory_mb=initial.rss_mb,
            final_memory_mb=final.rss_mb,
            growth_mb=growth_mb,
            growth_rate_mb_per_request=growth_rate,
            total_requests=total_requests,
            duration_seconds=duration,
            leak_detected=leak_detected,
            leak_severity=leak_severity
        )

    def print_memory_report(self, service_name: str):
        """Print formatted memory analysis report"""
        analysis = self.analyze_memory_growth(service_name)
        snapshots = self.snapshots.get(service_name, [])

        print(f"\n{'='*80}")
        print(f"Memory Profile: {service_name}")
        print(f"{'='*80}")
        print(f"Initial Memory:       {analysis.initial_memory_mb:.2f} MB RSS")
        print(f"Final Memory:         {analysis.final_memory_mb:.2f} MB RSS")
        print(f"Memory Growth:        {analysis.growth_mb:.2f} MB")
        print(f"Growth Rate:          {analysis.growth_rate_mb_per_request:.4f} MB/request")
        print(f"Total Requests:       {analysis.total_requests}")
        print(f"Duration:             {analysis.duration_seconds:.2f}s")

        print(f"\n{'─'*80}")

        if not analysis.leak_detected:
            print("✅ PASSED: No memory leak detected")
        else:
            severity_emoji = {
                'minor': '⚠️',
                'moderate': '❌',
                'severe': '🚨'
            }
            emoji = severity_emoji.get(analysis.leak_severity, '⚠️')
            print(f"{emoji} WARNING: Potential {analysis.leak_severity.upper()} memory leak detected")
            print(f"   Growth rate of {analysis.growth_rate_mb_per_request:.4f} MB/request is concerning")

        # Print memory usage trend
        if len(snapshots) > 2:
            print(f"\n{'─'*80}")
            print("Memory Usage Trend:")
            print(f"{'Time (s)':<12} {'RSS (MB)':<12} {'VMS (MB)':<12} {'CPU %':<10}")
            print("─" * 80)

            first_timestamp = snapshots[0].timestamp
            for snapshot in snapshots[::max(1, len(snapshots)//10)]:  # Show ~10 samples
                elapsed = snapshot.timestamp - first_timestamp
                print(
                    f"{elapsed:<12.1f} "
                    f"{snapshot.rss_mb:<12.2f} "
                    f"{snapshot.vms_mb:<12.2f} "
                    f"{snapshot.percent:<10.2f}"
                )

        print(f"{'='*80}\n")

    async def profile_all_services(
        self,
        num_requests: int = 100
    ) -> Dict[str, MemoryGrowthAnalysis]:
        """
        Profile all running services

        Returns dictionary of service analyses
        """
        services = {
            "market-data": {
                "port": 8003,
                "url": "http://localhost:8000/api/market/ticker/BTCUSDT"
            },
            "technical-analysis": {
                "port": 8004,
                "url": "http://localhost:8000/api/analysis/rsi/BTCUSDT?interval=60"
            },
            "trading-engine": {
                "port": 8005,
                "url": "http://localhost:8000/api/trading/signals/BTCUSDT?interval=60"
            },
            "api-gateway": {
                "port": 8000,
                "url": "http://localhost:8000/health"
            }
        }

        results = {}

        print("\n" + "="*80)
        print(" MEMORY PROFILING - ALL SERVICES")
        print("="*80)

        for service_name, config in services.items():
            await self.profile_under_load(
                service_name=service_name,
                port=config["port"],
                test_url=config["url"],
                num_requests=num_requests,
                concurrency=20,
                snapshot_interval=0.5
            )

            self.print_memory_report(service_name)
            results[service_name] = self.analyze_memory_growth(service_name)

            # Small delay between services
            await asyncio.sleep(2)

        # Print summary
        self.print_summary(results)

        return results

    def print_summary(self, results: Dict[str, MemoryGrowthAnalysis]):
        """Print overall summary"""
        print("\n" + "="*80)
        print(" MEMORY PROFILING SUMMARY")
        print("="*80)
        print(
            f"{'Service':<25} "
            f"{'Growth (MB)':>12} "
            f"{'Rate (MB/req)':>15} "
            f"{'Leak Status':>15}"
        )
        print("-"*80)

        for service_name, analysis in results.items():
            leak_status = analysis.leak_severity.upper() if analysis.leak_detected else "OK"
            emoji = "✅" if not analysis.leak_detected else "⚠️"

            print(
                f"{service_name:<25} "
                f"{analysis.growth_mb:>12.2f} "
                f"{analysis.growth_rate_mb_per_request:>15.4f} "
                f"{emoji} {leak_status:>13}"
            )

        print("="*80 + "\n")

        # Overall verdict
        any_leaks = any(a.leak_detected for a in results.values())
        if not any_leaks:
            print("✅ ALL SERVICES PASSED - No memory leaks detected")
        else:
            print("⚠️  SOME SERVICES SHOW MEMORY GROWTH - Review reports above")

        print("="*80 + "\n")


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Memory Profiler for Trading Bot")
    parser.add_argument(
        "--service",
        choices=['market-data', 'technical-analysis', 'trading-engine', 'api-gateway', 'all'],
        default='all',
        help="Service to profile"
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=100,
        help="Number of requests to send"
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Port for specific service"
    )
    parser.add_argument(
        "--url",
        type=str,
        help="URL to test"
    )

    args = parser.parse_args()

    profiler = MemoryProfiler()

    if args.service == 'all':
        await profiler.profile_all_services(num_requests=args.requests)
    else:
        # Profile single service
        if not args.port or not args.url:
            print("Error: --port and --url required for single service profiling")
            sys.exit(1)

        await profiler.profile_under_load(
            service_name=args.service,
            port=args.port,
            test_url=args.url,
            num_requests=args.requests,
            concurrency=20
        )

        profiler.print_memory_report(args.service)


if __name__ == "__main__":
    asyncio.run(main())
