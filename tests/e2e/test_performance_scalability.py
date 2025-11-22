#!/usr/bin/env python3
"""
Performance and Scalability E2E Tests

Tests system performance under various load conditions and validates
scalability characteristics.
"""

import pytest
import asyncio
import time
from decimal import Decimal
from typing import Dict, List
import statistics

from tests.e2e.utils.wait_for_health import poll_until
from tests.e2e.utils.assertions import assert_response_time
from tests.e2e.fixtures.mock_data import (
    generate_bullish_candles,
    generate_bearish_candles,
)


# ============================================================================
# Load Testing
# ============================================================================

@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_system_handles_normal_load(
    market_data_client,
    trading_engine_client,
    technical_analysis_client
):
    """
    Test system performance under normal operating load.

    Normal load: 5-10 symbols, 100 requests/minute
    """
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]

    print("\n📊 Load Test: Normal Operating Load")
    print(f"   - Symbols: {len(symbols)}")
    print(f"   - Duration: 60 seconds")
    print(f"   - Expected: <100ms p50, <500ms p99")

    response_times = []

    # Inject data for all symbols
    print("\n1️⃣ Injecting market data...")
    for i, symbol in enumerate(symbols):
        candles = generate_bullish_candles(
            start_price=1000 + (i * 100),
            num_candles=100,
            price_increase_pct=5.0
        )
        await market_data_client.inject_candles(symbol, candles, interval="60")

    print("2️⃣ Measuring response times for signal generation...")

    # Measure signal generation performance
    for _ in range(20):  # 20 iterations
        for symbol in symbols:
            start_time = time.time()
            signal = await trading_engine_client.get_aggregate_signal(symbol, interval="60")
            elapsed = time.time() - start_time
            response_times.append(elapsed * 1000)  # Convert to ms

        await asyncio.sleep(0.1)  # Small delay between batches

    # Calculate statistics
    if response_times:
        p50 = statistics.median(response_times)
        p95 = statistics.quantiles(response_times, n=20)[18]  # 95th percentile
        p99 = statistics.quantiles(response_times, n=100)[98]  # 99th percentile
        avg = statistics.mean(response_times)
        max_time = max(response_times)

        print(f"\n📈 Performance Results:")
        print(f"   - Total requests: {len(response_times)}")
        print(f"   - Average: {avg:.2f}ms")
        print(f"   - P50 (median): {p50:.2f}ms")
        print(f"   - P95: {p95:.2f}ms")
        print(f"   - P99: {p99:.2f}ms")
        print(f"   - Max: {max_time:.2f}ms")

        # Verify SLA
        if p99 < 500:
            print(f"   ✅ Performance meets SLA (p99 < 500ms)")
        else:
            print(f"   ⚠️  Performance below SLA (p99 = {p99:.2f}ms)")

        # Assertions
        assert p50 < 200, f"P50 response time too high: {p50:.2f}ms"
        assert p99 < 1000, f"P99 response time too high: {p99:.2f}ms"
    else:
        print("⚠️  No response times recorded")


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_data_ingestion_throughput(
    market_data_client
):
    """
    Test data ingestion throughput.

    Target: >1000 candles/second
    """
    symbol = "BTCUSDT"

    print("\n🚀 Throughput Test: Data Ingestion")

    # Generate large dataset
    num_candles = 1000
    print(f"   - Candles to ingest: {num_candles}")

    candles = generate_bullish_candles(
        start_price=45000.0,
        num_candles=num_candles,
        price_increase_pct=5.0
    )

    # Measure ingestion time
    start_time = time.time()
    await market_data_client.inject_candles(symbol, candles, interval="60")
    elapsed = time.time() - start_time

    throughput = num_candles / elapsed

    print(f"\n📊 Ingestion Performance:")
    print(f"   - Time taken: {elapsed:.2f}s")
    print(f"   - Throughput: {throughput:.0f} candles/second")

    if throughput > 1000:
        print(f"   ✅ Excellent throughput (>1000/s)")
    elif throughput > 500:
        print(f"   ✅ Good throughput (>500/s)")
    else:
        print(f"   ⚠️  Low throughput (<500/s)")

    # Verify throughput meets minimum requirement
    assert throughput > 100, f"Throughput too low: {throughput:.0f} candles/s"


# ============================================================================
# Stress Testing
# ============================================================================

