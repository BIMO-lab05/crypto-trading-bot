"""
Unit tests for performance module
Tests monitoring, batching, and connection pooling
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from app.performance import (
    PerformanceMetric,
    PerformanceMonitor,
    RequestBatcher,
    ConnectionPool
)


class TestPerformanceMetric:
    """Test PerformanceMetric dataclass"""

    def test_create_metric(self):
        """Test creating performance metric"""
        metric = PerformanceMetric(
            endpoint="/api/v1/risk/scorecard",
            duration_ms=45.2,
            timestamp=datetime.now(),
            status="success",
            cache_hit=True
        )

        assert metric.endpoint == "/api/v1/risk/scorecard"
        assert metric.duration_ms == 45.2
        assert metric.status == "success"
        assert metric.cache_hit is True

    def test_default_values(self):
        """Test default metric values"""
        metric = PerformanceMetric(
            endpoint="/test",
            duration_ms=10.0,
            timestamp=datetime.now()
        )

        assert metric.status == "success"
        assert metric.cache_hit is False


class TestPerformanceMonitor:
    """Test PerformanceMonitor functionality"""

    @pytest.fixture
    def monitor(self):
        """Create monitor instance for testing"""
        return PerformanceMonitor(max_history=100)

    def test_initialization(self, monitor):
        """Test monitor initialization"""
        assert len(monitor.metrics) == 0
        assert len(monitor.endpoint_stats) == 0

    def test_record_metric(self, monitor):
        """Test recording a single metric"""
        metric = PerformanceMetric(
            endpoint="/api/test",
            duration_ms=50.0,
            timestamp=datetime.now()
        )

        monitor.record(metric)

        assert len(monitor.metrics) == 1
        assert "/api/test" in monitor.endpoint_stats
        assert monitor.endpoint_stats["/api/test"]["count"] == 1
        assert monitor.endpoint_stats["/api/test"]["total_time"] == 50.0

    def test_record_multiple_metrics(self, monitor):
        """Test recording multiple metrics"""
        for i in range(10):
            metric = PerformanceMetric(
                endpoint="/api/test",
                duration_ms=float(i * 10),
                timestamp=datetime.now()
            )
            monitor.record(metric)

        stats = monitor.endpoint_stats["/api/test"]
        assert stats["count"] == 10
        assert stats["total_time"] == 450.0  # Sum of 0+10+20+...+90
        assert stats["min_time"] == 0.0
        assert stats["max_time"] == 90.0

    def test_record_cache_hits(self, monitor):
        """Test tracking cache hits"""
        # Record some cache hits
        for i in range(7):
            metric = PerformanceMetric(
                endpoint="/api/test",
                duration_ms=5.0,
                timestamp=datetime.now(),
                cache_hit=True
            )
            monitor.record(metric)

        # Record some cache misses
        for i in range(3):
            metric = PerformanceMetric(
                endpoint="/api/test",
                duration_ms=50.0,
                timestamp=datetime.now(),
                cache_hit=False
            )
            monitor.record(metric)

        stats = monitor.endpoint_stats["/api/test"]
        assert stats["count"] == 10
        assert stats["cache_hits"] == 7

    def test_record_errors(self, monitor):
        """Test tracking errors"""
        # Record successes
        for i in range(95):
            metric = PerformanceMetric(
                endpoint="/api/test",
                duration_ms=10.0,
                timestamp=datetime.now(),
                status="success"
            )
            monitor.record(metric)

        # Record errors
        for i in range(5):
            metric = PerformanceMetric(
                endpoint="/api/test",
                duration_ms=100.0,
                timestamp=datetime.now(),
                status="error"
            )
            monitor.record(metric)

        stats = monitor.endpoint_stats["/api/test"]
        assert stats["count"] == 100
        assert stats["errors"] == 5

    @pytest.mark.asyncio
    async def test_measure_context_manager_success(self, monitor):
        """Test measure context manager with successful operation"""
        async with monitor.measure("/api/test"):
            await asyncio.sleep(0.01)  # Simulate work

        assert len(monitor.metrics) == 1
        assert monitor.metrics[0].endpoint == "/api/test"
        assert monitor.metrics[0].status == "success"
        assert monitor.metrics[0].duration_ms >= 10.0  # At least 10ms

    @pytest.mark.asyncio
    async def test_measure_context_manager_error(self, monitor):
        """Test measure context manager with error"""
        with pytest.raises(ValueError):
            async with monitor.measure("/api/test"):
                raise ValueError("Test error")

        assert len(monitor.metrics) == 1
        assert monitor.metrics[0].status == "error"

    def test_get_summary_empty(self, monitor):
        """Test summary with no metrics"""
        summary = monitor.get_summary()

        assert "message" in summary
        assert summary["message"] == "No metrics available"

    def test_get_summary(self, monitor):
        """Test summary calculation"""
        # Add metrics with known values
        durations = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
        for duration in durations:
            metric = PerformanceMetric(
                endpoint="/api/test",
                duration_ms=duration,
                timestamp=datetime.now(),
                cache_hit=(duration < 50)  # First 4 are cache hits
            )
            monitor.record(metric)

        summary = monitor.get_summary()

        assert summary["total_requests"] == 10
        assert summary["avg_response_time_ms"] == 55.0
        assert summary["min_response_time_ms"] == 10.0
        assert summary["max_response_time_ms"] == 100.0
        assert summary["cache_hit_rate_pct"] == 40.0
        assert summary["error_rate_pct"] == 0.0

    def test_get_summary_time_window(self, monitor):
        """Test summary with time window filter"""
        # Add old metrics
        old_time = datetime.now() - timedelta(minutes=10)
        for i in range(5):
            metric = PerformanceMetric(
                endpoint="/api/test",
                duration_ms=100.0,
                timestamp=old_time
            )
            monitor.record(metric)

        # Add recent metrics
        for i in range(5):
            metric = PerformanceMetric(
                endpoint="/api/test",
                duration_ms=10.0,
                timestamp=datetime.now()
            )
            monitor.record(metric)

        # Get summary for last 5 minutes (should only include recent metrics)
        summary = monitor.get_summary(last_minutes=5)

        assert summary["total_requests"] == 5
        assert summary["avg_response_time_ms"] == 10.0

    def test_get_endpoint_stats(self, monitor):
        """Test per-endpoint statistics"""
        # Add metrics for multiple endpoints
        for i in range(10):
            metric1 = PerformanceMetric(
                endpoint="/api/endpoint1",
                duration_ms=10.0,
                timestamp=datetime.now()
            )
            monitor.record(metric1)

        for i in range(5):
            metric2 = PerformanceMetric(
                endpoint="/api/endpoint2",
                duration_ms=50.0,
                timestamp=datetime.now(),
                cache_hit=True
            )
            monitor.record(metric2)

        stats = monitor.get_endpoint_stats()

        assert len(stats) == 2
        assert stats["/api/endpoint1"]["requests"] == 10
        assert stats["/api/endpoint1"]["avg_time_ms"] == 10.0
        assert stats["/api/endpoint2"]["requests"] == 5
        assert stats["/api/endpoint2"]["cache_hit_rate_pct"] == 100.0

    def test_max_history_limit(self):
        """Test that metrics history is limited"""
        monitor = PerformanceMonitor(max_history=10)

        # Add more metrics than max_history
        for i in range(20):
            metric = PerformanceMetric(
                endpoint="/api/test",
                duration_ms=float(i),
                timestamp=datetime.now()
            )
            monitor.record(metric)

        # Should only keep last 10
        assert len(monitor.metrics) == 10
        # Should have oldest metrics removed (newest retained)
        assert monitor.metrics[-1].duration_ms == 19.0


class TestRequestBatcher:
    """Test RequestBatcher functionality"""

    @pytest.fixture
    def batcher(self):
        """Create batcher instance for testing"""
        return RequestBatcher(batch_size=5, max_wait_ms=100)

    def test_initialization(self, batcher):
        """Test batcher initialization"""
        assert batcher.batch_size == 5
        assert batcher.max_wait_ms == 100
        assert len(batcher.pending) == 0

    @pytest.mark.asyncio
    async def test_execute_single_request(self, batcher):
        """Test executing single request"""
        async def mock_operation():
            await asyncio.sleep(0.01)
            return {"result": "success"}

        result = await batcher.execute("test_batch", mock_operation)

        assert result == {"result": "success"}

    @pytest.mark.asyncio
    async def test_batch_processing_by_size(self, batcher):
        """Test batch processing triggered by size"""
        call_count = 0

        async def mock_operation():
            nonlocal call_count
            call_count += 1
            return {"result": "success"}

        # Execute batch_size requests concurrently
        tasks = [
            batcher.execute("test_batch", mock_operation)
            for _ in range(5)
        ]

        results = await asyncio.gather(*tasks)

        # All requests should get same result
        assert all(r == {"result": "success"} for r in results)

        # Operation should only be called once (batched)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_batch_processing_by_timeout(self, batcher):
        """Test batch processing triggered by timeout"""
        batcher = RequestBatcher(batch_size=10, max_wait_ms=50)
        call_count = 0

        async def mock_operation():
            nonlocal call_count
            call_count += 1
            return {"result": "success"}

        # Execute only 2 requests (less than batch_size)
        tasks = [
            batcher.execute("test_batch", mock_operation)
            for _ in range(2)
        ]

        results = await asyncio.gather(*tasks)

        # Should still process after timeout
        assert all(r == {"result": "success"} for r in results)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_different_batch_keys(self, batcher):
        """Test requests with different batch keys are processed separately"""
        call_count_a = 0
        call_count_b = 0

        async def mock_operation_a():
            nonlocal call_count_a
            call_count_a += 1
            return {"result": "A"}

        async def mock_operation_b():
            nonlocal call_count_b
            call_count_b += 1
            return {"result": "B"}

        # Execute requests for different batch keys
        task_a = batcher.execute("batch_a", mock_operation_a)
        task_b = batcher.execute("batch_b", mock_operation_b)

        result_a, result_b = await asyncio.gather(task_a, task_b)

        assert result_a == {"result": "A"}
        assert result_b == {"result": "B"}
        assert call_count_a == 1
        assert call_count_b == 1

    @pytest.mark.asyncio
    async def test_error_propagation(self, batcher):
        """Test that errors are propagated to all requests in batch"""
        async def failing_operation():
            raise ValueError("Test error")

        tasks = [
            batcher.execute("test_batch", failing_operation)
            for _ in range(3)
        ]

        # All tasks should raise the same error
        for task in tasks:
            with pytest.raises(ValueError, match="Test error"):
                await task


class TestConnectionPool:
    """Test ConnectionPool functionality"""

    @pytest.fixture
    def pool(self):
        """Create pool instance for testing"""
        return ConnectionPool(max_connections=5, timeout=10.0)

    def test_initialization(self, pool):
        """Test pool initialization"""
        assert pool.max_connections == 5
        assert pool.timeout == 10.0
        assert pool.active_connections == 0

    @pytest.mark.asyncio
    async def test_acquire_connection(self, pool):
        """Test acquiring connection from pool"""
        async with pool.acquire():
            assert pool.active_connections == 1

        assert pool.active_connections == 0

    @pytest.mark.asyncio
    async def test_multiple_concurrent_connections(self, pool):
        """Test multiple concurrent connections"""
        async def use_connection():
            async with pool.acquire():
                await asyncio.sleep(0.01)
                return pool.active_connections

        # Start 3 concurrent tasks
        tasks = [use_connection() for _ in range(3)]
        results = await asyncio.gather(*tasks)

        # During execution, should have had up to 3 active connections
        assert max(results) <= 3

        # After completion, should be back to 0
        assert pool.active_connections == 0

    @pytest.mark.asyncio
    async def test_connection_limit(self, pool):
        """Test that connection limit is enforced"""
        pool = ConnectionPool(max_connections=2, timeout=10.0)

        active_at_once = []

        async def slow_operation():
            async with pool.acquire():
                active_at_once.append(pool.active_connections)
                await asyncio.sleep(0.05)

        # Try to run 5 operations concurrently with max_connections=2
        tasks = [slow_operation() for _ in range(5)]
        await asyncio.gather(*tasks)

        # Should never exceed max_connections
        assert max(active_at_once) <= 2

    @pytest.mark.asyncio
    async def test_connection_release_on_error(self, pool):
        """Test that connections are released even on error"""
        try:
            async with pool.acquire():
                assert pool.active_connections == 1
                raise ValueError("Test error")
        except ValueError:
            pass

        # Connection should be released after error
        assert pool.active_connections == 0

    def test_get_stats(self, pool):
        """Test getting pool statistics"""
        stats = pool.get_stats()

        assert stats["max_connections"] == 5
        assert stats["active_connections"] == 0
        assert stats["available_connections"] == 5

    @pytest.mark.asyncio
    async def test_stats_during_use(self, pool):
        """Test statistics while connections are in use"""
        async with pool.acquire():
            stats = pool.get_stats()

            assert stats["active_connections"] == 1
            assert stats["available_connections"] == 4


class TestPerformanceIntegration:
    """Integration tests for performance monitoring"""

    @pytest.mark.asyncio
    async def test_full_monitoring_workflow(self):
        """Test complete monitoring workflow"""
        monitor = PerformanceMonitor(max_history=100)

        # Simulate multiple requests
        async with monitor.measure("/api/test1"):
            await asyncio.sleep(0.01)

        async with monitor.measure("/api/test2", cache_hit=True):
            await asyncio.sleep(0.005)

        async with monitor.measure("/api/test1"):
            await asyncio.sleep(0.01)

        # Get statistics
        summary = monitor.get_summary()
        assert summary["total_requests"] == 3
        assert summary["cache_hit_rate_pct"] > 0

        endpoint_stats = monitor.get_endpoint_stats()
        assert "/api/test1" in endpoint_stats
        assert "/api/test2" in endpoint_stats
        assert endpoint_stats["/api/test1"]["requests"] == 2
        assert endpoint_stats["/api/test2"]["requests"] == 1

    @pytest.mark.asyncio
    async def test_monitor_with_pool(self):
        """Test monitoring combined with connection pool"""
        monitor = PerformanceMonitor()
        pool = ConnectionPool(max_connections=3)

        async def monitored_operation():
            async with monitor.measure("/api/test"):
                async with pool.acquire():
                    await asyncio.sleep(0.01)
                    return "success"

        # Run multiple operations
        tasks = [monitored_operation() for _ in range(5)]
        results = await asyncio.gather(*tasks)

        assert all(r == "success" for r in results)
        assert monitor.get_summary()["total_requests"] == 5
        assert pool.active_connections == 0  # All released