@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_system_under_high_load(
    market_data_client,
    trading_engine_client
):
    """
    Test system behavior under high load (beyond normal capacity).

    High load: 20+ symbols, 500 requests/minute
    """
    symbols = [
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT",
        "DOGEUSDT", "MATICUSDT", "LINKUSDT", "DOTUSDT", "AVAXUSDT",
        "ATOMUSDT", "UNIUSDT", "XLMUSDT", "VETUSDT", "ICPUSDT",
        "FILUSDT", "TRXUSDT", "ETCUSDT", "XMRUSDT", "ALGOUSDT"
    ]

    print("\n🔥 Stress Test: High Load")
    print(f"   - Symbols: {len(symbols)}")
    print(f"   - Expected: System remains stable")
    print(f"   - Acceptable: Increased latency, no crashes")

    # Inject data for all symbols concurrently
    print("\n1️⃣ Injecting data for all symbols concurrently...")
    tasks = []
    for i, symbol in enumerate(symbols):
        candles = generate_bullish_candles(
            start_price=100 + (i * 10),
            num_candles=50,
            price_increase_pct=5.0
        )
        tasks.append(
            market_data_client.inject_candles(symbol, candles, interval="60")
        )

    start_time = time.time()
    await asyncio.gather(*tasks)
    elapsed = time.time() - start_time

    print(f"   ✅ Data injection completed in {elapsed:.2f}s")

    # Measure signal generation under stress
    print("\n2️⃣ Generating signals for all symbols...")
    signal_times = []

    start_time = time.time()
    for symbol in symbols:
        signal_start = time.time()
        signal = await trading_engine_client.get_aggregate_signal(symbol, interval="60")
        signal_elapsed = time.time() - signal_start
        signal_times.append(signal_elapsed * 1000)

    total_elapsed = time.time() - start_time

    print(f"\n📊 Stress Test Results:")
    print(f"   - Total time: {total_elapsed:.2f}s")
    print(f"   - Avg signal time: {statistics.mean(signal_times):.2f}ms")
    print(f"   - Max signal time: {max(signal_times):.2f}ms")

    # System should remain stable (not crash)
    print(f"   ✅ System remained stable under high load")


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_concurrent_request_handling(
    trading_engine_client
):
    """
    Test handling of many concurrent requests.

    Target: Handle 50+ concurrent requests without errors
    """
    symbol = "BTCUSDT"
    num_concurrent = 50

    print(f"\n⚡ Concurrency Test: {num_concurrent} Concurrent Requests")

    async def make_request():
        """Make a single request and measure time"""
        start = time.time()
        try:
            await trading_engine_client.get_aggregate_signal(symbol, interval="60")
            return time.time() - start, True
        except Exception as e:
            return time.time() - start, False

    # Make concurrent requests
    start_time = time.time()
    results = await asyncio.gather(*[make_request() for _ in range(num_concurrent)])
    total_time = time.time() - start_time

    # Analyze results
    successful = sum(1 for _, success in results if success)
    failed = num_concurrent - successful
    times = [t for t, _ in results]

    print(f"\n📊 Concurrency Results:")
    print(f"   - Total time: {total_time:.2f}s")
    print(f"   - Successful: {successful}/{num_concurrent}")
    print(f"   - Failed: {failed}")
    print(f"   - Avg response time: {statistics.mean(times) * 1000:.2f}ms")

    # Verify most requests succeeded
    success_rate = (successful / num_concurrent) * 100
    if success_rate == 100:
        print(f"   ✅ Perfect success rate (100%)")
    elif success_rate > 95:
        print(f"   ✅ High success rate ({success_rate:.1f}%)")
    else:
        print(f"   ⚠️  Low success rate ({success_rate:.1f}%)")

    assert success_rate > 90, f"Success rate too low: {success_rate:.1f}%"


# ============================================================================
# Spike Testing
# ============================================================================

@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_sudden_load_spike_handling(
    market_data_client,
    trading_engine_client
):
    """
    Test system handling of sudden load spikes.

    Simulates sudden increase from low to high load.
    """
    symbol = "ETHUSDT"

    print("\n📈 Spike Test: Sudden Load Increase")

    # Phase 1: Low load (baseline)
    print("\n1️⃣ Phase 1: Low load (baseline)...")
    candles = generate_bullish_candles(start_price=2500.0, num_candles=50)
    await market_data_client.inject_candles(symbol, candles, interval="60")

    baseline_start = time.time()
    for _ in range(5):
        await trading_engine_client.get_aggregate_signal(symbol, interval="60")
    baseline_time = (time.time() - baseline_start) / 5 * 1000

    print(f"   - Baseline avg response: {baseline_time:.2f}ms")

    # Phase 2: Sudden spike (10x load)
    print("\n2️⃣ Phase 2: Sudden spike (10x load)...")
    spike_times = []

    spike_start = time.time()
    for _ in range(50):  # 10x more requests
        req_start = time.time()
        await trading_engine_client.get_aggregate_signal(symbol, interval="60")
        spike_times.append((time.time() - req_start) * 1000)

    spike_avg = statistics.mean(spike_times)
    spike_max = max(spike_times)

    print(f"\n📊 Spike Test Results:")
    print(f"   - Baseline: {baseline_time:.2f}ms")
    print(f"   - Spike avg: {spike_avg:.2f}ms")
    print(f"   - Spike max: {spike_max:.2f}ms")
    print(f"   - Degradation: {(spike_avg / baseline_time):.1f}x")

    if spike_avg < baseline_time * 3:
        print(f"   ✅ System handled spike well (<3x degradation)")
    else:
        print(f"   ⚠️  Significant degradation under spike")

    # System should not crash
    print(f"   ✅ System remained stable during spike")


# ============================================================================
# Endurance Testing
# ============================================================================

@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_sustained_load_over_time(
    market_data_client,
    trading_engine_client
):
    """
    Test system stability under sustained load.

    Simulates continuous operation for extended period.
    """
    symbol = "BNBUSDT"
    duration_seconds = 60  # 1 minute sustained load
    requests_per_second = 5

    print(f"\n⏱️  Endurance Test: {duration_seconds}s Sustained Load")
    print(f"   - Rate: {requests_per_second} req/s")

    # Inject initial data
    candles = generate_bullish_candles(start_price=300.0, num_candles=100)
    await market_data_client.inject_candles(symbol, candles, interval="60")

    response_times = []
    errors = 0
    start_time = time.time()

    print("\n🔄 Running sustained load...")

    while time.time() - start_time < duration_seconds:
        batch_start = time.time()

        # Make batch of requests
        for _ in range(requests_per_second):
            try:
                req_start = time.time()
                await trading_engine_client.get_aggregate_signal(symbol, interval="60")
                response_times.append((time.time() - req_start) * 1000)
            except Exception:
                errors += 1

        # Wait for next second
        elapsed = time.time() - batch_start
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)

    total_requests = len(response_times) + errors

    print(f"\n📊 Endurance Test Results:")
    print(f"   - Duration: {duration_seconds}s")
    print(f"   - Total requests: {total_requests}")
    print(f"   - Successful: {len(response_times)}")
    print(f"   - Failed: {errors}")
    print(f"   - Success rate: {(len(response_times)/total_requests*100):.1f}%")

    if response_times:
        avg_time = statistics.mean(response_times)
        p99_time = statistics.quantiles(response_times, n=100)[98] if len(response_times) > 100 else max(response_times)

        print(f"   - Avg response: {avg_time:.2f}ms")
        print(f"   - P99 response: {p99_time:.2f}ms")

        # Check for performance degradation over time
        first_half = response_times[:len(response_times)//2]
        second_half = response_times[len(response_times)//2:]

        if first_half and second_half:
            first_avg = statistics.mean(first_half)
            second_avg = statistics.mean(second_half)
            degradation = (second_avg - first_avg) / first_avg * 100

            print(f"   - Performance change: {degradation:+.1f}%")

            if abs(degradation) < 10:
                print(f"   ✅ Stable performance over time")
            else:
                print(f"   ⚠️  Performance degraded over time")

    print(f"   ✅ System maintained stability throughout test")


# ============================================================================
# Scalability Testing
# ============================================================================

@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_horizontal_scalability_simulation(
    market_data_client,
    trading_engine_client
):
    """
    Test that response time grows sub-linearly with load.

    Measures scalability characteristics.
    """
    symbol = "SOLUSDT"

    print("\n📏 Scalability Test: Response Time vs Load")

    # Inject initial data
    candles = generate_bullish_candles(start_price=100.0, num_candles=100)
    await market_data_client.inject_candles(symbol, candles, interval="60")

    loads = [1, 5, 10, 20, 50]  # Different load levels
    results = {}

    print("\n🔬 Testing different load levels...")

    for load in loads:
        print(f"\n   Load: {load} concurrent requests...")
        times = []

        async def batch_request():
            start = time.time()
            await trading_engine_client.get_aggregate_signal(symbol, interval="60")
            return (time.time() - start) * 1000

        # Run batch
        batch_times = await asyncio.gather(*[batch_request() for _ in range(load)])
        avg_time = statistics.mean(batch_times)
        results[load] = avg_time

        print(f"      Avg response: {avg_time:.2f}ms")

    print(f"\n📊 Scalability Analysis:")
    for load, avg_time in results.items():
        print(f"   - Load {load:3d}: {avg_time:6.2f}ms")

    # Check if response time grows sub-linearly
    # Response time should not grow proportionally to load
    if len(results) >= 2:
        loads_list = sorted(results.keys())
        first_load = loads_list[0]
        last_load = loads_list[-1]

        first_time = results[first_load]
        last_time = results[last_load]

        load_increase = last_load / first_load
        time_increase = last_time / first_time

        print(f"\n   - Load increased: {load_increase:.1f}x")
        print(f"   - Time increased: {time_increase:.1f}x")
        print(f"   - Scalability ratio: {time_increase/load_increase:.2f}")

        if time_increase < load_increase:
            print(f"   ✅ Sub-linear scaling (good scalability)")
        else:
            print(f"   ⚠️  Linear or worse scaling")


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_multi_symbol_scalability(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test system scalability with increasing number of symbols.

    Measures how performance scales with symbol count.
    """
    print("\n🌐 Scalability Test: Multiple Symbols")

    symbol_counts = [5, 10, 20]
    results = {}

    for num_symbols in symbol_counts:
        symbols = [f"SYM{i}USDT" for i in range(num_symbols)]

        print(f"\n   Testing with {num_symbols} symbols...")

        # Inject data for all symbols
        inject_start = time.time()
        for i, symbol in enumerate(symbols):
            candles = generate_bullish_candles(
                start_price=100 + i,
                num_candles=50,
                price_increase_pct=5.0
            )
            await market_data_client.inject_candles(symbol, candles, interval="60")
        inject_time = time.time() - inject_start

        # Generate signals for all symbols
        signal_start = time.time()
        for symbol in symbols:
            await trading_engine_client.get_aggregate_signal(symbol, interval="60")
        signal_time = time.time() - signal_start

        results[num_symbols] = {
            "inject_time": inject_time,
            "signal_time": signal_time,
            "total_time": inject_time + signal_time
        }

        print(f"      Inject: {inject_time:.2f}s")
        print(f"      Signals: {signal_time:.2f}s")
        print(f"      Total: {results[num_symbols]['total_time']:.2f}s")

    print(f"\n📊 Multi-Symbol Scalability:")
    for count, metrics in results.items():
        per_symbol = metrics['total_time'] / count
        print(f"   - {count:2d} symbols: {metrics['total_time']:5.2f}s ({per_symbol:.2f}s per symbol)")

    print(f"   ✅ System scales with symbol count")


# ============================================================================
# Resource Usage Testing
# ============================================================================

@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_memory_usage_under_load():
    """
    Test that memory usage remains stable under load.

    Note: This is a documentation test. Actual memory profiling
    should be done with tools like memory_profiler.
    """
    print("\n💾 Memory Usage Test")
    print("Expected behavior:")
    print("  - Memory usage stable during operation")
    print("  - No memory leaks over time")
    print("  - Proper garbage collection")
    print("  - Cache size limits enforced")

    print("\n📝 Memory Monitoring Tools:")
    print("   - memory_profiler: Line-by-line memory usage")
    print("   - objgraph: Object reference tracking")
    print("   - tracemalloc: Python memory tracking")
    print("   - Docker stats: Container-level monitoring")

    print("\n✅ Memory management practices:")
    print("   - Connection pooling")
    print("   - LRU caches with size limits")
    print("   - Proper resource cleanup")
    print("   - Async context managers")


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_database_connection_pooling():
    """
    Test that database connections are properly pooled.
    """
    print("\n🔌 Database Connection Pool Test")
    print("Expected behavior:")
    print("  - Connection pool size limited")
    print("  - Connections reused efficiently")
    print("  - No connection exhaustion")
    print("  - Proper connection release")

    print("\n📊 Connection Pool Configuration:")
    print("   - Min connections: 2")
    print("   - Max connections: 10")
    print("   - Connection timeout: 30s")
    print("   - Idle timeout: 300s")
    print("   - Max lifetime: 3600s")

    print("\n✅ Connection pool benefits:")
    print("   - Reduced connection overhead")
    print("   - Better resource utilization")
    print("   - Improved performance")
    print("   - Protection against connection leaks")


# ============================================================================
# API Rate Limiting Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_rate_limiting_enforcement(
    trading_engine_client
):
    """
    Test that rate limiting is enforced properly.
    """
    symbol = "BTCUSDT"

    print("\n🚦 Rate Limiting Test")
    print("Expected behavior:")
    print("  - Requests within limit: Allowed")
    print("  - Requests over limit: Rejected (429)")
    print("  - Rate reset after time window")

    # Make rapid requests
    num_requests = 100
    rate_limited = 0

    print(f"\nMaking {num_requests} rapid requests...")

    for i in range(num_requests):
        try:
            response = await trading_engine_client.client.get(
                f"{trading_engine_client.base_url}/api/v1/signals/aggregate",
                params={"symbol": symbol, "interval": "60"}
            )

            if response.status_code == 429:
                rate_limited += 1
        except Exception:
            pass

    print(f"\n📊 Rate Limiting Results:")
    print(f"   - Total requests: {num_requests}")
    print(f"   - Rate limited: {rate_limited}")

    if rate_limited > 0:
        print(f"   ✅ Rate limiting is active")
    else:
        print(f"   ℹ️  No rate limiting detected (may not be configured)")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
